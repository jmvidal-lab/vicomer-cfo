#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
odoo_stock.py · Grupo VICOMER
Extrae la FOTO DE INVENTARIO de Odoo (4 companias) para el analisis ABC-XYZ.

Salida: OdooVentas/stock_odoo_YYYYMMDD.json
  - quants  : stock por SKU / bodega / compania, con valor
  - productos: maestro (default_code, nombre, categoria, costo estandar, PVP)
  - po_abiertas: lineas de compra pendientes de recibir (transito)

Credenciales: igual que odoo_ventas.py (odoo_config.json + odoo_apikey.txt
o variables de entorno ODOO_URL / ODOO_DB / ODOO_LOGIN / ODOO_APIKEY).
Solo biblioteca estandar.
"""
import os, sys, json, ssl, datetime, xmlrpc.client
try:  # proxy HTTPS para xmlrpc (no-op en el Mac)
    import sys as _s, os as _o
    _d = _o.path.dirname(_o.path.abspath(__file__))
    for _p in (_d, _o.path.dirname(_d)):
        if _o.path.exists(_o.path.join(_p, 'odoo_proxy.py')) and _p not in _s.path: _s.path.append(_p)
    import odoo_proxy
except ImportError:
    pass
from pathlib import Path

HOME = Path.home()
PROJ = Path(os.environ.get("VICOMER_PROJ", HOME / "Claude" / "Projects" / "CFO VICOMER"))
OUT_DIR = Path(os.environ.get("ODOO_OUT_DIR", PROJ / "OdooVentas"))

def cargar_cfg():
    cfg = {"url": os.environ.get("ODOO_URL"), "db": os.environ.get("ODOO_DB"),
           "login": os.environ.get("ODOO_LOGIN"), "apikey": os.environ.get("ODOO_APIKEY")}
    for cf in (HOME / ".odoo_config.json", PROJ / "odoo_config.json"):
        if cf.exists():
            try:
                d = json.loads(cf.read_text(encoding="utf-8"))
                for k in ("url", "db", "login", "apikey"):
                    if not cfg[k] and d.get(k): cfg[k] = d[k]
            except Exception as e:
                print("  aviso: no pude leer", cf, e)
    for kf in (HOME / ".odoo_apikey", PROJ / "odoo_apikey.txt"):
        if not cfg["apikey"] and kf.exists():
            cfg["apikey"] = kf.read_text(encoding="utf-8").strip()
    faltan = [k for k in ("url", "db", "login", "apikey") if not cfg.get(k)]
    if faltan:
        sys.exit("Faltan credenciales: " + ", ".join(faltan))
    return cfg

def main():
    cfg = cargar_cfg()
    ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
    common = xmlrpc.client.ServerProxy(f"{cfg['url']}/xmlrpc/2/common", allow_none=True, context=ctx)
    models = xmlrpc.client.ServerProxy(f"{cfg['url']}/xmlrpc/2/object", allow_none=True, context=ctx)
    uid = common.authenticate(cfg["db"], cfg["login"], cfg["apikey"], {})
    if not uid: sys.exit("Autenticacion fallida")
    print("conectado, uid =", uid)

    def kw(model, method, args, opts=None, cids=None):
        o = dict(opts or {})
        o.setdefault("context", {})
        if cids: o["context"]["allowed_company_ids"] = cids
        return models.execute_kw(cfg["db"], uid, cfg["apikey"], model, method, args, o)

    comps = kw("res.company", "search_read", [[]], {"fields": ["name"]})
    cids = [c["id"] for c in comps]
    print("companias:", [(c["id"], c["name"]) for c in comps])

    quants = kw("stock.quant", "search_read",
                [[("location_id.usage", "=", "internal")]],
                {"fields": ["product_id", "location_id", "company_id", "quantity",
                            "reserved_quantity", "value", "inventory_quantity_auto_apply"]}, cids)
    print("quants:", len(quants))

    pids = sorted({q["product_id"][0] for q in quants if q.get("product_id")})
    prods = []
    for i in range(0, len(pids), 300):
        prods += kw("product.product", "read", [pids[i:i+300]],
                    {"fields": ["default_code", "name", "categ_id", "standard_price",
                                "list_price", "type", "active", "barcode"]}, cids)
    print("productos:", len(prods))

    try:
        pol = kw("purchase.order.line", "search_read",
                 [[("order_id.state", "in", ["purchase", "done"]), ("qty_received", "<", 1e12)]],
                 {"fields": ["product_id", "product_qty", "qty_received", "price_unit",
                             "company_id", "order_id", "date_planned"], "limit": 5000}, cids)
        pol = [l for l in pol if (l.get("product_qty") or 0) > (l.get("qty_received") or 0)]
    except Exception as e:
        print("  aviso PO:", e); pol = []
    print("lineas de compra abiertas:", len(pol))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    hoy = datetime.date.today().strftime("%Y%m%d")
    out = OUT_DIR / f"stock_odoo_{hoy}.json"
    out.write_text(json.dumps({"generado": datetime.datetime.now().isoformat(timespec="seconds"),
                               "companias": comps, "quants": quants, "productos": prods,
                               "po_abiertas": pol}, ensure_ascii=False), encoding="utf-8")
    print("LISTO ->", out)

if __name__ == "__main__":
    main()
