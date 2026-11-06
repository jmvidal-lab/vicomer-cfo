#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
odoo_presupuesto.py  ·  v2 (2026-08) — los 3 países en Odoo
===========================================================
Compara las ventas reales de Odoo (Ecuador + Colombia VINTRAL + Costa Rica, SIN IVA)
contra el presupuesto, y genera un libro-compañero + JSON.

Ecuador migró de Perseo a Odoo. Cambios respecto a v1:
  - Ecuador ya NO se descarta: `company_map` lo mapea igual que a los otros países.
  - Presupuesto de Ecuador leído del Regional (hoja ECUADOR 2026, suma de canales).
  - Canal comercial de Ecuador reconstruido desde Odoo cruzando el RUC del cliente
    (`res.partner.vat`) contra el maestro DIM_Clients. Si Odoo no trae RUC, el canal
    cae en "SIN CANAL" y se reporta como advertencia — NO se silencia.
  - Histórico pre-migración por país configurable: `<pais>_hist_mensual`.

- Extrae facturas con odoo_ventas.fetch_facturas (amount_untaxed_signed = sin IVA).
- Lee el presupuesto por país del libro Regional:
    ECUADOR 2026   -> suma de subtotales por canal (RETAIL, DIGITAL, ...)      [USD]
    COLOMBIA 2026  -> fila 23 "TOTAL CAPA 1" (D23:O23 mensual, P23 anual)      [COP]
    COSTA RICA 2026-> fila 15 "TOTAL COSTA RICA" (D15:O15 mensual, P15 anual)
- YTD = hasta el último mes cerrado.
- Salida: OdooVentas/ESTADO_PRESUPUESTO_ODOO.xlsx  + estado_odoo.json

NO modifica los presupuestos; solo crea archivos nuevos.

Config en odoo_config.json:
    "company_map": { "VICOMER": "Ecuador", "VINTRAL": "Colombia", "3-102-940094": "Costa Rica" }
    "ecuador_hist_mensual": {"1": 123456.78, ...}   # meses anteriores al corte, desde Perseo
    "colombia_hist_mensual": {...}

Uso:  python3 odoo_presupuesto.py            (año actual)
      python3 odoo_presupuesto.py 2026
      python3 odoo_presupuesto.py autotest    (lógica offline, sin red)
