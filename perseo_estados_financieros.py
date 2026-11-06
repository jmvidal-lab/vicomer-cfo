#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
perseo_estados_financieros.py
=============================
Genera un ANALISIS EJECUTIVO de estados financieros (VICOMER S.A.S. - Ecuador)
directamente desde el mayor contable de Perseo, via el API REST.

Fuente unica de verdad: los ASIENTOS CONTABLES (asientoscontables_consulta).
Cada linea de detalle trae {codigocontable, importe} donde:
    importe > 0  = DEBITO      importe < 0 = CREDITO
El codigo contable de Perseo (ej. "1.1.02.05.01") equivale al plan de cuentas
sin puntos ("11020501" = Clientes). Estructura PUC:
    1 = Activo      2 = Pasivo     3 = Patrimonio
    4 = Ingresos    5 = Egresos (51 Costo, 52 G.Ventas, 53 G.Admin,
                                 54 G.Financieros, 55 No Deducibles)

Como todo asiento cuadra (sum debitos = sum creditos), la identidad
    Activo = Pasivo + Patrimonio + Resultado del Ejercicio
se cumple por construccion.

  Balance General : saldos ACUMULADOS de las cuentas 1/2/3 hasta el corte.
  Estado Resultados: movimientos de las cuentas 4/5 del periodo.
  Periodo por defecto: ultimo mes CERRADO + acumulado del anio (YTD).

Salida:
  ~/Claude/Projects/CFO VICOMER/Finanzas/Estados_Financieros_Ejecutivo_YYYY-MM.xlsx
  + copia de nombre fijo  Estados_Financieros_Ejecutivo_ULTIMO.xlsx

El api_key se lee de (en orden):
  1) variable de entorno  PERSEO_API_KEY
  2) archivo              ~/.perseo_apikey        (recomendado, chmod 600)
  3) archivo              <proyecto>/perseo_apikey.txt

Dependencia:  pip3 install --user openpyxl
Uso:
  python3 perseo_estados_financieros.py                # ultimo mes cerrado
  python3 perseo_estados_financieros.py 2026-06        # corte a fin de jun-2026
  python3 perseo_estados_financieros.py 2026-06 2019   # + anio de arranque del mayor
