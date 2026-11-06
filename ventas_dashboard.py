#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ventas_dashboard.py  ·  Grupo VICOMER
=====================================
EXTRACCION -> CONTRATO JSON  del sistema de dashboards ejecutivos de ventas.

Este script NO dibuja nada. Su unica responsabilidad es dejar en
OdooVentas/dashboard_ventas.json un documento auto-descriptivo con:
  - las cifras
  - la FUENTE de cada bloque
  - la fecha de cada extraccion
  - los HUECOS declarados (avisos), nunca rellenados

El render (ventas_dashboard_render.py) no vuelve a tocar Odoo.

REGLAS DE NEGOCIO (no negociables, ver DASHBOARD_VENTAS_SETUP.md)
  * Venta = amount_untaxed_signed (neta sin IVA, con signo). Solo 'posted'.
  * Ecuador: Ene-Jul 2026 vive en Perseo (odoo_config -> ecuador_hist_mensual);
    Odoo es fuente de verdad desde ecuador_corte_migracion (2026-08-01).
    NUNCA se agrega el mes del corte al historico: se contaria dos veces.
  * Colombia: Ene-Mar de la instancia anterior (colombia_hist_mensual) + Odoo desde Abr.
  * VIX S.A.S. se EXCLUYE del consolidado (decision de gerencia).
  * Odoo no mantiene tipos de cambio -> el USD consolidado es REFERENCIAL,
    calculado con pagos_reglas_depto.json -> tc_manual.
  * Un cero real y un dato faltante son cosas distintas y deben verse distintas.

MODOS
    python3 ventas_dashboard.py test     # autoprueba offline (sin red, sin Odoo)
    python3 ventas_dashboard.py diag     # conexion + conteos crudos, no escribe el JSON
    python3 ventas_dashboard.py 2026     # extraccion completa del anio
    python3 ventas_dashboard.py          # anio en curso

