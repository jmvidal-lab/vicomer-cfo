#!/usr/bin/env python3
"""
vix_banco.py — Movimientos bancarios de VIX (Banco Guayaquil …3043) → propuesta de conciliación.

NO escribe en Odoo. Produce una propuesta (JSON + MD) que revisa una persona.

Fuentes (adaptadores), en orden de preferencia:
  api_bg                  API "Movimientos" de Banco Guayaquil (OAuth2 + mTLS). Ver FuenteAPI_BG.
  export_cash_management  Archivo de movimientos (Excel/CSV) descargado de Banca Empresas y
                          dejado en VIX/banco_entrada/ (bajado de Drive VIX_Contabilidad/banco/).

Uso:
    python3 VIX/vix_banco.py api-token                         # (Mac) prueba credenciales BG
    python3 VIX/vix_banco.py api-bajar 2026-07-01 2026-11-13 [dir]   # (Mac) baja movimientos → JSON
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
    API "Movimientos" (Consulta v1) de Banco Guayaquil — cuenta corriente.
    Especificación: OpenAPI 3 del portal de integraciones BG (current-account-api-v1.json,
    Drive VIX/CONTABILIDAD, leída 2026-11-13).

      GET {base}/dc001/std/secure/current-account/v1/accounts/{accountId}/transactions
      Parámetros por HEADER: periodFrom, periodTo (yyyy-MM-dd, rango ≤ 360 días),
        filtersTransactionTypeIdentification=TT, pageMark=N (1ª) / S (siguientes),
        pagePointer y pageProgramName (los devuelve page.* de la respuesta anterior).
      Respuesta: serviceOutcome.code (0000 ok, 0006 sin movimientos), page.mark S/N,
        transactions[] con bookingDate, creditDebit CREDIT/DEBIT, amount.amountValue sin punto
        decimal + amount.decimalPointPosition, concept, document, reference1..3, accountBalance[].
      Auth: OAuth2 client_credentials (Entra ID) → Bearer. Producción exige además certificado
        de cliente (mTLS) — probado: "Client certificate is missing". Algunos productos APIM piden
        también Ocp-Apim-Subscription-Key (opcional aquí).

    Variables SOLO en el entorno del Mac (nunca en el repo):
      BG_ENV=dev|prod  BG_CLIENT_ID  BG_CLIENT_SECRET  BG_SCOPE  BG_CUENTA
      BG_CERT, BG_CERT_KEY (rutas .pem; obligatorias en prod)   BG_SUBSCRIPTION_KEY (opcional)
    """
    HOSTS = {"dev": "https://devintegrations.bancoguayaquil.com",
             "prod": "https://integrations.bancoguayaquil.com"}
    TOKEN_PATH = "/dc001/std/secure/oauth2/v2.0/token"
    MOV_PATH = "/dc001/std/secure/current-account/v1/accounts/{cuenta}/transactions"
    OK, SIN_MOV = "0000", "0006"
    ERRORES = {"9999": "error interno de comunicación", "8888": "error interno de comunicación",
               "4444": "formato de datos enviado inválido", "9993": "error en la aplicación (ClientID)",
               "9992": "cliente NO autorizado para consultar esta cuenta", "0992": "error desconocido"}

    def __init__(self):
        import os
        self.e = os.environ
        self.env = self.e.get("BG_ENV", "dev")
        if self.env not in self.HOSTS:
            sys.exit("BG_ENV debe ser dev o prod.")
        req = ["BG_CLIENT_ID", "BG_CLIENT_SECRET", "BG_SCOPE", "BG_CUENTA"]
        if self.env == "prod":
            req += ["BG_CERT", "BG_CERT_KEY"]
        faltan = [v for v in req if not self.e.get(v)]
        if faltan:
            sys.exit(f"API BG: faltan variables {', '.join(faltan)} (en ~/.bg/bg_vix.env, nunca en el repo).")

    def _ctx(self):
        import ssl
        ctx = ssl.create_default_context()
        if self.e.get("BG_CERT"):
            ctx.load_cert_chain(self.e["BG_CERT"], self.e["BG_CERT_KEY"])
        return ctx

    def _http(self, req):
        import urllib.error, urllib.request
        try:
            with urllib.request.urlopen(req, context=self._ctx(), timeout=60) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as ex:
            cuerpo = ex.read().decode(errors="replace")[:300]
            sys.exit(f"BG respondió HTTP {ex.code}: {cuerpo}")

    def token(self):
        import urllib.parse, urllib.request
        data = urllib.parse.urlencode({"client_id": self.e["BG_CLIENT_ID"], "client_secret": self.e["BG_CLIENT_SECRET"],
                                       "scope": self.e["BG_SCOPE"], "grant_type": "client_credentials"}).encode()
        r = self._http(urllib.request.Request(self.HOSTS[self.env] + self.TOKEN_PATH, data=data,
                                              headers={"Content-Type": "application/x-www-form-urlencoded"}))
        if "access_token" not in r:
            sys.exit(f"Token rechazado: {r.get('error')} {str(r.get('error_description', ''))[:200]}")
        return r["access_token"]

    @staticmethod
    def _monto(a):
        v = str(a.get("amountValue", "0")).strip() or "0"
        try:
            return round(int(v) / 10 ** int(a.get("decimalPointPosition", 2)), 2)
        except ValueError:
            return _num(v)

    def movimientos(self, desde, hasta):
        import urllib.request
        if (dt.date.fromisoformat(hasta) - dt.date.fromisoformat(desde)).days > 360:
            sys.exit("El banco admite rangos de hasta 360 días.")
        tok, url = self.token(), self.HOSTS[self.env] + self.MOV_PATH.format(cuenta=self.e["BG_CUENTA"])
        out, mark, pointer, prog = [], "N", "", ""
        for _ in range(500):  # tope de seguridad de páginas
            h = {"Content-Type": "application/json", "Authorization": f"Bearer {tok}",
                 "periodFrom": desde, "periodTo": hasta, "filtersTransactionTypeIdentification": "TT",
                 "pageMark": mark, "pagePointer": pointer, "pageProgramName": prog}
            if self.e.get("BG_SUBSCRIPTION_KEY"):
                h["Ocp-Apim-Subscription-Key"] = self.e["BG_SUBSCRIPTION_KEY"]
            r = self._http(urllib.request.Request(url, headers=h))
            cod = (r.get("serviceOutcome") or {}).get("code")
            if cod == self.SIN_MOV:
                break
            if cod != self.OK:
                sys.exit(f"BG serviceOutcome {cod}: {self.ERRORES.get(cod, (r.get('serviceOutcome') or {}).get('message'))}")
            for t in r.get("transactions") or []:
                m = self._monto(t.get("amount") or {})
                deb = t.get("creditDebit") == "DEBIT"
                saldo = next((self._monto(b.get("amount") or b) for b in t.get("accountBalance") or []
                              if str(b.get("type", "")).lower().startswith("avail")), None)
                out.append({"fecha": str(t.get("bookingDate") or t.get("valueDate"))[:10],
                            "descripcion": " ".join(x for x in [(t.get("transactionType") or {}).get("description", ""),
                                                                t.get("concept", "")] if x).strip(),
                            "referencia": " ".join(str(t.get(k) or "") for k in ("document", "reference1", "reference2", "reference3")).strip(),
                            "debito": m if deb else 0.0, "credito": 0.0 if deb else m, "saldo": saldo,
                            "id_banco": f"{t.get('document', '')}-{t.get('hostSequence') or t.get('sequence', '')}"})
            pg = r.get("page") or {}
            if pg.get("mark") != "S":
                break
            mark, pointer, prog = "S", str(pg.get("pointer", "")), str(pg.get("programName", ""))
        return out


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
                     ["name", "date", "partner_id", "amount_total", "amount_untaxed", "amount_tax", "amount_residual"],
                     order="date asc, id asc")  # FIFO: el cobro se propone contra la factura más antigua
    usadas, prop = set(), []
    for m in movs:
        if m["credito"] <= 0:
            prop.append({**m, "propuesta": "egreso: requiere factura/comprobante de gasto", "confianza": "—"})
            continue
        gemelas = [f["name"] for f in abiertas if f["id"] not in usadas
                   and abs(f["amount_residual"] - m["credito"]) <= tol]
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
            if len(gemelas) > 1:
                regla += f"; AMBIGUO: {len(gemelas)} facturas con el mismo monto ({', '.join(gemelas)}), se tomó la más antigua"
                conf = "media"
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
    archivos = [Path(ruta)] if ruta else sorted(p for p in ENTRADA.iterdir()
                                               if p.suffix.lower() in (".json", ".xlsx", ".csv", ".xls", ".txt"))
    if not archivos:
        sys.exit(f"No hay movimientos en {ENTRADA}. Bájalos de Drive VIX/CONTABILIDAD.")
    movs, vistos = [], set()
    for a in archivos:
        if a.suffix.lower() == ".json":
            lote = json.loads(a.read_text(encoding="utf-8"))["movimientos"]
        elif not fmt:
            sys.exit("banco.formato_export no está mapeado. Primero: vix_banco.py inspeccionar <archivo real>.")
        else:
            lote = FuenteExport(a, fmt).movimientos()
        for m in lote:  # archivos solapados no duplican movimientos
            k = m.get("id_banco") or (m["fecha"], m["descripcion"], m["debito"], m["credito"], m["saldo"])
            if k not in vistos:
                vistos.add(k); movs.append(m)
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


