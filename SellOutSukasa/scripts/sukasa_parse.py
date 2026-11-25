#!/usr/bin/env python3
"""Lee los Excel "ReporteProgramado*.xlsx" de Sukasa (uno por semana) y calcula
sell-out semanal, cobertura, necesidad de reposición y faltantes de exhibición.

Uso:  python3 sukasa_parse.py weeks.json sukasa_data.json [config.json]
weeks.json = [{"date":"YYYY-MM-DD","file":"ruta.xlsx"}, ...]  (cualquier orden; se ordena ascendente)

La lógica de cálculo es la misma que la versión original de la rutina (parse_vicomer.py);
solo cambia la lectura: ahora va directo del .xlsx con openpyxl, sin pasar por Drive.
"""
import json, math, sys, warnings
from datetime import datetime, date
warnings.filterwarnings("ignore")
import openpyxl

MES_COLS = ["ENE","FEB","MAR","ABR","MAY","JUN","JUL","AGO","SEP","OCT","NOV","DIC"]

def num(v):
    if v is None: return 0.0
    if isinstance(v, (int, float)): return float(v)
    s = str(v).strip().replace(" ", "").replace(",", "")
    if s in ("", "-", ".", "D", "B"): return 0.0
    try: return float(s)
    except ValueError: return 0.0

def txt(v):
    if v is None: return ""
    if isinstance(v, (datetime, date)): return v.strftime("%d/%m/%Y")
    if isinstance(v, float) and v.is_integer(): return str(int(v))
    return str(v).strip()

def load(path):
    ws = openpyxl.load_workbook(path, data_only=True).active
    rows = list(ws.iter_rows(values_only=True))
    header = [txt(c) for c in rows[0]]
    idx = {h: i for i, h in enumerate(header) if h}
    for need in ("CODIGO INTERNO", "PENDIENTES ENTREGA", "ENE", "PVP", "STOCK DISPONIBLE"):
        if need not in idx:
            raise SystemExit(f"{path}: falta la columna '{need}'. ¿Cambió el formato del reporte de Sukasa?")
    start = idx["PENDIENTES ENTREGA"] + 1; end = idx["ENE"]; store_cols = []
    for i in range(start, end):
        h = header[i]
        if h and not h.endswith("- B"):
            fi = i + 1 if (i + 1 < end and header[i + 1] == h + " - B") else None
            store_cols.append((h, i, fi))
    prods = {}
    for r in rows[1:]:
        r = list(r) + [None] * (len(header) - len(r))
        g = lambda n: r[idx[n]] if n in idx else None
        cod = txt(g("CODIGO INTERNO"))
        if not cod: continue
        stores = {}
        for h, ci, fi in store_cols:
            stores[h] = {"qty": num(r[ci]), "flag": txt(r[fi]) if fi is not None else ""}
        prods[cod] = {"cod": cod, "barras": txt(g("COD. BARRAS")), "ref": txt(g("REFERENCIA")),
            "marca": txt(g("MARCA")), "desc": txt(g("DESCRIPCION")), "tipo": txt(g("TIPO")),
            "descontinuado": txt(g("DESCONTINUADO")).upper() == "S", "pct_ventas": num(g("% VENTAS")),
            "pct_util": num(g("%UTIL")), "costo_landed": num(g("COSTO LANDED")), "pvp": num(g("PVP")),
            "ult_ingreso": txt(g("ULTIMO INGRESO")), "stock_disp": num(g("STOCK DISPONIBLE")),
            "pendientes": num(g("PENDIENTES ENTREGA")), "dias_stock": num(g("DIAS STOCK")),
            "meses": {m: num(g(m)) for m in MES_COLS}, "tot": num(g("TOT")), "stores": stores}
    return prods

def weekly_delta(cur, pri):
    out = {}
    for cod, p in cur.items():
        pp = pri.get(cod); u = 0.0
        if pp:
            for m in MES_COLS: u += p["meses"][m] - pp["meses"][m]
        out[cod] = max(u, 0.0)
    return out

