#!/usr/bin/env python3
"""Une sell-out Sukasa + stock Odoo + tránsito (opcional) y genera:
  - vicomer_data.json  (datos completos)
  - dashboard.html     (plantilla con los datos embebidos, lista para publicar)
  - emails.json        (3 correos: to, subject, html, text)

Uso: python3 build_report.py <dir_trabajo> <config.json> <templates_dir>
En <dir_trabajo> deben existir sukasa_data.json y, opcionalmente, odoo_stock.json y transito.json.
"""
import json, os, sys
from collections import Counter, defaultdict

def norm(s): return "".join(str(s or "").upper().split())
fmt = lambda v: "$" + f"{v:,.0f}"
fn = lambda v: f"{v:,.0f}"

def load_opt(path):
    try: return json.load(open(path, encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError): return None

def merge_supply(d, odoo, transit, cfg):
    S, R = d["summary"], d["rows"]
    fuente = cfg.get("odoo", {}).get("fuente_transito", "max")  # archivo | odoo | max
    tmap = defaultdict(lambda: {"qty": 0.0, "eta": None, "docs": []})
    if transit:
        for t in transit if isinstance(transit, list) else transit.get("items", []):
            key = None
            for r in R:
                if (t.get("cod") and t["cod"] == r["cod"]) or (t.get("barras") and norm(t["barras"]) == norm(r["barras"])) \
                        or (t.get("ref") and norm(t["ref"]) == norm(r["ref"])):
                    key = r["cod"]; break
            if not key: continue
            e = tmap[key]; e["qty"] += float(t.get("qty", 0) or 0)
            if t.get("eta") and (e["eta"] is None or t["eta"] < e["eta"]): e["eta"] = t["eta"]
            if t.get("doc"): e["docs"].append(str(t["doc"]))
    ok = bool(odoo and odoo.get("ok"))
    tot_sellin = tot_import = tot_transit = 0; skus_sellin = 0; oportunidades = []
    # Bolsa compartida por producto Odoo: si dos SKU de Sukasa apuntan al mismo producto
    # (p. ej. un "REEMPLAZO"), el stock libre y el tránsito se asignan una sola vez.
    # Prioridad: primero los SKU en quiebre en Sukasa, luego por menor cobertura.
    pool_free, pool_tr, compartidos = {}, {}, Counter()
    for r in R:
        it = (odoo or {}).get("items", {}).get(r["cod"]) if ok else None
        if it: compartidos[it.get("odoo_id") or it.get("odoo_code")] += 1
    for r in sorted(R, key=lambda r: (r["disponible"] > 0, r["cover_dias"])):
        it = (odoo or {}).get("items", {}).get(r["cod"]) if ok else None
        r["vic_match"] = bool(it)
        free = float(it["free"]) if it else 0.0
        odoo_in = float(it["incoming"]) if it else 0.0
        file_in = tmap[r["cod"]]["qty"] if r["cod"] in tmap else 0.0
        transit_q = {"archivo": file_in, "odoo": odoo_in}.get(fuente, max(file_in, odoo_in))
        r.update({"vic_free": free, "vic_on_hand": float(it["on_hand"]) if it else 0.0, "vic_transit": transit_q,
                  "vic_eta": tmap[r["cod"]]["eta"] if r["cod"] in tmap else None,
                  "vic_docs": tmap[r["cod"]]["docs"] if r["cod"] in tmap else []})
        need = r["oc_qty"] if r["need_oc"] else 0
        key = (it.get("odoo_id") or it.get("odoo_code")) if it else None
        if it:
            pool_free.setdefault(key, free); pool_tr.setdefault(key, transit_q)
            r["vic_compartido"] = compartidos[key] > 1
        sellin = min(need, pool_free[key]) if it else 0
        rest = need - sellin
        cub = min(rest, pool_tr[key]) if it else 0
        if it: pool_free[key] -= sellin; pool_tr[key] -= cub
        imp = rest - cub if it else need
        r.update({"sellin_qty": int(sellin), "transit_cover_qty": int(cub), "import_qty": int(imp)})
        tot_sellin += sellin; tot_import += imp; tot_transit += cub; skus_sellin += 1 if sellin > 0 else 0
        if it and r["disponible"] <= 0 and free > 0 and not r["descontinuado"]:
            oportunidades.append(r["cod"])
    S["odoo"] = {"ok": ok, "as_of": (odoo or {}).get("as_of"), "error": (odoo or {}).get("error"),
                 "transit_source": fuente if transit else ("odoo" if ok else None),
                 "sellin_units": int(tot_sellin), "sellin_skus": skus_sellin, "transit_units": int(tot_transit),
                 "import_units": int(tot_import), "oportunidades_quiebre": oportunidades,
                 "unmatched": (odoo or {}).get("unmatched", []) if ok else [],
                 "compartidos": sorted(r["cod"] for r in R if r.get("vic_compartido"))}

TH = 'bgcolor="#0b2545" style="color:#fff"'
def table(h, rows, right=()):
    s = '<table border="1" bordercolor="#ccc" cellpadding="5" style="border-collapse:collapse;font-size:12px"><tr>' + \
        "".join(f"<th {TH}>{x}</th>" for x in h) + "</tr>"
    for r in rows: s += "<tr>" + "".join(f'<td align="right">{v}</td>' if i in right else f"<td>{v}</td>" for i, v in enumerate(r)) + "</tr>"
    return s + "</table>"
def ttable(h, rows): return "\n".join([" | ".join(h)] + [" | ".join(str(v) for v in r) for r in rows])
wrap = lambda b: f'<div style="font-family:Arial,sans-serif;font-size:13px;color:#14181d;max-width:780px">{b}</div>'
ul = lambda xs: "<ul>" + "".join(f"<li>{x}</li>" for x in xs) + "</ul>"
tl = lambda xs: "\n".join("- " + x for x in xs)

def emails(d, cfg):
    S, R = d["summary"], d["rows"]; F = S["fecha_reporte"]; c = S["weekly_cmp"]; ws = S["weekly_series"]
    firma = cfg.get("firma", "Saludos,")
    OD = S.get("odoo", {}).get("ok")
    out = {}
    # ---------- 1. Ventas ----------
    prev = [w["rev"] for w in ws[:-1]]; avg_prev = sum(prev) / len(prev) if prev else 0
    mk = sorted(S["marca"].items(), key=lambda x: -x[1]["rev"])
    mrows = [(m, fn(v["units"]), fmt(v["rev"]), f'{100 * v["rev"] / S["week_rev"]:.0f}%' if S["week_rev"] else "–") for m, v in mk]
    top = sorted([r for r in R if r["wk_rev"] > 0], key=lambda r: -r["wk_rev"])[:6]
    trows = [(r["ref"], r["desc"][:50], r["marca"], fn(r["wk_units"]), fmt(r["wk_rev"]), fn(r["disponible"])) for r in top]
    sinv = sum(1 for r in R if r["wk_units"] == 0)
    serie = " · ".join(f'{w["week_end"][5:]}: {fmt(w["rev"])}' for w in ws)
    sen = []
    if avg_prev:
        ratio = S["week_rev"] / avg_prev
        if ratio >= 1.5: sen.append(f"Semana atípica al alza: {fmt(S['week_rev'])} es {ratio:.1f}x el promedio de las semanas previas ({fmt(avg_prev)}). Validar con Sukasa si hubo evento o promoción antes de tomarlo como run-rate.")
        elif ratio <= 0.6: sen.append(f"Semana débil: {fmt(S['week_rev'])} es {ratio:.1f}x el promedio previo ({fmt(avg_prev)}). Revisar quiebres y exhibición antes de atribuirlo a demanda.")
        else: sen.append(f"Semana en línea con el promedio previo ({fmt(avg_prev)}; {ratio:.1f}x).")
    if S["dias_periodo"] != 7: sen.append(f"Atención: el periodo comparado es de {S['dias_periodo']} días (faltó algún reporte), no de 7.")
    if mk and S["week_rev"]: sen.append(f"{mk[0][0]} concentra {100 * mk[0][1]['rev'] / S['week_rev']:.0f}% del valor de la semana.")
    qtop = [r for r in top if r["disponible"] <= 0]
    if qtop: sen.append(f"{len(qtop)} de los {len(top)} productos top quedaron con disponible 0 en Sukasa ({', '.join(r['ref'] for r in qtop)}): riesgo de venta perdida por quiebre." +
                        (" VICOMER tiene stock para reponer: " + ", ".join(r['ref'] for r in qtop if r.get('vic_free', 0) > 0) + "." if OD and any(r.get('vic_free', 0) > 0 for r in qtop) else ""))
    to1 = cfg["destinatarios"]["ventas"]
    pct = f"{'+' if (c and c['pct_rev'] or 0) > 0 else ''}{c['pct_rev']}%" if c and c["pct_rev"] is not None else "n/d"
    cmp_h = f"{fmt(c['prev'])} ({fn(c['prev_u'])} u) → {fmt(c['cur'])} ({fn(c['cur_u'])} u) · <b>{pct}</b>" if c else "n/d"
    html = wrap(f"""<p>Hola,</p><p>Sell-out de VICOMER en Sukasa, semana cerrada al <b>{F}</b> (vs {S['fecha_anterior']}).</p>
<p><b>Total semana:</b> {fn(S['week_units'])} unidades · <b>{fmt(S['week_rev'])}</b> a PVP<br><b>Vs semana anterior:</b> {cmp_h}<br><span style="color:#666">Serie: {serie}</span></p>
<p><b>Por marca</b></p>{table(['Marca','Unid.','Valor PVP','% semana'], mrows, (1,2,3))}
<p><b>Top productos (valor PVP)</b></p>{table(['Ref.','Producto','Marca','Unid.','Valor PVP','Disp. Sukasa'], trows, (3,4,5))}
<p><b>SKU sin venta en la semana:</b> {sinv} de {S['n_products']}.</p><p><b>Señales</b></p>{ul(sen)}
<p style="color:#666;font-size:11px">Valor estimado a PVP vigente (unidades × PVP), no es facturación neta. Fuente: reporte programado ERP Sukasa.</p><p>{firma}</p>""")
    text = f"""Hola,\n\nSell-out de VICOMER en Sukasa, semana cerrada al {F} (vs {S['fecha_anterior']}).\n\nTotal semana: {fn(S['week_units'])} u / {fmt(S['week_rev'])} a PVP\nVs semana anterior: {pct}\nSerie: {serie}\n\nPor marca:\n{ttable(['Marca','Unid.','Valor PVP','%'], mrows)}\n\nTop productos:\n{ttable(['Ref.','Producto','Marca','Unid.','Valor PVP','Disp. Sukasa'], trows)}\n\nSKU sin venta: {sinv} de {S['n_products']}.\n\nSeñales:\n{tl(sen)}\n\nValor estimado a PVP, no es facturación neta.\n\n{firma}"""
    out["ventas"] = {"to": to1, "subject": f"Sell-out Sukasa · Semana al {F}", "html": html, "text": text}

    # ---------- 2. Stock & OC ----------
    cf = S["config"]; O = S.get("odoo", {})
    A = sorted([r for r in R if r["need_oc"] and r["disponible"] <= 0], key=lambda r: -r["vel_mes"])
    B = sorted([r for r in R if r["need_oc"] and r["disponible"] > 0], key=lambda r: r["cover_dias"])[:8]
    regla = (f"velocidad = promedio mensual de los meses con venta en el año; disponible Sukasa = stock + pendientes de entrega; "
             f"se dispara reposición cuando la cobertura cae bajo {cf['trigger']} días (lead time {cf['lead']} + seguridad {cf['safety']}); "
             f"necesidad = velocidad × {cf['target']} días − disponible. Excluye descontinuados.")
    if OD:
        regla += (" Cruce con Odoo: la necesidad se cubre primero con stock libre VICOMER (despacho inmediato), luego con tránsito; "
                  "el saldo es importación neta atribuible a Sukasa (no incluye demanda de otros canales).")
        hA = ['Ref.','Producto','Marca','Disp. Sukasa','Vel./mes','Necesidad','Stock VIC','Tránsito','Despachar ya','Importar']
        rA = [(r["ref"], r["desc"][:42], r["marca"], fn(r["disponible"]), f'{r["vel_mes"]:.1f}', fn(r["oc_qty"]),
               fn(r["vic_free"]) if r["vic_match"] else "s/m", fn(r["vic_transit"]) + (f' ({r["vic_eta"]})' if r.get("vic_eta") else "") if r["vic_match"] else "s/m",
               fn(r["sellin_qty"]), fn(r["import_qty"])) for r in A]
        hB = ['Ref.','Producto','Marca','Disp.','Cobertura (días)','Necesidad','Stock VIC','Despachar ya','Importar']
        rB = [(r["ref"], r["desc"][:42], r["marca"], fn(r["disponible"]), fn(r["cover_dias"]), fn(r["oc_qty"]),
               fn(r["vic_free"]) if r["vic_match"] else "s/m", fn(r["sellin_qty"]), fn(r["import_qty"])) for r in B]
        rA_right, rB_right = (3,4,5,6,7,8,9), (3,4,5,6,7,8)
        sell = sorted([r for r in R if r["sellin_qty"] > 0], key=lambda r: (r["disponible"] > 0, -r["sellin_qty"]))
        rS = [(r["ref"], r["desc"][:42], fn(r["disponible"]), fn(r["vic_free"]), fn(r["sellin_qty"])) for r in sell]
        imp_m = Counter(); imp_v = Counter()
        for r in R:
            if r["import_qty"] > 0: imp_m[r["marca"]] += r["import_qty"]; imp_v[r["marca"]] += r["import_qty"] * r["costo_landed"]
        rM = [(m, fn(imp_m[m]), fmt(imp_v[m])) for m in sorted(imp_m, key=lambda m: -imp_v[m])]
        um = O.get("unmatched", [])
        kpi = (f"<b>{S['n_oc']} SKU</b> con necesidad de reposición · <b>{fn(S['oc_units'])} u</b>. De eso: "
               f"<b>{fn(O['sellin_units'])} u despachables ya</b> desde stock VICOMER ({O['sellin_skus']} SKU) · "
               f"{fn(O['transit_units'])} u cubiertas por tránsito · <b>{fn(O['import_units'])} u a importar</b>.")
        extra_h = (f"<p><b>Despachar ya a Sukasa (sell-in desde stock VICOMER, Odoo {O['as_of']})</b></p>" +
                   (table(['Ref.','Producto','Disp. Sukasa','Stock VIC libre','Despachar'], rS, (2,3,4)) if rS else "<p>Ninguno.</p>") +
                   "<p><b>Importación neta por marca (a costo landed)</b></p>" + (table(['Marca','Unid.','Valor costo landed'], rM, (1,2)) if rM else "<p>Nada que importar.</p>") +
                   (f"<p style='color:#8a6100'>{len(um)} SKU de Sukasa sin match en Odoo ({', '.join(u['ref'] for u in um[:12])}{'…' if len(um) > 12 else ''}): se tratan como importación completa. Agregarlos a mapeo_sku.csv.</p>" if um else ""))
        extra_t = (f"\nDespachar ya (stock VICOMER):\n{ttable(['Ref.','Producto','Disp. Sukasa','Stock VIC','Despachar'], rS) if rS else 'Ninguno.'}\n\n"
                   f"Importación neta por marca:\n{ttable(['Marca','Unid.','Costo landed'], rM) if rM else 'Nada.'}\n" +
                   (f"\nSKU sin match en Odoo: {', '.join(u['ref'] for u in um)}\n" if um else ""))
        reco = ["Emitir hoy la nota de pedido/despacho a Sukasa por la tabla «Despachar ya»: es venta inmediata y corrige quiebres sin esperar importación.",
                "Consolidar la importación neta por proveedor/marca para optimizar contenedor y flete.",
                f"Validar lead time real por proveedor: si es mayor a {cf['lead']} días, el disparo se queda corto.",
                "La importación neta solo mira la demanda de Sukasa: antes de emitir OC al proveedor, sumar la demanda de los demás canales."]
    else:
        hA = ['Ref.','Producto','Marca','Disp.','Vel./mes','Reposición sug.']
        rA = [(r["ref"], r["desc"][:45], r["marca"], fn(r["disponible"]), f'{r["vel_mes"]:.1f}', fn(r["oc_qty"])) for r in A]
        hB = ['Ref.','Producto','Marca','Disp.','Vel./mes','Cobertura (días)','Reposición sug.']
        rB = [(r["ref"], r["desc"][:45], r["marca"], fn(r["disponible"]), f'{r["vel_mes"]:.1f}', fn(r["cover_dias"]), fn(r["oc_qty"])) for r in B]
        rA_right, rB_right = (3,4,5), (3,4,5,6)
        kpi = f"<b>{S['n_oc']} SKU</b> requieren reposición · <b>{fn(S['oc_units'])} unidades</b> · {len(A)} SKU ya en quiebre."
        extra_h = f"<p style='color:#8a6100'>Sin cruce con Odoo esta semana ({O.get('error') or 'no disponible'}): no se distingue qué sale de stock VICOMER y qué hay que importar.</p>"
        extra_t = "\nSin cruce con Odoo esta semana.\n"
        reco = ["Cruzar contra stock propio VICOMER antes de emitir OC: parte puede cubrirse con sell-in inmediato.",
                "Consolidar por proveedor/marca; validar lead time real."]
    reco.append(f"Las cantidades son techo técnico ({cf['target']} días de cobertura); ajustar por MOQ y caja.")
    html = wrap(f"""<p>Hola,</p><p>Reposición Sukasa con corte al <b>{F}</b>.</p><p>{kpi}</p><p style="color:#555"><b>Regla:</b> {regla}</p>{extra_h}
<p><b>A. Quiebre inmediato en Sukasa</b> (disponible ≤ 0), por rotación</p>{table(hA, rA, rA_right) if rA else '<p>Ninguno.</p>'}
<p><b>B. Cobertura crítica</b> (top 8)</p>{table(hB, rB, rB_right) if rB else '<p>Ninguno.</p>'}
<p><b>Recomendación</b></p>{ul(reco)}<p>{firma}</p>""")
    text = (f"Hola,\n\nReposición Sukasa con corte al {F}.\n\n" + kpi.replace("<b>", "").replace("</b>", "") + f"\n\nRegla: {regla}\n{extra_t}\n"
            f"A. Quiebre inmediato:\n{ttable(hA, rA)}\n\nB. Cobertura crítica:\n{ttable(hB, rB)}\n\nRecomendación:\n{tl(reco)}\n\n{firma}")
    out["stock_oc"] = {"to": cfg["destinatarios"]["stock_oc"], "subject": f"Stock & reposición · Sukasa · {F}", "html": html, "text": text}

    # ---------- 3. Faltantes ----------
    cnt = Counter(h for r in R for h in r["faltantes"]); lrows = cnt.most_common()
    tf = sorted([r for r in R if r["n_faltantes"] > 0 and not r["descontinuado"]], key=lambda r: (-r["n_faltantes"], r["disponible"]))[:10]
    hF = ['Ref.','Producto','Huecos','Stock CD Sukasa'] + (['Stock VIC'] if OD else []) + ['Locales']
    rF = [(r["ref"], r["desc"][:42], r["n_faltantes"], fn(r["disponible"])) + ((fn(r["vic_free"]) if r["vic_match"] else "s/m",) if OD else ()) + (", ".join(r["faltantes"]),) for r in tf]
    desc_h = sum(r["n_faltantes"] for r in R if r["descontinuado"])
    con = [r for r in R if r["n_faltantes"] > 0 and r["disponible"] > 0 and not r["descontinuado"]]; cs_h = sum(r["n_faltantes"] for r in con)
    sin = [r for r in R if r["n_faltantes"] > 0 and r["disponible"] <= 0 and not r["descontinuado"]]; ss_h = sum(r["n_faltantes"] for r in sin)
    comp = f"{cs_h} huecos en SKU con stock en CD Sukasa (reponibles ya) · {ss_h} en SKU sin stock en Sukasa"
    if OD:
        vic = [r for r in sin if r.get("vic_free", 0) > 0]; vic_h = sum(r["n_faltantes"] for r in vic)
        comp += f" (de ellos {vic_h} se cubren con stock VICOMER → despachar)"
    comp += f" · {desc_h} en descontinuados (depurar marca D)."
    L = lrows[0] if lrows else ("–", 0)
    plan = [f"Comercial: pedir a Sukasa traslado CD → piso de {len(con)} SKU con stock ({cs_h} huecos), empezando por {L[0]} ({L[1]} huecos)" + (f", luego {lrows[1][0]} y {lrows[2][0]}." if len(lrows) > 2 else "."),
            "Compras/Logística: los huecos sin stock en Sukasa se resuelven con la tabla «Despachar ya» del correo de reposición; el resto depende de importación." if OD else
            "Compras: los huecos sin stock dependen de la reposición; priorizar alta rotación.",
            f"Depuración: solicitar a Sukasa quitar la marca D de los descontinuados ({desc_h} huecos ficticios)."]
    html = wrap(f"""<p>Hola,</p><p>Faltantes de exhibición de VICOMER en Sukasa al <b>{F}</b> (SKU marcados para piso «D» con 0 unidades en el local).</p>
<p><b>{S['n_faltantes_total']} huecos</b> en <b>{S['n_faltantes_lineas']} SKU</b> y <b>{len(cnt)} locales</b>.<br>{comp}</p>
<p><b>Ranking de locales</b></p>{table(['Local','Huecos'], lrows, (1,))}
<p><b>Top productos activos con más huecos</b></p>{table(hF, rF, (2,3,4) if OD else (2,3))}
<p><b>Plan de acción</b></p>{ul(plan)}<p>{firma}</p>""")
    text = (f"Hola,\n\nFaltantes de exhibición al {F}.\n\n{S['n_faltantes_total']} huecos en {S['n_faltantes_lineas']} SKU y {len(cnt)} locales.\n{comp}\n\n"
            f"Locales: " + " · ".join(f"{h} {n}" for h, n in lrows) + f"\n\nTop productos:\n{ttable(hF, rF)}\n\nPlan:\n{tl(plan)}\n\n{firma}")
    out["faltantes"] = {"to": cfg["destinatarios"]["faltantes"], "subject": f"Faltantes de exhibición por local · Sukasa · {F}", "html": html, "text": text}
    return out

def main():
    wd, cfg_path, tpl_dir = sys.argv[1:4]
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    d = json.load(open(os.path.join(wd, "sukasa_data.json"), encoding="utf-8"))
    merge_supply(d, load_opt(os.path.join(wd, "odoo_stock.json")), load_opt(os.path.join(wd, "transito.json")), cfg)
    json.dump(d, open(os.path.join(wd, "vicomer_data.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    tpl = open(os.path.join(tpl_dir, "dashboard_template.html"), encoding="utf-8").read()
    data = json.dumps(d, ensure_ascii=False).replace("</", "<\\/")
    assert tpl.count("__DATA__") == 1
    open(os.path.join(wd, "dashboard.html"), "w", encoding="utf-8").write(tpl.replace("__DATA__", data))
    em = emails(d, cfg)
    json.dump(em, open(os.path.join(wd, "emails.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    S = d["summary"]; O = S["odoo"]
    print(f"OK {S['fecha_reporte']} | semana {fmt(S['week_rev'])} ({S['week_units']:.0f} u) | "
          f"reposición {S['n_oc']} SKU/{S['oc_units']} u | faltantes {S['n_faltantes_total']} | "
          + (f"Odoo: despachar {O['sellin_units']} u, importar {O['import_units']} u, sin match {len(O['unmatched'])}" if O["ok"] else "Odoo: sin cruce"))

if __name__ == "__main__":
    main()
