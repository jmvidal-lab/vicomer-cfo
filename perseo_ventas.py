#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
perseo_ventas.py
Extrae las ventas (facturas) del dia desde el API de Perseo y genera un Excel.

- API:    POST https://perseo-data-c1.app/api/facturas_consulta
- Auth:   api_key dentro del JSON (NO se guarda en este archivo)
- Salida: ~/PerseoVentas/Ventas_YYYY-MM-DD.xlsx

El api_key se lee de (en orden):
  1) variable de entorno  PERSEO_API_KEY
  2) archivo              ~/.perseo_apikey   (recomendado, chmod 600)

Dependencia:  pip3 install --user openpyxl
Uso:          python3 perseo_ventas.py [dias]      (dias por defecto = 1)
"""

import os
import sys
import json
import ssl
import datetime
import urllib.request
import urllib.error
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# ------------------------------------------------------------------ config
API_URL = "https://perseo-data-c1.app/api/facturas_consulta"
OUT_DIR = Path.home() / "PerseoVentas"
# Copia automatica para el proyecto CFO VICOMER (la lee el asistente CFO).
EXTRA_OUT_DIRS = [Path.home() / "Claude" / "Projects" / "CFO VICOMER" / "PerseoVentas"]
DIAS_DEFAULT = 1

TIPO_DOC = {"01": "Factura", "04": "Nota de Credito", "05": "Nota de Debito",
            "06": "Guia de Remision"}

# ------------------------------------------------------------------ api key
def get_api_key() -> str:
    key = os.environ.get("PERSEO_API_KEY")
    if key:
        return key.strip()
    keyfile = Path.home() / ".perseo_apikey"
    if keyfile.exists():
        return keyfile.read_text(encoding="utf-8").strip()
    sys.exit("ERROR: no se encontro el api_key. Define PERSEO_API_KEY "
             "o crea el archivo ~/.perseo_apikey")

# ------------------------------------------------------------------ fetch
def fetch_facturas(api_key: str, dias: int) -> list:
    body = json.dumps({"api_key": api_key, "dias": dias,
                       "generarpdf": False}).encode("utf-8")
    req = urllib.request.Request(
        API_URL, data=body,
        headers={"Content-Type": "application/json"}, method="POST")
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        sys.exit(f"ERROR HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:300]}")
    except urllib.error.URLError as e:
        sys.exit(f"ERROR de conexion: {e.reason}")
    if isinstance(data, dict) and data.get("fault"):
        sys.exit(f"ERROR API: {data['fault'].get('faultstring')}")
    return data.get("facturas", []) if isinstance(data, dict) else []

# ------------------------------------------------------------------ normalize
def _num(v):
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return 0.0

def _fecha(s):
    # acepta '20260625' o '2026-06-25T..' -> '2026-06-25'
    if not s:
        return ""
    s = str(s)
    if len(s) >= 8 and s[:8].isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return s[:10]

def normalize(facturas: list) -> list:
    rows = []
    for x in facturas:
        rows.append({
            "id": x.get("facturasid"),
            "tipo": TIPO_DOC.get(str(x.get("sri_documentoscodigo")),
                                 str(x.get("sri_documentoscodigo", ""))),
            "secuencia": f"{x.get('establecimiento','')}-"
                         f"{x.get('puntoemision','')}-{x.get('secuencial','')}",
            "emision": _fecha(x.get("emision")),
            "cliente": x.get("razonsocial", ""),
            "identificacion": x.get("identificacion", ""),
            "subtotal": _num(x.get("subtotal")),
            "descuento": _num(x.get("total_descuento")),
            "iva": _num(x.get("total_iva")),
            "total": _num(x.get("total")),
            "autorizado": "SI" if x.get("numeroautorizacion") else "NO",
            "estado_sri": x.get("mensajeerror") or ("Enviado" if x.get("de_enviado") else ""),
        })
    return rows

# ------------------------------------------------------------------ excel
HEADER_FILL = PatternFill("solid", fgColor="1F3864")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=10)
TITLE_FONT = Font(color="1F3864", bold=True, size=15)
KPI_LABEL = Font(color="595959", bold=True, size=10)
KPI_VALUE = Font(color="1F3864", bold=True, size=12)
TOTAL_FONT = Font(bold=True, size=10)
TOTAL_FILL = PatternFill("solid", fgColor="D9E1F2")
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
MONEY = '"$"#,##0.00'

COLS = [
    ("Fecha", "emision", 12, None),
    ("Tipo", "tipo", 16, None),
    ("Secuencia", "secuencia", 20, None),
    ("Cliente", "cliente", 40, None),
    ("Identificacion", "identificacion", 16, None),
    ("Subtotal", "subtotal", 14, MONEY),
    ("Descuento", "descuento", 13, MONEY),
    ("IVA", "iva", 13, MONEY),
    ("Total", "total", 15, MONEY),
    ("Autorizado", "autorizado", 12, None),
    ("Estado SRI", "estado_sri", 18, None),
]

def build_workbook(rows: list, fecha_reporte: str) -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = "Ventas del dia"
    ws.sheet_view.showGridLines = False

    n = len(rows)
    facturas = [r for r in rows if r["tipo"] == "Factura"]
    nc = [r for r in rows if r["tipo"] == "Nota de Credito"]
    bruto = sum(r["total"] for r in facturas)
    devol = sum(r["total"] for r in nc)
    iva_total = sum(r["iva"] for r in rows)
    neto = bruto - devol
    ticket = (bruto / len(facturas)) if facturas else 0

    # ---- titulo
    ws.merge_cells("A1:K1")
    ws["A1"] = "REPORTE DE VENTAS DIARIAS  -  Perseo"
    ws["A1"].font = TITLE_FONT
    ws.merge_cells("A2:K2")
    ws["A2"] = f"Generado: {fecha_reporte}    |    Documentos: {n}"
    ws["A2"].font = Font(color="595959", size=9)

    # ---- KPIs (fila 4)
    kpis = [("Ventas brutas", bruto, MONEY), ("Devoluciones", devol, MONEY),
            ("Ventas netas", neto, MONEY), ("IVA total", iva_total, MONEY),
            ("Ticket promedio", ticket, MONEY)]
    col = 1
    for label, value, fmt in kpis:
        c1 = ws.cell(row=4, column=col, value=label)
        c1.font = KPI_LABEL
        c2 = ws.cell(row=5, column=col, value=value)
        c2.font = KPI_VALUE
        c2.number_format = fmt
        col += 2

    # ---- tabla
    head_row = 7
    for j, (title, _, _, _) in enumerate(COLS, start=1):
        c = ws.cell(row=head_row, column=j, value=title)
        c.fill = HEADER_FILL
        c.font = HEADER_FONT
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = BORDER

    r = head_row + 1
    for row in rows:
        for j, (_, key, _, fmt) in enumerate(COLS, start=1):
            c = ws.cell(row=r, column=j, value=row[key])
            c.border = BORDER
            c.font = Font(size=10)
            if fmt:
                c.number_format = fmt
        r += 1

    # ---- fila total
    ws.cell(row=r, column=1, value="TOTAL").font = TOTAL_FONT
    for j, (_, key, _, fmt) in enumerate(COLS, start=1):
        c = ws.cell(row=r, column=j)
        c.fill = TOTAL_FILL
        c.border = BORDER
        if key in ("subtotal", "descuento", "iva", "total"):
            c.value = round(sum(row[key] for row in rows), 2)
            c.number_format = MONEY
            c.font = TOTAL_FONT
    ws.cell(row=r, column=1).fill = TOTAL_FILL

    # ---- anchos
    for j, (_, _, width, _) in enumerate(COLS, start=1):
        ws.column_dimensions[get_column_letter(j)].width = width
    ws.freeze_panes = f"A{head_row+1}"
    return wb

# ------------------------------------------------------------------ main
def main():
    dias = int(sys.argv[1]) if len(sys.argv) > 1 else DIAS_DEFAULT
    api_key = get_api_key()
    facturas = fetch_facturas(api_key, dias)
    rows = normalize(facturas)

    hoy = datetime.date.today().isoformat()
    fecha_reporte = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    wb = build_workbook(rows, fecha_reporte)

    # Guarda en OUT_DIR y en cada carpeta extra (proyecto CFO). Si una falla,
    # avisa pero no aborta: la copia del proyecto nunca rompe la corrida.
    out_path = None
    for d in [OUT_DIR, *EXTRA_OUT_DIRS]:
        try:
            d.mkdir(parents=True, exist_ok=True)
            p = d / f"Ventas_{hoy}.xlsx"
            wb.save(p)
            if out_path is None:
                out_path = p
        except OSError as e:
            print(f"[WARN] no se pudo guardar en {d}: {e}", file=sys.stderr)

    total = sum(r["total"] for r in rows if r["tipo"] == "Factura")
    print(f"[OK] {fecha_reporte}  documentos={len(rows)}  "
          f"ventas={total:,.2f}  ->  {out_path}")

if __name__ == "__main__":
    main()
