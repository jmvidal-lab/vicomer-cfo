#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
armar_datos.py  ·  corte + serie + textos -> datos/eeff_AAAA-MM.json
=====================================================================
Pega el extracto de Odoo con la serie mensual y arrastra del archivo anterior lo
que Odoo no sabe: las notas de "Puntos de atencion", el bloque de conciliacion y
los textos de meta. Asi la corrida semanal es tres comandos y no una edicion a mano,
que es donde se cuelan los errores.

LO QUE NO HACE: no inventa la TRM. Hay que pasarla, y si falta, se niega.

USO
    python3 armar_datos.py --corte corte.json --serie serie.json \
        --anterior datos/eeff_2026-10.json --trm 3216.01 \
        --trm-fecha "7 de octubre de 2026" --salida datos/eeff_2026-10.json \
        --ventas ventas.json --inventario inv.json
"""
import json, sys, argparse
from pathlib import Path

ARRASTRE_META = ("_nota_fuente", "_nota_trm", "_nota_rango", "_nota_ventas",
                 "_nota_historico", "trm_fuente")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corte", required=True)
    ap.add_argument("--serie", required=True)
    ap.add_argument("--ventas", required=False)
    ap.add_argument("--inventario", required=False)
    ap.add_argument("--anterior", required=True)
    ap.add_argument("--trm", required=True, type=float)
    ap.add_argument("--trm-fecha", required=True)
    ap.add_argument("--salida", required=True)
    a = ap.parse_args()

    d = json.loads(Path(a.corte).read_text(encoding="utf-8"))
    s = json.loads(Path(a.serie).read_text(encoding="utf-8"))
    prev = json.loads(Path(a.anterior).read_text(encoding="utf-8"))

    if not (1000 < a.trm < 10000):
        raise SystemExit("TRM fuera de rango plausible: %s" % a.trm)
    d["meta"]["trm"] = a.trm
    d["meta"]["trm_fecha"] = a.trm_fecha
    for k in ARRASTRE_META:
        if prev.get("meta", {}).get(k):
            d["meta"][k] = prev["meta"][k]

    # Las notas y la conciliacion son texto escrito por una persona: Odoo no las puede
    # regenerar. Se arrastran y HAY QUE REVISARLAS, porque citan cifras.
    for cod in ("EC", "CO"):
        for campo in ("notas", "veredicto"):
            if cod in d and prev.get(cod, {}).get(campo) is not None:
                d[cod][campo] = prev[cod][campo]
        d.get(cod, {}).pop("_totales", None)
    if prev.get("conc"):
        d["conc"] = prev["conc"]

    if a.ventas:
        nuevo = json.loads(Path(a.ventas).read_text(encoding="utf-8"))
        # EL HISTORICO NO SE REGENERA. Es un snapshot congelado de los sistemas
        # anteriores (Perseo en Ecuador, la instancia vintral1 en Colombia) y Odoo no
        # lo conoce. Si no se arrastra aqui, cada corrida semanal lo borraria y el
        # tablero perderia en silencio los meses previos a la migracion.
        for cod, bloque in (prev.get("ventas") or {}).items():
            if cod == "meta" or not isinstance(bloque, dict):
                continue
            h = bloque.get("historico")
            if h and cod in nuevo:
                pm = nuevo[cod].get("primer_mes") or 99
                choque = [m for m in (h.get("meses") or {}) if int(m) >= pm]
                if choque:
                    raise SystemExit(
                        "SOLAPAMIENTO en %s: el histórico cubre %s y Odoo ya tiene facturas "
                        "desde el mes %s. Sumarlos contaría dos veces la misma venta."
                        % (cod, choque, pm))
                nuevo[cod]["historico"] = h
                nuevo[cod]["_nota_hueco"] = bloque.get("_nota_hueco") or nuevo[cod].get("_nota_hueco")
        d["ventas"] = nuevo
    elif prev.get("ventas"):
        # Sin extracto nuevo se conserva el anterior, pero marcado: un tablero que
        # presenta ventas viejas como si fueran de hoy es peor que uno sin ventas.
        d["ventas"] = prev["ventas"]
        print("AVISO: no se pasó --ventas; se arrastró el bloque anterior (corte %s)."
              % (prev["ventas"].get("meta") or {}).get("corte_iso"))

    # --- Inventario -------------------------------------------------------
    # El extracto trae TODAS las fichas de producto. Aqui se podan las que no tienen
    # ni existencias ni movimiento (no aportan nada y pesan), se declaran los meses
    # con demanda y se concilia contra el inventario en almacen del balance. Ese
    # numero sale del propio corte, no se escribe a mano.
    if a.inventario:
        raw = json.loads(Path(a.inventario).read_text(encoding="utf-8"))
        inv = {"meta": raw.get("meta") or {}}
        for cod in [k for k in raw if k != "meta"]:
            b = dict(raw[cod])
            items = [i for i in (b.get("items") or [])
                     if (i.get("stock_u") or 0) > 0 or (i.get("u_tot") or 0) > 0]
            b["items"] = items
            b["meses_con_demanda"] = sorted({int(m) for i in items for m in (i.get("u") or {})})
            b["n_sku_origen"] = len(raw[cod].get("items") or [])
            b["podado"] = len(items) != b["n_sku_origen"]
            # El inventario EN ALMACEN del balance lo calcula eeff_odoo.py en extras()
            # y queda en ind.inv_almacen. Es lo unico comparable contra el maestro:
            # la mercaderia en transito todavia no esta en bodega.
            bal = ((d.get(cod) or {}).get("ind") or {}).get("inv_almacen")
            if bal is None:
                bal = (((prev.get("inventario") or {}).get(cod) or {})
                       .get("conciliacion") or {}).get("balance_almacen")
            if bal is None:
                b["conciliacion"] = {"maestro": b.get("stock_total"), "balance_almacen": None,
                                     "dif": None, "pct": None}
            else:
                dif = round((b.get("stock_total") or 0) - bal, 2)
                b["conciliacion"] = {"maestro": b.get("stock_total"), "balance_almacen": bal,
                                     "dif": dif, "pct": round(dif / bal, 4) if bal else None}
            inv[cod] = b
        d["inventario"] = inv
    elif prev.get("inventario"):
        d["inventario"] = prev["inventario"]
        print("AVISO: no se pasó --inventario; se arrastró el bloque anterior (corte %s)."
              % (prev["inventario"].get("meta") or {}).get("corte_iso"))

    d["serie"] = {"meses": s["meta"]["meses"],
                  "EC": {"primer_mes": s["EC"]["primer_mes"], "buckets": s["EC"]["buckets"]},
                  "CO": {"primer_mes": s["CO"]["primer_mes"], "buckets": s["CO"]["buckets"]},
                  "_nota": ("Movimiento mensual del estado de resultados y foto del balance al "
                            "cierre de cada mes. El bloque de la migración no se puede partir y "
                            "lo declara en 'bloque' y 'cubre'.")}

    Path(a.salida).write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print("escrito %s (%.0f KB)" % (a.salida, Path(a.salida).stat().st_size/1024))
    print("REVISÁ EL VEREDICTO Y LAS ALERTAS: citan cifras y se arrastraron tal cual.")
    for cod, bl in (d.get("ventas") or {}).items():
        if isinstance(bl, dict) and (bl.get("historico") or {}).get("meses"):
            print("  %s: histórico arrastrado, %d mes(es) previos a la migración"
                  % (bl.get("pais", cod), len((bl["historico"] or {}).get("meses") or {})))
    for cod in ("EC", "CO"):
        if cod in d:
            print("  %s: %d notas arrastradas" % (d[cod]["pais"], len(d[cod].get("notas") or [])))
    for cod, bl in (d.get("inventario") or {}).items():
        if cod == "meta" or not isinstance(bl, dict):
            continue
        c = bl.get("conciliacion") or {}
        print("  %s: %d referencias con stock o movimiento · conciliación %s"
              % (bl.get("pais", cod), len(bl.get("items") or []),
                 ("%+.1f%% contra el balance" % (c["pct"] * 100)) if c.get("pct") is not None
                 else "sin inventario en el balance"))


if __name__ == "__main__":
    main()
