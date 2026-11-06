#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cartera_v3.py — Cartera REAL de un cliente en Odoo (VINTRAL).

v3: NO consulta el modelo account.move. La base tiene el modulo l10n_ec a medio
instalar (falta la columna account_move.l10n_ec_sri_import_withhold), asi que
cualquier lectura de account.move revienta. Todo se obtiene de account.move.line,
que no dispara ese bug. El tipo de documento se infiere del prefijo del nombre.

Uso:
    python3 cartera_v3.py
    python3 cartera_v3.py --cliente "casa magna"
    python3 cartera_v3.py --meses 24

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
                self.cfg["db"] = db; self.uid = uid
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

    def sr_drop(self, model, domain, fields, **kw):
        """Reintenta quitando de a un campo hasta que la consulta pase."""
        f = list(fields)
        while f:
            try:
                return self.sr(model, domain, f, **kw), f
            except Exception as e:
                msg = str(e)
                drop = next((c for c in f if c in msg and c != "id"), None)
                if drop is None:
                    drop = f[-1] if len(f) > 1 else None
                if drop is None:
                    raise
                f.remove(drop)
                print(f"    [.] campo '{drop}' no disponible, se omite")
        raise RuntimeError("no se pudo consultar " + model)


def d(s):
    try:
        return datetime.date.fromisoformat(str(s)[:10])
    except Exception:
        return None

def money(n):
    neg = n < 0
    return ("-" if neg else "") + f"{abs(round(n)):,}".replace(",", ".")

def chunks(lst, n=400):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

def clasificar(nombre):
    """Infiere el tipo de documento por el prefijo del nombre (evita account.move)."""
    n = (nombre or "").upper().strip()
    if not n:
        return "otro"
    if n.startswith(("RNC", "NC", "RC")):
        return "nota_credito"
    if "MISC" in n or n.startswith(("CE", "TEF", "BNK", "CSH", "PAY")):
        return "refinanciada_o_pago"
    if n.startswith(("FE", "FV", "INV", "FAC")):
        return "factura"
    return "otro"


