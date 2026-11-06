#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generar_eeff.py  ·  Odoo -> contrato de datos de EstadosFinancieros/
====================================================================
Traduce el mayor de Odoo al JSON que consume build.py. Es el "traductor" que
el HANDOFF dejaba pendiente, y ahora se puede escribir porque el diagnostico de
asientos contesto la pregunta que lo bloqueaba:

  El diario "Apertura ER" de Ecuador (1.114.344,15 = 74,2% del ingreso del ano)
  NO es ruido: es el resultado de enero-julio trasladado desde Perseo en la
  migracion. El error anterior no era incluirlo, era SUMARLO ADEMAS a la serie
  historica cosida. Incluido una sola vez, Odoo reproduce el julio oficial al
  centavo: resultado 98.861,50 y patrimonio 549.628,41 identicos.
  Lo mismo en Colombia con MISCE/2026/03/0011 (enero-marzo).

PREFIJOS DE GASTO (iguales en las dos companias, verificado en el plan de cuentas)
  502.01 gastos de ventas · 502.02 administrativos · 502.03 financieros
  502.04 Ecuador: no deducibles · Colombia: impuesto a la renta

USO
    python3 generar_eeff.py 2026-10-07 > eeff_2026-10.json
"""
import os, sys, json, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("VICOMER_PROJ", os.path.dirname(os.path.abspath(__file__)))
import finanzas_dashboard as F

PAISES = {"Ecuador": {"cid": 2, "mon": "USD"}, "Colombia": {"cid": 1, "mon": "COP"}}
# Cuentas de proveedor COMERCIAL. La intercompania y los salarios no son credito de
# proveedor: meterlos en el DPO lo infla y hace creer que hay financiamiento que no hay.
PROV_COMERCIAL = {
    "Ecuador":  ["201.03.01.04"],
    "Colombia": ["201.03.01.04", "201.03.02.01", "201.03.02.02"],
}
INTERCIA = {"Ecuador": ["101.02.06.02.03"], "Colombia": ["201.03.02.03"]}


def pref(code, p):
    return (code or "").replace(" ", "").startswith(p)


def bloque_pais(od, pais, cid, moneda, desde, hasta, dias):
    pl = F.plan_de_cuentas(od, cid)
    sal = F.saldos(od, cid, desde, hasta)          # movimiento del periodo
    acum = F.saldos(od, cid, None, hasta)          # saldo acumulado (balance)

    ing = gv = ga = gf = g4 = cogs = 0.0
    for aid, v in sal.items():
        a = pl.get(aid) or {}
        t, c = a.get("account_type"), a.get("code") or ""
        if t in F.INGRESO:
            ing += -v
        elif t in F.GASTO:
            if pref(c, "501"):
                cogs += v
            elif pref(c, "502.01"):
                gv += v
            elif pref(c, "502.02"):
                ga += v
            elif pref(c, "502.03"):
                gf += v
            elif pref(c, "502.04"):
                g4 += v
            else:
                ga += v
    ub = ing - cogs
    uo = ub - gv - ga
    uai = uo - gf
    neto = uai - g4

    etq4 = "(−) Impuesto a la renta" if pais == "Colombia" else "(−) Gastos no deducibles"
    pyg = [
        {"k": "Ventas netas", "v": round(ing, 2), "t": "s"},
        {"k": "(−) Costo de ventas", "v": round(-cogs, 2), "t": "r"},
        {"k": "Utilidad bruta", "v": round(ub, 2), "t": "S", "pct": round(ub / ing, 4)},
        {"k": "(−) Gastos de ventas", "v": round(-gv, 2), "t": "r"},
        {"k": "(−) Gastos administrativos", "v": round(-ga, 2), "t": "r"},
        {"k": "Utilidad operativa (EBIT)", "v": round(uo, 2), "t": "S", "pct": round(uo / ing, 4)},
        {"k": "(−) Gastos financieros", "v": round(-gf, 2), "t": "r"},
        {"k": "Utilidad antes de impuestos", "v": round(uai, 2), "t": "S", "pct": round(uai / ing, 4)},
        {"k": etq4, "v": round(-g4, 2), "t": "r"},
        {"k": "Resultado del ejercicio", "v": round(neto, 2), "t": "F", "pct": round(neto / ing, 4)},
    ]

    # --- Balance por clase, con el detalle que explica cada renglon
    reglas = F.load_reglas()
    clases = {}
    for aid, v in acum.items():
        a = pl.get(aid) or {}
        cl = F.clasifica_balance(a, reglas)
        if not cl:
            continue
        signo = -1.0 if cl not in ("efectivo", "cuentas_por_cobrar", "inventarios",
                                   "otros_activos_corrientes", "activo_no_corriente") else 1.0
        clases.setdefault(cl, []).append({"code": a.get("code") or "", "name": a.get("name") or "",
                                          "v": v * signo})
    def tot(cl):
        return sum(x["v"] for x in clases.get(cl, []))
    def top(cl, n=4):
        xs = sorted(clases.get(cl, []), key=lambda x: -abs(x["v"]))[:n]
        return " · ".join("%s %s" % (x["name"].strip().title()[:30], "{:,.0f}".format(abs(x["v"])))
                          for x in xs if abs(x["v"]) > 0)
    def solo(cl, codes):
        return sum(x["v"] for x in clases.get(cl, []) if x["code"].replace(" ", "") in codes)

    ac = sum(tot(c) for c in ("efectivo", "cuentas_por_cobrar", "inventarios", "otros_activos_corrientes"))
    anc = tot("activo_no_corriente")
    pc = sum(tot(c) for c in ("cuentas_por_pagar", "deuda_financiera", "impuestos_por_pagar",
                              "otros_pasivos_corrientes"))
    pnc = tot("pasivo_no_corriente") + tot("deuda_financiera_lp")
    pat_sr = tot("patrimonio")

    bg = {
        "activo": [
            {"k": "Efectivo y bancos", "v": round(tot("efectivo"), 2), "sub": top("efectivo", 3)},
            {"k": "Cuentas por cobrar clientes", "v": round(tot("cuentas_por_cobrar"), 2)},
            {"k": "Inventarios y mercadería en tránsito", "v": round(tot("inventarios"), 2),
             "sub": top("inventarios", 3)},
            {"k": "Otros activos corrientes", "v": round(tot("otros_activos_corrientes"), 2),
             "sub": top("otros_activos_corrientes", 4)},
        ],
        "activo_nc": ([{"k": "Propiedad, planta y equipo (neto)", "v": round(anc, 2),
                        "sub": top("activo_no_corriente", 3)}] if abs(anc) > 1 else []),
        "pasivo": [
            {"k": "Proveedores y cuentas por pagar", "v": round(tot("cuentas_por_pagar"), 2),
             "sub": top("cuentas_por_pagar", 4)},
            {"k": "Deuda financiera corto plazo", "v": round(tot("deuda_financiera"), 2),
             "sub": top("deuda_financiera", 3)},
            {"k": "Impuestos por pagar", "v": round(tot("impuestos_por_pagar"), 2)},
            {"k": "Otros pasivos corrientes", "v": round(tot("otros_pasivos_corrientes"), 2),
             "sub": top("otros_pasivos_corrientes", 4)},
        ],
        "pasivo_nc": ([{"k": "Pasivo no corriente", "v": round(pnc, 2),
                        "sub": top("pasivo_no_corriente", 2)}] if abs(pnc) > 1 else []),
        "patrimonio": [
            {"k": "Capital y resultados acumulados", "v": round(pat_sr, 2), "sub": top("patrimonio", 3)},
            {"k": "Resultado del ejercicio", "v": round(neto, 2), "sub": "Ene–Oct 2026"},
        ],
    }

    at, pt, pat = ac + anc, pc + pnc, pat_sr + neto
    prov = abs(solo("cuentas_por_pagar", PROV_COMERCIAL[pais]))
    cxc = tot("cuentas_por_cobrar")
    inv = tot("inventarios")
    dso = cxc / (ing / dias) if ing else None
    dio = inv / (cogs / dias) if cogs else None
    dpo = prov / (cogs / dias) if cogs else None
    df = tot("deuda_financiera"); dflp = tot("deuda_financiera_lp") + tot("pasivo_no_corriente")

    ind = {
        "mb": round(ub / ing, 4), "mo": round(uo / ing, 4), "mn": round(neto / ing, 4),
        "gastos_pct": round((gv + ga) / ing, 4),
        "liquidez": round(ac / pc, 2) if pc else None,
        "acida": round((ac - inv) / pc, 2) if pc else None,
        "ctrabajo": round(ac - pc, 2),
        "endeud": round(pt / at, 3) if at else None,
        "apal": round(pt / pat, 2) if pat else None,
        "df": round(df + dflp, 2), "df_act": round((df + dflp) / at, 3) if at else None,
        "roa": round(neto / at, 4) if at else None,
        "roe": round(neto / pat, 4) if pat else None,
        "roa_a": round(neto / at * 365 / dias, 4) if at else None,
        "roe_a": round(neto / pat * 365 / dias, 4) if pat else None,
        "dso": round(dso) if dso else None, "dio": round(dio) if dio else None,
        "dpo": round(dpo) if dpo else None,
        "ccc": round(dso + dio - dpo) if (dso and dio and dpo) else None,
        "proveedor_comercial": round(prov, 2),
        "intercia": round(abs(solo("cuentas_por_pagar", INTERCIA[pais])
                              or solo("otros_activos_corrientes", INTERCIA[pais])), 2),
    }
    descuadre = at - pt - pat
    bgd = dict(bg); bgd["descuadre_esperado"] = round(descuadre, 2)
    return {"pais": pais, "empresa": None, "moneda": moneda, "periodo": "Enero – Octubre 2026",
            "per_ok": True, "pl": pyg, "bg": bgd, "ind": ind,
            "_totales": {"activo": round(at, 2), "pasivo": round(pt, 2), "patrimonio": round(pat, 2)}}


def main():
    hasta = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    d0 = datetime.date(int(hasta[:4]), 1, 1)
    d1 = datetime.date.fromisoformat(hasta)
    dias = (d1 - d0).days + 1
    od = F.Odoo(F.load_config()); od.authenticate()
    comps = F.companias(od, (od.cfg.get("_raw") or {}).get("company_map") or {})
    out = {"meta": {"corte": "7 de octubre de 2026", "corte_iso": hasta,
                    "dias": dias, "fuente": "Odoo · account.move.line, asientos contabilizados"}}
    for pais, cfg in PAISES.items():
        b = bloque_pais(od, pais, cfg["cid"], cfg["mon"], d0.isoformat(), hasta, dias)
        b["empresa"] = (comps.get(cfg["cid"]) or {}).get("name")
        out["EC" if pais == "Ecuador" else "CO"] = b
    sys.stdout.write(json.dumps(out, ensure_ascii=False, indent=2))
    sys.stderr.write("\n  llamadas XML-RPC: %d · dias del periodo: %d\n" % (od.calls, dias))


if __name__ == "__main__":
    main()
