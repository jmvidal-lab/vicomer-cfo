#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cartera (cuentas por cobrar) de CASA MAGNA a la fecha — Odoo VINTRAL (vicomer).

Se conecta por XML-RPC usando la MISMA config que odoo_ventas.py:
  ~/Claude/Projects/CFO VICOMER/odoo_config.json   (url, db, login)
  ~/Claude/Projects/CFO VICOMER/odoo_apikey.txt    (la API key)
(o variables de entorno ODOO_URL / ODOO_DB / ODOO_LOGIN / ODOO_APIKEY)

Uso:
    python3 cartera_casamagna.py
    python3 cartera_casamagna.py --cliente "casa magna"   # cambia el filtro de nombre
    python3 cartera_casamagna.py --ids 496                 # fuerza partner_id(s)
    python3 cartera_casamagna.py --fx 3900                 # tipo de cambio COP->USD (ref)

Salida: tabla por factura con días de mora + aging (corriente/1-30/31-60/61-90/>90),
y archivos cartera_casamagna_AAAAMMDD.(json|csv) en esta carpeta.
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


# ----------------------------------------------------------------- config
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
        sys.exit("ERROR: faltan credenciales de Odoo: " + ", ".join(faltan) +
                 "\n  Revisa odoo_config.json / odoo_apikey.txt en la carpeta del proyecto.")
    return cfg


# ----------------------------------------------------------------- conexión
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
        try:
            dbp = xmlrpc.client.ServerProxy(f"{self.cfg['url']}/xmlrpc/2/db",
                                            allow_none=True, context=ssl.create_default_context())
            listed = dbp.list()
            if isinstance(listed, list):
                cands += listed
        except Exception:
            pass
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
                last = str(e)[:160]; continue
            if uid:
                self.cfg["db"] = db
                self.uid = uid
                return uid
        sys.exit(f"ERROR: no autenticó con ninguna base de datos. Último error: {last}")

    def search_read(self, model, domain, fields, limit=0):
        kw = {"fields": fields}
        if limit:
            kw["limit"] = limit
        return self.models.execute_kw(self.cfg["db"], self.uid, self.cfg["apikey"],
                                      model, "search_read", [domain], kw)


# ----------------------------------------------------------------- utilidades
def m2o_name(v):
    return v[1] if isinstance(v, (list, tuple)) and len(v) == 2 else ""

def m2o_id(v):
    return v[0] if isinstance(v, (list, tuple)) and len(v) == 2 else None

def fmt(n):
    return f"{round(n):,}".replace(",", ".")