def main():
    ap = argparse.ArgumentParser(description="Cartera real de un cliente (Odoo) — v3")
    ap.add_argument("--cliente", default="casa magna")
    ap.add_argument("--ids", default="")
    ap.add_argument("--meses", type=int, default=18)
    args = ap.parse_args()

    cfg = load_config()
    od = Odoo(cfg); od.authenticate()
    print(f"[OK] Odoo {cfg['url']} db='{cfg['db']}'")

    hoy = datetime.date.today()
    desde = (hoy.replace(day=1) - datetime.timedelta(days=31 * args.meses)).replace(day=1)

    # ---------- partners ----------
    if args.ids.strip():
        partner_ids = [int(x) for x in args.ids.split(",") if x.strip()]
        pnames = {i: f"#{i}" for i in partner_ids}
    else:
        term = args.cliente.replace(" ", "%")
        ps = od.sr("res.partner", ["|", ("name", "ilike", term), ("name", "ilike", args.cliente)],
                   ["id", "name", "active"], ctx={"active_test": False})
        partner_ids = [p["id"] for p in ps]
        pnames = {p["id"]: p["name"] for p in ps}
        arch = [p["name"] for p in ps if not p.get("active", True)]
        if arch:
            print(f"[!] ARCHIVADOS incluidos: {', '.join(arch)}")
    if not partner_ids:
        sys.exit(f"No se encontro cliente '{args.cliente}'")
    print(f"[OK] {len(partner_ids)} contacto(s): {', '.join(list(pnames.values())[:4])}"
          + (" ..." if len(pnames) > 4 else ""))
    titulo = args.cliente.upper()

    # ---------- dominio de cuenta por cobrar ----------
    base = [("partner_id", "child_of", partner_ids), ("parent_state", "=", "posted")]
    dom = None
    for cond in [("account_id.account_type", "=", "asset_receivable"),
                 ("account_id.internal_type", "=", "receivable"),
                 ("account_id.user_type_id.type", "=", "receivable")]:
        try:
            od.sr("account.move.line", base + [cond], ["id"], limit=1)
            dom = base + [cond]; break
        except Exception:
            continue
    if dom is None:
        sys.exit("ERROR: no pude identificar la cuenta por cobrar.")

    # ---------- lineas abiertas (SIN move_id: evita el bug de l10n_ec) ----------
    CAMPOS = ["id", "move_name", "date", "date_maturity", "amount_residual",
              "debit", "credit", "partner_id"]
    abiertas, _ = od.sr_drop("account.move.line",
                             dom + [("reconciled", "=", False), ("amount_residual", "!=", 0)],
                             CAMPOS)

    filas = []
    for l in abiertas:
        nom = l.get("move_name") or ""
        saldo = l.get("amount_residual") or 0.0
        venc = l.get("date_maturity") or l.get("date")
        v = d(venc)
        pid = (l.get("partner_id") or [None, ""])
        filas.append({
            "doc": nom,
            "tipo": clasificar(nom),
            "cliente": pid[1] if isinstance(pid, (list, tuple)) and len(pid) > 1 else "",
            "fecha": l.get("date"),
            "vence": venc,
            "dias": (hoy - v).days if v else 0,
            "saldo": saldo,
        })

    # descartar residuos de conciliacion
    ruido = [f for f in filas if abs(f["saldo"]) < 1000]
    filas = [f for f in filas if abs(f["saldo"]) >= 1000]

    facturas = [f for f in filas if f["tipo"] == "factura"]
    refin = [f for f in filas if f["tipo"] == "refinanciada_o_pago"]
    ncs = [f for f in filas if f["tipo"] == "nota_credito"]
    otros = [f for f in filas if f["tipo"] == "otro"]

    t_fac = sum(f["saldo"] for f in facturas)
    t_ref = sum(f["saldo"] for f in refin)
    t_nc = sum(f["saldo"] for f in ncs)
    t_ot = sum(f["saldo"] for f in otros)
    neto = t_fac + t_ref + t_nc + t_ot

    BK = ["Corriente", "1-30", "31-60", "61-90", "91-180", ">180"]
    def bucket(x):
        if x <= 0: return BK[0]
        if x <= 30: return BK[1]
        if x <= 60: return BK[2]
        if x <= 90: return BK[3]
        if x <= 180: return BK[4]
        return BK[5]

    ag_f = defaultdict(float); n_f = defaultdict(int)
    for f in facturas:
        b = bucket(f["dias"]); ag_f[b] += f["saldo"]; n_f[b] += 1
    venc_fac = sum(v for k, v in ag_f.items() if k != "Corriente")

    # ---------- historico: facturado (debitos) y cobrado (partials) ----------
    hist, _ = od.sr_drop("account.move.line",
                         dom + [("debit", ">", 0), ("date", ">=", desde.isoformat())],
                         ["id", "move_name", "date", "date_maturity", "debit"])
    hmap = {l["id"]: l for l in hist}

    fact_mes = defaultdict(float)
    for l in hist:
        if clasificar(l.get("move_name")) != "factura":
            continue
        fd = d(l.get("date"))
        if fd:
            fact_mes[fd.strftime("%Y-%m")] += l.get("debit") or 0.0

    partials = []
    for ch in chunks(list(hmap.keys())):
        try:
            partials += od.sr("account.partial.reconcile", [("debit_move_id", "in", ch)],
                              ["debit_move_id", "amount", "max_date"])
        except Exception as e:
            print(f"    [.] no se pudieron leer conciliaciones: {str(e)[:70]}")
            break

    cobr_mes = defaultdict(float)
    num = den = 0.0; peor = None
    for p in partials:
        li = (p.get("debit_move_id") or [None])[0]
        l = hmap.get(li)
        if not l: continue
        fp = d(p.get("max_date")); amt = p.get("amount") or 0.0
        if fp: cobr_mes[fp.strftime("%Y-%m")] += amt
        fv = d(l.get("date_maturity") or l.get("date"))
        if not (fp and fv) or amt <= 0: continue
        dias = (fp - fv).days
        num += amt * dias; den += amt
        if peor is None or dias > peor[1]:
            peor = (l.get("move_name") or "?", dias, amt)
    mora_real = (num / den) if den else None

    # =========================== SALIDA ===========================
    W = 76
    print("\n" + "=" * W)
    print(f"  CARTERA REAL — {titulo} — corte {hoy.isoformat()}")
    print("=" * W)

    print("\n1) CUANTO DEBE")
    print(f"   Facturas pendientes             {money(t_fac):>18}   ({len(facturas)} docs)")
    print(f"   Refinanciada / asientos         {money(t_ref):>18}   ({len(refin)} docs)")
    if ncs:
        print(f"   Notas de credito abiertas       {money(t_nc):>18}   ({len(ncs)} docs)")
    if otros:
        print(f"   Otros documentos                {money(t_ot):>18}   ({len(otros)} docs)")
    print("   " + "-" * 54)
    print(f"   CARTERA TOTAL                   {money(neto):>18}")
    if ruido:
        print(f"   (se excluyeron {len(ruido)} residuos de conciliacion < $1.000)")

    print("\n2) ANTIGUEDAD DE LAS FACTURAS (sin la refinanciada)")
    for b in BK:
        if b in ag_f:
            pct = ag_f[b] / t_fac * 100 if t_fac else 0
            print(f"   {b:12} {money(ag_f[b]):>18}  {pct:5.1f}%   ({n_f[b]} fact.)")
    print("   " + "-" * 54)
    print(f"   VENCIDO      {money(venc_fac):>18}  {venc_fac/t_fac*100 if t_fac else 0:5.1f}%")

    print(f"\n3) COMPORTAMIENTO DE PAGO REAL (ultimos {args.meses} meses)")
    if mora_real is not None:
        print(f"   Paga {mora_real:.0f} dias DESPUES del vencimiento (promedio ponderado)")
        if peor:
            print(f"   Peor caso: {peor[0]} pagada {peor[1]} dias tarde ({money(peor[2])})")
        print(f"   Base: {money(den)} conciliados")
    else:
        print("   No se pudo calcular.")

    print("\n4) FACTURADO vs COBRADO POR MES")
    meses = sorted(set(list(fact_mes.keys()) + list(cobr_mes.keys())))
    print(f"   {'Mes':9} {'Facturado':>16} {'Cobrado':>16} {'Diferencia':>16}")
    tf = tc = 0.0
    for m in meses:
        f_ = fact_mes.get(m, 0.0); c_ = cobr_mes.get(m, 0.0)
        tf += f_; tc += c_
        print(f"   {m:9} {money(f_):>16} {money(c_):>16} {money(f_-c_):>16}")
    print("   " + "-" * 60)
    print(f"   {'TOTAL':9} {money(tf):>16} {money(tc):>16} {money(tf-tc):>16}")

    print("\n5) ALERTAS")
    al = 0
    for r in sorted(ncs, key=lambda x: x["saldo"]):
        print(f"   [NC ABIERTA] {r['doc']:20} {money(r['saldo']):>16}"); al += 1
    for r in sorted([f for f in facturas if f["dias"] > 60], key=lambda x: -x["dias"])[:15]:
        print(f"   [+60 DIAS]   {r['doc']:20} {money(r['saldo']):>16}  {r['dias']} dias"); al += 1
    if not al:
        print("   Ninguna factura con mas de 60 dias.")
    print("=" * W)

    # ---------- CSV ----------
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = hoy.strftime("%Y%m%d")
    slug = "".join(c for c in args.cliente.lower().replace(" ", "_") if c.isalnum() or c == "_")[:24]
    cpath = OUT_DIR / f"cartera_real_{slug}_{stamp}.csv"
    with open(cpath, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["documento", "tipo", "cliente", "fecha", "vence", "dias_vencido", "saldo", "aging"])
        for r in sorted(filas, key=lambda x: -x["dias"]):
            w.writerow([r["doc"], r["tipo"], r["cliente"], r["fecha"], r["vence"], r["dias"],
                        f"{r['saldo']:.2f}".replace(".", ","), bucket(r["dias"])])
    mpath = OUT_DIR / f"cartera_real_{slug}_{stamp}_mensual.csv"
    with open(mpath, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["mes", "facturado", "cobrado", "diferencia"])
        for m in meses:
            f_ = fact_mes.get(m, 0.0); c_ = cobr_mes.get(m, 0.0)
            w.writerow([m, f"{f_:.2f}".replace(".", ","), f"{c_:.2f}".replace(".", ","),
                        f"{f_-c_:.2f}".replace(".", ",")])
    print(f"\nGuardado:\n  {cpath}\n  {mpath}")


if __name__ == "__main__":
    main()