Prueba: ODOO_LOCAL_JSON=archivo.json python3 odoo_presupuesto.py 2026
"""
import os, sys, json, datetime
from pathlib import Path
from collections import defaultdict

import odoo_ventas as OV

HOME = Path.home()
FILES_DIR = Path(os.environ.get("PERSEO_FILES_DIR", HOME / "Desktop" / "VICOMER COMERCIAL"))
REGIONAL_XLSX = FILES_DIR / "PRESUPUESTO COMERCIAL REGIONAL 2026 - GRUPO VICOMER.xlsx"
OUT_DIR = OV.OUT_DIR
MESES = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]

def log(m): OV.log(m)

# La config se busca primero junto al script (así funciona sin importar el HOME),
# y sólo después en la ruta canónica del proyecto.
CFG_CANDIDATOS = [Path(__file__).resolve().parent / "odoo_config.json",
                  HOME / "Claude" / "Projects" / "CFO VICOMER" / "odoo_config.json",
                  HOME / ".odoo_config.json"]
CANALES_ORDEN = ["RETAIL", "DIGITAL", "DIRECTO", "ESPECIAL", "MARKETPLACE",
                 "INTERCOMPANIA", "SIN CANAL"]


def _cfg():
    for p in CFG_CANDIDATOS:
        try:
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
    return {}


# ------------------------------------------------------------------ presupuesto por país
def read_budgets():
    import openpyxl
    out = {}
    if not REGIONAL_XLSX.exists():
        log(f"[WARN] no existe {REGIONAL_XLSX}; sin presupuesto de referencia.")
        return out
    wb = openpyxl.load_workbook(REGIONAL_XLSX, data_only=True)
    def row(sheet, r):
        ws = wb[sheet]
        mensual = [float(ws.cell(row=r, column=c).value or 0) for c in range(4, 16)]  # D..O
        anual = float(ws.cell(row=r, column=16).value or 0)                            # P
        return {"mensual": mensual, "anual": anual}
    if "COLOMBIA 2026" in wb.sheetnames:
        out["Colombia"] = row("COLOMBIA 2026", 23)     # TOTAL CAPA 1 (target base, COP)
    if "COSTA RICA 2026" in wb.sheetnames:
        out["Costa Rica"] = row("COSTA RICA 2026", 15)  # TOTAL COSTA RICA
    # Ecuador: el presupuesto vive por canal en la hoja ECUADOR 2026. Se reutiliza el
    # lector de perseo_presupuesto porque el presupuesto es del Excel, NO del ERP:
    # la migración a Odoo no lo cambia.
    try:
        import perseo_presupuesto as PE
        ppto_canal = PE.read_presupuesto_ecuador()
        if ppto_canal:
            mensual = [0.0] * 12
            anual = 0.0
            for c in ppto_canal.values():
                for i in range(12):
                    mensual[i] += float(c["mensual"][i])
                anual += float(c["anual"])
            out["Ecuador"] = {"mensual": mensual, "anual": anual, "por_canal": ppto_canal}
    except Exception as e:
        log(f"[WARN] no pude leer el presupuesto de Ecuador (hoja ECUADOR 2026): {e}")
    return out


def read_history():
    """Ventas de meses YA CERRADOS anteriores al corte de migración, por país.

    Colombia Ene-Mar 2026 = instancia Odoo ANTERIOR (vintral1.odoo.com, COP), sin IVA,
    capturados por API el 2026-07-05; el Odoo actual aporta desde ABRIL.
    Ecuador = meses facturados en Perseo antes del corte de agosto 2026, si Odoo no los
    tiene cargados. Vacío por defecto: hay que llenarlo tras verificar con odoo_descubrir.py.

    Configurable en odoo_config.json -> "<pais>_hist_mensual": {"1":..,"2":..}.
    """
    hist = {"Colombia": {"mensual": {1: 121934422.21, 2: 82011090.76, 3: 58375627.82}}}
    cfg = _cfg()
    for pais, clave in [("Colombia", "colombia_hist_mensual"), ("Ecuador", "ecuador_hist_mensual")]:
        ch = cfg.get(clave)
        if ch:
            try:
                hist[pais] = {"mensual": {int(k): float(v) for k, v in ch.items()}}
            except (TypeError, ValueError):
                log(f"[WARN] {clave} mal formado en odoo_config.json; se ignora")
    return hist


# ------------------------------------------------------------------ canal comercial (Ecuador)
def canal_resolver():
    """Devuelve una función factura -> canal, o None si no hay maestro de clientes.

    Cruza primero por RUC/cédula (10 dígitos) y luego por nombre normalizado, igual
    que hacía perseo_presupuesto. La diferencia es la fuente del RUC: ahora viene de
    `res.partner.vat` de Odoo en vez del campo `identificacion` del SRI en Perseo.
    """
    try:
        import perseo_presupuesto as PE
        by_dni, by_name, norm = PE.canal_por_cliente()
    except Exception as e:
        log(f"[WARN] sin maestro de canales (DIM_Clients): {e}")
        return None
    if not by_dni and not by_name:
        return None

    def canal_of(r):
        d = str(r.get("dni") or "").strip()[:10]
        if d and d in by_dni:
            return str(by_dni[d]).upper().replace("Ñ", "N")
        n = norm(r.get("cliente"))
        return str(by_name.get(n, "SIN CANAL")).upper().replace("Ñ", "N")

    return canal_of


def build_canales(rows_pais, ppto_canal, cierre, hist_mensual=None):
    """Arma el bloque `canales` (mismo contrato que producía perseo_presupuesto).

    `hist_mensual` = {mes: monto} de los meses anteriores al corte de migración, que
    vienen de Perseo y NO tienen desglose por canal. Se cargan en una línea propia
    ("HISTORICO PRE-ODOO") en vez de repartirlos con un criterio inventado: así la
    suma de canales cuadra con el total del país y queda explícito qué parte del YTD
    no es atribuible a un canal.
    """
    resolver = canal_resolver()
    if resolver is None:
        return None, ["No hay maestro DIM_Clients: no se pudo abrir el canal comercial."]
    canal_mes = defaultdict(lambda: [0.0] * 12)
    sin_canal_clientes = defaultdict(float)
    sin_dni = 0
    for r in rows_pais:
        c = resolver(r)
        canal_mes[c][int(r["mes"]) - 1] += float(r["subtotal"])
        if not str(r.get("dni") or "").strip():
            sin_dni += 1
        if c == "SIN CANAL":
            sin_canal_clientes[r.get("cliente")] += float(r["subtotal"])

    # Los meses históricos REEMPLAZAN lo que Odoo tenga en ese mes (mismo criterio que
    # el total del país), y se aíslan en su propia línea.
    hist_mensual = hist_mensual or {}
    if hist_mensual:
        hl = [0.0] * 12
        for mnum, val in hist_mensual.items():
            i = int(mnum) - 1
            if 0 <= i < 12:
                hl[i] = float(val)
                for canal in canal_mes:
                    canal_mes[canal][i] = 0.0
        canal_mes["HISTORICO PRE-ODOO"] = hl

    out = {}
    for canal, mensual in canal_mes.items():
        mensual = [round(v, 2) for v in mensual]
        ytd = round(sum(mensual[:cierre]), 2)
        b = (ppto_canal or {}).get(canal) or (ppto_canal or {}).get(canal.replace("NIA", "ÑIA")) or {}
        p_men = b.get("mensual", [0] * 12)
        p_ytd = round(sum(p_men[:cierre]), 2)
        p_anual = round(float(b.get("anual", 0)), 2)
        out[canal] = {
            "mensual": mensual, "ytd_real": ytd, "ppto_ytd": p_ytd, "ppto_anual": p_anual,
            "cumpl_ytd": round(ytd / p_ytd, 4) if p_ytd else None,
            "avance_anual": round(ytd / p_anual, 4) if p_anual else None,
            "var_ytd": round(ytd - p_ytd, 2),
        }
    avisos = []
    if hist_mensual:
        avisos.append(f"{len(hist_mensual)} mes(es) previos al corte de migración vienen de "
                      f"Perseo sin desglose de canal: aparecen en la línea "
                      f"'HISTORICO PRE-ODOO'. El cumplimiento por canal sólo es comparable "
                      f"desde el mes del corte.")
    total = sum(sum(c["mensual"]) for c in out.values())
    sc = out.get("SIN CANAL", {})
    sc_total = sum(sc.get("mensual", []))
    if total and sc_total / total > 0.10:
        avisos.append(f"{sc_total/total*100:.0f}% de las ventas quedó en SIN CANAL "
                      f"({len(sin_canal_clientes)} clientes). Los nombres de Odoo no coinciden "
                      f"con DIM_Clients: revisar el maestro antes de usar el desglose por canal.")
    if sin_dni:
        avisos.append(f"{sin_dni} facturas sin RUC en Odoo (res.partner.vat vacío): "
                      f"su canal se resolvió sólo por nombre.")
    return out, avisos


# ------------------------------------------------------------------ mapeo compañía -> país
def classify(empresa, moneda, company_map):
    """Mapea una compañía Odoo a país. Gana el fragmento MÁS LARGO que coincida,
    para que una clave corta no capture por accidente a otra compañía."""
    if company_map and empresa:
        e = empresa.lower()
        mejor, mejor_len = None, -1
        for key, pais in company_map.items():
            if key and key.lower() in e and len(key) > mejor_len:
                mejor, mejor_len = pais, len(key)
        if mejor:
            return mejor
    m = (moneda or "").upper()
    if m == "COP":
        return "Colombia"
    if m in ("CRC",):
        return "Costa Rica"
    # USD u otra: si el nombre delata Costa Rica
    if empresa and ("SRL" in empresa.upper() or "COSTA" in empresa.upper() or "RICA" in empresa.upper()):
        return "Costa Rica"
    if empresa and ("VINTRAL" in empresa.upper() or "COLOMBIA" in empresa.upper()):
        return "Colombia"
    return "(sin mapear)"

# ------------------------------------------------------------------ facturas (Odoo o local)
def get_facturas(year):
    lj = os.environ.get("ODOO_LOCAL_JSON")
    if lj:
        log(f"[TEST] facturas desde archivo local: {lj}")
        d = json.loads(Path(lj).read_text(encoding="utf-8"))
        return d.get("facturas", d) if isinstance(d, dict) else d
    cfg = OV.load_config()
    od = OV.Odoo(cfg); od.authenticate()
    return OV.fetch_facturas(od, year)

# ------------------------------------------------------------------ estado
def build_estado(rows, year, budgets=None, hist=None, hoy=None):
    company_map = _cfg().get("company_map", {})
    budgets = read_budgets() if budgets is None else budgets
    hist = read_history() if hist is None else hist
    hoy = hoy or datetime.date.today()
    cierre = (hoy.month - 1) if year == hoy.year else 12
    if cierre < 1:
        cierre = hoy.month
    paises = defaultdict(lambda: {"moneda": None, "mensual": [0.0]*12, "n": 0,
                                  "sin_map_empresas": set(), "rows": []})
    for r in rows:
        pais = classify(r.get("empresa"), r.get("moneda"), company_map)
        if pais == "ignore":       # compañía deliberadamente excluida del consolidado
            continue
        p = paises[pais]
        p["moneda"] = r.get("moneda") or p["moneda"]
        p["mensual"][int(r["mes"])-1] += float(r["subtotal"])   # SIN IVA neto
        p["n"] += 1
        p["rows"].append(r)
        if pais == "(sin mapear)":
            p["sin_map_empresas"].add(r.get("empresa"))
    salida = {}
    for pais, p in paises.items():
        mensual = [round(v, 2) for v in p["mensual"]]
        h = hist.get(pais)
        if h and h.get("mensual"):
            # el histórico (Odoo anterior) REEMPLAZA esos meses (el Odoo actual = 0 ahí)
            for mnum, val in h["mensual"].items():
                if 1 <= mnum <= 12:
                    mensual[mnum-1] = round(float(val), 2)
            hist_through = max(int(k) for k in h["mensual"].keys())
            hist_amount = round(sum(float(v) for v in h["mensual"].values()), 2)
        else:
            hist_through, hist_amount = 0, 0.0
        ytd = round(sum(mensual[:cierre]), 2)
        b = budgets.get(pais, {})
        p_men = b.get("mensual", [0]*12); p_ytd = round(sum(p_men[:cierre]), 2); p_anual = round(b.get("anual", 0), 2)
        d = {
            "moneda": p["moneda"], "n_facturas": p["n"], "mensual": mensual,
            "hist_amount": hist_amount, "hist_through": hist_through,
            "ytd_real": ytd, "ppto_ytd": p_ytd, "ppto_anual": p_anual,
            "cumpl_ytd": round(ytd / p_ytd, 4) if p_ytd else None,
            "avance_anual": round(ytd / p_anual, 4) if p_anual else None,
            "var_ytd": round(ytd - p_ytd, 2),
            "empresas_sin_mapear": sorted(x for x in p["sin_map_empresas"] if x),
            "avisos": [],
        }
        # MTD: el mes en curso, parcial, reportado aparte para no ensuciar el YTD.
        if year == hoy.year and cierre < 12:
            d["mtd"] = {"mes": hoy.month, "real": mensual[hoy.month - 1]}
        # Desglose por canal: hoy sólo existe maestro para Ecuador.
        if pais == "Ecuador":
            canales, avisos = build_canales(p["rows"], b.get("por_canal"), cierre,
                                            hist_mensual=(h or {}).get("mensual"))
            if canales:
                d["canales"] = canales
            d["avisos"].extend(avisos)
            # El aviso mira el dato REALMENTE usado en esta corrida, no la config:
            # así el autotest es reproducible y la alerta no depende de un archivo externo.
            if not hist_amount:
                d["avisos"].append(
                    "Sin histórico pre-migración cargado: si Odoo no tiene la facturación "
                    "de Ecuador anterior al corte, el YTD está subestimado. Llenar "
                    "'ecuador_hist_mensual' en odoo_config.json.")
            elif hist_through < cierre:
                d["avisos"].append(
                    f"El histórico de Perseo llega hasta {MESES[hist_through-1]} pero el YTD "
                    f"cierra en {MESES[cierre-1]}: los meses intermedios sólo cuentan lo que "
                    f"haya en Odoo. Completar 'ecuador_hist_mensual' hasta el mes de corte.")
        salida[pais] = d
    return {"generado": datetime.datetime.now().isoformat(timespec="seconds"),
            "anio": year, "mes_cierre": cierre, "meses": MESES, "paises": salida}

# ------------------------------------------------------------------ companion
def build_companion(est):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Estado CO-CR"
    ws.sheet_view.showGridLines = False
    NAVY="1F3864"; HFILL=PatternFill("solid",fgColor=NAVY); HFONT=Font(color="FFFFFF",bold=True,size=10)
    thin=Side(style="thin",color="D9D9D9"); BORDER=Border(thin,thin,thin,thin)
    ws.merge_cells("A1:P1"); ws["A1"]="ESTADO DEL PRESUPUESTO — GRUPO VICOMER (Odoo) · cifras netas SIN IVA"
    ws["A1"].font=Font(color=NAVY,bold=True,size=14)
    ws.merge_cells("A2:P2"); ws["A2"]=f"Actualizado: {est['generado']} · YTD a {est['meses'][est['mes_cierre']-1]} {est['anio']}"
    ws["A2"].font=Font(color="595959",size=9)
    r=4
    for pais, d in est["paises"].items():
        moneda=d["moneda"] or ""
        fmt=f'#,##0" {moneda}"'
        ws.cell(row=r,column=1,value=f"{pais}  ({moneda})").font=Font(color=NAVY,bold=True,size=12)
        r+=1
        hdr=["Concepto"]+est["meses"]+["YTD","Ppto YTD","Cumpl%","Var","Ppto año"]
        for j,h in enumerate(hdr,1):
            c=ws.cell(row=r,column=j,value=h); c.fill=HFILL; c.font=HFONT; c.alignment=Alignment(horizontal="center"); c.border=BORDER
        r+=1
        ws.cell(row=r,column=1,value="Real (sin IVA)").font=Font(bold=True)
        for m in range(12):
            c=ws.cell(row=r,column=2+m,value=d["mensual"][m]); c.number_format=fmt; c.border=BORDER
        ws.cell(row=r,column=14,value=d["ytd_real"]).number_format=fmt
        ws.cell(row=r,column=15,value=d["ppto_ytd"]).number_format=fmt
        cc=ws.cell(row=r,column=16,value=d["cumpl_ytd"]); cc.number_format='0.0%'
        ws.cell(row=r,column=17,value=d["var_ytd"]).number_format=fmt
        ws.cell(row=r,column=18,value=d["ppto_anual"]).number_format=fmt
        r+=1
        if d.get("hist_amount"):
            ws.cell(row=r,column=1,value=(f"(incluye histórico Ene-{est['meses'][d['hist_through']-1]} del Odoo anterior: "
                                          f"{d['hist_amount']:,.0f} {moneda}; Odoo aporta desde el mes siguiente)")).font=Font(color="595959",size=9,italic=True)
            r+=1
        if d.get("empresas_sin_mapear"):
            ws.cell(row=r,column=1,value="Empresas sin mapear: "+", ".join(d["empresas_sin_mapear"])).font=Font(color="C00000",size=9)
            r+=1
        for a in d.get("avisos", []):
            ws.cell(row=r,column=1,value="⚠ "+a).font=Font(color="B9770E",size=9,italic=True)
            r+=1
        r+=1
    ws.column_dimensions["A"].width=22
    for cl in "BCDEFGHIJKLM": ws.column_dimensions[cl].width=13
    for cl in ["N","O","P","Q","R"]: ws.column_dimensions[cl].width=14
    # Solo en OdooVentas: la carpeta VICOMER COMERCIAL lleva UN solo archivo, el consolidado (estado_grupo.py)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pth = OUT_DIR / "ESTADO_PRESUPUESTO_ODOO.xlsx"; wb.save(pth)
    return pth

# ------------------------------------------------------------------ main
def run(year):
    rows = get_facturas(year)
    log(f"facturas {year}: {len(rows)}")
    est = build_estado(rows, year)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR/"estado_odoo.json").write_text(json.dumps(est, ensure_ascii=False, indent=2), encoding="utf-8")
    comp = build_companion(est)
    for pais, d in est["paises"].items():
        cu = f"{d['cumpl_ytd']*100:.0f}%" if d["cumpl_ytd"] is not None else "s/ppto"
        log(f"  {pais}: YTD sin IVA = {d['ytd_real']:,.0f} {d['moneda'] or ''}  vs ppto {d['ppto_ytd']:,.0f}  = {cu}  ({d['n_facturas']} fact)")
        for a in d.get("avisos", []):
            log(f"    [AVISO] {a}")
    log(f"[OK] compañero -> {comp}")
    return est


# ------------------------------------------------------------------ autotest offline
def autotest():
    """Prueba la clasificación y el armado sin tocar la red ni los Excel."""
    fallos = []
    def check(cond, msg):
        (print(f"  ok  {msg}") if cond else fallos.append(msg))

    cmap = {"VICOMER": "Ecuador", "VINTRAL": "Colombia", "3-102-940094": "Costa Rica"}
    check(classify("VICOMER S.A.", "USD", cmap) == "Ecuador", "VICOMER -> Ecuador (ya no 'ignore')")
    check(classify("VINTRAL S.A.S", "COP", cmap) == "Colombia", "VINTRAL -> Colombia")
    check(classify("3-102-940094 SRL", "CRC", cmap) == "Costa Rica", "cédula jurídica -> Costa Rica")
    check(classify("CASA MAGNA LTDA", "COP", cmap) == "Colombia", "sin mapa cae a moneda COP")
    check(classify("NUEVA CO S.A.", "USD", cmap) == "(sin mapear)", "USD desconocida se marca sin mapear")
    # una clave corta no debe capturar a otra compañía: gana el fragmento más largo
    check(classify("VICOMER LOGISTICA S.A.", "USD",
                   {"VICOMER": "Ecuador", "VICOMER LOGISTICA": "ignore"}) == "ignore",
          "gana el fragmento más largo del company_map")

    rows = [
        {"empresa": "VICOMER S.A.", "moneda": "USD", "mes": 1, "subtotal": 1000.0,
         "cliente": "CLIENTE A", "dni": "0912345678"},
        {"empresa": "VICOMER S.A.", "moneda": "USD", "mes": 2, "subtotal": 500.0,
         "cliente": "CLIENTE B", "dni": ""},
        {"empresa": "VINTRAL S.A.S", "moneda": "COP", "mes": 1, "subtotal": 9_000_000.0,
         "cliente": "CLI CO", "dni": ""},
    ]
    budgets = {"Ecuador": {"mensual": [750.0] * 12, "anual": 9000.0, "por_canal": {}},
               "Colombia": {"mensual": [8_000_000.0] * 12, "anual": 96_000_000.0}}
    est = build_estado(rows, 2026, budgets=budgets, hist={}, hoy=datetime.date(2026, 4, 15))

    ec = est["paises"]["Ecuador"]
    co = est["paises"]["Colombia"]
    check(est["mes_cierre"] == 3, "YTD cierra en el último mes completo (marzo)")
    check(ec["ytd_real"] == 1500.0, "Ecuador suma sus facturas de Odoo")
    check(ec["ppto_ytd"] == 2250.0, "presupuesto YTD de Ecuador = 3 meses")
    check(ec["moneda"] == "USD", "Ecuador en USD")
    check(co["ytd_real"] == 9_000_000.0, "Colombia sigue funcionando igual")
    check(any("histórico pre-migración" in a for a in ec["avisos"]),
          "avisa si falta el histórico pre-migración de Ecuador")
    check(ec.get("mtd", {}).get("mes") == 4, "el mes en curso se reporta como MTD, fuera del YTD")

    est_h = build_estado(rows, 2026, budgets=budgets,
                         hist={"Ecuador": {"mensual": {1: 4000.0}}},
                         hoy=datetime.date(2026, 4, 15))
    ech = est_h["paises"]["Ecuador"]
    check(ech["mensual"][0] == 4000.0, "el histórico REEMPLAZA el mes, no se suma")
    check(ech["ytd_real"] == 4500.0, "YTD con histórico = 4000 + 500")
    check(ech["hist_through"] == 1 and ech["hist_amount"] == 4000.0, "metadatos del histórico")
    check(any("llega hasta Ene" in a for a in ech["avisos"]),
          "avisa si el histórico no cubre hasta el mes de cierre (Ene < Mar)")

    est_c = build_estado(rows, 2026, budgets=budgets,
                         hist={"Ecuador": {"mensual": {1: 4000.0, 2: 500.0, 3: 700.0}}},
                         hoy=datetime.date(2026, 4, 15))
    hist_avisos = [a for a in est_c["paises"]["Ecuador"]["avisos"]
                   if "histórico" in a or "llega hasta" in a]
    check(not hist_avisos, "sin avisos de histórico cuando éste cubre todo el YTD")

    print()
    if fallos:
        for f in fallos:
            print(f"  FALLA  {f}")
        sys.exit(f"AUTOTEST: {len(fallos)} fallas")
    print("AUTOTEST OK — clasificación, YTD, histórico y avisos.")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "autotest":
        autotest()
        sys.exit(0)
    yr = int(arg) if arg.isdigit() else datetime.date.today().year
    try:
        run(yr)
    except SystemExit:
        raise
    except Exception:
        import traceback; log("[ERROR]\n"+traceback.format_exc()); sys.exit(1)