# ----------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Cartera Casa Magna a la fecha (Odoo VINTRAL)")
    ap.add_argument("--cliente", default="casa magna", help="Texto a buscar en el nombre del cliente")
    ap.add_argument("--ids", default="", help="IDs de partner separados por coma (fuerza el filtro)")
    ap.add_argument("--fx", type=float, default=3700, help="Tipo de cambio COP->USD (referencial)")
    args = ap.parse_args()

    cfg = load_config()
    od = Odoo(cfg)
    od.authenticate()
    print(f"[OK] Conectado a {cfg['url']} (db '{cfg['db']}') como {cfg['login']}")

    hoy = datetime.date.today()

    # --- localizar partner(s) Casa Magna ---
    if args.ids.strip():
        partner_ids = [int(x) for x in args.ids.split(",") if x.strip()]
    else:
        term = args.cliente.replace(" ", "%")
        partners = od.search_read(
            "res.partner",
            ["|", ("name", "ilike", term), ("name", "ilike", args.cliente)],
            ["id", "name"])
        partner_ids = [p["id"] for p in partners]
        if partners:
            print("Clientes encontrados:", ", ".join(f"{p['name']} (#{p['id']})" for p in partners))
    if not partner_ids:
        sys.exit(f"No se encontró ningún cliente que contenga '{args.cliente}'. "
                 f"Prueba con --ids o ajusta --cliente.")

    # --- facturas con saldo pendiente (cartera) ---
    dom = [("move_type", "in", ["out_invoice", "out_refund"]),
           ("state", "=", "posted"),
           ("partner_id", "child_of", partner_ids),
           ("amount_residual", "!=", 0)]
    fields = ["name", "invoice_date", "invoice_date_due", "amount_total",
              "amount_residual", "amount_residual_signed", "payment_state",
              "currency_id", "partner_id", "move_type"]
    facs = od.search_read("account.move", dom, fields)

    if not facs:
        print("\n✅ Sin cartera pendiente: no hay facturas con saldo para Casa Magna.")
        return

    # --- aging ---
    buckets = ["Corriente (no vencido)", "1-30", "31-60", "61-90", ">90"]
    tot_bucket = defaultdict(float)
    filas = []
    total = 0.0
    monedas = set()
    for f in facs:
        saldo = f.get("amount_residual_signed") or f.get("amount_residual") or 0.0
        # amount_residual_signed: + factura pendiente, - nota de crédito pendiente
        venc = f.get("invoice_date_due") or f.get("invoice_date")
        dias = (hoy - datetime.date.fromisoformat(venc)).days if venc else 0
        if dias <= 0:
            b = buckets[0]
        elif dias <= 30:
            b = buckets[1]
        elif dias <= 60:
            b = buckets[2]
        elif dias <= 90:
            b = buckets[3]
        else:
            b = buckets[4]
        tot_bucket[b] += saldo
        total += saldo
        monedas.add(m2o_name(f.get("currency_id")))
        filas.append({
            "factura": f.get("name"),
            "cliente": m2o_name(f.get("partner_id")),
            "fecha": f.get("invoice_date"),
            "vence": f.get("invoice_date_due"),
            "dias_mora": max(dias, 0),
            "total": f.get("amount_total"),
            "saldo": saldo,
            "estado_pago": f.get("payment_state"),
            "aging": b,
        })

    filas.sort(key=lambda r: (-r["dias_mora"], r["factura"] or ""))
    moneda = " / ".join(sorted(m for m in monedas if m)) or "COP"

    # --- impresión ---
    print("\n" + "=" * 84)
    print(f"  CARTERA CASA MAGNA — corte {hoy.isoformat()}  ({moneda})")
    print("=" * 84)
    print(f"  {'Factura':16} {'Vence':11} {'Mora':>5}  {'Saldo':>16}  {'Estado':12} {'Aging'}")
    print("-" * 84)
    for r in filas:
        print(f"  {(r['factura'] or '')[:16]:16} {(r['vence'] or '')[:11]:11} "
              f"{r['dias_mora']:>5}  {fmt(r['saldo']):>16}  {(r['estado_pago'] or '')[:12]:12} {r['aging']}")
    print("-" * 84)
    print(f"  {'TOTAL CARTERA':>50}  {moneda} {fmt(total):>16}   (~USD {fmt(total/args.fx)})")
    print("\n  AGING:")
    for b in buckets:
        v = tot_bucket.get(b, 0.0)
        pct = (v / total * 100) if total else 0
        print(f"    {b:24} {moneda} {fmt(v):>16}  ({pct:4.0f}%)")
    print("=" * 84)

    # --- guardar ---
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = hoy.strftime("%Y%m%d")
    jpath = OUT_DIR / f"cartera_casamagna_{stamp}.json"
    jpath.write_text(json.dumps({
        "generado": datetime.datetime.now().isoformat(timespec="seconds"),
        "corte": hoy.isoformat(), "moneda": moneda,
        "total_cartera": round(total, 2),
        "aging": {b: round(tot_bucket.get(b, 0.0), 2) for b in buckets},
        "n_facturas": len(filas), "facturas": filas,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    cpath = OUT_DIR / f"cartera_casamagna_{stamp}.csv"
    with open(cpath, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["factura", "cliente", "fecha", "vence",
                                           "dias_mora", "total", "saldo", "estado_pago", "aging"])
        w.writeheader(); w.writerows(filas)
    print(f"\nGuardado:\n  {jpath}\n  {cpath}")


if __name__ == "__main__":
    main()
