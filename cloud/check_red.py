#!/usr/bin/env python3
"""cloud/check_red.py — prueba de conectividad y credenciales en la nube.

Solo lectura. Nunca imprime secretos. Uso:  python3 cloud/check_red.py
Si algo falla con 403 / host_not_allowed: falta el dominio en
Edit environment → Network access → Custom → Allowed domains.
"""
import json, os, sys, urllib.request, xmlrpc.client
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import odoo_proxy  # noqa: F401  (enruta xmlrpc por el proxy de la nube)

ok = True

def cfg_odoo():
    c = {}
    f = ROOT / "odoo_config.json"
    if f.exists():
        c = json.loads(f.read_text(encoding="utf-8"))
    return (os.environ.get("ODOO_URL") or c.get("url"),
            os.environ.get("ODOO_DB") or c.get("db"),
            os.environ.get("ODOO_LOGIN") or c.get("login"),
            os.environ.get("ODOO_APIKEY"))

def odoo(nombre, url, db, login, key):
    global ok
    if not key:
        print(f"✘ {nombre}: falta la API key en el environment"); ok = False; return
    try:
        uid = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common").authenticate(db, login, key, {})
        if uid:
            m = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
            cias = m.execute_kw(db, uid, key, "res.company", "search_read", [[]], {"fields": ["name"]})
            print(f"✔ {nombre}: CONEXION OK (uid {uid}, {len(cias)} compañías)")
        else:
            print(f"✘ {nombre}: conecta pero NO autentica (revisa login/apikey)"); ok = False
    except Exception as e:
        print(f"✘ {nombre}: {type(e).__name__}: {str(e)[:160]}"); ok = False

def perseo():
    global ok
    key = os.environ.get("PERSEO_API_KEY")
    if not key:
        print("✘ Perseo: falta PERSEO_API_KEY"); ok = False; return
    body = json.dumps({"api_key": key, "dias": 1, "generarpdf": False}).encode()
    req = urllib.request.Request("https://perseo-data-c1.app/api/facturas_consulta", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            print(f"✔ Perseo: HTTP {r.status} (API histórica accesible)")
    except Exception as e:
        print(f"✘ Perseo: {type(e).__name__}: {str(e)[:160]}"); ok = False

url, db, login, key = cfg_odoo()
odoo("Odoo principal", url, db, login, key)
if os.environ.get("ODOO_APIKEY_VINTRAL1"):
    odoo("Odoo vintral1 (histórico CO)", "https://vintral1.odoo.com", "vintral1", login,
         os.environ["ODOO_APIKEY_VINTRAL1"])
perseo()
sys.exit(0 if ok else 1)
