#!/usr/bin/env python3
"""
vix_banco.py — Movimientos bancarios de VIX (Banco Guayaquil …3043) → propuesta de conciliación.

NO escribe en Odoo. Produce una propuesta (JSON + MD) que revisa una persona.

Fuentes (adaptadores), en orden de preferencia:
  api_bg                  API corporativa de Banco Guayaquil. PENDIENTE: el banco no publica
                          portal de desarrolladores; confirmar con el oficial de cuenta si existe
                          servicio host-to-host / API de consulta de saldos y movimientos para
                          Banca Empresas, credenciales (certificado/OAuth) y si el dominio puede
                          agregarse a la lista de red permitida del environment.
  export_cash_management  Archivo de movimientos (Excel/CSV) descargado de Banca Empresas y
                          dejado en VIX/banco_entrada/ (bajado de Drive VIX_Contabilidad/banco/).

Uso:
    python3 VIX/vix_banco.py inspeccionar <archivo>     # muestra encabezados y 5 filas (para mapear el formato)
    python3 VIX/vix_banco.py proponer [<archivo>]        # normaliza + empareja con facturas/pagos → propuesta

El mapeo de columnas vive en vix_reglas.json → banco.formato_export. Mientras no se haya
mapeado con un archivo REAL, `proponer` se niega a correr (no adivina columnas de un extracto).
"""
import datetime as dt
import json
import sys
from pathlib import Path

from vix_odoo import AQUI, REGLAS, OdooVIX

ENTRADA = AQUI / "banco_entrada"
SALIDA = AQUI / "salida"


# ── Adaptadores ───────────────────────────────────────────────────────
class FuenteAPI_BG:
    """
    API de integraciones de Banco Guayaquil — servicio "Movimientos" (Consulta v1).

    Autenticación (portal de integraciones BG, verificado 2026-11-13):
      · OAuth2 client_credentials vía Entra ID.
      · mTLS: producción responde "Client certificate is missing" sin certificado de cliente.
    Token:
      dev  https://devintegrations.bancoguayaquil.com/dc001/std/secure/oauth2/v2.0/token
      prod https://integrations.bancoguayaquil.com/dc001/std/secure/oauth2/v2.0/token
    Variables (SOLO en el entorno, nunca en el repo):
      BG_ENV=dev|prod, BG_CLIENT_ID, BG_CLIENT_SECRET, BG_SCOPE,
      BG_CERT (ruta .pem del certificado de cliente), BG_CERT_KEY (ruta de la llave)
    El endpoint de movimientos, sus parámetros y la paginación se toman de la definición
    OpenAPI 3 del portal → vix_reglas.json → banco.api_bg. Mientras no esté cargada, se niega.

    DÓNDE CORRE: por el mTLS, en el Mac (conexión directa al banco). El proxy de la nube
    intercepta TLS y no puede presentar el certificado del cliente. El Mac deja los
    movimientos normalizados en Drive; la nube los consume con `proponer`.
    """
    TOKEN = {
        "dev": "https://devintegrations.bancoguayaquil.com/dc001/std/secure/oauth2/v2.0/token",
        "prod": "https://integrations.bancoguayaquil.com/dc001/std/secure/oauth2/v2.0/token",
    }

    def __init__(self, conf: dict):
        import os
        self.conf = conf or {}
        self.env = os.environ.get("BG_ENV", "dev")
        faltan = [v for v in ("BG_CLIENT_ID", "BG_CLIENT_SECRET", "BG_SCOPE", "BG_CERT", "BG_CERT_KEY")
                  if not os.environ.get(v)]
        if faltan:
            sys.exit(f"API BG: faltan variables {', '.join(faltan)} (en el entorno, nunca en el repo).")
        if not self.conf.get("endpoint_movimientos"):
            sys.exit("API BG: falta banco.api_bg.endpoint_movimientos (cargar la definición OpenAPI 3 del portal).")
        self._env = os.environ

    def _ssl(self):
        import ssl
        ctx = ssl.create_default_context()
        ctx.load_cert_chain(self._env["BG_CERT"], self._env["BG_CERT_KEY"])
        return ctx

    def _post_form(self, url, data):
        import urllib.parse, urllib.request
        req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(),
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, context=self._ssl(), timeout=30) as r:
            return json.loads(r.read())

    def token(self):
        r = self._post_form(self.TOKEN[self.env], {
            "client_id": self._env["BG_CLIENT_ID"], "client_secret": self._env["BG_CLIENT_SECRET"],
            "scope": self._env["BG_SCOPE"], "grant_type": "client_credentials"})
        return r["access_token"]

    def movimientos(self, desde, hasta):
        """Paginación y nombres de campos: se completan con la definición OpenAPI (banco.api_bg)."""
        import urllib.parse, urllib.request
        c, tok, out, pag = self.conf, self.token(), [], 1
        while True:
            q = {c["param_desde"]: desde, c["param_hasta"]: hasta, c["param_cuenta"]: self._env["BG_CUENTA"],
                 c.get("param_pagina", "page"): pag}
            url = f"{c['base_url'][self.env]}{c['endpoint_movimientos']}?{urllib.parse.urlencode(q)}"
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}", "Accept": "application/json"})
            with urllib.request.urlopen(req, context=self._ssl(), timeout=60) as r:
                data = json.loads(r.read())
            items = data
            for k in c["ruta_items"].split("."):
                items = items[k] if k else items
            m = c["campos"]
            for it in items:
                monto = _num(it[m["monto"]])
                es_debito = str(it.get(m.get("tipo", ""), "")).upper() in c.get("valores_debito", ["D", "DEBITO"])
                out.append({"fecha": str(it[m["fecha"]])[:10], "descripcion": str(it.get(m["descripcion"], "")),
                            "referencia": str(it.get(m.get("referencia", ""), "")),
                            "debito": abs(monto) if es_debito or monto < 0 else 0.0,
                            "credito": 0.0 if es_debito or monto < 0 else abs(monto),
                            "saldo": _num(it[m["saldo"]]) if m.get("saldo") in it else None})
            if not items or len(items) < c.get("tam_pagina", 100):
                return out
            pag += 1


