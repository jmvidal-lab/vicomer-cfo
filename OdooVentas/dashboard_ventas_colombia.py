#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dashboard Ventas Colombia (VINTRAL S.A.S.) — cálculo ejecutivo.

Uso:
    python3 dashboard_ventas_colombia.py
    python3 dashboard_ventas_colombia.py --json ruta/al/odoo_facturas_2026.json --html salida.html

Lee el JSON de facturas de Odoo, filtra Colombia (VINTRAL, COP) y calcula:
  - Ventas de la SEMANA (últimos 7 días respecto a hoy; si no hay datos
    nuevos, cae automáticamente a la última semana con datos = "al corte").
  - Ventas del MES en curso (MTD).
  - Top 5 clientes del mes.
  - Advertencia si la extracción tiene más de 8 días de antigüedad.
Opcionalmente genera el HTML del correo con --html.
"""

import argparse
import datetime as dt
import glob
import json
import os
import sys
from collections import defaultdict

FX_COP_USD = 3700  # tipo de cambio COP -> USD


# ---------------------------------------------------------------- utilidades
def fmt_cop(n):
    """5112277 -> '5.112.277' (separador de miles con punto, sin decimales)."""
    return f"{round(n):,}".replace(",", ".")


def fmt_usd(n):
    """1382 -> '$1.382'."""
    return "$" + f"{round(n):,}".replace(",", ".")


def to_usd(cop):
    return cop / FX_COP_USD


def fecha(x):
    return dt.date.fromisoformat(x["fecha"])


def localizar_json(ruta_cli):
    if ruta_cli:
        return ruta_cli
    # 1) junto a este script
    aqui = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "odoo_facturas_2026.json")
    if os.path.exists(aqui):
        return aqui
    # 2) sandbox / rutas típicas
    for patron in (
        "/sessions/*/mnt/*/OdooVentas/odoo_facturas_2026.json",
        os.path.expanduser("~/Claude/Projects/CFO VICOMER/OdooVentas/odoo_facturas_2026.json"),
    ):
        hits = sorted(glob.glob(patron), key=os.path.getmtime, reverse=True)
        if hits:
            return hits[0]
    return None


# ------------------------------------------------------------------- cálculo
def calcular(ruta_json, hoy=None):
    data = json.load(open(ruta_json, encoding="utf-8"))
    facturas = [f for f in data["facturas"] if "VINTRAL" in f["empresa"].upper()]
    if not facturas:
        raise SystemExit("No se encontraron facturas VINTRAL en el JSON.")

    fecha_corte = dt.datetime.fromisoformat(data["generado"]).date()
    hoy = hoy or dt.date.today()
    antiguedad = (hoy - fecha_corte).days

    # --- Semana: últimos 7 días respecto a hoy.
    # Si la extracción está desactualizada y ese rango no tiene facturas,
    # se ancla a los últimos 7 días con datos (hasta la fecha de corte).
    ini = hoy - dt.timedelta(days=7)
    semana = [f for f in facturas if ini < fecha(f) <= hoy]
    ancla = "hoy"
    if not semana:
        ini = fecha_corte - dt.timedelta(days=7)
        semana = [f for f in facturas if ini < fecha(f) <= fecha_corte]
        ancla = "corte"
    fin = hoy if ancla == "hoy" else fecha_corte

    # --- MTD: mes calendario en curso.
    mtd = [f for f in facturas if fecha(f).year == hoy.year and fecha(f).month == hoy.month]

    # --- Top 5 clientes del mes.
    por_cliente = defaultdict(float)
    for f in mtd:
        por_cliente[f["cliente"]] += f["subtotal"]
    top5 = sorted(por_cliente.items(), key=lambda kv: kv[1], reverse=True)[:5]

    return {
        "fecha_corte": fecha_corte,
        "antiguedad": antiguedad,
        "advertencia": antiguedad > 8,
        "semana_ini": ini,
        "semana_fin": fin,
        "semana_ancla": ancla,
        "semana_cop": sum(f["subtotal"] for f in semana),
        "semana_n": len(semana),
        "mtd_cop": sum(f["subtotal"] for f in mtd),
        "mtd_n": len(mtd),
        "top5": top5,
    }


# --------------------------------------------------------------------- salida
MESES = ["", "ene", "feb", "mar", "abr", "may", "jun",
         "jul", "ago", "sep", "oct", "nov", "dic"]


def rango_txt(d1, d2):
    if d1.month == d2.month:
        return f"{d1.day}–{d2.day} {MESES[d2.month]}"
    return f"{d1.day} {MESES[d1.month]}–{d2.day} {MESES[d2.month]}"


def imprimir(r):
    corte = f"{r['fecha_corte'].day} {MESES[r['fecha_corte'].month]} {r['fecha_corte'].year}"
    print("=" * 52)
    print("  DASHBOARD VENTAS COLOMBIA (VINTRAL)")
    print(f"  Datos al {corte}")
    print("=" * 52)
    if r["advertencia"]:
        print(f"  /!\\ Datos con {r['antiguedad']} dias de antiguedad.")
        print("      Refrescar: python3 odoo_ventas.py 2026 (en el Mac)")
        print("-" * 52)
    etq = "al corte" if r["semana_ancla"] == "corte" else "ult. 7 dias"
    print(f"  Semana ({rango_txt(r['semana_ini'], r['semana_fin'])}, {etq}):")
    print(f"     COP {fmt_cop(r['semana_cop'])}  |  ~{fmt_usd(to_usd(r['semana_cop']))}  |  {r['semana_n']} facturas")
    print(f"  Acumulado mes (MTD):")
    print(f"     COP {fmt_cop(r['mtd_cop'])}  |  ~{fmt_usd(to_usd(r['mtd_cop']))}  |  {r['mtd_n']} facturas")
    print("-" * 52)
    print("  Top clientes del mes:")
    if not r["top5"]:
        print("     (sin facturas en el mes en curso)")
    for cli, cop in r["top5"]:
        print(f"     {cli[:34]:34} COP {fmt_cop(cop):>12}  ~{fmt_usd(to_usd(cop))}")
    print("=" * 52)


def generar_html(r):
    corte = f"{r['fecha_corte'].day} {MESES[r['fecha_corte'].month]} {r['fecha_corte'].year}"
    aviso = ""
    if r["advertencia"]:
        aviso = (
            '<div style="background:#fef3c7;border-left:4px solid #f59e0b;padding:10px 14px;'
            'border-radius:4px;margin-bottom:18px;font-size:13px;color:#92400e;">'
            f'&#9888; <strong>Datos al {corte} ({r["antiguedad"]} d&iacute;as de antig&uuml;edad).</strong> '
            'Conviene refrescar la extracci&oacute;n de Odoo '
            '(<code>python3 odoo_ventas.py 2026</code> en el Mac).</div>'
        )
    filas = "".join(
        '<tr><td style="padding:8px 10px;border-bottom:1px solid #f0f0f0;">' + cli +
        '</td><td align="right" style="padding:8px 10px;border-bottom:1px solid #f0f0f0;">' +
        fmt_cop(cop) + '</td><td align="right" style="padding:8px 10px;border-bottom:1px solid #f0f0f0;">' +
        fmt_usd(to_usd(cop)) + '</td></tr>'
        for cli, cop in r["top5"]
    )
    etq = "al corte" if r["semana_ancla"] == "corte" else ""
    sem_lbl = rango_txt(r["semana_ini"], r["semana_fin"]) + (f", {etq}" if etq else "")
    return f"""<div style="font-family:Arial,Helvetica,sans-serif;color:#1a1a1a;max-width:600px;margin:0 auto;">
  <h2 style="margin:0 0 2px;font-size:20px;color:#0f2a4a;">Dashboard Ventas Colombia (VINTRAL)</h2>
  <p style="margin:0 0 16px;font-size:13px;color:#6b7280;">Datos al {corte}</p>
  {aviso}
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:20px;"><tr>
    <td width="50%" valign="top" style="padding-right:8px;">
      <div style="border:1px solid #e5e7eb;border-radius:8px;padding:16px;">
        <div style="font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:.5px;">Semana ({sem_lbl})</div>
        <div style="font-size:24px;font-weight:700;color:#0f2a4a;margin:6px 0 2px;">COP {fmt_cop(r['semana_cop'])}</div>
        <div style="font-size:13px;color:#374151;">&asymp; {fmt_usd(to_usd(r['semana_cop']))} USD &middot; {r['semana_n']} facturas</div>
      </div>
    </td>
    <td width="50%" valign="top" style="padding-left:8px;">
      <div style="border:1px solid #e5e7eb;border-radius:8px;padding:16px;">
        <div style="font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:.5px;">Acumulado mes (MTD)</div>
        <div style="font-size:24px;font-weight:700;color:#0f2a4a;margin:6px 0 2px;">COP {fmt_cop(r['mtd_cop'])}</div>
        <div style="font-size:13px;color:#374151;">&asymp; {fmt_usd(to_usd(r['mtd_cop']))} USD &middot; {r['mtd_n']} facturas</div>
      </div>
    </td>
  </tr></table>
  <div style="font-size:13px;font-weight:700;color:#0f2a4a;margin-bottom:8px;">Top clientes del mes</div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;font-size:13px;">
    <tr style="background:#f3f4f6;color:#374151;">
      <th align="left" style="padding:8px 10px;border-bottom:1px solid #e5e7eb;">Cliente</th>
      <th align="right" style="padding:8px 10px;border-bottom:1px solid #e5e7eb;">COP</th>
      <th align="right" style="padding:8px 10px;border-bottom:1px solid #e5e7eb;">&asymp; USD</th>
    </tr>
    {filas}
  </table>
  <p style="font-size:13px;color:#1a1a1a;margin:20px 0 0;">Juan Marcelo Vidal</p>
</div>"""


# ----------------------------------------------------------------------- main
def main():
    global FX_COP_USD
    ap = argparse.ArgumentParser(description="Dashboard Ventas Colombia (VINTRAL)")
    ap.add_argument("--json", help="Ruta al odoo_facturas_2026.json")
    ap.add_argument("--html", help="Ruta de salida para el HTML del correo")
    ap.add_argument("--fx", type=float, default=FX_COP_USD, help="Tipo de cambio COP->USD")
    args = ap.parse_args()

    FX_COP_USD = args.fx

    ruta = localizar_json(args.json)
    if not ruta:
        sys.exit("No se encontro odoo_facturas_2026.json. Pasa la ruta con --json.")

    r = calcular(ruta)
    imprimir(r)

    if args.html:
        with open(args.html, "w", encoding="utf-8") as fh:
            fh.write(generar_html(r))
        print(f"\nHTML escrito en: {args.html}")


if __name__ == "__main__":
    main()
