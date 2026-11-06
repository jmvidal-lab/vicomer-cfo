#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
perseo_presupuesto.py
=====================
Actualiza AUTOMÁTICAMENTE los documentos comerciales de VICOMER (solo Ecuador)
con las ventas reales extraídas del API de Perseo, y produce un resumen del
estado del presupuesto (para el correo semanal).

QUÉ HACE
--------
1. Consulta las facturas del año en curso desde Perseo
   (POST https://perseo-data-c1.app/api/facturas_consulta).
2. Normaliza cada documento (Factura=positivo, Nota de Crédito=negativo).
3. Reescribe QUIRÚRGICAMENTE las hojas de datos crudos de cada libro,
   preservando gráficos, tablas dinámicas, formato y fórmulas:
      - "PRESUPUESTO COMERCIAL REGIONAL 2026 - GRUPO VICOMER.xlsx"  -> hoja "Ventas Reales EC"
      - "ANALISIS COMERCIAL VICOMER 2026.xlsx"                      -> hoja/tabla "BD" (TablaVentas)
   Las fórmulas nativas del libro (SUMPRODUCT, VLOOKUP de canal, variación,
   dashboard, tabla dinámica) se recalculan solas al abrir en Excel.
   (El archivo de Colombia NO se toca: se integrará después vía Odoo.)
4. Genera un libro-compañero limpio "ESTADO_PRESUPUESTO_ECUADOR.xlsx"
   (real vs presupuesto por canal y por cliente) y un "estado_presupuesto.json"
   que consume el correo semanal.

SEGURIDAD OPERATIVA (corre desatendido)
---------------------------------------
- Antes de escribir hace BACKUP con timestamp de cada libro.
- Tras escribir VALIDA el resultado (abre el zip, cuenta hojas, verifica que
  gráficos/dinámicas sigan presentes). Si falla, RESTAURA el backup y registra error.
- Reemplazo atómico (archivo temporal -> os.replace).

api_key: variable de entorno PERSEO_API_KEY o archivo ~/.perseo_apikey (chmod 600).
Uso:  python3 perseo_presupuesto.py
Dep.: pip3 install --user openpyxl
"""

import os, sys, re, ssl, json, gzip, shutil, zipfile, datetime, traceback
import urllib.request, urllib.error
from pathlib import Path
from collections import defaultdict

# ----------------------------------------------------------------- CONFIG
API_URL   = "https://perseo-data-c1.app/api/facturas_consulta"
HOME      = Path.home()
FILES_DIR = Path(os.environ.get("PERSEO_FILES_DIR", HOME / "Desktop" / "VICOMER COMERCIAL"))
OUT_DIR   = Path(os.environ.get("PERSEO_OUT_DIR",   HOME / "Claude" / "Projects" / "CFO VICOMER" / "PresupuestoAuto"))
BACKUP_DIR = OUT_DIR / "_backups"
YEAR      = int(os.environ.get("PERSEO_YEAR", datetime.date.today().year))
LOCAL_JSON = os.environ.get("PERSEO_LOCAL_JSON")  # gancho de prueba (usa un json.gz local en vez del API)

REGIONAL_XLSX = FILES_DIR / "PRESUPUESTO COMERCIAL REGIONAL 2026 - GRUPO VICOMER.xlsx"
ANALISIS_XLSX = FILES_DIR / "ANALISIS COMERCIAL VICOMER 2026.xlsx"

EPOCH = datetime.date(1899, 12, 30)          # sistema de fecha de Excel (1900)
MESES = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]

def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

# ----------------------------------------------------------------- API KEY
def get_api_key() -> str:
    k = os.environ.get("PERSEO_API_KEY")
    if k:
        return k.strip()
    for p in (HOME / ".perseo_apikey",
              HOME / "Claude" / "Projects" / "CFO VICOMER" / "perseo_apikey.txt"):
        if p.exists():
            return p.read_text(encoding="utf-8").strip()
    sys.exit("ERROR: no se encontró el api_key (PERSEO_API_KEY o ~/.perseo_apikey)")

# ----------------------------------------------------------------- FETCH
def fetch_facturas(dias: int) -> list:
    """Trae las facturas de los últimos `dias`. Si PERSEO_LOCAL_JSON está
    definido, lee de ese archivo (para pruebas fuera de la red de Perseo)."""
    if LOCAL_JSON:
        log(f"[TEST] leyendo facturas de archivo local: {LOCAL_JSON}")
        op = gzip.open if LOCAL_JSON.endswith(".gz") else open
        with op(LOCAL_JSON, "rt", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("facturas", []) if isinstance(data, dict) else data
    body = json.dumps({"api_key": get_api_key(), "dias": dias, "generarpdf": False}).encode()
    req = urllib.request.Request(API_URL, data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=600, context=ssl.create_default_context()) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        sys.exit(f"ERROR HTTP {e.code}: {e.read().decode('utf-8','ignore')[:300]}")
    except urllib.error.URLError as e:
        sys.exit(f"ERROR de conexión: {e.reason}")
    if isinstance(data, dict) and data.get("fault"):
        sys.exit(f"ERROR API: {data['fault'].get('faultstring')}")
    return data.get("facturas", []) if isinstance(data, dict) else data

# ----------------------------------------------------------------- NORMALIZE
def _date(s):
    s = str(s)
    if len(s) >= 8 and s[:8].isdigit():
        return datetime.date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    return None

def normalize(facturas: list, year: int) -> list:
    """Devuelve una lista de transacciones del año, ordenadas por fecha.
    Factura (01) => montos positivos ; Nota de Crédito (04) => negativos."""
    rows = []
    for x in facturas:
        d = _date(x.get("emision"))
        if not d or d.year != year:
            continue
        code = str(x.get("sri_documentoscodigo"))
        if code not in ("01", "04"):
            continue
        sign = -1.0 if code == "04" else 1.0
        rows.append({
            "serie": f"{x.get('establecimiento','')} {x.get('puntoemision','')}".strip(),
            "sec":   int(str(x.get("secuencial") or "0").lstrip("0") or "0"),
            "dni":   str(x.get("identificacion") or ""),
            "cli":   str(x.get("razonsocial") or ""),
            "fpago": str(x.get("forma_pago_sri_codigo") or ""),
            "fecha": d,
            "subtotal": round(sign * float(x.get("subtotal") or 0), 4),
            "desc":     round(sign * float(x.get("total_descuento") or 0), 4),
            "iva":      round(sign * float(x.get("total_iva") or 0), 4),
            "total":    round(sign * float(x.get("total") or 0), 2),
            "es_nc":  code == "04",
        })
    rows.sort(key=lambda r: (r["fecha"], r["sec"]))
    return rows

# ----------------------------------------------------------------- XML helpers
def _esc_text(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))

def _esc_formula(s):
    # las fórmulas van dentro de <f>...; sólo hay que escapar & < >
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def _serial(d):
    return (d - EPOCH).days

def _c_num(ref, val, s=None):
    st = f' s="{s}"' if s is not None else ""
    return f'<c r="{ref}"{st}><v>{val}</v></c>'

def _c_inl(ref, txt, s=None):
    st = f' s="{s}"' if s is not None else ""
    return f'<c r="{ref}"{st} t="inlineStr"><is><t xml:space="preserve">{_esc_text(txt)}</t></is></c>'

def _c_formula(ref, formula, cached, s=None, array=False, t=None):
    st = f' s="{s}"' if s is not None else ""
    tt = f' t="{t}"' if t else ""
    fx = f'<f t="array" ref="{ref}">{_esc_formula(formula)}</f>' if array else f'<f>{_esc_formula(formula)}</f>'
    cv = f'<v>{cached}</v>' if cached is not None else ''
    return f'<c r="{ref}"{st}{tt}>{fx}{cv}</c>'

# ----------------------------------------------------------------- WRITE: Regional (Ventas Reales EC)
def build_ventas_reales_ec_xml(orig_xml, rows):
    """Regenera la hoja 'Ventas Reales EC' con N transacciones + bloque resumen
    mensual, ampliando los rangos de las fórmulas SUMPRODUCT a $2:$(N+1)."""
    N = len(rows); last = N + 1
    HDR = ["Serie","Secuencia","DNI","Cliente","Forma Pago","Fecha","SubTotal","Descuento",
           "SubT IVA 0%","SubT IVA 15%","SubT IVA 5%","IVA 15%","IVA 5%","Propina","TOTAL"]
    def L(i):  # columna A..O
        return chr(64 + i)
    sd = []
    sd.append(f'<row r="1" spans="1:15">' + "".join(_c_inl(f"{L(i+1)}1", h, 366) for i, h in enumerate(HDR)) + '</row>')
    r = 2
    for x in rows:
        dni_cell = _c_num(f"C{r}", x["dni"]) if x["dni"].isdigit() else _c_inl(f"C{r}", x["dni"])
        cells = [
            _c_inl(f"A{r}", x["serie"]),
            _c_num(f"B{r}", x["sec"]),
            dni_cell,
            _c_inl(f"D{r}", x["cli"]),
            _c_inl(f"E{r}", x["fpago"]),
            _c_num(f"F{r}", _serial(x["fecha"]), 367),
            _c_num(f"G{r}", x["subtotal"], 254),
            _c_num(f"H{r}", x["desc"], 254),
            _c_num(f"I{r}", 0, 254),
            _c_num(f"J{r}", x["subtotal"], 254),
            _c_num(f"K{r}", 0, 254),
            _c_num(f"L{r}", x["iva"], 254),
            _c_num(f"M{r}", 0, 254),
            _c_num(f"N{r}", 0, 254),
            _c_num(f"O{r}", x["total"], 254),
        ]
        sd.append(f'<row r="{r}" spans="1:15">' + "".join(cells) + '</row>')
        r += 1
    # resumen mensual bajo los datos
    title_r = last + 2; sub_r = title_r + 1; m0 = sub_r + 1
    sd.append(f'<row r="{title_r}" spans="1:15"><c r="A{title_r}" s="368" t="inlineStr"><is><t>RESUMEN MENSUAL (Perseo)</t></is></c></row>')
    sd.append(f'<row r="{sub_r}" spans="1:15">'
              f'<c r="A{sub_r}" s="369" t="inlineStr"><is><t>Mes</t></is></c>'
              f'<c r="B{sub_r}" s="369" t="inlineStr"><is><t>SubTotal</t></is></c>'
              f'<c r="C{sub_r}" s="369" t="inlineStr"><is><t>TOTAL neto</t></is></c>'
              f'<c r="D{sub_r}" s="369" t="inlineStr"><is><t># Docs</t></is></c></row>')
    for i, mm in enumerate(MESES):
        rr = m0 + i; mnum = i + 1
        fB = f'SUMPRODUCT((MONTH($F$2:$F${last})={mnum})*$G$2:$G${last})'
        fC = f'SUMPRODUCT((MONTH($F$2:$F${last})={mnum})*$O$2:$O${last})'
        fD = f'SUMPRODUCT((MONTH($F$2:$F${last})={mnum})*($O$2:$O${last}<>0))'
        sd.append(f'<row r="{rr}" spans="1:15">'
                  f'<c r="A{rr}" t="inlineStr"><is><t>{mm}</t></is></c>'
                  + _c_formula(f"B{rr}", fB, None, s=370, array=True)
                  + _c_formula(f"C{rr}", fC, None, s=370, array=True)
                  + _c_formula(f"D{rr}", fD, None, s=371, array=True)
                  + '</row>')
    tot_r = m0 + 12
    sd.append(f'<row r="{tot_r}" spans="1:15">'
              f'<c r="A{tot_r}" s="372" t="inlineStr"><is><t>Total</t></is></c>'
              + _c_formula(f"B{tot_r}", f"SUM(B{m0}:B{m0+11})", None, s=373)
              + _c_formula(f"C{tot_r}", f"SUM(C{m0}:C{m0+11})", None, s=373)
              + _c_formula(f"D{tot_r}", f"SUM(D{m0}:D{m0+11})", None, s=374)
              + '</row>')
    sheetData = "<sheetData>" + "".join(sd) + "</sheetData>"
    head = orig_xml[:orig_xml.index("<sheetData>")]
    tail = orig_xml[orig_xml.index("</sheetData>") + len("</sheetData>"):]
    head = re.sub(r'<dimension ref="[^"]+"/>', f'<dimension ref="A1:O{tot_r}"/>', head)
    head = re.sub(r'topLeftCell="[^"]+"', 'topLeftCell="A2"', head)
    head = re.sub(r'<selection pane="bottomLeft"[^/]*/>',
                  '<selection pane="bottomLeft" activeCell="A2" sqref="A2"/>', head)
    tail = re.sub(r'<mergeCells count="1"><mergeCell ref="A295:D295"/></mergeCells>', '', tail)
    return head + sheetData + tail, last

def patch_regional_refs(xml, last):
    """Amplía el rango de las fórmulas que leen 'Ventas Reales EC' y, para que el
    REAL sea SIN IVA (consistente con el presupuesto), las repunta de la columna
    O (TOTAL, con IVA) a la columna G (SubTotal, base imponible sin IVA)."""
    xml = xml.replace("'Ventas Reales EC'!$F$2:$F$293", f"'Ventas Reales EC'!$F$2:$F${last}")
    xml = xml.replace("'Ventas Reales EC'!$O$2:$O$293", f"'Ventas Reales EC'!$G$2:$G${last}")
    return xml

# ----------------------------------------------------------------- WRITE: Analisis (BD / TablaVentas)
def build_bd_xml(orig_xml, rows):
    """Regenera la hoja 'BD' (Excel Table 'TablaVentas', 23 columnas).
    Canal (col V) y Mes (col W) se dejan como fórmulas (autoderivadas)."""
    N = len(rows); last = N + 1
    HDR = ["Serie","Secuencia","DNI","Cliente","Forma de Pago","Tipo Pago","Emisión","SubTotal",
           "Desc","SubT.IVA 0%","Columna1","SubT.IVA 15%","Columna2","SubT.IVA 5%","IVA 15%",
           "Columna3","IVA 5%","Propina","Columna4","TOTAL","Columna5","Canal","Mes"]
    def L(i):  # 1->A ... 23->W
        return chr(64 + i) if i <= 26 else None
    sd = []
    sd.append(f'<row r="1" spans="1:23">' + "".join(_c_inl(f"{L(i+1)}1", h, 6) for i, h in enumerate(HDR)) + '</row>')
    r = 2
    for x in rows:
        dni_cell = _c_num(f"C{r}", x["dni"]) if x["dni"].isdigit() else _c_inl(f"C{r}", x["dni"])
        canal_f = (f'IFERROR(IF(ISNUMBER(SEARCH("Factura Afectada",D{r})),"NOTA DE CREDITO",'
                   f'VLOOKUP(D{r},DIM_Clients!$A:$B,2,FALSE)),"SIN CATEGORIZAR")')
        cells = [
            _c_inl(f"A{r}", x["serie"]),
            _c_num(f"B{r}", x["sec"]),
            dni_cell,
            _c_inl(f"D{r}", x["cli"]),
            _c_inl(f"E{r}", ""),               # Forma de Pago (vacío, como el original)
            _c_inl(f"F{r}", x["fpago"]),        # Tipo Pago
            _c_num(f"G{r}", _serial(x["fecha"]), 5),   # Emisión (fecha)
            _c_num(f"H{r}", x["subtotal"], 50),        # SubTotal
            _c_num(f"I{r}", x["desc"], 50),            # Desc
            _c_num(f"J{r}", 0, 50),                    # SubT.IVA 0%
            _c_num(f"K{r}", 0, 50),                    # Columna1
            _c_num(f"L{r}", x["subtotal"], 50),        # SubT.IVA 15%
            _c_num(f"M{r}", 0, 50),                    # Columna2
            _c_num(f"N{r}", 0, 50),                    # SubT.IVA 5%
            _c_num(f"O{r}", x["iva"], 50),             # IVA 15%
            _c_num(f"P{r}", 0, 50),                    # Columna3
            _c_num(f"Q{r}", 0, 50),                    # IVA 5%
            _c_num(f"R{r}", 0, 50),                    # Propina
            _c_num(f"S{r}", 0, 50),                    # Columna4
            _c_num(f"T{r}", x["total"], 50),           # TOTAL
            _c_num(f"U{r}", 0, 50),                    # Columna5
            _c_formula(f"V{r}", canal_f, "SIN CATEGORIZAR", s=8, t="str"),   # Canal
            _c_formula(f"W{r}", f'IFERROR(TEXT(G{r},"yyyy-mm"),"")', x["fecha"].strftime("%Y-%m"), t="str"),  # Mes
        ]
        sd.append(f'<row r="{r}" spans="1:23">' + "".join(cells) + '</row>')
        r += 1
    sheetData = "<sheetData>" + "".join(sd) + "</sheetData>"
    head = orig_xml[:orig_xml.index("<sheetData>")]
    tail = orig_xml[orig_xml.index("</sheetData>") + len("</sheetData>"):]
    head = re.sub(r'<dimension ref="[^"]+"/>', f'<dimension ref="A1:W{last}"/>', head)
    return head + sheetData + tail, last

def flip_total_to_subtotal(xml):
    """Reporte SIN IVA: las agregaciones que suman la columna TOTAL (con IVA, col T)
    pasan a sumar SubTotal (base imponible sin IVA, col H)."""
    return xml.replace("BD!$T:$T", "BD!$H:$H").replace("BD!T:T", "BD!H:H")

def patch_pivot_datafield(xml):
    """La tabla dinámica pasa a sumar SubTotal (fld 7) en lugar de TOTAL (fld 19)."""
    return (xml.replace('name="Suma de TOTAL" fld="19"', 'name="Suma de SubTotal" fld="7"')
               .replace('name="Suma de TOTAL"', 'name="Suma de SubTotal"'))

def patch_table_and_pivot(zin, names, replacements, table_ref_last, pivot_ref_last):
    """Devuelve dict {name: bytes} con table1.xml y pivotCacheDefinition patcheados."""
    out = {}
    for n in names:
        if n.startswith("xl/tables/") and n.endswith(".xml"):
            t = zin.read(n).decode()
            t = re.sub(r'ref="A1:W\d+"', f'ref="A1:W{table_ref_last}"', t)
            t = re.sub(r'<autoFilter ref="A1:W\d+"', f'<autoFilter ref="A1:W{table_ref_last}"', t)
            out[n] = t.encode()
        elif n.startswith("xl/pivotCache/pivotCacheDefinition") and n.endswith(".xml"):
            p = zin.read(n).decode()
            p = re.sub(r'(<worksheetSource ref=")A1:W\d+(")', rf'\g<1>A1:W{pivot_ref_last}\g<2>', p)
            if 'refreshOnLoad="1"' not in p:
                p = re.sub(r'<pivotCacheDefinition ', '<pivotCacheDefinition refreshOnLoad="1" ', p, count=1)
            out[n] = p.encode()
    return out

# ----------------------------------------------------------------- workbook.xml calc flag
def patch_fullcalc(wbx):
    if "<calcPr" in wbx:
        def _add(m):
            g = m.group(0)
            return g if "fullCalcOnLoad" in g else g[:-2] + ' fullCalcOnLoad="1"/>'
        return re.sub(r'<calcPr[^>]*/>', _add, wbx)
    return wbx.replace("</workbook>", '<calcPr calcId="0" fullCalcOnLoad="1"/></workbook>')

# ----------------------------------------------------------------- sheet lookup
def sheet_path_for(zin, sheet_name):
    wbx = zin.read("xl/workbook.xml").decode()
    rels = dict(re.findall(r'Id="([^"]+)"[^>]*Target="([^"]+)"', zin.read("xl/_rels/workbook.xml.rels").decode()))
    rid = dict(re.findall(r'<sheet[^>]*name="([^"]+)"[^>]*r:id="([^"]+)"', wbx))[sheet_name]
    tgt = rels[rid]
    return "xl/" + tgt.replace("../", "") if not tgt.startswith("/") else tgt[1:]

# ----------------------------------------------------------------- validation + atomic write
def validate_xlsx(path, min_sheets, must_have_parts):
    try:
        z = zipfile.ZipFile(path)
        names = set(z.namelist())
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=False)
        ok_sheets = len(wb.sheetnames) >= min_sheets
        ok_parts = all(any(n.startswith(p) for n in names) for p in must_have_parts)
        z.close()
        return ok_sheets and ok_parts, f"hojas={len(wb.sheetnames)} partes_ok={ok_parts}"
    except Exception as e:
        return False, f"no abre: {e}"

def update_regional(rows):
    src = REGIONAL_XLSX
    if not src.exists():
        log(f"[WARN] no existe {src} — se omite Regional"); return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    bak = BACKUP_DIR / f"{src.stem}__{datetime.datetime.now():%Y%m%d_%H%M%S}.xlsx"
    shutil.copy2(src, bak)
    tmp = src.with_suffix(".tmp.xlsx")
    with zipfile.ZipFile(src) as zin:
        s8 = sheet_path_for(zin, "Ventas Reales EC")
        new8, last = build_ventas_reales_ec_xml(zin.read(s8).decode(), rows)
        wbx = patch_fullcalc(zin.read("xl/workbook.xml").decode())
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zo:
            for n in zin.namelist():
                if n == s8:
                    zo.writestr(n, new8.encode())
                elif n == "xl/workbook.xml":
                    zo.writestr(n, wbx.encode())
                elif re.match(r'xl/worksheets/sheet\d+\.xml$', n):
                    # ECUADOR 2026 (fila REAL) y YTD vs Presupuesto (venta neta): rango + O->G
                    zo.writestr(n, patch_regional_refs(zin.read(n).decode(), last).encode())
                else:
                    zo.writestr(n, zin.read(n))
    ok, info = validate_xlsx(tmp, 8, ["xl/charts/"])
    if not ok:
        tmp.unlink(missing_ok=True)
        log(f"[ERROR] Regional no validó ({info}) — se conserva el original y el backup {bak.name}")
        return None
    os.replace(tmp, src)
    log(f"[OK] Regional actualizado ({info}); backup: {bak.name}")
    return bak

def update_analisis(rows):
    src = ANALISIS_XLSX
    if not src.exists():
        log(f"[WARN] no existe {src} — se omite Análisis"); return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    bak = BACKUP_DIR / f"{src.stem}__{datetime.datetime.now():%Y%m%d_%H%M%S}.xlsx"
    shutil.copy2(src, bak)
    tmp = src.with_suffix(".tmp.xlsx")
    with zipfile.ZipFile(src) as zin:
        sbd = sheet_path_for(zin, "BD")
        newbd, last = build_bd_xml(zin.read(sbd).decode(), rows)
        patched = patch_table_and_pivot(zin, zin.namelist(), {}, last, last)
        wbx = patch_fullcalc(zin.read("xl/workbook.xml").decode())
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zo:
            for n in zin.namelist():
                if n == sbd:
                    zo.writestr(n, newbd.encode())
                elif n in patched:                       # tabla + pivotCache (ref/refreshOnLoad)
                    zo.writestr(n, patched[n])
                elif n == "xl/workbook.xml":
                    zo.writestr(n, wbx.encode())
                elif n.startswith("xl/pivotTables/") and n.endswith(".xml"):
                    zo.writestr(n, patch_pivot_datafield(zin.read(n).decode()).encode())
                elif re.match(r'xl/worksheets/sheet\d+\.xml$', n):
                    zo.writestr(n, flip_total_to_subtotal(zin.read(n).decode()).encode())
                else:
                    zo.writestr(n, zin.read(n))
    ok, info = validate_xlsx(tmp, 14, ["xl/charts/", "xl/pivotTables/"])
    if not ok:
        tmp.unlink(missing_ok=True)
        log(f"[ERROR] Análisis no validó ({info}) — se conserva el original y el backup {bak.name}")
        return None
    os.replace(tmp, src)
    log(f"[OK] Análisis actualizado ({info}); backup: {bak.name}")
    return bak

# ----------------------------------------------------------------- presupuesto (targets) + resumen
def read_presupuesto_ecuador():
    """Lee del libro Regional el presupuesto anual por canal (hoja ECUADOR 2026)
    y el presupuesto YTD por canal. Devuelve dict por canal."""
    import openpyxl
    if not REGIONAL_XLSX.exists():
        return {}
    wb = openpyxl.load_workbook(REGIONAL_XLSX, data_only=True)
    ws = wb["ECUADOR 2026"]
    # filas subtotal por canal en ECUADOR 2026: RETAIL=23, DIGITAL=27, DIRECTO=30, ESPECIAL=34, MARKETPLACE=37, INTERCOMPANIA=38
    subt = {"RETAIL":23, "DIGITAL":27, "DIRECTO":30, "ESPECIAL":34, "MARKETPLACE":37, "INTERCOMPAÑIA":38}
    out = {}
    for canal, r in subt.items():
        mensual = [ws.cell(row=r, column=c).value or 0 for c in range(4, 16)]  # D..O = Ene..Dic
        anual = ws.cell(row=r, column=16).value or 0                            # P = TOTAL
        out[canal] = {"mensual": [float(v) for v in mensual], "anual": float(anual)}
    return out

def canal_por_cliente():
    """Mapa (dni10 -> canal) y (nombre_norm -> canal) desde DIM_Clients + BD del Análisis."""
    import openpyxl, unicodedata
    def norm(s):
        s = str(s or "").upper().strip()
        s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
        return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", " ", s)).strip()
    by_dni, by_name = {}, {}
    if ANALISIS_XLSX.exists():
        wb = openpyxl.load_workbook(ANALISIS_XLSX, data_only=True)
        if "BD" in wb.sheetnames:
            ws = wb["BD"]
            for r in range(2, ws.max_row + 1):
                dni = ws.cell(row=r, column=3).value; cli = ws.cell(row=r, column=4).value
                canal = ws.cell(row=r, column=22).value
                if not canal or str(canal).strip().upper() in ("NOTA DE CREDITO", "SIN CATEGORIZAR"):
                    continue
                if dni:
                    by_dni.setdefault(str(dni).strip()[:10], canal)
                if cli:
                    by_name.setdefault(norm(cli), canal)
        if "DIM_Clients" in wb.sheetnames:
            ws = wb["DIM_Clients"]
            for r in range(2, ws.max_row + 1):
                cli = ws.cell(row=r, column=1).value; cat = ws.cell(row=r, column=2).value
                if cli and cat and str(cat).strip().upper() != "NOTA DE CREDITO":
                    by_name.setdefault(norm(cli), cat)
    return by_dni, by_name, norm

def build_estado(rows):
    """Agrega real por canal x mes y por cliente; compara vs presupuesto."""
    by_dni, by_name, norm = canal_por_cliente()
    def canal_of(x):
        d = x["dni"].strip()[:10]
        if d in by_dni: return str(by_dni[d]).upper().replace("Ñ", "N")
        n = norm(x["cli"])
        return str(by_name.get(n, "SIN CANAL")).upper().replace("Ñ", "N")
    canal_mes = defaultdict(lambda: [0.0]*12)   # canal -> [12] neto
    cli_tot = defaultdict(float)
    sin_canal = defaultdict(float)
    total_mes = [0.0]*12
    n_fac = n_nc = 0
    for x in rows:
        c = canal_of(x); m = x["fecha"].month - 1
        val = x["subtotal"]          # SIN IVA (base imponible) — como el presupuesto
        canal_mes[c][m] += val
        total_mes[m] += val
        cli_tot[(x["cli"], c)] += val
        if c == "SIN CANAL": sin_canal[x["cli"]] += val
        if x["es_nc"]: n_nc += 1
        else: n_fac += 1
    ppto = read_presupuesto_ecuador()
    hoy = datetime.date.today(); mes_actual = hoy.month
    # Convención CFO: el YTD cierra en el último mes COMPLETO. El mes en curso
    # (parcial) se reporta aparte como MTD, para no distorsionar el cumplimiento.
    cierre = mes_actual - 1
    if cierre < 1:
        cierre = mes_actual          # enero: aún no hay mes cerrado -> usa el mes en curso
    canales = {}
    for c, arr in canal_mes.items():
        ytd = round(sum(arr[:cierre]), 2)
        pkey = c if c in ppto else {"INTERCOMPANIA": "INTERCOMPAÑIA"}.get(c, c)
        p = ppto.get(pkey, {})
        p_ytd = round(sum(p.get("mensual", [0]*12)[:cierre]), 2)
        p_anual = round(p.get("anual", 0), 2)
        canales[c] = {
            "mensual": [round(v, 2) for v in arr],
            "ytd_real": ytd, "ppto_ytd": p_ytd, "ppto_anual": p_anual,
            "cumpl_ytd": round(ytd / p_ytd, 4) if p_ytd else None,
            "avance_anual": round(ytd / p_anual, 4) if p_anual else None,
            "var_ytd": round(ytd - p_ytd, 2),
        }
    ytd_total = round(sum(total_mes[:cierre]), 2)
    ppto_ytd_total = round(sum(v["ppto_ytd"] for v in canales.values()), 2)
    ppto_anual_total = round(sum(v["ppto_anual"] for v in canales.values()), 2)
    # Mes en curso (MTD) — sólo si hay un mes parcial además del cierre
    mtd = None
    if mes_actual != cierre:
        p_mes = sum(ppto.get(k if k in ppto else {"INTERCOMPANIA":"INTERCOMPAÑIA"}.get(k,k), {})
                    .get("mensual", [0]*12)[mes_actual-1] for k in canales)
        r_mes = round(total_mes[mes_actual-1], 2)
        mtd = {"mes": mes_actual, "real": r_mes, "ppto": round(p_mes, 2),
               "cumpl": round(r_mes / p_mes, 4) if p_mes else None}
    top_sin = sorted(sin_canal.items(), key=lambda kv: -abs(kv[1]))[:15]
    return {
        "generado": datetime.datetime.now().isoformat(timespec="seconds"),
        "anio": YEAR, "mes_actual": mes_actual, "mes_cierre": cierre, "mtd": mtd,
        "meses": MESES,
        "n_facturas": n_fac, "n_nc": n_nc, "n_docs": n_fac + n_nc,
        "total_mensual_neto": [round(v, 2) for v in total_mes],
        "ytd_total": ytd_total,
        "ppto_ytd_total": ppto_ytd_total,
        "ppto_anual_total": ppto_anual_total,
        "cumpl_ytd_total": round(ytd_total / ppto_ytd_total, 4) if ppto_ytd_total else None,
        "avance_anual_total": round(ytd_total / ppto_anual_total, 4) if ppto_anual_total else None,
        "canales": canales,
        "clientes_sin_canal": [{"cliente": k, "monto": round(v, 2)} for k, v in top_sin],
        "monto_sin_canal": round(sum(sin_canal.values()), 2),
    }

# ----------------------------------------------------------------- companion workbook
def build_companion(estado):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Estado Presupuesto EC"
    ws.sheet_view.showGridLines = False
    NAVY = "1F3864"; HFILL = PatternFill("solid", fgColor=NAVY)
    HFONT = Font(color="FFFFFF", bold=True, size=10)
    TITLE = Font(color=NAVY, bold=True, size=15); GREY = Font(color="595959", size=9)
    MONEY = '"$"#,##0'; PCT = '0.0%'
    thin = Side(style="thin", color="D9D9D9"); BORDER = Border(thin, thin, thin, thin)
    ws.merge_cells("A1:P1"); ws["A1"] = "ESTADO DEL PRESUPUESTO COMERCIAL — ECUADOR (Perseo) · cifras netas SIN IVA"; ws["A1"].font = TITLE
    ws.merge_cells("A2:P2")
    ws["A2"] = f"Actualizado: {estado['generado']}   |   YTD a {estado['meses'][estado['mes_actual']-1]}   |   Docs: {estado['n_docs']} (Fact {estado['n_facturas']} / NC {estado['n_nc']})"
    ws["A2"].font = GREY
    # KPIs
    kp = [("Ventas netas YTD", estado["ytd_total"], MONEY),
          ("Presupuesto YTD", estado["ppto_ytd_total"], MONEY),
          ("Cumplimiento YTD", estado["cumpl_ytd_total"], PCT),
          ("Presupuesto anual", estado["ppto_anual_total"], MONEY),
          ("Avance anual", estado["avance_anual_total"], PCT)]
    col = 1
    for label, val, fmt in kp:
        ws.cell(row=4, column=col, value=label).font = Font(color="595959", bold=True, size=9)
        c = ws.cell(row=5, column=col, value=val); c.font = Font(color=NAVY, bold=True, size=12)
        if val is not None: c.number_format = fmt
        col += 3
    # tabla canal x mes
    hdr = ["Canal"] + estado["meses"] + ["YTD real", "Ppto YTD", "Cumpl%", "Var $", "Ppto año", "Avance año"]
    hr = 7
    for j, h in enumerate(hdr, 1):
        c = ws.cell(row=hr, column=j, value=h); c.fill = HFILL; c.font = HFONT
        c.alignment = Alignment(horizontal="center"); c.border = BORDER
    r = hr + 1
    orden = ["RETAIL","DIGITAL","DIRECTO","ESPECIAL","MARKETPLACE","INTERCOMPANIA","SIN CANAL"]
    canales = estado["canales"]
    for c in orden + [k for k in canales if k not in orden]:
        if c not in canales: continue
        d = canales[c]
        ws.cell(row=r, column=1, value=c).font = Font(bold=True, size=10)
        for m in range(12):
            cell = ws.cell(row=r, column=2+m, value=d["mensual"][m]); cell.number_format = MONEY; cell.border = BORDER
        vals = [("YTD", d["ytd_real"], MONEY), ("PPT", d["ppto_ytd"], MONEY),
                ("CMP", d["cumpl_ytd"], PCT), ("VAR", d["var_ytd"], MONEY),
                ("PPA", d["ppto_anual"], MONEY), ("AVA", d["avance_anual"], PCT)]
        for k, (_, v, fmt) in enumerate(vals):
            cell = ws.cell(row=r, column=14+k, value=v)
            if v is not None: cell.number_format = fmt
            cell.border = BORDER
        r += 1
    # total
    ws.cell(row=r, column=1, value="TOTAL EC").font = Font(bold=True)
    for m in range(12):
        cell = ws.cell(row=r, column=2+m, value=estado["total_mensual_neto"][m]); cell.number_format = MONEY
    ws.cell(row=r, column=14, value=estado["ytd_total"]).number_format = MONEY
    ws.cell(row=r, column=15, value=estado["ppto_ytd_total"]).number_format = MONEY
    ws.cell(row=r, column=16, value=estado["cumpl_ytd_total"]).number_format = PCT
    ws.cell(row=r, column=18, value=estado["ppto_anual_total"]).number_format = MONEY
    ws.cell(row=r, column=19, value=estado["avance_anual_total"]).number_format = PCT
    ws.column_dimensions["A"].width = 16
    for cl in "BCDEFGHIJKLM": ws.column_dimensions[cl].width = 10
    for cl in ["N","O","P","Q","R","S"]: ws.column_dimensions[cl].width = 11
    # alertas / sin canal
    if estado["clientes_sin_canal"]:
        r += 2
        ws.cell(row=r, column=1, value=f"CLIENTES SIN CANAL ASIGNADO (total ${estado['monto_sin_canal']:,.0f})").font = Font(color="C00000", bold=True)
        r += 1
        for it in estado["clientes_sin_canal"]:
            ws.cell(row=r, column=1, value=it["cliente"])
            ws.cell(row=r, column=2, value=it["monto"]).number_format = MONEY
            r += 1
    out = OUT_DIR / "ESTADO_PRESUPUESTO_ECUADOR.xlsx"
    wb.save(out)
    return out

# ----------------------------------------------------------------- MAIN
def run_update():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    hoy = datetime.date.today()
    dias = (hoy - datetime.date(YEAR, 1, 1)).days + 2   # cubre todo el año en curso
    log(f"Consultando Perseo (dias={dias}, año={YEAR}) ...")
    facturas = fetch_facturas(dias)
    rows = normalize(facturas, YEAR)
    log(f"Transacciones {YEAR}: {len(rows)}")
    if not rows:
        log("[WARN] sin transacciones del año; no se modifica nada.")
        return None
    # Por defecto NO se editan los Excel curados (Regional/Análisis): esa edición
    # quirúrgica dejaba el archivo medio-convertido e incongruente. La automatización
    # produce un reporte limpio aparte. Para reactivar la edición in-situ: PERSEO_WRITE_XLSX=1
    if os.environ.get("PERSEO_WRITE_XLSX") == "1":
        update_regional(rows)
        update_analisis(rows)
    estado = build_estado(rows)
    comp = build_companion(estado)
    (OUT_DIR / "estado_presupuesto.json").write_text(
        json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"[OK] compañero: {comp}")
    log(f"[OK] YTD neto EC: ${estado['ytd_total']:,.2f}  cumpl YTD: "
        f"{(estado['cumpl_ytd_total'] or 0)*100:.1f}%")
    return estado

if __name__ == "__main__":
    try:
        run_update()
    except SystemExit:
        raise
    except Exception:
        log("[ERROR] fallo no controlado:\n" + traceback.format_exc())
        sys.exit(1)