def cmd_api_token():
    FuenteAPI_BG().token()
    print("✔ Token obtenido: client_id, secret, scope (y certificado si aplica) son válidos.")


def cmd_api_bajar(desde, hasta, destino=None):
    """Corre en el Mac: baja movimientos y los deja normalizados (JSON) para la nube."""
    movs = FuenteAPI_BG().movimientos(desde, hasta)
    d = Path(destino) if destino else ENTRADA
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"bg_vix_movimientos_{desde}_{hasta}.json"
    f.write_text(json.dumps({"fuente": "api_bg", "desde": desde, "hasta": hasta, "movimientos": movs},
                            ensure_ascii=False, indent=2), encoding="utf-8")
    c = sum(m["credito"] for m in movs); dd = sum(m["debito"] for m in movs)
    print(f"✔ {len(movs)} movimientos · créditos {c:,.2f} · débitos {dd:,.2f} → {f}")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "api-token":
        cmd_api_token()
    elif len(sys.argv) >= 4 and sys.argv[1] == "api-bajar":
        cmd_api_bajar(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
    elif len(sys.argv) >= 3 and sys.argv[1] == "inspeccionar":
        cmd_inspeccionar(sys.argv[2])
    elif len(sys.argv) >= 2 and sys.argv[1] == "proponer":
        cmd_proponer(sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        print(__doc__)
