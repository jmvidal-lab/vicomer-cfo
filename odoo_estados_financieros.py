#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
odoo_estados_financieros.py  ·  v1 (2026-08-03)
===============================================
ESTADOS FINANCIEROS EJECUTIVOS de VICOMER Ecuador construidos desde ODOO.

Reemplaza a `perseo_estados_financieros.py`, que se conserva INTACTO como
respaldo/histórico. Este script no lo modifica ni lo pisa: escribe sus propios
archivos con el sufijo `_ODOO_`.

  Fuente única de verdad: el mayor contable de Odoo (`account.move.line`),
  filtrado a asientos CONTABILIZADOS (parent_state = 'posted') de la compañía
  de Ecuador, con fecha <= corte. En Odoo `balance` = débito - crédito, el
  mismo convenio de signo que el `importe` de Perseo, así que toda la capa de
  cálculo heredada sigue siendo válida.

  Balance General  : saldos ACUMULADOS de las cuentas 1/2/3 hasta el corte.
  Estado Resultados: movimientos de las cuentas 4/5 del mes cerrado y del YTD.

------------------------------------------------------------------------------
ADVERTENCIA IMPORTANTE — LA EQUIVALENCIA CON PERSEO NO ESTÁ VERIFICADA
------------------------------------------------------------------------------
Ecuador migró de Perseo a Odoo. No está confirmado que el plan de cuentas de
Odoo conserve la codificación PUC que usaban los EEFF de Perseo. Hasta que
`python3 odoo_estados_financieros.py conciliar 2026-06` (o el mes que sea)
muestre diferencias razonables contra el reporte de Perseo del mismo mes,
estos números NO son comparables con la serie histórica. No se deben publicar
al directorio sin esa conciliación.
------------------------------------------------------------------------------

