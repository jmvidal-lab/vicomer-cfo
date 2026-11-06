#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cartera_v2.py — Cartera REAL de un cliente en Odoo (VINTRAL).

Responde 4 preguntas de gerencia:
  1. Cuanto me debe REALMENTE (neto de notas de credito y anticipos sin aplicar)
  2. Que tan vencido esta (por fecha de vencimiento real, cuota por cuota)
  3. Cuantos dias se demora en pagar DE VERDAD (historico, no foto)
  4. Cuanto le facture vs cuanto me pago, mes a mes

Uso:
    python3 cartera_v2.py
    python3 cartera_v2.py --cliente "casa magna"
    python3 cartera_v2.py --meses 24
    python3 cartera_v2.py --ids 496

Solo lectura: NO modifica nada en Odoo.
"""

import os, sys, json, ssl, csv, argparse, datetime, xmlrpc.client
try:  # proxy HTTPS para xmlrpc (no-op en el Mac)
    import sys as _s, os as _o
    _d = _o.path.dirname(_o.path.abspath(__file__))
    for _p in (_d, _o.path.dirname(_d)):
        if _o.path.exists(_o.path.join(_p, 'odoo_proxy.py')) and _p not in _s.path: _s.path.append(_p)
    import odoo_proxy
except ImportError:
    pass
from pathlib import Path
from collections import defaultdict

HOME = Path.home()
PROJ = HOME / "Claude" / "Projects" / "CFO VICOMER"
OUT_DIR = Path(os.environ.get("ODOO_OUT_DIR", PROJ / "OdooVentas"))


# --------------------------------------------------------------- config
def load_config():
    cfg = {"url": os.environ.get("ODOO_URL"), "db": os.environ.get("ODOO_DB"),
           "login": os.environ.get("ODOO_LOGIN"), "apikey": os.environ.get("ODOO_APIKEY")}
    for f in (HOME / ".odoo_config.json", PROJ / "odoo_config.json"):
        if f.exists():
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                for k in ("url", "db", "login", "apikey"):
                    cfg[k] = cfg[k] or d.get(k)
            except Exception as e:
                print(f"[WARN] no se pudo leer {f}: {e}")
    for kf in (HOME / ".odoo_apikey", PROJ / "odoo_apikey.txt"):
        if not cfg["apikey"] and kf.exists():
            cfg["apikey"] = kf.read_text(encoding="utf-8").strip()
    if cfg.get("url"):
        cfg["url"] = cfg["url"].rstrip("/")
    faltan = [k for k in ("url", "login", "apikey") if not cfg.get(k)]
    if faltan:
        sys.exit("ERROR: faltan credenciales de Odoo: " + ", ".join(faltan))
    return cfg


# --------------------------------------------------------------- conexion
class Odoo:
    def __init__(self, cfg):
        self.cfg = cfg
        ctx = ssl.create_default_context()
        self.common = xmlrpc.client.ServerProxy(f"{cfg['url']}/xmlrpc/2/common", allow_none=True, context=ctx)
        self.models = xmlrpc.client.ServerProxy(f"{cfg['url']}/xmlrpc/2/object", allow_none=True, context=ctx)
        self.uid = None

    def _dbs(self):
        cands = []
        if self.cfg.get("db"):
            cands.append(self.cfg["db"])
        host = self.cfg["url"].split("//")[-1].split("/")[0]
        cands += [host.split(".")[0], host]
        try:
            dbp = xmlrpc.client.ServerProxy(f"{self.cfg['url']}/xmlrpc/2/db",
                                            allow_none=True, context=ssl.create_default_context())
            listed = dbp.list()
            if isinstance(listed, list):
                cands += listed
        except Exception:
            pass
        seen, out = set(), []
        for c in cands:
            if c and c not in seen:
                seen.add(c); out.append(c)
        return out

    def authenticate(self):
        last = None
        for db in self._dbs():
            try:
                uid = self.common.authenticate(db, self.cfg["login"], self.cfg["apikey"], {})
            except Exception as e:
                last = str(e)[:200]; continue
            if uid:
                self.cfg["db"] = db
                self.uid = uid
                return uid
        sys.exit(f"ERROR: no autentico con ninguna base. Ultimo error: {last}")

    def sr(self, model, domain, fields, limit=0, ctx=None):
        kw = {"fields": fields}
        if limit:
            kw["limit"] = limit
        if ctx:
            kw["context"] = ctx
        return self.models.execute_kw(self.cfg["db"], self.uid, self.cfg["apikey"],
                                      model, "search_read", [domain], kw)

    def sr_safe(self, model, domain, fields, **kw):
        """Reintenta quitando campos que la version de Odoo no tenga."""
        f = list(fields)
        for _ in range(len(fields) + 1):
            try:
                return self.sr(model, domain, f, **kw), f
            except Exception as e:
                msg = str(e)
                dropped = None
                for c in list(f):
                    if c in msg and c not in ("id",):
                        dropped = c; break
                if not dropped:
                    raise
                f.remove(dropped)
        raise RuntimeError("no se pudo consultar " + model)


# --------------------------------------------------------------- utils
def m2o_name(v):
    return v[1] if isinstance(v, (list, tuple)) and len(v) == 2 else ""

def d(s):
    try:
        return datetime.date.fromisoformat(str(s)[:10])
    except Exception:
        return None

def money(n):
    neg = n < 0
    s = f"{abs(round(n)):,}".replace(",", ".")
    return ("-" + s) if neg else s

def chunks(lst, n=400):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


# --------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Cartera real de un cliente (Odoo)")
    ap.add_argument("--cliente", default="casa magna")
    ap.add_argument("--ids", default="")
    ap.add_argument("--meses", type=int, default=18, help="Ventana historica en meses")
    args = ap.parse_args()

    cfg = load_config()
    od = Odoo(cfg)
    od.authenticate()
    print(f"[OK] Odoo {cfg['url']} db='{cfg['db']}' user={cfg['login']}")

    hoy = datetime.date.today()
    desde = (hoy.replace(day=1) - datetime.timedelta(days=31 * args.meses)).replace(day=1)

    # ---------- partner ----------
    if args.ids.strip():
        partner_ids = [int(x) for x in args.ids.split(",") if x.strip()]
        nombres = [f"#{i}" for i in partner_ids]
    else:
        term = args.cliente.replace(" ", "%")
        ps = od.sr("res.partner", ["|", ("name", "ilike", term), ("name", "ilike", args.cliente)],
                   ["id", "name", "active"], ctx={"active_test": False})
        partner_ids = [p["id"] for p in ps]
        nombres = [p["name"] for p in ps]
        arch = [p["name"] for p in ps if not p.get("active", True)]
        if arch:
            print(f"[!] Contactos ARCHIVADOS incluidos: {', '.join(arch)}")
    if not partner_ids:
        sys.exit(f"No se encontro cliente '{args.cliente}'")
    titulo = nombres[0] if nombres else args.cliente
    print(f"[OK] Cliente(s): {', '.join(f'{n}' for n in nombres)}")

    # ---------- lineas por cobrar abiertas ----------
    base = [("partner_id", "child_of", partner_ids), ("parent_state", "=", "posted")]
    dom_open = None
    for cond in [("account_id.account_type", "=", "asset_receivable"),
                 ("account_id.internal_type", "=", "receivable"),
                 ("account_id.user_type_id.type", "=", "receivable")]:
        try:
            test = od.sr("account.move.line", base + [cond], ["id"], limit=1)
            dom_open = base + [cond]
            break
        except Exception:
            continue
    if dom_open is None:
        sys.exit("ERROR: no pude identificar la cuenta por cobrar en este Odoo.")

    LF = ["id", "move_id", "move_name", "date", "date_maturity", "amount_residual",
          "amount_residual_currency", "currency_id", "company_currency_id",
          "debit", "credit", "reconciled", "partner_id"]
    abiertas, LF = od.sr_safe("account.move.line",
                              dom_open + [("reconciled", "=", False), ("amount_residual", "!=", 0)], LF)

    # tipo de documento de cada apunte
    move_ids = sorted({(l.get("move_id") or [None])[0] for l in abiertas if l.get("move_id")})
    tipos = {}
    for ch in chunks(move_ids):
        for m in od.sr("account.move", [("id", "in", ch)], ["id", "move_type", "name", "invoice_date_due"]):
            tipos[m["id"]] = m

    facturas, ncs, pagos_sueltos = [], [], []
    for l in abiertas:
        mv = tipos.get((l.get("move_id") or [None])[0], {})
        mt = mv.get("move_type", "entry")
        r = {
            "doc": mv.get("name") or l.get("move_name") or "",
            "tipo": mt,
            "fecha": l.get("date"),
            "vence": l.get("date_maturity") or l.get("date"),
            "saldo": l.get("amount_residual") or 0.0,
        }
        v = d(r["vence"])
        r["dias"] = (hoy - v).days if v else 0
        if mt == "out_invoice":
            facturas.append(r)
        elif mt == "out_refund":
            ncs.append(r)
        else:
            pagos_sueltos.append(r)

    tot_fac = sum(r["saldo"] for r in facturas)
    tot_nc = sum(r["saldo"] for r in ncs)
    tot_pag = sum(r["saldo"] for r in pagos_sueltos)
    neto = tot_fac + tot_nc + tot_pag

    # ---------- aging ----------
    BK = ["Corriente", "1-30", "31-60", "61-90", "91-180", ">180"]
    def bucket(x):
        if x <= 0: return BK[0]
        if x <= 30: return BK[1]
        if x <= 60: return BK[2]
        if x <= 90: return BK[3]
        if x <= 180: return BK[4]
        return BK[5]
    ag = defaultdict(float); agn = defaultdict(int)
    for r in facturas:
        ag[bucket(r["dias"])] += r["saldo"]; agn[bucket(r["dias"])] += 1

    # ---------- comportamiento de pago historico ----------
    hist, LH = od.sr_safe("account.move.line",
                          dom_open + [("debit", ">", 0), ("date", ">=", desde.isoformat())],
                          ["id", "move_name", "date", "date_maturity", "debit"])
    hmap = {l["id"]: l for l in hist}
    partials = []
    if hmap:
        for ch in chunks(list(hmap.keys())):
            try:
                partials += od.sr("account.partial.reconcile", [("debit_move_id", "in", ch)],
                                  ["debit_move_id", "amount", "max_date"])
            except Exception:
                break

    num = den = 0.0
    peor = None
    pagos_por_mes = defaultdict(float)
    for p in partials:
        li = (p.get("debit_move_id") or [None])[0]
        l = hmap.get(li)
        if not l:
            continue
        fp = d(p.get("max_date"))
        fv = d(l.get("date_maturity") or l.get("date"))
        amt = p.get("amount") or 0.0
        if fp:
            pagos_por_mes[fp.strftime("%Y-%m")] += amt
        if not (fp and fv) or amt <= 0:
            continue
        dias = (fp - fv).days
        num += amt * dias; den += amt
        if peor is None or dias > peor[1]:
            peor = (l.get("move_name") or "?", dias, amt)
    mora_real = (num / den) if den else None

    # ---------- facturado por mes ----------
    fac_hist = od.sr("account.move",
                     [("partner_id", "child_of", partner_ids), ("state", "=", "posted"),
                      ("move_type", "in", ["out_invoice", "out_refund"]),
                      ("invoice_date", ">=", desde.isoformat())],
                     ["invoice_date", "amount_total_signed", "move_type"])
    fact_por_mes = defaultdict(float)
    for f in fac_hist:
        fd = d(f.get("invoice_date"))
        if fd:
            fact_por_mes[fd.strftime("%Y-%m")] += f.get("amount_total_signed") or 0.0

    # ---------- pagos sin aplicar ----------
    pay, LP = od.sr_safe("account.payment",
                         [("partner_id", "child_of", partner_ids), ("state", "not in", ["draft", "cancel"]),
                          ("date", ">=", desde.isoformat())],
                         ["id", "name", "date", "amount", "payment_type", "is_matched", "state"])
    entrantes = [p for p in pay if p.get("payment_type") in (None, "inbound")]
    sin_aplicar = [p for p in entrantes if p.get("is_matched") is False]

    # =========================== SALIDA ===========================
    W = 78
    print("\n" + "=" * W)
    print(f"  CARTERA REAL — {titulo} — corte {hoy.isoformat()}")
    print("=" * W)

    print("\n1) CUANTO ME DEBE REALMENTE")
    print(f"   Facturas pendientes            {money(tot_fac):>18}   ({len(facturas)} docs)")
    print(f"   Notas de credito abiertas      {money(tot_nc):>18}   ({len(ncs)} docs)")
    print(f"   Pagos/anticipos sin aplicar    {money(tot_pag):>18}   ({len(pagos_sueltos)} docs)")
    print("   " + "-" * 52)
    print(f"   CARTERA NETA REAL              {money(neto):>18}")
    if abs(tot_nc + tot_pag) > 0:
        print(f"   >> El reporte anterior sobreestimaba en {money(-(tot_nc + tot_pag))}")

    print("\n2) ANTIGUEDAD DE LAS FACTURAS")
    for b in BK:
        if b in ag:
            pct = ag[b] / tot_fac * 100 if tot_fac else 0
            print(f"   {b:12} {money(ag[b]):>18}  {pct:5.1f}%   ({agn[b]} fact.)")
    venc = sum(v for k, v in ag.items() if k != "Corriente")
    print("   " + "-" * 52)
    print(f"   VENCIDO      {money(venc):>18}  {venc/tot_fac*100 if tot_fac else 0:5.1f}%")

    print(f"\n3) COMPORTAMIENTO DE PAGO REAL (ultimos {args.meses} meses)")
    if mora_real is not None:
        print(f"   Se demora {mora_real:.0f} dias DESPUES del vencimiento, en promedio ponderado.")
        if peor:
            print(f"   Peor caso: {peor[0]} pagada {peor[1]} dias tarde ({money(peor[2])})")
        print(f"   (base: {money(den)} efectivamente cobrados y conciliados)")
    else:
        print("   No se pudo calcular (sin conciliaciones legibles en la ventana).")

    print(f"\n4) FACTURADO vs COBRADO POR MES")
    meses = sorted(set(list(fact_por_mes.keys()) + list(pagos_por_mes.keys())))
    print(f"   {'Mes':9} {'Facturado':>16} {'Cobrado':>16} {'Diferencia':>16} {'Acumulado':>16}")
    acum = 0.0
    tf = tc = 0.0
    for m in meses:
        f_ = fact_por_mes.get(m, 0.0); c_ = pagos_por_mes.get(m, 0.0)
        acum += f_ - c_; tf += f_; tc += c_
        print(f"   {m:9} {money(f_):>16} {money(c_):>16} {money(f_-c_):>16} {money(acum):>16}")
    print("   " + "-" * 70)
    print(f"   {'TOTAL':9} {money(tf):>16} {money(tc):>16} {money(tf-tc):>16}")
    if tf:
        print(f"   >> Te pago el {tc/tf*100:.0f}% de lo que le facturaste en el periodo.")

    print("\n5) ALERTAS")
    alertas = 0
    for r in ncs:
        print(f"   [NC SIN APLICAR] {r['doc']:14} {money(r['saldo']):>16}  emitida {r['fecha']}")
        alertas += 1
    for p in sin_aplicar:
        print(f"   [PAGO SIN APLICAR] {p.get('name') or '?':14} {money(p.get('amount') or 0):>16}  {p.get('date')}")
        alertas += 1
    for r in facturas:
        if r["dias"] > 90:
            print(f"   [+90 DIAS] {r['doc']:14} {money(r['saldo']):>16}  {r['dias']} dias")
            alertas += 1
    if not alertas:
        print("   Ninguna.")
    print("=" * W)

    # ---------- CSV ----------
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = hoy.strftime("%Y%m%d")
    slug = "".join(c for c in titulo.lower().replace(" ", "_") if c.isalnum() or c == "_")[:24]
    cpath = OUT_DIR / f"cartera_real_{slug}_{stamp}.csv"
    with open(cpath, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["documento", "tipo", "fecha", "vence", "dias_vencido", "saldo", "aging"])
        for r in sorted(facturas + ncs + pagos_sueltos, key=lambda x: -x["dias"]):
            w.writerow([r["doc"], r["tipo"], r["fecha"], r["vence"], r["dias"],
                        f"{r['saldo']:.2f}".replace(".", ","), bucket(r["dias"])])
    mpath = OUT_DIR / f"cartera_real_{slug}_{stamp}_mensual.csv"
    with open(mpath, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["mes", "facturado", "cobrado", "diferencia"])
        for m in meses:
            f_ = fact_por_mes.get(m, 0.0); c_ = pagos_por_mes.get(m, 0.0)
            w.writerow([m, f"{f_:.2f}".replace(".", ","), f"{c_:.2f}".replace(".", ","),
                        f"{f_-c_:.2f}".replace(".", ",")])
    print(f"\nGuardado:\n  {cpath}\n  {mpath}")


if __name__ == "__main__":
    main()
