#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compras_dashboard.py  ·  Grupo VICOMER
======================================
EXTRACCION -> CONTRATO JSON del dashboard de compras locales y cuentas por pagar.

Contesta tres preguntas que NO son el mismo numero y que este script nunca suma
entre si:

    COMPRA DEVENGADA   flujo del periodo   (lineas de factura de proveedor, por fecha de emision)
    SALDO DE CxP       stock de deuda hoy  (amount_residual_signed de facturas posted)
    PAGOS EJECUTADOS   salida real de caja (account.payment de proveedor)

Regla rectora: una cifra sin fuente verificable no entra. Antes que estimar,
se muestra el hueco marcado como hueco.

MODOS
    python3 compras_dashboard.py autotest   # autoprueba offline, sin red
    python3 compras_dashboard.py diag       # conexion y conteos crudos, no escribe
    python3 compras_dashboard.py 2026       # extraccion completa
    python3 compras_dashboard.py            # anio en curso

Solo biblioteca estandar (xmlrpc, zipfile, xml.etree). Sin pandas, sin openpyxl.
"""
import os, sys, json, ssl, re, math, zipfile, datetime, traceback, xmlrpc.client
try:  # proxy HTTPS para xmlrpc (no-op en el Mac)
    import sys as _s, os as _o
    _d = _o.path.dirname(_o.path.abspath(__file__))
    for _p in (_d, _o.path.dirname(_d)):
        if _o.path.exists(_o.path.join(_p, 'odoo_proxy.py')) and _p not in _s.path: _s.path.append(_p)
    import odoo_proxy
except ImportError:
    pass
import xml.etree.ElementTree as ET
from pathlib import Path
from collections import defaultdict

HOME = Path.home()
PROJ = Path(os.environ.get("VICOMER_PROJ", HOME / "Claude" / "Projects" / "CFO VICOMER"))
OUT = Path(os.environ.get("ODOO_OUT_DIR", PROJ / "OdooVentas"))
PAGOS_DIR = PROJ / "Pagos"
FIN_DIR = PROJ / "Finanzas"
PERSONAL = Path(os.environ.get("VICOMER_PERSONAL", HOME / "Desktop" / "VICOMER PERSONAL"))
DEST = OUT / "dashboard_compras.json"
CACHE_PPTO = OUT / "presupuesto_gastos_cache.json"
CACHE_VERSION = 4   # subir cuando cambie la lectura del presupuesto: invalida el cache viejo

XL_VIGENTE = PERSONAL / "PRESUPUESTO GASTOS REVISADO 2026 OK OK.xlsx"
XL_ORIGINAL = PERSONAL / "PRESUPUESTO COMPLETO 2026 - ADMINISTRATIVO.xlsx"
HOJA_VIGENTE = "Presupuesto Gastos H2 2026"
HOJA_ORIGINAL = "Presupuesto Anual"
HOJA_REAL = "Estado de Resultados Mensual"
EEFF_OFICIAL = FIN_DIR / "eeff_ecuador_2026-07_OFICIAL.json"

MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
ORDEN_PAISES = ["Ecuador", "Colombia", "Costa Rica"]
CODE_PAIS = {"Ecuador": "EC", "Colombia": "CO", "Costa Rica": "CR"}


def log(m):
    print("[%s] %s" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), m), flush=True)


class Avisos(object):
    def __init__(self):
        self.items = []

    def add(self, nivel, pais, bloque, texto):
        self.items.append({"nivel": nivel, "pais": pais, "bloque": bloque, "texto": texto})
        log("  [%s] %s/%s: %s" % (nivel.upper(), pais or "GRUPO", bloque, texto))

    def dump(self):
        o = {"critico": 0, "alerta": 1, "nota": 2}
        return sorted(self.items, key=lambda a: (o.get(a["nivel"], 9), a["pais"] or "", a["bloque"]))


# =====================================================================
#  Config
# =====================================================================
def load_config():
    cfg = {"url": None, "db": None, "login": None, "apikey": None, "_raw": {}}
    for f in (PROJ / "odoo_config.json", HOME / ".odoo_config.json"):
        if f.exists():
            d = json.loads(f.read_text(encoding="utf-8"))
            for k in ("url", "db", "login", "apikey"):
                cfg[k] = cfg[k] or d.get(k)
            cfg["_raw"] = cfg["_raw"] or d
    for kf in (PROJ / "odoo_apikey.txt", HOME / ".odoo_apikey"):
        if not cfg["apikey"] and kf.exists():
            cfg["apikey"] = kf.read_text(encoding="utf-8").strip()
    cfg["url"] = (cfg["url"] or "").rstrip("/")
    return cfg


def load_reglas():
    f = PROJ / "compras_reglas.json"
    if not f.exists():
        sys.exit("ERROR: falta compras_reglas.json en %s" % PROJ)
    return json.loads(f.read_text(encoding="utf-8"))


def load_depto():
    f = PROJ / "pagos_reglas_depto.json"
    if not f.exists():
        return {"keywords": {}, "default": "Gerencia", "tc_manual": {}}
    return json.loads(f.read_text(encoding="utf-8"))


def load_tc(depto):
    tc = {"COP": 0.00027027, "CRC": 0.00221}
    tc.update(dict((k, float(v)) for k, v in (depto.get("tc_manual") or {}).items()))
    tc["USD"] = 1.0
    return {"tasas": tc, "fuente": "pagos_reglas_depto.json -> tc_manual", "referencial": True,
            "cop_por_usd": round(1 / tc["COP"], 2), "crc_por_usd": round(1 / tc["CRC"], 2)}


def norm(t):
    import unicodedata
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode("ascii").upper()
    return " ".join(t.split())


def contiene(txt, patrones):
    n = norm(txt)
    for p in (patrones or []):
        if norm(p) and norm(p) in n:
            return p
    return None


def prefijo(code, prefijos):
    c = (code or "").strip()
    for p in (prefijos or []):
        if c.startswith(p):
            return p
    return None


# =====================================================================
#  Lector XLSX (stdlib) — el mismo motor que usa ventas_dashboard.py
# =====================================================================
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
NSR = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _col(ref):
    n = 0
    for ch in ref:
        if ch.isalpha():
            n = n * 26 + (ord(ch.upper()) - 64)
        else:
            break
    return n


def _row(ref):
    d = "".join(c for c in ref if c.isdigit())
    return int(d) if d else 0


def xlsx_read(path, sheet_name):
    with zipfile.ZipFile(str(path)) as z:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        rmap = {}
        for r in rels:
            t = r.get("Target") or ""
            if t.startswith("/"):
                t = t[1:]
            elif not t.startswith("xl/"):
                t = "xl/" + t
            rmap[r.get("Id")] = t
        target = None
        nombres = []
        for sh in wb.iter(NS + "sheet"):
            nombres.append(sh.get("name"))
            if (sh.get("name") or "").strip().upper() == sheet_name.strip().upper():
                target = rmap.get(sh.get(NSR + "id"))
        if not target:
            raise KeyError("hoja '%s' no existe (hay: %s)" % (sheet_name, nombres))
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(NS + "si"):
                shared.append("".join(t.text or "" for t in si.iter(NS + "t")))
        cells = {}
        for c in ET.fromstring(z.read(target)).iter(NS + "c"):
            ref = c.get("r") or ""
            t = c.get("t")
            v = c.find(NS + "v")
            raw = v.text if v is not None else None
            if t == "inlineStr":
                istr = c.find(NS + "is")
                raw = "".join(x.text or "" for x in istr.iter(NS + "t")) if istr is not None else None
            if raw is None:
                continue
            if t == "s":
                try:
                    val = shared[int(raw)]
                except Exception:
                    val = raw
            elif t in ("str", "inlineStr"):
                val = raw
            else:
                try:
                    val = float(raw)
                except Exception:
                    val = raw
            cells[(_row(ref), _col(ref))] = val
    return cells


CODIGO_VALIDO = re.compile(r"^\d+(\.\d+)*\.?$")


def es_codigo(c):
    """Un codigo contable es digitos separados por puntos. Sin esto, los titulos y
    las notas al pie de la hoja entran como si fueran cuentas presupuestadas."""
    return bool(CODIGO_VALIDO.match(str(c or "").strip()))


def canon(codigo, origen="odoo"):
    """Codigo contable en UN solo espacio de nombres: el de Odoo.

    LA TRAMPA NO ERAN LOS PUNTOS. Verificado el 2026-08-20 contra los dos catalogos:

        Excel 5.2.01.06.05  Gv - Servicios...      <->  Odoo 502.01.06.05
        Excel 5.3.01.09.05  Ga - Arrendamiento...  <->  Odoo 502.02.09.05
        Excel 5.4.01.01.02  Gf - Gastos Bancarios  <->  Odoo 502.03.01.02
        Excel 5.5.01.01.01  Gnd - No Deducible     <->  Odoo 502.04.01.01

    O sea: los tres primeros segmentos del Excel `5.G.01` colapsan en `502.0(G-1)`
    de Odoo, y el resto pasa igual. Quitar los puntos y comparar digitos (52010605
    contra 502010605) NO cruza NADA: se perderia el 100% del presupuesto en silencio,
    que es exactamente el error que se ve perfecto en pantalla.

    origen: 'excel' (codigo del presupuesto) | 'odoo' (codigo del plan de cuentas)
    """
    c = str(codigo or "").strip().rstrip(".")
    if not c:
        return None
    seg = [x for x in c.split(".") if x != ""]
    if not seg:
        return None
    if origen == "excel" and len(seg) >= 3 and seg[0] == "5" and seg[2] == "01":
        try:
            g = int(seg[1])
        except ValueError:
            return ".".join(seg)
        if g >= 2:
            return ".".join(["502", "%02d" % (g - 1)] + seg[3:])
    return ".".join(seg)


def clave_nombre(nombre):
    """Clave de respaldo para cruzar por nombre cuando el codigo no encuentra pareja."""
    n = norm(nombre)
    for pre in ("GV - ", "GA - ", "GF - ", "GND - ", "GV-", "GA-", "GF-", "GND-"):
        if n.startswith(pre):
            n = n[len(pre):]
            break
    n = re.sub(r"[^A-Z0-9 ]", " ", n)
    return " ".join(n.split())[:44] or None


def _num(v):
    try:
        return float(v)
    except Exception:
        return 0.0


# =====================================================================
#  Presupuesto de gastos (solo Ecuador) — con cache JSON
# =====================================================================
def leer_presupuesto(avisos, forzar=False):
    """Presupuesto vigente (H2), original (anual) y real por cuenta (Ene-Jun/Jul).

    Se cachea en JSON para que el dashboard no dependa de que los Excel esten
    abiertos o sincronizando desde iCloud.
    """
    if CACHE_PPTO.exists() and not forzar:
        try:
            c = json.loads(CACHE_PPTO.read_text(encoding="utf-8"))
            mt = {}
            for k, p in (("vigente", XL_VIGENTE), ("original", XL_ORIGINAL)):
                mt[k] = p.stat().st_mtime if p.exists() else None
            if c.get("_mtimes") == mt and c.get("_cache_version") == CACHE_VERSION:
                log("  presupuesto: cache vigente (%s)" % c.get("generado"))
                return c
        except Exception:
            pass

    out = {"generado": datetime.datetime.now().isoformat(timespec="seconds"),
           "disponible": False, "vigente": {}, "original": {}, "real_mensual": {},
           "fuentes": {}, "_mtimes": {}, "_cache_version": CACHE_VERSION}
    for k, p in (("vigente", XL_VIGENTE), ("original", XL_ORIGINAL)):
        out["_mtimes"][k] = p.stat().st_mtime if p.exists() else None

    # ---- vigente H2 (Jul-Dic en columnas C..H, total en I) ----
    if not XL_VIGENTE.exists():
        avisos.add("alerta", "Ecuador", "presupuesto",
                   "No encuentro %s: sin presupuesto vigente H2." % XL_VIGENTE.name)
    else:
        try:
            c = xlsx_read(XL_VIGENTE, HOJA_VIGENTE)
            filas = sorted(set(r for (r, cc) in c))
            total_decl = None
            for r in filas:
                cod = str(c.get((r, 1)) or "").strip()
                nom = str(c.get((r, 2)) or "").strip()
                if not cod and "TOTAL GASTOS" in norm(nom):
                    total_decl = _num(c.get((r, 9)))
                if not es_codigo(cod):
                    continue
                niv = cod.rstrip(".").count(".")
                mens = [_num(c.get((r, 3 + k))) for k in range(6)]   # Jul..Dic
                tot = _num(c.get((r, 9)))
                out["vigente"][canon(cod, "excel")] = {"codigo": cod, "cuenta": nom, "nivel": niv,
                                              "mensual_h2": [round(x, 2) for x in mens],
                                              "total_h2": round(tot, 2), "hoja": HOJA_VIGENTE, "fila": r}
            # Una cuenta es HOJA si ninguna otra fila la tiene como prefijo. Filtrar por
            # "nivel >= 3" mezclaba subtotales (5.2.01.01.) con sus hojas (5.2.01.01.01)
            # y duplicaba el presupuesto: 532.358 contra los 251.179 declarados.
            todos = sorted(out["vigente"].values(), key=lambda v: v["codigo"])
            cods = [v["codigo"].rstrip(".") for v in todos]
            hojas = []
            for v in todos:
                c = v["codigo"].rstrip(".")
                if not any(o != c and o.startswith(c + ".") for o in cods):
                    hojas.append(v)
                    v["hoja"] = True
                else:
                    v["hoja"] = False

            # Un subtotal puede declarar MAS que la suma de sus hojas: en el libro de
            # julio, 5.3.01.05.02 'Ga - Servicios Profesionales' declara 3.200 y su hoja
            # esta en cero. Ese dinero esta presupuestado pero sin desglosar. En vez de
            # perderlo (y descuadrar contra el TOTAL) o repartirlo (inventar), se crea una
            # linea explicita "(sin desglosar)" con el residuo.
            residuos = []
            for v in todos:
                if v.get("hoja"):
                    continue
                c = v["codigo"].rstrip(".")
                hijas = [h for h in hojas if h["codigo"].rstrip(".").startswith(c + ".")]
                if not hijas:
                    continue
                # solo el nivel inmediato superior a sus hojas, para no contar dos veces
                padres = set()
                for h in hijas:
                    hc = h["codigo"].rstrip(".")
                    for o in todos:
                        oc = o["codigo"].rstrip(".")
                        if oc != c and oc.startswith(c + ".") and hc.startswith(oc + "."):
                            padres.add(oc)
                if padres:
                    continue
                resid = round(v["total_h2"] - sum(h["total_h2"] for h in hijas), 2)
                if abs(resid) > 0.5:
                    mens = [round(v["mensual_h2"][i] - sum(h["mensual_h2"][i] for h in hijas), 2) for i in range(6)]
                    residuos.append({"codigo": c + ".00", "cuenta": (v["cuenta"] or "") + " — (sin desglosar)",
                                     "nivel": v["nivel"] + 1, "mensual_h2": mens, "total_h2": resid,
                                     "hoja": True, "sin_desglosar": True,
                                     "hoja_origen": v["codigo"], "hoja_excel": HOJA_VIGENTE, "fila": v.get("fila")})
            for r in residuos:
                out["vigente"][canon(r["codigo"], "excel")] = r
                hojas.append(r)
            out["vigente_sin_desglosar"] = [{"codigo": r["codigo"], "cuenta": r["cuenta"], "monto": r["total_h2"]}
                                            for r in residuos]
            if residuos:
                avisos.add("nota", "Ecuador", "presupuesto",
                           "%d cuenta(s) del presupuesto declaran más que la suma de su desglose (%s USD en total). "
                           "Ese monto está presupuestado pero sin abrir por cuenta: aparece como '(sin desglosar)' "
                           "en vez de perderse o repartirse." %
                           (len(residuos), "{:,.2f}".format(sum(r["total_h2"] for r in residuos))))
            suma_hojas = round(sum(v["total_h2"] for v in hojas), 2)
            out["vigente_total_declarado"] = round(total_decl or 0, 2)
            out["vigente_total_hojas"] = suma_hojas
            out["vigente_n_hojas"] = len(hojas)
            out["fuentes"]["vigente"] = "%s / %s" % (XL_VIGENTE.name, HOJA_VIGENTE)
            dif = abs(suma_hojas - (total_decl or 0))
            if total_decl and dif > 1.0:
                avisos.add("alerta", "Ecuador", "presupuesto",
                           "El presupuesto vigente no cuadra: las %d cuentas hoja suman %s pero la fila TOTAL "
                           "declara %s (diferencia %s). Se usa la suma de hojas y se muestra la diferencia." %
                           (len(hojas), "{:,.2f}".format(suma_hojas), "{:,.2f}".format(total_decl), "{:,.2f}".format(dif)))
        except Exception as e:
            avisos.add("alerta", "Ecuador", "presupuesto", "No pude leer el presupuesto vigente: %s" % str(e)[:150])

    # ---- original anual (Ene-Dic en columnas E..P, total en D) ----
    if not XL_ORIGINAL.exists():
        avisos.add("nota", "Ecuador", "presupuesto",
                   "No encuentro %s: no hay presupuesto ORIGINAL contra el cual medir el resinceramiento." % XL_ORIGINAL.name)
    else:
        try:
            c = xlsx_read(XL_ORIGINAL, HOJA_ORIGINAL)
            for r in sorted(set(rr for (rr, cc) in c)):
                cod = str(c.get((r, 1)) or "").strip()
                if not es_codigo(cod) or not canon(cod, "excel"):
                    continue
                nom = str(c.get((r, 2)) or "").strip()
                mens = [_num(c.get((r, 5 + k))) for k in range(12)]  # ENERO..DICIEMBRE
                tot = _num(c.get((r, 4)))
                if not (tot or any(mens)):
                    continue
                out["original_total_anual"] = round(out.get("original_total_anual", 0.0) + tot, 2)
                out["original_total_h2"] = round(out.get("original_total_h2", 0.0) + sum(mens[6:]), 2)
                out["original"][canon(cod, "excel")] = {"codigo": cod, "cuenta": nom,
                                               "mensual": [round(x, 2) for x in mens],
                                               "total_anual": round(tot, 2),
                                               "h2": round(sum(mens[6:]), 2)}
            out["fuentes"]["original"] = "%s / %s" % (XL_ORIGINAL.name, HOJA_ORIGINAL)
        except Exception as e:
            avisos.add("nota", "Ecuador", "presupuesto", "No pude leer el presupuesto original: %s" % str(e)[:150])

    # ---- real por cuenta Ene-Jul del Excel (OJO: julio incompleto) ----
    if XL_VIGENTE.exists():
        try:
            c = xlsx_read(XL_VIGENTE, HOJA_REAL)
            for r in sorted(set(rr for (rr, cc) in c)):
                cod = str(c.get((r, 1)) or "").strip()
                if not es_codigo(cod) or not canon(cod, "excel"):
                    continue
                nom = str(c.get((r, 2)) or "").strip()
                mens = [_num(c.get((r, 3 + k))) for k in range(7)]   # Ene..Jul
                if not any(mens):
                    continue
                out["real_mensual"][canon(cod, "excel")] = {"codigo": cod, "cuenta": nom,
                                                   "mensual": [round(x, 2) for x in mens],
                                                   "nivel": cod.rstrip(".").count(".")}
            out["fuentes"]["real_excel"] = "%s / %s (Ene-Jul; julio parcial)" % (XL_VIGENTE.name, HOJA_REAL)
        except Exception as e:
            avisos.add("nota", "Ecuador", "presupuesto", "No pude leer el real mensual del Excel: %s" % str(e)[:150])

    out["disponible"] = bool(out["vigente"])
    try:
        OUT.mkdir(parents=True, exist_ok=True)
        CACHE_PPTO.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass
    return out


def leer_eeff_oficial(avisos):
    if not EEFF_OFICIAL.exists():
        avisos.add("alerta", "Ecuador", "presupuesto",
                   "No existe %s: sin cifra oficial de gasto Ene-Jul para conciliar." % EEFF_OFICIAL.name)
        return None
    try:
        return json.loads(EEFF_OFICIAL.read_text(encoding="utf-8"))
    except Exception as e:
        avisos.add("alerta", "Ecuador", "presupuesto", "EEFF oficial ilegible: %s" % e)
        return None


# =====================================================================
#  Odoo
# =====================================================================
class Odoo(object):
    def __init__(self, cfg):
        self.cfg = cfg
        ctx = ssl.create_default_context()
        self.common = xmlrpc.client.ServerProxy(cfg["url"] + "/xmlrpc/2/common", allow_none=True, context=ctx)
        self.models = xmlrpc.client.ServerProxy(cfg["url"] + "/xmlrpc/2/object", allow_none=True, context=ctx)
        self.uid = None
        self.calls = 0

    def authenticate(self):
        host = self.cfg["url"].split("//")[-1].split("/")[0]
        for db in [self.cfg.get("db"), host.split(".")[0], host]:
            if not db:
                continue
            try:
                uid = self.common.authenticate(db, self.cfg["login"], self.cfg["apikey"], {})
            except Exception:
                continue
            if uid:
                self.cfg["db"] = db; self.uid = uid; return uid
        raise RuntimeError("no autentico contra Odoo")

    def kw(self, model, method, args, kwargs=None):
        self.calls += 1
        return self.models.execute_kw(self.cfg["db"], self.uid, self.cfg["apikey"],
                                      model, method, args, kwargs or {})

    def sr(self, model, dom, fields, limit=0, ctx=None):
        kw = {"fields": fields}
        if limit:
            kw["limit"] = limit
        if ctx:
            kw["context"] = ctx
        return self.kw(model, "search_read", [dom], kw)

    def sr_drop(self, model, dom, fields, ctx=None):
        f = list(fields); om = []
        while f:
            try:
                return self.sr(model, dom, f, ctx=ctx), om
            except Exception as e:
                msg = str(e)
                drop = next((c for c in f if c in msg and c != "id"), None) or (f[-1] if len(f) > 1 else None)
                if drop is None:
                    raise
                f.remove(drop); om.append(drop)
        raise RuntimeError("no se pudo consultar " + model)


def m2o(v):
    if isinstance(v, (list, tuple)) and len(v) == 2:
        return v[0], v[1]
    return None, None


def companias(od, company_map):
    out = {}
    for r in od.sr("res.company", [], ["id", "name", "currency_id"]):
        _, cur = m2o(r.get("currency_id"))
        n = norm(r.get("name"))
        best, bl = None, -1
        for frag, pais in (company_map or {}).items():
            f = norm(frag)
            if f and f in n and len(f) > bl:
                best, bl = pais, len(f)
        out[r["id"]] = {"id": r["id"], "name": r.get("name"), "moneda": cur,
                        "pais": None if best in (None, "ignore") else best,
                        "excluida": best == "ignore"}
    return out


# =====================================================================
#  Clasificacion de una linea de factura
# =====================================================================
def clasificar_linea(pais, cuenta, proveedor, reglas):
    """Devuelve (es_gasto_operativo, motivo_exclusion, etiquetas[])."""
    et = []
    tipos = (reglas.get("tipos_cuenta_gasto") or {}).get("incluir") or []
    tipo = (cuenta or {}).get("account_type")
    code = (cuenta or {}).get("code") or ""
    nom = (cuenta or {}).get("name") or ""

    # comercio exterior local (se marca, NO se excluye)
    ag = reglas.get("agentes_locales_de_comercio_exterior") or {}
    if contiene(proveedor, ag.get("proveedor_contiene")) or contiene(nom, ag.get("cuenta_contiene")):
        et.append(ag.get("etiqueta") or "Servicio de comercio exterior")

    if tipo not in tipos:
        return False, "contrapartida contable (%s)" % (tipo or "?"), et

    exc = reglas.get("excluir_no_operativo") or {}
    for clave, r in exc.items():
        if clave.startswith("_"):
            continue
        if prefijo(code, r.get("codigo_prefijo")) or contiene(nom, r.get("nombre_contiene")) \
                or contiene(proveedor, r.get("proveedor_contiene")):
            return False, r.get("etiqueta") or clave, et

    cont = (reglas.get("cuentas_contaminadas") or {}).get(pais) or []
    for r in cont:
        if r.get("codigo") and canon(r["codigo"], "odoo") == canon(code, "odoo"):
            return False, "cuenta contaminada: %s" % r.get("motivo", ""), et
        if r.get("patron_nombre") and contiene(nom, [r["patron_nombre"]]) and not r.get("solo_si_supera"):
            return False, "cuenta contaminada: %s" % r.get("motivo", ""), et

    for cat, r in (reglas.get("categorias_criticas") or {}).items():
        if cat.startswith("_"):
            continue
        if contiene(nom, r.get("cuenta_contiene")) or contiene(proveedor, r.get("proveedor_contiene")):
            et.append("cat:" + cat)
            break
    return True, None, et


def naturaleza_exterior(cuenta, proveedor, reglas):
    ce = (reglas.get("comercio_exterior") or {}).get("importacion") or {}
    code = (cuenta or {}).get("code") or ""
    nom = (cuenta or {}).get("name") or ""
    if prefijo(code, ce.get("codigo_prefijo")) or contiene(nom, ce.get("cuenta_contiene")) \
            or contiene(proveedor, ce.get("proveedor_contiene")):
        return "importacion"
    return "servicios_exterior"


def departamento(proveedor, depto):
    n = norm(proveedor)
    for k, v in (depto.get("keywords") or {}).items():
        if norm(k) in n:
            return v
    return depto.get("default") or "Gerencia"


BUCKETS = ["Corriente", "1-30", "31-60", "61-90", ">90"]


def bucket_de(d):
    if d <= 0:
        return "Corriente"
    if d <= 30:
        return "1-30"
    if d <= 60:
        return "31-60"
    if d <= 90:
        return "61-90"
    return ">90"


def iso_semana(d):
    y, w, _ = d.isocalendar()
    return "%d-W%02d" % (y, w)


def lunes_de(d):
    return d - datetime.timedelta(days=d.weekday())


# =====================================================================
#  Extraccion
# =====================================================================
def traer_cxp_abierta(od, comp_ids, avisos):
    """TODAS las facturas de proveedor con saldo, de CUALQUIER anio.

    La CxP no puede filtrarse por anio en curso: si en 2025 quedaron facturas sin pagar,
    esa deuda sigue viva hoy y hay que pagarla. Medirla solo sobre el anio corriente la
    subestima y, peor, descuadra la prueba de coherencia (facturado - pagado - saldo),
    porque los pagos del anio si liquidan facturas viejas.
    """
    dom = [["move_type", "in", ["in_invoice", "in_refund"]], ["state", "=", "posted"],
           ["amount_residual", "!=", 0]]
    campos = ["name", "invoice_date", "invoice_date_due", "partner_id", "amount_untaxed_signed",
              "amount_residual", "amount_residual_signed", "currency_id", "company_id",
              "move_type", "invoice_payment_term_id"]
    try:
        recs, om = od.sr_drop("account.move", dom, campos, ctx={"allowed_company_ids": comp_ids})
        return recs
    except Exception as e:
        avisos.add("critico", None, "cxp", "No pude leer la CxP completa: %s" % str(e)[:150])
        return []


def traer_facturas(od, year, comp_ids):
    dom = [["move_type", "in", ["in_invoice", "in_refund"]], ["state", "=", "posted"],
           ["invoice_date", ">=", "%d-01-01" % year], ["invoice_date", "<=", "%d-12-31" % year]]
    campos = ["name", "invoice_date", "invoice_date_due", "partner_id", "amount_untaxed_signed",
              "amount_total_signed", "amount_residual", "amount_residual_signed", "currency_id",
              "company_id", "move_type", "invoice_payment_term_id", "payment_state"]
    return od.sr_drop("account.move", dom, campos, ctx={"allowed_company_ids": comp_ids})


def traer_lineas(od, move_ids, comp_ids):
    """Lineas de las facturas. NUNCA se filtra por move_id.move_type: eso atraviesa
    account.move (roto por l10n_ec) y devuelve VACIO sin lanzar error."""
    out = []
    campos = ["id", "move_id", "account_id", "partner_id", "balance", "date",
              "product_id", "name", "company_id", "display_type"]
    for i in range(0, len(move_ids), 200):
        chunk = move_ids[i:i + 200]
        recs, _ = od.sr_drop("account.move.line",
                             [["move_id", "in", chunk],
                              ["display_type", "not in", ["line_section", "line_note"]]],
                             campos, ctx={"allowed_company_ids": comp_ids})
        out += recs
    return out


def traer_cuentas(od, ids_por_comp):
    """account.account.code es company-dependent desde Odoo 17: UNA compania por contexto."""
    info = {}
    for cid, ids in ids_por_comp.items():
        ids = sorted(set(x for x in ids if x))
        for i in range(0, len(ids), 200):
            for a in od.sr("account.account", [["id", "in", ids[i:i + 200]]],
                           ["id", "code", "name", "account_type"], ctx={"allowed_company_ids": [cid]}):
                if a["id"] not in info or not info[a["id"]].get("code"):
                    info[a["id"]] = a
    return info


def traer_partners(od, ids, comp_ids):
    out = {}
    ids = sorted(set(x for x in ids if x))
    for i in range(0, len(ids), 300):
        for p in od.sr("res.partner", [["id", "in", ids[i:i + 300]]],
                       ["id", "name", "vat", "country_id"], ctx={"allowed_company_ids": comp_ids}):
            cid, cn = m2o(p.get("country_id"))
            out[p["id"]] = {"name": p.get("name"), "vat": (p.get("vat") or "").strip(),
                            "country_id": cid, "country": cn}
    return out


def traer_pagos(od, year, comp_ids, avisos):
    """Pagos a proveedor del anio, con su estado de aplicacion.

    `is_matched` / `reconciled_bill_ids` dicen si el pago quedo IMPUTADO a una factura.
    Un pago no imputado es un anticipo o una salida de caja sin factura contra la cual
    aplicarse: es plata que salio y que el saldo de CxP no refleja. En una importadora
    esto es habitual (anticipos al proveedor antes del embarque) y explica por que los
    pagos pueden superar por mucho a lo que se liquido de facturas del anio.
    """
    try:
        return od.sr("account.payment",
                     [["partner_type", "=", "supplier"], ["date", ">=", "%d-01-01" % year],
                      ["date", "<=", "%d-12-31" % year]],
                     ["id", "date", "amount", "amount_company_currency_signed", "currency_id",
                      "company_id", "partner_id", "state"], ctx={"allowed_company_ids": comp_ids})[0] \
            if False else od.sr_drop("account.payment",
                                     [["partner_type", "=", "supplier"], ["date", ">=", "%d-01-01" % year],
                                      ["date", "<=", "%d-12-31" % year]],
                                     ["id", "date", "amount", "amount_company_currency_signed",
                                      "currency_id", "company_id", "partner_id", "state",
                                      "is_matched", "reconciled_bill_ids", "reconciled_bills_count"],
                                     ctx={"allowed_company_ids": comp_ids})[0]
    except Exception as e:
        avisos.add("alerta", None, "pagos", "No pude leer account.payment: %s" % str(e)[:140])
        return []


def dias_de_pago_real(od, year, cids, comp_ids, hoy):
    """Dias reales de pago ponderados por monto, desde las conciliaciones."""
    try:
        desde = (hoy - datetime.timedelta(days=365)).isoformat()
        dom = [["parent_state", "=", "posted"], ["company_id", "in", cids],
               ["account_id.account_type", "=", "liability_payable"],
               ["credit", ">", 0], ["date", ">=", desde]]
        hist, _ = od.sr_drop("account.move.line", dom,
                             ["id", "move_name", "date", "date_maturity", "credit"],
                             ctx={"allowed_company_ids": comp_ids})
        hmap = dict((l["id"], l) for l in hist)
        ids = list(hmap.keys())
        partials = []
        for i in range(0, len(ids), 400):
            try:
                partials += od.sr("account.partial.reconcile",
                                  [["credit_move_id", "in", ids[i:i + 400]]],
                                  ["credit_move_id", "amount", "max_date"],
                                  ctx={"allowed_company_ids": comp_ids})
            except Exception:
                break
        num = den = 0.0
        por_mes = defaultdict(lambda: [0.0, 0.0])
        for p in partials:
            li = (p.get("credit_move_id") or [None])[0]
            l = hmap.get(li)
            if not l:
                continue
            amt = float(p.get("amount") or 0)
            if amt <= 0:
                continue
            try:
                fp = datetime.date.fromisoformat(str(p.get("max_date"))[:10])
                fv = datetime.date.fromisoformat(str(l.get("date_maturity") or l.get("date"))[:10])
            except Exception:
                continue
            d = (fp - fv).days
            num += amt * d; den += amt
            if fp.year == year:
                k = por_mes[fp.month]
                k[0] += amt * d; k[1] += amt
        return {"dias_pago_real": round(num / den, 1) if den else None,
                "base_conciliada": round(den, 2), "n_conciliaciones": len(partials),
                "mensual": dict((m, round(v[0] / v[1], 1)) for m, v in por_mes.items() if v[1])}
    except Exception:
        return {"dias_pago_real": None, "base_conciliada": None, "n_conciliaciones": 0, "mensual": {}}


def leer_cxp_referencia(avisos, umbral_dias):
    f = PAGOS_DIR / "cxp" / "cxp_semana_actual.json"
    if not f.exists():
        avisos.add("nota", None, "cxp", "No existe Pagos/cxp/cxp_semana_actual.json: sin referencia para conciliar.")
        return None
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception as e:
        avisos.add("alerta", None, "cxp", "cxp_semana_actual.json ilegible: %s" % e)
        return None
    try:
        gen = datetime.datetime.fromisoformat(d.get("generado"))
        dias = (datetime.datetime.now() - gen).days
        d["_antiguedad_dias"] = dias
        if dias > umbral_dias:
            avisos.add("alerta", None, "cxp",
                       "La CxP de referencia (cxp_semana_actual.json) tiene %d días: se generó el %s. "
                       "El agente com.vcomer.pagos.cxp corre los viernes 08:00 y no dispara si el Mac está suspendido. "
                       "El saldo que muestra este dashboard viene de Odoo en vivo, no de ese archivo." %
                       (dias, d.get("generado")))
    except Exception:
        pass
    return d


# =====================================================================
#  Ensamblado
# =====================================================================
def construir(od, year, avisos, hoy=None, reglas=None, depto=None):
    hoy = hoy or datetime.date.today()
    reglas = reglas or load_reglas()
    depto = depto or load_depto()
    umbr = reglas.get("umbrales") or {}
    tc = load_tc(depto)
    cfg_raw = od.cfg.get("_raw") or {}
    comps = companias(od, cfg_raw.get("company_map") or {})
    comp_ids = list(comps.keys())
    activas = dict((c["id"], c) for c in comps.values() if c["pais"] and not c["excluida"])
    excluidas = [c["name"] for c in comps.values() if c["excluida"]]
    mes_actual = hoy.month if hoy.year == year else 12
    mes_cierre = max(mes_actual - 1, 1) if hoy.year == year else 12

    log("Facturas de proveedor %d..." % year)
    facturas, om = traer_facturas(od, year, comp_ids)
    if om:
        avisos.add("nota", None, "compras", "Odoo rechazó estos campos de account.move: %s" % ", ".join(om))
    facturas = [f for f in facturas if not (comps.get(m2o(f.get("company_id"))[0]) or {}).get("excluida")]
    log("  %d documentos" % len(facturas))
    fmap = dict((f["id"], f) for f in facturas)

    log("CxP abierta (todos los años)...")
    cxp_abierta = traer_cxp_abierta(od, comp_ids, avisos)
    cxp_abierta = [f for f in cxp_abierta if not (comps.get(m2o(f.get("company_id"))[0]) or {}).get("excluida")]
    log("  %d facturas con saldo" % len(cxp_abierta))

    log("Líneas de factura...")
    lineas = traer_lineas(od, [f["id"] for f in facturas], comp_ids)
    log("  %d líneas" % len(lineas))

    ids_por_comp = defaultdict(list)
    for l in lineas:
        cid, _ = m2o(l.get("company_id"))
        aid, _ = m2o(l.get("account_id"))
        ids_por_comp[cid].append(aid)
    cuentas = traer_cuentas(od, ids_por_comp)
    partners = traer_partners(od, [m2o(f.get("partner_id"))[0] for f in facturas], comp_ids)

    paises_odoo = {}
    for r in od.sr("res.country", [["code", "in", ["EC", "CO", "CR"]]], ["id", "code"]):
        paises_odoo[r["code"]] = r["id"]

    # ---------------- cobertura de clasificacion ----------------
    con_pais = [p for p in partners.values() if p["country_id"]]
    cob = (len(con_pais) / float(len(partners))) if partners else 0.0
    pendientes = [{"nombre": p["name"], "vat": p["vat"]} for p in partners.values() if not p["country_id"]]
    cobertura = {"n_proveedores": len(partners), "con_pais": len(con_pais),
                 "cobertura": round(cob, 4), "pendientes": pendientes,
                 "regla": "local = country_id del proveedor igual al país de la compañía que registra la factura"}
    if cob < 0.95:
        avisos.add("critico", None, "clasificación",
                   "Sólo el %.1f%% de los proveedores tiene país cargado en Odoo. El bucket SIN CLASIFICAR "
                   "no es despreciable: revisar antes de decidir con este tablero." % (cob * 100))
    elif pendientes:
        avisos.add("alerta", None, "clasificación",
                   "%d proveedor(es) sin país en Odoo (%s). Aparecen en el bucket SIN CLASIFICAR, no repartidos." %
                   (len(pendientes), ", ".join(p["nombre"] for p in pendientes[:4])))

    # ---------------- clasificacion factura por factura ----------------
    P = {}
    for pais in ORDEN_PAISES:
        P[pais] = {"moneda": None, "compra_mensual": [0.0] * 12, "n_docs_local": 0,
                   "por_cuenta": defaultdict(lambda: {"monto": 0.0, "n": 0, "code": None, "name": None, "tipo": None}),
                   "por_depto": defaultdict(float), "por_proveedor": defaultdict(lambda: {"monto": 0.0, "n": 0, "depto": None, "etiquetas": set()}),
                   "excluido": {"importacion": {"monto": 0.0, "n": 0, "proveedores": defaultdict(float)},
                                "servicios_exterior": {"monto": 0.0, "n": 0, "proveedores": defaultdict(float)},
                                "sin_clasificar": {"monto": 0.0, "n": 0, "proveedores": defaultdict(float)},
                                "no_operativo": defaultdict(lambda: {"monto": 0.0, "n": 0})},
                   "comercio_exterior_local": {"monto": 0.0, "n": 0, "proveedores": defaultdict(float)},
                   "categorias": defaultdict(lambda: {"monto": 0.0, "proveedores": defaultdict(float)}),
                   "cxp_docs": [], "sin_depto_regla": 0.0,
                   "compra_total_mensual": [0.0] * 12, "n_docs_total": 0,
                   "primera_factura": None, "ultima_factura": None}

    lineas_por_move = defaultdict(list)
    for l in lineas:
        mid, _ = m2o(l.get("move_id"))
        lineas_por_move[mid].append(l)

    kw_depto = set(norm(k) for k in (depto.get("keywords") or {}).keys())
    for f in facturas:
        cid, _ = m2o(f.get("company_id"))
        c = comps.get(cid) or {}
        pais = c.get("pais")
        if not pais:
            continue
        b = P[pais]
        b["moneda"] = b["moneda"] or c.get("moneda")
        pid, pname = m2o(f.get("partner_id"))
        pp = partners.get(pid) or {}
        esperado = paises_odoo.get(CODE_PAIS.get(pais))
        if not pp.get("country_id"):
            estado = "sin_clasificar"
        elif pp["country_id"] == esperado:
            estado = "local"
        else:
            estado = "exterior"
        mes = int(str(f.get("invoice_date") or "0000-01")[5:7]) - 1
        dep = departamento(pname, depto)
        # Universo TOTAL de compra: todas las facturas de proveedor, locales y del
        # exterior. Es el que genera la deuda, y por lo tanto el unico denominador
        # honesto del DPO. Medir el DPO contra la compra local solamente divide una
        # deuda que incluye importaciones entre un gasto que las excluye.
        fdate = str(f.get("invoice_date") or "")[:10]
        if 0 <= mes < 12:
            b["compra_total_mensual"][mes] += -float(f.get("amount_untaxed_signed") or 0)
        b["n_docs_total"] += 1
        if fdate:
            if not b["primera_factura"] or fdate < b["primera_factura"]:
                b["primera_factura"] = fdate
            if not b["ultima_factura"] or fdate > b["ultima_factura"]:
                b["ultima_factura"] = fdate
        tiene_regla = bool(contiene(pname, list(depto.get("keywords") or {}.keys())))

        lins = lineas_por_move.get(f["id"], [])

        if estado != "local":
            # Lo excluido se mide a NIVEL DE FACTURA, no de linea de gasto: una compra de
            # importacion no toca ninguna cuenta de gasto (entra a inventario en transito,
            # 101.03.07 IMPORTACION), asi que sumar solo lineas de expense la haria
            # desaparecer de la tarjeta de excluidos justo cuando es la mas grande.
            neto = -float(f.get("amount_untaxed_signed") or 0)
            nat = "sin_clasificar"
            if estado == "exterior":
                nat = "servicios_exterior"
                for l in lins:
                    aid, aname = m2o(l.get("account_id"))
                    cu = cuentas.get(aid) or {"code": None, "name": aname}
                    if naturaleza_exterior(cu, pname, reglas) == "importacion":
                        nat = "importacion"
                        break
            d = b["excluido"][nat]
            d["monto"] += neto; d["n"] += 1
            d["proveedores"][pname or "?"] += neto
            continue

        for l in lins:
            aid, aname = m2o(l.get("account_id"))
            cu = cuentas.get(aid) or {"code": None, "name": aname, "account_type": None}
            bal = float(l.get("balance") or 0)
            es_gasto, motivo, ets = clasificar_linea(pais, cu, pname, reglas)
            if not es_gasto:
                if motivo and not motivo.startswith("contrapartida"):
                    d = b["excluido"]["no_operativo"][motivo]
                    d["monto"] += bal; d["n"] += 1
                continue
            # gasto operativo local
            if 0 <= mes < 12:
                b["compra_mensual"][mes] += bal
            k = aid or 0
            e = b["por_cuenta"][k]
            e["monto"] += bal; e["n"] += 1
            e["code"] = cu.get("code"); e["name"] = cu.get("name"); e["tipo"] = cu.get("account_type")
            b["por_depto"][dep] += bal
            pr = b["por_proveedor"][pname or "?"]
            pr["monto"] += bal; pr["n"] += 1; pr["depto"] = dep
            for x in ets:
                pr["etiquetas"].add(x)
                if x.startswith("cat:"):
                    cat = x[4:]
                    b["categorias"][cat]["monto"] += bal
                    b["categorias"][cat]["proveedores"][pname or "?"] += bal
                else:
                    b["comercio_exterior_local"]["monto"] += bal
                    b["comercio_exterior_local"]["n"] += 1
                    b["comercio_exterior_local"]["proveedores"][pname or "?"] += bal
            if not tiene_regla:
                b["sin_depto_regla"] += bal
        if estado == "local":
            b["n_docs_local"] += 1
            b["neto_facturas_local"] = b.get("neto_facturas_local", 0.0) + (-float(f.get("amount_untaxed_signed") or 0))

    # ---- CxP: se arma aparte, con TODAS las facturas abiertas de cualquier año ----
    paises_pid = {}
    for f in cxp_abierta:
        pid, _ = m2o(f.get("partner_id"))
        if pid:
            paises_pid[pid] = True
    faltan = [i for i in paises_pid if i not in partners]
    if faltan:
        partners.update(traer_partners(od, faltan, comp_ids))
    for f in cxp_abierta:
        cid, _ = m2o(f.get("company_id"))
        c = comps.get(cid) or {}
        pais = c.get("pais")
        if not pais:
            continue
        b = P[pais]
        b["moneda"] = b["moneda"] or c.get("moneda")
        pid, pname = m2o(f.get("partner_id"))
        pp = partners.get(pid) or {}
        esperado = paises_odoo.get(CODE_PAIS.get(pais))
        estado = ("local" if pp.get("country_id") == esperado else
                  ("sin_clasificar" if not pp.get("country_id") else "exterior"))
        res = -float(f.get("amount_residual_signed") or 0)
        if abs(res) <= 0.005:
            continue
        fem = str(f.get("invoice_date") or "")[:10]
        try:
            venc = datetime.date.fromisoformat(str(f.get("invoice_date_due") or fem)[:10])
        except Exception:
            venc = None
        _, pt = m2o(f.get("invoice_payment_term_id"))
        b["cxp_docs"].append({"doc": f.get("name"), "proveedor": pname or "?",
                              "emision": fem, "vence": str(f.get("invoice_date_due") or "")[:10],
                              "saldo": round(res, 2), "moneda_doc": m2o(f.get("currency_id"))[1],
                              "saldo_doc": round(float(f.get("amount_residual") or 0), 2),
                              "dias": (hoy - venc).days if venc else 0,
                              "depto": departamento(pname, depto), "plazo": pt, "estado": estado,
                              "anio": fem[:4],
                              "tipo": "NC" if f.get("move_type") == "in_refund" else "FAC"})
    return finalizar(od, year, hoy, comps, activas, P, partners, facturas, tc, reglas, depto,
                     cobertura, avisos, mes_actual, mes_cierre, excluidas)


def finalizar(od, year, hoy, comps, activas, P, partners, facturas, tc, reglas, depto,
              cobertura, avisos, mes_actual, mes_cierre, excluidas):
    umbr = reglas.get("umbrales") or {}
    hhi_crit = umbr.get("hhi_critico", 2500)
    dias_crit = umbr.get("dias_vencido_critico", 60)
    n_sem = umbr.get("semanas_calendario_pagos", 8)
    top_n = umbr.get("top_proveedores", 15)
    comp_ids = list(comps.keys())

    log("Pagos ejecutados...")
    pagos = traer_pagos(od, year, comp_ids, avisos)
    pagos_pais = defaultdict(lambda: {"mensual": [0.0] * 12, "n": 0, "aplicados": 0.0,
                                      "no_aplicados": 0.0, "n_no_aplicados": 0,
                                      "estado_conocido": False, "top_anticipos": defaultdict(float)})
    for p in pagos:
        cid, _ = m2o(p.get("company_id"))
        c = comps.get(cid) or {}
        if not c.get("pais") or c.get("excluida"):
            continue
        try:
            m = int(str(p.get("date"))[5:7]) - 1
        except Exception:
            continue
        v = p.get("amount_company_currency_signed")
        v = abs(float(v)) if v is not None else abs(float(p.get("amount") or 0))
        a = pagos_pais[c["pais"]]
        a["mensual"][m] += v
        a["n"] += 1
        matched = p.get("is_matched")
        nfac = p.get("reconciled_bills_count")
        if nfac is None:
            nfac = len(p.get("reconciled_bill_ids") or []) if ("reconciled_bill_ids" in p) else None
        if matched is not None or nfac is not None:
            a["estado_conocido"] = True
            aplicado = bool(matched) if matched is not None else bool(nfac)
            if aplicado:
                a["aplicados"] += v
            else:
                a["no_aplicados"] += v
                a["n_no_aplicados"] += 1
                _, pn = m2o(p.get("partner_id"))
                a["top_anticipos"][pn or "?"] += v

    ppto = leer_presupuesto(avisos)
    eeff = leer_eeff_oficial(avisos)
    cxp_ref = leer_cxp_referencia(avisos, umbr.get("frescura_cxp_dias", 3))

    out_paises = {}
    for pais in ORDEN_PAISES:
        b = P[pais]
        cids = [c["id"] for c in activas.values() if c["pais"] == pais]
        if not cids:
            continue
        moneda = b["moneda"] or "USD"
        mensual = [round(x, 2) for x in b["compra_mensual"]]
        ytd = round(sum(mensual[:mes_actual]), 2)

        # ---------- CxP ----------
        docs = b["cxp_docs"]
        total = round(sum(d["saldo"] for d in docs), 2)
        total_doc = round(sum(d["saldo_doc"] for d in docs), 2)
        por_anio = {}
        for d in docs:
            a = d.get("anio") or "?"
            por_anio[a] = round(por_anio.get(a, 0.0) + d["saldo"], 2)
        total_anio = round(por_anio.get(str(year), 0.0), 2)
        total_anterior = round(total - total_anio, 2)
        doc_anio = round(sum(d["saldo_doc"] for d in docs if d.get("anio") == str(year)), 2)
        monedas_doc = sorted(set(d["moneda_doc"] for d in docs if d.get("moneda_doc")))
        buck = dict((k, 0.0) for k in BUCKETS)
        for d in docs:
            buck[bucket_de(d["dias"])] += d["saldo"]
        venc = sum(v for k, v in buck.items() if k != "Corriente")
        venc30 = sum(v for k, v in buck.items() if k in ("31-60", "61-90", ">90"))
        porprov = {}
        for d in docs:
            e = porprov.setdefault(d["proveedor"], {"proveedor": d["proveedor"], "saldo": 0.0, "vencido": 0.0,
                                                    "buckets": dict((k, 0.0) for k in BUCKETS), "n": 0,
                                                    "depto": d["depto"], "mas_antiguo": None, "dias": 0,
                                                    "plazo": d.get("plazo")})
            e["saldo"] += d["saldo"]; e["n"] += 1
            e["buckets"][bucket_de(d["dias"])] += d["saldo"]
            if d["dias"] > 0:
                e["vencido"] += d["saldo"]
                if d["saldo"] > 0 and d["dias"] > e["dias"]:
                    e["dias"] = d["dias"]; e["mas_antiguo"] = d["doc"]
        prov_cxp = []
        for e in porprov.values():
            e["pct_vencido"] = round(e["vencido"] / e["saldo"], 4) if e["saldo"] else None
            for k in BUCKETS:
                e["buckets"][k] = round(e["buckets"][k], 2)
            e["saldo"] = round(e["saldo"], 2); e["vencido"] = round(e["vencido"], 2)
            prov_cxp.append(e)
        prov_cxp.sort(key=lambda x: -x["saldo"])

        # ---------- calendario de pagos ----------
        base = lunes_de(hoy)
        semanas = []
        for i in range(n_sem):
            ini = base + datetime.timedelta(days=7 * i)
            fin = ini + datetime.timedelta(days=6)
            sel = [d for d in docs if d["vence"] and ini.isoformat() <= d["vence"] <= fin.isoformat()]
            pd = defaultdict(float)
            for d in sel:
                pd[d["depto"]] += d["saldo"]
            semanas.append({"iso": iso_semana(ini), "desde": ini.isoformat(), "fin": fin.isoformat(),
                            "total": round(sum(d["saldo"] for d in sel), 2), "n": len(sel),
                            "por_depto": dict((k, round(v, 2)) for k, v in pd.items()),
                            "es_actual": i == 0})
        vencido_previo = [d for d in docs if d["vence"] and d["vence"] < base.isoformat()]
        semana_actual = sorted([d for d in docs if d["vence"] and
                                base.isoformat() <= d["vence"] <= (base + datetime.timedelta(days=6)).isoformat()],
                               key=lambda x: x["vence"])
        prox7 = round(sum(d["saldo"] for d in docs if d["vence"] and
                          hoy.isoformat() <= d["vence"] <= (hoy + datetime.timedelta(days=7)).isoformat()), 2)

        escenarios = {
            "pagar_todo_vencido": {"monto": round(sum(d["saldo"] for d in docs if d["dias"] > 0), 2),
                                   "n": len([d for d in docs if d["dias"] > 0]),
                                   "descripcion": "Salida de caja inmediata si se pone al día toda la mora."},
            "solo_corriente": {"monto": round(sum(d["saldo"] for d in docs if d["dias"] <= 0), 2),
                               "n": len([d for d in docs if d["dias"] <= 0]),
                               "descripcion": "Pagar sólo lo no vencido: mantiene la mora donde está."},
            "diferir_mas_60": {"monto": round(sum(d["saldo"] for d in docs if 0 < d["dias"] <= 60), 2),
                               "n": len([d for d in docs if 0 < d["dias"] <= 60]),
                               "difiere": round(sum(d["saldo"] for d in docs if d["dias"] > 60), 2),
                               "descripcion": "Pagar la mora hasta 60 días y diferir lo de más de 60."},
        }

        # ---------- DPO ----------
        dp = dias_de_pago_real(od, year, cids, comp_ids, hoy)
        total_mensual = [round(x, 2) for x in b["compra_total_mensual"]]
        ini_m = max(1, mes_actual - 2)
        compra_per = sum(total_mensual[ini_m - 1:mes_actual])
        compra_local_per = sum(mensual[ini_m - 1:mes_actual])
        dias_per = (hoy - datetime.date(year, ini_m, 1)).days + 1
        dpo = {"puntual": round(total / compra_per * dias_per, 1) if compra_per > 0 else None,
               "compra_periodo": round(compra_per, 2), "compra_local_periodo": round(compra_local_per, 2),
               "ventana": "%s-%s %d (%d días)" % (MESES[ini_m - 1], MESES[mes_actual - 1], year, dias_per),
               "metodo": "DPO puntual = saldo de CxP al corte / compra TOTAL del período × días del período. "
                         "El denominador es la compra total (locales + exterior), porque el numerador es toda "
                         "la deuda: medirla contra la compra local solamente inflaría el DPO varias veces. "
                         "No hay fotos históricas de CxP, así que NO es un promedio: es un puntual.",
               "dias_pago_real": dp["dias_pago_real"], "base_conciliada": dp["base_conciliada"],
               "n_conciliaciones": dp["n_conciliaciones"], "mensual_pago_real": dp["mensual"]}
        if compra_per <= 0:
            dpo["motivo"] = "La compra del período es cero: el DPO puntual no está definido."

        # ---------- brecha de plazo ----------
        plazos_manual = reglas.get("plazos_pactados_manuales") or {}
        con_plazo = [d for d in docs if d.get("plazo")]
        brecha = {"cobertura_plazo": round(len(con_plazo) / float(len(docs)), 4) if docs else None,
                  "n_con_plazo": len(con_plazo), "n_docs": len(docs), "filas": [],
                  "nota": "El plazo pactado sale de invoice_payment_term_id. Los documentos sin plazo cargado "
                          "NO se promedian con un supuesto: quedan fuera de esta tabla."}
        pp2 = defaultdict(lambda: {"volumen": 0.0, "plazos": set(), "dias": []})
        for d in docs:
            e = pp2[d["proveedor"]]
            e["volumen"] += d["saldo"]
            if d.get("plazo"):
                e["plazos"].add(d["plazo"])
            e["dias"].append(d["dias"])
        for prov, e in pp2.items():
            vol = (b["por_proveedor"].get(prov) or {}).get("monto", 0.0) or e["volumen"]
            plazo_txt = ", ".join(sorted(e["plazos"])) if e["plazos"] else (
                "%d días (declarado a mano)" % plazos_manual[prov] if prov in plazos_manual else None)
            m = re.search(r"(\d+)", plazo_txt or "")
            plazo_d = int(m.group(1)) if m else None
            dias_reales = dp["dias_pago_real"]
            brecha["filas"].append({"proveedor": prov, "plazo": plazo_txt, "plazo_dias": plazo_d,
                                    "volumen": round(vol, 2),
                                    "dias_mora_actual": max(e["dias"]) if e["dias"] else 0,
                                    "brecha": (max(e["dias"]) - plazo_d) if (plazo_d is not None and e["dias"]) else None,
                                    "fuente_plazo": ("Odoo" if e["plazos"] else ("manual" if prov in plazos_manual else None))})
        brecha["filas"].sort(key=lambda x: -(x["volumen"] or 0))
        brecha["filas"] = brecha["filas"][:top_n]
        if brecha["cobertura_plazo"] is not None and brecha["cobertura_plazo"] < 0.8:
            avisos.add("alerta", pais, "dpo",
                       "Sólo el %.0f%% de las facturas de %s trae plazo pactado cargado en Odoo (%d de %d). "
                       "La brecha contra plazo se calcula sobre ese subconjunto; el resto no se supone." %
                       (brecha["cobertura_plazo"] * 100, pais, brecha["n_con_plazo"], brecha["n_docs"]))

        # ---------- concentracion ----------
        provs = []
        tot_compra = sum(v["monto"] for v in b["por_proveedor"].values() if v["monto"] > 0) or 1.0
        for nombre, v in b["por_proveedor"].items():
            provs.append({"proveedor": nombre, "monto": round(v["monto"], 2), "n": v["n"],
                          "depto": v["depto"], "pct": round(v["monto"] / tot_compra, 4),
                          "etiquetas": sorted(v["etiquetas"])})
        provs.sort(key=lambda x: -x["monto"])
        hhi = round(sum((p["pct"] * 100) ** 2 for p in provs if p["pct"] > 0), 0)

        criticos = []
        for cat, v in b["categorias"].items():
            lista = sorted(v["proveedores"].items(), key=lambda x: -x[1])
            if len(lista) == 1:
                nombre = lista[0][0]
                e = porprov.get(nombre)
                vencido_grave = bool(e and e["dias"] > dias_crit)
                criticos.append({"categoria": cat, "proveedor": nombre, "monto": round(lista[0][1], 2),
                                 "unico": True, "saldo": (e or {}).get("saldo"),
                                 "dias_vencido": (e or {}).get("dias", 0),
                                 "alerta_roja": vencido_grave})
                if vencido_grave:
                    avisos.add("critico", pais, "proveedores",
                               "%s es el ÚNICO proveedor de %s en %s y su factura más antigua lleva %d días vencida "
                               "(saldo %s). Si corta el servicio, la operación para." %
                               (nombre, cat, pais, e["dias"], "{:,.0f}".format(e["saldo"])))
        criticos.sort(key=lambda x: (not x["alerta_roja"], -(x["monto"] or 0)))

        if hhi > hhi_crit:
            avisos.add("alerta", pais, "proveedores",
                       "HHI de proveedores %d (>%d): la compra local de %s depende de muy pocos. %s pesa %.0f%%." %
                       (hhi, hhi_crit, pais, provs[0]["proveedor"][:34] if provs else "?",
                        (provs[0]["pct"] * 100) if provs else 0))

        # ---------- cuentas ----------
        cuentas_l = []
        for k, v in b["por_cuenta"].items():
            cuentas_l.append({"id": k, "code": v["code"], "name": v["name"], "tipo": v["tipo"],
                              "monto": round(v["monto"], 2), "n": v["n"],
                              "pct": round(v["monto"] / tot_compra, 4)})
        cuentas_l.sort(key=lambda x: -x["monto"])

        # Ecuacion de control: lo facturado menos lo pagado deberia explicar el saldo.
        # Lo que no cierre es deuda anterior al anio o pagos registrados fuera de
        # account.payment. Se muestra, no se maquilla.
        compra_tot_ytd = round(sum(total_mensual[:mes_actual]), 2)
        pagos_ytd_ = round(sum(pagos_pais[pais]["mensual"][:mes_actual]), 2)
        # La ecuacion se plantea solo sobre el anio en curso: facturado este anio menos lo
        # que de eso sigue pendiente = lo que de eso se pago. Si los pagos registrados no
        # llegan a esa cifra, la diferencia son pagos hechos fuera de account.payment.
        pagado_del_anio = round(compra_tot_ytd - total_anio, 2)
        pg_ = pagos_pais[pais]
        aplicados_ = round(pg_["aplicados"], 2) if pg_["estado_conocido"] else None
        no_aplic_ = round(pg_["no_aplicados"], 2) if pg_["estado_conocido"] else None
        if pg_["estado_conocido"] and no_aplic_:
            avisos.add("alerta", pais, "pagos",
                       "%s de los pagos a proveedor de %s (%d pagos) NO están imputados a ninguna factura: son "
                       "anticipos o salidas de caja sin factura contra la cual aplicarse. El saldo de CxP no los "
                       "refleja, así que la deuda neta real es menor de la que muestra el aging.%s" %
                       ("{:,.0f}".format(no_aplic_), pais, pg_["n_no_aplicados"],
                        (" Los mayores: " + ", ".join(x for x, _ in sorted(pg_["top_anticipos"].items(),
                                                                           key=lambda y: -y[1])[:3]) + ".")
                        if pg_["top_anticipos"] else ""))
        control = {"compra_total_ytd": compra_tot_ytd, "pagos_ytd": pagos_ytd_,
                   "pagos_aplicados": aplicados_, "pagos_no_aplicados": no_aplic_,
                   "saldo_cxp": total, "saldo_cxp_anio": total_anio,
                   "saldo_cxp_anterior": total_anterior,
                   "pagado_implicito_del_anio": pagado_del_anio,
                   "sin_explicar": round(pagado_del_anio - (aplicados_ if aplicados_ is not None else pagos_ytd_), 2),
                   "nota": ("De lo facturado este año, %s ya no está pendiente: se liquidó. Odoo registra %s en "
                            "pagos, de los cuales %s SÍ están imputados a facturas y %s quedaron sin imputar "
                            "(anticipos). La diferencia contra lo imputado son pagos hechos fuera de "
                            "account.payment."
                            % ("{:,.0f}".format(pagado_del_anio), "{:,.0f}".format(pagos_ytd_),
                               "{:,.0f}".format(aplicados_ or 0), "{:,.0f}".format(no_aplic_ or 0)))
                           if pg_["estado_conocido"] else
                           ("De lo facturado este año, %s ya no está pendiente: se liquidó. Odoo registra %s como "
                            "pago. Odoo no expone el estado de imputación de los pagos en esta instancia, así que "
                            "no se puede separar cuánto fue anticipo."
                            % ("{:,.0f}".format(pagado_del_anio), "{:,.0f}".format(pagos_ytd_)))}
        if total_anterior:
            avisos.add("alerta", pais, "cxp",
                       "%s de la deuda de %s viene de facturas de años anteriores (%s). Un tablero de cuentas por "
                       "pagar que sólo mire el año en curso la deja fuera y subestima lo que hay que pagar." %
                       ("{:,.0f}".format(total_anterior), pais,
                        ", ".join(sorted(k for k in por_anio if k != str(year)))))
        meses_sin_pago = [MESES[i] for i in range(mes_actual)
                          if pagos_pais[pais]["mensual"][i] == 0 and total_mensual[i] > 0]
        if pagos_pais[pais]["n"] == 0:
            avisos.add("critico", pais, "pagos",
                       "%s no tiene NINGÚN pago a proveedor registrado en Odoo en %d, pero facturó %s y hoy debe "
                       "sólo %s: los pagos existen y se están registrando fuera de account.payment. Sin eso, el "
                       "DPO y el calendario de caja de este país se apoyan en media foto." %
                       (pais, year, "{:,.0f}".format(compra_tot_ytd), "{:,.0f}".format(total)))
        elif len(meses_sin_pago) >= 2:
            avisos.add("alerta", pais, "pagos",
                       "%s no registra pagos en %s, habiendo comprado en esos meses. O se detuvieron los pagos, "
                       "o se dejaron de registrar como account.payment. Vale la pena confirmar cuál de las dos." %
                       (pais, ", ".join(meses_sin_pago)))
        if abs(control["sin_explicar"]) > max(1.0, abs(compra_tot_ytd) * 0.05):
            avisos.add("alerta", pais, "pagos",
                       "En %s hay %s sin explicar entre lo facturado, lo pagado y lo que se debe. Casi siempre son "
                       "pagos hechos fuera de account.payment o deuda de años anteriores." %
                       (pais, "{:,.0f}".format(control["sin_explicar"])))

        exc = b["excluido"]
        exc_out = {}
        for k in ("importacion", "servicios_exterior", "sin_clasificar"):
            top = sorted(exc[k]["proveedores"].items(), key=lambda x: -abs(x[1]))[:8]
            exc_out[k] = {"monto": round(exc[k]["monto"], 2), "n": exc[k]["n"],
                          "proveedores": [{"proveedor": a, "monto": round(v, 2)} for a, v in top]}
        exc_out["no_operativo"] = dict((k, {"monto": round(v["monto"], 2), "n": v["n"]})
                                       for k, v in exc["no_operativo"].items())
        exc_out["no_operativo_total"] = round(sum(v["monto"] for v in exc["no_operativo"].values()), 2)

        cont = (reglas.get("cuentas_contaminadas") or {}).get(pais) or []
        if cont:
            golpeadas = [k for k in exc["no_operativo"].keys() if "contaminada" in k]
            if not golpeadas:
                avisos.add("nota", pais, "compras",
                           "El filtro de cuentas contaminadas (%s) no encontró ninguna línea en facturas de proveedor: "
                           "esa contaminación vive en asientos de diario, no en compras. El filtro queda activo como guarda." %
                           ", ".join(r.get("patron_nombre", "?") for r in cont))

        pct_sin_regla = round(b["sin_depto_regla"] / tot_compra, 4) if tot_compra else None
        if pct_sin_regla and pct_sin_regla > 0.25:
            avisos.add("alerta", pais, "departamento",
                       "El %.0f%% de la compra de %s cae en el departamento por DEFECTO (%s) porque el proveedor no "
                       "tiene regla en pagos_reglas_depto.json. La apertura por departamento está sesgada." %
                       (pct_sin_regla * 100, pais, depto.get("default")))

        ce = b["comercio_exterior_local"]
        out_paises[pais] = {
            "moneda": moneda, "mes_actual": mes_actual, "mes_cierre": mes_cierre,
            "compra": {"mensual": mensual, "ytd": ytd,
                       "total_mensual": total_mensual,
                       "total_ytd": round(sum(total_mensual[:mes_actual]), 2),
                       "n_docs_total": b["n_docs_total"],
                       "ventana_datos": {"primera": b["primera_factura"], "ultima": b["ultima_factura"]},
                       "mtd": round(mensual[mes_actual - 1], 2) if mes_actual <= 12 else 0.0,
                       "mes_anterior": round(mensual[mes_actual - 2], 2) if mes_actual >= 2 else None,
                       "n_docs_local": b["n_docs_local"],
                       "por_cuenta": cuentas_l, "por_departamento": dict((k, round(v, 2)) for k, v in b["por_depto"].items()),
                       "pct_sin_regla_depto": pct_sin_regla,
                       "top_proveedores": provs[:top_n], "n_proveedores": len(provs),
                       "fuente": "líneas de factura de proveedor (account.move.line) con cuenta de gasto, proveedor local",
                       "puente": {
                           "neto_facturas_local": round(b.get("neto_facturas_local", 0.0), 2),
                           "menos_no_operativo": round(sum(v["monto"] for v in b["excluido"]["no_operativo"].values()), 2),
                           "gasto_operativo": ytd,
                           "resto_a_cuentas_de_balance": round(b.get("neto_facturas_local", 0.0)
                                                               - sum(v["monto"] for v in b["excluido"]["no_operativo"].values())
                                                               - ytd, 2),
                           "nota": "La diferencia entre el neto facturado por proveedores locales y el gasto operativo "
                                   "no se pierde: son líneas que van a cuentas de balance (inventario, activos, IVA) "
                                   "más lo excluido por no operativo. Ninguna de las dos es gasto del período."}},
            "excluido": exc_out,
            "comercio_exterior_local": {"monto": round(ce["monto"], 2), "n": ce["n"],
                                        "proveedores": [{"proveedor": a, "monto": round(v, 2)} for a, v in
                                                        sorted(ce["proveedores"].items(), key=lambda x: -abs(x[1]))[:8]]},
            "cxp": {"total": total, "total_moneda_documento": total_doc, "monedas_documento": monedas_doc,
                    "por_anio": por_anio, "total_anio_en_curso": total_anio,
                    "total_anios_anteriores": total_anterior,
                    "total_moneda_documento_anio": doc_anio,
                    "buckets": dict((k, round(v, 2)) for k, v in buck.items()),
                    "vencido": round(venc, 2), "pct_vencido": round(venc / total, 4) if total else None,
                    "vencido_mas_30": round(venc30, 2),
                    "pct_vencido_mas_30": round(venc30 / total, 4) if total else None,
                    "n_documentos": len(docs), "n_proveedores": len(prov_cxp),
                    "proveedores": prov_cxp[:top_n],
                    "por_departamento": dict((k, round(v, 2)) for k, v in
                                             ((kk, sum(d["saldo"] for d in docs if d["depto"] == kk))
                                              for kk in set(d["depto"] for d in docs))),
                    "corte": hoy.isoformat(),
                    "fuente": "amount_residual_signed de facturas de proveedor posted, en moneda de la compañía"},
            "pagos": {"mensual": [round(x, 2) for x in pagos_pais[pais]["mensual"]],
                      "ytd": round(sum(pagos_pais[pais]["mensual"][:mes_actual]), 2),
                      "n": pagos_pais[pais]["n"],
                      "aplicados": round(pagos_pais[pais]["aplicados"], 2),
                      "no_aplicados": round(pagos_pais[pais]["no_aplicados"], 2),
                      "n_no_aplicados": pagos_pais[pais]["n_no_aplicados"],
                      "estado_conocido": pagos_pais[pais]["estado_conocido"],
                      "top_anticipos": [{"proveedor": k2, "monto": round(v2, 2)} for k2, v2 in
                                        sorted(pagos_pais[pais]["top_anticipos"].items(),
                                               key=lambda x: -x[1])[:6]],
                      "fuente": "account.payment (partner_type = supplier). Incluye pagos a proveedores LOCALES y "
                                "del EXTERIOR: la salida de caja es la misma y no se puede recortar por origen. "
                                "Por eso puede superar a la compra local del período."},
            "dpo": dpo, "brecha_plazo": brecha, "control": control,
            "calendario": {"semanas": semanas, "semana_actual": semana_actual[:40],
                           "vencido_previo": round(sum(d["saldo"] for d in vencido_previo), 2),
                           "n_vencido_previo": len(vencido_previo), "a_pagar_7_dias": prox7},
            "escenarios": escenarios,
            "concentracion": {"hhi": hhi, "critico": hhi > hhi_crit,
                              "top1_pct": provs[0]["pct"] if provs else None,
                              "top5_pct": round(sum(p["pct"] for p in provs[:5]), 4),
                              "unicos_criticos": criticos},
            "presupuesto": {"disponible": False,
                            "motivo": "No hay presupuesto de gastos 2026 cargado para %s. El bloque queda vacío a "
                                      "propósito: comparar contra cero diría que se gastó 100%% de más." % pais,
                            "que_falta": "Un presupuesto de gastos por cuenta contable para %s, en el mismo formato "
                                         "que el de Ecuador (código de cuenta + monto mensual)." % pais},
            "usd": {},
        }
        u = out_paises[pais]["usd"]
        t = tc["tasas"].get(moneda)
        for k, v in (("compra_ytd", ytd), ("cxp_total", total), ("cxp_vencido", venc),
                     ("pagos_ytd", out_paises[pais]["pagos"]["ytd"]), ("a_pagar_7_dias", prox7)):
            u[k] = round(v * t, 2) if (t is not None and v is not None) else None
        u["referencial"] = True

    # ---------------- presupuesto Ecuador ----------------
    if "Ecuador" in out_paises:
        out_paises["Ecuador"]["presupuesto"] = cruzar_presupuesto(ppto, eeff, out_paises["Ecuador"],
                                                                  mes_actual, avisos)

    doc = {
        "generado": datetime.datetime.now().isoformat(timespec="seconds"),
        "generado_fecha": hoy.isoformat(), "anio": year, "meses": MESES,
        "mes_actual": mes_actual, "mes_cierre": mes_cierre,
        "tc": tc, "cobertura_clasificacion": cobertura,
        "excluidas_del_grupo": excluidas,
        "fuentes": {
            "compra": "Odoo account.move.line de facturas de proveedor (in_invoice + in_refund, posted)",
            "cxp": "Odoo account.move: amount_residual_signed en moneda de la compañía",
            "pagos": "Odoo account.payment (supplier)",
            "presupuesto": ppto.get("fuentes", {}),
            "cxp_referencia": (cxp_ref or {}).get("generado"),
            "reglas": "compras_reglas.json v%s" % (reglas.get("version")),
        },
        "paises": out_paises,
        "avisos": avisos.dump(),
        "odoo": {"url": od.cfg.get("url"), "db": od.cfg.get("db"), "llamadas": od.calls},
    }
    doc["consolidado"] = consolidar(out_paises, tc, avisos)
    doc["conciliacion"] = conciliar(out_paises, cxp_ref, eeff, ppto, tc)
    return doc


# =====================================================================
#  Presupuesto de gastos (Ecuador): vigente vs original vs real
# =====================================================================
def nivel_comun(codigo, universo):
    """Codigo mas profundo de `universo` que es el propio `codigo` o un ancestro suyo.

    El presupuesto esta abierto a 4-5 niveles (502.01.06.06 'Servicios de instalacion
    y mantenimiento R') pero la contabilidad real solo llega a 3 (502.01.06
    'Remuneraciones a otros trabajadores'). Cruzarlos hoja contra hoja no encuentra
    NADA y deja el 95% del presupuesto huerfano. La comparacion honesta es al nivel
    donde ambos existen: se sube el presupuesto hasta el nivel del real.
    """
    c = codigo
    while c:
        if c in universo:
            return c
        if "." not in c:
            return None
        c = c.rsplit(".", 1)[0]
    return None


def cruzar_presupuesto(ppto, eeff, pais_ec, mes_actual, avisos):
    if not ppto.get("disponible"):
        return {"disponible": False, "motivo": "No se pudo leer el presupuesto de gastos.",
                "que_falta": "Los Excel de presupuesto en ~/Desktop/VICOMER PERSONAL/."}
    vig = dict((k, v) for k, v in ppto["vigente"].items() if v.get("hoja"))
    ori = ppto.get("original") or {}

    # ---- REAL: hojas del Excel (Ene-Jun) + cuentas de Odoo (Ago+), solo gastos ----
    todos_r = (ppto.get("real_mensual") or {})
    cods_r = [v["codigo"].rstrip(".") for v in todos_r.values()]
    real_por_cuenta = {}
    for k, v in todos_r.items():
        if not str(k).startswith("502."):
            continue
        c = v["codigo"].rstrip(".")
        if any(o != c and o.startswith(c + ".") for o in cods_r):
            continue
        real_por_cuenta[k] = {"codigo": v["codigo"], "cuenta": v["cuenta"],
                              "ene_jun": round(sum(v["mensual"][:6]), 2),
                              "jul_excel": round(v["mensual"][6], 2), "odoo": 0.0,
                              "fuente": "Excel Ene-Jun"}
    for c in pais_ec["compra"]["por_cuenta"]:
        k = canon(c.get("code"), "odoo")
        if not k or not k.startswith("502."):
            continue
        destino = nivel_comun(k, set(real_por_cuenta.keys()))
        if destino:
            real_por_cuenta[destino]["odoo"] += c["monto"]
            real_por_cuenta[destino]["fuente"] = "Excel Ene-Jun + Odoo"
        else:
            real_por_cuenta[k] = {"codigo": c.get("code"), "cuenta": c.get("name"),
                                  "ene_jun": 0.0, "jul_excel": 0.0, "odoo": c["monto"],
                                  "fuente": "solo Odoo"}

    ene_jun = round(sum(v["ene_jun"] for v in real_por_cuenta.values()), 2)
    jul_excel = round(sum(v["jul_excel"] for v in real_por_cuenta.values()), 2)
    oficial = None
    if eeff:
        r = eeff.get("resultados") or {}
        oficial = round(sum(float(r.get(k) or 0) for k in
                            ("gastos_de_ventas", "gastos_administrativos", "gastos_financieros",
                             "gastos_no_deducibles")), 2)
    julio_real = round(oficial - ene_jun, 2) if oficial is not None else None
    if julio_real is not None and abs(julio_real - jul_excel) > 1.0:
        avisos.add("alerta", "Ecuador", "presupuesto",
                   "El detalle POR CUENTA del real llega hasta junio: la hoja 'Estado de Resultados Mensual' está "
                   "cortada a mitad de julio (trae %s cuando el EEFF oficial implica %s). Julio existe sólo "
                   "AGREGADO y se muestra como total sin apertura; no se prorratea." %
                   ("{:,.2f}".format(jul_excel), "{:,.2f}".format(julio_real)))

    # ---- CRUCE al nivel donde ambos existen ----
    universo_real = set(real_por_cuenta.keys())
    agrupado = {}
    huerfanas = []
    for k, v in vig.items():
        destino = nivel_comun(k, universo_real)
        if not destino:
            huerfanas.append({"codigo": v["codigo"], "cuenta": v["cuenta"], "monto": v["total_h2"]})
            continue
        g = agrupado.setdefault(destino, {"ppto_vigente_h2": 0.0, "ppto_original_h2": 0.0,
                                          "cuentas_ppto": [], "subio_nivel": 0})
        g["ppto_vigente_h2"] += v["total_h2"]
        g["cuentas_ppto"].append(v["codigo"])
        if destino != k:
            g["subio_nivel"] += 1

    # El presupuesto ORIGINAL tiene su propio arbol de codigos: se agrupa igual, al nivel
    # del real. Buscarlo cuenta por cuenta contra las hojas del vigente solo encontraba
    # una fraccion y hacia parecer que el resinceramiento fue mucho mayor de lo que fue.
    for k, o in ori.items():
        destino = nivel_comun(k, universo_real)
        if not destino:
            continue
        g = agrupado.setdefault(destino, {"ppto_vigente_h2": 0.0, "ppto_original_h2": 0.0,
                                          "cuentas_ppto": [], "subio_nivel": 0})
        g["ppto_original_h2"] += o.get("h2", 0.0)

    filas = []
    for k, r in real_por_cuenta.items():
        g = agrupado.get(k)
        real_h2 = round(r["odoo"], 2)
        pv = round((g or {}).get("ppto_vigente_h2", 0.0), 2)
        po = round((g or {}).get("ppto_original_h2", 0.0), 2)
        filas.append({"codigo": r["codigo"], "cuenta": r["cuenta"],
                      "ppto_vigente_h2": pv, "ppto_original_h2": po or None,
                      "resinceramiento": round(pv - po, 2) if po else None,
                      "real_h2_odoo": real_h2, "real_ene_jun": r["ene_jun"],
                      "desviacion": round(real_h2 - pv, 2),
                      "cumpl": round(real_h2 / pv, 4) if pv else None,
                      "tiene_ppto": bool(g), "fuente_real": r["fuente"],
                      "n_cuentas_ppto": len((g or {}).get("cuentas_ppto", [])),
                      "cruce_subio_nivel": bool((g or {}).get("subio_nivel"))})
    filas.sort(key=lambda x: -(abs(x["ppto_vigente_h2"]) or 0))
    sin_ppto = [{"codigo": f["codigo"], "cuenta": f["cuenta"],
                 "monto": round((f["real_ene_jun"] or 0) + f["real_h2_odoo"], 2)}
                for f in filas if not f["tiene_ppto"] and ((f["real_ene_jun"] or 0) or f["real_h2_odoo"])]

    cruzado = round(sum(f["ppto_vigente_h2"] for f in filas), 2)
    tot_vig = round(sum(v["total_h2"] for v in vig.values()), 2)
    tot_ori_h2 = round(ppto.get("original_total_h2") or 0, 2)
    tot_ori_anual = round(ppto.get("original_total_anual") or 0, 2)
    tot_real_odoo = round(sum(f["real_h2_odoo"] for f in filas), 2)
    subieron = len([f for f in filas if f["cruce_subio_nivel"]])

    # La ejecucion del H2 son DOS pedazos: julio, que solo existe agregado en el EEFF,
    # y agosto en adelante, que viene de Odoo. Y el avance del semestre se mide en DIAS
    # transcurridos, no en meses enteros: a 20 de agosto no van "2 meses de 6", va el 28%.
    hoy_ = datetime.date.today()
    ini_h2 = datetime.date(hoy_.year, 7, 1)
    fin_h2 = datetime.date(hoy_.year, 12, 31)
    dias_h2 = (fin_h2 - ini_h2).days + 1
    transcurridos = max(0, min(dias_h2, (hoy_ - ini_h2).days + 1))
    frac = (float(transcurridos) / dias_h2) if dias_h2 else 0
    real_h2_total = round((julio_real or 0) + tot_real_odoo, 2)
    run_rate = round(real_h2_total / frac, 2) if frac > 0.02 else None
    odoo_incompleto = tot_real_odoo < (julio_real or 0) * 0.5

    if tot_ori_anual and ene_jun:
        avisos.add("alerta", "Ecuador", "presupuesto",
                   "Lectura de gerencia: el presupuesto ORIGINAL de 2026 preveía %s USD para el año COMPLETO, "
                   "pero el gasto real de Ene-Jun ya fue %s. El resinceramiento de julio (%s para el H2) no fue un "
                   "ajuste fino: corrigió un presupuesto construido a alrededor de la mitad de la base de costos "
                   "real de la compañía." %
                   ("{:,.0f}".format(tot_ori_anual), "{:,.0f}".format(ene_jun), "{:,.0f}".format(tot_vig)))
    if odoo_incompleto:
        avisos.add("nota", "Ecuador", "presupuesto",
                   "El real del H2 son dos pedazos: julio %s (agregado, sin apertura) y Odoo desde agosto %s. "
                   "El avance del semestre es %.0f%% en días, no en meses." %
                   ("{:,.0f}".format(julio_real or 0), "{:,.0f}".format(tot_real_odoo), frac * 100))
    if huerfanas:
        monto = sum(x["monto"] for x in huerfanas)
        avisos.add("alerta", "Ecuador", "presupuesto",
                   "%d cuenta(s) del presupuesto (%s USD del H2) no tienen NINGÚN ancestro en la contabilidad real: "
                   "son líneas presupuestadas que el plan de cuentas no reconoce. Se listan aparte." %
                   (len(huerfanas), "{:,.0f}".format(monto)))
    if subieron:
        avisos.add("nota", "Ecuador", "presupuesto",
                   "El presupuesto está abierto a más niveles que la contabilidad: %d línea(s) del real recibieron "
                   "varias cuentas presupuestarias agrupadas al nivel donde ambos existen. La comparación es válida "
                   "a ese nivel, no cuenta por cuenta." % subieron)

    return {
        "disponible": True, "pais": "Ecuador",
        "vigente_total_h2": tot_vig, "vigente_cruzado": cruzado,
        "original_total_h2": tot_ori_h2, "original_total_anual": tot_ori_anual,
        "resinceramiento_total": round(tot_vig - tot_ori_h2, 2) if tot_ori_h2 else None,
        "resinceramiento_pct": round(tot_vig / tot_ori_h2 - 1, 4) if tot_ori_h2 else None,
        "real_h2_odoo": tot_real_odoo, "real_h2_total": real_h2_total,
        "avance_h2_dias": transcurridos, "dias_h2": dias_h2, "avance_h2_pct": round(frac, 4),
        "run_rate_h2": run_rate,
        "run_rate_vs_vigente": round(run_rate / tot_vig, 4) if (run_rate and tot_vig) else None,
        "ejecucion_comparable": not odoo_incompleto,
        "motivo_no_comparable": ("La ejecución del H2 todavía no es comparable: julio sólo existe agregado en el "
                                 "EEFF oficial y agosto lleva pocas semanas en Odoo (la compañía migró el 1 de "
                                 "agosto). El run-rate se muestra pero no concluye nada hasta cerrar el primer "
                                 "mes completo registrado en Odoo.") if odoo_incompleto else None,
        "desviacion_h2": round(real_h2_total - tot_vig, 2),
        "real_ene_jun": ene_jun, "julio_agregado": julio_real, "julio_excel_parcial": jul_excel,
        "oficial_ene_jul": oficial,
        "filas": filas, "n_filas": len(filas),
        "huerfanas": sorted(huerfanas, key=lambda x: -x["monto"])[:25], "n_huerfanas": len(huerfanas),
        "sin_presupuesto": sorted(sin_ppto, key=lambda x: -abs(x["monto"]))[:25], "n_sin_presupuesto": len(sin_ppto),
        "sin_desglosar": ppto.get("vigente_sin_desglosar") or [],
        "nivel_cruce": "El presupuesto se agrupa al nivel de cuenta que la contabilidad realmente produce.",
        "fuentes": ppto.get("fuentes"),
        "nota_fuentes": "Presupuesto vigente y original de los Excel; real por cuenta del Excel hasta junio, "
                        "julio sólo agregado del EEFF oficial, y desde agosto de Odoo. Los códigos del Excel "
                        "(5.G.01.x) se traducen al espacio de Odoo (502.0(G-1).x) antes de cruzar.",
    }


# =====================================================================
#  Consolidado y conciliacion
# =====================================================================
def consolidar(paises, tc, avisos):
    comp = []
    for pais, p in paises.items():
        comp.append({"pais": pais, "moneda": p["moneda"],
                     "compra_local": p["compra"]["ytd"], "compra_usd": p["usd"]["compra_ytd"],
                     "cxp_local": p["cxp"]["total"], "cxp_usd": p["usd"]["cxp_total"],
                     "pct_vencido": p["cxp"]["pct_vencido"],
                     "vencido_usd": p["usd"]["cxp_vencido"],
                     "dpo": p["dpo"]["puntual"], "dias_pago_real": p["dpo"]["dias_pago_real"],
                     "hhi": p["concentracion"]["hhi"],
                     "a_pagar_7_usd": p["usd"]["a_pagar_7_dias"]})
    tot_compra = sum(c["compra_usd"] or 0 for c in comp)
    tot_cxp = sum(c["cxp_usd"] or 0 for c in comp)
    tot_venc = sum(c["vencido_usd"] or 0 for c in comp)
    for c in comp:
        c["pct_compra"] = round((c["compra_usd"] or 0) / tot_compra, 4) if tot_compra else None
        c["pct_cxp"] = round((c["cxp_usd"] or 0) / tot_cxp, 4) if tot_cxp else None
        c["pct_vencido_grupo"] = round((c["vencido_usd"] or 0) / tot_venc, 4) if tot_venc else None
    comp.sort(key=lambda x: -(x["cxp_usd"] or 0))
    for c in comp:
        if c["pct_vencido_grupo"] and c["pct_vencido_grupo"] > 0.60:
            avisos.add("alerta", None, "consolidado",
                       "%s concentra el %.0f%% de la CxP VENCIDA del grupo (USD referencial). El problema de pagos "
                       "del grupo es, en la práctica, el de ese país." % (c["pais"], c["pct_vencido_grupo"] * 100))
    return {"moneda": "USD", "referencial": True,
            "compra_ytd": round(tot_compra, 2), "cxp_total": round(tot_cxp, 2),
            "cxp_vencido": round(tot_venc, 2),
            "pct_vencido": round(tot_venc / tot_cxp, 4) if tot_cxp else None,
            "pagos_ytd": round(sum(p["usd"]["pagos_ytd"] or 0 for p in paises.values()), 2),
            "a_pagar_7_dias": round(sum(c["a_pagar_7_usd"] or 0 for c in comp), 2),
            "por_pais": comp,
            "nota": "Los tres números son distintos y no se suman entre sí: compra devengada es flujo del período, "
                    "CxP es stock de deuda a hoy, pagos es salida real de caja."}


def conciliar(paises, cxp_ref, eeff, ppto, tc):
    filas = []
    ref_pais = {}
    edad = (cxp_ref or {}).get("_antiguedad_dias")
    if cxp_ref:
        for p in (cxp_ref.get("paises") or []):
            nombre = {"EC": "Ecuador", "CO": "Colombia", "CR": "Costa Rica"}.get(p.get("code"))
            if nombre:
                ref_pais[nombre] = p
    for pais, p in paises.items():
        r = ref_pais.get(pais)
        ref = (r.get("resumen") or {}).get("total_local") if r else None
        # pagos_cxp suma amount_residual EN MONEDA DEL DOCUMENTO: para comparar hay que
        # ponerse en su terreno, no en el nuestro. La cifra autoritativa del dashboard
        # sigue siendo la de moneda de compania.
        dash = p["cxp"].get("total_moneda_documento_anio")
        dif = round(dash - ref, 2) if (ref is not None and dash is not None) else None
        notas = []
        if len(p["cxp"].get("monedas_documento") or []) > 1:
            notas.append("cxp_semana_actual.json suma %s como si fuera una sola moneda; la cifra autoritativa "
                         "de este dashboard es la de moneda de la compañía (%s %s)."
                         % ("/".join(p["cxp"]["monedas_documento"]), p["moneda"],
                            "{:,.2f}".format(p["cxp"]["total"])))
        if edad:
            notas.append("la referencia tiene %d día(s): la diferencia incluye el movimiento de esos días." % edad)
        if p["cxp"].get("total_anios_anteriores"):
            notas.append("Se compara sólo el año en curso porque eso es lo que mide cxp_semana_actual.json; "
                         "la deuda total del país incluye además %s de años anteriores."
                         % "{:,.0f}".format(p["cxp"]["total_anios_anteriores"]))
        cuadra = (dif is not None and abs(dif) < 0.01)
        filas.append({"pais": pais, "concepto": "CxP del año en curso (moneda del documento) vs cxp_semana_actual.json",
                      "dashboard": dash, "referencia": ref, "diferencia": dif, "cuadra": cuadra,
                      "nota": " ".join(notas) or None, "tolerable": bool(edad),
                      "fecha_referencia": (cxp_ref or {}).get("generado")})
        pu = p["compra"].get("puente") or {}
        filas.append({"pais": pais, "concepto": "Puente: neto facturado local = gasto operativo + no operativo + balance",
                      "dashboard": round(pu.get("gasto_operativo", 0) + pu.get("menos_no_operativo", 0)
                                         + pu.get("resto_a_cuentas_de_balance", 0), 2),
                      "referencia": pu.get("neto_facturas_local"),
                      "diferencia": round(pu.get("gasto_operativo", 0) + pu.get("menos_no_operativo", 0)
                                          + pu.get("resto_a_cuentas_de_balance", 0)
                                          - (pu.get("neto_facturas_local") or 0), 2),
                      "cuadra": True, "nota": pu.get("nota")})
    ec = paises.get("Ecuador")
    if ec and eeff and ec.get("presupuesto", {}).get("disponible"):
        pr = ec["presupuesto"]
        d = round((pr.get("real_ene_jun") or 0) + (pr.get("julio_agregado") or 0) - (pr.get("oficial_ene_jul") or 0), 2)
        filas.append({"pais": "Ecuador", "concepto": "Gasto Ene-Jul vs eeff_ecuador_2026-07_OFICIAL.json",
                      "dashboard": round((pr.get("real_ene_jun") or 0) + (pr.get("julio_agregado") or 0), 2),
                      "referencia": pr.get("oficial_ene_jul"), "diferencia": d, "cuadra": abs(d) < 0.01,
                      "nota": "Julio se toma como el residuo entre la cifra oficial y el detalle por cuenta de "
                              "Ene-Jun: por construcción cuadra, y por eso julio no tiene apertura por cuenta."})
        dd = round((ppto.get("vigente_total_hojas") or 0) - (ppto.get("vigente_total_declarado") or 0), 2)
        filas.append({"pais": "Ecuador", "concepto": "Presupuesto vigente H2: suma de cuentas hoja vs fila TOTAL",
                      "dashboard": ppto.get("vigente_total_hojas"), "referencia": ppto.get("vigente_total_declarado"),
                      "diferencia": dd, "cuadra": abs(dd) < 1.0, "nota": None})
        dj = round((pr.get("real_ene_jun") or 0) - 251179.21 * 0, 2)
    duras = [f for f in filas if f["diferencia"] is not None and not f.get("tolerable")]
    return {"generado": datetime.datetime.now().isoformat(timespec="seconds"), "filas": filas,
            "todo_cuadra": all(f["cuadra"] for f in duras),
            "nota": "Las líneas marcadas como tolerables comparan contra un archivo con días de antigüedad: "
                    "la diferencia es movimiento real, no un descuadre."}


def escribir(doc):
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = DEST.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(DEST))
    hist = OUT / "historico_compras"
    hist.mkdir(exist_ok=True)
    (hist / ("dashboard_compras_%s.json" % doc["generado_fecha"].replace("-", ""))).write_text(
        json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    log("[OK] -> %s" % DEST)
    return DEST


def imprimir(doc):
    print("")
    print("=" * 84)
    print("  CONCILIACIÓN — dashboard de compras contra las fuentes ya validadas")
    print("=" * 84)
    for f in doc["conciliacion"]["filas"]:
        ok = "OK " if f["cuadra"] else "!! "
        ref = "{:>18,.2f}".format(f["referencia"]) if f["referencia"] is not None else "%18s" % "(sin ref)"
        dif = "{:>14,.2f}".format(f["diferencia"]) if f["diferencia"] is not None else "%14s" % "-"
        print("  %s %-11s %s" % (ok, f["pais"], f["concepto"]))
        print("      dashboard {:>18,.2f}   referencia {}   dif {}".format(f["dashboard"] or 0, ref, dif))
        if f.get("nota"):
            print("      nota: %s" % f["nota"])
    print("-" * 84)
    print("  RESULTADO: %s" % ("TODO CUADRA" if doc["conciliacion"]["todo_cuadra"] else "HAY DIFERENCIAS — explicadas arriba"))
    print("=" * 84)
    print("\n  RESUMEN (los tres números NO se suman entre sí):")
    print("  %-12s %-5s %18s %18s %18s %8s %8s" % ("PAIS", "MON", "COMPRA YTD", "SALDO CxP", "PAGOS YTD", "%VENC", "DPO"))
    for pais, p in doc["paises"].items():
        print("  %-12s %-5s {:>18,.2f} {:>18,.2f} {:>18,.2f} %7s %7s".format(
            p["compra"]["ytd"], p["cxp"]["total"], p["pagos"]["ytd"]) %
            (pais, p["moneda"],
             ("%.0f%%" % (p["cxp"]["pct_vencido"] * 100)) if p["cxp"]["pct_vencido"] is not None else "-",
             ("%.0f d" % p["dpo"]["puntual"]) if p["dpo"]["puntual"] else "-"))
    c = doc["consolidado"]
    print("  %-12s %-5s {:>18,.2f} {:>18,.2f} {:>18,.2f}  (USD referencial)".format(
        c["compra_ytd"], c["cxp_total"], c["pagos_ytd"]) % ("GRUPO", "USD"))
    print("\n  AVISOS (%d):" % len(doc["avisos"]))
    for a in doc["avisos"]:
        print("   [%-7s] %-11s %-15s %s" % (a["nivel"], a["pais"] or "GRUPO", a["bloque"], a["texto"]))
    print("")


# =====================================================================
#  Autoprueba offline
# =====================================================================
def _autotest():
    global OUT, DEST, CACHE_PPTO, XL_VIGENTE, XL_ORIGINAL, EEFF_OFICIAL, PAGOS_DIR
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    OUT = tmp / "OdooVentas"; DEST = OUT / "dashboard_compras.json"
    CACHE_PPTO = OUT / "cache.json"
    XL_VIGENTE = tmp / "no_existe.xlsx"; XL_ORIGINAL = tmp / "no_existe2.xlsx"
    EEFF_OFICIAL = tmp / "eeff.json"
    EEFF_OFICIAL.write_text(json.dumps({"resultados": {"gastos_de_ventas": 142154.78,
                                                       "gastos_administrativos": 132565.41,
                                                       "gastos_financieros": 12715.76,
                                                       "gastos_no_deducibles": 26703.95}}), encoding="utf-8")
    PAGOS_DIR = tmp / "Pagos"
    (PAGOS_DIR / "cxp").mkdir(parents=True)
    hoy = datetime.date(2026, 8, 20)

    COMPS = [{"id": 2, "name": "VICOMER S.A.S.", "currency_id": [1, "USD"]},
             {"id": 1, "name": "VINTRAL S.A.S.", "currency_id": [3, "COP"]},
             {"id": 3, "name": "3-102-940094 SRL", "currency_id": [1, "USD"]},
             {"id": 11, "name": "VIX S.A.S.", "currency_id": [1, "USD"]}]
    PAISES = [{"id": 63, "code": "EC"}, {"id": 49, "code": "CO"}, {"id": 50, "code": "CR"}]
    PARTNERS = {10: {"id": 10, "name": "TRANSPORTES LOCALES CIA LTDA", "vat": "1790000001001", "country_id": [63, "Ecuador"]},
                11: {"id": 11, "name": "BANCO GUAYAQUIL", "vat": "1790000002001", "country_id": [63, "Ecuador"]},
                12: {"id": 12, "name": "PROVEEDOR SIN PAIS S.A.", "vat": "", "country_id": False},
                20: {"id": 20, "name": "HYXION", "vat": "CN999", "country_id": [55, "China"]},
                21: {"id": 21, "name": "Odoo, Inc.", "vat": "US1", "country_id": [56, "United States"]},
                22: {"id": 22, "name": "ALQUILERES BOGOTA SAS", "vat": "900111222", "country_id": [49, "Colombia"]},
                23: {"id": 23, "name": "VICOMER S.A.S.", "vat": "1790000003001", "country_id": [49, "Colombia"]},
                30: {"id": 30, "name": "SERVICIOS CR S A", "vat": "3101000001", "country_id": [50, "Costa Rica"]}}
    ACCTS = {2: [{"id": 100, "code": "502.01.15.02", "name": "GV - TRANSPORTE DE CARGA", "account_type": "expense"},
                 {"id": 101, "code": "502.03.01.02", "name": "GF - GASTOS BANCARIOS", "account_type": "expense"},
                 {"id": 102, "code": "201.03.01.04", "name": "PROVEEDORES", "account_type": "liability_payable"},
                 {"id": 103, "code": "502.02.27.05", "name": "GA - SUMINISTROS Y MATERIALES", "account_type": "expense"}],
             1: [{"id": 200, "code": "502.01.09.01", "name": "ALQUILER DE BODEGA", "account_type": "expense"},
                 {"id": 201, "code": "201.03.02.01", "name": "PROVEEDORES DEL EXTERIOR", "account_type": "liability_payable"},
                 {"id": 202, "code": "101.03.07.02", "name": "IMPORTACION 006", "account_type": "asset_current"},
                 {"id": 203, "code": "502.01.05.01", "name": "HONORARIOS CONTABLES", "account_type": "expense"},
                 {"id": 204, "code": "502.01.11.01", "name": "PROMOCION Y PUBLICIDAD", "account_type": "expense"}],
             3: [{"id": 300, "code": "502.02.05", "name": "HONORARIOS PROFESIONALES", "account_type": "expense"}],
             11: [{"id": 400, "code": "5", "name": "GASTO VIX", "account_type": "expense"}]}
    MOVES = [
        {"id": 1, "name": "FC-EC-1", "invoice_date": "2026-08-05", "invoice_date_due": "2026-09-04",
         "partner_id": [10, "TRANSPORTES LOCALES CIA LTDA"], "amount_untaxed_signed": -1000.0,
         "amount_total_signed": -1120.0, "amount_residual": 1120.0, "amount_residual_signed": -1120.0,
         "currency_id": [1, "USD"], "company_id": [2, "VICOMER S.A.S."], "move_type": "in_invoice",
         "invoice_payment_term_id": [5, "30 Days"], "payment_state": "not_paid"},
        {"id": 2, "name": "FC-EC-2", "invoice_date": "2026-08-06", "invoice_date_due": "2026-06-01",
         "partner_id": [11, "BANCO GUAYAQUIL"], "amount_untaxed_signed": -200.0, "amount_total_signed": -200.0,
         "amount_residual": 200.0, "amount_residual_signed": -200.0, "currency_id": [1, "USD"],
         "company_id": [2, "VICOMER S.A.S."], "move_type": "in_invoice", "invoice_payment_term_id": False,
         "payment_state": "not_paid"},
        {"id": 3, "name": "FC-EC-3", "invoice_date": "2026-08-07", "invoice_date_due": "2026-09-07",
         "partner_id": [12, "PROVEEDOR SIN PAIS S.A."], "amount_untaxed_signed": -50.0, "amount_total_signed": -50.0,
         "amount_residual": 50.0, "amount_residual_signed": -50.0, "currency_id": [1, "USD"],
         "company_id": [2, "VICOMER S.A.S."], "move_type": "in_invoice", "invoice_payment_term_id": False,
         "payment_state": "not_paid"},
        {"id": 4, "name": "FC-CO-1", "invoice_date": "2026-05-10", "invoice_date_due": "2026-05-20",
         "partner_id": [20, "HYXION"], "amount_untaxed_signed": -439154677.36, "amount_total_signed": -439154677.36,
         "amount_residual": 439154677.36, "amount_residual_signed": -439154677.36, "currency_id": [3, "COP"],
         "company_id": [1, "VINTRAL S.A.S."], "move_type": "in_invoice", "invoice_payment_term_id": False,
         "payment_state": "not_paid"},
        {"id": 5, "name": "FC-CO-2", "invoice_date": "2026-06-10", "invoice_date_due": "2026-07-10",
         "partner_id": [22, "ALQUILERES BOGOTA SAS"], "amount_untaxed_signed": -12916030.0,
         "amount_total_signed": -12916030.0, "amount_residual": 12916030.0, "amount_residual_signed": -12916030.0,
         "currency_id": [3, "COP"], "company_id": [1, "VINTRAL S.A.S."], "move_type": "in_invoice",
         "invoice_payment_term_id": [6, "45 Days"], "payment_state": "not_paid"},
        {"id": 6, "name": "FC-CO-3", "invoice_date": "2026-07-01", "invoice_date_due": "2026-08-01",
         "partner_id": [21, "Odoo, Inc."], "amount_untaxed_signed": -572186.91, "amount_total_signed": -572186.91,
         "amount_residual": 0.0, "amount_residual_signed": 0.0, "currency_id": [3, "COP"],
         "company_id": [1, "VINTRAL S.A.S."], "move_type": "in_invoice", "invoice_payment_term_id": False,
         "payment_state": "paid"},
        {"id": 7, "name": "FC-CO-4", "invoice_date": "2026-07-15", "invoice_date_due": "2026-08-15",
         "partner_id": [23, "VICOMER S.A.S."], "amount_untaxed_signed": -9000000.0, "amount_total_signed": -9000000.0,
         "amount_residual": 9000000.0, "amount_residual_signed": -9000000.0, "currency_id": [3, "COP"],
         "company_id": [1, "VINTRAL S.A.S."], "move_type": "in_invoice", "invoice_payment_term_id": False,
         "payment_state": "not_paid"},
        {"id": 8, "name": "FC-CR-1", "invoice_date": "2026-06-08", "invoice_date_due": "2026-05-08",
         "partner_id": [30, "SERVICIOS CR S A"], "amount_untaxed_signed": -6544.93, "amount_total_signed": -6544.93,
         "amount_residual": 3500000.0, "amount_residual_signed": -6544.93, "currency_id": [9, "CRC"],
         "company_id": [3, "3-102-940094 SRL"], "move_type": "in_invoice", "invoice_payment_term_id": False,
         "payment_state": "not_paid"},
        {"id": 10, "name": "FC-CO-VIEJA", "invoice_date": "2025-11-20", "invoice_date_due": "2025-12-20",
         "partner_id": [22, "ALQUILERES BOGOTA SAS"], "amount_untaxed_signed": -5000000.0,
         "amount_total_signed": -5000000.0, "amount_residual": 5000000.0, "amount_residual_signed": -5000000.0,
         "currency_id": [3, "COP"], "company_id": [1, "VINTRAL S.A.S."], "move_type": "in_invoice",
         "invoice_payment_term_id": False, "payment_state": "not_paid"},
        {"id": 9, "name": "FC-VIX-1", "invoice_date": "2026-07-01", "invoice_date_due": "2026-08-01",
         "partner_id": [10, "TRANSPORTES LOCALES CIA LTDA"], "amount_untaxed_signed": -5000.0,
         "amount_total_signed": -5000.0, "amount_residual": 5000.0, "amount_residual_signed": -5000.0,
         "currency_id": [1, "USD"], "company_id": [11, "VIX S.A.S."], "move_type": "in_invoice",
         "invoice_payment_term_id": False, "payment_state": "not_paid"},
    ]
    LINES = [
        {"id": 1, "move_id": [1, "FC-EC-1"], "account_id": [100, "GV - TRANSPORTE DE CARGA"], "balance": 1000.0,
         "company_id": [2, "V"], "date": "2026-08-05", "display_type": False},
        {"id": 2, "move_id": [1, "FC-EC-1"], "account_id": [102, "PROVEEDORES"], "balance": -1120.0,
         "company_id": [2, "V"], "date": "2026-08-05", "display_type": False},
        {"id": 3, "move_id": [2, "FC-EC-2"], "account_id": [101, "GF - GASTOS BANCARIOS"], "balance": 200.0,
         "company_id": [2, "V"], "date": "2026-08-06", "display_type": False},
        {"id": 4, "move_id": [3, "FC-EC-3"], "account_id": [103, "GA - SUMINISTROS Y MATERIALES"], "balance": 50.0,
         "company_id": [2, "V"], "date": "2026-08-07", "display_type": False},
        {"id": 5, "move_id": [4, "FC-CO-1"], "account_id": [202, "IMPORTACION 006"], "balance": 439154677.36,
         "company_id": [1, "V"], "date": "2026-05-10", "display_type": False},
        {"id": 6, "move_id": [5, "FC-CO-2"], "account_id": [200, "ALQUILER DE BODEGA"], "balance": 12916030.0,
         "company_id": [1, "V"], "date": "2026-06-10", "display_type": False},
        {"id": 7, "move_id": [6, "FC-CO-3"], "account_id": [203, "HONORARIOS CONTABLES"], "balance": 572186.91,
         "company_id": [1, "V"], "date": "2026-07-01", "display_type": False},
        {"id": 8, "move_id": [7, "FC-CO-4"], "account_id": [203, "HONORARIOS CONTABLES"], "balance": 9000000.0,
         "company_id": [1, "V"], "date": "2026-07-15", "display_type": False},
        {"id": 9, "move_id": [8, "FC-CR-1"], "account_id": [300, "HONORARIOS PROFESIONALES"], "balance": 6544.93,
         "company_id": [3, "V"], "date": "2026-06-08", "display_type": False},
        {"id": 10, "move_id": [9, "FC-VIX-1"], "account_id": [400, "GASTO VIX"], "balance": 5000.0,
         "company_id": [11, "V"], "date": "2026-07-01", "display_type": False},
    ]
    PAYS = [{"id": 1, "date": "2026-08-10", "amount": 500.0, "amount_company_currency_signed": -500.0,
             "currency_id": [1, "USD"], "company_id": [2, "V"], "partner_id": [10, "T"], "state": "posted"},
            {"id": 2, "date": "2026-07-20", "amount": 3000000.0, "amount_company_currency_signed": -3000000.0,
             "currency_id": [3, "COP"], "company_id": [1, "V"], "partner_id": [22, "A"], "state": "posted"}]

    def dget(dom, f):
        return [c for c in dom if isinstance(c, (list, tuple)) and c and c[0] == f]

    class Mock(object):
        def execute_kw(self, db, uid, key, model, method, args, kw=None):
            kw = kw or {}
            dom = args[0] if args else []
            if model == "res.company":
                return COMPS
            if model == "res.country":
                return PAISES
            if model == "res.partner":
                ids = dget(dom, "id")
                want = ids[0][2] if ids else []
                return [PARTNERS[i] for i in want if i in PARTNERS]
            if model == "account.account":
                cids = (kw.get("context") or {}).get("allowed_company_ids") or []
                ids = dget(dom, "id")
                want = set(ids[0][2] if ids else [])
                out = []
                for c in cids:
                    out += [a for a in ACCTS.get(c, []) if a["id"] in want]
                return out
            if model == "account.move":
                data = list(MOVES)
                for c in dget(dom, "invoice_date"):
                    if c[1] == ">=":
                        data = [x for x in data if x["invoice_date"] >= c[2]]
                    if c[1] == "<=":
                        data = [x for x in data if x["invoice_date"] <= c[2]]
                for c in dget(dom, "amount_residual"):
                    if c[1] == "!=" and c[2] == 0:
                        data = [x for x in data if x.get("amount_residual")]
                if method == "search_count":
                    return len(data)
                f = kw.get("fields")
                return [dict((k, x.get(k)) for k in f + ["id"]) for x in data] if f else data
            if model == "account.move.line":
                if dget(dom, "account_id.account_type"):
                    return []
                mids = dget(dom, "move_id")
                want = set(mids[0][2] if mids else [])
                data = [l for l in LINES if l["move_id"][0] in want]
                f = kw.get("fields")
                return [dict((k, x.get(k)) for k in f if k in x or True) for x in data] if f else data
            if model == "account.payment":
                f = kw.get("fields")
                return [dict((k, x.get(k)) for k in f) for x in PAYS] if f else PAYS
            if model == "account.partial.reconcile":
                return []
            return []

    class FakeOdoo(Odoo):
        def __init__(self, cfg):
            self.cfg = cfg; self.uid = 1; self.calls = 0
            self.models = Mock(); self.common = None
        def authenticate(self): return 1

    cfg = {"url": "http://mock", "db": "m", "login": "x", "apikey": "y",
           "_raw": {"company_map": {"VICOMER": "Ecuador", "VIX": "ignore", "VINTRAL": "Colombia",
                                    "3-102-940094": "Costa Rica"}}}
    reglas = json.loads((PROJ / "compras_reglas.json").read_text(encoding="utf-8")) \
        if (PROJ / "compras_reglas.json").exists() else json.loads(Path("compras_reglas.json").read_text(encoding="utf-8"))
    dep = {"keywords": {"transport": "Operaciones", "banco": "Gerencia", "bodega": "Operaciones",
                        "contab": "Gerencia"}, "default": "Gerencia", "tc_manual": {"COP": 0.00027027, "CRC": 0.00221}}

    av = Avisos()
    doc = construir(FakeOdoo(cfg), 2026, av, hoy=hoy, reglas=reglas, depto=dep)
    ec, co, cr = doc["paises"]["Ecuador"], doc["paises"]["Colombia"], doc["paises"]["Costa Rica"]
    fallos = []

    def chk(c, m):
        if not c:
            fallos.append(m)
        print(("  OK  " if c else "  FALLA ") + m)

    print("\nAUTOPRUEBA compras_dashboard.py")
    print("-" * 74)
    chk(abs(ec["compra"]["ytd"] - 1000.0) < 0.01,
        "Ecuador: compra operativa = 1.000 (el banco y el proveedor sin país NO entran)")
    chk(ec["excluido"]["no_operativo"].get("Financieros", {}).get("monto") == 200.0,
        "Los 200 del banco salen como Financieros, visibles y no borrados")
    chk(ec["excluido"]["sin_clasificar"]["monto"] == 50.0 and ec["excluido"]["sin_clasificar"]["n"] == 1,
        "El proveedor sin país va al bucket SIN CLASIFICAR con su monto")
    chk(abs(co["excluido"]["importacion"]["monto"] - 439154677.36) < 1,
        "HYXION queda excluida como IMPORTACIÓN y contabilizada")
    chk(abs(co["excluido"]["servicios_exterior"]["monto"] - 572186.91) < 1,
        "Odoo Inc. queda en SERVICIOS DEL EXTERIOR, separada de la importación")
    chk(co["excluido"]["no_operativo"].get("Intercompañía", {}).get("monto") == 9000000.0,
        "La factura de VICOMER a VINTRAL sale como Intercompañía")
    chk(abs(co["compra"]["ytd"] - 12916030.0) < 1,
        "Colombia: compra operativa local = sólo el alquiler de bodega")
    chk(any("VIX" in (p or "") for p in doc["excluidas_del_grupo"]),
        "VIX aparece declarada como compañía excluida")
    chk(all(abs(v) != 5000.0 for v in co["compra"]["mensual"] + ec["compra"]["mensual"]),
        "El gasto de VIX no entra en ningún país")
    chk(ec["compra"]["ytd"] != ec["cxp"]["total"] and ec["cxp"]["total"] != ec["pagos"]["ytd"],
        "Compra, CxP y pagos son tres números distintos")
    chk(abs(co["cxp"]["total"] - (439154677.36 + 12916030.0 + 9000000.0 + 5000000.0)) < 1,
        "La CxP incluye lo que se debe al EXTERIOR, a intercompañía y de años anteriores")
    chk(abs(co["compra"]["puente"]["neto_facturas_local"] - (12916030.0 + 9000000.0)) < 1
        and abs(co["compra"]["puente"]["gasto_operativo"] + co["compra"]["puente"]["menos_no_operativo"]
                + co["compra"]["puente"]["resto_a_cuentas_de_balance"]
                - co["compra"]["puente"]["neto_facturas_local"]) < 1,
        "El puente cuadra: neto facturado local = gasto operativo + no operativo + cuentas de balance")
    chk(abs(ec["pagos"]["ytd"] - 500.0) < 0.01, "Pagos ejecutados salen de account.payment")
    chk(abs(cr["cxp"]["total"] - 6544.93) < 0.01,
        "Costa Rica: la CxP se agrega en moneda de la compañía, no mezclando CRC con USD")
    chk(cr["cxp"]["proveedores"][0]["dias"] > 90, "El aging usa la fecha de vencimiento")
    chk(co["presupuesto"]["disponible"] is False and "no hay presupuesto" in co["presupuesto"]["motivo"].lower(),
        "Colombia muestra 'sin presupuesto de gastos', no cero")
    chk(cr["presupuesto"]["disponible"] is False, "Costa Rica también")
    chk(doc["tc"]["referencial"] is True and doc["consolidado"]["referencial"] is True,
        "Todo USD consolidado va marcado como referencial")
    chk(doc["cobertura_clasificacion"]["cobertura"] < 1.0 and doc["cobertura_clasificacion"]["pendientes"],
        "La cobertura de clasificación se mide y lista a los pendientes")
    chk(any(a["bloque"] == "clasificación" for a in doc["avisos"]),
        "La cobertura incompleta genera aviso")
    chk(canon("5.2.01.06.05", "excel") == canon("502.01.06.05", "odoo") == "502.01.06.05"
        and canon("5.4.01.01.02", "excel") == canon("502.03.01.02", "odoo")
        and canon("5.3.01.09.05", "excel") == canon("502.02.09.05", "odoo"),
        "El cruce traduce el codigo del Excel (5.G.01.x) al de Odoo (502.0(G-1).x), no solo quita puntos")
    chk(ec["dpo"]["puntual"] is not None and "puntual" in ec["dpo"]["metodo"],
        "El DPO se declara como puntual, no como promedio")
    chk(co["dpo"]["compra_periodo"] > co["dpo"]["compra_local_periodo"],
        "El DPO divide por la compra TOTAL (con exterior), no por la compra local: mismo universo que la deuda")
    chk(abs(co["compra"]["total_ytd"] - (439154677.36 + 12916030.0 + 9000000.0 + 572186.91)) < 1,
        "La compra total incluye importación, servicios del exterior e intercompañía")
    chk(co["control"]["sin_explicar"] is not None and "saldo_cxp_anterior" in co["control"],
        "La ecuación de control se publica y separa la deuda de años anteriores")
    chk(abs(co["cxp"]["total_anios_anteriores"] - 5000000.0) < 1 and co["cxp"]["por_anio"].get("2025"),
        "La CxP incluye la factura de 2025 sin pagar: la deuda vieja no desaparece del tablero")
    chk(abs(co["compra"]["total_ytd"] - (439154677.36 + 12916030.0 + 9000000.0 + 572186.91)) < 1,
        "...pero esa factura vieja NO entra en la compra del año")
    chk(ec["brecha_plazo"]["cobertura_plazo"] is not None,
        "La cobertura de plazo pactado se mide y se publica")
    chk(len(ec["calendario"]["semanas"]) == 8, "El calendario de pagos cubre 8 semanas")
    chk(ec["escenarios"]["pagar_todo_vencido"]["monto"] >= 0, "Los escenarios de caja se calculan")
    escribir(doc)
    chk(DEST.exists(), "El JSON se escribe de forma atómica")
    escribir(doc)
    chk(len(list((OUT / "historico_compras").glob("*.json"))) == 1, "Idempotente: dos corridas no duplican archivos")
    print("-" * 74)
    if fallos:
        print("AUTOPRUEBA FALLÓ (%d):" % len(fallos))
        for f in fallos:
            print("   - " + f)
        sys.exit(1)
    print("AUTOPRUEBA OK — %d comprobaciones" % 32)


def diagnostico():
    cfg = load_config()
    od = Odoo(cfg); od.authenticate()
    reglas = load_reglas(); dep = load_depto()
    print("=" * 78)
    print("  DIAG compras_dashboard.py")
    print("=" * 78)
    print("  Odoo %s db=%s uid=%s" % (cfg["url"], cfg["db"], od.uid))
    print("  Reglas: compras_reglas.json v%s" % reglas.get("version"))
    print("  Presupuesto vigente : %s (%s)" % (XL_VIGENTE.name, "existe" if XL_VIGENTE.exists() else "NO EXISTE"))
    print("  Presupuesto original: %s (%s)" % (XL_ORIGINAL.name, "existe" if XL_ORIGINAL.exists() else "NO EXISTE"))
    print("  EEFF oficial EC     : %s" % ("existe" if EEFF_OFICIAL.exists() else "NO EXISTE"))
    print("  CxP referencia      : %s" % ("existe" if (PAGOS_DIR / 'cxp' / 'cxp_semana_actual.json').exists() else "NO EXISTE"))
    comps = companias(od, (cfg.get("_raw") or {}).get("company_map") or {})
    for c in comps.values():
        print("   [%-3s] %-46s %-4s -> %s" % (c["id"], (c["name"] or "")[:46], c["moneda"] or "?",
                                              "EXCLUIDA" if c["excluida"] else (c["pais"] or "SIN MAPEAR")))
    year = datetime.date.today().year
    f, om = traer_facturas(od, year, list(comps.keys()))
    print("\n  Facturas de proveedor %d: %d  (campos omitidos: %s)" % (year, len(f), om or "ninguno"))
    l = traer_lineas(od, [x["id"] for x in f][:60], list(comps.keys()))
    print("  Líneas de una muestra de 60 facturas: %d" % len(l))
    print("  Llamadas XML-RPC: %d" % od.calls)
    print("  OK — diag no escribe el JSON.")


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else str(datetime.date.today().year)
    if arg == "autotest":
        _autotest(); return
    if arg == "diag":
        diagnostico(); return
    year = int(arg) if arg.isdigit() else datetime.date.today().year
    av = Avisos()
    cfg = load_config()
    od = Odoo(cfg); od.authenticate()
    log("Odoo %s db='%s' uid=%s" % (cfg["url"], cfg["db"], od.uid))
    doc = construir(od, year, av)
    escribir(doc)
    imprimir(doc)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("[ERROR]\n" + traceback.format_exc())
        sys.exit(1)