def _leer_tabla(ruta: Path):
    suf = ruta.suffix.lower()
    if suf in (".csv", ".txt"):
        import csv
        txt = ruta.read_text(encoding="utf-8-sig", errors="replace")
        dial = csv.Sniffer().sniff(txt[:4000], delimiters=",;\t|")
        return [r for r in csv.reader(txt.splitlines(), dial)]
    if suf in (".xlsx", ".xlsm", ".xls"):
        import openpyxl
        ws = openpyxl.load_workbook(ruta, read_only=True, data_only=True).active
        return [[c for c in fila] for fila in ws.iter_rows(values_only=True)]
    sys.exit(f"Formato no soportado: {suf} (usa .xlsx o .csv). Los PDF de estado de cuenta se procesan aparte.")


def _num(v):
    if v in (None, ""):
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("$", "").replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(",", "") if s.rfind(".") > s.rfind(",") else s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    return float(s or 0)


def _fecha(v, fmt):
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    return dt.datetime.strptime(str(v).strip(), fmt).date()


class FuenteExport:
    def __init__(self, ruta: Path, formato: dict):
        self.ruta, self.f = ruta, formato

    def movimientos(self):
        filas = _leer_tabla(self.ruta)
        h = self.f["fila_encabezado"]
        enc = [str(c or "").strip() for c in filas[h]]
        col = {k: enc.index(v) for k, v in self.f["columnas"].items() if v}
        out = []
        for fila in filas[h + 1:]:
            if not fila or all(c in (None, "") for c in fila):
                continue
            try:
                f = _fecha(fila[col["fecha"]], self.f["formato_fecha"])
            except (ValueError, TypeError):
                continue  # filas de totales / pie
            if "monto" in col:  # una sola columna con signo
                m = _num(fila[col["monto"]])
                deb, cre = (-m, 0.0) if m < 0 else (0.0, m)
            else:
                deb, cre = abs(_num(fila[col["debito"]])), abs(_num(fila[col["credito"]]))
            out.append({
                "fecha": f.isoformat(),
                "descripcion": str(fila[col["descripcion"]] or "").strip(),
                "referencia": str(fila[col["referencia"]] or "").strip() if "referencia" in col else "",
                "debito": round(deb, 2), "credito": round(cre, 2),
                "saldo": round(_num(fila[col["saldo"]]), 2) if "saldo" in col else None,
            })
        return out


# ── Controles y emparejamiento ────────────────────────────────────────
def control_saldos(movs, tol):
    """Saldo_n = saldo_{n-1} + crédito - débito. Devuelve las rupturas (no corrige)."""
    rupt = []
    con_saldo = [m for m in movs if m["saldo"] is not None]
    for a, b in zip(con_saldo, con_saldo[1:]):
        esperado = round(a["saldo"] + b["credito"] - b["debito"], 2)
        if abs(esperado - b["saldo"]) > tol:
            rupt.append({"fecha": b["fecha"], "esperado": esperado, "extracto": b["saldo"]})
    return rupt


