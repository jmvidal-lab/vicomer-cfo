#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
odoo_ventas.py
==============
Cliente del API de Odoo (XML-RPC) para extraer las VENTAS FACTURADAS de
VINTRAL (Colombia) y Costa Rica desde una instancia multicompañía, con el
mismo criterio que Perseo: cifras netas SIN IVA y notas de crédito restando.

Análogo a Perseo:
    Perseo -> Ecuador          |  Odoo -> Colombia (VINTRAL) + Costa Rica
    factura 01 / NC 04         |  account.move: out_invoice / out_refund (posted)
    subtotal (sin IVA)         |  amount_untaxed_signed (sin IVA, con signo)

Odoo XML-RPC necesita CUATRO datos (no solo la API key):
    - URL      p.ej.  https://vicomer.odoo.com   o  https://miservidor:8069
    - DB       nombre de la base de datos (en Odoo.sh suele ser el del proyecto)
    - LOGIN    tu usuario de Odoo (correo de acceso)
    - API KEY  (reemplaza a la contraseña)  -> Ajustes > cuenta > clave de API

CONFIGURACIÓN (cualquiera de las dos vías):
    A) Variables de entorno: ODOO_URL, ODOO_DB, ODOO_LOGIN, ODOO_APIKEY
    B) Archivos:  ~/.odoo_config.json   {"url":"...","db":"...","login":"..."}
                  ~/.odoo_apikey        (solo la clave, chmod 600)

USO:
    python3 odoo_ventas.py diag           # diagnóstico: compañías, monedas, muestra
    python3 odoo_ventas.py 2026           # extrae y guarda JSON de facturas del año
    python3 odoo_ventas.py test           # autoprueba offline (servidor simulado)

