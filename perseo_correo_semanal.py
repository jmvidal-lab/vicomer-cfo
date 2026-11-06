#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
perseo_correo_semanal.py
========================
Envía el CORREO SEMANAL con el estado consolidado del presupuesto del Grupo VICOMER
(Ecuador + Colombia + Costa Rica), TODO sin IVA. Lee el MISMO archivo que se genera
en la carpeta (estado_grupo.json), así el correo y el Excel son 100% congruentes.

- Adjunta únicamente el consolidado "ESTADO PRESUPUESTO GRUPO VICOMER.xlsx".
- Envío por SMTP (Gmail personal, ver correo_config.json).

Destinatarios (correo_config.json / env):  Para dir.comercial@v-comer.com · CC jmvidal@v-comer.com
Prueba sin enviar:  PERSEO_MAIL_DRYRUN=1 python3 perseo_correo_semanal.py
"""
import os, sys, ssl, json, smtplib, datetime, mimetypes, re
from pathlib import Path
from email.message import EmailMessage

import perseo_presupuesto as PE

NAVY="#1F3864"; GREEN="#2E7D32"; RED="#C0392B"; AMBER="#B9770E"; GREY="#595959"

# ------------------------------------------------------------------ config correo/smtp
def _load_cfg():
    for p in (Path.home() / ".perseo_correo.json",
              Path.home() / "Claude" / "Projects" / "CFO VICOMER" / "correo_config.json"):
        if p.exists():
            try: return json.loads(p.read_text(encoding="utf-8"))
            except Exception: pass
    return {}
_CFG = _load_cfg()
def _list(envk, cfgk, default):
    v = os.environ.get(envk)
    if v: return [e.strip() for e in v.split(",") if e.strip()]
    c = _CFG.get(cfgk)
    return (c if isinstance(c, list) else [c]) if c else default

MAIL_TO   = _list("PERSEO_MAIL_TO", "to", ["dir.comercial@v-comer.com"])
MAIL_CC   = _list("PERSEO_MAIL_CC", "cc", ["jmvidal@v-comer.com"])
SMTP_USER = os.environ.get("SMTP_USER") or _CFG.get("smtp_user") or "jmvidal@v-comer.com"
MAIL_FROM = os.environ.get("PERSEO_MAIL_FROM") or _CFG.get("from") or SMTP_USER
SMTP_HOST = os.environ.get("SMTP_HOST") or _CFG.get("smtp_host") or "smtp.gmail.com"
SMTP_PORT = int(os.environ.get("SMTP_PORT") or _CFG.get("smtp_port") or 465)
DRYRUN    = os.environ.get("PERSEO_MAIL_DRYRUN") == "1"

CONSOLIDADO = PE.FILES_DIR / "ESTADO PRESUPUESTO GRUPO VICOMER.xlsx"
GRUPO_JSON  = PE.OUT_DIR / "estado_grupo.json"

def get_smtp_password():
    p = os.environ.get("SMTP_APP_PASSWORD") or _CFG.get("app_password")
    if not p:
        f = Path.home() / ".perseo_smtp"
        if f.exists(): p = f.read_text(encoding="utf-8")
    if not p:
        sys.exit("ERROR: no se encontró la contraseña SMTP (correo_config.json / SMTP_APP_PASSWORD / ~/.perseo_smtp)")
    return p.replace(" ", "").strip()

# ------------------------------------------------------------------ datos
def get_estado():
    if GRUPO_JSON.exists():
        e = json.loads(GRUPO_JSON.read_text(encoding="utf-8"))
        if e.get("generado", "")[:10] == datetime.date.today().isoformat():
            PE.log("usando estado_grupo del día"); return e
    PE.log("estado_grupo no fresco; regenerando...")
    import estado_grupo as EG
    return EG.run(datetime.date.today().year)

def money(v, cur):
    try:
        return (f"{v:,.0f} COP" if cur == "COP" else f"${v:,.0f}")
    except Exception:
        return "-"

def pct(v):
    return f"{v*100:.0f}%" if isinstance(v, (int, float)) else "-"

def cumpl_color(v):
    if v is None: return GREY
    return GREEN if v >= 1 else (AMBER if v >= 0.85 else RED)

ORDEN = ["Ecuador", "Colombia", "Costa Rica"]

# ------------------------------------------------------------------ apreciaciones
def apreciaciones(est):
    ap = []; P = est["paises"]; mes = est["meses"][est["mes_cierre"]-1]
    for pais in ORDEN:
        d = P.get(pais)
        if not d or d.get("cumpl_ytd") is None: continue
        estado = "por encima" if d["cumpl_ytd"] >= 1 else "por debajo"
        ap.append(f"<b>{pais}</b>: {pct(d['cumpl_ytd'])} del presupuesto YTD a {mes} — {estado} del plan "
                  f"({money(d['var_ytd'], d['moneda'])}).")
    # canales rezagados de Ecuador
    ec = P.get("Ecuador", {})
    canales = {k: v for k, v in (ec.get("canales") or {}).items() if v.get("ppto_ytd")}
    rez = sorted([(k, v) for k, v in canales.items() if (v.get("cumpl_ytd") or 1) < 0.85],
                 key=lambda kv: kv[1].get("cumpl_ytd") or 0)
    if rez:
        txt = "; ".join(f"{k} {pct(v['cumpl_ytd'])}" for k, v in rez[:4])
        ap.append(f"Ecuador — canales rezagados (&lt;85%): {txt}. Foco comercial ahí.")
    # nota histórico Colombia
    co = P.get("Colombia", {})
    if co.get("hist_amount"):
        ap.append(f"Colombia: VINTRAL migró al Odoo actual en abril; Ene-{est['meses'][co['hist_through']-1]} "
                  f"viene de la instancia anterior (vintral1): {money(co['hist_amount'],'COP')}.")
    return ap

# ------------------------------------------------------------------ HTML
def build_html(est):
    mes = est["meses"][est["mes_cierre"]-1]; P = est["paises"]
    # total global en USD (destacado)
    g = est.get("global_usd") or {}
    g_block = ""
    if g.get("real") is not None:
        gcol = cumpl_color(g.get("cumpl"))
        g_block = (f'<table style="width:100%;border-collapse:collapse;background:#fff;border:1px solid #eee;border-top:none;">'
                   f'<tr><td style="padding:14px 16px;">'
                   f'<div style="font-size:11px;color:{GREY};text-transform:uppercase;letter-spacing:.5px;">Ventas totales del grupo (USD)</div>'
                   f'<div style="font-size:27px;font-weight:700;color:{NAVY};margin-top:2px;">${g["real"]:,.0f}</div>'
                   f'<div style="font-size:12px;color:{GREY};margin-top:3px;">Presupuesto ${g["ppto"]:,.0f} · '
                   f'<span style="color:{gcol};font-weight:700;">Cumplimiento {pct(g.get("cumpl"))}</span> · '
                   f'Colombia convertida a tasa COP/USD {g["rate"]:,.0f}</div>'
                   f'</td></tr></table>')
    # resumen por país
    rows = ""
    for pais in ORDEN:
        d = P.get(pais)
        if not d:
            rows += (f'<tr><td style="padding:8px 10px;border-bottom:1px solid #eee;font-weight:600;">{pais}</td>'
                     f'<td colspan="5" style="padding:8px 10px;border-bottom:1px solid #eee;color:{RED};">No disponible — revisar conexión Odoo</td></tr>')
            continue
        cur = d.get("moneda") or ""; col = cumpl_color(d.get("cumpl_ytd"))
        varcol = GREEN if (d.get("var_ytd") or 0) >= 0 else RED
        rows += (f'<tr><td style="padding:8px 10px;border-bottom:1px solid #eee;font-weight:600;">{pais}</td>'
                 f'<td style="padding:8px 10px;border-bottom:1px solid #eee;text-align:right;">{money(d.get("ytd_real"),cur)}</td>'
                 f'<td style="padding:8px 10px;border-bottom:1px solid #eee;text-align:right;color:{GREY};">{money(d.get("ppto_ytd"),cur)}</td>'
                 f'<td style="padding:8px 10px;border-bottom:1px solid #eee;text-align:right;font-weight:700;color:{col};">{pct(d.get("cumpl_ytd"))}</td>'
                 f'<td style="padding:8px 10px;border-bottom:1px solid #eee;text-align:right;color:{varcol};">{money(d.get("var_ytd"),cur)}</td>'
                 f'<td style="padding:8px 10px;border-bottom:1px solid #eee;text-align:right;color:{GREY};">{pct(d.get("avance_anual"))}</td></tr>')
    # canales Ecuador
    ec = P.get("Ecuador", {}); ec_rows = ""
    for c_ in ["RETAIL","DIGITAL","DIRECTO","ESPECIAL","MARKETPLACE","INTERCOMPANIA","SIN CANAL"]:
        cd = (ec.get("canales") or {}).get(c_)
        if not cd: continue
        col = cumpl_color(cd.get("cumpl_ytd"))
        ec_rows += (f'<tr><td style="padding:6px 10px;border-bottom:1px solid #eee;">{c_}</td>'
                    f'<td style="padding:6px 10px;border-bottom:1px solid #eee;text-align:right;">{money(cd["ytd_real"],"USD")}</td>'
                    f'<td style="padding:6px 10px;border-bottom:1px solid #eee;text-align:right;color:{GREY};">{money(cd["ppto_ytd"],"USD")}</td>'
                    f'<td style="padding:6px 10px;border-bottom:1px solid #eee;text-align:right;font-weight:700;color:{col};">{pct(cd.get("cumpl_ytd"))}</td></tr>')
    ec_block = ""
    if ec_rows:
        ec_block = (f'<h3 style="color:{NAVY};margin:22px 0 8px;">Ecuador — por canal (YTD)</h3>'
                    f'<table style="width:100%;border-collapse:collapse;font-size:13px;border:1px solid #eee;">'
                    f'<tr style="background:{NAVY};color:#fff;"><th style="padding:7px 10px;text-align:left;">Canal</th>'
                    f'<th style="padding:7px 10px;text-align:right;">Real</th><th style="padding:7px 10px;text-align:right;">Ppto</th>'
                    f'<th style="padding:7px 10px;text-align:right;">Cumpl%</th></tr>{ec_rows}</table>')
    ap_html = "".join(f'<li style="margin:6px 0;line-height:1.45;">{a}</li>' for a in apreciaciones(est))

    return f"""<div style="font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;max-width:720px;margin:auto;color:#222;">
  <div style="background:{NAVY};color:#fff;padding:16px 20px;border-radius:8px 8px 0 0;">
    <div style="font-size:18px;font-weight:700;">Estado del Presupuesto Comercial — Grupo VICOMER</div>
    <div style="font-size:12px;opacity:.85;margin-top:2px;">Semana del {datetime.date.today():%d/%m/%Y} · YTD a {mes} {est['anio']} · Cifras netas SIN IVA</div>
  </div>
  {g_block}
  <h3 style="color:{NAVY};margin:22px 0 8px;">Por país (moneda local)</h3>
  <table style="width:100%;border-collapse:collapse;font-size:13px;border:1px solid #eee;">
    <tr style="background:#f4f6fb;"><th style="padding:8px 10px;text-align:left;">País</th>
      <th style="padding:8px 10px;text-align:right;">Real YTD</th><th style="padding:8px 10px;text-align:right;">Ppto YTD</th>
      <th style="padding:8px 10px;text-align:right;">Cumpl%</th><th style="padding:8px 10px;text-align:right;">Variación</th>
      <th style="padding:8px 10px;text-align:right;">Avance año</th></tr>
    {rows}
  </table>
  {ec_block}
  <h3 style="color:{NAVY};margin:22px 0 8px;">Apreciaciones</h3>
  <ul style="font-size:13px;padding-left:18px;margin:0;">{ap_html}</ul>
  <p style="font-size:11px;color:{GREY};margin-top:22px;border-top:1px solid #eee;padding-top:10px;">
    Informe generado automáticamente el {est['generado']}. Fuente: {', '.join(f"{p} = {d.get('fuente', '?')}" for p, d in est.get('paises', {}).items() if not p.startswith('_')) or 'Odoo'}.
    Cifras netas sin IVA; cada país en su moneda (no se suman). Se adjunta el detalle en Excel.
  </p>
