#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pagos_correo.py
===============
Envía los correos del Comité de Pagos Semanal a partir de los JSON que Claude
deposita en Pagos/salida/ (bajados de Google Drive tras la aprobación en el artefacto):

  orden_pago_*.json            -> correo a jmvidal@v-comer.com solicitando autorizar en banco
                                  (adjunta el JSON y, si existe, el archivo banco_* de la semana)
  solicitud_comprobacion_*.json-> un correo por departamento a su responsable (CC jmvidal)

Tras enviar, mueve el JSON a Pagos/enviados/.
SMTP: mismos credenciales de correo_config.json (smtp_user / app_password).

Prueba sin enviar:  PAGOS_MAIL_DRYRUN=1 python3 pagos_correo.py
Se dispara automáticamente por LaunchAgent (WatchPaths en Pagos/salida).
"""
import os, sys, ssl, json, smtplib, datetime, shutil
from pathlib import Path
from email.message import EmailMessage

PROJ = Path(__file__).resolve().parent
SALIDA = PROJ / "Pagos" / "salida"
ENVIADOS = PROJ / "Pagos" / "enviados"
DRYRUN = os.environ.get("PAGOS_MAIL_DRYRUN") == "1"

NAVY = "#1F3864"; GREEN = "#2E7D32"; VIOLET = "#5b4b9e"; GREY = "#595959"

# ------------------------------------------------------------------ SMTP
def _cfg():
    for p in (Path.home() / ".perseo_correo.json", PROJ / "correo_config.json"):
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
    return {}

CFG = _cfg()
SMTP_USER = CFG.get("smtp_user") or "jmvidal@v-comer.com"
MAIL_FROM = CFG.get("from") or SMTP_USER
SMTP_HOST = CFG.get("smtp_host", "smtp.gmail.com")
SMTP_PORT = int(CFG.get("smtp_port", 465))
JM = "jmvidal@v-comer.com"

def smtp_pass():
    p = CFG.get("app_password") or os.environ.get("SMTP_APP_PASSWORD")
    if not p:
        f = Path.home() / ".perseo_smtp"
        if f.exists():
            p = f.read_text(encoding="utf-8")
    if not p:
        sys.exit("ERROR: sin contraseña SMTP")
    return p.replace(" ", "").strip()

def enviar(msg):
    if DRYRUN:
        print(f"  [DRYRUN] {msg['Subject']} -> {msg['To']} (cc {msg.get('Cc','')})")
        return
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx) as s:
        s.login(SMTP_USER, smtp_pass())
        s.send_message(msg)
    print(f"  Enviado: {msg['Subject']} -> {msg['To']}")

# ------------------------------------------------------------------ formato
def fmt(m, cur):
    try:
        if cur in ("COP", "CRC"):
            return f"{cur} {m:,.0f}"
        return f"{cur} {m:,.2f}"
    except Exception:
        return f"{cur} {m}"

def tabla(headers, rows, total_row=None):
    th = "".join(f'<th style="text-align:left;padding:6px 10px;background:{NAVY};color:#fff;font-size:12px;">{h}</th>' for h in headers)
    trs = ""
    for r in rows:
        tds = "".join(f'<td style="padding:6px 10px;border-bottom:1px solid #e3e6ea;font-size:13px;">{c}</td>' for c in r)
        trs += f"<tr>{tds}</tr>"
    if total_row:
        tds = "".join(f'<td style="padding:6px 10px;font-weight:bold;font-size:13px;">{c}</td>' for c in total_row)
        trs += f'<tr style="background:#f2f5f8;">{tds}</tr>'
    return f'<table style="border-collapse:collapse;width:100%;margin:8px 0 18px;">{"<tr>" + th + "</tr>"}{trs}</table>'

# ------------------------------------------------------------------ orden de pago
def correo_orden(doc, jsonfile):
    semana = doc.get("semana", "")
    html = [f'<div style="font-family:Arial,sans-serif;max-width:760px;">'
            f'<h2 style="color:{NAVY};">Orden de Pago Semanal — Grupo VICOMER</h2>'
            f'<p style="color:{GREY};font-size:13px;">Semana {semana} · Generada {doc.get("generado","")[:16].replace("T"," ")}</p>'
            f'<p style="font-size:14px;">Se solicita <b>autorizar en el banco</b> los siguientes pagos aprobados por el comité:</p>']
    for p in doc.get("paises", []):
        rows = [[f'{g["proveedor"]}{" 🧾" if g.get("comprobacion_solicitada") else ""}',
                 g.get("factura", ""), g.get("departamento", ""), g.get("vence", ""),
                 fmt(g.get("monto_pagar", g.get("monto", 0)), p.get("moneda", "")) ]
                for g in p.get("pagos", [])]
        html.append(f'<h3 style="color:{NAVY};font-size:15px;">{p.get("pais","")} ({p.get("moneda","")})</h3>')
        html.append(tabla(["Proveedor", "Factura", "Depto.", "Vence", "Valor"], rows,
                          ["TOTAL " + p.get("pais", ""), "", "", "", fmt(p.get("total", 0), p.get("moneda", ""))]))
    html.append(f'<p style="font-size:12px;color:{GREY};">🧾 = comprobación solicitada al departamento. '
                f'Documento generado por el Comité de Pagos (artefacto Cowork) y enviado automáticamente.</p></div>')

    msg = EmailMessage()
    msg["Subject"] = f"🏦 ORDEN DE PAGO Semana {semana} — autorizar en banco"
    msg["From"] = MAIL_FROM
    msg["To"] = doc.get("destinatario", JM)
    msg.set_content("Orden de pago semanal. Ver versión HTML.")
    msg.add_alternative("".join(html), subtype="html")
    msg.add_attachment(jsonfile.read_bytes(), maintype="application", subtype="json",
                       filename=jsonfile.name)
    # Adjuntar archivo de banco de la misma semana si existe (carga masiva Banco Guayaquil)
    for bf in sorted(SALIDA.glob(f"banco_*{semana}*")):
        msg.add_attachment(bf.read_bytes(), maintype="application", subtype="octet-stream",
                           filename=bf.name)
        print(f"  Adjunto banco: {bf.name}")
    enviar(msg)

# ------------------------------------------------------------------ comprobaciones
def correo_comprobaciones(doc):
    semana = doc.get("semana", "")
    for dep in doc.get("departamentos", []):
        r = dep.get("responsable") or {}
        email = r.get("email")
        nombre = r.get("nombre") or dep.get("departamento", "")
        if not email:
            print(f"  AVISO: {dep.get('departamento')} sin responsable — no se envía")
            continue
        rows = [[i.get("pais", ""), i.get("proveedor", ""), i.get("factura", ""),
                 i.get("vence", ""), fmt(i.get("monto", 0), i.get("moneda", ""))]
                for i in dep.get("items", [])]
        tot = " + ".join(fmt(v, c) for c, v in (dep.get("totales") or {}).items())
        html = (f'<div style="font-family:Arial,sans-serif;max-width:760px;">'
                f'<h2 style="color:{VIOLET};">Solicitud de Comprobación — {dep.get("departamento","")}</h2>'
                f'<p style="color:{GREY};font-size:13px;">Semana {semana} · Grupo VICOMER</p>'
                f'<p style="font-size:14px;">Hola {nombre.split()[0] if nombre else ""}, se solicita presentar la '
                f'<b>comprobación (soporte documental y justificación)</b> de los siguientes pagos '
                f'antes del cierre de la próxima semana:</p>'
                + tabla(["País", "Proveedor", "Factura", "Vence", "Valor"], rows,
                        ["TOTAL", "", "", "", tot])
                + f'<p style="font-size:12px;color:{GREY};">Enviado automáticamente por el Comité de Pagos. '
                  f'Coordina: Juan Marcelo Vidal ({JM}).</p></div>')
        msg = EmailMessage()
        msg["Subject"] = f"🧾 Comprobación de pagos {dep.get('departamento','')} — Semana {semana}"
        msg["From"] = MAIL_FROM
        msg["To"] = email
        msg["Cc"] = JM
        msg.set_content("Solicitud de comprobación de pagos. Ver versión HTML.")
        msg.add_alternative(html, subtype="html")
        enviar(msg)

# ------------------------------------------------------------------ main
def main():
    SALIDA.mkdir(parents=True, exist_ok=True)
    ENVIADOS.mkdir(parents=True, exist_ok=True)
    pendientes = sorted(SALIDA.glob("*.json"))
    if not pendientes:
        print("Sin archivos pendientes en Pagos/salida/")
        return
    for f in pendientes:
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"AVISO: {f.name} no es JSON válido ({e}) — se omite")
            continue
        tipo = doc.get("tipo", "")
        print(f"Procesando {f.name} (tipo={tipo})")
        try:
            if tipo == "orden_pago_semanal":
                correo_orden(doc, f)
            elif tipo == "solicitud_comprobacion":
                correo_comprobaciones(doc)
            else:
                print(f"  Tipo desconocido — se omite")
                continue
            if not DRYRUN:
                stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                shutil.move(str(f), str(ENVIADOS / f"{stamp}_{f.name}"))
        except Exception as e:
            print(f"  ERROR enviando {f.name}: {e}")

if __name__ == "__main__":
    main()