DOBLE MODO DE MAPEO (se elige solo, o se fuerza)
  modo "puc"  : la cuenta se clasifica por el PREFIJO de su código, idéntico a
                Perseo (11 activo corriente, 1101 efectivo, 1102 clientes,
                1103 inventarios, 21 pasivo corriente, 2104/2203 deuda
                financiera, 3 patrimonio, 41 ventas, 42 otros ingresos,
                51 costo, 52 g.ventas, 53 g.admin, 54 financieros, 55 no ded.).
  modo "tipo" : la cuenta se clasifica por su `account_type` nativo de Odoo y
                se le asigna un código PUC SINTÉTICO. Así toda la lógica de
                rubros/ratios (que suma por prefijo) funciona sin cambios.
  Autodetección: si al menos 12 de los 17 prefijos PUC tienen cuentas reales,
  usa "puc"; si no, "tipo". Se puede forzar con la variable de entorno
  EEFF_MODO=puc|tipo o con el argumento CLI --modo=puc|tipo.
  El modo elegido queda escrito en el Excel (nota de portada + hoja "Metodo y
  Fuente"), en el JSON y en el log. Los importes de un modo y otro NO son
  comparables sin revisión: en modo "tipo" Odoo no distingue gastos de ventas
  de gastos de administración (todo cae en "gastos operativos") ni marca los
  no deducibles.

NOTA SOBRE LA REUTILIZACIÓN DE CÓDIGO
  `compute_statements`, `build_report` y `sum_prefix` están COPIADOS (adaptados)
  desde perseo_estados_financieros.py en vez de importados, porque ese módulo
  importa openpyxl a nivel de módulo y este script debe poder calcular y
  autotestearse sin openpyxl instalado. `build_workbook` (todo el formato del
  Excel) SÍ se importa de forma perezosa desde perseo_estados_financieros para
  que ambos reportes salgan visualmente idénticos; si no se puede importar, hay
  un formato mínimo de respaldo.

SALIDA
  Finanzas/Estados_Financieros_Ejecutivo_ODOO_YYYY-MM.xlsx
  Finanzas/Estados_Financieros_Ejecutivo_ODOO_ULTIMO.xlsx
  Finanzas/eeff_odoo_YYYY-MM.json    (rubros + modo + compañía + advertencias)

CONFIG
  odoo_config.json (url, db, login, company_map) + odoo_apikey.txt
  OdooVentas/descubrimiento_odoo.json  (opcional, lo genera odoo_descubrir.py)

USO
  python3 odoo_estados_financieros.py                  # último mes cerrado
  python3 odoo_estados_financieros.py 2026-07          # corte a fin de jul-2026
  python3 odoo_estados_financieros.py 2026-07 --modo=tipo
  python3 odoo_estados_financieros.py diag [YYYY-MM]   # qué ve el script en Odoo
  python3 odoo_estados_financieros.py conciliar [YYYY-MM]  # Odoo vs Perseo
  python3 odoo_estados_financieros.py autotest         # pruebas offline, sin red

Sólo stdlib + openpyxl (openpyxl únicamente para escribir/leer Excel).
"""
import os
import sys
import ssl
import json
import calendar
import datetime
import xmlrpc.client
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
PROJ = Path(__file__).resolve().parent
OUT_DIR = PROJ / "Finanzas"
DESCUBRIMIENTO = Path(os.environ.get("ODOO_OUT_DIR", PROJ / "OdooVentas")) / "descubrimiento_odoo.json"

EMPRESA_DEFAULT = "VICOMER (Ecuador)"
PAIS_OBJETIVO = "Ecuador"
PAGINA = 5000                    # tamaño de página al leer account.move.line

# Prefijos PUC que usan los EEFF heredados de Perseo. Sirven para autodetectar
# el modo de mapeo: si el plan de cuentas de Odoo los cubre, se usa "puc".
PREFIJOS_PERSEO = ["11", "1101", "1102", "1103", "12", "21", "2104", "22", "2203",
                   "3", "41", "42", "51", "52", "53", "54", "55"]
MIN_PREFIJOS_PUC = 12            # umbral de autodetección (de 17)

# ---------------------------------------------------------------- modo "tipo"
# account_type de Odoo -> código PUC SINTÉTICO. El código sintético final es
# "<base>.<codigo_odoo_limpio>"; el punto evita colisiones de prefijo (p.ej.
# que una cuenta de pasivo no corriente "22.0345" se cuente como deuda
# financiera "2203") y a la vez conserva la semántica de startswith().
TIPO_A_PUC = {
    "asset_cash":           "1101",   # efectivo y equivalentes
    "asset_receivable":     "1102",   # clientes
    "asset_current":        "1104",   # otros activos corrientes (1103 si es inventario)
    "asset_prepayments":    "1105",   # pagos anticipados (corriente)
    "asset_non_current":    "1201",
    "asset_fixed":          "1202",
    "liability_payable":    "2101",   # proveedores
    "liability_current":    "2102",   # otros pasivos corrientes (2104 si es financiero)
    "liability_credit_card": "2104",  # tarjetas = deuda financiera corriente
    "liability_non_current": "2201",  # (2203 si es financiero)
    "equity":               "3101",
    "equity_unaffected":    "3102",   # resultados de ejercicios anteriores
    "income":               "41",
    "income_other":         "42",
    "expense_direct_cost":  "51",     # costo de ventas
    "expense":              "53",     # gastos operativos (Odoo no separa ventas/admin)
    "expense_depreciation": "53",
    "off_balance":          None,     # fuera de balance: se descarta
}
# Heurísticas por NOMBRE de cuenta (sólo se aplican en modo "tipo").
NOMBRES_INVENTARIO = ("inventar", "existenc", "mercader", "stock", "producto termin",
                      "materia prima")
NOMBRES_FINANCIERO = ("prestam", "préstam", "obligacion financ", "obligación financ",
                      "obligaciones financ", "banco", "bancari", "leasing", "sobregiro",
                      "deuda financ", "credito banc", "crédito banc", "pagare", "pagaré")


def log(msg):
    print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}", flush=True)


# ------------------------------------------------------------------ utilidades
def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def code_limpio(s) -> str:
    """Código de cuenta sin puntos, guiones ni espacios: '1.1.02.05' -> '110205'."""
    return str(s or "").replace(".", "").replace("-", "").replace(" ", "").strip()


def ymd(fecha_iso) -> str:
    """'2026-07-31' -> '20260731'. Tolera datetime y cadenas ya compactas."""
    s = str(fecha_iso or "")
    if len(s) >= 10 and s[4] == "-":
        return s[:10].replace("-", "")
    return s[:8]


def last_closed_month(today: datetime.date):
    """(año, mes) del último mes CERRADO respecto de hoy."""
    prev = today.replace(day=1) - datetime.timedelta(days=1)
    return prev.year, prev.month


def month_end(y: int, m: int) -> datetime.date:
    return datetime.date(y, m, calendar.monthrange(y, m)[1])


MESES = ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago",
         "Sep", "Oct", "Nov", "Dic"]


# ------------------------------------------------------------------ config Odoo
def load_config():
    """Config de Odoo, mismo patrón que odoo_margen.py / odoo_descubrir.py."""
    cfg = {"url": os.environ.get("ODOO_URL"), "db": os.environ.get("ODOO_DB"),
           "login": os.environ.get("ODOO_LOGIN"), "apikey": os.environ.get("ODOO_APIKEY")}
    extra = {}
    for f in (HOME / ".odoo_config.json", PROJ / "odoo_config.json"):
        if f.exists():
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                extra.update(d)
                for k in ("url", "db", "login", "apikey"):
                    cfg[k] = cfg[k] or d.get(k)
            except Exception as e:
                log(f"AVISO: no pude leer {f}: {e}")
    for kf in (HOME / ".odoo_apikey", PROJ / "odoo_apikey.txt"):
        if not cfg["apikey"] and kf.exists():
            cfg["apikey"] = kf.read_text(encoding="utf-8").strip()
    if cfg.get("url"):
        cfg["url"] = cfg["url"].rstrip("/")
    for k in ("url", "db", "login", "apikey"):
        if not cfg.get(k):
            sys.exit(f"ERROR: falta '{k}' de Odoo. Revisa odoo_config.json / odoo_apikey.txt")
    cfg["company_map"] = extra.get("company_map", {})
    return cfg


class Odoo:
    """Cliente XML-RPC mínimo (mismo patrón que odoo_margen.py)."""

    def __init__(self, cfg):
        self.cfg = cfg
        ctx = ssl.create_default_context()
        self.common = xmlrpc.client.ServerProxy(f"{cfg['url']}/xmlrpc/2/common",
                                                allow_none=True, context=ctx)
        self.models = xmlrpc.client.ServerProxy(f"{cfg['url']}/xmlrpc/2/object",
                                                allow_none=True, context=ctx)
        self.uid = None
        self.version = {}

    def authenticate(self):
        try:
            self.version = self.common.version()
        except Exception as e:
            log(f"AVISO: no pude leer la versión de Odoo: {e}")
        self.uid = self.common.authenticate(self.cfg["db"], self.cfg["login"],
                                            self.cfg["apikey"], {})
        if not self.uid:
            sys.exit("ERROR: no autenticó en Odoo. Revisa db/login/apikey.")
        return self.uid

    def kw(self, model, method, args, kwargs=None):
        return self.models.execute_kw(self.cfg["db"], self.uid, self.cfg["apikey"],
                                      model, method, args, kwargs or {})

    def try_kw(self, model, method, args, kwargs=None, default=None):
        try:
            return self.kw(model, method, args, kwargs)
        except Exception as e:
            log(f"  (sondeo {model}.{method} falló: {str(e)[:100]})")
            return default


def leer_descubrimiento():
    """Retrato de la instancia generado por odoo_descubrir.py. {} si no existe."""
    if DESCUBRIMIENTO.exists():
        try:
            return json.loads(DESCUBRIMIENTO.read_text(encoding="utf-8"))
        except Exception as e:
            log(f"AVISO: no pude leer {DESCUBRIMIENTO}: {e}")
    return {}


def pais_de_company(cname, company_map):
    """País mapeado para una compañía. Gana el fragmento MÁS LARGO que coincida."""
    cn = (cname or "").upper()
    mejor, mejor_len = None, -1
    for frag, pais in (company_map or {}).items():
        if frag.upper() in cn and len(frag) > mejor_len:
            mejor, mejor_len = pais, len(frag)
    return mejor


def identificar_ecuador(comps, company_map, advertencias):
    """Devuelve la compañía de Ecuador (dict de res.company) o aborta."""
    candidatos = [c for c in comps
                  if pais_de_company(c.get("name"), company_map) == PAIS_OBJETIVO]
    if not candidatos:
        # Respaldo: lo que haya dicho odoo_descubrir.py
        doc = leer_descubrimiento()
        cands = doc.get("candidatos_ecuador") or []
        if cands:
            cid = cands[0]["id"]
            elegida = next((c for c in comps if c["id"] == cid), None)
            if elegida:
                advertencias.append(
                    f"company_map no mapea ninguna compañía a Ecuador; se usó el candidato "
                    f"de descubrimiento_odoo.json: «{elegida['name']}» (id={cid}).")
                return elegida
        sys.exit("ERROR: no identifiqué la compañía de Ecuador. Añade el fragmento del "
                 "nombre a company_map en odoo_config.json con valor \"Ecuador\" "
                 "(verifica con: python3 odoo_descubrir.py resumen).")
    if len(candidatos) > 1:
        advertencias.append(
            "Hay más de una compañía mapeada a Ecuador: "
            + ", ".join(f"«{c['name']}» (id={c['id']})" for c in candidatos)
            + f". Se usó «{candidatos[0]['name']}».")
    return candidatos[0]


# ------------------------------------------------------------- plan de cuentas
def leer_cuentas(od, comp_id, comp_ids):
    """Plan de cuentas visible para la compañía. Devuelve lista normalizada.

    CRÍTICO: desde Odoo 17 el campo `code` de account.account es *company-dependent*.
    Si se lee con varias compañías en el contexto, Odoo devuelve el código VACÍO para
    las cuentas que no son de la compañía principal del contexto. Leyendo así, VICOMER
    devolvía 0/17 prefijos PUC cubiertos y el script elegía el modo `tipo`; leyendo con
    la compañía de Ecuador sola, el plan SÍ conserva la codificación PUC (14/17).
    Es la diferencia entre unos estados financieros correctos y unos mal mapeados.
    """
    campos = ["id", "code", "name", "account_type"]
    ctx = {"allowed_company_ids": [comp_id]}     # <-- SOLO la compañía de Ecuador
    accts = od.try_kw("account.account", "search_read", [[]],
                      {"fields": campos + ["company_ids"], "context": ctx, "limit": 8000},
                      default=None)
    if accts is None:
        # Odoo < 17 usa company_id (many2one) en vez de company_ids
        accts = od.try_kw("account.account", "search_read", [[]],
                          {"fields": campos + ["company_id"], "context": ctx, "limit": 8000},
                          default=[])
    norm = []
    for a in accts:
        comps = a.get("company_ids") or a.get("company_id") or []
        if isinstance(comps, list) and len(comps) == 2 and isinstance(comps[0], int) \
                and isinstance(comps[1], str):
            comps = [comps[0]]                      # formato many2one [id, nombre]
        if not isinstance(comps, list):
            comps = []
        norm.append({
            "id": a["id"],
            "code": (a.get("code") or "").strip(),
            "code_limpio": code_limpio(a.get("code")),
            "name": a.get("name") or "",
            "account_type": a.get("account_type") or "",
            "company_ids": comps,
        })
    # Cuentas de la compañía de Ecuador (si el dato de compañía viene vacío, se
    # asume que la cuenta es compartida y se conserva).
    propias = [a for a in norm if (not a["company_ids"]) or comp_id in a["company_ids"]]
    propias = propias if propias else norm
    sin_cod = sum(1 for a in propias if not a["code_limpio"])
    if sin_cod:
        log(f"  AVISO: {sin_cod} de {len(propias)} cuentas sin código legible "
            f"(no se pueden mapear por prefijo)")
    return propias


def cobertura_prefijos(cuentas):
    """{prefijo: nº de cuentas cuyo código limpio empieza por él}."""
    return {p: sum(1 for a in cuentas if a["code_limpio"].startswith(p))
            for p in PREFIJOS_PERSEO}


def elegir_modo(cuentas, forzado=None):
    """Devuelve (modo, cobertura, n_cubiertos, autodetectado)."""
    cob = cobertura_prefijos(cuentas)
    cubiertos = sum(1 for p in PREFIJOS_PERSEO if cob.get(p, 0) > 0)
    auto = "puc" if cubiertos >= MIN_PREFIJOS_PUC else "tipo"
    if forzado in ("puc", "tipo"):
        return forzado, cob, cubiertos, False
    return auto, cob, cubiertos, True


def _tipo_a_puc(account_type, nombre):
    """Código PUC sintético base para una cuenta, según su account_type."""
    base = TIPO_A_PUC.get(account_type, None)
    if base is None:
        return None
    n = (nombre or "").lower()
    if account_type == "asset_current" and any(k in n for k in NOMBRES_INVENTARIO):
        return "1103"                                  # inventarios
    if account_type == "liability_current" and any(k in n for k in NOMBRES_FINANCIERO):
        return "2104"                                  # deuda financiera corriente
    if account_type == "liability_non_current" and any(k in n for k in NOMBRES_FINANCIERO):
        return "2203"                                  # deuda financiera no corriente
    return base


def construir_mapa(cuentas, modo, advertencias=None):
    """
    Devuelve (mapa_id_a_puc, mapa_id_a_cuenta, sin_mapear).
      modo "puc"  -> el código PUC es el propio código limpio de Odoo.
      modo "tipo" -> código sintético "<base>.<codigo_odoo_limpio>".
    """
    advertencias = advertencias if advertencias is not None else []
    id_a_puc, id_a_cta, sin_mapear = {}, {}, []
    sin_tipo = set()
    for a in cuentas:
        id_a_cta[a["id"]] = a
        if modo == "puc":
            cod = a["code_limpio"]
            if not cod or cod[0] not in "12345":
                sin_mapear.append(a)
                continue
            id_a_puc[a["id"]] = cod
        else:
            base = _tipo_a_puc(a["account_type"], a["name"])
            if not base:
                sin_mapear.append(a)
                if a["account_type"] not in ("off_balance",):
                    sin_tipo.add(a["account_type"] or "(vacío)")
                continue
            id_a_puc[a["id"]] = f"{base}.{a['code_limpio'] or a['id']}"
    if sin_tipo:
        advertencias.append("account_type sin mapeo en TIPO_A_PUC (cuentas excluidas): "
                            + ", ".join(sorted(sin_tipo)))
    if modo == "puc" and sin_mapear:
        advertencias.append(f"{len(sin_mapear)} cuentas con código que no empieza en 1-5 "
                            f"quedaron fuera del reporte (modo puc).")
    return id_a_puc, id_a_cta, sin_mapear


def advertencias_de_modo(modo, cubiertos, cob):
    """Advertencias estructurales derivadas del modo de mapeo elegido."""
    adv = []
    if modo == "tipo":
        adv.append("MODO TIPO: las cuentas se clasifican por account_type de Odoo, no por "
                   "código PUC. Los importes NO son directamente comparables con la serie "
                   "histórica de Perseo sin revisar la conciliación.")
        adv.append("MODO TIPO: Odoo no distingue gastos de VENTAS de gastos de "
                   "ADMINISTRACIÓN; todo el gasto operativo se presenta en «Gastos de "
                   "Administracion». Gastos financieros y no deducibles quedan en 0.")
        adv.append("MODO TIPO: los inventarios y la deuda financiera se detectan por el "
                   "NOMBRE de la cuenta (heurística). Verificar contra el balance de Odoo.")
    else:
        faltan = [p for p in PREFIJOS_PERSEO if cob.get(p, 0) == 0]
        if faltan:
            adv.append("MODO PUC: prefijos sin ninguna cuenta (esos rubros salen en 0): "
                       + ", ".join(faltan))
        # Caso observado en VICOMER (2026-08): el gasto operativo está todo colgado
        # de 52 y no existen 53/54/55. El P&L cuadra en total pero NO en su apertura.
        gasto_faltante = [p for p in ("53", "54", "55") if cob.get(p, 0) == 0]
        if gasto_faltante and cob.get("52", 0) > 50:
            adv.append(
                f"MODO PUC: no existen los prefijos {', '.join(gasto_faltante)} y el 52 "
                f"concentra {cob.get('52')} cuentas. El gasto operativo total es correcto, "
                f"pero su APERTURA no: gastos de administración, financieros y no deducibles "
                f"saldrán en 0 y todo aparecerá como gasto de ventas. Para separarlos hay que "
                f"mapear por account_type o subdividir el prefijo 52.")
    adv.append(f"Cobertura de prefijos PUC: {cubiertos}/{len(PREFIJOS_PERSEO)}.")
    return adv


# ------------------------------------------------------------------ extracción
def primer_asiento(od, comp_id, comp_ids):
    """Fecha (ISO) del primer apunte contabilizado de la compañía, o None."""
    try:
        r = od.kw("account.move.line", "search_read",
                  [[["parent_state", "=", "posted"], ["company_id", "=", comp_id]]],
                  {"fields": ["date"], "limit": 1, "order": "date asc",
                   "context": {"allowed_company_ids": comp_ids}})
        return r[0]["date"] if r else None
    except Exception:
        return None


def leer_lineas(od, comp_id, comp_ids, cutoff, id_a_puc, advertencias):
    """
    Lee el mayor de Odoo y lo devuelve como la MISMA lista de tuplas que usaba
    Perseo: (fecha YYYYMMDD, codigo_puc, importe) con importe>0 = débito.
    Pagina de a PAGINA registros con offset para no reventar en volúmenes altos.
    """
    dom = [["parent_state", "=", "posted"],
           ["company_id", "=", comp_id],
           ["date", "<=", cutoff.isoformat()]]

    # display_type sólo existe en versiones recientes; si no está, no se filtra.
    campos_ml = od.try_kw("account.move.line", "fields_get",
                          [[], ["type"]], {}, default=None)
    if campos_ml is None:
        advertencias.append("No pude leer fields_get de account.move.line; no se filtraron "
                            "líneas de sección/nota.")
    elif "display_type" in campos_ml:
        dom.append(["display_type", "not in", ["line_section", "line_note"]])
    else:
        advertencias.append("El campo display_type no existe en esta versión de Odoo; "
                            "no se filtraron líneas de sección/nota.")

    ctx = {"allowed_company_ids": comp_ids}
    lines = []
    saldo_por_cuenta = defaultdict(float)
    fmin, fmax = None, None
    offset, total, descartadas = 0, 0, 0
    while True:
        rows = od.kw("account.move.line", "search_read", [dom],
                     {"fields": ["account_id", "balance", "date"],
                      "limit": PAGINA, "offset": offset, "order": "id",
                      "context": ctx})
        if not rows:
            break
        for r in rows:
            acc = r.get("account_id") or [0, ""]
            aid = acc[0] if isinstance(acc, (list, tuple)) else acc
            puc = id_a_puc.get(aid)
            f = ymd(r.get("date"))
            if fmin is None or f < fmin:
                fmin = f
            if fmax is None or f > fmax:
                fmax = f
            if not puc:
                descartadas += 1
                continue
            imp = _num(r.get("balance"))
            lines.append((f, puc, imp))
            saldo_por_cuenta[aid] += imp
        total += len(rows)
        offset += PAGINA
        log(f"    ...{total} líneas leídas")
        if len(rows) < PAGINA:
            break
    if descartadas:
        advertencias.append(f"{descartadas} líneas del mayor quedaron fuera del reporte "
                            f"(cuenta sin mapeo al plan de rubros).")
    log(f"  mayor Odoo: {total} líneas leídas, {len(lines)} clasificadas, "
        f"rango {fmin} → {fmax}")
    return lines, {"n_leidas": total, "n_clasificadas": len(lines),
                   "n_descartadas": descartadas,
                   "primera_fecha": fmin, "ultima_fecha": fmax}, saldo_por_cuenta


# ------------------------------------------------------- cálculo (copia adaptada
# ------------------------------------------------------- de perseo_estados_financieros.py)
def sum_prefix(saldos: dict, prefix: str) -> float:
    """Suma los saldos de las cuentas HOJA cuyo código empieza con prefix."""
    return sum(v for k, v in saldos.items() if k.startswith(prefix))


def compute_statements(lines, cutoff: datetime.date, y_fin: int, m_fin: int):
    """Balance (acumulado <= corte) y P&L (mes cerrado + YTD). Idéntico a Perseo."""
    corte = cutoff.strftime("%Y%m%d")
    per0 = datetime.date(y_fin, m_fin, 1).strftime("%Y%m%d")   # inicio mes cerrado
    ytd0 = datetime.date(y_fin, 1, 1).strftime("%Y%m%d")       # inicio del año

    saldo_acum = defaultdict(float)   # todas las cuentas, acumulado <= corte
    pl_mes = defaultdict(float)       # cuentas 4/5, mes cerrado
    pl_ytd = defaultdict(float)       # cuentas 4/5, YTD
    for f, cod, imp in lines:
        if f > corte:
            continue
        saldo_acum[cod] += imp
        if cod[:1] in ("4", "5"):
            if f >= ytd0:
                pl_ytd[cod] += imp
            if f >= per0:
                pl_mes[cod] += imp
    return saldo_acum, pl_mes, pl_ytd


def build_report(saldo_acum, pl_mes, pl_ytd):
    """Todas las líneas del estado ejecutivo. Copia adaptada de la versión Perseo."""
    act_corr = sum_prefix(saldo_acum, "11")
    act_ncor = sum_prefix(saldo_acum, "12")
    activo = sum_prefix(saldo_acum, "1")
    pas_corr = -sum_prefix(saldo_acum, "21")
    pas_ncor = -sum_prefix(saldo_acum, "22")
    pasivo = -sum_prefix(saldo_acum, "2")
    patrim3 = -sum_prefix(saldo_acum, "3")     # capital + resultados acumulados
    # Resultado ACUMULADO en el mayor (cuentas 4+5 hasta el corte).
    resultado_acum = -(sum_prefix(saldo_acum, "4") + sum_prefix(saldo_acum, "5"))
    # Resultado del EJERCICIO en curso (cuentas 4+5 del año, YTD).
    resultado_ej = -(sum_prefix(pl_ytd, "4") + sum_prefix(pl_ytd, "5"))
    patrimonio = patrim3 + resultado_acum
    patrim_resto = patrimonio - resultado_ej
    inventarios = sum_prefix(saldo_acum, "1103")
    efectivo = sum_prefix(saldo_acum, "1101")
    clientes = sum_prefix(saldo_acum, "1102")
    deuda_fin = -(sum_prefix(saldo_acum, "2104") + sum_prefix(saldo_acum, "2203"))
    cuadre = activo - (pasivo + patrimonio)

    def pl(d):
        ventas = -sum_prefix(d, "41")
        otros_ing = -sum_prefix(d, "42")
        costo = sum_prefix(d, "51")
        gv = sum_prefix(d, "52")
        ga = sum_prefix(d, "53")
        gf = sum_prefix(d, "54")
        gnd = sum_prefix(d, "55")
        ub = ventas - costo
        uop = ub - gv - ga
        un = uop + otros_ing - gf - gnd
        return dict(ventas=ventas, otros_ing=otros_ing, costo=costo, gv=gv, ga=ga,
                    gf=gf, gnd=gnd, ub=ub, uop=uop, un=un)

    mes = pl(pl_mes)
    ytd = pl(pl_ytd)

    def r(n, dnm):
        return (n / dnm) if dnm else 0.0

    ratios = dict(
        liquidez_corr=r(act_corr, pas_corr),
        prueba_acida=r(act_corr - inventarios, pas_corr),
        capital_trab=act_corr - pas_corr,
        endeud_pat=r(pasivo, patrimonio),
        endeud_act=r(pasivo, activo),
        deuda_fin_pat=r(deuda_fin, patrimonio),
        margen_bruto=r(ytd["ub"], ytd["ventas"]),
        margen_oper=r(ytd["uop"], ytd["ventas"]),
        margen_neto=r(ytd["un"], ytd["ventas"]),
        roe=r(resultado_acum, patrimonio),
        roa=r(resultado_acum, activo),
    )

    return dict(
        activo=activo, act_corr=act_corr, act_ncor=act_ncor,
        pasivo=pasivo, pas_corr=pas_corr, pas_ncor=pas_ncor,
        patrim3=patrim3, resultado_acum=resultado_acum, resultado_ej=resultado_ej,
        patrim_resto=patrim_resto, patrimonio=patrimonio,
        efectivo=efectivo, clientes=clientes, inventarios=inventarios,
        deuda_fin=deuda_fin, cuadre=cuadre,
        mes=mes, ytd=ytd, ratios=ratios,
    )


# ------------------------------------------------------------------ excel
def _workbook_respaldo(rep, cutoff, mes_lbl, ytd_lbl, gen_ts, nota):
    """Formato mínimo, sólo si no se puede importar build_workbook de Perseo."""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Resumen Ejecutivo"
    ws.column_dimensions["A"].width = 40
    ws.append(["ESTADOS FINANCIEROS (ODOO) — RESUMEN EJECUTIVO"])
    ws.append([f"Corte: {cutoff.isoformat()}   Generado: {gen_ts}"])
    ws.append([nota])
    ws.append([])
    ws.append(["Concepto", mes_lbl, ytd_lbl])
    for lbl, k in [("Ventas Netas", "ventas"), ("(-) Costo de Ventas", "costo"),
                   ("Utilidad Bruta", "ub"), ("(-) Gastos de Ventas", "gv"),
                   ("(-) Gastos de Administracion", "ga"),
                   ("Utilidad Operativa (EBIT)", "uop"), ("(+) Otros Ingresos", "otros_ing"),
                   ("(-) Gastos Financieros", "gf"), ("(-) Gastos No Deducibles", "gnd"),
                   ("Utilidad Neta (antes de imp.)", "un")]:
        ws.append([lbl, rep["mes"][k], rep["ytd"][k]])
    ws.append([])
    for lbl, k in [("Efectivo y Equivalentes", "efectivo"),
                   ("Cuentas por Cobrar (neto)", "clientes"), ("Inventarios", "inventarios"),
                   ("Activo Corriente", "act_corr"), ("Activo No Corriente", "act_ncor"),
                   ("ACTIVO TOTAL", "activo"), ("PASIVO TOTAL", "pasivo"),
                   ("PATRIMONIO TOTAL", "patrimonio"), ("Cuadre contable", "cuadre")]:
        ws.append([lbl, rep[k]])
    return wb


def construir_excel(rep, cutoff, mes_lbl, ytd_lbl, gen_ts, meta):
    """
    Arma el Excel reutilizando (importación perezosa) el formato de
    perseo_estados_financieros.build_workbook y le añade la hoja de método.
    """
    nota = (f"FUENTE: mayor contable de ODOO ({meta['compania']}, id={meta['compania_id']}) · "
            f"MODO DE MAPEO: {meta['modo'].upper()}"
            f"{' (autodetectado)' if meta['autodetectado'] else ' (forzado)'} · "
            f"Equivalencia con Perseo NO verificada hasta correr `conciliar`.")
    wb = None
    try:
        if str(PROJ) not in sys.path:
            sys.path.insert(0, str(PROJ))
        import perseo_estados_financieros as pfe   # importa openpyxl a nivel de módulo
        pfe.EMPRESA = meta["compania"]             # el encabezado dice la compañía real
        wb = pfe.build_workbook(rep, cutoff, mes_lbl, ytd_lbl, gen_ts, nota)
    except Exception as e:
        log(f"AVISO: no pude reutilizar el formato de perseo_estados_financieros ({e}); "
            f"uso el formato de respaldo.")
        wb = _workbook_respaldo(rep, cutoff, mes_lbl, ytd_lbl, gen_ts, nota)

    # ---- hoja de método: el modo de mapeo tiene que quedar imposible de ignorar
    ws = wb.create_sheet("Metodo y Fuente")
    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 78
    filas = [
        ("ORIGEN DE LOS DATOS", ""),
        ("Sistema", "Odoo (account.move.line, asientos contabilizados)"),
        ("Instancia", meta.get("url", "")),
        ("Compañía", f"{meta['compania']} (id={meta['compania_id']})"),
        ("Corte", cutoff.isoformat()),
        ("Líneas leídas / clasificadas", f"{meta['n_leidas']} / {meta['n_clasificadas']}"),
        ("Rango de fechas del mayor", f"{meta.get('primera_fecha')} → {meta.get('ultima_fecha')}"),
        ("Generado", meta.get("generado", "")),
        ("", ""),
        ("MODO DE MAPEO", meta["modo"].upper()
            + (" (autodetectado)" if meta["autodetectado"] else " (forzado)")),
        ("Criterio", f"{meta['prefijos_cubiertos']} de {len(PREFIJOS_PERSEO)} prefijos PUC "
                     f"con cuentas (umbral {MIN_PREFIJOS_PUC})"),
        ("puc", "clasifica por prefijo de código, igual que Perseo"),
        ("tipo", "clasifica por account_type de Odoo con códigos PUC sintéticos"),
        ("", ""),
        ("ADVERTENCIA", "Los importes NO son comparables con la serie histórica de Perseo "
                        "hasta correr: python3 odoo_estados_financieros.py conciliar"),
    ]
    for a, b in filas:
        ws.append([a, b])
    ws.append(["", ""])
    ws.append(["ADVERTENCIAS", ""])
    for i, adv in enumerate(meta.get("advertencias", []) or ["(ninguna)"], 1):
        ws.append([f"{i}", adv])
    ws.append(["", ""])
    ws.append(["COBERTURA DE PREFIJOS PUC", ""])
    for p in PREFIJOS_PERSEO:
        ws.append([p, meta.get("cobertura", {}).get(p, 0)])
    return wb


# ------------------------------------------------------------------ salida JSON
def rubros_de(rep):
    """Rubros principales, los mismos que se concilian contra Perseo."""
    return {
        "ventas_ytd": round(rep["ytd"]["ventas"], 2),
        "costo_ytd": round(rep["ytd"]["costo"], 2),
        "utilidad_bruta_ytd": round(rep["ytd"]["ub"], 2),
        "utilidad_operativa_ytd": round(rep["ytd"]["uop"], 2),
        "utilidad_neta_ytd": round(rep["ytd"]["un"], 2),
        "ventas_mes": round(rep["mes"]["ventas"], 2),
        "utilidad_neta_mes": round(rep["mes"]["un"], 2),
        "activo": round(rep["activo"], 2),
        "activo_corriente": round(rep["act_corr"], 2),
        "pasivo": round(rep["pasivo"], 2),
        "pasivo_corriente": round(rep["pas_corr"], 2),
        "patrimonio": round(rep["patrimonio"], 2),
        "efectivo": round(rep["efectivo"], 2),
        "clientes": round(rep["clientes"], 2),
        "inventarios": round(rep["inventarios"], 2),
        "deuda_financiera": round(rep["deuda_fin"], 2),
        "cuadre": round(rep["cuadre"], 2),
    }


def guardar_json(rep, meta, y_fin, m_fin):
    doc = {
        "generado": meta.get("generado"),
        "fuente": "odoo",
        "url": meta.get("url"),
        "compania": meta.get("compania"),
        "compania_id": meta.get("compania_id"),
        "corte": meta.get("corte"),
        "periodo": f"{y_fin}-{m_fin:02d}",
        "modo_mapeo": meta.get("modo"),
        "modo_autodetectado": meta.get("autodetectado"),
        "prefijos_cubiertos": meta.get("prefijos_cubiertos"),
        "cobertura_prefijos": meta.get("cobertura"),
        "rango_fechas": {"primera": meta.get("primera_fecha"),
                         "ultima": meta.get("ultima_fecha")},
        "lineas": {"leidas": meta.get("n_leidas"), "clasificadas": meta.get("n_clasificadas"),
                   "descartadas": meta.get("n_descartadas")},
        "advertencias": meta.get("advertencias", []),
        "rubros": rubros_de(rep),
        "mes": {k: round(v, 2) for k, v in rep["mes"].items()},
        "ytd": {k: round(v, 2) for k, v in rep["ytd"].items()},
        "ratios": {k: round(v, 6) for k, v in rep["ratios"].items()},
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    p = OUT_DIR / f"eeff_odoo_{y_fin}-{m_fin:02d}.json"
    p.write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    return p, doc


# ------------------------------------------------------------------ pipeline
def parse_periodo(args):
    """Devuelve (cutoff, año, mes) a partir de un 'YYYY-MM' o del último mes cerrado."""
    for a in args:
        if len(a) >= 7 and a[:4].isdigit() and a[4] == "-" and a[5:7].isdigit():
            y, m = int(a[:4]), int(a[5:7])
            return month_end(y, m), y, m
    y, m = last_closed_month(datetime.date.today())
    return month_end(y, m), y, m


def parse_modo(args):
    """--modo=puc|tipo  o  EEFF_MODO=puc|tipo. None = autodetectar."""
    for a in args:
        if a.startswith("--modo="):
            v = a.split("=", 1)[1].strip().lower()
            if v not in ("puc", "tipo"):
                sys.exit("ERROR: --modo debe ser 'puc' o 'tipo'.")
            return v
    v = (os.environ.get("EEFF_MODO") or "").strip().lower()
    if v in ("puc", "tipo"):
        return v
    if v:
        sys.exit("ERROR: EEFF_MODO debe ser 'puc' o 'tipo'.")
    return None


def extraer(cutoff, y_fin, m_fin, modo_forzado=None):
    """Todo el trabajo contra Odoo. Devuelve (rep, meta, saldo_por_cuenta, id_a_cta)."""
    advertencias = []
    cfg = load_config()
    od = Odoo(cfg)
    od.authenticate()
    log(f"Conectado a {cfg['url']} db={cfg['db']} uid={od.uid} "
        f"v={od.version.get('server_version')}")

    comps = od.kw("res.company", "search_read", [[]],
                  {"fields": ["id", "name", "currency_id"]})
    comp_ids = [c["id"] for c in comps]
    ec = identificar_ecuador(comps, cfg.get("company_map", {}), advertencias)
    moneda = (ec.get("currency_id") or [0, "?"])[1]
    log(f"Compañía Ecuador: «{ec['name']}» (id={ec['id']}, {moneda})")
    if moneda != "USD":
        advertencias.append(f"La compañía de Ecuador reporta en {moneda}, no en USD. "
                            f"Los importes del reporte están en {moneda}.")

    log("Leyendo plan de cuentas…")
    cuentas = leer_cuentas(od, ec["id"], comp_ids)
    modo, cob, cubiertos, auto = elegir_modo(cuentas, modo_forzado)
    log(f"Plan de cuentas: {len(cuentas)} cuentas · prefijos PUC cubiertos "
        f"{cubiertos}/{len(PREFIJOS_PERSEO)} · MODO = {modo.upper()}"
        f"{' (autodetectado)' if auto else ' (forzado)'}")
    advertencias.extend(advertencias_de_modo(modo, cubiertos, cob))

    id_a_puc, id_a_cta, sin_mapear = construir_mapa(cuentas, modo, advertencias)

    log(f"Leyendo mayor hasta {cutoff.isoformat()}…")
    lines, info, saldo_cta = leer_lineas(od, ec["id"], comp_ids, cutoff, id_a_puc,
                                         advertencias)
    if not lines:
        # Causa habitual tras la migración: el corte pedido es anterior a la fecha en
        # que Ecuador entró a Odoo, así que no hay nada que leer (no es un fallo).
        primero = primer_asiento(od, ec["id"], comp_ids)
        if primero and primero > cutoff.isoformat():
            sys.exit(
                f"\nNO HAY DATOS PARA ESE PERÍODO — no es un error del script.\n"
                f"  Ecuador entró a Odoo el {primero}; pediste corte al {cutoff.isoformat()}.\n"
                f"  Todo lo anterior vive únicamente en Perseo.\n\n"
                f"  Para ese mes usa:  python3 perseo_estados_financieros.py\n"
                f"  Desde Odoo, el primer corte posible es fin de {primero[:7]}.\n")
        sys.exit("ERROR: el mayor de Odoo no devolvió líneas clasificables. "
                 "Corre `python3 odoo_estados_financieros.py diag` para ver por qué.")

    saldo_acum, pl_mes, pl_ytd = compute_statements(lines, cutoff, y_fin, m_fin)
    rep = build_report(saldo_acum, pl_mes, pl_ytd)
    if abs(rep["cuadre"]) > 1:
        advertencias.append(f"El balance no cuadra por {rep['cuadre']:,.2f}: hay cuentas "
                            f"fuera del mapeo o asientos sin contrapartida clasificada.")

    meta = {
        "generado": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "url": cfg["url"], "compania": ec["name"], "compania_id": ec["id"],
        "moneda": moneda, "corte": cutoff.isoformat(),
        "modo": modo, "autodetectado": auto,
        "prefijos_cubiertos": cubiertos, "cobertura": cob,
        "n_cuentas": len(cuentas), "n_sin_mapear": len(sin_mapear),
        "advertencias": advertencias,
    }
    meta.update({"n_leidas": info["n_leidas"], "n_clasificadas": info["n_clasificadas"],
                 "n_descartadas": info["n_descartadas"],
                 "primera_fecha": info["primera_fecha"], "ultima_fecha": info["ultima_fecha"]})
    return rep, meta, saldo_cta, id_a_cta


def run(args):
    cutoff, y_fin, m_fin = parse_periodo(args)
    modo_forzado = parse_modo(args)
    rep, meta, _, _ = extraer(cutoff, y_fin, m_fin, modo_forzado)

    mes_lbl = f"{MESES[m_fin]}-{y_fin}"
    ytd_lbl = f"YTD {y_fin} (Ene-{MESES[m_fin]})"
    wb = construir_excel(rep, cutoff, mes_lbl, ytd_lbl, meta["generado"], meta)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    p1 = OUT_DIR / f"Estados_Financieros_Ejecutivo_ODOO_{y_fin}-{m_fin:02d}.xlsx"
    p2 = OUT_DIR / "Estados_Financieros_Ejecutivo_ODOO_ULTIMO.xlsx"
    wb.save(p1)
    try:
        wb.save(p2)
    except OSError:
        pass
    pj, _ = guardar_json(rep, meta, y_fin, m_fin)

    log(f"OK · MODO={meta['modo'].upper()} · Ventas YTD={rep['ytd']['ventas']:,.0f} · "
        f"UtilNeta YTD={rep['ytd']['un']:,.0f} · Activo={rep['activo']:,.0f} · "
        f"Cuadre={rep['cuadre']:,.2f}")
    for adv in meta["advertencias"]:
        log(f"  AVISO: {adv}")
    log(f"-> {p1}")
    log(f"-> {pj}")
    log("RECORDATORIO: corre `conciliar` contra el mes equivalente de Perseo antes de "
        "usar estos números fuera de finanzas.")


# ------------------------------------------------------------------ diag
def run_diag(args):
    cutoff, y_fin, m_fin = parse_periodo(args)
    modo_forzado = parse_modo(args)
    rep, meta, saldo_cta, id_a_cta = extraer(cutoff, y_fin, m_fin, modo_forzado)

    print("\n" + "=" * 78)
    print("DIAGNÓSTICO — ESTADOS FINANCIEROS DESDE ODOO")
    print("=" * 78)
    print(f"Instancia          : {meta['url']}")
    print(f"Compañía Ecuador   : {meta['compania']} (id={meta['compania_id']}, {meta['moneda']})")
    print(f"Corte              : {meta['corte']}  ({MESES[m_fin]}-{y_fin})")
    print(f"Líneas del mayor   : {meta['n_leidas']} leídas · {meta['n_clasificadas']} "
          f"clasificadas · {meta['n_descartadas']} descartadas")
    print(f"Rango de fechas    : {meta['primera_fecha']} → {meta['ultima_fecha']}")
    print(f"Plan de cuentas    : {meta['n_cuentas']} cuentas ({meta['n_sin_mapear']} sin mapear)")
    print(f"MODO DE MAPEO      : {meta['modo'].upper()}"
          f"{' (autodetectado)' if meta['autodetectado'] else ' (forzado)'}"
          f"  ·  prefijos cubiertos {meta['prefijos_cubiertos']}/{len(PREFIJOS_PERSEO)}")

    print("\nCOBERTURA DE PREFIJOS PUC (los que usan los EEFF de Perseo)")
    for p in PREFIJOS_PERSEO:
        n = meta["cobertura"].get(p, 0)
        print(f"   {'OK ' if n else '!! '}{p:<6} {n:>5} cuentas")

    doc = leer_descubrimiento()
    if doc:
        cob_desc = (doc.get("plan_cuentas") or {}).get("cobertura_prefijos_perseo")
        if cob_desc:
            dif = [p for p in PREFIJOS_PERSEO
                   if bool(cob_desc.get(p, 0)) != bool(meta["cobertura"].get(p, 0))]
            print(f"\ndescubrimiento_odoo.json ({doc.get('generado')}): "
                  f"{'coincide' if not dif else 'DIFIERE en ' + ', '.join(dif)}")

    print("\nTOP 20 CUENTAS POR |SALDO| ACUMULADO")
    top = sorted(saldo_cta.items(), key=lambda kv: -abs(kv[1]))[:20]
    for aid, val in top:
        a = id_a_cta.get(aid, {})
        print(f"   {a.get('code', '?'):<14} {val:>18,.2f}  {a.get('account_type', '?'):<22} "
              f"{a.get('name', '')[:34]}")

    print("\nRUBROS CALCULADOS")
    for k, v in rubros_de(rep).items():
        print(f"   {k:<24} {v:>18,.2f}")

    print("\nADVERTENCIAS")
    for adv in meta["advertencias"] or ["(ninguna)"]:
        print(f"   - {adv}")
    print("=" * 78 + "\n")


# ------------------------------------------------------------------ conciliar
# Etiquetas del Excel de Perseo -> (columna, rubro equivalente en el JSON Odoo).
# Col B = mes cerrado en el Estado de Resultados y saldo en el Balance; col C = YTD.
MAPA_CONCILIACION = [
    ("Ventas Netas",                 "C", "ventas_ytd"),
    ("(-) Costo de Ventas",          "C", "costo_ytd"),
    ("Utilidad Bruta",               "C", "utilidad_bruta_ytd"),
    ("Utilidad Operativa (EBIT)",    "C", "utilidad_operativa_ytd"),
    ("Utilidad Neta (antes de imp.)", "C", "utilidad_neta_ytd"),
    ("Efectivo y Equivalentes",      "B", "efectivo"),
    ("Cuentas por Cobrar (neto)",    "B", "clientes"),
    ("Inventarios",                  "B", "inventarios"),
    ("Activo Corriente",             "B", "activo_corriente"),
    ("ACTIVO TOTAL",                 "B", "activo"),
    ("PASIVO TOTAL",                 "B", "pasivo"),
    ("PATRIMONIO TOTAL",             "B", "patrimonio"),
]


def leer_perseo(y, m):
    """
    Rubros del reporte de Perseo del mismo mes. Devuelve (rubros, origen) o
    (None, motivo). Prefiere un JSON si existiera; si no, lee el Excel.
    """
    pj = OUT_DIR / f"eeff_perseo_{y}-{m:02d}.json"
    if pj.exists():
        try:
            d = json.loads(pj.read_text(encoding="utf-8"))
            return d.get("rubros") or {}, str(pj)
        except Exception as e:
            log(f"AVISO: no pude leer {pj}: {e}")
    px = OUT_DIR / f"Estados_Financieros_Ejecutivo_{y}-{m:02d}.xlsx"
    if not px.exists():
        return None, (f"No existe ni {pj.name} ni {px.name} en {OUT_DIR}. "
                      f"Genera el reporte de Perseo de ese mes o copia el archivo.")
    try:
        from openpyxl import load_workbook
    except ImportError:
        return None, "openpyxl no está instalado: no puedo leer el Excel de Perseo."
    ws = load_workbook(px, data_only=True).active
    # label (columna A, sin sangría) -> {"B": valor, "C": valor}
    encontrados = {}
    for fila in ws.iter_rows(min_row=1, max_col=3, values_only=True):
        etiqueta = (str(fila[0]).strip() if fila[0] is not None else "")
        if not etiqueta:
            continue
        b = fila[1] if isinstance(fila[1], (int, float)) else None
        c = fila[2] if isinstance(fila[2], (int, float)) else None
        if b is None and c is None:
            continue                      # fila de KPI o encabezado, no de detalle
        encontrados.setdefault(etiqueta, {"B": b, "C": c})
    rubros = {}
    for etiqueta, col, rubro in MAPA_CONCILIACION:
        v = (encontrados.get(etiqueta) or {}).get(col)
        if v is not None:
            rubros[rubro] = float(v)
    return rubros, str(px)


def run_conciliar(args):
    cutoff, y_fin, m_fin = parse_periodo(args)
    per, origen_per = leer_perseo(y_fin, m_fin)
    if per is None:
        sys.exit(f"ERROR: {origen_per}")

    # El lado Odoo: reutiliza el JSON del mes si ya existe (permite conciliar sin
    # volver a golpear Odoo); si no, lo calcula.
    pj = OUT_DIR / f"eeff_odoo_{y_fin}-{m_fin:02d}.json"
    if pj.exists() and "--recalcular" not in args:
        d = json.loads(pj.read_text(encoding="utf-8"))
        odoo_r = d.get("rubros") or {}
        modo = d.get("modo_mapeo")
        origen_odoo = f"{pj.name} (generado {d.get('generado')})"
        advs = d.get("advertencias", [])
    else:
        rep, meta, _, _ = extraer(cutoff, y_fin, m_fin, parse_modo(args))
        odoo_r = rubros_de(rep)
        modo = meta["modo"]
        origen_odoo = "consulta en vivo a Odoo"
        advs = meta["advertencias"]
        guardar_json(rep, meta, y_fin, m_fin)

    print("\n" + "=" * 86)
    print(f"CONCILIACIÓN PERSEO vs ODOO — {MESES[m_fin]}-{y_fin}")
    print("=" * 86)
    print(f"Perseo : {origen_per}")
    print(f"Odoo   : {origen_odoo}   ·   MODO DE MAPEO = {str(modo).upper()}")
    print("-" * 86)
    print(f"{'Rubro':<26}{'Perseo':>18}{'Odoo':>18}{'Dif. abs':>14}{'Dif. %':>10}")
    print("-" * 86)
    peor = 0.0
    n_ok = n_rev = 0
    for _, _, rubro in MAPA_CONCILIACION:
        if rubro not in per:
            continue
        p = float(per[rubro])
        o = float(odoo_r.get(rubro, 0.0))
        dif = o - p
        pct = (dif / abs(p)) if p else (0.0 if abs(dif) < 0.01 else float("inf"))
        marca = "  OK" if abs(pct) <= 0.01 or abs(dif) < 1 else "  !!"
        if marca == "  OK":
            n_ok += 1
        else:
            n_rev += 1
            peor = max(peor, abs(pct) if pct != float("inf") else 999)
        pct_txt = "  n/a" if pct == float("inf") else f"{pct*100:>9.1f}%"
        print(f"{rubro:<26}{p:>18,.0f}{o:>18,.0f}{dif:>14,.0f}{pct_txt}{marca}")
    print("-" * 86)
    print(f"Rubros conciliados: {n_ok} dentro de ±1% · {n_rev} a revisar")
    if modo == "tipo":
        print("\n>>> El mapeo es por account_type (modo TIPO). Diferencias en el desglose de")
        print("    gastos son ESPERADAS: Odoo no separa gastos de ventas de administración.")
        print("    Lo que debe cuadrar es Ventas, Costo, Utilidad Neta, Activo, Pasivo y")
        print("    Patrimonio. Si esos cuadran, el cambio de fuente es seguro.")
    if advs:
        print("\nADVERTENCIAS DEL LADO ODOO")
        for a in advs:
            print(f"   - {a}")
    print("=" * 86 + "\n")
    # Siempre sale con 0: conciliar es una herramienta de análisis, no una prueba.
    # El juicio sobre si la diferencia es aceptable lo hace finanzas, no el script.
    return 0


# ------------------------------------------------------------------ autotest
def _cuenta(code, name, tipo, _id=[0]):
    _id[0] += 1
    return {"id": _id[0], "code": code, "code_limpio": code_limpio(code),
            "name": name, "account_type": tipo, "company_ids": [1]}


def autotest():
    """
    Prueba OFFLINE de la lógica de clasificación: no toca la red ni necesita
    openpyxl. Corre el MISMO libro contable con dos planes de cuentas distintos
    (uno PUC estilo Perseo y otro con códigos ajenos al PUC) y verifica que
    ambos modos produzcan los mismos estados financieros.
    """
    fallos = []

    def chk(cond, msg):
        if not cond:
            fallos.append(msg)

    def casi(a, b, tol=0.01):
        return abs(a - b) <= tol

    # --- Plan A: PUC (como Perseo). Debe autodetectar modo "puc".
    plan_puc = [
        _cuenta("1.1.01.01", "Bancos",                    "asset_cash"),
        _cuenta("1.1.02.01", "Clientes nacionales",       "asset_receivable"),
        _cuenta("1.1.03.01", "Inventario de mercadería",  "asset_current"),
        _cuenta("1.2.01.01", "Muebles y enseres",         "asset_fixed"),
        _cuenta("2.1.01.01", "Proveedores locales",       "liability_payable"),
        _cuenta("2.1.04.01", "Obligaciones financieras bancarias", "liability_current"),
        _cuenta("3.1.01.01", "Capital social",            "equity"),
        _cuenta("4.1.01.01", "Ventas de mercadería",      "income"),
        _cuenta("4.2.01.01", "Otros ingresos",            "income_other"),
        _cuenta("5.1.01.01", "Costo de ventas",           "expense_direct_cost"),
        _cuenta("5.2.01.01", "Gastos de ventas",          "expense"),
        _cuenta("5.3.01.01", "Gastos de administración",  "expense"),
        _cuenta("5.4.01.01", "Intereses bancarios",       "expense"),
    ]
    # --- Plan B: códigos ajenos al PUC (catálogo tipo SRI). Debe dar modo "tipo".
    plan_sri = [
        _cuenta("100101", "Bancos",                       "asset_cash"),
        _cuenta("100201", "Clientes nacionales",          "asset_receivable"),
        _cuenta("100301", "Inventario de mercadería",     "asset_current"),
        _cuenta("100401", "Anticipos a proveedores",      "asset_prepayments"),
        _cuenta("150101", "Muebles y enseres",            "asset_fixed"),
        _cuenta("200101", "Proveedores locales",          "liability_payable"),
        _cuenta("200201", "Obligaciones financieras bancarias", "liability_current"),
        _cuenta("250101", "Préstamo bancario largo plazo", "liability_non_current"),
        _cuenta("300101", "Capital social",               "equity"),
        _cuenta("400101", "Ventas de mercadería",         "income"),
        _cuenta("400201", "Otros ingresos",               "income_other"),
        _cuenta("600101", "Costo de ventas",              "expense_direct_cost"),
        _cuenta("700101", "Gastos generales",             "expense"),
    ]

    # Índice por nombre para armar el mismo libro contable en ambos planes.
    def por_nombre(plan):
        return {a["name"]: a["id"] for a in plan}

    # Libro contable sintético (todos los asientos cuadran):
    #   apertura 5.000 banco/capital · préstamo 2.000 · compra inventario 3.000 a crédito
    #   venta 1.000 a crédito · costo 600 · gasto 200 · otros ingresos 50
    def libro(idx, cuenta_gasto):
        return [
            ("20251231", idx["Bancos"],                 5000.0),
            ("20251231", idx["Capital social"],        -5000.0),
            ("20260201", idx["Bancos"],                 2000.0),
            ("20260201", idx["Obligaciones financieras bancarias"], -2000.0),
            ("20260115", idx["Inventario de mercadería"], 3000.0),
            ("20260115", idx["Proveedores locales"],   -3000.0),
            ("20260610", idx["Clientes nacionales"],    1000.0),
            ("20260610", idx["Ventas de mercadería"],  -1000.0),
            ("20260610", idx["Costo de ventas"],         600.0),
            ("20260610", idx["Inventario de mercadería"], -600.0),
            ("20260620", idx[cuenta_gasto],              200.0),
            ("20260620", idx["Bancos"],                 -200.0),
            ("20260625", idx["Bancos"],                   50.0),
            ("20260625", idx["Otros ingresos"],          -50.0),
        ]

    esperado = dict(ventas=1000.0, costo=600.0, ub=400.0, uop=200.0, un=250.0,
                    otros=50.0, activo=10250.0, pasivo=5000.0, patrimonio=5250.0,
                    efectivo=6850.0, clientes=1000.0, inventarios=2400.0,
                    deuda_fin=2000.0, resultado_ej=250.0)
    cutoff = datetime.date(2026, 6, 30)

    for etiqueta, plan, gasto, modo_esperado in (
            ("puc", plan_puc, "Gastos de ventas", "puc"),
            ("tipo", plan_sri, "Gastos generales", "tipo")):
        modo, cob, cubiertos, auto = elegir_modo(plan, None)
        chk(modo == modo_esperado,
            f"[{etiqueta}] autodetección dio '{modo}' y se esperaba '{modo_esperado}' "
            f"(prefijos cubiertos={cubiertos})")
        chk(auto is True, f"[{etiqueta}] la autodetección debería marcarse como automática")

        advs = []
        id_a_puc, _, sin_mapear = construir_mapa(plan, modo, advs)
        chk(not sin_mapear, f"[{etiqueta}] quedaron {len(sin_mapear)} cuentas sin mapear")

        lines = []
        for f, aid, imp in libro(por_nombre(plan), gasto):
            puc = id_a_puc.get(aid)
            chk(puc is not None, f"[{etiqueta}] cuenta id={aid} sin código PUC asignado")
            if puc:
                lines.append((f, puc, imp))

        sa, pm, py = compute_statements(lines, cutoff, 2026, 6)
        rep = build_report(sa, pm, py)

        pruebas = [
            ("ventas YTD",      rep["ytd"]["ventas"],  esperado["ventas"]),
            ("costo YTD",       rep["ytd"]["costo"],   esperado["costo"]),
            ("ut. bruta YTD",   rep["ytd"]["ub"],      esperado["ub"]),
            ("ut. operativa",   rep["ytd"]["uop"],     esperado["uop"]),
            ("ut. neta YTD",    rep["ytd"]["un"],      esperado["un"]),
            ("otros ingresos",  rep["ytd"]["otros_ing"], esperado["otros"]),
            ("ventas del mes",  rep["mes"]["ventas"],  esperado["ventas"]),
            ("activo",          rep["activo"],         esperado["activo"]),
            ("pasivo",          rep["pasivo"],         esperado["pasivo"]),
            ("patrimonio",      rep["patrimonio"],     esperado["patrimonio"]),
            ("efectivo",        rep["efectivo"],       esperado["efectivo"]),
            ("clientes",        rep["clientes"],       esperado["clientes"]),
            ("inventarios",     rep["inventarios"],    esperado["inventarios"]),
            ("deuda financiera", rep["deuda_fin"],     esperado["deuda_fin"]),
            ("resultado ejercicio", rep["resultado_ej"], esperado["resultado_ej"]),
        ]
        for nombre, obtenido, esp in pruebas:
            chk(casi(obtenido, esp),
                f"[{etiqueta}] {nombre}: obtenido {obtenido:,.2f}, esperado {esp:,.2f}")

        # La identidad contable tiene que cerrar en ambos modos.
        chk(casi(rep["cuadre"], 0.0),
            f"[{etiqueta}] el balance no cuadra: Activo - (Pasivo + Patrimonio) = "
            f"{rep['cuadre']:,.2f}")
        chk(casi(rep["activo"], rep["pasivo"] + rep["patrimonio"]),
            f"[{etiqueta}] Activo ({rep['activo']:,.2f}) != Pasivo + Patrimonio "
            f"({rep['pasivo'] + rep['patrimonio']:,.2f})")
        chk(casi(rep["ratios"]["margen_bruto"], 0.4),
            f"[{etiqueta}] margen bruto {rep['ratios']['margen_bruto']:.4f} != 0.4")
        print(f"  [{etiqueta}] modo={modo} · ventas={rep['ytd']['ventas']:,.0f} "
              f"· ut.neta={rep['ytd']['un']:,.0f} · activo={rep['activo']:,.0f} "
              f"· cuadre={rep['cuadre']:,.2f}")

    # --- pruebas puntuales de las heurísticas del modo tipo
    chk(_tipo_a_puc("asset_current", "Inventario de mercadería") == "1103",
        "heurística: un inventario debería mapear a 1103")
    chk(_tipo_a_puc("asset_current", "Impuestos anticipados") == "1104",
        "heurística: un activo corriente cualquiera debería mapear a 1104")
    chk(_tipo_a_puc("liability_non_current", "Préstamo bancario LP") == "2203",
        "heurística: un préstamo de LP debería mapear a 2203")
    chk(_tipo_a_puc("off_balance", "Cuentas de orden") is None,
        "las cuentas de orden deberían quedar fuera del reporte")
    # El separador '.' del código sintético evita colisiones de prefijo.
    chk(not "2201.250101".startswith("2203"),
        "el código sintético de pasivo no corriente no debe colisionar con 2203")

    # --- la conversión de fecha y de código no puede cambiar
    chk(ymd("2026-07-31") == "20260731", "ymd() no convirtió una fecha ISO")
    chk(code_limpio("1.1-02 05") == "110205", "code_limpio() no limpió el código")

    print("")
    if fallos:
        print(f"AUTOTEST: {len(fallos)} FALLO(S)")
        for f in fallos:
            print(f"  ✗ {f}")
        return 1
    print("AUTOTEST: OK — ambos modos (puc y tipo) producen los mismos estados "
          "financieros y el balance cuadra.")
    return 0


# ------------------------------------------------------------------ main
def main():
    args = sys.argv[1:]
    cmd = args[0] if args and not args[0].startswith("-") else ""
    if cmd == "autotest":
        sys.exit(autotest())
    if cmd == "diag":
        run_diag(args[1:])
        return
    if cmd == "conciliar":
        sys.exit(run_conciliar(args[1:]))
    if cmd in ("-h", "--help", "ayuda"):
        print(__doc__)
        return
    run(args)


if __name__ == "__main__":
    main()
