#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
casamagna_build.py
==================
Fusiona SELL OUT (correo) + SELL IN (Odoo) y:
  1) construye el dashboard interactivo  CasaMagna/Sell_Out_CasaMagna.html
  2) lo comprime en .zip
  3) lo envía por correo (SMTP) a los destinatarios de casamagna_config.json

Entradas (generadas por casamagna_sellout.py y casamagna_sellin.py):
    CasaMagna/sellout_casamagna.tsv
    CasaMagna/sellout_semanas.json
    CasaMagna/sellin_casamagna.json
Plantilla:
    casamagna_dashboard_template.html   (marcadores /*__DATA__*/ y /*__SELLIN__*/)

USO:
    python3 casamagna_build.py            # arma dashboard + zip + envía correo
    python3 casamagna_build.py --no-mail  # solo arma dashboard + zip (no envía)
Env CASAMAGNA_DRYRUN=1  -> equivale a --no-mail.
"""
import os, sys, csv, json, re, ssl, smtplib, zipfile, datetime, mimetypes
from email.message import EmailMessage
from pathlib import Path
from collections import defaultdict

from casamagna_common import load_config, read_secret, make_normalizer, out_dir, expand, PROJ

TEMPLATE = PROJ / "casamagna_dashboard_template.html"


def _neto(costo, margen, tiva):
    try:
        c = float(costo or 0); m = float(margen or 0); t = float(tiva or 0)
    except ValueError:
        return 0.0
    return c / (1 - m) if 0 <= m < 1 else t / 1.19


def build_data(d):
    tsv = d / "sellout_casamagna.tsv"
    weeks = json.loads((d / "sellout_semanas.json").read_text(encoding="utf-8"))
    rows = []
    with tsv.open(encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            try:
                qty = float(r["cantidad"])
            except (ValueError, KeyError):
                qty = 0
            tiva = float(r.get("total_iva") or 0)
            costo = float(r.get("costo_total") or 0)
            marg = float(r.get("margen") or 0)
            rows.append([r["fecha"][:10], r["marca"].strip(), r["plaza"].strip(),
                         r["almacen"].strip(), r["sku"].strip(), r["descripcion"].strip(),
                         qty, round(_neto(costo, marg, tiva)), round(tiva), round(costo),
                         round(marg, 4), r["rep"].strip()])
    weeks = sorted(set(weeks) | {x[0] for x in rows})
    return {"cols": ["w", "marca", "plaza", "alm", "sku", "desc", "qty", "neto",
                     "tiva", "costo", "margen", "rep"], "rows": rows, "weeks": weeks}


def build_sellin_meta(d, weeks):
    si = json.loads((d / "sellin_casamagna.json").read_text(encoding="utf-8"))
    inst = si.get("instancias", [])
    firsts = [i.get("primera") for i in inst if i.get("primera")]
    src = " + ".join(i["nombre"] for i in inst if "error" not in i) or "Odoo XML-RPC"
    return {"win0": weeks[0] if weeks else "", "win1": weeks[-1] if weeks else "",
            "odoo_first": min(firsts) if firsts else None, "sources": src,
            "sellin": si.get("sellin", {})}


def render(data, sellin):
    tpl = TEMPLATE.read_text(encoding="utf-8")
    tpl = tpl.replace("/*__DATA__*/ null", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    tpl = tpl.replace("/*__SELLIN__*/ null", json.dumps(sellin, ensure_ascii=False, separators=(",", ":")))
    if "/*__DATA__*/" in tpl or "/*__SELLIN__*/" in tpl:
        sys.exit("ERROR: no se pudo inyectar la data en la plantilla.")
    return tpl


def kpis(data, sellin):
    ix = {c: i for i, c in enumerate(data["cols"])}
    R = data["rows"]
    neto = sum(r[ix["neto"]] for r in R); u = sum(r[ix["qty"]] for r in R)
    costo = sum(r[ix["costo"]] for r in R)
    norm, _ = make_normalizer({"TMO30H": "TMO30", "TMO24H": "TMO24", "TIM15": "TIM1501"}, [])
    so = defaultdict(float)
    for r in R:
        so[norm(r[ix["sku"]])] += r[ix["qty"]]
    so_desc = {}
    for r in R:
        so_desc.setdefault(norm(r[ix["sku"]]), r[ix["desc"]])
    si = sellin.get("sellin", {})
    tin = sum(v["u"] for v in si.values())
    detail = []
    for k in set(so) | set(si):
        iu = si.get(k, {}).get("u", 0); ou = so.get(k, 0)
        desc = so_desc.get(k) or si.get(k, {}).get("raw") or k
        detail.append({"sku": k, "desc": desc, "iu": iu, "ou": ou, "gap": iu - ou})
    excl = {e.upper() for e in load_config().get("sku_excluir", [])}
    falta = sorted([d for d in detail if d["gap"] < 0 and d["sku"] not in excl],
                   key=lambda x: x["gap"])
    return {"neto": neto, "u": u, "margen": (neto - costo) / neto if neto else 0,
            "sellin_u": tin, "cobertura": tin / u if u else 0, "falta": falta}


def make_zip(html_path):
    z = html_path.with_name("Dashboard_SellOut_CasaMagna.zip")
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(html_path, html_path.name)
    return z


def send_mail(cfg, zip_path, k):
    c = cfg["correo_salida"]
    pwd = read_secret(c["apppass_file"]).replace(" ", "")
    if not pwd:
        sys.exit(f"ERROR: falta App Password SMTP en {c['apppass_file']}.")
    recipients = c["to"] + c.get("cc", [])
    msg = EmailMessage()
    msg["Subject"] = f"Sell Out + Sell In · Casa Magna · actualizado {datetime.date.today():%d-%b-%Y}"
    msg["From"] = c["from"]; msg["To"] = ", ".join(c["to"])
    if c.get("cc"):
        msg["Cc"] = ", ".join(c["cc"])
    cob = f"{k['cobertura']*100:.0f}%" + (" (pidieron todo lo vendido)" if k["cobertura"] >= 1 else "")
    falta = k.get("falta", [])
    # ---- texto plano ----
    lineas_falta = ("\n".join(
        f"   - {d['sku']} ({d['desc'][:40]}): vendidas {d['ou']:.0f} / facturadas {d['iu']:.0f} -> faltan {-d['gap']:.0f}"
        for d in falta) or "   (ninguno: Casa Magna pidió todo lo que vendió)")
    body = (f"Actualización automática del análisis Casa Magna.\n\n"
            f">> SELL IN vs SELL OUT (para logística) <<\n"
            f"Cobertura In/Out: {cob}\n"
            f"Sell out (vendido por Casa Magna): {k['u']:,.0f} u\n"
            f"Sell in (facturado por VINTRAL, Odoo): {k['sellin_u']:,.0f} u\n\n"
            f"SKUs por gestionar (vendieron MÁS de lo que les facturamos = posible pedido pendiente):\n"
            f"{lineas_falta}\n\n"
            f"--- Contexto comercial ---\n"
            f"Venta neta (sin IVA): ${k['neto']:,.0f} COP | Margen bruto: {k['margen']*100:.1f}%\n\n"
            f"Adjunto el dashboard interactivo (descomprimir el .zip y abrir el HTML).\n")
    msg.set_content(body)
    # ---- HTML con énfasis en Sell In vs Sell Out ----
    filas = "".join(
        f"<tr><td style='padding:5px 10px'><b>{d['sku']}</b></td>"
        f"<td style='padding:5px 10px;color:#374151'>{d['desc'][:46]}</td>"
        f"<td style='padding:5px 10px;text-align:right'>{d['ou']:.0f}</td>"
        f"<td style='padding:5px 10px;text-align:right'>{d['iu']:.0f}</td>"
        f"<td style='padding:5px 10px;text-align:right;color:#b91c1c;font-weight:700'>{-d['gap']:.0f}</td></tr>"
        for d in falta)
    tabla = (f"<table style='border-collapse:collapse;font-size:13px;margin-top:8px'>"
             f"<tr style='background:#f3f4f6'><th style='padding:5px 10px;text-align:left'>SKU</th>"
             f"<th style='padding:5px 10px;text-align:left'>Descripción</th>"
             f"<th style='padding:5px 10px'>Vendidas</th><th style='padding:5px 10px'>Facturadas</th>"
             f"<th style='padding:5px 10px'>Faltan</th></tr>{filas}</table>") if falta else \
            "<p style='color:#15803d;font-weight:600'>✓ Ninguno: Casa Magna pidió todo lo que vendió.</p>"
    html = f"""<div style="font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;font-size:14px;color:#1f2937;line-height:1.55;max-width:700px">