def emparejar(movs, od, reg):
    """Créditos ↔ facturas abiertas de VIX (monto exacto o monto neto de retenciones típicas)."""
    tol = reg["tolerancias"]["conciliacion_usd"]
    abiertas = od.sr("account.move", [["move_type", "=", "out_invoice"], ["state", "=", "posted"],
                                      ["payment_state", "not in", ["paid", "in_payment", "reversed"]]],
                     ["name", "date", "partner_id", "amount_total", "amount_untaxed", "amount_tax", "amount_residual"])
    usadas, prop = set(), []
    for m in movs:
        if m["credito"] <= 0:
            prop.append({**m, "propuesta": "egreso: requiere factura/comprobante de gasto", "confianza": "—"})
            continue
        mejor = None
        for f in abiertas:
            if f["id"] in usadas:
                continue
            if abs(f["amount_residual"] - m["credito"]) <= tol:
                mejor = (f, "monto exacto", "alta")
                break
            # neto de retenciones (IR % sobre base + IVA % sobre IVA): se informa, no se asume
            for ir in (0.0175, 0.02, 0.0275, 0.03):
                for riva in (0.0, 0.3, 0.7, 1.0):
                    neto = round(f["amount_total"] - f["amount_untaxed"] * ir - f["amount_tax"] * riva, 2)
                    if abs(neto - m["credito"]) <= tol:
                        mejor = (f, f"neto de retención IR {ir:.2%} + IVA {riva:.0%}", "media")
                        break
                if mejor:
                    break
            if mejor:
                break
        if mejor:
            f, regla, conf = mejor
            usadas.add(f["id"])
            prop.append({**m, "factura": f["name"], "cliente": f["partner_id"][1],
                         "propuesta": f"cobro de {f['name']} ({regla})", "confianza": conf})
        else:
            prop.append({**m, "propuesta": "ingreso sin factura identificada: revisar", "confianza": "baja"})
    return prop


def cmd_inspeccionar(ruta):
    filas = _leer_tabla(Path(ruta))
    print(f"{len(filas)} filas. Primeras 12 (para identificar encabezado y columnas):")
    for i, f in enumerate(filas[:12]):
        print(f"  [{i}] {f}")
    print("\nCon esto se completa vix_reglas.json → banco.formato_export "
          "(fila_encabezado, formato_fecha, columnas).")


def cmd_proponer(ruta=None):
    reg = REGLAS
    fmt = reg["banco"].get("formato_export")
    if not fmt:
        sys.exit("banco.formato_export no está mapeado. Primero: vix_banco.py inspeccionar <archivo real>.")
    archivos = [Path(ruta)] if ruta else sorted(p for p in ENTRADA.iterdir() if p.suffix.lower() in (".xlsx", ".csv", ".xls", ".txt"))
    if not archivos:
        sys.exit(f"No hay extractos en {ENTRADA}. Bájalos de Drive VIX_Contabilidad/banco/.")
    movs = []
    for a in archivos:
        movs += FuenteExport(a, fmt).movimientos()
    movs.sort(key=lambda m: m["fecha"])
    rupt = control_saldos(movs, reg["tolerancias"]["conciliacion_usd"])
    prop = emparejar(movs, OdooVIX(), reg)

    SALIDA.mkdir(exist_ok=True)
    hoy = dt.date.today().isoformat()
    (SALIDA / f"banco_propuesta_{hoy}.json").write_text(
        json.dumps({"archivos": [a.name for a in archivos], "rupturas_saldo": rupt, "movimientos": prop},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    tot_c = sum(m["credito"] for m in movs)
    tot_d = sum(m["debito"] for m in movs)
    lin = [f"# Propuesta de conciliación VIX — {hoy}",
           f"Extractos: {', '.join(a.name for a in archivos)} · {len(movs)} movimientos · "
           f"créditos {tot_c:,.2f} · débitos {tot_d:,.2f}",
           f"Rupturas de saldo: **{len(rupt)}**" + (" ⚠️ el extracto está incompleto o mal leído" if rupt else " ✔"),
           "", "| Fecha | Descripción | Débito | Crédito | Propuesta | Confianza |", "|---|---|---|---|---|---|"]
    for m in prop:
        lin.append(f"| {m['fecha']} | {m['descripcion'][:50]} | {m['debito']:,.2f} | {m['credito']:,.2f} "
                   f"| {m['propuesta']} | {m['confianza']} |")
    md = "\n".join(lin)
    (SALIDA / f"banco_propuesta_{hoy}.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "inspeccionar":
        cmd_inspeccionar(sys.argv[2])
    elif len(sys.argv) >= 2 and sys.argv[1] == "proponer":
        cmd_proponer(sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        print(__doc__)
