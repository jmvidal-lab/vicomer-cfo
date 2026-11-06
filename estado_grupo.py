#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
estado_grupo.py
===============
Genera UN solo reporte consolidado, limpio y congruente, del presupuesto comercial
del Grupo VICOMER (Ecuador + Colombia + Costa Rica), TODO sin IVA.

Desde agosto 2026 los TRES países salen de Odoo (amount_untaxed_signed, sin IVA),
cada uno en su moneda (USD / COP / USD-CRC). Ecuador migró de Perseo a Odoo.

- Ecuador: Odoo (compañía VICOMER). El desglose por canal se reconstruye cruzando
  el RUC del cliente contra DIM_Clients. Los meses anteriores al corte de migración
  salen de `ecuador_hist_mensual` en odoo_config.json (facturación histórica de Perseo).
- Colombia (VINTRAL): histórico Ene-Mar de la instancia anterior + Odoo desde abril.
- Costa Rica: Odoo.

Perseo queda como RESPALDO de Ecuador: si Odoo no devuelve nada para Ecuador, se
usa Perseo y el reporte lo señala. Forzar con ESTADO_GRUPO_EC=perseo|odoo.

Salida (NO toca los Excel curados):
  - VICOMER COMERCIAL/ESTADO PRESUPUESTO GRUPO VICOMER.xlsx   (Resumen + hoja por país)
  - PresupuestoAuto/estado_grupo.json                         (lo consume el correo)