</div>"""

def build_text(est):
    mes = est["meses"][est["mes_cierre"]-1]; P = est["paises"]
    out = ["ESTADO DEL PRESUPUESTO COMERCIAL — GRUPO VICOMER (sin IVA)", f"YTD a {mes} {est['anio']}", ""]
    g = est.get("global_usd") or {}
    if g.get("real") is not None:
        out += [f"TOTAL GRUPO (USD): {money(g['real'],'USD')} vs ppto {money(g['ppto'],'USD')} = {pct(g.get('cumpl'))}"
                f"  (Colombia a tasa COP/USD {g['rate']:,.0f})", ""]
    out.append("Por país (moneda local):")
    for pais in ORDEN:
        d = P.get(pais)
        if not d:
            out.append(f"  {pais}: NO DISPONIBLE — revisar conexión Odoo"); continue
        out.append(f"  {pais}: real {money(d.get('ytd_real'),d.get('moneda'))} / ppto {money(d.get('ppto_ytd'),d.get('moneda'))} = {pct(d.get('cumpl_ytd'))}")
    out += ["", "Apreciaciones:"]
    for a in apreciaciones(est):
        out.append("  - " + re.sub("<[^>]+>", "", a).replace("&lt;", "<").replace("&gt;", ">"))
    return "\n".join(out)

# ------------------------------------------------------------------ envío
def attach(msg, path):
    path = Path(path)
    if not path.exists():
        PE.log(f"[WARN] adjunto no encontrado: {path}"); return
    ctype, _ = mimetypes.guess_type(str(path))
    maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
    msg.add_attachment(path.read_bytes(), maintype=maintype, subtype=subtype, filename=path.name)

def main():
    est = get_estado()
    P = est["paises"]
    def cp(pais):
        d = P.get(pais) or {}; return pct(d.get("cumpl_ytd"))
    g = est.get("global_usd") or {}
    gtxt = f"Global ${g['real']:,.0f} ({pct(g.get('cumpl'))}) · " if g.get("real") is not None else ""
    subj = (f"Presupuesto Grupo VICOMER — Sem {datetime.date.today():%d/%m} · "
            f"{gtxt}EC {cp('Ecuador')} · CO {cp('Colombia')} · CR {cp('Costa Rica')}")
    msg = EmailMessage()
    msg["Subject"] = subj; msg["From"] = MAIL_FROM; msg["To"] = ", ".join(MAIL_TO)
    if MAIL_CC: msg["Cc"] = ", ".join(MAIL_CC)
    msg.set_content(build_text(est))
    msg.add_alternative(build_html(est), subtype="html")
    attach(msg, CONSOLIDADO)

    if DRYRUN:
        outp = PE.OUT_DIR / "preview_correo.html"; PE.OUT_DIR.mkdir(parents=True, exist_ok=True)
        outp.write_text(build_html(est), encoding="utf-8")
        PE.log(f"[DRYRUN] no se envía. Asunto: {subj}")
        PE.log(f"[DRYRUN] Para={MAIL_TO} CC={MAIL_CC} From={MAIL_FROM} adjuntos={[p.get_filename() for p in msg.iter_attachments()]}")
        PE.log(f"[DRYRUN] preview -> {outp}")
        return
    pwd = get_smtp_password(); recipients = MAIL_TO + MAIL_CC
    PE.log(f"Enviando a {recipients} desde {MAIL_FROM} vía {SMTP_HOST}:{SMTP_PORT} ...")
    ctx = ssl.create_default_context()
    if SMTP_PORT == 465:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx, timeout=60) as s:
            s.login(SMTP_USER, pwd); s.send_message(msg, to_addrs=recipients)
    else:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=60) as s:
            s.starttls(context=ctx); s.login(SMTP_USER, pwd); s.send_message(msg, to_addrs=recipients)
    PE.log("[OK] correo semanal enviado.")

if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        import traceback; PE.log("[ERROR] correo:\n" + traceback.format_exc()); sys.exit(1)