<p>Equipo,</p>
<p>Actualización automática del análisis <b>Casa Magna</b>.</p>
<div style="border:2px solid #2563eb;border-radius:10px;padding:14px 16px;margin:14px 0;background:#eff6ff">
  <div style="font-size:15px;font-weight:700;color:#1e40af">🔁 Sell In vs Sell Out — seguimiento logístico (Juan José)</div>
  <p style="margin:8px 0 4px">Cobertura In/Out: <b>{cob}</b> &nbsp;·&nbsp; Sell out <b>{k['u']:,.0f} u</b> vs Sell in facturado <b>{k['sellin_u']:,.0f} u</b>.</p>
  <p style="margin:8px 0 2px"><b>SKUs por gestionar</b> (Casa Magna vendió más de lo que les hemos facturado → revisar pedido/despacho pendiente):</p>
  {tabla}
</div>
<p style="color:#6b7280;font-size:13px">Contexto comercial: venta neta ${k['neto']:,.0f} COP (sin IVA), margen bruto {k['margen']*100:.1f}%.</p>
<p>Adjunto el <b>dashboard interactivo</b> (descomprimir el .zip y abrir el HTML) con el detalle Sell In vs Sell Out por SKU, tendencia y rotación.</p>
<p style="margin:0">Saludos,<br>Juan Marcelo</p>
</div>"""
    msg.add_alternative(html, subtype="html")
    data = zip_path.read_bytes()
    msg.add_attachment(data, maintype="application", subtype="zip", filename=zip_path.name)
    ctx = ssl.create_default_context()
    if int(c.get("smtp_port", 465)) == 465:
        with smtplib.SMTP_SSL(c["smtp_host"], c["smtp_port"], context=ctx, timeout=60) as s:
            s.login(c["smtp_user"], pwd); s.send_message(msg, to_addrs=recipients)
    else:
        with smtplib.SMTP(c["smtp_host"], c["smtp_port"], timeout=60) as s:
            s.starttls(context=ctx); s.login(c["smtp_user"], pwd); s.send_message(msg, to_addrs=recipients)
    print(f"[OK] correo enviado a {recipients}")


def main(no_mail=False):
    cfg = load_config()
    d = out_dir(cfg)
    data = build_data(d)
    sellin = build_sellin_meta(d, data["weeks"])
    html = render(data, sellin)
    html_path = d / "Sell_Out_CasaMagna.html"
    html_path.write_text(html, encoding="utf-8")
    k = kpis(data, sellin)
    print(f"[OK] dashboard -> {html_path}")
    print(f"     neto=${k['neto']:,.0f}  u={k['u']:.0f}  margen={k['margen']*100:.1f}%  "
          f"sellin={k['sellin_u']:.0f}u  cobertura={k['cobertura']*100:.1f}%")
    z = make_zip(html_path)
    print(f"[OK] zip -> {z}")
    if no_mail or os.environ.get("CASAMAGNA_DRYRUN") == "1":
        print("[DRYRUN] no se envió correo.")
    else:
        send_mail(cfg, z, k)


if __name__ == "__main__":
    main(no_mail=("--no-mail" in sys.argv))