YTD = hasta el último mes CERRADO (el mes en curso se reporta aparte).
Uso:  python3 estado_grupo.py [año]
"""
import os, sys, json, datetime, traceback
from pathlib import Path

import perseo_presupuesto as PE
import odoo_presupuesto as OD

FILES_DIR = PE.FILES_DIR                 # VICOMER COMERCIAL
OUT_DIR   = PE.OUT_DIR                    # PresupuestoAuto (json + logs)
MESES     = PE.MESES
CONSOLIDADO = FILES_DIR / "ESTADO PRESUPUESTO GRUPO VICOMER.xlsx"

NAVY="1F3864"; GREEN="2E7D32"; RED="C00000"; AMBER="B9770E"; GREY="595959"

def log(m): PE.log(m)

def read_rate():
    """Tasa COP/USD para consolidar (celda C13 de la hoja RESUMEN del Regional; ajustable ahí)."""
    import openpyxl
    try:
        wb = openpyxl.load_workbook(FILES_DIR / "PRESUPUESTO COMERCIAL REGIONAL 2026 - GRUPO VICOMER.xlsx", data_only=True)
        v = wb["RESUMEN"]["C13"].value
        if v and float(v) > 0:
            return float(v)
    except Exception:
        pass
    return 3700.0

def add_global_usd(est):
    """Agrega el total consolidado en USD (Colombia COP -> USD con la tasa del Regional)."""
    rate = read_rate()
    def usd(d, key):
        v = d.get(key)
        if v is None: return 0.0
        return v / rate if (d.get("moneda") == "COP") else float(v)
    real = ppto = anual = 0.0
    for pais, d in est["paises"].items():
        if pais.startswith("_"): continue
        real += usd(d, "ytd_real"); ppto += usd(d, "ppto_ytd"); anual += usd(d, "ppto_anual")
    est["global_usd"] = {"rate": rate, "real": round(real, 2), "ppto": round(ppto, 2),
                         "ppto_anual": round(anual, 2),
                         "cumpl": round(real/ppto, 4) if ppto else None,
                         "avance_anual": round(real/anual, 4) if anual else None}
    return est

# ------------------------------------------------------------------ recolectar
def collect(year):
    """Devuelve dict unificado {pais: {...}} con Ecuador (USD), Colombia (COP), Costa Rica (USD)."""
    paises = {}
    avisos = []
    hoy = datetime.date.today()
    cierre = (year != hoy.year) and 12 or max(hoy.month - 1, 1)
    modo_ec = (os.environ.get("ESTADO_GRUPO_EC") or "auto").lower()

    # ---- Los 3 países desde Odoo ----
    try:
        rows = OD.get_facturas(year)
        od = OD.build_estado(rows, year)
        cierre = od.get("mes_cierre", cierre)
        for pais, d in od["paises"].items():
            if pais == "(sin mapear)":
                paises.setdefault("_sin_mapear", d)
                avisos.append("Hay compañías Odoo sin mapear a país: "
                              + ", ".join(d.get("empresas_sin_mapear") or []))
                continue
            d = dict(d); d["fuente"] = "Odoo"; d["n"] = d.get("n_facturas")
            paises[pais] = d
            for a in d.get("avisos", []):
                avisos.append(f"{pais}: {a}")
    except SystemExit as e:
        log(f"[WARN] Odoo no disponible: {e}")
        avisos.append(f"Odoo no disponible: {e}")
    except Exception:
        log("[WARN] Odoo falló:\n" + traceback.format_exc())
        avisos.append("Odoo falló (ver log)")

    # ---- Ecuador: respaldo Perseo si Odoo no lo trajo ----
    ec_odoo_ok = bool(paises.get("Ecuador", {}).get("ytd_real"))
    usar_perseo = (modo_ec == "perseo") or (modo_ec == "auto" and not ec_odoo_ok)
    if usar_perseo:
        if modo_ec == "auto":
            log("[WARN] Ecuador no vino de Odoo — cayendo al respaldo Perseo")
            avisos.append("Ecuador salió del RESPALDO Perseo: Odoo no devolvió ventas. "
                          "Revisar el mapeo de la compañía VICOMER (odoo_descubrir.py resumen).")
        try:
            ec = PE.run_update()   # fetch Perseo + estado (NO edita Excel curados por defecto)
            if ec:
                cierre = ec.get("mes_cierre", cierre)
                paises["Ecuador"] = {
                    "moneda": "USD",
                    "mensual": ec["total_mensual_neto"],
                    "hist_amount": 0, "hist_through": 0,
                    "ytd_real": ec["ytd_total"], "ppto_ytd": ec["ppto_ytd_total"],
                    "ppto_anual": ec["ppto_anual_total"], "cumpl_ytd": ec["cumpl_ytd_total"],
                    "avance_anual": ec["avance_anual_total"],
                    "var_ytd": round(ec["ytd_total"] - ec["ppto_ytd_total"], 2),
                    "canales": ec["canales"], "mtd": ec.get("mtd"),
                    "n": ec.get("n_docs"), "fuente": "Perseo (respaldo)",
                }
        except SystemExit as e:
            log(f"[WARN] Ecuador (respaldo Perseo) no disponible: {e}")
        except Exception:
            log("[WARN] Ecuador (respaldo Perseo) falló:\n" + traceback.format_exc())

    return {"generado": datetime.datetime.now().isoformat(timespec="seconds"),
            "anio": year, "mes_cierre": cierre, "meses": MESES, "paises": paises,
            "avisos": avisos}

# ------------------------------------------------------------------ workbook
def _fmt(cur):
    return '#,##0' if cur == "COP" else '"$"#,##0'

def build_workbook(est):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    wb = openpyxl.Workbook()
    HFILL = PatternFill("solid", fgColor=NAVY); HFONT = Font(color="FFFFFF", bold=True, size=10)
    TITLE = Font(color=NAVY, bold=True, size=14); GREYF = Font(color=GREY, size=9)
    thin = Side(style="thin", color="D9D9D9"); BORDER = Border(thin, thin, thin, thin)
    PCT = '0.0%'
    orden = ["Ecuador", "Colombia", "Costa Rica"]
    paises = est["paises"]
    mes = est["meses"][est["mes_cierre"]-1]

    def cumpl_color(v):
        if v is None: return GREY
        return GREEN if v >= 1 else (AMBER if v >= 0.85 else RED)

    # ---------------- RESUMEN ----------------
    ws = wb.active; ws.title = "Resumen"; ws.sheet_view.showGridLines = False
    ws.merge_cells("A1:H1"); ws["A1"] = "ESTADO DEL PRESUPUESTO COMERCIAL — GRUPO VICOMER"; ws["A1"].font = TITLE
    ws.merge_cells("A2:H2")
    ws["A2"] = f"Actualizado: {est['generado']}   |   YTD a {mes} {est['anio']}   |   Cifras netas SIN IVA   |   Cada país en su moneda"
    ws["A2"].font = GREYF
    hdr = ["País", "Moneda", "Real YTD", "Presupuesto YTD", "Cumpl %", "Variación", "Presupuesto Año", "Avance Año"]
    hr = 4
    for j, h in enumerate(hdr, 1):
        c = ws.cell(row=hr, column=j, value=h); c.fill = HFILL; c.font = HFONT
        c.alignment = Alignment(horizontal="center"); c.border = BORDER
    r = hr + 1
    for pais in orden:
        if pais not in paises: continue
        d = paises[pais]; cur = d["moneda"] or ""; fmt = _fmt(cur)
        ws.cell(row=r, column=1, value=pais).font = Font(bold=True)
        ws.cell(row=r, column=2, value=cur)
        for col, key in [(3, "ytd_real"), (4, "ppto_ytd"), (6, "var_ytd"), (7, "ppto_anual")]:
            c = ws.cell(row=r, column=col, value=d.get(key)); c.number_format = fmt; c.border = BORDER
        c = ws.cell(row=r, column=5, value=d.get("cumpl_ytd"))
        if d.get("cumpl_ytd") is not None: c.number_format = PCT
        c.font = Font(bold=True, color=cumpl_color(d.get("cumpl_ytd"))); c.border = BORDER
        c = ws.cell(row=r, column=8, value=d.get("avance_anual"))
        if d.get("avance_anual") is not None: c.number_format = PCT
        c.border = BORDER
        r += 1
    # TOTAL GRUPO en USD (Colombia convertida con la tasa del Regional)
    g = est.get("global_usd")
    if g:
        USD = '"$"#,##0'
        ws.cell(row=r, column=1, value="TOTAL GRUPO (USD)").font = Font(bold=True, color=NAVY)
        ws.cell(row=r, column=2, value="USD").font = Font(bold=True)
        for col, key in [(3, "real"), (4, "ppto"), (7, "ppto_anual")]:
            c = ws.cell(row=r, column=col, value=g.get(key)); c.number_format = USD; c.font = Font(bold=True); c.fill = PatternFill("solid", fgColor="EAEFF7")
        c = ws.cell(row=r, column=5, value=g.get("cumpl")); c.number_format = PCT; c.font = Font(bold=True, color=cumpl_color(g.get("cumpl")))
        c = ws.cell(row=r, column=8, value=g.get("avance_anual")); c.number_format = PCT; c.font = Font(bold=True)
        r += 1
        ws.cell(row=r, column=1, value=f"Consolidado en USD con tasa COP/USD = {g['rate']:,.0f} (celda C13 de RESUMEN en el Regional; ajústala ahí).").font = GREYF
        r += 1
    # nota de fuentes (se arma con lo que realmente se usó, no con un texto fijo)
    r += 1
    fuentes = ", ".join(f"{p} = {paises[p].get('fuente', '?')}" for p in orden if p in paises)
    ws.cell(row=r, column=1, value=f"Fuentes: {fuentes}. Todo base imponible SIN IVA.").font = GREYF
    r += 1
    for a in est.get("avisos", []):
        c = ws.cell(row=r, column=1, value="⚠ " + a)
        c.font = Font(color=AMBER, size=9, italic=True)
        r += 1
    if "Colombia" in paises and paises["Colombia"].get("hist_amount"):
        d = paises["Colombia"]
        ws.cell(row=r, column=1, value=(f"Colombia: Ene-{est['meses'][d['hist_through']-1]} de la instancia Odoo anterior (vintral1) "
                                        f"= {d['hist_amount']:,.0f} COP; Abril+ del Odoo actual (vicomer). Ambos sin IVA.")).font = GREYF
        r += 1
    ws.column_dimensions["A"].width = 14
    for cl in "BCDEFGH": ws.column_dimensions[cl].width = 17

    # ---------------- ECUADOR (canal × mes) ----------------
    if "Ecuador" in paises and paises["Ecuador"].get("canales"):
        d = paises["Ecuador"]; fmt = _fmt("USD")
        we = wb.create_sheet(f"Ecuador ({d.get('fuente', 'Odoo')})"[:31]); we.sheet_view.showGridLines = False
        we.merge_cells("A1:R1"); we["A1"] = "ECUADOR — Real vs Presupuesto por canal (sin IVA)"; we["A1"].font = TITLE
        cols = ["Canal"] + est["meses"] + ["YTD real", "Ppto YTD", "Cumpl%", "Var", "Avance año"]
        hr = 3
        for j, h in enumerate(cols, 1):
            c = we.cell(row=hr, column=j, value=h); c.fill = HFILL; c.font = HFONT; c.alignment = Alignment(horizontal="center"); c.border = BORDER
        rr = hr + 1
        corder = ["RETAIL","DIGITAL","DIRECTO","ESPECIAL","MARKETPLACE","INTERCOMPANIA","SIN CANAL"]
        canales = d["canales"]
        for c_ in corder + [k for k in canales if k not in corder]:
            if c_ not in canales: continue
            cd = canales[c_]
            we.cell(row=rr, column=1, value=c_).font = Font(bold=True, size=10)
            for m in range(12):
                cell = we.cell(row=rr, column=2+m, value=cd["mensual"][m]); cell.number_format = fmt; cell.border = BORDER
            vals = [(14, "ytd_real", fmt), (15, "ppto_ytd", fmt), (16, "cumpl_ytd", PCT), (17, "var_ytd", fmt), (18, "avance_anual", PCT)]
            for col, key, f in vals:
                cell = we.cell(row=rr, column=col, value=cd.get(key))
                if cd.get(key) is not None: cell.number_format = f
                cell.border = BORDER
            rr += 1
        we.cell(row=rr, column=1, value="TOTAL ECUADOR").font = Font(bold=True)
        for m in range(12):
            we.cell(row=rr, column=2+m, value=d["mensual"][m]).number_format = fmt
        we.cell(row=rr, column=14, value=d["ytd_real"]).number_format = fmt
        we.cell(row=rr, column=15, value=d["ppto_ytd"]).number_format = fmt
        cc = we.cell(row=rr, column=16, value=d["cumpl_ytd"]); cc.number_format = PCT
        we.cell(row=rr, column=18, value=d["avance_anual"]).number_format = PCT
        we.column_dimensions["A"].width = 15
        for cl in "BCDEFGHIJKLM": we.column_dimensions[cl].width = 11
        for cl in ["N","O","P","Q","R"]: we.column_dimensions[cl].width = 12

    # ---------------- COLOMBIA / COSTA RICA (mes × país) ----------------
    for pais in ["Colombia", "Costa Rica"]:
        if pais not in paises: continue
        d = paises[pais]; cur = d["moneda"] or ""; fmt = _fmt(cur)
        wsx = wb.create_sheet(pais + " (Odoo)"); wsx.sheet_view.showGridLines = False
        wsx.merge_cells("A1:D1"); wsx["A1"] = f"{pais.upper()} — Real vs Presupuesto (sin IVA, {cur})"; wsx["A1"].font = TITLE
        hdr = ["Mes", "Real", "Presupuesto", "Cumpl% acumulado"]
        hr = 3
        for j, h in enumerate(hdr, 1):
            c = wsx.cell(row=hr, column=j, value=h); c.fill = HFILL; c.font = HFONT; c.alignment = Alignment(horizontal="center"); c.border = BORDER
        # presupuesto mensual del país; el real ya viene mes a mes (incluye histórico Ene-Mar)
        budg = OD.read_budgets().get(pais, {}).get("mensual", [0]*12)
        ht = d.get("hist_through", 0)
        acc_r = acc_p = 0.0; rr = hr + 1
        for m in range(12):
            real_m = d["mensual"][m]; ppto_m = budg[m]
            dentro = (m + 1) <= est["mes_cierre"]
            if dentro:
                acc_r += real_m; acc_p += ppto_m
            label = est["meses"][m] + ("  (Odoo anterior)" if ht and m < ht else "")
            wsx.cell(row=rr, column=1, value=label)
            c = wsx.cell(row=rr, column=2, value=round(real_m, 2)); c.number_format = fmt; c.border = BORDER
            c = wsx.cell(row=rr, column=3, value=round(ppto_m, 2)); c.number_format = fmt; c.border = BORDER
            if dentro:
                cc = wsx.cell(row=rr, column=4, value=round(acc_r/acc_p, 4) if acc_p else None)
                if acc_p: cc.number_format = PCT
            rr += 1
        wsx.cell(row=rr, column=1, value="YTD (a mes cerrado)").font = Font(bold=True)
        c = wsx.cell(row=rr, column=2, value=d["ytd_real"]); c.number_format = fmt; c.font = Font(bold=True)
        c = wsx.cell(row=rr, column=3, value=d["ppto_ytd"]); c.number_format = fmt; c.font = Font(bold=True)
        cc = wsx.cell(row=rr, column=4, value=d["cumpl_ytd"]);
        if d["cumpl_ytd"] is not None: cc.number_format = PCT
        cc.font = Font(bold=True, color=cumpl_color(d["cumpl_ytd"]))
        if d.get("hist_amount"):
            rr += 2
            wsx.cell(row=rr, column=1, value=(f"Ene-{est['meses'][d['hist_through']-1]} (Odoo anterior, vintral1.odoo.com) = {d['hist_amount']:,.0f} {cur}. "
                                              f"Abril+ del Odoo actual (vicomer.odoo.com). Todo sin IVA.")).font = GREYF
        wsx.column_dimensions["A"].width = 22
        for cl in "BCD": wsx.column_dimensions[cl].width = 20

    FILES_DIR.mkdir(parents=True, exist_ok=True)
    wb.save(CONSOLIDADO)
    return CONSOLIDADO

# ------------------------------------------------------------------ main
def run(year):
    est = collect(year)
    est = add_global_usd(est)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "estado_grupo.json").write_text(json.dumps(est, ensure_ascii=False, indent=2), encoding="utf-8")
    path = build_workbook(est)
    log("Resumen consolidado:")
    for pais, d in est["paises"].items():
        if pais.startswith("_"): continue
        cu = f"{d['cumpl_ytd']*100:.0f}%" if d.get("cumpl_ytd") is not None else "s/ppto"
        log(f"  {pais:12s} {d['ytd_real']:>16,.0f} {d['moneda']:3s} vs ppto {d['ppto_ytd']:>16,.0f} = {cu}")
    log(f"[OK] consolidado -> {path}")
    return est

if __name__ == "__main__":
    yr = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else datetime.date.today().year
    try:
        run(yr)
    except Exception:
        log("[ERROR]\n" + traceback.format_exc()); sys.exit(1)
