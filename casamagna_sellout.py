#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
casamagna_sellout.py
====================
Extrae el SELL OUT de Casa Magna desde el correo (Gmail vía IMAP): los reportes
semanales de NetSuite  ("CASA MAGNA S.A.S. :: VENTAS SEMANA ANTERIOR",
remitente system@sent-via.netsuite.com), cuyo adjunto searchresults.xls es en
realidad XML (SpreadsheetML).

Escribe:
    CasaMagna/sellout_casamagna.tsv   (fecha, marca, plaza, almacen, sku, descripcion,
                                       cantidad, total_iva, costo_total, margen, rep)
    CasaMagna/sellout_semanas.json    (lista de lunes reportados, incl. semanas en 0)

La 'fecha' de cada línea = fecha del correo (lunes de la semana reportada), igual
que usa el dashboard.

USO:
    python3 casamagna_sellout.py           # baja e indexa todo el histórico disponible
    python3 casamagna_sellout.py test      # autoprueba offline del parser XML

Credencial: App Password de Google de la cuenta jmvidal@v-comer.com
(apppass_file en casamagna_config.json), chmod 600.
"""
import sys, re, json, imaplib, email, datetime
from email.utils import parsedate_to_datetime

from casamagna_common import load_config, read_secret, out_dir

COLS = ["fecha", "marca", "plaza", "almacen", "sku", "descripcion",
        "cantidad", "total_iva", "costo_total", "margen", "rep"]


def parse_spreadsheetml(txt):
    """Devuelve lista de filas (cada fila = lista de celdas de texto). Solo filas de datos."""
    rows = []
    for chunk in re.split(r"<Row\b", txt)[1:]:
        cells = [re.sub(r"&amp;", "&", re.sub(r"&lt;", "<", re.sub(r"&gt;", ">",
                 re.sub(r"&#39;", "'", re.sub(r"&quot;", '"', m.group(1)))))).strip()
                 for m in re.finditer(r"<Data[^>]*>([\s\S]*?)</Data>", chunk)]
        if cells:
            rows.append(cells)
    return rows


def rows_from_xls(txt, week):
    """De un XML de NetSuite saca las líneas de venta con la fecha=semana (lunes del correo).
       Orden NetSuite: FECHA,MARCA,PLAZA,ALMACEN,UBICACION,ARTICULO,DESCRIPCION,CANTIDAD,
       PRECIO_UNIT,SUBTOTAL,TOTAL_IVA,COSTO_UNIT,COSTO_TOTAL,MARGEN,REP."""
    out = []
    for r in parse_spreadsheetml(txt):
        if not r or not re.match(r"^20\d\d-", r[0] or ""):   # salta cabecera/pie
            continue
        g = lambda i: r[i] if i < len(r) else ""
        out.append([week, g(1), g(2), g(3), g(5), g(6), g(7), g(10), g(12), g(13), g(14)])
    return out


def _decode(part):
    payload = part.get_payload(decode=True) or b""
    for enc in ("utf-8", "latin-1"):
        try:
            return payload.decode(enc)
        except Exception:
            continue
    return payload.decode("utf-8", "ignore")


def fetch_sellout():
    cfg = load_config()
    g = cfg["gmail"]
    pwd = read_secret(g["apppass_file"]).replace(" ", "")
    if not pwd:
        sys.exit(f"ERROR: falta App Password de Gmail en {g['apppass_file']} (chmod 600).")

    M = imaplib.IMAP4_SSL(g["imap_host"], g.get("imap_port", 993))
    M.login(g["user"], pwd)
    M.select('"[Gmail]/All Mail"' if _has_all_mail(M) else "INBOX")
    # Gmail: búsqueda cruda por remitente + asunto
    q = f'from:{g["remitente"]} subject:("{g["asunto"]}")'
    typ, data = M.search(None, "X-GM-RAW", q)
    ids = data[0].split() if data and data[0] else []

    all_rows, weeks = [], set()
    for num in ids:
        typ, msgdata = M.fetch(num, "(RFC822)")
        if typ != "OK" or not msgdata or not msgdata[0]:
            continue
        msg = email.message_from_bytes(msgdata[0][1])
        try:
            week = parsedate_to_datetime(msg["Date"]).date().isoformat()
        except Exception:
            continue
        weeks.add(week)
        for part in msg.walk():
            fn = (part.get_filename() or "").lower()
            ctype = (part.get_content_type() or "").lower()
            if fn.endswith(".xls") or "excel" in ctype or "spreadsheet" in ctype:
                txt = _decode(part)
                if "<Row" in txt or "<row" in txt.lower():
                    all_rows.extend(rows_from_xls(txt, week))
    M.logout()

    d = out_dir(cfg)
    tsv = d / "sellout_casamagna.tsv"
    with tsv.open("w", encoding="utf-8") as f:
        f.write("\t".join(COLS) + "\n")
        for r in all_rows:
            f.write("\t".join(str(x).replace("\t", " ").replace("\n", " ") for x in r) + "\n")
    (d / "sellout_semanas.json").write_text(
        json.dumps(sorted(weeks), ensure_ascii=False), encoding="utf-8")
    print(f"[OK] sell out: {len(all_rows)} líneas en {len(weeks)} semanas -> {tsv}")
    return all_rows, sorted(weeks)


def _has_all_mail(M):
    try:
        typ, boxes = M.list()
        return any(b'\\All' in b or b"[Gmail]/All Mail" in b for b in (boxes or []))
    except Exception:
        return False


SAMPLE_XML = """<?xml version="1.0"?><Workbook><Worksheet><Table>
<Row><Cell><Data>FECHA</Data></Cell><Cell><Data>MARCA</Data></Cell><Cell><Data>PLAZA</Data></Cell><Cell><Data>ALMACEN</Data></Cell><Cell><Data>UBICACION</Data></Cell><Cell><Data>ARTICULO</Data></Cell><Cell><Data>DESCRIPCION</Data></Cell><Cell><Data>CANTIDAD</Data></Cell><Cell><Data>PRECIO</Data></Cell><Cell><Data>SUBTOTAL</Data></Cell><Cell><Data>TOTAL</Data></Cell><Cell><Data>CU</Data></Cell><Cell><Data>CT</Data></Cell><Cell><Data>MARGEN</Data></Cell><Cell><Data>REP</Data></Cell></Row>
<Row><Cell><Data>2026-06-25T00:00:00</Data></Cell><Cell><Data>THOR</Data></Cell><Cell><Data>MEDELLIN</Data></Cell><Cell><Data>OVIEDO</Data></Cell><Cell><Data>BOD</Data></Cell><Cell><Data>TEW30ES</Data></Cell><Cell><Data>HORNO 30"</Data></Cell><Cell><Data>1</Data></Cell><Cell><Data>100</Data></Cell><Cell><Data>100</Data></Cell><Cell><Data>119</Data></Cell><Cell><Data>70</Data></Cell><Cell><Data>70</Data></Cell><Cell><Data>0.3</Data></Cell><Cell><Data>IVAN M</Data></Cell></Row>
</Table></Worksheet></Workbook>"""


def _selftest():
    rows = rows_from_xls(SAMPLE_XML, "2026-06-29")
    assert len(rows) == 1, rows
    r = rows[0]
    assert r == ["2026-06-29", "THOR", "MEDELLIN", "OVIEDO", "TEW30ES", 'HORNO 30"',
                 "1", "119", "70", "0.3", "IVAN M"], r
    print("SELFTEST OK: parser SpreadsheetML mapea columnas y usa la semana del correo.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        _selftest()
    else:
        fetch_sellout()