Sin dependencias externas (usa xmlrpc.client de la librería estándar).
"""

import os, sys, json, ssl, socket, datetime, xmlrpc.client
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
from urllib.parse import urlparse

HOME = Path.home()
OUT_DIR = Path(os.environ.get("ODOO_OUT_DIR", HOME / "Claude" / "Projects" / "CFO VICOMER" / "OdooVentas"))

def log(m):
    print(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {m}", flush=True)

# ------------------------------------------------------------------ config
def load_config():
    cfg = {"url": os.environ.get("ODOO_URL"),
           "db": os.environ.get("ODOO_DB"),
           "login": os.environ.get("ODOO_LOGIN"),
           "apikey": os.environ.get("ODOO_APIKEY")}
    PROJ = HOME / "Claude" / "Projects" / "CFO VICOMER"
    for f in (HOME / ".odoo_config.json", PROJ / "odoo_config.json"):
        if f.exists():
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                for k in ("url", "db", "login", "apikey"):
                    cfg[k] = cfg[k] or d.get(k)
            except Exception as e:
                log(f"[WARN] no se pudo leer {f}: {e}")
    for kf in (HOME / ".odoo_apikey", PROJ / "odoo_apikey.txt"):
        if not cfg["apikey"] and kf.exists():
            cfg["apikey"] = kf.read_text(encoding="utf-8").strip()
    if cfg.get("url"):
        cfg["url"] = cfg["url"].rstrip("/")
    return cfg

def _need(cfg, *keys):
    missing = [k for k in keys if not cfg.get(k)]
    if missing:
        sys.exit("ERROR: faltan credenciales de Odoo: " + ", ".join(missing) +
                 "\n  Defínelas en ~/.odoo_config.json / ~/.odoo_apikey o por variables de entorno.")

def _persist_db(db):
    """Guarda la db detectada en el odoo_config.json del proyecto (conserva lo demás)."""
    f = HOME / "Claude" / "Projects" / "CFO VICOMER" / "odoo_config.json"
    try:
        d = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        d["db"] = db
        f.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        log(f"[WARN] no se pudo guardar la db en {f}: {e}")

# ------------------------------------------------------------------ conexión
class Odoo:
    def __init__(self, cfg):
        self.cfg = cfg
        ctx = ssl.create_default_context()
        # allow_none para que Odoo acepte kwargs vacíos
        self.common = xmlrpc.client.ServerProxy(f"{cfg['url']}/xmlrpc/2/common", allow_none=True, context=ctx)
        self.models = xmlrpc.client.ServerProxy(f"{cfg['url']}/xmlrpc/2/object", allow_none=True, context=ctx)
        self.uid = None

    def version(self):
        return self.common.version()

    def list_dbs(self):
        try:
            db = xmlrpc.client.ServerProxy(f"{self.cfg['url']}/xmlrpc/2/db",
                                           allow_none=True, context=ssl.create_default_context())
            r = db.list()
            return r if isinstance(r, list) else None
        except Exception:
            return None

    def _db_candidates(self):
        cands, listed = [], self.list_dbs()
        if self.cfg.get("db"):
            cands.append(self.cfg["db"])
        if listed:
            cands += listed
        host = urlparse(self.cfg["url"]).hostname or ""
        sub = host.split(".")[0]
        for c in (sub, host.replace(".", "-"), host):
            if c:
                cands.append(c)
        seen, out = set(), []
        for c in cands:
            if c and c not in seen:
                seen.add(c); out.append(c)
        return out, listed

    def authenticate(self):
        """Autentica probando la db configurada y, si falla, autodescubre el
        nombre real (lista del servidor + variantes del subdominio) y lo guarda."""
        _need(self.cfg, "url", "login", "apikey")
        cands, listed = self._db_candidates()
        last_err = None
        for db in cands:
            try:
                uid = self.common.authenticate(db, self.cfg["login"], self.cfg["apikey"], {})
            except xmlrpc.client.Fault as e:
                last_err = str(e.faultString)[:140]
                continue
            except Exception as e:
                last_err = str(e)[:140]
                continue
            if uid:
                if db != self.cfg.get("db"):
                    log(f"[OK] base de datos detectada: '{db}'  (se guarda en odoo_config.json)")
                    self.cfg["db"] = db
                    _persist_db(db)
                self.uid = uid
                return uid
        msg = "ERROR: no autenticó con ninguna base de datos.\n"
        if listed:
            msg += f"  Bases disponibles en el servidor: {listed}\n  Pon la correcta en odoo_config.json (\"db\": \"...\")."
        else:
            msg += ("  El servidor no permite listar bases por API.\n"
                    "  Consigue el nombre EXACTO de la BD (Odoo: Ajustes → modo desarrollador,\n"
                    "  o el selector de bases en la pantalla de login) y ponlo en odoo_config.json.")
        if last_err:
            msg += f"\n  Último error: {last_err}"
        sys.exit(msg)

    def execute(self, model, method, args, kw=None):
        return self.models.execute_kw(self.cfg["db"], self.uid, self.cfg["apikey"],
                                      model, method, args, kw or {})

    def search_read(self, model, domain, fields, limit=0, context=None):
        kw = {"fields": fields}
        if limit:
            kw["limit"] = limit
        if context:
            kw["context"] = context
        return self.execute(model, "search_read", [domain], kw)

# ------------------------------------------------------------------ helpers
def _m2o(v):
    """Campo many2one de Odoo llega como [id, 'nombre'] o False."""
    if isinstance(v, (list, tuple)) and len(v) == 2:
        return v[0], v[1]
    return None, None

def companies(od):
    rows = od.search_read("res.company", [], ["id", "name", "currency_id"])
    out = {}
    for r in rows:
        cur_id, cur_name = _m2o(r.get("currency_id"))
        out[r["id"]] = {"name": r.get("name"), "currency": cur_name}
    return out

# ------------------------------------------------------------------ diagnóstico
def diagnostico():
    cfg = load_config()
    print("="*70)
    print("  DIAGNÓSTICO CONEXIÓN ODOO")
    print("="*70)
    print(f"  URL   : {cfg.get('url') or '(falta)'}")
    print(f"  DB    : {cfg.get('db') or '(falta)'}")
    print(f"  LOGIN : {cfg.get('login') or '(falta)'}")
    print(f"  APIKEY: {'sí' if cfg.get('apikey') else '(falta)'}")
    _need(cfg, "url")
    od = Odoo(cfg)
    try:
        v = od.version()
        print(f"\n  Servidor Odoo versión: {v.get('server_version')}")
    except Exception as e:
        sys.exit(f"  ERROR conectando a {cfg['url']}: {e}")
    listed = od.list_dbs()
    print(f"  Bases de datos que expone el servidor: {listed if listed else '(no las lista por API)'}")
    od.authenticate()   # autodescubre la db si la configurada no sirve
    print(f"  Autenticado OK. db='{od.cfg['db']}'  uid={od.uid}")

    comps = companies(od)
    print(f"\n  COMPAÑÍAS visibles ({len(comps)}):")
    for cid, c in comps.items():
        print(f"    [{cid}] {c['name']}  (moneda {c['currency']})")

    year = datetime.date.today().year
    dom = [["move_type", "in", ["out_invoice", "out_refund"]],
           ["state", "=", "posted"],
           ["invoice_date", ">=", f"{year}-01-01"]]
    ctx = {"allowed_company_ids": list(comps.keys())}
    cnt = od.execute("account.move", "search_count", [dom], {"context": ctx})
    print(f"\n  Facturas emitidas {year} (posted, todas las compañías): {cnt}")

    sample = od.search_read("account.move", dom,
                            ["name","invoice_date","partner_id","amount_untaxed",
                             "amount_untaxed_signed","amount_total","amount_total_signed",
                             "currency_id","company_id","move_type"], limit=3, context=ctx)
    print("\n  MUESTRA (3 facturas):")
    for s in sample:
        _, comp = _m2o(s.get("company_id")); _, cli = _m2o(s.get("partner_id"))
        _, cur = _m2o(s.get("currency_id"))
        print(f"    {s.get('invoice_date')} {s.get('move_type'):11s} {comp} | {cli[:28] if cli else ''} "
              f"| sinIVA={s.get('amount_untaxed_signed')} {cur} | total={s.get('amount_total_signed')}")
    # por compañía
    print("\n  RESUMEN por compañía (año en curso):")
    for cid, c in comps.items():
        d2 = dom + [["company_id", "=", cid]]
        n = od.execute("account.move", "search_count", [d2], {"context": ctx})
        print(f"    {c['name']:35s} facturas={n}  moneda={c['currency']}")
    print("\n  OK. Con esto cableo las cifras a los presupuestos de Colombia y Costa Rica.")

# ------------------------------------------------------------------ extracción
def _date(s):
    if not s:
        return None
    try:
        return datetime.date.fromisoformat(str(s)[:10])
    except Exception:
        return None

def _partner_vats(od, recs, ctx):
    """{partner_id: vat} para los partners de `recs`. Devuelve {} si Odoo no lo permite.

    El RUC/cédula es lo que permite mapear cada factura a su canal comercial usando
    el maestro DIM_Clients (que cruza por DNI). Sin esto, Ecuador cae todo en
    'SIN CANAL' al migrar de Perseo a Odoo.
    """
    ids = sorted({(r.get("partner_id") or [None])[0] for r in recs} - {None, False})
    if not ids:
        return {}
    out = {}
    try:
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            for p in od.search_read("res.partner", [["id", "in", chunk]], ["vat"], context=ctx):
                v = (p.get("vat") or "").strip()
                if v:
                    out[p["id"]] = v
    except Exception as e:
        log(f"[WARN] no pude leer el RUC de los clientes ({e}); el canal quedará sin mapear")
        return {}
    return out


def fetch_facturas(od, year, comp_ids=None):
    comps = companies(od)
    ctx = {"allowed_company_ids": list(comps.keys())}
    dom = [["move_type", "in", ["out_invoice", "out_refund"]],
           ["state", "=", "posted"],
           ["invoice_date", ">=", f"{year}-01-01"],
           ["invoice_date", "<=", f"{year}-12-31"]]
    if comp_ids:
        dom.append(["company_id", "in", list(comp_ids)])
    fields = ["name","invoice_date","partner_id","amount_untaxed","amount_untaxed_signed",
              "amount_total","amount_total_signed","currency_id","company_id","move_type"]
    recs = od.search_read("account.move", dom, fields, context=ctx)
    vats = _partner_vats(od, recs, ctx)
    rows = []
    for r in recs:
        d = _date(r.get("invoice_date"))
        if not d:
            continue
        comp_id, comp = _m2o(r.get("company_id"))
        part_id, cli = _m2o(r.get("partner_id"))
        _, cur = _m2o(r.get("currency_id"))
        es_nc = r.get("move_type") == "out_refund"
        rows.append({
            "empresa": comp, "empresa_id": comp_id,
            "cliente": cli, "moneda": cur,
            # RUC/cédula del cliente. Necesario para asignar el canal comercial de
            # Ecuador (el maestro DIM_Clients cruza por DNI de 10 dígitos). Vacío
            # si el partner no tiene `vat` cargado en Odoo.
            "dni": vats.get(part_id, ""),
            "fecha": d.isoformat(), "mes": d.month,
            "doc": r.get("name"), "tipo": r.get("move_type"), "es_nc": es_nc,
            # SIN IVA, con signo (NC negativa), en moneda de la compañía:
            "subtotal": round(float(r.get("amount_untaxed_signed") or 0), 2),
            "total": round(float(r.get("amount_total_signed") or 0), 2),
        })
    rows.sort(key=lambda x: (x["empresa"] or "", x["fecha"]))
    return rows

def resumen_por_empresa_mes(rows):
    agg = defaultdict(lambda: {"moneda": None, "mensual": [0.0]*12, "n": 0})
    for r in rows:
        a = agg[r["empresa"]]
        a["moneda"] = r["moneda"]
        a["mensual"][r["mes"]-1] += r["subtotal"]   # SIN IVA neto
        a["n"] += 1
    for a in agg.values():
        a["mensual"] = [round(v, 2) for v in a["mensual"]]
        a["ytd"] = round(sum(a["mensual"]), 2)
    return dict(agg)

def run_extract(year):
    cfg = load_config()
    od = Odoo(cfg); od.authenticate()
    rows = fetch_facturas(od, year)
    log(f"facturas {year}: {len(rows)}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"odoo_facturas_{year}.json").write_text(
        json.dumps({"generado": datetime.datetime.now().isoformat(timespec='seconds'),
                    "anio": year, "facturas": rows,
                    "resumen": resumen_por_empresa_mes(rows)},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    res = resumen_por_empresa_mes(rows)
    for emp, a in res.items():
        log(f"  {emp}: YTD sin IVA = {a['ytd']:,.2f} {a['moneda']}  ({a['n']} facturas)")
    log(f"[OK] -> {OUT_DIR / f'odoo_facturas_{year}.json'}")
    return res

# ------------------------------------------------------------------ autoprueba offline
def _selftest():
    """Levanta un XML-RPC que imita a Odoo y valida auth + normalización sin IVA."""
    import threading
    from xmlrpc.server import SimpleXMLRPCServer, SimpleXMLRPCRequestHandler

    INV = [
        {"name":"F-001","invoice_date":"2026-01-10","partner_id":[5,"CASAMAGNA S.A.S"],
         "amount_untaxed":1000000.0,"amount_untaxed_signed":1000000.0,"amount_total":1190000.0,
         "amount_total_signed":1190000.0,"currency_id":[3,"COP"],"company_id":[2,"VINTRAL S.A.S"],"move_type":"out_invoice"},
        {"name":"NC-001","invoice_date":"2026-01-20","partner_id":[5,"CASAMAGNA S.A.S"],
         "amount_untaxed":200000.0,"amount_untaxed_signed":-200000.0,"amount_total":238000.0,
         "amount_total_signed":-238000.0,"currency_id":[3,"COP"],"company_id":[2,"VINTRAL S.A.S"],"move_type":"out_refund"},
        {"name":"F-CR1","invoice_date":"2026-02-05","partner_id":[9,"CLIENTE CR"],
         "amount_untaxed":500.0,"amount_untaxed_signed":500.0,"amount_total":565.0,
         "amount_total_signed":565.0,"currency_id":[7,"USD"],"company_id":[3,"3-102-940094 SRL"],"move_type":"out_invoice"},
    ]
    COMPS = [{"id":2,"name":"VINTRAL S.A.S","currency_id":[3,"COP"]},
             {"id":3,"name":"3-102-940094 SRL","currency_id":[7,"USD"]}]

    class Common:
        def version(self): return {"server_version":"16.0-mock"}
        def authenticate(self, db, login, key, ua):
            return 7 if (db and login and key) else False
    class Obj:
        def execute_kw(self, db, uid, key, model, method, args, kw=None):
            kw = kw or {}
            if model=="res.company" and method=="search_read":
                return COMPS
            if model=="account.move":
                data=list(INV)
                # filtro company_id si viene en el domain
                dom=args[0] if args else []
                for cond in dom:
                    if cond[0]=="company_id" and cond[1]=="=":
                        data=[x for x in data if x["company_id"][0]==cond[2]]
                    if cond[0]=="company_id" and cond[1]=="in":
                        data=[x for x in data if x["company_id"][0] in cond[2]]
                if method=="search_count": return len(data)
                if method=="search_read":
                    flds=kw.get("fields")
                    return [{k:x.get(k) for k in flds} for x in data] if flds else data
            return []
    class RH(SimpleXMLRPCRequestHandler):
        def log_message(self,*a): pass
    srv=SimpleXMLRPCServer(("127.0.0.1",0), requestHandler=RH, allow_none=True, logRequests=False)
    port=srv.server_address[1]
    srv.register_instance(Common(), allow_dotted_names=True)  # /RPC2 -> usaremos rutas
    # Servir según path:
    class Router:
        def _dispatch(self, method, params): raise Exception("n/a")
    # SimpleXMLRPCServer no rutea por path; montamos dos servidores.
    common_srv=SimpleXMLRPCServer(("127.0.0.1",0), requestHandler=RH, allow_none=True, logRequests=False)
    common_srv.register_instance(Common())
    obj_srv=SimpleXMLRPCServer(("127.0.0.1",0), requestHandler=RH, allow_none=True, logRequests=False)
    obj_srv.register_instance(Obj())
    srv.server_close()
    tc=threading.Thread(target=common_srv.serve_forever, daemon=True); tc.start()
    to=threading.Thread(target=obj_srv.serve_forever, daemon=True); to.start()
    cp=common_srv.server_address[1]; op=obj_srv.server_address[1]

    class Odoo2(Odoo):
        def __init__(self, cfg):
            self.cfg=cfg; self.uid=None
            self.common=xmlrpc.client.ServerProxy(f"http://127.0.0.1:{cp}/", allow_none=True)
            self.models=xmlrpc.client.ServerProxy(f"http://127.0.0.1:{op}/", allow_none=True)
    cfg={"url":"http://x","db":"testdb","login":"me","apikey":"k"}
    od=Odoo2(cfg); assert od.version()["server_version"]=="16.0-mock"
    assert od.authenticate()==7
    rows=fetch_facturas(od, 2026)
    res=resumen_por_empresa_mes(rows)
    print("SELFTEST filas:",len(rows))
    for e,a in res.items(): print("  ",e,"YTD sinIVA",a["ytd"],a["moneda"],"n",a["n"])
    # VINTRAL enero neto = 1,000,000 - 200,000 = 800,000 COP
    v=res["VINTRAL S.A.S"]
    assert abs(v["mensual"][0]-800000.0)<0.01, v["mensual"][0]
    assert abs(v["ytd"]-800000.0)<0.01
    assert abs(res["3-102-940094 SRL"]["ytd"]-500.0)<0.01
    print("SELFTEST OK: NC resta y las cifras van SIN IVA por compañía/moneda.")

# ------------------------------------------------------------------ main
if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "diag"
    if arg == "diag":
        diagnostico()
    elif arg == "test":
        _selftest()
    elif arg.isdigit():
        run_extract(int(arg))
    else:
        print(__doc__)