def main():
    weeks_path, out_path = sys.argv[1], sys.argv[2]
    cfg = json.load(open(sys.argv[3], encoding="utf-8")) if len(sys.argv) > 3 else {}
    p = cfg.get("parametros", {})
    LEAD = p.get("lead_time_dias", 90); SAFETY = p.get("seguridad_dias", 30); TARGET = p.get("cobertura_objetivo_dias", 180)
    TRIGGER = LEAD + SAFETY
    weeks = sorted(json.load(open(weeks_path, encoding="utf-8")), key=lambda w: w["date"])
    # si llegaron dos reportes el mismo día, quedarse con el último de la lista
    dedup = {}
    for w in weeks: dedup[w["date"]] = w
    weeks = [dedup[k] for k in sorted(dedup)]
    if len(weeks) < 2: raise SystemExit("Se necesitan al menos 2 reportes semanales para calcular la semana.")
    snaps = [(w["date"], load(w["file"])) for w in weeks]
    for d, s in snaps:
        if len(s) < p.get("min_productos", 30): raise SystemExit(f"{d}: solo {len(s)} productos, reporte incompleto")
    cur_d, cur = snaps[-1]; pri_d, pri = snaps[-2]

    weekly_series = []
    for i in range(1, len(snaps)):
        de, a = snaps[i]; b = snaps[i - 1][1]; dw = weekly_delta(a, b)
        dias = (datetime.fromisoformat(de) - datetime.fromisoformat(snaps[i - 1][0])).days
        mk = {}
        for c, uu in dw.items():
            m = a[c]["marca"] or "(s/m)"; e = mk.setdefault(m, {"u": 0.0, "r": 0.0}); e["u"] += uu; e["r"] += uu * a[c]["pvp"]
        weekly_series.append({"week_end": de, "dias": dias, "units": round(sum(dw.values()), 1),
            "rev": round(sum(dw[c] * a[c]["pvp"] for c in dw), 2),
            "marca": {k: {"units": round(v["u"], 1), "rev": round(v["r"], 2)} for k, v in mk.items()}})

    dwk = weekly_delta(cur, pri); rows = []; marca = {}
    for cod, p_ in cur.items():
        wk_u = dwk.get(cod, 0.0); wk_r = wk_u * p_["pvp"]
        mc = [p_["meses"][m] for m in MES_COLS if p_["meses"][m] > 0]
        vel_mes = (sum(mc) / len(mc)) if mc else 0.0; vel_dia = vel_mes / 30.0
        disp = p_["stock_disp"] + p_["pendientes"]
        cover = (disp / vel_dia) if vel_dia > 0 else (999 if disp > 0 else 0)
        need = (not p_["descontinuado"]) and vel_dia > 0 and cover < TRIGGER
        oc = max(0, math.ceil(vel_dia * TARGET - disp)) if need else 0
        falt = [h for h, s in p_["stores"].items() if s["flag"] == "D" and s["qty"] == 0]
        m = p_["marca"] or "(s/m)"; ag = marca.setdefault(m, {"u": 0.0, "r": 0.0}); ag["u"] += wk_u; ag["r"] += wk_r
        rows.append({**{k: p_[k] for k in ("cod","barras","ref","marca","desc","tipo","pvp","stock_disp","pendientes","dias_stock",
                     "descontinuado","pct_ventas","pct_util","costo_landed","ult_ingreso")},
            "meses": p_["meses"], "tot": p_["tot"], "wk_units": round(wk_u, 2), "wk_rev": round(wk_r, 2), "vel_mes": round(vel_mes, 2),
            "cover_dias": round(cover, 0), "need_oc": need, "oc_qty": oc, "faltantes": falt, "n_faltantes": len(falt), "disponible": disp})

    monthly = []
    for m in MES_COLS:
        u = sum(p_["meses"][m] for p_ in cur.values()); rev = sum(p_["meses"][m] * p_["pvp"] for p_ in cur.values())
        if u or rev: monthly.append({"mes": m, "units": round(u, 1), "rev": round(rev, 2)})
    monthly_marca = {}
    for p_ in cur.values():
        e = monthly_marca.setdefault(p_["marca"] or "(s/m)", {m: 0.0 for m in MES_COLS})
        for m in MES_COLS: e[m] += p_["meses"][m]
    wcmp = None
    if len(weekly_series) >= 2:
        a, b = weekly_series[-1], weekly_series[-2]
        wcmp = {"cur": a["rev"], "prev": b["rev"], "cur_u": a["units"], "prev_u": b["units"], "d_rev": round(a["rev"] - b["rev"], 2),
                "d_units": round(a["units"] - b["units"], 1), "pct_rev": round(100 * (a["rev"] - b["rev"]) / b["rev"], 1) if b["rev"] else None,
                "week_cur": a["week_end"], "week_prev": b["week_end"]}
    tot_u = sum(r["wk_units"] for r in rows); tot_r = sum(r["wk_rev"] for r in rows)
    summary = {"generated": datetime.now().isoformat(timespec="seconds"), "fecha_reporte": cur_d, "fecha_anterior": pri_d,
        "dias_periodo": weekly_series[-1]["dias"], "week_units": round(tot_u, 1), "week_rev": round(tot_r, 2), "n_products": len(rows),
        "n_oc": sum(1 for r in rows if r["need_oc"]), "oc_units": sum(r["oc_qty"] for r in rows if r["need_oc"]),
        "n_faltantes_lineas": sum(1 for r in rows if r["n_faltantes"] > 0), "n_faltantes_total": sum(r["n_faltantes"] for r in rows),
        "marca": {k: {"units": round(v["u"], 1), "rev": round(v["r"], 2)} for k, v in marca.items()},
        "weekly_series": weekly_series, "weekly_cmp": wcmp, "monthly": monthly,
        "monthly_marca": {k: {m: round(v[m], 1) for m in MES_COLS} for k, v in monthly_marca.items()},
        "config": {"lead": LEAD, "safety": SAFETY, "target": TARGET, "trigger": TRIGGER},
        "stores": sorted({h for p_ in cur.values() for h in p_["stores"]})}
    json.dump({"summary": summary, "rows": rows}, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("OK", cur_d, "vs", pri_d, f"({summary['dias_periodo']} días)", "| semana $", summary["week_rev"], "u", summary["week_units"],
          "| OC", summary["n_oc"], "| faltantes", summary["n_faltantes_total"])

if __name__ == "__main__":
    main()
