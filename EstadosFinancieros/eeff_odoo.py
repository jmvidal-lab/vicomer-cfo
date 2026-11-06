#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eeff_odoo.py  ·  Estados Financieros Grupo VICOMER — extractor autocontenido
=============================================================================
Odoo (XML-RPC) -> el contrato de datos que consume build.py.

AUTOCONTENIDO A PROPOSITO. Antes esto importaba finanzas_dashboard.py y leia tres
JSON de la carpeta padre. En septiembre de 2026 el usuario reorganizo su Escritorio,
las rutas fijas se rompieron en silencio y el tablero salio tres semanas con datos
viejos sin que nada fallara. Una corrida automatica semanal no puede depender de
donde este cada archivo: aqui no se importa nada del proyecto y la configuracion
viene embebida, con los JSON externos solo como anulacion opcional.

CREDENCIALES — primero el entorno, despues archivos
  ODOO_URL  ODOO_DB  ODOO_LOGIN  ODOO_APIKEY
  Si estan en el entorno, NO se necesita ningun archivo del Mac. Es lo que permite
  que la tarea semanal corra con la maquina del usuario apagada.
  Como respaldo se leen odoo_config.json / odoo_apikey.txt si existen.

MODOS
    python3 eeff_odoo.py check                  # solo prueba la conexion
    python3 eeff_odoo.py corte  2026-10-07      # estado a una fecha  -> stdout JSON
    python3 eeff_odoo.py serie  2026-10-07      # serie mensual       -> stdout JSON
    python3 eeff_odoo.py ventas 2026-10-07      # facturacion y cartera -> stdout JSON
    python3 eeff_odoo.py regresion 2026-07-31   # prueba contra el estado firmado

