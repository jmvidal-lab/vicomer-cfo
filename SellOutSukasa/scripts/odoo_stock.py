#!/usr/bin/env python3
"""Cruza los SKU del reporte de Sukasa con el stock de VICOMER en Odoo (XML-RPC).

Uso:  python3 odoo_stock.py sukasa_data.json odoo_stock.json config.json

Credenciales por variables de entorno (nunca en el config). Acepta los nombres del repo
(ODOO_URL, ODOO_DB, ODOO_LOGIN, ODOO_APIKEY) y los alias ODOO_USER / ODOO_API_KEY.
En la nube enruta XML-RPC por el proxy con odoo_proxy.py (raíz del repo).
SOLO LECTURA: únicamente search_read.

Si el entorno no tiene esas variables pero sí un conector/MCP de Odoo, el agente puede
generar odoo_stock.json con el conector respetando el mismo esquema (ver SKILL.md).

Match de producto, en este orden:
  1. mapeo_sku.csv (cod_interno_sukasa -> default_code Odoo), si existe
  2. código de barras (COD. BARRAS de Sukasa = barcode en Odoo)
  3. referencia (REFERENCIA de Sukasa = default_code en Odoo, sin espacios, mayúsculas)
"""
import csv, json, os, re, sys, xmlrpc.client
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
try:
    import odoo_proxy  # noqa: F401  (xmlrpc ignora HTTPS_PROXY; sin esto falla en la nube)
except ImportError:
    pass
from datetime import datetime

def norm(s): return "".join(str(s or "").upper().split())
def alnum(s): return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())

def main():
    data_path, out_path, cfg_path = sys.argv[1:4]
    cfg = json.load(open(cfg_path, encoding="utf-8")).get("odoo", {})
    rows = json.load(open(data_path, encoding="utf-8"))["rows"]
    alias = {"ODOO_URL": ["ODOO_URL"], "ODOO_DB": ["ODOO_DB"], "ODOO_USER": ["ODOO_LOGIN", "ODOO_USER"],
             "ODOO_API_KEY": ["ODOO_APIKEY", "ODOO_API_KEY"]}
    env = {k: next((os.environ[n] for n in ns if os.environ.get(n)), None) for k, ns in alias.items()}
    if not env["ODOO_API_KEY"] and os.path.exists(os.path.expanduser("~/.odoo_apikey")):
        env["ODOO_API_KEY"] = open(os.path.expanduser("~/.odoo_apikey")).read().strip()
    if not all(env.values()):
        faltan = [k for k, v in env.items() if not v]
        json.dump({"ok": False, "error": "Faltan variables de entorno: " + ", ".join(faltan)}, open(out_path, "w"))
        raise SystemExit("Odoo no configurado (" + ", ".join(faltan) + "). Se sigue sin cruce de stock.")

    mapping = {}
    mp = os.path.join(os.path.dirname(os.path.abspath(cfg_path)), cfg.get("archivo_mapeo", "mapeo_sku.csv"))
    if os.path.exists(mp):
        for r in csv.DictReader(open(mp, encoding="utf-8")):
            if r.get("cod_interno_sukasa") and r.get("default_code_odoo"):
                mapping[r["cod_interno_sukasa"].strip()] = norm(r["default_code_odoo"])

    url = env["ODOO_URL"].rstrip("/")
    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common", allow_none=True)
    uid = common.authenticate(env["ODOO_DB"], env["ODOO_USER"], env["ODOO_API_KEY"], {})
    if not uid: raise SystemExit("Odoo: autenticación fallida")
    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", allow_none=True)
    ctx = {}
    if cfg.get("company_id"): ctx["allowed_company_ids"] = [cfg["company_id"]]
    if cfg.get("warehouse_id"): ctx["warehouse"] = cfg["warehouse_id"]
    if cfg.get("location_id"): ctx["location"] = cfg["location_id"]

    barcodes = sorted({r["barras"] for r in rows if r["barras"]})
    codes = sorted({r["ref"] for r in rows if r["ref"]} | {r["ref"].replace(" ", "") for r in rows if r["ref"]} | set(mapping.values())
                   | {alnum(r["ref"]) for r in rows if r["ref"]})
    fields = ["id", "default_code", "barcode", "name", "qty_available", "free_qty", "incoming_qty", "virtual_available"]
    domain = ["|", ["barcode", "in", barcodes], ["default_code", "in", codes]]
    try:
        prods = models.execute_kw(env["ODOO_DB"], uid, env["ODOO_API_KEY"], "product.product", "search_read", [domain],
                                  {"fields": fields, "context": ctx})
    except xmlrpc.client.Fault:  # versiones sin free_qty
        fields.remove("free_qty")
        prods = models.execute_kw(env["ODOO_DB"], uid, env["ODOO_API_KEY"], "product.product", "search_read", [domain],
                                  {"fields": fields, "context": ctx})
    by_bar = {norm(p["barcode"]): p for p in prods if p.get("barcode")}
    by_code = {norm(p["default_code"]): p for p in prods if p.get("default_code")}
    by_alnum = {alnum(p["default_code"]): p for p in prods if p.get("default_code")}

    items, unmatched = {}, []
    for r in rows:
        p = None; via = None
        if r["cod"] in mapping: p = by_code.get(mapping[r["cod"]]); via = "mapeo"
        if not p and r["barras"]: p = by_bar.get(norm(r["barras"])); via = "barcode"
        if not p and r["ref"]: p = by_code.get(norm(r["ref"])); via = "referencia"
        if not p and r["ref"]: p = by_alnum.get(alnum(r["ref"])); via = "referencia_alnum"
        if not p:
            unmatched.append({"cod": r["cod"], "ref": r["ref"], "barras": r["barras"], "desc": r["desc"]}); continue
        free = p.get("free_qty", p["qty_available"])
        items[r["cod"]] = {"odoo_id": p["id"], "odoo_code": p.get("default_code") or "", "match": via,
                           "on_hand": p["qty_available"], "free": max(free, 0), "incoming": max(p["incoming_qty"], 0)}
    out = {"ok": True, "source": "odoo-xmlrpc", "as_of": datetime.now().strftime("%Y-%m-%d %H:%M"),
           "context": ctx, "items": items, "unmatched": unmatched}
    json.dump(out, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"Odoo OK: {len(items)} SKU con match, {len(unmatched)} sin match")

if __name__ == "__main__":
    main()
