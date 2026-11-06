#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generar_serie.py  ·  serie mensual para el filtro de rango
===========================================================
Emite, por pais y por mes: el MOVIMIENTO del estado de resultados y la FOTO del
balance al cierre de ese mes. Con eso la pagina arma cualquier rango sin volver
a Odoo.

LA REGLA CONTABLE QUE EL FILTRO NO PUEDE ROMPER
  El estado de resultados es un FLUJO: se suma sobre el rango.
  El balance es un SALDO: es la foto del ULTIMO mes del rango, nunca una suma.
  Un selector que mueva los dos igual produce un balance inventado.

EL LIMITE DE LOS DATOS, DECLARADO
  La migracion entro como un solo asiento. En Ecuador, julio trae 1.114.344,15 en
  10 lineas: es todo enero-julio en un bulto. En Colombia, marzo trae enero-marzo.
  Esos bloques NO SE PUEDEN PARTIR. El generador los marca con el periodo real que
  cubren y la pagina se niega a trocearlos: antes de estimar, muestra el hueco.

USO
    python3 generar_serie.py 2026-10-07 > serie_2026.json
"""
import os, sys, json, calendar, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("VICOMER_PROJ", os.path.dirname(os.path.abspath(__file__)))
import finanzas_dashboard as F
import generar_eeff as G

MESES = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]


def fin_de_mes(y, m, tope):
    d = datetime.date(y, m, calendar.monthrange(y, m)[1])
    return min(d, tope)


def pyg_rango(od, pl, cid, desde, hasta):
    sal = F.saldos(od, cid, desde, hasta)
    r = {"ing": 0.0, "cogs": 0.0, "gv": 0.0, "ga": 0.0, "gf": 0.0, "g4": 0.0, "n": 0}
    for aid, v in sal.items():
        a = pl.get(aid) or {}
        t, c = a.get("account_type"), a.get("code") or ""
        if t in F.INGRESO:
            r["ing"] += -v; r["n"] += 1
        elif t in F.GASTO:
            if G.pref(c, "501"):   r["cogs"] += v
            elif G.pref(c, "502.01"): r["gv"] += v
            elif G.pref(c, "502.02"): r["ga"] += v
            elif G.pref(c, "502.03"): r["gf"] += v
            elif G.pref(c, "502.04"): r["g4"] += v
            else: r["ga"] += v
    return {k: round(v, 2) for k, v in r.items()}


def foto_balance(od, pl, cid, pais, hasta):
    """Saldos acumulados a una fecha, agrupados como los presenta el tablero."""
    reglas = F.load_reglas()
    acum = F.saldos(od, cid, None, hasta)
    clases = {}
    ACT = ("efectivo", "cuentas_por_cobrar", "inventarios", "otros_activos_corrientes",
           "activo_no_corriente")
    for aid, v in acum.items():
        a = pl.get(aid) or {}
        cl = F.clasifica_balance(a, reglas)
        if not cl:
            continue
        clases.setdefault(cl, []).append({"code": (a.get("code") or "").replace(" ", ""),
                                          "name": a.get("name") or "",
                                          "v": v * (1.0 if cl in ACT else -1.0)})
    tot = lambda cl: round(sum(x["v"] for x in clases.get(cl, [])), 2)
    def top(cl, n=4):
        xs = sorted(clases.get(cl, []), key=lambda x: -abs(x["v"]))[:n]
        return " · ".join("%s %s" % (x["name"].strip().title()[:30], "{:,.0f}".format(abs(x["v"])))
                          for x in xs if abs(x["v"]) > 0)
    def solo(cl, codes):
        return round(sum(x["v"] for x in clases.get(cl, []) if x["code"] in codes), 2)
    return {
        "efectivo": tot("efectivo"), "efectivo_sub": top("efectivo", 3),
        "cxc": tot("cuentas_por_cobrar"),
        "inventarios": tot("inventarios"), "inventarios_sub": top("inventarios", 3),
        "otros_ac": tot("otros_activos_corrientes"), "otros_ac_sub": top("otros_activos_corrientes", 4),
        "anc": tot("activo_no_corriente"), "anc_sub": top("activo_no_corriente", 3),
        "cxp": tot("cuentas_por_pagar"), "cxp_sub": top("cuentas_por_pagar", 4),
        "df": tot("deuda_financiera"), "df_sub": top("deuda_financiera", 3),
        "imp": tot("impuestos_por_pagar"),
        "otros_pc": tot("otros_pasivos_corrientes"), "otros_pc_sub": top("otros_pasivos_corrientes", 4),
        "pnc": round(tot("pasivo_no_corriente") + tot("deuda_financiera_lp"), 2),
        "pnc_sub": top("pasivo_no_corriente", 2),
        "patrimonio_sr": tot("patrimonio"), "patrimonio_sub": top("patrimonio", 3),
        "proveedor_comercial": abs(solo("cuentas_por_pagar", G.PROV_COMERCIAL[pais])),
        "intercia": abs(solo("cuentas_por_pagar", G.INTERCIA[pais])
                        or solo("otros_activos_corrientes", G.INTERCIA[pais])),
    }


def main():
    hasta = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    tope = datetime.date.fromisoformat(hasta)
    y = tope.year
    od = F.Odoo(F.load_config()); od.authenticate()
    comps = F.companias(od, (od.cfg.get("_raw") or {}).get("company_map") or {})
    out = {"meta": {"anio": y, "corte_iso": hasta, "meses": MESES[:tope.month]}}
    for pais, cfg in G.PAISES.items():
        cid = cfg["cid"]
        pl = F.plan_de_cuentas(od, cid)
        buckets, primero = [], None
        for m in range(1, tope.month + 1):
            d0 = datetime.date(y, m, 1).isoformat()
            d1 = fin_de_mes(y, m, tope)
            r = pyg_rango(od, pl, cid, d0, d1.isoformat())
            vivo = any(abs(r[k]) > 0.005 for k in ("ing", "cogs", "gv", "ga", "gf", "g4"))
            if vivo and primero is None:
                primero = m
            buckets.append({"m": m, "hasta": d1.isoformat(), "vivo": vivo, "pyg": r,
                            "bg": foto_balance(od, pl, cid, pais, d1.isoformat())})
        # El primer mes con movimiento arrastra todo lo anterior: es el asiento de la
        # migracion. Se declara el periodo REAL que cubre; nadie puede partirlo.
        for b in buckets:
            if primero is not None and b["m"] == primero and primero > 1:
                b["cubre"] = [1, primero]
                b["bloque"] = True
                b["etiqueta"] = "%s–%s" % (MESES[0], MESES[primero - 1])
                b["motivo_bloque"] = ("La migración entró como un solo asiento: %s líneas de ingreso "
                                      "para %d meses. No se puede separar mes a mes."
                                      % (b["pyg"]["n"], primero))
            else:
                b["cubre"] = [b["m"], b["m"]]
                b["bloque"] = False
                b["etiqueta"] = MESES[b["m"] - 1]
        out["EC" if pais == "Ecuador" else "CO"] = {
            "pais": pais, "empresa": (comps.get(cid) or {}).get("name"),
            "moneda": cfg["mon"], "primer_mes": primero, "buckets": buckets}
    sys.stdout.write(json.dumps(out, ensure_ascii=False, indent=2))
    sys.stderr.write("\n  llamadas XML-RPC: %d\n" % od.calls)


if __name__ == "__main__":
    main()