"""

import os
import sys
import json
import ssl
import calendar
import datetime
import urllib.request
import urllib.error
from pathlib import Path
from collections import defaultdict

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# ------------------------------------------------------------------ config
BASE       = "https://perseo-data-c1.app/api"
URL_ASIENTOS = f"{BASE}/asientoscontables_consulta"
URL_CUENTAS  = f"{BASE}/cuentascontables_consulta"

PROJ    = Path.home() / "Claude" / "Projects" / "CFO VICOMER"
OUT_DIR = PROJ / "Finanzas"

# Anio desde el cual se acumula el mayor para el Balance (incluye asiento de
# apertura). Debe ser anterior al primer movimiento contable de la empresa.
DEFAULT_START_YEAR = 2019

EMPRESA = "VICOMER S.A.S."

# --------------------------------------------------------------- api key
def get_api_key() -> str:
    key = os.environ.get("PERSEO_API_KEY")
    if key:
        return key.strip()
    for p in (Path.home() / ".perseo_apikey", PROJ / "perseo_apikey.txt"):
        if p.exists():
            return p.read_text(encoding="utf-8").strip()
    sys.exit("ERROR: no se encontro el api_key. Define PERSEO_API_KEY o crea "
             "~/.perseo_apikey")

# --------------------------------------------------------------- http
def _post_raw(url: str, payload: dict, timeout: int = 300):
    """Devuelve (status, content_type, texto_crudo)."""
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json",
                 "Accept": "application/json"}, method="POST")
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read().decode("utf-8", "ignore")
            return resp.status, resp.headers.get("Content-Type", ""), raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "ignore")
        return e.code, e.headers.get("Content-Type", ""), raw
    except urllib.error.URLError as e:
        raise RuntimeError(f"conexion: {e.reason}")

def _post(url: str, payload: dict, timeout: int = 300) -> dict:
    status, ctype, raw = _post_raw(url, payload, timeout)
    raw = raw.strip()
    if not raw:
        return {}                      # cuerpo vacio = sin datos en el rango
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError(f"HTTP {status} respuesta no-JSON "
                           f"({ctype}; {len(raw)} bytes): {raw[:200]}")

def fetch_asientos(api_key: str, desde: str, hasta: str) -> list:
    """Trae los asientos en el rango [desde, hasta] (formato YYYYMMDD)."""
    data = _post(URL_ASIENTOS, {"api_key": api_key,
                                "fechadesde": desde, "fechahasta": hasta})
    if isinstance(data, dict) and data.get("fault"):
        raise RuntimeError(f"API: {data['fault'].get('faultstring')}")
    if isinstance(data, dict):
        return data.get("asiento", []) or []
    return data or []

def fetch_cuentas(api_key: str) -> dict:
    """Mapa codigo(sin puntos) -> descripcion del plan de cuentas."""
    try:
        data = _post(URL_CUENTAS, {"api_key": api_key})
        cuentas = data.get("cuenta", []) if isinstance(data, dict) else (data or [])
    except RuntimeError:
        return {}
    m = {}
    for c in cuentas:
        cod = _code(c.get("codigocontable", ""))
        if cod:
            m[cod] = str(c.get("descripcion", "")).strip()
    return m

# --------------------------------------------------------------- helpers
def _code(s) -> str:
    return str(s or "").replace(".", "").strip()

def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0

def _fecha(s) -> str:
    s = str(s or "")
    return s[:8] if (len(s) >= 8 and s[:8].isdigit()) else s[:10].replace("-", "")

def last_closed_month(today: datetime.date):
    """Devuelve (anio, mes) del ultimo mes CERRADO respecto de hoy."""
    first = today.replace(day=1)
    prev = first - datetime.timedelta(days=1)
    return prev.year, prev.month

def month_end(y: int, m: int) -> datetime.date:
    return datetime.date(y, m, calendar.monthrange(y, m)[1])

# --------------------------------------------------------------- extraccion mayor
def _extract(asientos, lines) -> int:
    """Vuelca las lineas de detalle no anuladas de una lista de asientos."""
    for a in asientos:
        if a.get("anulado"):
            continue
        f = _fecha(a.get("fecha"))
        for det in a.get("detalle", []) or []:
            if det.get("anulado"):
                continue
            cod = _code(det.get("codigocontable"))
            if not cod:
                continue
            lines.append((f, cod, _num(det.get("importe"))))
    return len(asientos)

def collect_lines(api_key: str, start_year: int, cutoff: datetime.date):
    """Recorre el mayor por ANIO (con fallback mensual) y devuelve una lista de
    (fecha, codigo, importe) de todas las lineas de detalle no anuladas."""
    lines = []
    total_asientos = 0
    for y in range(start_year, cutoff.year + 1):
        a0 = datetime.date(y, 1, 1)
        a1 = min(datetime.date(y, 12, 31), cutoff)
        try:
            asientos = fetch_asientos(api_key, a0.strftime("%Y%m%d"),
                                      a1.strftime("%Y%m%d"))
            n = _extract(asientos, lines)
            total_asientos += n
            print(f"[INFO] {y}: asientos={n}  (acumulado lineas={len(lines)})")
        except RuntimeError as e:
            # fallback: reintenta mes por mes ese anio
            print(f"[WARN] {y} anual fallo ({e}); reintentando por mes...",
                  file=sys.stderr)
            mm = 1
            while datetime.date(y, mm, 1) <= a1:
                d0 = datetime.date(y, mm, 1)
                d1 = min(month_end(y, mm), cutoff)
                try:
                    asi = fetch_asientos(api_key, d0.strftime("%Y%m%d"),
                                         d1.strftime("%Y%m%d"))
                    total_asientos += _extract(asi, lines)
                except RuntimeError as e2:
                    print(f"[WARN] {y}-{mm:02d}: {e2}", file=sys.stderr)
                mm += 1
    print(f"[INFO] TOTAL asientos={total_asientos}  lineas={len(lines)}  "
          f"corte={cutoff.isoformat()}")
    return lines

# --------------------------------------------------------------- agregacion
def sum_prefix(saldos: dict, prefix: str) -> float:
    """Suma los saldos de las cuentas HOJA cuyo codigo empieza con prefix."""
    return sum(v for k, v in saldos.items() if k.startswith(prefix))

def compute_statements(lines, cutoff: datetime.date, y_ini: int, m_ini: int,
                       y_fin: int, m_fin: int):
    """Construye Balance (acumulado <= corte) y P&L (mes cerrado + YTD)."""
    ymd = cutoff.strftime("%Y%m%d")
    per0 = datetime.date(y_fin, m_fin, 1).strftime("%Y%m%d")   # inicio mes cerrado
    ytd0 = datetime.date(y_fin, 1, 1).strftime("%Y%m%d")        # inicio anio

    saldo_acum = defaultdict(float)   # todas las cuentas, acumulado <= corte
    pl_mes     = defaultdict(float)   # cuentas 4/5, mes cerrado
    pl_ytd     = defaultdict(float)   # cuentas 4/5, YTD
    for f, cod, imp in lines:
        if f > ymd:
            continue
        saldo_acum[cod] += imp
        if cod[:1] in ("4", "5"):
            if f >= ytd0:
                pl_ytd[cod] += imp
            if f >= per0:
                pl_mes[cod] += imp
    return saldo_acum, pl_mes, pl_ytd

def build_report(saldo_acum, pl_mes, pl_ytd):
    """Devuelve un dict con todas las lineas del estado ejecutivo."""
    # ---- Balance (acumulado). Activo natural +, Pasivo/Patrim natural -.
    act_corr = sum_prefix(saldo_acum, "11")
    act_ncor = sum_prefix(saldo_acum, "12")
    activo   = sum_prefix(saldo_acum, "1")
    pas_corr = -sum_prefix(saldo_acum, "21")
    pas_ncor = -sum_prefix(saldo_acum, "22")
    pasivo   = -sum_prefix(saldo_acum, "2")
    patrim3  = -sum_prefix(saldo_acum, "3")   # cuentas 3 (capital + result. acum.)
    # Resultado ACUMULADO en el mayor (cuentas 4+5 hasta el corte). Si Perseo cierra
    # el ejercicio cada 31-dic, esto equivale al resultado del anio en curso.
    resultado_acum = -(sum_prefix(saldo_acum, "4") + sum_prefix(saldo_acum, "5"))
    # Resultado del EJERCICIO en curso (cuentas 4+5 del anio, YTD).
    resultado_ej = -(sum_prefix(pl_ytd, "4") + sum_prefix(pl_ytd, "5"))
    # Patrimonio total derivado del mayor (cuadra por construccion salvo saldos
    # de apertura faltantes, que quedan visibles en 'cuadre').
    patrimonio = patrim3 + resultado_acum
    # Para presentacion: separo el resultado del ejercicio del resto del patrimonio.
    patrim_resto = patrimonio - resultado_ej
    inventarios = sum_prefix(saldo_acum, "1103")
    efectivo    = sum_prefix(saldo_acum, "1101")
    clientes    = sum_prefix(saldo_acum, "1102")
    deuda_fin   = (sum_prefix(saldo_acum, "2104") + sum_prefix(saldo_acum, "2203"))
    deuda_fin   = -deuda_fin
    cuadre = activo - (pasivo + patrimonio)

    def pl(d):
        ventas = -sum_prefix(d, "41")
        otros_ing = -sum_prefix(d, "42")
        costo = sum_prefix(d, "51")
        gv = sum_prefix(d, "52")
        ga = sum_prefix(d, "53")
        gf = sum_prefix(d, "54")
        gnd = sum_prefix(d, "55")
        # add-back depreciacion/amortizacion para EBITDA (por nombre no disponible aqui;
        # se aproxima EBITDA = Utilidad Operativa; ver nota)
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
        liquidez_corr = r(act_corr, pas_corr),
        prueba_acida  = r(act_corr - inventarios, pas_corr),
        capital_trab  = act_corr - pas_corr,
        endeud_pat    = r(pasivo, patrimonio),
        endeud_act    = r(pasivo, activo),
        deuda_fin_pat = r(deuda_fin, patrimonio),
        margen_bruto  = r(ytd["ub"], ytd["ventas"]),
        margen_oper   = r(ytd["uop"], ytd["ventas"]),
        margen_neto   = r(ytd["un"], ytd["ventas"]),
        # anualizar el resultado YTD para ROE/ROA
        roe = r(resultado_acum, patrimonio),
        roa = r(resultado_acum, activo),
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

# --------------------------------------------------------------- excel
NAVY = "1F3864"; GREEN = "2E7D32"; RED = "C00000"; GREY = "595959"
TITLE_FONT = Font(color=NAVY, bold=True, size=16)
SUB_FONT   = Font(color=GREY, size=9)
SEC_FILL   = PatternFill("solid", fgColor=NAVY)
SEC_FONT   = Font(color="FFFFFF", bold=True, size=11)
LBL_FONT   = Font(color="000000", size=10)
BOLD       = Font(bold=True, size=10)
BOLD_NAVY  = Font(color=NAVY, bold=True, size=11)
KPI_LBL    = Font(color=GREY, bold=True, size=9)
KPI_VAL    = Font(color=NAVY, bold=True, size=14)
TOTAL_FILL = PatternFill("solid", fgColor="D9E1F2")
SUBTL_FILL = PatternFill("solid", fgColor="F2F2F2")
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
MONEY = '"$"#,##0'; MONEY2 = '"$"#,##0.00'; PCT = '0.0%'; NUM = '0.00'

def _pct(v): return f"{v*100:.1f}%"

def build_workbook(rep, cutoff, mes_lbl, ytd_lbl, gen_ts, nota_fuente):
    wb = Workbook()
    ws = wb.active
    ws.title = "Resumen Ejecutivo"
    ws.sheet_view.showGridLines = False
    for col, w in zip("ABCDE", (36, 17, 18, 14, 14)):
        ws.column_dimensions[col].width = w
    # impresion limpia (para exportar a PDF)
    from openpyxl.worksheet.properties import PageSetupProperties
    ws.page_setup.orientation = "portrait"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.print_area = "A1:E80"

    # ---- titulo
    ws.merge_cells("A1:E1")
    ws["A1"] = f"ESTADOS FINANCIEROS - RESUMEN EJECUTIVO   {EMPRESA}"
    ws["A1"].font = Font(color=NAVY, bold=True, size=14)
    ws.merge_cells("A2:E2")
    ws["A2"] = (f"Corte: {cutoff.strftime('%d-%b-%Y')}   |   Generado: {gen_ts}"
                f"   |   Valores en USD")
    ws["A2"].font = SUB_FONT
    ws.merge_cells("A3:E3")
    ws["A3"] = nota_fuente
    ws["A3"].font = Font(color=GREY, size=8, italic=True)

    row = 5

    # =============================== RESUMEN 8 LINEAS (KPIs)
    def section(title, r):
        ws.merge_cells(f"A{r}:E{r}")
        c = ws[f"A{r}"]; c.value = title; c.fill = SEC_FILL; c.font = SEC_FONT
        c.alignment = Alignment(vertical="center")
        ws.row_dimensions[r].height = 20
        return r + 1

    ytd = rep["ytd"]; mes = rep["mes"]; ra = rep["ratios"]
    row = section("SINTESIS EJECUTIVA (YTD)", row)
    kpis = [
        ("Ventas Netas", ytd["ventas"], MONEY),
        ("Utilidad Bruta", ytd["ub"], MONEY),
        ("Utilidad Operativa", ytd["uop"], MONEY),
        ("Utilidad Neta", ytd["un"], MONEY),
    ]
    kpis2 = [
        ("Margen Bruto", ra["margen_bruto"], PCT),
        ("Margen Neto", ra["margen_neto"], PCT),
        ("Liquidez Corriente", ra["liquidez_corr"], NUM),
        ("Endeud. (Pas/Pat)", ra["endeud_pat"], NUM),
    ]
    for base_r, data in ((row, kpis), (row + 3, kpis2)):
        for i, (lbl, val, fmt) in enumerate(data):
            col = 1 + i
            cl = ws.cell(base_r, col, lbl); cl.font = KPI_LBL
            cv = ws.cell(base_r + 1, col, val); cv.font = KPI_VAL; cv.number_format = fmt
    row += 6

    # =============================== ESTADO DE RESULTADOS
    row = section("ESTADO DE RESULTADOS", row)
    hdr = row
    ws.cell(hdr, 1, "Concepto").font = BOLD
    ws.cell(hdr, 2, mes_lbl).font = BOLD
    ws.cell(hdr, 3, ytd_lbl).font = BOLD
    ws.cell(hdr, 4, "% Vta (YTD)").font = BOLD
    for c in range(1, 5):
        ws.cell(hdr, c).fill = SUBTL_FILL
        ws.cell(hdr, c).alignment = Alignment(horizontal="right" if c > 1 else "left")
    row += 1

    def er_line(lbl, k, bold=False, pct_base=None, fill=None):
        nonlocal row
        ws.cell(row, 1, lbl).font = BOLD if bold else LBL_FONT
        for col, src in ((2, mes), (3, ytd)):
            cc = ws.cell(row, col, src[k]); cc.number_format = MONEY
            cc.font = BOLD if bold else LBL_FONT
            cc.alignment = Alignment(horizontal="right")
        base = ytd.get(pct_base) if pct_base else ytd["ventas"]
        pv = (ytd[k] / base) if base else 0
        pc = ws.cell(row, 4, pv); pc.number_format = PCT
        pc.font = BOLD if bold else LBL_FONT
        pc.alignment = Alignment(horizontal="right")
        if fill:
            for c in range(1, 5):
                ws.cell(row, c).fill = fill
        row += 1

    er_line("Ventas Netas", "ventas", bold=True)
    er_line("(-) Costo de Ventas", "costo")
    er_line("Utilidad Bruta", "ub", bold=True, fill=SUBTL_FILL)
    er_line("(-) Gastos de Ventas", "gv")
    er_line("(-) Gastos de Administracion", "ga")
    er_line("Utilidad Operativa (EBIT)", "uop", bold=True, fill=SUBTL_FILL)
    er_line("(+) Otros Ingresos", "otros_ing")
    er_line("(-) Gastos Financieros", "gf")
    er_line("(-) Gastos No Deducibles", "gnd")
    er_line("Utilidad Neta (antes de imp.)", "un", bold=True, fill=TOTAL_FILL)
    row += 1

    # =============================== BALANCE GENERAL
    row = section("BALANCE GENERAL (Estado de Situacion)", row)
    def bg_line(lbl, val, bold=False, fill=None, indent=False):
        nonlocal row
        ws.cell(row, 1, ("   " if indent else "") + lbl).font = BOLD if bold else LBL_FONT
        cc = ws.cell(row, 2, val); cc.number_format = MONEY
        cc.font = BOLD if bold else LBL_FONT
        cc.alignment = Alignment(horizontal="right")
        if fill:
            for c in range(1, 3):
                ws.cell(row, c).fill = fill
        row += 1

    bg_line("Efectivo y Equivalentes", rep["efectivo"], indent=True)
    bg_line("Cuentas por Cobrar (neto)", rep["clientes"], indent=True)
    bg_line("Inventarios", rep["inventarios"], indent=True)
    bg_line("Activo Corriente", rep["act_corr"], bold=True, fill=SUBTL_FILL)
    bg_line("Activo No Corriente", rep["act_ncor"], indent=True)
    bg_line("ACTIVO TOTAL", rep["activo"], bold=True, fill=TOTAL_FILL)
    bg_line("Pasivo Corriente", rep["pas_corr"], indent=True)
    bg_line("Pasivo No Corriente", rep["pas_ncor"], indent=True)
    bg_line("PASIVO TOTAL", rep["pasivo"], bold=True, fill=SUBTL_FILL)
    bg_line("Patrimonio (capital + result. acum.)", rep["patrim_resto"], indent=True)
    bg_line("Resultado del Ejercicio (YTD)", rep["resultado_ej"], indent=True)
    bg_line("PATRIMONIO TOTAL", rep["patrimonio"], bold=True, fill=SUBTL_FILL)
    bg_line("PASIVO + PATRIMONIO", rep["pasivo"] + rep["patrimonio"], bold=True, fill=TOTAL_FILL)
    cuad = ws.cell(row, 1, "Cuadre contable (Activo - Pas - Pat)")
    cuad.font = Font(size=8, italic=True, color=(GREEN if abs(rep["cuadre"]) < 1 else RED))
    cc = ws.cell(row, 2, rep["cuadre"]); cc.number_format = MONEY2
    cc.font = Font(size=8, italic=True, color=(GREEN if abs(rep["cuadre"]) < 1 else RED))
    cc.alignment = Alignment(horizontal="right")
    row += 2

    # =============================== INDICADORES
    row = section("INDICADORES CLAVE", row)
    ind = [
        ("Liquidez Corriente", ra["liquidez_corr"], NUM, "Activo Corr / Pasivo Corr"),
        ("Prueba Acida", ra["prueba_acida"], NUM, "(Act Corr - Inv) / Pasivo Corr"),
        ("Capital de Trabajo", ra["capital_trab"], MONEY, "Activo Corr - Pasivo Corr"),
        ("Endeudamiento (Pas/Pat)", ra["endeud_pat"], NUM, "Apalancamiento"),
        ("Endeudamiento (Pas/Act)", ra["endeud_act"], PCT, "% del activo financiado con deuda"),
        ("Deuda Financiera / Patrim.", ra["deuda_fin_pat"], NUM, "Deuda bancaria / Patrimonio"),
        ("Margen Bruto (YTD)", ra["margen_bruto"], PCT, ""),
        ("Margen Operativo (YTD)", ra["margen_oper"], PCT, ""),
        ("Margen Neto (YTD)", ra["margen_neto"], PCT, ""),
        ("ROE (Result/Patrimonio)", ra["roe"], PCT, "Retorno sobre patrimonio"),
        ("ROA (Result/Activo)", ra["roa"], PCT, "Retorno sobre activos"),
    ]
    ws.cell(row, 1, "Indicador").font = BOLD
    ws.cell(row, 2, "Valor").font = BOLD
    ws.cell(row, 3, "Definicion").font = BOLD
    for c in range(1, 4):
        ws.cell(row, c).fill = SUBTL_FILL
    row += 1
    for lbl, val, fmt, note in ind:
        ws.cell(row, 1, lbl).font = LBL_FONT
        cc = ws.cell(row, 2, val); cc.number_format = fmt
        cc.font = BOLD_NAVY; cc.alignment = Alignment(horizontal="right")
        ws.cell(row, 3, note).font = Font(size=8, color=GREY)
        row += 1

    return wb

# --------------------------------------------------------------- main
def parse_cutoff(argv):
    if len(argv) > 1 and "-" in argv[1]:
        y, m = argv[1].split("-")[:2]
        y, m = int(y), int(m)
        return month_end(y, m), y, m
    y, m = last_closed_month(datetime.date.today())
    return month_end(y, m), y, m

def run_diag(api_key: str):
    """Muestra la respuesta CRUDA de Perseo para diagnosticar."""
    y, m = last_closed_month(datetime.date.today())
    d0 = datetime.date(y, m, 1).strftime("%Y%m%d")
    d1 = month_end(y, m).strftime("%Y%m%d")
    print(f"== DIAG asientoscontables_consulta  {d0} -> {d1} ==")
    st, ct, raw = _post_raw(URL_ASIENTOS, {"api_key": api_key,
                                           "fechadesde": d0, "fechahasta": d1})
    print(f"status={st}  content-type={ct}  bytes={len(raw)}")
    print("primeros 600 chars:\n" + raw[:600])
    print("\n== DIAG cuentascontables_consulta ==")
    st2, ct2, raw2 = _post_raw(URL_CUENTAS, {"api_key": api_key})
    print(f"status={st2}  content-type={ct2}  bytes={len(raw2)}")
    print("primeros 400 chars:\n" + raw2[:400])

def run_tb(api_key: str):
    """Diagnostico de balance: compara acumular TODO el historico vs SOLO el anio
    en curso (para detectar asientos de apertura anuales que se doble-cuentan)."""
    cutoff, y_fin, m_fin = parse_cutoff(["x", sys.argv[2]] if len(sys.argv) > 2 else [])
    lines = collect_lines(api_key, DEFAULT_START_YEAR, cutoff)
    ymd = cutoff.strftime("%Y%m%d")
    cy0 = f"{y_fin}0101"

    def bal(filtro):
        d = defaultdict(float)
        for f, cod, imp in lines:
            if f > ymd:
                continue
            if filtro == "cy" and f < cy0:
                continue
            d[cod] += imp
        return d
    all_ = bal("all"); cy = bal("cy")

    def show(tag, d):
        act = sum(v for k, v in d.items() if k.startswith("1"))
        pas = -sum(v for k, v in d.items() if k.startswith("2"))
        pat = -sum(v for k, v in d.items() if k.startswith("3"))
        efe = sum(v for k, v in d.items() if k.startswith("1101"))
        cli = sum(v for k, v in d.items() if k.startswith("1102"))
        inv = sum(v for k, v in d.items() if k.startswith("1103"))
        print(f"  [{tag}] Activo={act:,.0f}  Pasivo={pas:,.0f}  Patrim={pat:,.0f} | "
              f"Efectivo={efe:,.0f}  Clientes={cli:,.0f}  Inv={inv:,.0f}")
    print("\n=== BALANCE al", cutoff.isoformat(), "===")
    print(" A) Acumulando TODO el historico (2021->corte):")
    show("HIST", all_)
    print(f" B) Acumulando SOLO el anio en curso ({y_fin}):")
    show("ANIO", cy)

    # Deteccion de aperturas: suma de cuentas '1' en el mes de enero de cada anio
    print("\n=== Movimiento de cuentas de Activo ('1') en ENERO de cada anio ===")
    for y in range(DEFAULT_START_YEAR, y_fin + 1):
        s = sum(imp for f, cod, imp in lines
                if f.startswith(f"{y}01") and cod.startswith("1"))
        n = sum(1 for f, cod, imp in lines if f.startswith(f"{y}01"))
        if n:
            print(f"  {y}-01: lineas={n}  sum(Activo)={s:,.0f}")

    # Nombres de cuenta
    try:
        nombres = fetch_cuentas(api_key)
    except Exception:
        nombres = {}

    # TOP cuentas por |saldo| acumulado (todo el historico)
    print("\n=== TOP 30 cuentas por |saldo| ACUMULADO (todo el historico) ===")
    top = sorted(all_.items(), key=lambda kv: -abs(kv[1]))[:30]
    for cod, val in top:
        print(f"  {cod:<14} {val:>18,.0f}  {nombres.get(cod,'')[:40]}")

    # Cuantas cuentas 'hoja' distintas hay por grupo de nivel-1
    print("\n=== Nº de cuentas distintas y saldo por grupo nivel-1 ===")
    for g in "12345":
        codes = [k for k in all_ if k.startswith(g)]
        tot = sum(all_[k] for k in codes)
        print(f"  grupo {g}: cuentas={len(codes):<5} saldo_acum={tot:,.0f}")

    # Detalle de cuentas '3' (patrimonio) por sub-grupo
    print("\n=== Cuentas '3' (Patrimonio) - top 15 por |saldo| ===")
    tres = sorted([kv for kv in all_.items() if kv[0].startswith("3")],
                  key=lambda kv: -abs(kv[1]))[:15]
    for cod, val in tres:
        print(f"  {cod:<14} {val:>18,.0f}  {nombres.get(cod,'')[:40]}")

def run_origen(api_key: str):
    """Diagnostico: agrupa por 'origen' para identificar los asientos de
    regulacion/cierre de resultados que inflan los saldos."""
    cutoff, y_fin, m_fin = parse_cutoff(["x", sys.argv[2]] if len(sys.argv) > 2 else [])
    # Recolecta a nivel de ASIENTO (origen, concepto, lineas)
    asientos_all = []
    for y in range(DEFAULT_START_YEAR, cutoff.year + 1):
        a0 = datetime.date(y, 1, 1).strftime("%Y%m%d")
        a1 = min(datetime.date(y, 12, 31), cutoff).strftime("%Y%m%d")
        try:
            asi = fetch_asientos(api_key, a0, a1)
        except RuntimeError as e:
            print(f"[WARN] {y}: {e}", file=sys.stderr); asi = []
        for a in asi:
            if a.get("anulado"):
                continue
            dets = [(_code(d.get("codigocontable")), _num(d.get("importe")))
                    for d in (a.get("detalle") or []) if not d.get("anulado")]
            asientos_all.append((str(a.get("origen", "")), str(a.get("concepto", "")),
                                 _fecha(a.get("fecha")), dets))
    print(f"[INFO] asientos={len(asientos_all)}")

    # Agrupa por origen: cuenta y contribucion a grupo 4 (ingresos) y toca-37
    from collections import defaultdict
    stat = defaultdict(lambda: [0, 0.0, 0.0, 0])  # n, sum_g4, sum_g5, n_toca37
    for origen, concepto, f, dets in asientos_all:
        toca37 = any(c.startswith("37") for c, _ in dets)
        g4 = sum(v for c, v in dets if c.startswith("4"))
        g5 = sum(v for c, v in dets if c.startswith("5"))
        s = stat[origen]
        s[0] += 1; s[1] += g4; s[2] += g5; s[3] += (1 if toca37 else 0)
    print("\n=== Por ORIGEN: n_asientos | sum(grupo4) | sum(grupo5) | n_tocan_37 ===")
    for origen, (n, g4, g5, n37) in sorted(stat.items(), key=lambda kv: -abs(kv[1][1])):
        print(f"  {origen:<22} n={n:<6} g4={g4:>16,.0f} g5={g5:>16,.0f} toca37={n37}")

    # Recalculo de grupos EXCLUYENDO asientos que tocan 37xx
    def group_totals(exclude_37):
        g = defaultdict(float)
        for origen, concepto, f, dets in asientos_all:
            if f > cutoff.strftime("%Y%m%d"):
                continue
            if exclude_37 and any(c.startswith("37") for c, _ in dets):
                continue
            for c, v in dets:
                if c[:1] in "12345":
                    g[c[:1]] += v
        return g
    print("\n=== Totales por grupo nivel-1 ===")
    inc = group_totals(False); exc = group_totals(True)
    for gk in "12345":
        print(f"  grupo {gk}: con_todo={inc[gk]:>16,.0f}   sin_asientos_37={exc[gk]:>16,.0f}")

    # Muestra los asientos que tocan 37 (regulacion) - primeros 8
    print("\n=== Muestra de asientos que tocan 37xx (regulacion/cierre) ===")
    shown = 0
    for origen, concepto, f, dets in asientos_all:
        if any(c.startswith("37") for c, _ in dets):
            print(f"  {f} origen={origen:<16} {concepto[:50]}")
            for c, v in dets[:6]:
                print(f"        {c:<14} {v:>16,.2f}")
            shown += 1
            if shown >= 6:
                break

def main():
    api_key = get_api_key()
    if len(sys.argv) > 1 and sys.argv[1] == "diag":
        run_diag(api_key)
        return
    if len(sys.argv) > 1 and sys.argv[1] == "tb":
        run_tb(api_key)
        return
    if len(sys.argv) > 1 and sys.argv[1] == "origen":
        run_origen(api_key)
        return
    cutoff, y_fin, m_fin = parse_cutoff(sys.argv)
    start_year = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_START_YEAR

    print(f"[INFO] Extrayendo mayor {start_year}-01 -> {cutoff.isoformat()} ...")
    lines = collect_lines(api_key, start_year, cutoff)
    if not lines:
        sys.exit("ERROR: no se obtuvieron asientos. Revisa api_key/conexion/fechas.")

    saldo_acum, pl_mes, pl_ytd = compute_statements(
        lines, cutoff, y_fin, 1, y_fin, m_fin)
    rep = build_report(saldo_acum, pl_mes, pl_ytd)

    MESES = ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago",
             "Sep", "Oct", "Nov", "Dic"]
    mes_lbl = f"{MESES[m_fin]}-{y_fin}"
    ytd_lbl = f"YTD {y_fin} (Ene-{MESES[m_fin]})"
    gen_ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    nota = ("Construido directamente desde el mayor contable de Perseo "
            "(asientos). El cuadre contable debe ser ~$0.")

    wb = build_workbook(rep, cutoff, mes_lbl, ytd_lbl, gen_ts, nota)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fname = f"Estados_Financieros_Ejecutivo_{y_fin}-{m_fin:02d}.xlsx"
    p1 = OUT_DIR / fname
    p2 = OUT_DIR / "Estados_Financieros_Ejecutivo_ULTIMO.xlsx"
    wb.save(p1)
    try:
        wb.save(p2)
    except OSError:
        pass
    print(f"[OK] {gen_ts}  Ventas YTD={rep['ytd']['ventas']:,.0f}  "
          f"UtilNeta YTD={rep['ytd']['un']:,.0f}  Activo={rep['activo']:,.0f}  "
          f"Cuadre={rep['cuadre']:,.2f}  ->  {p1}")

if __name__ == "__main__":
    main()
