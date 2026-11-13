#!/usr/bin/env python3
"""
vix_compras.py — Comprobantes RECIBIDOS por VIX según el SRI (reporte "Recibidos" .txt) → resumen.

    python3 VIX/vix_compras.py [carpeta]      # por defecto VIX/sri_entrada/

Deduplica por clave de acceso, agrupa por emisor y mes, y marca:
  · partes relacionadas (socios / empresas del grupo)  → retenciones y anexo APS
  · personas naturales que facturan servicios          → retención IR e IVA obligatoria
  · gastos de consumo personal (restaurantes, clubes)  → riesgo de no deducibilidad
NO escribe en Odoo.
"""
import csv, json, sys
from collections import defaultdict
from pathlib import Path

AQUI = Path(__file__).resolve().parent
REG = json.loads((AQUI / "vix_reglas.json").read_text(encoding="utf-8"))


def leer(carpeta: Path):
    vistos, out = set(), []
    for f in sorted(carpeta.glob("*.txt")):
        filas = list(csv.DictReader(f.read_text(encoding="utf-8-sig", errors="replace").splitlines(), delimiter="\t"))
        for r in filas:
            if not r.get("CLAVE_ACCESO") or r["CLAVE_ACCESO"] in vistos:
                continue
            vistos.add(r["CLAVE_ACCESO"])
            d, mth, y = r["FECHA_EMISION"].split("/")
            out.append({"fecha": f"{y}-{mth}-{d}", "ruc": r["RUC_EMISOR"], "emisor": r["RAZON_SOCIAL_EMISOR"],
                        "tipo": r["TIPO_COMPROBANTE"], "serie": r["SERIE_COMPROBANTE"],
                        "base": float(r["VALOR_SIN_IMPUESTOS"] or 0), "iva": float(r["IVA"] or 0),
                        "total": float(r["IMPORTE_TOTAL"] or 0), "clave": r["CLAVE_ACCESO"]})
    return sorted(out, key=lambda x: x["fecha"])


def clasificar(c):
    cl = REG.get("clasificacion_compras", {})
    if c["ruc"] in cl.get("partes_relacionadas_ruc", {}):
        return "relacionada: " + cl["partes_relacionadas_ruc"][c["ruc"]]
    for k, v in cl.get("por_ruc", {}).items():
        if c["ruc"] == k:
            return v
    for palabra, v in cl.get("por_palabra", {}).items():
        if palabra.lower() in c["emisor"].lower():
            return v
    return "sin clasificar"


def main():
    carpeta = Path(sys.argv[1]) if len(sys.argv) > 1 else AQUI / "sri_entrada"
    comp = leer(carpeta)
    tot = defaultdict(lambda: [0, 0.0, 0.0, 0.0])
    print("| Fecha | Emisor | Serie | Base | IVA | Total | Clasificación |\n|---|---|---|---|---|---|---|")
    for c in comp:
        k = clasificar(c)
        c["clase"] = k
        t = tot[k]; t[0] += 1; t[1] += c["base"]; t[2] += c["iva"]; t[3] += c["total"]
        print(f"| {c['fecha']} | {c['emisor'][:38]} | {c['serie']} | {c['base']:,.2f} | {c['iva']:,.2f} | {c['total']:,.2f} | {k} |")
    print("\n| Clasificación | # | Base | IVA | Total |\n|---|---|---|---|---|")
    for k, (n, b, i, t) in sorted(tot.items()):
        print(f"| {k} | {n} | {b:,.2f} | {i:,.2f} | {t:,.2f} |")
    print(f"| **Total** | {len(comp)} | {sum(c['base'] for c in comp):,.2f} | {sum(c['iva'] for c in comp):,.2f} | {sum(c['total'] for c in comp):,.2f} |")
    (AQUI / "salida").mkdir(exist_ok=True)
    (AQUI / "salida" / "compras_sri.json").write_text(json.dumps(comp, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