Solo biblioteca estandar de Python 3 (xmlrpc, zipfile, xml.etree). Sin pandas,
sin requests, sin openpyxl.
"""

import os, sys, json, ssl, csv, math, zipfile, datetime, traceback, xmlrpc.client
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
OUT_DIR = Path(os.environ.get("ODOO_OUT_DIR", PROJ / "OdooVentas"))
PPTO_DIR = PROJ / "PresupuestoAuto"
def _files_dir():
    e = os.environ.get("PERSEO_FILES_DIR")
    if e:
        return Path(e)
    try:
        c = json.loads((HOME / "Claude" / "Projects" / "CFO VICOMER" / "odoo_config.json").read_text(encoding="utf-8"))
        if c.get("files_dir") and Path(c["files_dir"]).exists():
            return Path(c["files_dir"])
    except Exception:
        pass
    return HOME / "Desktop" / "VICOMER COMERCIAL"


FILES_DIR = _files_dir()


def _buscar_regional():
    """El libro Regional se mueve y se renombra (uno o dos espacios, con o sin guion).

    Fijar una sola ruta hacia que el dashboard perdiera la curva mensual de presupuesto
    en silencio, y quedara mostrando 'sin presupuesto' con toda naturalidad. Se busca en
    varias carpetas y por patron, y se reporta cual se uso.
    """
    env = os.environ.get("REGIONAL_XLSX")
    if env and Path(env).exists():
        return Path(env)
    # Busqueda RECURSIVA acotada: el 2026-09 el usuario reorganizo el Escritorio en
    # "01 EMPRESAS/" y todas las rutas fijas se rompieron sin avisar. El dashboard salio
    # tres semanas sin curva de presupuesto y sin que nada fallara.
    raices = [FILES_DIR, FILES_DIR.parent, HOME / "Desktop", HOME / "Documents",
              HOME / "Claude" / "Projects" / "CFO VICOMER"]
    cands = []
    vistos = set()
    for raiz in raices:
        try:
            if not raiz.exists() or str(raiz) in vistos:
                continue
            vistos.add(str(raiz))
            for f in raiz.rglob("*.xlsx"):
                try:
                    if len(f.relative_to(raiz).parts) > 4:
                        continue
                except Exception:
                    continue
                n = f.name.upper()
                if n.startswith("~$"):
                    continue
                if "PRESUPUESTO" in n and "REGIONAL" in n and "2026" in n:
                    cands.append(f)
        except Exception:
            continue
    if not cands:
        return FILES_DIR / "PRESUPUESTO COMERCIAL REGIONAL 2026 - GRUPO VICOMER.xlsx"
    cands.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    hallado = cands[0]
    # Se guarda la carpeta en odoo_config.json: estado_grupo.py y perseo_presupuesto.py
    # leen sus libros de ahi via PERSEO_FILES_DIR, y asi una sola mudanza no rompe todo
    # el ecosistema otra vez.
    try:
        cfgf = HOME / "Claude" / "Projects" / "CFO VICOMER" / "odoo_config.json"
        if cfgf.exists():
            d = json.loads(cfgf.read_text(encoding="utf-8"))
            if d.get("files_dir") != str(hallado.parent):
                d["files_dir"] = str(hallado.parent)
                d["_nota_files_dir"] = ("Carpeta donde vive el libro Regional de presupuesto. La detecta "
                                        "ventas_dashboard.py buscando por patron y la guarda aqui para que "
                                        "estado_grupo.py y perseo_presupuesto.py la usen via PERSEO_FILES_DIR.")
                cfgf.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return hallado


REGIONAL_XLSX = _buscar_regional()
DEST_JSON = OUT_DIR / "dashboard_ventas.json"

MESES = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]
ORDEN_PAISES = ["Ecuador", "Colombia", "Costa Rica"]
INCOME_TYPES = ("income", "income_other")
COGS_TYPES = ("expense_direct_cost", "cost_of_revenue")
COGS_NOMBRE = ("COSTO DE VENTA", "COSTO DE LA MERCANCIA", "COSTO DE MERCANCIA",
               "COSTO DE VENTAS", "COSTO MERCADERIA", "COST OF GOODS",
               "COSTO DE LA MERCANCÍA", "COSTO MERCANCIA")

TOP_PRODUCTOS = 15
TOP_CLIENTES = 10
HHI_CRITICO = 2500


def log(m):
    print("[%s] %s" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), m), flush=True)


# =====================================================================
#  Avisos: el dashboard declara sus huecos, no los rellena
# =====================================================================
class Avisos(object):
    def __init__(self):
        self.items = []

    def add(self, nivel, pais, bloque, texto):
        """nivel: 'critico' | 'alerta' | 'nota'"""
        self.items.append({"nivel": nivel, "pais": pais, "bloque": bloque, "texto": texto})
        log("  [%s] %s/%s: %s" % (nivel.upper(), pais or "GRUPO", bloque, texto))

    def dump(self):
        orden = {"critico": 0, "alerta": 1, "nota": 2}
        return sorted(self.items, key=lambda a: (orden.get(a["nivel"], 9), a["pais"] or "", a["bloque"]))


# =====================================================================
#  Configuracion
# =====================================================================
def load_config():
    cfg = {"url": os.environ.get("ODOO_URL"), "db": os.environ.get("ODOO_DB"),
           "login": os.environ.get("ODOO_LOGIN"), "apikey": os.environ.get("ODOO_APIKEY")}
    extra = {}
    for f in (Path(__file__).resolve().parent / "odoo_config.json",
              PROJ / "odoo_config.json", HOME / ".odoo_config.json"):
        if f.exists():
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                for k in ("url", "db", "login", "apikey"):
                    cfg[k] = cfg[k] or d.get(k)
                extra = extra or d
            except Exception as e:
                log("[WARN] no se pudo leer %s: %s" % (f, e))
    for kf in (PROJ / "odoo_apikey.txt", HOME / ".odoo_apikey"):
        if not cfg["apikey"] and kf.exists():
            cfg["apikey"] = kf.read_text(encoding="utf-8").strip()
    if cfg.get("url"):
        cfg["url"] = cfg["url"].rstrip("/")
    cfg["_raw"] = extra
    return cfg


def load_tc():
    """Tipos de cambio manuales. Odoo NO los mantiene (todo devuelve 0.00031805)."""
    tc = {"COP": 0.00027027, "CRC": 0.00221}
    fuente = "default embebido"
    f = PROJ / "pagos_reglas_depto.json"
    if f.exists():
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            man = d.get("tc_manual") or {}
            for k, v in man.items():
                tc[k] = float(v)
            fuente = "pagos_reglas_depto.json -> tc_manual"
        except Exception as e:
            log("[WARN] tc_manual ilegible: %s" % e)
    tc["USD"] = 1.0
    return {"tasas": tc, "fuente": fuente,
            "cop_por_usd": round(1.0 / tc["COP"], 2) if tc.get("COP") else None,
            "crc_por_usd": round(1.0 / tc["CRC"], 2) if tc.get("CRC") else None,
            "referencial": True}


def pais_de_empresa(nombre, company_map):
    """Gana el fragmento MAS LARGO que este contenido en el nombre de la compania."""
    n = (nombre or "").upper()
    best, blen = None, -1
    for frag, pais in (company_map or {}).items():
        f = frag.upper()
        if f and f in n and len(f) > blen:
            best, blen = pais, len(f)
    return best


# =====================================================================
#  Lector de XLSX con biblioteca estandar (zip + XML). Sin openpyxl.
# =====================================================================
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
NSR = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _col_to_idx(ref):
    n = 0
    for ch in ref:
        if ch.isalpha():
            n = n * 26 + (ord(ch.upper()) - 64)
        else:
            break
    return n


def _row_of(ref):
    d = "".join(c for c in ref if c.isdigit())
    return int(d) if d else 0


def xlsx_sheets(path):
    """{nombre_hoja: ruta interna} respetando el orden del libro."""
    out = {}
    with zipfile.ZipFile(str(path)) as z:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        rmap = {}
        for r in rels:
            rid = r.get("Id"); tgt = r.get("Target") or ""
            if tgt.startswith("/"):
                tgt = tgt[1:]
            elif not tgt.startswith("xl/"):
                tgt = "xl/" + tgt
            rmap[rid] = tgt
        for sh in wb.iter(NS + "sheet"):
            out[sh.get("name")] = rmap.get(sh.get(NSR + "id"))
    return out


def xlsx_read(path, sheet_name):
    """Devuelve {(fila, col): valor} con valores en cache (data_only equivalente)."""
    sheets = xlsx_sheets(path)
    target = None
    for name, p in sheets.items():
        if name.strip().upper() == sheet_name.strip().upper():
            target = p; break
    if not target:
        raise KeyError("hoja '%s' no existe (hay: %s)" % (sheet_name, list(sheets.keys())))
    with zipfile.ZipFile(str(path)) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            ss = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in ss.iter(NS + "si"):
                shared.append("".join(t.text or "" for t in si.iter(NS + "t")))
        cells = {}
        root = ET.fromstring(z.read(target))
        for c in root.iter(NS + "c"):
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
            cells[(_row_of(ref), _col_to_idx(ref))] = val
    return cells


def _num(v):
    try:
        return float(v)
    except Exception:
        return 0.0


def buscar_fila_presupuesto(cells, objetivo_anual, tol=0.01):
    """Encuentra la fila TOTAL del pais VALIDANDO contra el anual ya conocido.

    No se fija el numero de fila ni la columna de enero: se barren todas las filas y
    todas las ventanas de 12 columnas consecutivas, y se acepta la que cumpla LAS TRES
    condiciones. Con una sola (que sume el anual) no basta: en las hojas de Colombia y
    Costa Rica hay filas donde UNA celda trae el total del anio, y eso producia una
    "curva mensual" con todo el presupuesto cargado en un solo mes.

      1. la suma de las 12 celdas cuadra con el presupuesto anual conocido,
      2. al menos 6 de los 12 meses tienen cifra (un presupuesto comercial no vive en un mes),
      3. ningun mes se lleva mas del 45% del anio.

    Si nada cumple, devuelve None y el bloque se declara como hueco.
    """
    if not objetivo_anual:
        return None, None, "sin presupuesto anual de referencia contra el cual validar"
    filas = sorted(set(r for (r, c) in cells.keys()))
    max_c = max([c for (r, c) in cells.keys()] or [0])
    mejor = None
    casi = 0
    for r in filas:
        for c0 in range(2, max(3, max_c - 10)):
            mensual = [_num(cells.get((r, c0 + k))) for k in range(12)]
            s12 = sum(mensual)
            if not s12 or abs(s12 - objetivo_anual) / abs(objetivo_anual) > tol:
                continue
            casi += 1
            con_dato = len([x for x in mensual if abs(x) > 0.005])
            pico = max(abs(x) for x in mensual) / abs(s12)
            if con_dato < 6 or pico > 0.45:
                continue
            err = abs(s12 - objetivo_anual) / abs(objetivo_anual)
            score = (con_dato, -err)
            if mejor is None or score > mejor[0]:
                etiqueta = cells.get((r, 1)) or cells.get((r, 2)) or cells.get((r, 3)) or ""
                mejor = (score, {"fila": r, "col_ene": c0,
                                 "mensual": [round(x, 2) for x in mensual],
                                 "anual": round(s12, 2), "meses_con_dato": con_dato,
                                 "pico_mes": round(pico, 4),
                                 "etiqueta": str(etiqueta)[:60]}, err)
    if mejor:
        return mejor[1], mejor[2], None
    motivo = ("ninguna fila reparte el presupuesto anual en al menos 6 meses" if casi
              else "ninguna fila suma el presupuesto anual conocido")
    return None, None, motivo


HOJAS_PAIS = {"Ecuador": ["ECUADOR 2026", "ECUADOR"],
              "Colombia": ["COLOMBIA 2026", "COLOMBIA"],
              "Costa Rica": ["COSTA RICA 2026", "COSTA RICA"]}


def presupuesto_mensual(estado_grupo, avisos):
    """Presupuesto mes a mes por pais, auto-validado contra el anual de estado_grupo."""
    out = {}
    if not REGIONAL_XLSX.exists():
        avisos.add("alerta", None, "presupuesto",
                   "No encuentro el libro Regional de presupuesto (busqué en %s por cualquier archivo que "
                   "contenga PRESUPUESTO + REGIONAL + 2026). Sin él no hay curva mensual de presupuesto; el YTD y "
                   "el anual de estado_grupo.json siguen siendo válidos. Si el libro se movió o se renombró, "
                   "apuntarlo con la variable REGIONAL_XLSX." %
                   ", ".join(str(x) for x in [FILES_DIR, HOME / "Desktop" / "VICOMER PERSONAL"]))
        return out
    out_fuente = str(REGIONAL_XLSX)
    try:
        hojas = xlsx_sheets(REGIONAL_XLSX)
    except Exception as e:
        avisos.add("alerta", None, "presupuesto", "No pude abrir el libro Regional: %s" % e)
        return out
    for pais in ORDEN_PAISES:
        d = (estado_grupo.get("paises") or {}).get(pais) or {}
        objetivo = d.get("ppto_anual")
        hoja = None
        for cand in HOJAS_PAIS.get(pais, []):
            for h in hojas:
                if h.strip().upper() == cand:
                    hoja = h; break
            if hoja:
                break
        if not hoja:
            avisos.add("alerta", pais, "presupuesto",
                       "No encontre la hoja de %s en el libro Regional; sin curva mensual de presupuesto." % pais)
            continue
        try:
            cells = xlsx_read(REGIONAL_XLSX, hoja)
        except Exception as e:
            avisos.add("alerta", pais, "presupuesto", "Hoja '%s' ilegible: %s" % (hoja, e))
            continue
        fila, err, motivo = buscar_fila_presupuesto(cells, objetivo)
        if not fila:
            avisos.add("alerta", pais, "presupuesto",
                       "En la hoja '%s' %s (presupuesto anual %s). El dashboard NO dibuja curva mensual de "
                       "presupuesto para %s: el YTD y el anual siguen siendo válidos, la estacionalidad no. "
                       "Para tenerla, el Regional debe traer el presupuesto abierto por mes en esa hoja." %
                       (hoja, motivo, "{:,.0f}".format(objetivo) if objetivo else "?", pais))
            continue
        out[pais] = {"mensual": fila["mensual"], "anual": fila["anual"], "hoja": hoja,
                     "fila": fila["fila"], "etiqueta": fila["etiqueta"],
                     "meses_con_dato": fila["meses_con_dato"], "pico_mes": fila["pico_mes"],
                     "validado_contra": objetivo, "error_relativo": round(err or 0, 6),
                     "fuente": "PRESUPUESTO COMERCIAL REGIONAL 2026 - GRUPO VICOMER.xlsx / hoja %s, fila %d, meses en columnas %d-%d" % (hoja, fila["fila"], fila["col_ene"], fila["col_ene"] + 11)}
    return out


# =====================================================================
#  Conexion Odoo
# =====================================================================
class Odoo(object):
    def __init__(self, cfg):
        self.cfg = cfg
        ctx = ssl.create_default_context()
        self.common = xmlrpc.client.ServerProxy(cfg["url"] + "/xmlrpc/2/common", allow_none=True, context=ctx)
        self.models = xmlrpc.client.ServerProxy(cfg["url"] + "/xmlrpc/2/object", allow_none=True, context=ctx)
        self.uid = None
        self.calls = 0

    def _dbs(self):
        cands = []
        if self.cfg.get("db"):
            cands.append(self.cfg["db"])
        host = self.cfg["url"].split("//")[-1].split("/")[0]
        cands += [host.split(".")[0], host.replace(".", "-"), host]
        seen, out = set(), []
        for c in cands:
            if c and c not in seen:
                seen.add(c); out.append(c)
        return out

    def authenticate(self):
        falta = [k for k in ("url", "login", "apikey") if not self.cfg.get(k)]
        if falta:
            raise RuntimeError("faltan credenciales de Odoo: " + ", ".join(falta))
        last = None
        for db in self._dbs():
            try:
                uid = self.common.authenticate(db, self.cfg["login"], self.cfg["apikey"], {})
            except Exception as e:
                last = str(e)[:200]; continue
            if uid:
                self.cfg["db"] = db; self.uid = uid
                return uid
        raise RuntimeError("no autentico con ninguna base de datos. Ultimo error: %s" % last)

    def kw(self, model, method, args, kwargs=None):
        self.calls += 1
        return self.models.execute_kw(self.cfg["db"], self.uid, self.cfg["apikey"],
                                      model, method, args, kwargs or {})

    def sr(self, model, domain, fields, limit=0, ctx=None):
        kw = {"fields": fields}
        if limit:
            kw["limit"] = limit
        if ctx:
            kw["context"] = ctx
        return self.kw(model, "search_read", [domain], kw)

    def sr_drop(self, model, domain, fields, ctx=None):
        """Reintenta quitando campos hasta que la consulta pase (bug l10n_ec)."""
        f = list(fields)
        omitidos = []
        while f:
            try:
                return self.sr(model, domain, f, ctx=ctx), omitidos
            except Exception as e:
                msg = str(e)
                drop = next((c for c in f if c in msg and c != "id"), None)
                if drop is None:
                    drop = f[-1] if len(f) > 1 else None
                if drop is None:
                    raise
                f.remove(drop); omitidos.append(drop)
        raise RuntimeError("no se pudo consultar " + model)


def _m2o(v):
    if isinstance(v, (list, tuple)) and len(v) == 2:
        return v[0], v[1]
    return None, None


def companias(od, company_map):
    rows = od.sr("res.company", [], ["id", "name", "currency_id"])
    out = {}
    for r in rows:
        _, cur = _m2o(r.get("currency_id"))
        pais = pais_de_empresa(r.get("name"), company_map)
        out[r["id"]] = {"id": r["id"], "name": r.get("name"), "moneda": cur,
                        "pais": None if pais in (None, "ignore") else pais,
                        "excluida": pais == "ignore"}
    return out


# =====================================================================
#  BLOQUE 1 — Ventas (fuente doble: historico + Odoo)
# =====================================================================
def fetch_facturas(od, year, comp_ids):
    dom = [["move_type", "in", ["out_invoice", "out_refund"]],
           ["state", "=", "posted"],
           ["invoice_date", ">=", "%d-01-01" % year],
           ["invoice_date", "<=", "%d-12-31" % year]]
    ctx = {"allowed_company_ids": comp_ids}
    campos = ["name", "invoice_date", "partner_id", "amount_untaxed_signed",
              "amount_total_signed", "currency_id", "company_id", "move_type"]
    recs, _ = od.sr_drop("account.move", dom, campos, ctx=ctx)
    out = []
    for r in recs:
        f = str(r.get("invoice_date") or "")[:10]
        if len(f) != 10:
            continue
        cid, cname = _m2o(r.get("company_id"))
        pid, pname = _m2o(r.get("partner_id"))
        _, cur = _m2o(r.get("currency_id"))
        out.append({"empresa_id": cid, "empresa": cname, "cliente_id": pid,
                    "cliente": pname or "(sin cliente)", "moneda": cur,
                    "fecha": f, "mes": int(f[5:7]), "doc": r.get("name"),
                    "tipo": r.get("move_type"),
                    "neto": round(float(r.get("amount_untaxed_signed") or 0), 2),
                    "bruto": round(float(r.get("amount_total_signed") or 0), 2)})
    return out


def ventas_por_pais(facturas, comps, cfg_raw, year, avisos):
    """Mensual por pais = historico pre-migracion + Odoo desde el corte."""
    hoy = datetime.date.today()
    corte_ec = str(cfg_raw.get("ecuador_corte_migracion") or "")[:10]
    mes_corte_ec = int(corte_ec[5:7]) if len(corte_ec) == 10 and corte_ec[:4] == str(year) else None

    hist_cfg = {"Ecuador": cfg_raw.get("ecuador_hist_mensual") or {},
                "Colombia": cfg_raw.get("colombia_hist_mensual") or {}}

    datos = {}
    for pais in ORDEN_PAISES:
        datos[pais] = {"moneda": None, "odoo_mensual": [0.0] * 12, "hist_mensual": [0.0] * 12,
                       "n_facturas": 0, "n_nc": 0, "empresas": []}

    excluidas = []
    sin_mapear = []
    for f in facturas:
        c = comps.get(f["empresa_id"]) or {}
        if c.get("excluida"):
            if c.get("name") not in excluidas:
                excluidas.append(c.get("name"))
            continue
        pais = c.get("pais")
        if not pais:
            if c.get("name") not in sin_mapear:
                sin_mapear.append(c.get("name"))
            continue
        d = datos[pais]
        d["moneda"] = d["moneda"] or f["moneda"] or c.get("moneda")
        d["odoo_mensual"][f["mes"] - 1] += f["neto"]
        d["n_facturas"] += 1
        if f["tipo"] == "out_refund":
            d["n_nc"] += 1
        if c.get("name") not in d["empresas"]:
            d["empresas"].append(c.get("name"))

    if excluidas:
        avisos.add("nota", None, "alcance",
                   "Compañías excluidas del consolidado por decisión de gerencia: %s." % ", ".join(excluidas))
    if sin_mapear:
        avisos.add("critico", None, "alcance",
                   "Compañías Odoo SIN mapear a país (sus ventas no están en ningún dashboard): %s. "
                   "Revisar company_map en odoo_config.json." % ", ".join(sin_mapear))

    # historico pre-migracion
    for pais, hm in hist_cfg.items():
        if not hm:
            continue
        d = datos[pais]
        for k, v in hm.items():
            try:
                m = int(k)
            except (TypeError, ValueError):
                continue
            if not (1 <= m <= 12):
                continue
            d["hist_mensual"][m - 1] += float(v)

    # GUARDA ANTI-DOBLE-CONTEO
    for pais in ORDEN_PAISES:
        d = datos[pais]
        choques = [MESES[i] for i in range(12)
                   if d["hist_mensual"][i] and d["odoo_mensual"][i]]
        if choques:
            avisos.add("critico", pais, "ventas",
                       "DOBLE CONTEO detectado en %s: el mes tiene cifra histórica y facturas en Odoo. "
                       "Se conserva Odoo y se descarta el histórico de ese mes. Corregir "
                       "'<pais>_hist_mensual' en odoo_config.json." % ", ".join(choques))
            for i in range(12):
                if d["hist_mensual"][i] and d["odoo_mensual"][i]:
                    d["hist_mensual"][i] = 0.0
        d["mensual"] = [round(d["hist_mensual"][i] + d["odoo_mensual"][i], 2) for i in range(12)]
        d["hist_through"] = max([i + 1 for i in range(12) if d["hist_mensual"][i]] or [0])
        d["hist_amount"] = round(sum(d["hist_mensual"]), 2)
        if d["hist_amount"] and d["odoo_mensual"] != [0.0] * 12:
            d["fuente_ventas"] = "mixta (histórico pre-migración Ene-%s + Odoo desde %s)" % (
                MESES[d["hist_through"] - 1], MESES[d["hist_through"]] if d["hist_through"] < 12 else "?")
        elif d["hist_amount"]:
            d["fuente_ventas"] = "histórico pre-migración (Odoo aún sin facturas)"
        else:
            d["fuente_ventas"] = "Odoo"
        if pais == "Ecuador" and mes_corte_ec:
            d["corte_migracion"] = corte_ec
            if d["hist_mensual"][mes_corte_ec - 1]:
                avisos.add("critico", pais, "ventas",
                           "ecuador_hist_mensual incluye el mes del corte (%s): es doble conteo." % MESES[mes_corte_ec - 1])
    return datos


# =====================================================================
#  BLOQUE 2 — Margen bruto (mayor contable, por compania y por mes)
# =====================================================================
def cuentas_resultado(od, comps, avisos):
    """account.account.code es company-dependent desde Odoo 17: se lee UNA compania
    por vez, si no ~2/3 de las cuentas salen sin codigo."""
    res = {}
    for cid, c in comps.items():
        ctx = {"allowed_company_ids": [cid]}
        try:
            accts = od.sr("account.account",
                          [["account_type", "in", list(INCOME_TYPES) + list(COGS_TYPES) + ["expense"]]],
                          ["id", "code", "name", "account_type"], ctx=ctx)
        except Exception as e:
            avisos.add("alerta", c.get("pais"), "margen",
                       "No pude leer el plan de cuentas de %s: %s" % (c.get("name"), str(e)[:120]))
            res[cid] = {"income": [], "cogs": [], "rescatadas": [], "error": str(e)[:200]}
            continue
        inc = [a["id"] for a in accts if a["account_type"] in INCOME_TYPES]
        cog = [a["id"] for a in accts if a["account_type"] in COGS_TYPES]
        rescatadas = []
        if not cog:
            for a in accts:
                if a["account_type"] == "expense" and any(p in (a.get("name") or "").upper() for p in COGS_NOMBRE):
                    cog.append(a["id"])
                    rescatadas.append({"code": a.get("code"), "name": a.get("name")})
        res[cid] = {"income": inc, "cogs": cog, "rescatadas": rescatadas,
                    "n_cuentas": len(accts)}
        if rescatadas:
            avisos.add("alerta", c.get("pais"), "margen",
                       "%s no tiene ninguna cuenta tipificada como costo directo. El COGS se rescató "
                       "por NOMBRE de: %s. Corregir el tipo de cuenta en Odoo." %
                       (c.get("name"), "; ".join((r["name"] or "")[:40] for r in rescatadas)))
    return res


def _rg_balance(od, cuentas, comp_ids, desde, hasta, groupby, ctx_ids):
    if not cuentas:
        return []
    dom = [["parent_state", "=", "posted"], ["date", ">=", desde], ["date", "<=", hasta],
           ["account_id", "in", cuentas]]
    if comp_ids:
        dom.append(["company_id", "in", comp_ids])
    return od.kw("account.move.line", "read_group",
                 [dom, ["balance:sum"], groupby],
                 {"lazy": False, "context": {"allowed_company_ids": ctx_ids}})


def margen_por_pais(od, comps, cuentas, year, mes_max, avisos):
    ctx_ids = list(comps.keys())
    out = {}
    for pais in ORDEN_PAISES:
        cids = [cid for cid, c in comps.items() if c.get("pais") == pais]
        if not cids:
            continue
        inc = sorted(set(i for cid in cids for i in cuentas.get(cid, {}).get("income", [])))
        cog = sorted(set(i for cid in cids for i in cuentas.get(cid, {}).get("cogs", [])))
        moneda = comps[cids[0]].get("moneda")
        blk = {"moneda": moneda, "disponible": False, "motivo": None,
               "mensual": [], "ytd": None,
               "fuente": "account.move.line (mayor Odoo), cuentas de resultado",
               "cuentas_income": len(inc), "cuentas_cogs": len(cog)}
        if not cog:
            blk["motivo"] = ("Odoo no registra costo de ventas para %s: no existe ninguna cuenta de "
                             "costo directo con movimiento. El margen NO es calculable — no es 100%%." % pais)
            avisos.add("critico", pais, "margen", blk["motivo"] +
                       " Para tenerlo hace falta cargar el COGS (valoración de inventario o asiento de costo) en Odoo.")
            out[pais] = blk
            continue
        try:
            mensual = []
            v_ytd = c_ytd = 0.0
            for m in range(1, 13):
                if m > mes_max:
                    mensual.append({"mes": m, "venta": None, "cogs": None, "margen": None, "margen_pct": None})
                    continue
                ini = datetime.date(year, m, 1)
                fin = datetime.date(year + (m == 12), (m % 12) + 1, 1) - datetime.timedelta(days=1)
                rv = _rg_balance(od, inc, cids, ini.isoformat(), fin.isoformat(), ["company_id"], ctx_ids)
                rc = _rg_balance(od, cog, cids, ini.isoformat(), fin.isoformat(), ["company_id"], ctx_ids)
                venta = -sum(float(r.get("balance") or 0) for r in rv)
                costo = sum(float(r.get("balance") or 0) for r in rc)
                v_ytd += venta; c_ytd += costo
                mg = ((venta - costo) / venta) if venta else None
                mensual.append({"mes": m, "venta": round(venta, 2), "cogs": round(costo, 2),
                                "margen": round(venta - costo, 2),
                                "margen_pct": round(mg, 4) if mg is not None else None})
            mg_ytd = ((v_ytd - c_ytd) / v_ytd) if v_ytd else None
            blk["disponible"] = True
            blk["mensual"] = mensual
            blk["ytd"] = {"venta": round(v_ytd, 2), "cogs": round(c_ytd, 2),
                          "margen": round(v_ytd - c_ytd, 2),
                          "margen_pct": round(mg_ytd, 4) if mg_ytd is not None else None}
            # El COGS puede estar registrado en asientos puntuales (no mes a mes). En ese
            # caso el ACUMULADO es valido y el desglose mensual es ruido: un mes al 100%
            # y el siguiente en negativo. Antes que dibujar esa sierra, se declara.
            raros = [x for x in mensual if x["venta"] and x["margen_pct"] is not None
                     and (x["margen_pct"] > 0.90 or x["margen_pct"] < 0)]
            con_venta = [x for x in mensual if x["venta"]]
            blk["mensual_confiable"] = not raros
            if mg_ytd is not None and mg_ytd > 0.90:
                blk["disponible"] = False
                blk["motivo"] = ("Margen calculado %.0f%% — implausible en distribución. El costo no se está "
                                 "registrando completo. Se declara como no confiable." % (mg_ytd * 100))
                avisos.add("critico", pais, "margen", blk["motivo"])
            elif mg_ytd is not None and mg_ytd < 0:
                avisos.add("critico", pais, "margen",
                           "Margen bruto YTD NEGATIVO (%.1f%%) en %s. Revisar costeo antes de decidir." % (mg_ytd * 100, pais))
            if raros and blk["disponible"]:
                blk["motivo_mensual"] = (
                    "El COGS de %s no está mensualizado: %d mes(es) dan margen imposible (%s). "
                    "El acumulado del año sí es utilizable; la curva mensual no. Se muestra el YTD y "
                    "se oculta la sierra en vez de presentarla como tendencia." %
                    (pais, len(raros), ", ".join("%s %.0f%%" % (MESES[x["mes"] - 1], x["margen_pct"] * 100) for x in raros[:4])))
                avisos.add("alerta", pais, "margen", blk["motivo_mensual"])
            if blk["disponible"] and len(con_venta) < max(1, mes_max - 1):
                blk["cobertura_meses"] = len(con_venta)
                avisos.add("nota", pais, "margen",
                           "El mayor de %s sólo tiene movimiento de resultado en %d de %d meses (migración a Odoo). "
                           "El margen YTD compara la venta y el costo que SÍ están contabilizados, no el año calendario completo."
                           % (pais, len(con_venta), mes_max))
            if cuentas.get(cids[0], {}).get("rescatadas"):
                blk["cogs_rescatado_por_nombre"] = True
        except Exception as e:
            blk["motivo"] = "Error leyendo el mayor: %s" % str(e)[:160]
            avisos.add("alerta", pais, "margen", blk["motivo"])
        out[pais] = blk
    return out


def mix_productos(od, comps, cuentas, year, mes_cierre, avisos):
    """Venta y COGS por producto desde el mayor (lineas con product_id)."""
    ctx_ids = list(comps.keys())
    out = {}
    for pais in ORDEN_PAISES:
        cids = [cid for cid, c in comps.items() if c.get("pais") == pais]
        if not cids:
            continue
        inc = sorted(set(i for cid in cids for i in cuentas.get(cid, {}).get("income", [])))
        cog = sorted(set(i for cid in cids for i in cuentas.get(cid, {}).get("cogs", [])))
        blk = {"disponible": False, "motivo": None, "productos": [], "categorias": [],
               "moneda": comps[cids[0]].get("moneda"),
               "fuente": "account.move.line agrupado por producto (mayor Odoo)"}
        try:
            desde, hasta = "%d-01-01" % year, "%d-12-31" % year
            rv = _rg_balance(od, inc, cids, desde, hasta, ["product_id"], ctx_ids)
            venta = {}
            for r in rv:
                pid, pname = _m2o(r.get("product_id"))
                if pid is None:
                    pid, pname = 0, "(sin producto)"
                venta[pid] = {"nombre": pname, "venta": venta.get(pid, {}).get("venta", 0.0) - float(r.get("balance") or 0)}
            costo = {}
            if cog:
                rc = _rg_balance(od, cog, cids, desde, hasta, ["product_id"], ctx_ids)
                for r in rc:
                    pid, pname = _m2o(r.get("product_id"))
                    if pid is None:
                        pid, pname = 0, "(sin producto)"
                    costo[pid] = costo.get(pid, 0.0) + float(r.get("balance") or 0)
            # delta vs mes anterior
            delta = {}
            if mes_cierre >= 2:
                def _mes_rango(m):
                    ini = datetime.date(year, m, 1)
                    fin = datetime.date(year + (m == 12), (m % 12) + 1, 1) - datetime.timedelta(days=1)
                    return ini.isoformat(), fin.isoformat()
                for m, key in ((mes_cierre, "act"), (mes_cierre - 1, "ant")):
                    a, b = _mes_rango(m)
                    for r in _rg_balance(od, inc, cids, a, b, ["product_id"], ctx_ids):
                        pid, _n = _m2o(r.get("product_id"))
                        pid = pid if pid is not None else 0
                        delta.setdefault(pid, {"act": 0.0, "ant": 0.0})[key] -= float(r.get("balance") or 0)
            blk["delta_meses"] = [mes_cierre - 1, mes_cierre] if mes_cierre >= 2 else None
            total = sum(v["venta"] for v in venta.values()) or 0.0
            prods = []
            sin_producto = 0.0
            for pid, v in venta.items():
                if pid == 0:
                    sin_producto += v["venta"]
                cst = costo.get(pid)
                mg = (v["venta"] - cst) if cst is not None else None
                d = delta.get(pid) or {}
                prods.append({
                    "id": pid, "nombre": v["nombre"],
                    "venta": round(v["venta"], 2),
                    "cogs": round(cst, 2) if cst is not None else None,
                    "margen": round(mg, 2) if mg is not None else None,
                    "margen_pct": round(mg / v["venta"], 4) if (mg is not None and v["venta"]) else None,
                    "pct_total": round(v["venta"] / total, 4) if total else None,
                    # Si el producto no tuvo venta en NINGUNO de los dos meses comparados,
                    # el delta no es una caida: es que no hubo operacion. Se deja vacio.
                    "delta_mes": (round(d.get("act", 0.0) - d.get("ant", 0.0), 2)
                                  if (d and (d.get("act") or d.get("ant"))) else None),
                })
            prods.sort(key=lambda p: -(p["venta"] or 0))
            blk["productos"] = prods[:TOP_PRODUCTOS]
            blk["n_productos"] = len(prods)
            blk["venta_total"] = round(total, 2)
            blk["disponible"] = bool(prods)
            blk["cogs_por_producto"] = bool(costo)
            if not costo:
                blk["motivo_cogs"] = ("Las cuentas de costo no llevan producto en el asiento: se puede ver el MIX de "
                                      "venta por producto, pero no el margen por producto.")
                avisos.add("alerta", pais, "mix",
                           "%s: no hay COGS a nivel de producto. El ranking se ordena por venta, no por margen aportado." % pais)
            if sin_producto and total and abs(sin_producto / total) > 0.10:
                avisos.add("alerta", pais, "mix",
                           "%s: %.0f%% de la venta del mayor no tiene producto asignado en el asiento; "
                           "el mix por producto es parcial." % (pais, 100.0 * sin_producto / total))
            if not prods:
                blk["motivo"] = "El mayor no devolvió ventas con producto para %s." % pais
        except Exception as e:
            blk["motivo"] = "Error leyendo el mix: %s" % str(e)[:160]
            avisos.add("alerta", pais, "mix", blk["motivo"])
        out[pais] = blk
    return out


# =====================================================================
#  BLOQUE 3 — Cartera / aging / DSO
# =====================================================================
def clasificar_doc(nombre):
    n = (nombre or "").upper().strip()
    if not n:
        return "otro"
    if n.startswith(("RNC", "NC", "RC")):
        return "nota_credito"
    if "MISC" in n or n.startswith(("CE", "TEF", "BNK", "CSH", "PAY")):
        return "ajuste_o_pago"
    if n.startswith(("FE", "FV", "INV", "FAC", "001", "002")):
        return "factura"
    return "otro"


BUCKETS = ["Corriente", "1-30", "31-60", "61-90", ">90"]


def bucket_de(dias):
    if dias <= 0:
        return "Corriente"
    if dias <= 30:
        return "1-30"
    if dias <= 60:
        return "31-60"
    if dias <= 90:
        return "61-90"
    return ">90"


def cartera_por_pais(od, comps, hoy, avisos):
    ctx_ids = list(comps.keys())
    out = {}
    for pais in ORDEN_PAISES:
        cids = [cid for cid, c in comps.items() if c.get("pais") == pais]
        if not cids:
            continue
        blk = {"disponible": False, "motivo": None, "moneda": comps[cids[0]].get("moneda"),
               "fuente": "account.move.line (cuentas por cobrar abiertas). No se consulta account.move: "
                         "el módulo l10n_ec incompleto lo hace reventar.",
               "corte": hoy.isoformat()}
        base = [["parent_state", "=", "posted"], ["company_id", "in", cids],
                ["reconciled", "=", False], ["amount_residual", "!=", 0]]
        dom = None
        for cond in (["account_id.account_type", "=", "asset_receivable"],
                     ["account_id.internal_type", "=", "receivable"]):
            try:
                od.sr("account.move.line", base + [cond], ["id"], limit=1,
                      ctx={"allowed_company_ids": ctx_ids})
                dom = base + [cond]
                break
            except Exception:
                continue
        if dom is None:
            blk["motivo"] = "No pude identificar la cuenta por cobrar en Odoo para %s." % pais
            avisos.add("alerta", pais, "cartera", blk["motivo"])
            out[pais] = blk
            continue
        try:
            campos = ["id", "move_name", "date", "date_maturity", "amount_residual", "partner_id"]
            lineas, omitidos = od.sr_drop("account.move.line", dom, campos,
                                          ctx={"allowed_company_ids": ctx_ids})
        except Exception as e:
            blk["motivo"] = "Error leyendo cartera: %s" % str(e)[:160]
            avisos.add("alerta", pais, "cartera", blk["motivo"])
            out[pais] = blk
            continue

        filas, ruido = [], 0
        umbral = 1000.0 if blk["moneda"] == "COP" else 1.0
        for l in lineas:
            saldo = float(l.get("amount_residual") or 0)
            if abs(saldo) < umbral:
                ruido += 1
                continue
            venc = l.get("date_maturity") or l.get("date")
            try:
                v = datetime.date.fromisoformat(str(venc)[:10])
            except Exception:
                v = None
            _pid, pname = _m2o(l.get("partner_id"))
            filas.append({"doc": l.get("move_name") or "", "tipo": clasificar_doc(l.get("move_name")),
                          "cliente": pname or "(sin cliente)", "fecha": str(l.get("date") or "")[:10],
                          "vence": str(venc or "")[:10],
                          "dias": (hoy - v).days if v else 0, "saldo": round(saldo, 2)})
        total = sum(f["saldo"] for f in filas)
        by_bucket = dict((b, 0.0) for b in BUCKETS)
        for f in filas:
            by_bucket[bucket_de(f["dias"])] += f["saldo"]
        vencido = sum(v for k, v in by_bucket.items() if k != "Corriente")
        vencido_30 = sum(v for k, v in by_bucket.items() if k in ("31-60", "61-90", ">90"))

        porcliente = {}
        for f in filas:
            c = porcliente.setdefault(f["cliente"], {
                "cliente": f["cliente"], "saldo": 0.0, "vencido": 0.0,
                "buckets": dict((b, 0.0) for b in BUCKETS),
                "dias_pond": 0.0, "mas_antigua": None, "mas_antigua_dias": 0, "n_docs": 0})
            c["saldo"] += f["saldo"]; c["n_docs"] += 1
            c["buckets"][bucket_de(f["dias"])] += f["saldo"]
            if f["dias"] > 0:
                c["vencido"] += f["saldo"]
                if f["saldo"] > 0 and f["dias"] > c["mas_antigua_dias"]:
                    c["mas_antigua"] = f["doc"]; c["mas_antigua_dias"] = f["dias"]
            if f["saldo"] > 0:
                c["dias_pond"] += f["saldo"] * max(f["dias"], 0)
        clientes = []
        for c in porcliente.values():
            base_pond = sum(v for v in [c["saldo"]] if v > 0) or 0
            c["dias_promedio"] = round(c["dias_pond"] / base_pond, 1) if base_pond else None
            c["pct_vencido"] = round(c["vencido"] / c["saldo"], 4) if c["saldo"] else None
            c.pop("dias_pond", None)
            for b in BUCKETS:
                c["buckets"][b] = round(c["buckets"][b], 2)
            c["saldo"] = round(c["saldo"], 2); c["vencido"] = round(c["vencido"], 2)
            clientes.append(c)
        clientes.sort(key=lambda x: -x["saldo"])

        blk.update({
            "disponible": True,
            "total": round(total, 2),
            "buckets": dict((b, round(by_bucket[b], 2)) for b in BUCKETS),
            "vencido": round(vencido, 2),
            "pct_vencido": round(vencido / total, 4) if total else None,
            "vencido_mas_30": round(vencido_30, 2),
            "pct_vencido_mas_30": round(vencido_30 / total, 4) if total else None,
            "n_documentos": len(filas), "residuos_excluidos": ruido,
            "campos_omitidos": omitidos,
            "clientes": clientes[:TOP_CLIENTES],
            "n_clientes": len(clientes),
        })
        if omitidos:
            avisos.add("nota", pais, "cartera",
                       "Odoo rechazó estos campos y se omitieron: %s." % ", ".join(omitidos))
        if not filas:
            blk["disponible"] = False
            blk["motivo"] = "Odoo no devuelve cuentas por cobrar abiertas para %s. Puede ser real (todo cobrado) " \
                            "o que la contabilidad aún no esté cargada — verificar antes de leerlo como buena noticia." % pais
            avisos.add("alerta", pais, "cartera", blk["motivo"])
        out[pais] = blk
    return out


def dso_y_cobranza(od, comps, year, hoy, ventas, cartera, avisos):
    """DSO puntual + comportamiento de pago real (ponderado por monto conciliado)."""
    ctx_ids = list(comps.keys())
    out = {}
    for pais in ORDEN_PAISES:
        cids = [cid for cid, c in comps.items() if c.get("pais") == pais]
        if not cids:
            continue
        blk = {"dso_puntual": None, "dias_pago_real": None, "base_conciliada": None,
               "metodo": "DSO puntual = cartera al corte / venta neta del periodo x días del periodo. "
                         "No hay fotos históricas de cartera, así que NO es un promedio: es un puntual.",
               "disponible": False}
        car = (cartera.get(pais) or {})
        v = ventas.get(pais) or {}
        mensual = v.get("mensual") or [0.0] * 12
        # ventana: ultimos 90 dias naturales del anio en curso
        mes_hoy = hoy.month if hoy.year == year else 12
        ini = max(1, mes_hoy - 2)
        venta_periodo = sum(mensual[ini - 1:mes_hoy])
        dias_periodo = (hoy - datetime.date(year, ini, 1)).days + 1 if hoy.year == year else 365
        if car.get("disponible") and venta_periodo > 0:
            blk["dso_puntual"] = round((car.get("total") or 0) / venta_periodo * dias_periodo, 1)
            blk["ventana"] = "%s-%s %d (%d días)" % (MESES[ini - 1], MESES[mes_hoy - 1], year, dias_periodo)
            blk["disponible"] = True
        elif not car.get("disponible"):
            blk["motivo"] = "Sin cartera no hay DSO."
        else:
            blk["motivo"] = "Venta del período = 0: el DSO no está definido."
        # comportamiento de pago real
        try:
            desde = (hoy - datetime.timedelta(days=365)).isoformat()
            dom = [["parent_state", "=", "posted"], ["company_id", "in", cids],
                   ["account_id.account_type", "=", "asset_receivable"],
                   ["debit", ">", 0], ["date", ">=", desde]]
            hist, _ = od.sr_drop("account.move.line", dom,
                                 ["id", "move_name", "date", "date_maturity", "debit"],
                                 ctx={"allowed_company_ids": ctx_ids})
            hmap = dict((l["id"], l) for l in hist)
            ids = list(hmap.keys())
            partials = []
            for i in range(0, len(ids), 400):
                try:
                    partials += od.sr("account.partial.reconcile",
                                      [["debit_move_id", "in", ids[i:i + 400]]],
                                      ["debit_move_id", "amount", "max_date"],
                                      ctx={"allowed_company_ids": ctx_ids})
                except Exception:
                    break
            num = den = 0.0
            for p in partials:
                li = (p.get("debit_move_id") or [None])[0]
                l = hmap.get(li)
                if not l:
                    continue
                amt = float(p.get("amount") or 0)
                try:
                    fp = datetime.date.fromisoformat(str(p.get("max_date"))[:10])
                    fv = datetime.date.fromisoformat(str(l.get("date_maturity") or l.get("date"))[:10])
                except Exception:
                    continue
                if amt <= 0:
                    continue
                num += amt * (fp - fv).days; den += amt
            if den:
                blk["dias_pago_real"] = round(num / den, 1)
                blk["base_conciliada"] = round(den, 2)
                blk["n_conciliaciones"] = len(partials)
        except Exception as e:
            avisos.add("nota", pais, "cartera",
                       "No pude calcular el comportamiento de pago real de %s: %s" % (pais, str(e)[:110]))
        out[pais] = blk
    return out


# =====================================================================
#  BLOQUE 4 — Clientes y concentracion
# =====================================================================
def clientes_y_hhi(facturas, facturas_prev, comps, ventas, avisos, year, ytd_por_pais=None):
    out = {}
    porpais = defaultdict(lambda: defaultdict(float))
    porpais_prev = defaultdict(lambda: defaultdict(float))
    for f in facturas:
        c = comps.get(f["empresa_id"]) or {}
        if c.get("excluida") or not c.get("pais"):
            continue
        porpais[c["pais"]][f["cliente"]] += f["neto"]
    for f in (facturas_prev or []):
        c = comps.get(f["empresa_id"]) or {}
        if c.get("excluida") or not c.get("pais"):
            continue
        porpais_prev[c["pais"]][f["cliente"]] += f["neto"]

    nucleos = nucleos_grupo(comps)
    for pais in ORDEN_PAISES:
        v = ventas.get(pais) or {}
        base_odoo = sum(v.get("odoo_mensual") or [0.0])
        ytd = (ytd_por_pais or {}).get(pais)
        d = porpais.get(pais) or {}
        total = sum(x for x in d.values() if x > 0) or sum(d.values())
        blk = {"disponible": bool(d), "moneda": v.get("moneda"),
               "base": "facturación registrada en Odoo del año %d, incluido el mes en curso" % year,
               "base_odoo": round(base_odoo, 2), "ytd_pais": ytd,
               "cobertura_pct": round(base_odoo / ytd, 4) if ytd else None,
               "clientes": [], "hhi": None, "top1_pct": None, "top5_pct": None}
        if not d:
            blk["motivo"] = "Sin facturas en Odoo para %s en %d." % (pais, year)
            out[pais] = blk
            continue
        filas = []
        prev = porpais_prev.get(pais) or {}
        for nombre, monto in d.items():
            share = (monto / total) if total else 0
            p = prev.get(nombre)
            ic = es_intercompania(nombre, nucleos)
            filas.append({"cliente": nombre, "venta": round(monto, 2),
                          "pct": round(share, 4),
                          "intercompania": bool(ic), "intercompania_con": ic,
                          "venta_aa": round(p, 2) if p is not None else None,
                          "delta_aa": round((monto - p) / abs(p), 4) if p else None})
        filas.sort(key=lambda x: -x["venta"])
        ic_total = sum(f["venta"] for f in filas if f["intercompania"])
        blk["venta_intercompania"] = round(ic_total, 2)
        blk["pct_intercompania"] = round(ic_total / total, 4) if total else None
        terceros = [f for f in filas if not f["intercompania"]]
        t3 = sum(f["venta"] for f in terceros if f["venta"] > 0) or 1
        blk["hhi_terceros"] = round(sum(((f["venta"] / t3) * 100) ** 2 for f in terceros if f["venta"] > 0), 0)
        if ic_total and (blk["pct_intercompania"] or 0) >= 0.005:
            avisos.add("alerta", pais, "clientes",
                       "%s de la venta registrada de %s es INTERCOMPAÑÍA (%s): no es venta a terceros ni "
                       "cartera de mercado. El HHI de terceros, sin ella, es %d." %
                       ("{:.0f}%".format(blk["pct_intercompania"] * 100), pais,
                        ", ".join(sorted(set(f["intercompania_con"] for f in filas if f["intercompania"]))),
                        blk["hhi_terceros"]))
        hhi = sum((f["pct"] * 100) ** 2 for f in filas if f["pct"] > 0)
        blk["clientes"] = filas[:TOP_CLIENTES]
        blk["n_clientes"] = len(filas)
        blk["hhi"] = round(hhi, 0)
        blk["top1_pct"] = filas[0]["pct"] if filas else None
        blk["top5_pct"] = round(sum(f["pct"] for f in filas[:5]), 4)
        blk["critico"] = hhi > HHI_CRITICO
        if hhi > HHI_CRITICO:
            blk["lectura"] = ("HHI %d (>%d = concentración crítica). %s pesa %.0f%% de la venta de %s: "
                              "si ese cliente se va o renegocia, el país no tiene con qué reemplazarlo en el año." %
                              (hhi, HHI_CRITICO, filas[0]["cliente"][:34], filas[0]["pct"] * 100, pais))
            avisos.add("alerta", pais, "concentración", blk["lectura"])
        else:
            blk["lectura"] = "HHI %d. Concentración dentro de rango manejable para %s." % (hhi, pais)
        if blk["cobertura_pct"] is not None and blk["cobertura_pct"] < 0.95:
            nivel = "critico" if blk["cobertura_pct"] < 0.35 else "alerta"
            avisos.add(nivel, pais, "concentración",
                       "El desglose por cliente sólo cubre el %.0f%% del YTD de %s: el resto viene del histórico "
                       "pre-migración, que no trae cliente. El HHI y el top de clientes describen ESE %.0f%%, "
                       "no el año completo — no los leas como la foto anual." %
                       (blk["cobertura_pct"] * 100, pais, blk["cobertura_pct"] * 100))
        if not any(f.get("venta_aa") is not None for f in filas):
            avisos.add("nota", pais, "clientes",
                       "Sin comparativo contra %d: Odoo no tiene facturas de ese año para %s (la operación "
                       "anterior vivía en otra instancia/ERP). La columna Δ vs año anterior queda vacía a propósito."
                       % (year - 1, pais))
        out[pais] = blk
    return out


def cruce_venta_cobro(facturas, comps, cartera, hoy, year):
    """Clientes que crecen en venta y hoy tienen cartera deteriorada."""
    out = {}
    v3 = defaultdict(lambda: defaultdict(float))
    v3p = defaultdict(lambda: defaultdict(float))
    m_hoy = hoy.month if hoy.year == year else 12
    act = set(range(max(1, m_hoy - 2), m_hoy + 1))
    ant = set(range(max(1, m_hoy - 5), max(1, m_hoy - 2)))
    for f in facturas:
        c = comps.get(f["empresa_id"]) or {}
        if c.get("excluida") or not c.get("pais"):
            continue
        if f["mes"] in act:
            v3[c["pais"]][f["cliente"]] += f["neto"]
        elif f["mes"] in ant:
            v3p[c["pais"]][f["cliente"]] += f["neto"]
    for pais in ORDEN_PAISES:
        car = cartera.get(pais) or {}
        if not car.get("disponible"):
            continue
        idx = dict((c["cliente"], c) for c in car.get("clientes") or [])
        filas = []
        for cli, monto in (v3.get(pais) or {}).items():
            prev = (v3p.get(pais) or {}).get(cli, 0.0)
            c = idx.get(cli)
            if not c or not c.get("pct_vencido"):
                continue
            # Un cliente NUEVO (base previa cero) no "crece y se deteriora": simplemente
            # todavia no ha pagado su primera factura. Exigir base previa material evita
            # el falso positivo que hace ruido en el panel.
            if not (prev > 0):
                continue
            crec = (monto - prev) / prev
            if crec > 0.10 and c["pct_vencido"] > 0.25:
                filas.append({"cliente": cli, "venta_3m": round(monto, 2),
                              "venta_3m_prev": round(prev, 2), "crecimiento": round(crec, 4),
                              "saldo": c["saldo"], "pct_vencido": c["pct_vencido"],
                              "dias_promedio": c.get("dias_promedio")})
        filas.sort(key=lambda x: -x["saldo"])
        if filas:
            out[pais] = filas[:8]
    return out


# =====================================================================
#  Ensamblado del contrato JSON
# =====================================================================
def _norm(txt):
    import unicodedata
    t = unicodedata.normalize("NFKD", str(txt or "")).encode("ascii", "ignore").decode("ascii").upper()
    for basura in (" S.A.S.", " S.A.S", " SAS", " S.A.", " S.A", " CIA. LTDA.", " CIA LTDA",
                   " LTDA", " SOCIEDAD ANONIMA", " SOCIEDAD DE RESPONSABILIDAD LIMITADA",
                   " SRL", " C.A.", " CA", "."):
        t = t.replace(basura, " ")
    return " ".join(t.split())


def nucleos_grupo(comps):
    """Nombres normalizados de las companias del grupo, para detectar ventas intercompania.

    Un cliente que ES otra compania del grupo no es concentracion comercial ni cartera de
    terceros: es plata que se debe a si misma. Contarlo como venta a cliente infla el mix
    y disfraza el riesgo real.
    """
    out = {}
    for c in comps.values():
        n = _norm(c.get("name"))
        if len(n) >= 4:
            out[n.split(" ")[0]] = c.get("name")
    return out


def es_intercompania(nombre_cliente, nucleos):
    n = _norm(nombre_cliente)
    for k, orig in nucleos.items():
        if len(k) >= 4 and (n == k or n.startswith(k + " ") or (" " + k + " ") in (" " + n + " ")):
            return orig
    return None


def serie_historica(pais):
    """Serie diaria de cartera/DSO reconstruida de las corridas anteriores.

    Odoo no guarda fotos de cartera pasada. En vez de estimarla, cada corrida deja
    su propio snapshot en OdooVentas/historico/ y la serie se arma con eso: el
    dashboard empieza sin tendencia y la gana con el uso. Es un hueco declarado,
    no un dato inventado.
    """
    hist = OUT_DIR / "historico"
    if not hist.exists():
        return []
    out = []
    for f in sorted(hist.glob("dashboard_ventas_*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        p = (d.get("paises") or {}).get(pais)
        if not p:
            continue
        car = p.get("cartera") or {}
        ds = p.get("dso") or {}
        out.append({"fecha": d.get("generado_fecha"),
                    "cartera": car.get("total") if car.get("disponible") else None,
                    "pct_vencido": car.get("pct_vencido") if car.get("disponible") else None,
                    "dso": ds.get("dso_puntual"),
                    "ytd": p.get("ytd_real")})
    vistos, limpio = set(), []
    for x in out:
        if x["fecha"] in vistos:
            continue
        vistos.add(x["fecha"]); limpio.append(x)
    return limpio[-120:]


def _respaldo_estado():
    return OUT_DIR / "estado_grupo_ultimo_bueno.json"


def leer_estado_grupo(avisos):
    """Presupuesto de referencia, con red de seguridad.

    El agente com.vcomer.presupuesto sobrescribe estado_grupo.json con un documento
    VACIO cuando corre sin red (Mac dormida). Verificado el 2026-09-10: quedo en
    paises:[] . Para que eso no borre el presupuesto del dashboard, cada vez que se lee
    un estado_grupo con datos se guarda una copia, y si el del dia viene vacio se usa la
    copia declarando su antiguedad. Un presupuesto viejo con fecha visible es utilizable;
    ninguno, no.
    """
    f = PPTO_DIR / "estado_grupo.json"
    if not f.exists():
        avisos.add("alerta", None, "presupuesto",
                   "No existe PresupuestoAuto/estado_grupo.json: sin presupuesto de referencia. "
                   "Corre estado_grupo.py o revisa el agente com.vcomer.presupuesto.")
        return {}
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception as e:
        avisos.add("alerta", None, "presupuesto", "estado_grupo.json ilegible: %s" % e)
        return {}
    if not (d.get("paises") or {}):
        resp = _respaldo_estado()
        if resp.exists():
            try:
                r = json.loads(resp.read_text(encoding="utf-8"))
                if (r.get("paises") or {}):
                    avisos.add("alerta", None, "presupuesto",
                               "estado_grupo.json vino VACÍO (el agente com.vcomer.presupuesto corrió sin red y lo "
                               "sobrescribió el %s). Se usa el último respaldo con datos, del %s: el presupuesto "
                               "que ves tiene esa fecha, no la de hoy. Correr estado_grupo.py con conexión lo arregla."
                               % (d.get("generado"), r.get("generado")))
                    r["_desde_respaldo"] = True
                    return r
            except Exception:
                pass
        avisos.add("critico", None, "presupuesto",
                   "estado_grupo.json existe pero vino VACÍO (el agente corrió sin red y se sobrescribió) y no hay "
                   "respaldo previo. Sin presupuesto de referencia hasta que estado_grupo.py corra con conexión.")
        return {}
    try:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        _respaldo_estado().write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    try:
        gen = datetime.datetime.fromisoformat(d.get("generado"))
        dias = (datetime.datetime.now() - gen).days
        if dias >= 2:
            avisos.add("alerta", None, "presupuesto",
                       "El presupuesto de referencia (estado_grupo.json) tiene %d días de antigüedad "
                       "(generado %s). El real es de hoy; el presupuesto puede estar desfasado." % (dias, d.get("generado")))
    except Exception:
        pass
    return d


def a_usd(valor, moneda, tc):
    if valor is None:
        return None
    t = (tc.get("tasas") or {}).get(moneda)
    if t is None:
        return None
    return round(float(valor) * t, 2)


def construir(od, year, avisos, hoy=None):
    hoy = hoy or datetime.date.today()
    cfg_raw = od.cfg.get("_raw") or {}
    company_map = cfg_raw.get("company_map") or {}
    tc = load_tc()
    eg = leer_estado_grupo(avisos)
    mes_actual = hoy.month if hoy.year == year else 12
    mes_cierre = eg.get("mes_cierre") or (max(mes_actual - 1, 1) if hoy.year == year else 12)

    log("Compañías...")
    comps = companias(od, company_map)
    for cid, c in comps.items():
        log("  [%s] %-45s %-4s -> %s" % (cid, (c["name"] or "")[:45], c["moneda"],
                                         "EXCLUIDA" if c["excluida"] else (c["pais"] or "SIN MAPEAR")))

    log("Facturas %d..." % year)
    facturas = fetch_facturas(od, year, list(comps.keys()))
    log("  %d documentos" % len(facturas))
    try:
        facturas_prev = fetch_facturas(od, year - 1, list(comps.keys()))
        log("  %d documentos de %d (comparativo)" % (len(facturas_prev), year - 1))
    except Exception as e:
        facturas_prev = []
        avisos.add("nota", None, "clientes", "Sin comparativo %d: %s" % (year - 1, str(e)[:110]))

    ventas = ventas_por_pais(facturas, comps, cfg_raw, year, avisos)

    # presupuesto
    ppto_mensual = presupuesto_mensual(eg, avisos)

    log("Plan de cuentas / margen...")
    cuentas = cuentas_resultado(od, comps, avisos)
    margen = margen_por_pais(od, comps, cuentas, year, mes_actual, avisos)
    log("Mix de producto...")
    mix = mix_productos(od, comps, cuentas, year, mes_cierre, avisos)
    log("Cartera...")
    cartera = cartera_por_pais(od, comps, hoy, avisos)
    dso = dso_y_cobranza(od, comps, year, hoy, ventas, cartera, avisos)
    log("Clientes y concentración...")
    # La cobertura se mide contra la MISMA ventana que el ranking de clientes: todo el
    # ano corrido incluido el mes en curso. Compararla contra el YTD a mes cerrado daba
    # coberturas > 100% en los paises cuya unica venta esta en el mes abierto.
    ytd_prelim = dict((k, round(sum((ventas[k]["mensual"])[:mes_actual]), 2)) for k in ventas)
    clientes = clientes_y_hhi(facturas, facturas_prev, comps, ventas, avisos, year, ytd_prelim)
    cruce = cruce_venta_cobro(facturas, comps, cartera, hoy, year)

    dias_mes = (datetime.date(year + (mes_actual == 12), (mes_actual % 12) + 1, 1) -
                datetime.timedelta(days=1)).day
    dia_hoy = hoy.day if (hoy.year == year and hoy.month == mes_actual) else dias_mes

    paises = {}
    for pais in ORDEN_PAISES:
        v = ventas.get(pais)
        if not v:
            continue
        egp = (eg.get("paises") or {}).get(pais) or {}
        mensual = v["mensual"]
        ytd_real = round(sum(mensual[:mes_cierre]), 2)
        ppto_ytd = egp.get("ppto_ytd")
        ppto_anual = egp.get("ppto_anual")
        pm = ppto_mensual.get(pais)
        ppto_curva = pm["mensual"] if pm else None
        mtd_real = round(mensual[mes_actual - 1], 2) if mes_actual <= 12 else 0.0
        mtd_ppto = ppto_curva[mes_actual - 1] if ppto_curva else None
        moneda = v["moneda"] or egp.get("moneda") or "USD"
        run_rate = round(ytd_real / mes_cierre * 12, 2) if mes_cierre else None

        paises[pais] = {
            "moneda": moneda,
            "mensual": mensual,
            "mensual_odoo": [round(x, 2) for x in v["odoo_mensual"]],
            "mensual_hist": [round(x, 2) for x in v["hist_mensual"]],
            "hist_through": v["hist_through"], "hist_amount": v["hist_amount"],
            "corte_migracion": v.get("corte_migracion"),
            "fuente_ventas": v["fuente_ventas"],
            "empresas": v["empresas"], "n_facturas": v["n_facturas"], "n_nc": v["n_nc"],
            "mes_cierre": mes_cierre, "mes_actual": mes_actual,
            "ytd_real": ytd_real,
            "ppto_ytd": ppto_ytd,
            "cumpl_ytd": round(ytd_real / ppto_ytd, 4) if ppto_ytd else None,
            "var_ytd": round(ytd_real - ppto_ytd, 2) if ppto_ytd is not None else None,
            "ppto_anual": ppto_anual,
            "ppto_mensual": ppto_curva,
            "ppto_mensual_meta": dict((k, pm[k]) for k in ("hoja", "fila", "etiqueta", "fuente", "error_relativo")) if pm else None,
            "avance_anual": round(ytd_real / ppto_anual, 4) if ppto_anual else None,
            "run_rate_anual": run_rate,
            "run_rate_vs_ppto": round(run_rate / ppto_anual, 4) if (run_rate and ppto_anual) else None,
            "mtd": {"mes": mes_actual, "real": mtd_real, "ppto": mtd_ppto,
                    "cumpl": round(mtd_real / mtd_ppto, 4) if mtd_ppto else None,
                    "dia": dia_hoy, "dias_mes": dias_mes,
                    "avance_calendario": round(float(dia_hoy) / dias_mes, 4)},
            "margen": margen.get(pais),
            "mix": mix.get(pais),
            "cartera": cartera.get(pais),
            "dso": dso.get(pais),
            "clientes": clientes.get(pais),
            "cruce_venta_cobro": cruce.get(pais) or [],
            "serie_historica": serie_historica(pais),
            "usd": {},
        }
        p = paises[pais]
        p["usd"] = {"ytd_real": a_usd(ytd_real, moneda, tc),
                    "ppto_ytd": a_usd(ppto_ytd, moneda, tc),
                    "ppto_anual": a_usd(ppto_anual, moneda, tc),
                    "cartera": a_usd((cartera.get(pais) or {}).get("total"), moneda, tc)
                    if (cartera.get(pais) or {}).get("disponible") else None,
                    "mensual": [a_usd(x, moneda, tc) for x in mensual],
                    "referencial": True}

    # ---------------- consolidado ----------------
    real = sum(p["usd"]["ytd_real"] or 0 for p in paises.values())
    ppto = sum(p["usd"]["ppto_ytd"] or 0 for p in paises.values())
    anual = sum(p["usd"]["ppto_anual"] or 0 for p in paises.values())
    mensual_usd = [round(sum((p["usd"]["mensual"][i] or 0) for p in paises.values()), 2) for i in range(12)]
    comp = []
    for pais, p in paises.items():
        share = (p["usd"]["ytd_real"] or 0) / real if real else 0
        comp.append({"pais": pais, "usd": p["usd"]["ytd_real"], "pct": round(share, 4),
                     "moneda": p["moneda"], "local": p["ytd_real"],
                     "cumpl": p["cumpl_ytd"],
                     "margen_pct": ((p["margen"] or {}).get("ytd") or {}).get("margen_pct")
                     if (p["margen"] or {}).get("disponible") else None,
                     "dso": (p["dso"] or {}).get("dso_puntual"),
                     "hhi": (p["clientes"] or {}).get("hhi"),
                     "desviacion_usd": round((p["usd"]["ytd_real"] or 0) - (p["usd"]["ppto_ytd"] or 0), 2)})
    comp.sort(key=lambda x: -(x["usd"] or 0))
    desv_total = sum(abs(c["desviacion_usd"]) for c in comp) or 1
    for c in comp:
        c["pct_desviacion"] = round(abs(c["desviacion_usd"]) / desv_total, 4)
        if c["pct"] > 0.60:
            avisos.add("alerta", None, "consolidado",
                       "%s concentra el %.0f%% de la venta del grupo (USD referencial): el grupo es, en la práctica, "
                       "ese país." % (c["pais"], c["pct"] * 100))
        if c["pct_desviacion"] > 0.60:
            avisos.add("alerta", None, "consolidado",
                       "%s explica el %.0f%% de la desviación total contra presupuesto del grupo." %
                       (c["pais"], c["pct_desviacion"] * 100))

    ranking = sorted([c for c in comp if c["cumpl"] is not None], key=lambda x: -(x["cumpl"] or 0))

    consolidado = {
        "moneda": "USD", "referencial": True,
        "ytd_real": round(real, 2), "ppto_ytd": round(ppto, 2),
        "cumpl_ytd": round(real / ppto, 4) if ppto else None,
        "var_ytd": round(real - ppto, 2),
        "ppto_anual": round(anual, 2),
        "avance_anual": round(real / anual, 4) if anual else None,
        "run_rate_anual": round(real / mes_cierre * 12, 2) if mes_cierre else None,
        "mensual": mensual_usd,
        "mtd": {"mes": mes_actual,
                "real": round(sum(a_usd(p["mtd"]["real"], p["moneda"], tc) or 0 for p in paises.values()), 2)},
        "composicion": comp,
        "ranking_cumplimiento": ranking,
        "hhi_grupo": None,
    }
    # HHI del grupo: clientes de todos los paises, en USD referencial
    agg = defaultdict(float)
    for pais, p in paises.items():
        cl = p.get("clientes") or {}
        for c in (cl.get("clientes") or []):
            u = a_usd(c["venta"], p["moneda"], tc)
            if u:
                agg[c["cliente"]] += u
    tot = sum(v for v in agg.values() if v > 0)
    if tot:
        consolidado["hhi_grupo"] = round(sum(((v / tot) * 100) ** 2 for v in agg.values() if v > 0), 0)
        top = sorted(agg.items(), key=lambda x: -x[1])[:10]
        consolidado["top_clientes_grupo"] = [{"cliente": k, "usd": round(v, 2), "pct": round(v / tot, 4)} for k, v in top]
        consolidado["nota_hhi"] = ("HHI calculado sobre los top-%d clientes de cada país en USD referencial; "
                                   "es un piso, no el HHI exacto del universo completo." % TOP_CLIENTES)

    doc = {
        "generado": datetime.datetime.now().isoformat(timespec="seconds"),
        "generado_fecha": hoy.isoformat(),
        "anio": year,
        "mes_cierre": mes_cierre,
        "mes_actual": mes_actual,
        "meses": MESES,
        "tc": tc,
        "fuentes": {
            "ventas": "Odoo XML-RPC account.move (out_invoice + out_refund, posted, amount_untaxed_signed)"
                      " + histórico pre-migración de odoo_config.json",
            "presupuesto": "PresupuestoAuto/estado_grupo.json (YTD/anual) + libro Regional (curva mensual)",
            "margen": "Odoo account.move.line sobre cuentas de resultado",
            "cartera": "Odoo account.move.line, cuentas por cobrar abiertas",
            "estado_grupo_generado": eg.get("generado"),
        },
        "paises": paises,
        "consolidado": consolidado,
        "avisos": avisos.dump(),
        "odoo": {"url": od.cfg.get("url"), "db": od.cfg.get("db"), "llamadas": od.calls},
        "excluidas": [c["name"] for c in comps.values() if c["excluida"]],
        "conciliacion": conciliacion(paises, eg, cfg_raw),
    }
    return doc


def conciliacion(paises, eg, cfg_raw):
    """Cuadre linea por linea contra estado_grupo.json y los historicos."""
    filas = []
    for pais, p in paises.items():
        egp = (eg.get("paises") or {}).get(pais) or {}
        ref = egp.get("ytd_real")
        dif = round(p["ytd_real"] - ref, 2) if ref is not None else None
        filas.append({"pais": pais, "concepto": "YTD real vs estado_grupo.json",
                      "dashboard": p["ytd_real"], "referencia": ref, "diferencia": dif,
                      "cuadra": (dif is not None and abs(dif) < 0.01),
                      "nota": None if ref is not None else "estado_grupo.json no trae este país."})
        clave = {"Ecuador": "ecuador_hist_mensual", "Colombia": "colombia_hist_mensual"}.get(pais)
        if clave and cfg_raw.get(clave):
            esperado = round(sum(float(v) for v in cfg_raw[clave].values()), 2)
            d2 = round(p["hist_amount"] - esperado, 2)
            filas.append({"pais": pais, "concepto": "Histórico pre-migración vs %s" % clave,
                          "dashboard": p["hist_amount"], "referencia": esperado, "diferencia": d2,
                          "cuadra": abs(d2) < 0.01, "nota": None})
        if p.get("ppto_mensual"):
            s = round(sum(p["ppto_mensual"]), 2)
            ref2 = p.get("ppto_anual")
            d3 = round(s - ref2, 2) if ref2 else None
            filas.append({"pais": pais, "concepto": "Curva mensual de presupuesto vs presupuesto anual",
                          "dashboard": s, "referencia": ref2, "diferencia": d3,
                          "cuadra": (d3 is not None and abs(d3) <= abs(ref2 or 1) * 0.01), "nota": None})
    return {"generado": datetime.datetime.now().isoformat(timespec="seconds"), "filas": filas,
            "todo_cuadra": all(f["cuadra"] for f in filas if f["diferencia"] is not None)}


# =====================================================================
#  Escritura idempotente
# =====================================================================
def escribir(doc):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = DEST_JSON.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(DEST_JSON))
    log("[OK] -> %s" % DEST_JSON)
    # historico diario (idempotente: un archivo por dia, se sobrescribe)
    hist = OUT_DIR / "historico"
    hist.mkdir(exist_ok=True)
    (hist / ("dashboard_ventas_%s.json" % doc["generado_fecha"].replace("-", ""))).write_text(
        json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return DEST_JSON


def imprimir_conciliacion(doc):
    print("")
    print("=" * 78)
    print("  CONCILIACIÓN — el dashboard contra las fuentes ya validadas")
    print("=" * 78)
    for f in doc["conciliacion"]["filas"]:
        ok = "OK " if f["cuadra"] else "!! "
        ref = ("%18s" % ("{:,.2f}".format(f["referencia"]))) if f["referencia"] is not None else "%18s" % "(sin ref)"
        dif = ("%14s" % ("{:,.2f}".format(f["diferencia"]))) if f["diferencia"] is not None else "%14s" % "-"
        print("  %s %-11s %-52s" % (ok, f["pais"], f["concepto"]))
        print("      dashboard %18s   referencia %s   dif %s" % ("{:,.2f}".format(f["dashboard"]), ref, dif))
        if f.get("nota"):
            print("      nota: %s" % f["nota"])
    print("-" * 78)
    print("  RESULTADO: %s" % ("TODO CUADRA" if doc["conciliacion"]["todo_cuadra"] else "HAY DIFERENCIAS — revisar arriba"))
    print("=" * 78)
    print("")
    print("  AVISOS (%d):" % len(doc["avisos"]))
    for a in doc["avisos"]:
        print("   [%-7s] %-11s %-14s %s" % (a["nivel"], a["pais"] or "GRUPO", a["bloque"], a["texto"]))
    print("")


# =====================================================================
#  diag
# =====================================================================
def diagnostico():
    cfg = load_config()
    print("=" * 78)
    print("  DIAGNÓSTICO — ventas_dashboard.py")
    print("=" * 78)
    print("  URL   : %s" % (cfg.get("url") or "(falta)"))
    print("  DB    : %s" % (cfg.get("db") or "(falta)"))
    print("  LOGIN : %s" % (cfg.get("login") or "(falta)"))
    print("  APIKEY: %s" % ("sí" if cfg.get("apikey") else "(falta)"))
    print("  PROJ  : %s" % PROJ)
    print("  Regional xlsx: %s  (%s)" % (REGIONAL_XLSX, "existe" if REGIONAL_XLSX.exists() else "NO EXISTE — buscado por patrón en varias carpetas"))
    print("  Respaldo estado_grupo: %s" % ("existe" if _respaldo_estado().exists() else "aún no"))
    print("  estado_grupo.json: %s" % ("existe" if (PPTO_DIR / 'estado_grupo.json').exists() else "NO EXISTE"))
    od = Odoo(cfg)
    print("\n  Versión servidor: %s" % od.common.version().get("server_version"))
    od.authenticate()
    print("  Autenticado OK. db='%s' uid=%s" % (od.cfg["db"], od.uid))
    comps = companias(od, (cfg.get("_raw") or {}).get("company_map") or {})
    print("\n  COMPAÑÍAS (%d):" % len(comps))
    for cid, c in comps.items():
        print("    [%-3s] %-48s %-4s -> %s" % (cid, (c["name"] or "")[:48], c["moneda"] or "?",
                                               "EXCLUIDA" if c["excluida"] else (c["pais"] or "SIN MAPEAR")))
    year = datetime.date.today().year
    ctx = {"allowed_company_ids": list(comps.keys())}
    for cid, c in comps.items():
        dom = [["move_type", "in", ["out_invoice", "out_refund"]], ["state", "=", "posted"],
               ["invoice_date", ">=", "%d-01-01" % year], ["company_id", "=", cid]]
        try:
            n = od.kw("account.move", "search_count", [dom], {"context": ctx})
        except Exception as e:
            n = "ERROR %s" % str(e)[:60]
        print("    facturas %d de %-40s : %s" % (year, (c["name"] or "")[:40], n))
    av = Avisos()
    cuentas = cuentas_resultado(od, comps, av)
    print("\n  CUENTAS DE RESULTADO por compañía:")
    for cid, c in comps.items():
        k = cuentas.get(cid, {})
        print("    %-48s income=%-4s cogs=%-4s rescatadas=%s" %
              ((c["name"] or "")[:48], len(k.get("income", [])), len(k.get("cogs", [])),
               len(k.get("rescatadas", []))))
        for r in k.get("rescatadas", []):
            print("        rescatada por nombre: %s %s" % (r.get("code"), r.get("name")))
    print("\n  CARTERA (conteo crudo de líneas abiertas por compañía):")
    for cid, c in comps.items():
        dom = [["parent_state", "=", "posted"], ["company_id", "=", cid],
               ["account_id.account_type", "=", "asset_receivable"],
               ["reconciled", "=", False], ["amount_residual", "!=", 0]]
        try:
            n = od.kw("account.move.line", "search_count", [dom], {"context": ctx})
        except Exception as e:
            n = "ERROR %s" % str(e)[:60]
        print("    %-48s : %s" % ((c["name"] or "")[:48], n))
    print("\n  Llamadas XML-RPC: %d" % od.calls)
    print("  OK — diag no escribe el JSON.")


# =====================================================================
#  Autoprueba offline
# =====================================================================
def _selftest():
    """Servidor XML-RPC simulado. Valida las reglas que producen cifras falsas si se rompen."""
    hoy = datetime.date(2026, 8, 20)
    year = 2026

    COMPS = [{"id": 2, "name": "VICOMER S.A.S.", "currency_id": [1, "USD"]},
             {"id": 1, "name": "VINTRAL S.A.S.", "currency_id": [3, "COP"]},
             {"id": 3, "name": "3-102-940094 SOCIEDAD DE RESPONSABILIDAD LIMITADA", "currency_id": [1, "USD"]},
             {"id": 11, "name": "VIX S.A.S.", "currency_id": [1, "USD"]}]
    MOVES = [
        {"name": "FE-1", "invoice_date": "2026-08-05", "partner_id": [10, "COMOHOGAR S.A."],
         "amount_untaxed_signed": 70000.0, "amount_total_signed": 78400.0,
         "currency_id": [1, "USD"], "company_id": [2, "VICOMER S.A.S."], "move_type": "out_invoice"},
        {"name": "NC-1", "invoice_date": "2026-08-07", "partner_id": [10, "COMOHOGAR S.A."],
         "amount_untaxed_signed": -5000.0, "amount_total_signed": -5600.0,
         "currency_id": [1, "USD"], "company_id": [2, "VICOMER S.A.S."], "move_type": "out_refund"},
        {"name": "FE-2", "invoice_date": "2026-08-11", "partner_id": [11, "OTRO CLIENTE EC"],
         "amount_untaxed_signed": 15775.51, "amount_total_signed": 17668.57,
         "currency_id": [1, "USD"], "company_id": [2, "VICOMER S.A.S."], "move_type": "out_invoice"},
        {"name": "FV-1", "invoice_date": "2026-04-15", "partner_id": [20, "CASA MAGNA S.A.S."],
         "amount_untaxed_signed": 329046932.36, "amount_total_signed": 391565849.5,
         "currency_id": [3, "COP"], "company_id": [1, "VINTRAL S.A.S."], "move_type": "out_invoice"},
        {"name": "001-CR", "invoice_date": "2026-06-08", "partner_id": [30, "CEMACO INTERNACIONAL S.A."],
         "amount_untaxed_signed": 83947.0, "amount_total_signed": 94860.11,
         "currency_id": [1, "USD"], "company_id": [3, "3-102-940094 SOCIEDAD DE RESPONSABILIDAD LIMITADA"],
         "move_type": "out_invoice"},
        {"name": "VIX-1", "invoice_date": "2026-07-02", "partner_id": [40, "CLIENTE VIX"],
         "amount_untaxed_signed": 10000.0, "amount_total_signed": 11200.0,
         "currency_id": [1, "USD"], "company_id": [11, "VIX S.A.S."], "move_type": "out_invoice"},
    ]
    ACCTS = {2: [{"id": 100, "code": "4101", "name": "VENTAS", "account_type": "income"},
                 {"id": 200, "code": "5101", "name": "COSTO DE LA MERCANCIA VENDIDA", "account_type": "expense"}],
             1: [{"id": 101, "code": "4135", "name": "COMERCIO AL POR MAYOR", "account_type": "income"},
                 {"id": 201, "code": "6135", "name": "COSTO DE LA MERCANCIA VENDIDA", "account_type": "expense"}],
             3: [{"id": 102, "code": "5", "name": "INGRESOS CR", "account_type": "income"}],
             11: [{"id": 103, "code": "4", "name": "VENTAS VIX", "account_type": "income"}]}
    # mayor: (account_id, company_id, mes, balance, product_id)
    LEDGER = [(100, 2, 8, -80775.51, [7, "AIRE 12000 BTU"]), (200, 2, 8, 48000.0, [7, "AIRE 12000 BTU"]),
              (101, 1, 4, -329046932.36, [9, "NEVERA 300L"]), (201, 1, 4, 146800000.0, [9, "NEVERA 300L"]),
              (102, 3, 6, -83947.0, [8, "COCINA CR"])]
    RECEIV = [
        {"id": 900, "move_name": "FE-1", "date": "2026-08-05", "date_maturity": "2026-09-04",
         "amount_residual": 65000.0, "partner_id": [10, "COMOHOGAR S.A."], "company_id": [2, "VICOMER S.A.S."], "debit": 78400.0},
        {"id": 901, "move_name": "FV-1", "date": "2026-04-15", "date_maturity": "2026-05-15",
         "amount_residual": 120000000.0, "partner_id": [20, "CASA MAGNA S.A.S."], "company_id": [1, "VINTRAL S.A.S."], "debit": 391565849.5},
        {"id": 902, "move_name": "001-CR", "date": "2026-06-08", "date_maturity": "2026-07-08",
         "amount_residual": 94860.11, "partner_id": [30, "CEMACO INTERNACIONAL S.A."],
         "company_id": [3, "3-102-940094 SOCIEDAD DE RESPONSABILIDAD LIMITADA"], "debit": 94860.11},
    ]

    def _dom_get(dom, field):
        return [c for c in dom if isinstance(c, (list, tuple)) and c and c[0] == field]

    class Mock(object):
        def __init__(self):
            self.calls = 0
        def execute_kw(self, db, uid, key, model, method, args, kw=None):
            self.calls += 1
            kw = kw or {}
            dom = args[0] if args else []
            if model == "res.company":
                return COMPS
            if model == "account.account":
                cids = (kw.get("context") or {}).get("allowed_company_ids") or []
                acc = []
                for c in cids:
                    acc += ACCTS.get(c, [])
                tipos = None
                for c in _dom_get(dom, "account_type"):
                    tipos = c[2]
                return [a for a in acc if (tipos is None or a["account_type"] in tipos)]
            if model == "account.move":
                data = list(MOVES)
                for c in _dom_get(dom, "invoice_date"):
                    if c[1] == ">=":
                        data = [x for x in data if x["invoice_date"] >= c[2]]
                    if c[1] == "<=":
                        data = [x for x in data if x["invoice_date"] <= c[2]]
                for c in _dom_get(dom, "company_id"):
                    if c[1] == "=":
                        data = [x for x in data if x["company_id"][0] == c[2]]
                    if c[1] == "in":
                        data = [x for x in data if x["company_id"][0] in c[2]]
                if method == "search_count":
                    return len(data)
                f = kw.get("fields")
                return [dict((k, x.get(k)) for k in f) for x in data] if f else data
            if model == "account.move.line":
                recv = bool(_dom_get(dom, "account_id.account_type"))
                if recv:
                    data = list(RECEIV)
                    for c in _dom_get(dom, "company_id"):
                        if c[1] == "in":
                            data = [x for x in data if x["company_id"][0] in c[2]]
                        if c[1] == "=":
                            data = [x for x in data if x["company_id"][0] == c[2]]
                    if _dom_get(dom, "debit"):
                        pass
                    if method == "search_count":
                        return len(data)
                    if method == "search_read":
                        f = kw.get("fields")
                        return [dict((k, x.get(k)) for k in f) for x in data] if f else data
                    return []
                if method == "read_group":
                    accs = None; comp = None; desde = hasta = None
                    for c in _dom_get(dom, "account_id"):
                        accs = c[2]
                    for c in _dom_get(dom, "company_id"):
                        comp = c[2] if isinstance(c[2], list) else [c[2]]
                    for c in _dom_get(dom, "date"):
                        if c[1] == ">=": desde = c[2]
                        if c[1] == "<=": hasta = c[2]
                    gb = args[2] if len(args) > 2 else []
                    out = {}
                    for (aid, cid, mes, bal, prod) in LEDGER:
                        if accs is not None and aid not in accs:
                            continue
                        if comp is not None and cid not in comp:
                            continue
                        f = "%d-%02d-15" % (year, mes)
                        if desde and f < desde: continue
                        if hasta and f > hasta: continue
                        k = tuple(prod) if "product_id" in gb else cid
                        out.setdefault(k, 0.0)
                        out[k] += bal
                    res = []
                    for k, v in out.items():
                        r = {"balance": v}
                        if "product_id" in gb:
                            r["product_id"] = list(k)
                        else:
                            r["company_id"] = [k, "?"]
                        res.append(r)
                    return res
                return []
            if model == "account.partial.reconcile":
                return []
            return []

    class Common(object):
        def version(self): return {"server_version": "18.0-mock"}
        def authenticate(self, db, l, k, ua): return 7

    class FakeOdoo(Odoo):
        def __init__(self, cfg):
            self.cfg = cfg; self.uid = 7; self.calls = 0
            self.common = Common(); self.models = Mock()
        def authenticate(self): return 7

    cfg = {"url": "http://mock", "db": "mock", "login": "x", "apikey": "y",
           "_raw": {"company_map": {"VICOMER": "Ecuador", "VIX": "ignore", "VINTRAL": "Colombia",
                                    "3-102-940094": "Costa Rica", "SOCIEDAD DE RESPONSABILIDAD": "Costa Rica"},
                    "ecuador_hist_mensual": {"1": 196899.91, "2": 82864.10, "3": 216807.95, "4": 56841.12,
                                             "5": 125252.76, "6": 333128.95, "7": 105449.10},
                    "colombia_hist_mensual": {"1": 121934422.21, "2": 82011090.76, "3": 58375627.82},
                    "ecuador_corte_migracion": "2026-08-01"}}

    global PPTO_DIR, REGIONAL_XLSX, OUT_DIR, DEST_JSON
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    PPTO_DIR = tmp / "PresupuestoAuto"; PPTO_DIR.mkdir()
    (PPTO_DIR / "estado_grupo.json").write_text(json.dumps({
        "generado": datetime.datetime.now().isoformat(timespec="seconds"), "anio": 2026, "mes_cierre": 7,
        "paises": {"Ecuador": {"moneda": "USD", "ytd_real": 1117243.89, "ppto_ytd": 1095845.0, "ppto_anual": 2290147.0},
                   "Colombia": {"moneda": "COP", "ytd_real": 591368073.15, "ppto_ytd": 1566617209.0, "ppto_anual": 3671996149.0},
                   "Costa Rica": {"moneda": "USD", "ytd_real": 83947.0, "ppto_ytd": 129167.0, "ppto_anual": 300002.0}}
    }), encoding="utf-8")
    REGIONAL_XLSX = tmp / "no_existe.xlsx"
    OUT_DIR = tmp / "OdooVentas"
    DEST_JSON = OUT_DIR / "dashboard_ventas.json"

    av = Avisos()
    od = FakeOdoo(cfg)
    doc = construir(od, year, av, hoy=hoy)

    ec = doc["paises"]["Ecuador"]; co = doc["paises"]["Colombia"]; cr = doc["paises"]["Costa Rica"]
    fallos = []

    def chk(cond, msg):
        if not cond:
            fallos.append(msg)
        print(("  OK  " if cond else "  FALLA ") + msg)

    print("\nAUTOPRUEBA ventas_dashboard.py")
    print("-" * 70)
    chk(abs(sum(ec["mensual_hist"]) - 1117243.89) < 0.01,
        "Ecuador Ene-Jul histórico = 1.117.243,89 (no se pierde)")
    chk(ec["mensual_hist"][7] == 0.0, "Ecuador NO tiene histórico en agosto (no se duplica)")
    chk(abs(ec["mensual"][7] - 80775.51) < 0.01, "Ecuador agosto = 80.775,51 sólo de Odoo (70.000 - 5.000 + 15.775,51)")
    chk(abs(ec["ytd_real"] - 1117243.89) < 0.01, "Ecuador YTD (a mes cerrado=7) = 1.117.243,89")
    chk(abs(co["hist_amount"] - 262321140.79) < 0.01, "Colombia Ene-Mar histórico de la instancia vieja")
    chk(abs(co["mensual"][3] - 329046932.36) < 0.01, "Colombia abril viene de la instancia nueva")
    chk(all("VIX" not in e for p in doc["paises"].values() for e in p["empresas"]),
        "VIX excluida de los 4 dashboards")
    chk(10000.0 not in [x for p in doc["paises"].values() for x in p["mensual"]],
        "La venta de VIX no aparece en ningún país")
    chk(cr["margen"]["disponible"] is False and "no es calculable" in (cr["margen"]["motivo"] or "").lower(),
        "Costa Rica: margen NO calculable (ni 100% ni 0%)")
    chk(ec["margen"]["disponible"] and ec["margen"]["ytd"]["margen_pct"] is not None,
        "Ecuador: margen calculado desde el mayor")
    chk(abs(ec["margen"]["ytd"]["margen_pct"] - (80775.51 - 48000.0) / 80775.51) < 0.001,
        "Ecuador margen bruto = (venta - COGS)/venta con el COGS rescatado por nombre")
    chk(any(a["bloque"] == "margen" and a["nivel"] == "critico" for a in doc["avisos"]),
        "El COGS ausente de Costa Rica queda declarado como aviso crítico")
    chk(doc["consolidado"]["referencial"] is True and doc["tc"]["referencial"] is True,
        "Todo USD consolidado va marcado como referencial")
    chk(abs(co["usd"]["ytd_real"] - round(co["ytd_real"] * 0.00027027, 2)) < 1.0 and co["usd"]["ytd_real"] < co["ytd_real"] / 3000,
        "Colombia a USD usa el TC manual (~3.700), no el 0,00031805 de Odoo")
    chk(ec["clientes"]["hhi"] is not None and ec["clientes"]["hhi"] > 2500,
        "HHI de Ecuador marca concentración crítica")
    chk(ec["cartera"]["disponible"] and ec["cartera"]["total"] == 65000.0, "Cartera de Ecuador leída de account.move.line")
    chk(cr["ppto_mensual"] is None and any(a["bloque"] == "presupuesto" for a in doc["avisos"]),
        "Sin libro Regional, la curva mensual se declara ausente (no se inventa)")
    chk(doc["conciliacion"]["todo_cuadra"], "Conciliación contra estado_grupo.json e históricos: cuadra")
    # el agente com.vcomer.presupuesto sobrescribe estado_grupo.json con {} cuando corre
    # sin red: el respaldo tiene que salvar el presupuesto en vez de perderlo
    (PPTO_DIR / "estado_grupo.json").write_text(json.dumps(
        {"generado": datetime.datetime.now().isoformat(timespec="seconds"), "anio": 2026,
         "mes_cierre": 7, "paises": {}}), encoding="utf-8")
    av3 = Avisos()
    doc3 = construir(FakeOdoo(cfg), year, av3, hoy=hoy)
    chk(doc3["paises"]["Ecuador"]["ppto_ytd"] == 1095845.0,
        "Si estado_grupo.json viene VACÍO, el respaldo conserva el presupuesto en vez de perderlo")
    chk(any("respaldo" in a["texto"] for a in doc3["avisos"]),
        "...y el dashboard declara que ese presupuesto viene de un respaldo con su fecha")
    chk(ec["mtd"]["real"] == 80775.51 and ec["mtd"]["mes"] == 8, "MTD de agosto correcto")
    chk(doc["consolidado"]["ytd_real"] > 0 and doc["consolidado"]["composicion"][0]["pais"] == "Ecuador",
        "Consolidado ordena la composición por peso en USD")

    # doble conteo: si alguien mete el mes 8 en el historico de Ecuador, hay que gritar
    cfg2 = json.loads(json.dumps(cfg))
    cfg2["_raw"]["ecuador_hist_mensual"]["8"] = 80775.51
    av2 = Avisos()
    doc2 = construir(FakeOdoo(cfg2), year, av2, hoy=hoy)
    chk(any(a["nivel"] == "critico" and "DOBLE CONTEO" in a["texto"] for a in doc2["avisos"]),
        "Si el histórico invade el mes del corte, se detecta el DOBLE CONTEO y se descarta")
    chk(abs(doc2["paises"]["Ecuador"]["mensual"][7] - 80775.51) < 0.01,
        "Y agosto sigue valiendo 80.775,51 (no 161.551,02)")

    escribir(doc)
    chk(DEST_JSON.exists(), "El JSON se escribe de forma atómica")
    escribir(doc)
    chk(len(list((OUT_DIR / "historico").glob("*.json"))) == 1, "Idempotente: correrlo dos veces no duplica archivos")

    print("-" * 70)
    if fallos:
        print("AUTOPRUEBA FALLÓ (%d):" % len(fallos))
        for f in fallos:
            print("   - " + f)
        sys.exit(1)
    print("AUTOPRUEBA OK — %d comprobaciones" % 26)
    imprimir_conciliacion(doc)


# =====================================================================
def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else str(datetime.date.today().year)
    if arg == "test":
        _selftest(); return
    if arg == "diag":
        diagnostico(); return
    year = int(arg) if arg.isdigit() else datetime.date.today().year
    avisos = Avisos()
    cfg = load_config()
    od = Odoo(cfg)
    od.authenticate()
    log("Odoo %s db='%s' uid=%s" % (cfg["url"], cfg["db"], od.uid))
    doc = construir(od, year, avisos)
    escribir(doc)
    imprimir_conciliacion(doc)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("[ERROR]\n" + traceback.format_exc())
        sys.exit(1)