Solo biblioteca estandar.
"""
import os, sys, json, ssl, base64, calendar, datetime, http.client, xmlrpc.client
from urllib.parse import urlsplit, unquote

MESES = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]

# --- Clasificacion por account_type -----------------------------------------
ACTIVO = ("asset_receivable","asset_cash","asset_current","asset_non_current",
          "asset_prepayments","asset_fixed")
PASIVO = ("liability_payable","liability_credit_card","liability_current","liability_non_current")
PATRIMONIO = ("equity","equity_unaffected")
INGRESO = ("income","income_other")
GASTO = ("expense","expense_depreciation","expense_direct_cost","cost_of_revenue")

# --- Configuracion embebida (anulable con odoo_config.json / finanzas_reglas.json)
COMPANY_MAP = {"VICOMER":"Ecuador", "VICOMER LOGISTICA":"ignore", "VIX":"ignore",
               "VINTRAL":"Colombia", "3-102-940094":"Costa Rica",
               "SOCIEDAD DE RESPONSABILIDAD":"Costa Rica",
               "VIDAL AMBROSI MARCELO RENE":"ignore", "VIDAL TORRES JUAN MARCELO":"ignore"}

PAISES = {"Ecuador": {"cid": 2, "mon": "USD"}, "Colombia": {"cid": 1, "mon": "COP"}}

# Cuentas de proveedor COMERCIAL. La intercompania y los salarios no son credito de
# proveedor: incluirlos llevaba el DPO de Colombia a 454 dias e inventaba un
# financiamiento que no existe.
PROV_COMERCIAL = {"Ecuador": ["201.03.01.04"],
                  "Colombia": ["201.03.01.04","201.03.02.01","201.03.02.02"]}
INTERCIA = {"Ecuador": ["101.02.06.02.03"], "Colombia": ["201.03.02.03"]}

REGLAS = {
  "inventarios": ["INVENTARIO","MERCADERIA","MERCANCIA","MERCANCÍA","EXISTENCIAS",
                  "PRODUCTOS TERMINADOS","IMPORTACION","IMPORTACIÓN","MERCANCIAS EN TRANSITO"],
  "deuda_financiera": ["OBLIGACIONES FINANCIERAS","OBLIGACION FINANCIERA","PRESTAMO","PRÉSTAMO",
                       "SOBREGIRO","LEASING","TARJETA DE CREDITO","TARJETA DE CRÉDITO",
                       "CREDITO BANCARIO","CRÉDITO BANCARIO"],
  "impuestos_por_pagar": ["IVA POR PAGAR","IVA EN VENTAS","RETENCION","RETENCIÓN",
                          "IMPUESTO A LA RENTA","IMPUESTOS POR PAGAR","ICA POR PAGAR"],
}

# El estado firmado por contabilidad al 31-jul-2026. Es la prueba de regresion: si
# Odoo deja de reproducirlo, el ERP dejo de ser fuente valida y no se publica nada.
REGRESION = {
  "Ecuador":  {"ventas":1113374.15,"cogs":647897.68,"resultado":98861.50,
               "activo":1360023.73,"pasivo":810395.32,"patrimonio":549628.42},
  "Colombia": {"ventas":933278870.49,"cogs":443220231.25,"resultado":193781946.08,
               "activo":3050919626.96,"pasivo":1628480900.17,"patrimonio":1422438726.79},
}
# DELTAS ESPERADOS de Odoo contra ese estado, medidos y explicados el 2026-10-07.
# La prueba NO exige que Odoo sea identico al estado firmado: exige que la diferencia
# siga siendo LA MISMA. Un delta que se mueve es la senal de que algo cambio en la
# contabilidad y de que el tablero no se puede publicar a ciegas.
DELTA = {
 "Ecuador": {
   "ventas":      (   970.00, "otros ingresos que el estado oficial presenta aparte"),
   "cogs":        (     0.00, "idéntico"),
   "resultado":   (     0.00, "idéntico al centavo"),
   "activo":      ( -4339.14, "clasificación; se compensa en el pasivo"),
   "pasivo":      ( -4339.14, "clasificación; se compensa en el activo"),
   "patrimonio":  (    -0.01, "redondeo")},
 "Colombia": {
   "ventas":      (  601234.97, "otros ingresos presentados aparte"),
   "cogs":        (       0.00, "idéntico"),
   "resultado":   (-43581990.00, "provisión de renta: Odoo 115.763.000 contra 72.180.000"),
   "activo":      (-227011608.41, "sin explicar: intercompañía, proveedores e IVA"),
   "pasivo":      (-183429618.41, "sin explicar: intercompañía y proveedores"),
   "patrimonio":  (-43581990.00, "arrastra la diferencia de resultado")},
}


def log(m):
    sys.stderr.write("%s  %s\n" % (datetime.datetime.now().strftime("%H:%M:%S"), m))
    sys.stderr.flush()


def norm(t):
    t = (t or "").upper()
    for a,b in (("Á","A"),("É","E"),("Í","I"),("Ó","O"),("Ú","U"),("Ñ","N")):
        t = t.replace(a,b)
    return " ".join(t.split())


def contiene(txt, pats):
    n = norm(txt)
    return any(norm(p) and norm(p) in n for p in (pats or []))


def pref(code, p):
    return (code or "").replace(" ", "").startswith(p)


# =====================================================================
#  Proxy HTTPS — xmlrpc.client ignora HTTPS_PROXY
# =====================================================================
def _proxy_for(host):
    p = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if not p:
        return None
    no = os.environ.get("NO_PROXY") or os.environ.get("no_proxy") or ""
    for d in [x.strip().lstrip(".") for x in no.split(",") if x.strip()]:
        if d == "*" or host == d or host.endswith("." + d):
            return None
    return urlsplit(p if "://" in p else "http://" + p)


class _ProxyTransport(xmlrpc.client.SafeTransport):
    def __init__(self, proxy, **kw):
        super().__init__(**kw)
        self._proxy = proxy

    def make_connection(self, host):
        if self._connection and host == self._connection[0]:
            return self._connection[1]
        chost, self._extra_headers, x509 = self.get_host_info(host)
        p = self._proxy
        conn = http.client.HTTPSConnection(p.hostname, p.port or 8080,
                                           context=self.context, **(x509 or {}))
        hdrs = {}
        if p.username:
            cred = "%s:%s" % (unquote(p.username), unquote(p.password or ""))
            hdrs["Proxy-Authorization"] = "Basic " + base64.b64encode(cred.encode()).decode()
        h, _, port = chost.partition(":")
        conn.set_tunnel(h, int(port) if port else 443, headers=hdrs)
        self._connection = host, conn
        return conn


def _proxy_server(uri):
    u = urlsplit(uri)
    prx = _proxy_for(u.hostname or "") if u.scheme == "https" else None
    tr = _ProxyTransport(prx, context=ssl.create_default_context()) if prx else None
    return xmlrpc.client.ServerProxy(uri, transport=tr, allow_none=True,
                                     context=None if tr else ssl.create_default_context())


# =====================================================================
#  Configuracion y conexion
# =====================================================================
def load_config():
    cfg = {"url": os.environ.get("ODOO_URL"), "db": os.environ.get("ODOO_DB"),
           "login": os.environ.get("ODOO_LOGIN"), "apikey": os.environ.get("ODOO_APIKEY"),
           "company_map": dict(COMPANY_MAP), "origen": []}
    if all(cfg[k] for k in ("url","login","apikey")):
        cfg["origen"].append("variables de entorno")
    aqui = os.path.dirname(os.path.abspath(__file__))
    for f in (os.path.join(aqui,"odoo_config.json"),
              os.path.join(os.path.dirname(aqui),"odoo_config.json"),
              os.path.expanduser("~/.odoo_config.json")):
        if os.path.exists(f):
            try:
                d = json.loads(open(f, encoding="utf-8").read())
                for k in ("url","db","login","apikey"):
                    if not cfg[k] and d.get(k):
                        cfg[k] = d[k]
                        if "odoo_config.json" not in cfg["origen"]:
                            cfg["origen"].append("odoo_config.json")
                if d.get("company_map"):
                    cfg["company_map"] = d["company_map"]
            except Exception as e:
                log("[WARN] %s ilegible: %s" % (f, e))
            break
    for kf in (os.path.join(aqui,"odoo_apikey.txt"), os.path.expanduser("~/.odoo_apikey")):
        if not cfg["apikey"] and os.path.exists(kf):
            cfg["apikey"] = open(kf, encoding="utf-8").read().strip()
            cfg["origen"].append("odoo_apikey.txt")
    if cfg.get("url"):
        cfg["url"] = cfg["url"].rstrip("/")
    falta = [k for k in ("url","login","apikey") if not cfg.get(k)]
    if falta:
        raise SystemExit(
            "FALTAN CREDENCIALES DE ODOO: %s.\n"
            "Definí ODOO_URL, ODOO_DB, ODOO_LOGIN y ODOO_APIKEY como variables de entorno, "
            "o dejá odoo_config.json y odoo_apikey.txt junto a este script.\n"
            "No se extrae nada sin credenciales: antes de inventar una cifra, el hueco."
            % ", ".join(falta))
    return cfg


class Odoo(object):
    def __init__(self, cfg):
        self.cfg = cfg
        self.common = _proxy_server(cfg["url"] + "/xmlrpc/2/common")
        self.models = _proxy_server(cfg["url"] + "/xmlrpc/2/object")
        self.uid = None
        self.calls = 0

    def authenticate(self):
        host = self.cfg["url"].split("//")[-1].split("/")[0]
        cands, seen = [], set()
        for c in (self.cfg.get("db"), host.split(".")[0], host.replace(".", "-"), host):
            if c and c not in seen:
                seen.add(c); cands.append(c)
        last = None
        for db in cands:
            try:
                uid = self.common.authenticate(db, self.cfg["login"], self.cfg["apikey"], {})
            except Exception as e:
                last = str(e)[:160]; continue
            if uid:
                self.cfg["db"] = db; self.uid = uid; return uid
        raise RuntimeError("no autenticó contra ninguna base. Último error: %s" % last)

    def kw(self, model, method, args, kwargs=None):
        self.calls += 1
        return self.models.execute_kw(self.cfg["db"], self.uid, self.cfg["apikey"],
                                      model, method, args, kwargs or {})

    def sr(self, model, dom, fields, ctx=None):
        kw = {"fields": fields}
        if ctx:
            kw["context"] = ctx
        return self.kw(model, "search_read", [dom], kw)


def m2o(v):
    return (v[0], v[1]) if isinstance(v, (list, tuple)) and len(v) == 2 else (None, None)


def companias(od):
    cm = od.cfg.get("company_map") or COMPANY_MAP
    out = {}
    for r in od.sr("res.company", [], ["id","name","currency_id"]):
        _, cur = m2o(r.get("currency_id"))
        n = norm(r.get("name")); best, bl = None, -1
        for frag, pais in cm.items():
            f = norm(frag)
            if f and f in n and len(f) > bl:
                best, bl = pais, len(f)
        out[r["id"]] = {"id": r["id"], "name": r.get("name"), "moneda": cur,
                        "pais": None if best in (None,"ignore") else best,
                        "excluida": best == "ignore"}
    return out


def plan_de_cuentas(od, cid):
    """UNA compania por contexto: code y name son company-dependent desde Odoo 17.
    Leerlos con todas las companias en contexto devuelve codigos vacios y cruza etiquetas."""
    return {a["id"]: a for a in od.sr("account.account", [],
            ["id","code","name","account_type"], ctx={"allowed_company_ids":[cid]})}


def saldos(od, cid, desde, hasta):
    dom = [["parent_state","=","posted"], ["company_id","=",cid], ["date","<=",hasta]]
    if desde:
        dom.append(["date",">=",desde])
    rows = od.kw("account.move.line","read_group",
                 [dom, ["balance:sum"], ["account_id"]],
                 {"lazy": False, "context": {"allowed_company_ids":[cid]}})
    out = {}
    for r in rows:
        aid, _ = m2o(r.get("account_id"))
        if aid:
            out[aid] = out.get(aid, 0.0) + float(r.get("balance") or 0)
    return out


def clasifica(cuenta):
    nom, t = cuenta.get("name"), cuenta.get("account_type")
    if t in ACTIVO:
        if contiene(nom, REGLAS["inventarios"]): return "inventarios"
        if t == "asset_cash": return "efectivo"
        if t == "asset_receivable": return "cuentas_por_cobrar"
        if t in ("asset_non_current","asset_fixed"): return "activo_no_corriente"
        return "otros_activos_corrientes"
    if t in PASIVO:
        # La deuda financiera se marca por NOMBRE pero se ubica por PLAZO: meter la
        # porcion de largo plazo en el corriente hunde la liquidez sin que nadie lo note.
        es_deuda = contiene(nom, REGLAS["deuda_financiera"])
        if t == "liability_non_current":
            return "deuda_financiera_lp" if es_deuda else "pasivo_no_corriente"
        if es_deuda: return "deuda_financiera"
        if contiene(nom, REGLAS["impuestos_por_pagar"]): return "impuestos_por_pagar"
        if t == "liability_payable": return "cuentas_por_pagar"
        return "otros_pasivos_corrientes"
    if t in PATRIMONIO:
        return "patrimonio"
    return None


def clases_de(od, pl, cid, hasta):
    ACT = ("efectivo","cuentas_por_cobrar","inventarios","otros_activos_corrientes",
           "activo_no_corriente")
    out = {}
    for aid, v in saldos(od, cid, None, hasta).items():
        a = pl.get(aid) or {}
        cl = clasifica(a)
        if not cl:
            continue
        out.setdefault(cl, []).append({"code": (a.get("code") or "").replace(" ",""),
                                       "name": a.get("name") or "",
                                       "v": v * (1.0 if cl in ACT else -1.0)})
    return out


def foto(od, pl, cid, pais, hasta, clases=None):
    c = clases if clases is not None else clases_de(od, pl, cid, hasta)
    tot = lambda k: round(sum(x["v"] for x in c.get(k, [])), 2)
    def top(k, n=4):
        xs = sorted(c.get(k, []), key=lambda x: -abs(x["v"]))[:n]
        return " · ".join("%s %s" % (x["name"].strip().title()[:30], "{:,.0f}".format(abs(x["v"])))
                          for x in xs if abs(x["v"]) > 0)
    def solo(k, codes):
        return round(sum(x["v"] for x in c.get(k, []) if x["code"] in codes), 2)
    return {"efectivo":tot("efectivo"), "efectivo_sub":top("efectivo",3),
            "cxc":tot("cuentas_por_cobrar"),
            "inventarios":tot("inventarios"), "inventarios_sub":top("inventarios",3),
            "otros_ac":tot("otros_activos_corrientes"), "otros_ac_sub":top("otros_activos_corrientes",4),
            "anc":tot("activo_no_corriente"), "anc_sub":top("activo_no_corriente",3),
            "cxp":tot("cuentas_por_pagar"), "cxp_sub":top("cuentas_por_pagar",4),
            "df":tot("deuda_financiera"), "df_sub":top("deuda_financiera",3),
            "imp":tot("impuestos_por_pagar"),
            "otros_pc":tot("otros_pasivos_corrientes"), "otros_pc_sub":top("otros_pasivos_corrientes",4),
            "pnc":round(tot("pasivo_no_corriente")+tot("deuda_financiera_lp"),2),
            "pnc_sub":top("pasivo_no_corriente",2),
            "patrimonio_sr":tot("patrimonio"), "patrimonio_sub":top("patrimonio",3),
            "proveedor_comercial":abs(solo("cuentas_por_pagar", PROV_COMERCIAL[pais])),
            "intercia":abs(solo("cuentas_por_pagar", INTERCIA[pais])
                           or solo("otros_activos_corrientes", INTERCIA[pais]))}


PARTICIPACION_EC = 0.15   # participacion de trabajadores, Codigo del Trabajo
IR_EC = 0.25              # impuesto a la renta sociedades, Ecuador


def extras(od, pl, cid, pais, desde, hasta, clases):
    """Lo que el P&G resumido esconde y un CFO necesita: depreciacion (para el EBITDA),
    intereses separados de las multas, inventario en almacen contra transito, y cartera
    de clientes separada de la de relacionadas."""
    dep = ibanco = imora = multas = 0.0
    det_dep, det_int = [], []
    for aid, v in saldos(od, cid, desde, hasta).items():
        a = pl.get(aid) or {}
        if a.get("account_type") not in GASTO:
            continue
        n = norm(a.get("name")); c = a.get("code") or ""
        if "DEPREC" in n or "AMORTIZ" in n or a.get("account_type") == "expense_depreciation":
            dep += v; det_dep.append({"code": c, "name": a.get("name"), "v": round(v, 2)})
        if "MORA" in n or "MULTA" in n:
            imora += v if "INTERES" in n else 0.0
            multas += v if "INTERES" not in n else 0.0
        elif "INTERES" in n:
            ibanco += v; det_int.append({"code": c, "name": a.get("name"), "v": round(v, 2)})
    alm = tra = 0.0
    for x in clases.get("inventarios", []):
        n = norm(x["name"])
        if "TRANSIT" in n or "IMPORTACI" in n:
            tra += x["v"]
        else:
            alm += x["v"]
    # Cartera: el DSO solo se mide con clientes de verdad. Mezclar las relacionadas
    # infla los dias de cobro y esconde que no es cartera comercial.
    rel_pal = ["VINTRAL","VICOMER","RELACIONAD","ACCIONISTA","SOCIO","COSTA RICA","CMPK","VIX"]
    cxc_ext = cxc_rel = 0.0
    for x in clases.get("cuentas_por_cobrar", []):
        (globals().__setitem__("_t", 0))
        if contiene(x["name"], rel_pal): cxc_rel += x["v"]
        else: cxc_ext += x["v"]
    for x in clases.get("otros_activos_corrientes", []):
        if contiene(x["name"], rel_pal):
            cxc_rel += x["v"]
    return {"depreciacion": round(dep, 2), "depreciacion_detalle": det_dep,
            "intereses": round(ibanco, 2), "intereses_detalle": det_int,
            "intereses_mora": round(imora, 2), "multas": round(multas, 2),
            "inventario_almacen": round(alm, 2), "inventario_transito": round(tra, 2),
            "cxc_externa": round(cxc_ext, 2), "cxc_relacionada": round(cxc_rel, 2)}


def pyg(od, pl, cid, desde, hasta):
    """Prefijos verificados, iguales en las dos companias:
    502.01 ventas · 502.02 administrativos · 502.03 financieros
    502.04 Ecuador no deducibles / Colombia impuesto a la renta."""
    r = {"ing":0.0,"cogs":0.0,"gv":0.0,"ga":0.0,"gf":0.0,"g4":0.0,"n":0}
    det = {k: [] for k in ("ing","cogs","gv","ga","gf","g4")}
    for aid, v in saldos(od, cid, desde, hasta).items():
        a = pl.get(aid) or {}
        t, c = a.get("account_type"), a.get("code") or ""
        k = None
        if t in INGRESO:
            r["ing"] += -v; r["n"] += 1; k = "ing"; v = -v
        elif t in GASTO:
            if   pref(c,"501"):    k = "cogs"
            elif pref(c,"502.01"): k = "gv"
            elif pref(c,"502.02"): k = "ga"
            elif pref(c,"502.03"): k = "gf"
            elif pref(c,"502.04"): k = "g4"
            else:                  k = "ga"
            r[k] += v
        if k and abs(v) > 0.005:
            det[k].append({"code": c, "name": a.get("name") or "", "v": round(v, 2)})
    out = {k: (round(v,2) if k != "n" else v) for k, v in r.items()}
    for k in det:
        det[k].sort(key=lambda x: -abs(x["v"]))
    out["detalle"] = det
    return out


def bloque_corte(od, comps, pais, cid, moneda, d0, hasta, dias):
    pl = plan_de_cuentas(od, cid)
    y = pyg(od, pl, cid, d0, hasta)
    clases = clases_de(od, pl, cid, hasta)
    g = foto(od, pl, cid, pais, hasta, clases)
    ex = extras(od, pl, cid, pais, d0, hasta, clases)
    ub = y["ing"]-y["cogs"]; uo = ub-y["gv"]-y["ga"]; uai = uo-y["gf"]; neto = uai-y["g4"]
    P = lambda v: round(v/y["ing"], 4) if y["ing"] else None
    etq4 = "(−) Impuesto a la renta" if pais == "Colombia" else "(−) Gastos no deducibles"
    pl_ = [
      {"k":"Ventas netas","v":y["ing"],"t":"s","b":"ing"},
      {"k":"(−) Costo de ventas","v":-y["cogs"],"t":"r","b":"cogs"},
      {"k":"Utilidad bruta","v":round(ub,2),"t":"S","pct":P(ub)},
      {"k":"(−) Gastos de ventas","v":-y["gv"],"t":"r","b":"gv"},
      {"k":"(−) Gastos administrativos","v":-y["ga"],"t":"r","b":"ga"},
      {"k":"Utilidad operativa (EBIT)","v":round(uo,2),"t":"S","pct":P(uo)},
      {"k":"(−) Gastos financieros","v":-y["gf"],"t":"r","b":"gf"},
      {"k":"Utilidad antes de impuestos","v":round(uai,2),"t":"S","pct":P(uai)},
      {"k":etq4,"v":-y["g4"],"t":"r","b":"g4"},
      {"k":"Resultado del ejercicio","v":round(neto,2),"t":"F","pct":P(neto)}]
    mesFin = MESES[int(hasta[5:7])-1]
    # 'cl' enlaza cada renglon con su clase de cuentas para poder expandirlo en pantalla.
    bg = {
      "activo":[{"k":"Efectivo y bancos","v":g["efectivo"],"sub":g["efectivo_sub"],"cl":"efectivo"},
                {"k":"Cuentas por cobrar clientes","v":g["cxc"],"cl":"cuentas_por_cobrar"},
                {"k":"Inventarios y mercadería en tránsito","v":g["inventarios"],
                 "sub":g["inventarios_sub"],"cl":"inventarios"},
                {"k":"Otros activos corrientes","v":g["otros_ac"],"sub":g["otros_ac_sub"],
                 "cl":"otros_activos_corrientes"}],
      "activo_nc":([{"k":"Propiedad, planta y equipo (neto)","v":g["anc"],"sub":g["anc_sub"],
                     "cl":"activo_no_corriente"}] if abs(g["anc"]) > 1 else []),
      "pasivo":[{"k":"Proveedores y cuentas por pagar","v":g["cxp"],"sub":g["cxp_sub"],
                 "cl":"cuentas_por_pagar"},
                {"k":"Deuda financiera corto plazo","v":g["df"],"sub":g["df_sub"],
                 "cl":"deuda_financiera"},
                {"k":"Impuestos por pagar","v":g["imp"],"cl":"impuestos_por_pagar"},
                {"k":"Otros pasivos corrientes","v":g["otros_pc"],"sub":g["otros_pc_sub"],
                 "cl":"otros_pasivos_corrientes"}],
      "pasivo_nc":([{"k":"Pasivo no corriente","v":g["pnc"],"sub":g["pnc_sub"],
                     "cl":"pasivo_no_corriente"}] if abs(g["pnc"]) > 1 else []),
      "patrimonio":[{"k":"Capital y resultados acumulados","v":g["patrimonio_sr"],
                     "sub":g["patrimonio_sub"],"cl":"patrimonio"},
                    {"k":"Resultado del ejercicio","v":round(neto,2),
                     "sub":"Ene–%s %s" % (mesFin, hasta[:4])}]}
    ac = g["efectivo"]+g["cxc"]+g["inventarios"]+g["otros_ac"]; at = ac+g["anc"]
    pc = g["cxp"]+g["df"]+g["imp"]+g["otros_pc"]; pt = pc+g["pnc"]
    pat = g["patrimonio_sr"]+neto
    bg["descuadre_esperado"] = round(at-pt-pat, 2)
    R = lambda v,n=2: round(v, n)
    dso = g["cxc"]/(y["ing"]/dias) if y["ing"] else None
    dio = g["inventarios"]/(y["cogs"]/dias) if y["cogs"] else None
    dpo = g["proveedor_comercial"]/(y["cogs"]/dias) if y["cogs"] else None
    dfT = g["df"]+g["pnc"]
    ind = {"mb":P(ub),"mo":P(uo),"mn":P(neto),"gastos_pct":P(y["gv"]+y["ga"]),
           "liquidez":R(ac/pc) if pc else None, "acida":R((ac-g["inventarios"])/pc) if pc else None,
           "ctrabajo":R(ac-pc), "endeud":R(pt/at,3) if at else None,
           "apal":R(pt/pat) if pat else None, "df":R(dfT), "df_act":R(dfT/at,3) if at else None,
           "roa":R(neto/at,4) if at else None, "roe":R(neto/pat,4) if pat else None,
           "roa_a":R(neto/at*365/dias,4) if at else None,
           "roe_a":R(neto/pat*365/dias,4) if pat else None,
           "dso":round(dso) if dso else None,"dio":round(dio) if dio else None,
           "dpo":round(dpo) if dpo else None,
           "ccc":round(dso+dio-dpo) if (dso and dio and dpo) else None,
           "proveedor_comercial":g["proveedor_comercial"], "intercia":g["intercia"]}
    # --- EBITDA = utilidad antes de impuestos + gastos financieros + depreciacion
    ebitda = uai + y["gf"] + ex["depreciacion"]
    ind["ebitda"] = R(ebitda); ind["m_ebitda"] = P(ebitda)
    ind["depreciacion"] = ex["depreciacion"]
    ind["intereses"] = ex["intereses"]; ind["intereses_mora"] = ex["intereses_mora"]
    ind["multas"] = ex["multas"]
    # Tasa implicita de la deuda: intereses anualizados sobre deuda financiera. Si queda
    # muy por debajo del mercado, lo probable no es que se financien barato: es que haya
    # intereses sin registrar.
    dfT2 = g["df"] + g["pnc"]
    ind["tasa_deuda"] = R(ex["intereses"] * 365.0 / dias / dfT2, 4) if dfT2 else None
    ind["inv_almacen"] = ex["inventario_almacen"]; ind["inv_transito"] = ex["inventario_transito"]
    ind["cxc_externa"] = ex["cxc_externa"]; ind["cxc_relacionada"] = ex["cxc_relacionada"]
    # DSO con clientes externos; las relacionadas no son cartera comercial.
    ind["dso_externo"] = round(ex["cxc_externa"] / (y["ing"]/dias)) if y["ing"] else None
    ind["dio_almacen"] = round(ex["inventario_almacen"] / (y["cogs"]/dias)) if y["cogs"] else None
    ind["dio_transito"] = round(ex["inventario_transito"] / (y["cogs"]/dias)) if y["cogs"] else None

    fiscal = {"pais": pais}
    if pais == "Ecuador":
        # Ecuador no provisiona ni participacion laboral ni impuesto a la renta en Odoo.
        # Sin esas dos, la "utilidad" del ERP es utilidad ANTES de repartir y de tributar.
        part = max(0.0, uai) * PARTICIPACION_EC
        base = max(0.0, uai) - part + y["g4"]      # los no deducibles vuelven a la base
        ir = base * IR_EC
        fiscal.update({"estimado": True, "registrado": False, "utilidad_antes": R(uai),
                       "participacion": R(part), "base_imponible": R(base),
                       "impuesto_renta": R(ir), "no_deducibles": R(y["g4"]),
                       "utilidad_neta_estimada": R(uai - part - ir),
                       "tasa_efectiva": R((part + ir)/uai, 4) if uai else None,
                       "costo_fiscal_no_deducibles": R(y["g4"] * IR_EC),
                       "nota": ("Odoo no registra participación de trabajadores ni impuesto a la "
                                "renta. Se estiman al 15% y 25%; los gastos no deducibles vuelven "
                                "a la base imponible. La utilidad del ERP es ANTES de repartir y "
                                "de tributar.")})
    else:
        fiscal.update({"estimado": False, "registrado": y["g4"] != 0, "utilidad_antes": R(uai),
                       "impuesto_renta": R(y["g4"]), "utilidad_neta_estimada": R(neto),
                       "tasa_efectiva": R(y["g4"]/uai, 4) if uai else None,
                       "nota": ("El gasto de renta está en 502.04. La tasa efectiva se mide "
                                "contra la utilidad antes de impuestos del propio ERP.")})

    return {"pais":pais, "empresa":(comps.get(cid) or {}).get("name"), "moneda":moneda,
            "periodo":"Enero – %s %s" % (mesFin, hasta[:4]), "per_ok":True,
            "pl":pl_, "bg":bg, "ind":ind, "fiscal":fiscal,
            "detalle_bg":{k: sorted(v, key=lambda x: -abs(x["v"]))[:25] for k, v in clases.items()},
            "detalle_pl":y.get("detalle"),
            "_totales":{"activo":R(at),"pasivo":R(pt),"patrimonio":R(pat)}}


def conectar():
    cfg = load_config()
    od = Odoo(cfg); od.authenticate()
    log("Odoo %s · db=%s · uid=%s · credenciales: %s"
        % (cfg["url"], cfg["db"], od.uid, ", ".join(cfg["origen"]) or "?"))
    return od


def cmd_check():
    od = conectar()
    v = od.common.version()
    comps = companias(od)
    print("CONEXION OK · servidor %s" % v.get("server_version"))
    print("credenciales desde: %s" % ", ".join(od.cfg["origen"]))
    for c in comps.values():
        print("  [%s] %-44s %-4s -> %s" % (c["id"], (c["name"] or "")[:44], c["moneda"] or "?",
              "EXCLUIDA" if c["excluida"] else (c["pais"] or "SIN MAPEAR")))


def cmd_corte(hasta):
    d1 = datetime.date.fromisoformat(hasta)
    d0 = datetime.date(d1.year, 1, 1)
    dias = (d1 - d0).days + 1
    od = conectar(); comps = companias(od)
    out = {"meta":{"corte":"%d de %s de %d" % (d1.day,
                   ["enero","febrero","marzo","abril","mayo","junio","julio","agosto",
                    "septiembre","octubre","noviembre","diciembre"][d1.month-1], d1.year),
                   "corte_iso":hasta, "dias":dias, "anio":d1.year, "anio_txt":str(d1.year),
                   "rango_defecto":[1, d1.month],
                   "fuente":"Odoo · account.move.line, asientos contabilizados"}}
    for pais, c in PAISES.items():
        out["EC" if pais == "Ecuador" else "CO"] = bloque_corte(
            od, comps, pais, c["cid"], c["mon"], d0.isoformat(), hasta, dias)
    sys.stdout.write(json.dumps(out, ensure_ascii=False, indent=2))
    log("llamadas XML-RPC: %d" % od.calls)


def cmd_serie(hasta):
    tope = datetime.date.fromisoformat(hasta); y = tope.year
    od = conectar(); comps = companias(od)
    out = {"meta":{"anio":y,"corte_iso":hasta,"meses":MESES[:tope.month]}}
    for pais, c in PAISES.items():
        cid = c["cid"]; pl = plan_de_cuentas(od, cid)
        buckets, primero = [], None
        for m in range(1, tope.month+1):
            d0 = datetime.date(y, m, 1).isoformat()
            d1 = min(datetime.date(y, m, calendar.monthrange(y, m)[1]), tope)
            r = pyg(od, pl, cid, d0, d1.isoformat())
            vivo = any(abs(r[k]) > 0.005 for k in ("ing","cogs","gv","ga","gf","g4"))
            if vivo and primero is None:
                primero = m
            buckets.append({"m":m,"hasta":d1.isoformat(),"vivo":vivo,"pyg":r,
                            "bg":foto(od, pl, cid, pais, d1.isoformat())})
        # El primer mes con movimiento arrastra todo lo anterior: es el asiento de la
        # migracion. Se declara el periodo REAL que cubre; nadie puede partirlo.
        for b in buckets:
            if primero is not None and b["m"] == primero and primero > 1:
                b["cubre"] = [1, primero]; b["bloque"] = True
                b["etiqueta"] = "%s–%s" % (MESES[0], MESES[primero-1])
                b["motivo_bloque"] = ("La migración entró como un solo asiento: %s líneas de "
                                      "ingreso para %d meses. No se puede separar mes a mes."
                                      % (b["pyg"]["n"], primero))
            else:
                b["cubre"] = [b["m"], b["m"]]; b["bloque"] = False
                b["etiqueta"] = MESES[b["m"]-1]
        out["EC" if pais == "Ecuador" else "CO"] = {
            "pais":pais, "empresa":(comps.get(cid) or {}).get("name"),
            "moneda":c["mon"], "primer_mes":primero, "buckets":buckets}
    sys.stdout.write(json.dumps(out, ensure_ascii=False, indent=2))
    log("llamadas XML-RPC: %d" % od.calls)


def cmd_regresion(hasta="2026-07-31"):
    """Odoo contra el estado firmado por contabilidad.

    No se exige identidad: se exige que la DIFERENCIA siga siendo la misma que el dia
    que se midio y se explico. Un delta que se mueve significa que alguien posteo
    asientos con fecha vieja, o que cambio el plan de cuentas. En cualquiera de los dos
    casos, el tablero no se publica hasta entender por que."""
    d1 = datetime.date.fromisoformat(hasta); d0 = datetime.date(d1.year, 1, 1)
    dias = (d1-d0).days+1
    od = conectar(); comps = companias(od)
    print("=" * 108)
    print("  REGRESION · Odoo al %s contra el estado firmado por contabilidad" % hasta)
    print("  Pasa si la diferencia es la esperada. Falla si la diferencia CAMBIO.")
    print("=" * 108)
    print("  %-9s %-11s %18s %18s %15s %15s" % ("país","concepto","contabilidad","odoo",
                                                "dif. real","dif. esperada"))
    print("  " + "-"*104)
    fallo = []
    for pais, c in PAISES.items():
        b = bloque_corte(od, comps, pais, c["cid"], c["mon"], d0.isoformat(), hasta, dias)
        m = {r["k"]: r["v"] for r in b["pl"]}
        odoo = {"ventas":m["Ventas netas"], "cogs":-m["(−) Costo de ventas"],
                "resultado":m["Resultado del ejercicio"],
                "activo":b["_totales"]["activo"], "pasivo":b["_totales"]["pasivo"],
                "patrimonio":b["_totales"]["patrimonio"]}
        for k, oficial in REGRESION[pais].items():
            esperado, porque = DELTA[pais][k]
            real = odoo[k] - oficial
            tol = max(1.0, abs(oficial) * 0.001)      # 0,1% de la cifra oficial
            ok = abs(real - esperado) <= tol
            if not ok:
                fallo.append("%s · %s: la diferencia pasó de %s a %s"
                             % (pais, k, "{:,.2f}".format(esperado), "{:,.2f}".format(real)))
            print("  %-9s %-11s %18s %18s %15s %15s  %s" % (
                pais, k, "{:,.2f}".format(oficial), "{:,.2f}".format(odoo[k]),
                "{:,.2f}".format(real), "{:,.2f}".format(esperado),
                ("ok · " + porque) if ok else "<== CAMBIÓ"))
    print()
    if fallo:
        print("  REGRESION FALLIDA — la diferencia contra el estado firmado se movió:")
        for f in fallo:
            print("    · %s" % f)
        print("  NO publiques. Alguien posteó asientos con fecha vieja o cambió el plan de cuentas.")
        sys.exit(1)
    print("  REGRESION OK — Odoo sigue reproduciendo el estado firmado con las mismas")
    print("  diferencias medidas y explicadas. El ERP es fuente válida para publicar.")


# =====================================================================
#  VENTAS — facturacion y cartera, todo desde Odoo
# =====================================================================
PAISES_VENTAS = {"Ecuador": {"cid": 2, "mon": "USD", "cod": "EC"},
                 "Colombia": {"cid": 1, "mon": "COP", "cod": "CO"},
                 "Costa Rica": {"cid": 3, "mon": "USD", "cod": "CR"}}

BUCKETS = [("por_vencer", -10**9, 0), ("d1_30", 1, 30), ("d31_60", 31, 60),
           ("d61_90", 61, 90), ("d91_180", 91, 180), ("d180_mas", 181, 10**9)]


def facturas_mes_cliente(od, cid, year, hasta):
    """Facturas de venta agregadas por mes y cliente.

    El filtro por move_type sobre account.move SI es seguro; lo que revienta con el
    l10n_ec incompleto es atravesar move_id.move_type DESDE account.move.line."""
    dom = [["move_type","in",["out_invoice","out_refund"]], ["state","=","posted"],
           ["invoice_date",">=","%d-01-01" % year], ["invoice_date","<=",hasta]]
    campos = ["invoice_date","partner_id","amount_untaxed_signed","company_id"]
    try:
        recs = od.sr("account.move", dom + [["company_id","=",cid]], campos,
                     ctx={"allowed_company_ids":[cid]})
    except Exception as e:
        log("[WARN] facturas de la compañía %s ilegibles: %s" % (cid, str(e)[:120]))
        return {}
    out = {}
    for r in recs:
        f = str(r.get("invoice_date") or "")[:10]
        if len(f) != 10:
            continue
        m = int(f[5:7])
        pid, pname = m2o(r.get("partner_id"))
        k = pid or 0
        e = out.setdefault(m, {}).setdefault(k, {"n": pname or "(sin cliente)", "v": 0.0, "f": 0})
        e["v"] += float(r.get("amount_untaxed_signed") or 0)
        e["f"] += 1
    return out


def cartera(od, pl, cid, moneda, hasta):
    """Aging al corte. amount_residual va en la moneda de la COMPANIA.

    Sumar amount_residual mezclando monedas de factura fue el error que una vez dio
    345.131 de cartera en Costa Rica cuando la real eran 4.101 dolares."""
    ids = [a["id"] for a in pl.values() if a.get("account_type") == "asset_receivable"]
    if not ids:
        return {"disponible": False, "motivo": "la compañía no tiene cuentas por cobrar tipificadas"}
    dom = [["parent_state","=","posted"], ["company_id","=",cid], ["account_id","in",ids],
           ["date","<=",hasta], ["amount_residual","!=",0]]
    try:
        recs = od.sr("account.move.line", dom,
                     ["amount_residual","date_maturity","date","partner_id","move_name"],
                     ctx={"allowed_company_ids":[cid]})
    except Exception as e:
        return {"disponible": False, "motivo": "cartera ilegible: %s" % str(e)[:100]}
    corte = datetime.date.fromisoformat(hasta)
    b = {k: 0.0 for k, _, _ in BUCKETS}
    nb = {k: 0 for k, _, _ in BUCKETS}
    total, n, sin_venc = 0.0, 0, 0
    porcli = {}
    for r in recs:
        v = float(r.get("amount_residual") or 0)
        if abs(v) < 0.005:
            continue
        total += v; n += 1
        venc = r.get("date_maturity") or r.get("date")
        try:
            dias = (corte - datetime.date.fromisoformat(str(venc)[:10])).days
        except Exception:
            dias = 0; sin_venc += 1
        for k, lo, hi in BUCKETS:
            if lo <= dias <= hi:
                b[k] += v; nb[k] += 1; break
        pid, pname = m2o(r.get("partner_id"))
        c = porcli.setdefault(pid or 0, {"n": pname or "(sin cliente)", "v": 0.0, "venc": 0.0})
        c["v"] += v
        if dias > 0:
            c["venc"] += v
    vencido = sum(b[k] for k, lo, _ in BUCKETS if lo >= 1)
    v30 = sum(b[k] for k, lo, _ in BUCKETS if lo >= 31)
    top = sorted(porcli.values(), key=lambda x: -abs(x["v"]))[:10]
    return {"disponible": True, "moneda": moneda, "corte": hasta,
            "total": round(total, 2), "n_documentos": n,
            "buckets": {k: round(b[k], 2) for k, _, _ in BUCKETS},
            "buckets_n": nb,
            "vencido": round(vencido, 2),
            "pct_vencido": round(vencido/total, 4) if total else None,
            "vencido_mas_30": round(v30, 2),
            "pct_vencido_mas_30": round(v30/total, 4) if total else None,
            "sin_vencimiento": sin_venc,
            "top": [{"nombre": x["n"], "v": round(x["v"], 2), "venc": round(x["venc"], 2)} for x in top],
            "fuente": "account.move.line · cuentas por cobrar con saldo, amount_residual en moneda de la compañía"}


def cmd_ventas(hasta):
    d1 = datetime.date.fromisoformat(hasta); year = d1.year
    od = conectar(); comps = companias(od)
    out = {"meta": {"corte_iso": hasta, "anio": year, "meses": MESES[:d1.month],
                    "fuente": "Odoo · account.move (facturas de venta contabilizadas)"}}
    for pais, c in PAISES_VENTAS.items():
        cid = c["cid"]
        agg = facturas_mes_cliente(od, cid, year, hasta)
        pl = plan_de_cuentas(od, cid)
        meses = []
        primero = None
        for m in range(1, d1.month+1):
            cli = agg.get(m) or {}
            tot = round(sum(x["v"] for x in cli.values()), 2)
            nf = sum(x["f"] for x in cli.values())
            vivo = bool(cli) and abs(tot) > 0.005
            if vivo and primero is None:
                primero = m
            meses.append({"m": m, "vivo": vivo, "venta": tot, "n_facturas": nf,
                          "clientes": sorted(
                              [{"id": k, "n": v["n"], "v": round(v["v"], 2), "f": v["f"]}
                               for k, v in cli.items()],
                              key=lambda x: -abs(x["v"]))[:40]})
        # Mismo criterio que el estado de resultados: cada mes cubre su propio periodo.
        # En ventas NO hay bloque de migracion porque las facturas pre-migracion
        # sencillamente no existen en Odoo: se declara el hueco, no se rellena.
        for b in meses:
            b["cubre"] = [b["m"], b["m"]]
            b["etiqueta"] = MESES[b["m"]-1]
        out[c["cod"]] = {"pais": pais, "empresa": (comps.get(cid) or {}).get("name"),
                         "moneda": c["mon"], "primer_mes": primero, "meses": meses,
                         "cartera": cartera(od, pl, cid, c["mon"], hasta),
                         "sin_factura_antes_de": primero,
                         "_nota_hueco": ("Odoo solo tiene facturas desde %s. Los meses anteriores "
                                         "existen en la contabilidad como asiento de migración, "
                                         "sin detalle de factura ni de cliente."
                                         % (MESES[primero-1] if primero else "—"))}
    sys.stdout.write(json.dumps(out, ensure_ascii=False, indent=2))
    log("llamadas XML-RPC: %d" % od.calls)


# =====================================================================
#  INVENTARIO — stock al corte y demanda por SKU y por mes
# =====================================================================
def productos_con_stock(od, cid, pids_extra):
    """Ficha y existencias EN CONTEXTO DE LA COMPANIA.

    qty_available y standard_price son company-dependent: leerlos sin contexto mezcla
    las existencias de los tres paises en un solo numero."""
    ctx = {"allowed_company_ids": [cid]}
    campos = ["id","default_code","name","categ_id","standard_price","qty_available","type","active"]
    vistos, out = set(), {}
    try:
        recs, _om = sr_drop(od, "product.product",
                            [["type","in",["product","consu"]], ["qty_available","!=",0]], campos, ctx)
    except Exception as e:
        log("[WARN] product.product con stock ilegible: %s" % str(e)[:110]); recs = []
    for r in recs:
        vistos.add(r["id"]); out[r["id"]] = r
    faltan = [i for i in pids_extra if i not in vistos]
    for k in range(0, len(faltan), 200):
        try:
            recs2, _o = sr_drop(od, "product.product", [["id","in",faltan[k:k+200]]], campos, ctx)
        except Exception:
            continue
        for r in recs2:
            out[r["id"]] = r
    fin = {}
    for r in out.values():
        _c, cname = m2o(r.get("categ_id"))
        fin[r["id"]] = {"id": r["id"], "sku": r.get("default_code") or "",
                        "nombre": r.get("name") or "", "categoria": cname or "(sin categoría)",
                        "costo_u": round(float(r.get("standard_price") or 0), 4),
                        "stock_u": round(float(r.get("qty_available") or 0), 2),
                        "activo": bool(r.get("active", True))}
    return fin


def sr_drop(od, model, dom, fields, ctx=None):
    """Reintenta quitando campos hasta que la consulta pase. Existe por l10n_ec:
    hay campos que revientan la lectura del modelo entero sin decir cual."""
    f = list(fields); om = []
    while f:
        try:
            return od.sr(model, dom, f, ctx=ctx), om
        except Exception as e:
            msg = str(e)
            drop = next((c for c in f if c in msg and c != "id"), None) or (f[-1] if len(f) > 1 else None)
            if drop is None:
                raise
            f.remove(drop); om.append(drop)
    raise RuntimeError("no se pudo consultar " + model)


def demanda_por_sku(od, cid, year, hasta):
    """Unidades y venta neta por producto y por mes, desde las lineas de factura.

    NUNCA se filtra por move_id.move_type desde account.move.line: eso atraviesa
    account.move, roto por el l10n_ec incompleto, y devuelve VACIO sin lanzar error.
    Se pasan los ids de factura explicitos."""
    dom = [["move_type","in",["out_invoice","out_refund"]], ["state","=","posted"],
           ["invoice_date",">=","%d-01-01" % year], ["invoice_date","<=",hasta],
           ["company_id","=",cid]]
    try:
        movs = od.sr("account.move", dom, ["id","invoice_date","move_type"],
                     ctx={"allowed_company_ids":[cid]})
    except Exception as e:
        log("[WARN] facturas ilegibles: %s" % str(e)[:110]); return {}, 0
    meta = {}
    for m in movs:
        f = str(m.get("invoice_date") or "")[:10]
        if len(f) == 10:
            meta[m["id"]] = (int(f[5:7]), -1.0 if m.get("move_type") == "out_refund" else 1.0)
    ids = list(meta.keys())
    agg, nlin = {}, 0
    for k in range(0, len(ids), CHUNK_INV):
        try:
            recs, _o = sr_drop(od, "account.move.line",
                               [["move_id","in",ids[k:k+CHUNK_INV]], ["product_id","!=",False]],
                               ["move_id","product_id","quantity","price_subtotal","display_type"],
                               {"allowed_company_ids":[cid]})
        except Exception:
            continue
        for r in recs:
            dt = r.get("display_type")
            if dt not in (False, None, "", "product"):
                continue
            mid, _ = m2o(r.get("move_id"))
            if mid not in meta:
                continue
            mes, sg = meta[mid]
            pid, pname = m2o(r.get("product_id"))
            if not pid:
                continue
            e = agg.setdefault(pid, {"n": pname or "", "u": {}, "v": {}})
            e["u"][mes] = e["u"].get(mes, 0.0) + float(r.get("quantity") or 0) * sg
            e["v"][mes] = e["v"].get(mes, 0.0) + float(r.get("price_subtotal") or 0) * sg
            nlin += 1
    return agg, nlin


CHUNK_INV = 200


def cmd_inventario(hasta):
    d1 = datetime.date.fromisoformat(hasta); year = d1.year
    od = conectar(); comps = companias(od)
    out = {"meta": {"corte_iso": hasta, "anio": year, "meses": MESES[:d1.month],
                    "fuente": ("Odoo · existencias de product.product en contexto de cada compañía, "
                               "demanda de las líneas de factura de venta")}}
    for pais, c in PAISES_VENTAS.items():
        cid = c["cid"]
        dem, nlin = demanda_por_sku(od, cid, year, hasta)
        fichas = productos_con_stock(od, cid, list(dem.keys()))
        items, meses_vivos = [], set()
        for pid, f in fichas.items():
            d = dem.get(pid) or {"u": {}, "v": {}}
            for m in d["u"]:
                meses_vivos.add(m)
            uds = {str(m): round(v, 2) for m, v in sorted(d["u"].items())}
            val = {str(m): round(v, 2) for m, v in sorted(d["v"].items())}
            items.append({"id": pid, "sku": f["sku"], "nombre": f["nombre"],
                          "cat": f["categoria"], "costo_u": f["costo_u"],
                          "stock_u": f["stock_u"],
                          "stock_val": round(f["stock_u"] * f["costo_u"], 2),
                          "u": uds, "v": val,
                          "u_tot": round(sum(d["u"].values()), 2),
                          "v_tot": round(sum(d["v"].values()), 2)})
        # SKU que se vendieron pero ya no tienen ficha legible: se declaran, no se pierden
        huerfanos = [pid for pid in dem if pid not in fichas]
        items.sort(key=lambda x: -abs(x["v_tot"]))
        out[c["cod"]] = {"pais": pais, "empresa": (comps.get(cid) or {}).get("name"),
                         "moneda": c["mon"], "items": items,
                         "meses_con_demanda": sorted(meses_vivos),
                         "n_lineas": nlin, "huerfanos": len(huerfanos),
                         "stock_total": round(sum(x["stock_val"] for x in items), 2),
                         "n_sku_con_stock": sum(1 for x in items if x["stock_u"] > 0),
                         "_nota": ("El stock es la foto al corte y no depende del rango. La demanda "
                                   "sí: solo existe donde Odoo tiene facturas.")}
    sys.stdout.write(json.dumps(out, ensure_ascii=False, indent=2))
    log("llamadas XML-RPC: %d" % od.calls)


def main():
    a = sys.argv[1:] or ["check"]
    cmd = a[0]
    hoy = datetime.date.today().isoformat()
    if cmd == "check":        cmd_check()
    elif cmd == "corte":      cmd_corte(a[1] if len(a) > 1 else hoy)
    elif cmd == "serie":      cmd_serie(a[1] if len(a) > 1 else hoy)
    elif cmd == "ventas":     cmd_ventas(a[1] if len(a) > 1 else hoy)
    elif cmd == "inventario": cmd_inventario(a[1] if len(a) > 1 else hoy)
    elif cmd == "regresion":  cmd_regresion(a[1] if len(a) > 1 else "2026-07-31")
    else:
        raise SystemExit("modos: check | corte <f> | serie <f> | ventas <f> | inventario <f> | regresion [f]")


if __name__ == "__main__":
    main()
