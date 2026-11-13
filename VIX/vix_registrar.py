#!/usr/bin/env python3
"""
vix_registrar.py — Registra en Odoo (VIX, cia 11) los BORRADORES del saneamiento jul–nov 2026.

    python3 VIX/vix_registrar.py                 # simulación: muestra lo que haría
    VIX_ESCRIBIR=1 python3 VIX/vix_registrar.py  # crea los borradores (requiere escritura.habilitada)

Qué crea (todo en estado BORRADOR; publica y concilia el contador):
  A. Facturas de proveedor desde el reporte SRI "Recibidos" (salida/compras_sri.json).
  B. Un asiento por movimiento bancario (extractos BG en banco_entrada/), contra la cuenta
     que corresponde según vix_reglas.json → saneamiento.
Idempotente: no duplica facturas (clave de acceso) ni asientos (ref "VIXBANCO:<id>").
Deja bitácora en VIX/bitacora/registro_<fecha>.json (ignorada por git: contiene datos).
"""
import datetime as dt
import json
import os
import sys
from pathlib import Path

from vix_odoo import AQUI, CIA, REGLAS, OdooVIX
from vix_banco import ENTRADA, FuenteExport

ESCRIBIR = os.environ.get("VIX_ESCRIBIR") == "1"
SAN = REGLAS["saneamiento"]
CTA = SAN["cuentas"]
LOG = []


def log(tipo, **kw):
    LOG.append({"tipo": tipo, **kw})
    print(f"  {'✔' if ESCRIBIR else '·'} {tipo}: " + ", ".join(f"{k}={v}" for k, v in kw.items() if k != "lineas"))


def _r2(x):
    from decimal import Decimal, ROUND_HALF_UP
    return float(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def desglose_iva(base, iva):
    """Base gravada 15% y base 0% de una factura del SRI.
    1) Si el 15% de toda la base (redondeo half-up, como Odoo) da exactamente el IVA → todo gravado.
    2) Si no, se separa: gravada = IVA/0.15 y el resto a 0%. Prima que el total cuadre al centavo con el SRI."""
    from decimal import Decimal
    if _r2(Decimal(str(base)) * Decimal("0.15")) == _r2(iva):
        return base, 0.0
    gravada = _r2(iva / 0.15)
    if _r2(Decimal(str(gravada)) * Decimal("0.15")) != _r2(iva):  # busca la base gravada cuyo 15% reproduzca el IVA exacto
        for d in (-0.01, 0.01, -0.02, 0.02):
            if _r2(Decimal(str(gravada + d)) * Decimal("0.15")) == _r2(iva):
                gravada = _r2(gravada + d); break
    return gravada, _r2(base - gravada)


class Reg:
    def __init__(self):
        self.od = OdooVIX()
        self.acc = {a["code"]: a["id"] for a in self.od.leer(
            "account.account", "search_read", [["company_ids", "in", [CIA]]], fields=["code"])}
        self.partners = {}

    def a(self, code):
        if code not in self.acc:
            sys.exit(f"Cuenta {code} no existe en VIX.")
        return self.acc[code]

    # ── terceros ───────────────────────────────────────────────────────
    def partner(self, ruc, nombre):
        if ruc in self.partners:
            return self.partners[ruc]
        r = self.od.leer("res.partner", "search_read", [["vat", "=", ruc]], fields=["id"], limit=1)
        if r:
            pid = r[0]["id"]
        elif ESCRIBIR:
            pid = self.od.escribir("res.partner", "create", {
                "name": nombre, "vat": ruc, "is_company": len(ruc) == 13 and ruc[2] in "69",
                "l10n_latam_identification_type_id": SAN["tipo_identificacion_ruc"], "country_id": SAN["pais_ec"]})
            log("proveedor creado", ruc=ruc, nombre=nombre, id=pid)
        else:
            pid = f"(nuevo {ruc})"
            log("proveedor a crear", ruc=ruc, nombre=nombre)
        self.partners[ruc] = pid
        return pid

    def cuenta_por_pagar(self, pid):
        if not isinstance(pid, int):
            return self.a(CTA["cxp_proveedores"])
        p = self.od.leer("res.partner", "read", [pid], fields=["property_account_payable_id"])[0]
        return p["property_account_payable_id"][0] if p["property_account_payable_id"] else self.a(CTA["cxp_proveedores"])

    # ── A. facturas de proveedor ──────────────────────────────────────
    def facturas(self):
        comp = json.loads((AQUI / "salida" / "compras_sri.json").read_text(encoding="utf-8"))
        existentes = {m["l10n_ec_authorization_number"] for m in self.od.sr(
            "account.move", [["move_type", "=", "in_invoice"]], ["l10n_ec_authorization_number"]) if m["l10n_ec_authorization_number"]}
        print(f"\nA. Facturas de proveedor ({len(comp)} en SRI, {len(existentes)} ya en Odoo)")
        for c in comp:
            if c["clave"] in existentes:
                log("factura ya existe", serie=c["serie"])
                continue
            pid = self.partner(c["ruc"], c["emisor"])
            cuenta = self.a(SAN["cuenta_gasto_por_clase"].get(c["clase"].split(":")[0].strip(), CTA["gasto_otros"]))
            gravada, cero = desglose_iva(c["base"], c["iva"])
            no_objeto = round(c["total"] - c["base"] - c["iva"], 2)  # propina/servicio 10%
            lineas = []
            desc = f"{c['emisor'][:40]} {c['serie']}"
            if gravada > 0:
                lineas.append({"name": desc, "quantity": 1, "price_unit": gravada, "account_id": cuenta, "tax_ids": [(6, 0, [SAN["iva15_compras"]])]})
            if abs(cero) >= 0.01:
                lineas.append({"name": desc + " (IVA 0%)", "quantity": 1, "price_unit": cero, "account_id": cuenta, "tax_ids": [(6, 0, [SAN["iva0_compras"]])]})
            if abs(no_objeto) >= 0.01:
                lineas.append({"name": desc + " (servicio/propina, no objeto IVA)", "quantity": 1, "price_unit": no_objeto, "account_id": cuenta, "tax_ids": [(6, 0, [SAN["iva_no_objeto"]])]})
            vals = {"move_type": "in_invoice", "journal_id": REGLAS["diarios"]["compras"], "partner_id": pid,
                    "invoice_date": c["fecha"], "date": c["fecha"],
                    "l10n_latam_document_type_id": SAN["doc_factura"], "l10n_latam_document_number": c["serie"],
                    "l10n_ec_authorization_number": c["clave"], "ref": c["serie"],
                    "narration": f"Registrado por Claude desde reporte SRI Recibidos. Clase: {c['clase']}. Sin retención (política VIX declarada por JMV 2026-11-13: VERIFICAR con contador).",
                    "invoice_line_ids": [(0, 0, l) for l in lineas]}
            if ESCRIBIR:
                mid = self.od.escribir("account.move", "create", vals)
                tot = self.od.leer("account.move", "read", [mid], fields=["amount_total"])[0]["amount_total"]
                ok = abs(tot - c["total"]) < 0.02
                log("factura borrador", serie=c["serie"], emisor=c["emisor"][:30], total_sri=c["total"], total_odoo=tot,
                    cuadra=ok, id=mid)
            else:
                log("factura a crear", serie=c["serie"], emisor=c["emisor"][:30], total=c["total"], clase=c["clase"])

    # ── B. asientos bancarios ─────────────────────────────────────────
    def banco(self):
        fmt = REGLAS["banco"]["formato_export"]
        movs, vistos = [], set()
        for f in sorted(ENTRADA.glob("*.txt")):
            for m in FuenteExport(f, fmt).movimientos():
                if m["id_banco"] not in vistos:
                    vistos.add(m["id_banco"]); movs.append(m)
        movs += SAN.get("movimientos_manuales", [])  # p.ej. pago de tarjeta posterior al extracto
        movs.sort(key=lambda m: m["fecha"])
        hechos = {m["ref"] for m in self.od.sr("account.move", [["ref", "=like", "VIXBANCO:%"]], ["ref"])}
        print(f"\nB. Asientos bancarios ({len(movs)} movimientos)")
        banco = self.a(CTA["banco"])
        for m in movs:
            ref = "VIXBANCO:" + m["id_banco"][:60]
            if ref in hechos:
                log("asiento ya existe", ref=ref)
                continue
            regla = self.regla(m)
            if not regla:
                log("SIN REGLA (se omite)", fecha=m["fecha"], desc=m["descripcion"], monto=m["debito"] or m["credito"])
                continue
            monto = m["credito"] or m["debito"]
            contra = []
            for c in regla["contrapartidas"]:
                pid = c.get("partner_id")
                cuenta = self.cuenta_por_pagar(pid) if c["cuenta"] == "CXP_PARTNER" else self.a(c["cuenta"])
                contra.append({"name": c["glosa"], "account_id": cuenta, "partner_id": pid,
                               "debit": c["monto"] if m["debito"] else 0.0, "credit": c["monto"] if m["credito"] else 0.0})
            dif = round(monto - sum(c["monto"] for c in regla["contrapartidas"]), 2)
            for c in regla.get("ajustes", []):  # p.ej. comisión del exterior: gasto adicional
                contra.append({"name": c["glosa"], "account_id": self.a(c["cuenta"]), "debit": c["monto"], "credit": 0.0})
            lineas = [{"name": m["descripcion"][:60], "account_id": banco,
                       "debit": m["credito"], "credit": m["debito"]}] + contra
            d = sum(l["debit"] for l in lineas); cr = sum(l["credit"] for l in lineas)
            if abs(d - cr) > 0.005:
                sys.exit(f"Asiento descuadrado {ref}: D {d} C {cr} (dif regla {dif})")
            vals = {"move_type": "entry", "journal_id": REGLAS["diarios"]["varios"], "date": m["fecha"], "ref": ref,
                    "narration": f"Movimiento BG …{REGLAS['banco']['cuenta_ultimos4']}: {m['descripcion']} | {m['referencia']}. {regla['nota']}",
                    "line_ids": [(0, 0, {k: v for k, v in l.items() if v is not None}) for l in lineas]}
            if ESCRIBIR:
                mid = self.od.escribir("account.move", "create", vals)
                log("asiento borrador", fecha=m["fecha"], monto=monto, concepto=regla["nota"][:60], id=mid)
            else:
                log("asiento a crear", fecha=m["fecha"], monto=monto, concepto=regla["nota"][:70])

    # ── C. consumos con tarjeta: cancelan la factura del proveedor contra la deuda con BG ──
    def tarjeta(self):
        tj = SAN["tarjeta"]
        hechos = {m["ref"] for m in self.od.sr("account.move", [["ref", "=like", "VIXTARJ:%"]], ["ref"])}
        comp = {c["serie"]: c for c in json.loads((AQUI / "salida" / "compras_sri.json").read_text(encoding="utf-8"))}
        bg = self.partner(SAN["ruc_banco_guayaquil"], "BANCO GUAYAQUIL S.A.")
        print(f"\nC. Consumos con tarjeta ({len(tj['consumos'])})")
        for c in tj["consumos"]:
            ref = f"VIXTARJ:{c['serie']}"
            if ref in hechos:
                log("consumo ya existe", ref=ref); continue
            sri = comp[c["serie"]]
            if abs(sri["total"] - c["monto"]) > 0.01:
                sys.exit(f"Consumo {c['serie']} {c['monto']} no cuadra con SRI {sri['total']}")
            prov = self.partner(sri["ruc"], sri["emisor"])
            vals = {"move_type": "entry", "journal_id": REGLAS["diarios"]["varios"], "date": c["fecha"], "ref": ref,
                    "narration": f"Pago con tarjeta Visa VIX …7722 de la factura {c['serie']} ({sri['emisor']}). Concilie contra la factura.",
                    "line_ids": [(0, 0, {"name": f"Pago con tarjeta {c['serie']}", "account_id": self.cuenta_por_pagar(prov), "partner_id": prov, "debit": c["monto"], "credit": 0.0}),
                                 (0, 0, {"name": "Tarjeta Visa VIX …7722", "account_id": self.a(CTA["tarjeta_credito"]), "partner_id": bg, "debit": 0.0, "credit": c["monto"]})]}
            if ESCRIBIR and isinstance(prov, int) and isinstance(bg, int):
                mid = self.od.escribir("account.move", "create", vals)
                log("consumo tarjeta borrador", serie=c["serie"], monto=c["monto"], id=mid)
            else:
                log("consumo tarjeta a crear", serie=c["serie"], monto=c["monto"], proveedor=sri["emisor"][:30])

    def regla(self, m):
        """Clasificación de cada movimiento: reglas explícitas, decididas por JMV el 2026-11-13."""
        d, monto, f = m["descripcion"].lower(), m["credito"] or m["debito"], m["fecha"]
        jmv, mrva, vic, vin = (SAN["partners"][k] for k in ("jmv", "mrva", "vicomer", "vintral"))
        bg = self.partner(SAN["ruc_banco_guayaquil"], "BANCO GUAYAQUIL S.A.")
        cxc_l, cxc_e = CTA["cxc_vicomer_actual"], CTA["cxc_vintral_actual"]
        # cobros
        cobros = SAN["cobros"]
        if m["credito"] and f in cobros and 0 <= cobros[f]["monto_factura"] - monto <= 60:
            c = cobros[f]
            r = {"nota": f"Cobro {c['factura']}", "contrapartidas": [
                {"cuenta": cxc_l if c["cliente"] == "vicomer" else (cxc_e if c["factura"][-1] != "6" else cxc_l),
                 "monto": c["monto_factura"], "glosa": f"Cobro {c['factura']}", "partner_id": vic if c["cliente"] == "vicomer" else vin}]}
            com = round(c["monto_factura"] - monto, 2)
            if com > 0:
                r["ajustes"] = [{"cuenta": CTA["comision_bancaria"], "monto": com, "glosa": "Comisión banco corresponsal del exterior"}]
                r["nota"] += f" (neto de comisión del exterior {com:.2f})"  # banco 2.454,73 + comisión = CxC 2.500
            return r if com >= 0 else None
        # préstamos del socio JMV
        if m["credito"] and ("vidal torres juan marcelo" in m["referencia"].lower() or f == "2026-09-11" and "efectivo" in d):
            return {"nota": "Préstamo de JMV a VIX" + (" (depósito en efectivo hecho por T. P. Salamea Q. por cuenta de JMV)" if "efectivo" in d else ""),
                    "contrapartidas": [{"cuenta": CTA["prestamo_socio"], "monto": monto, "glosa": "Préstamo JMV", "partner_id": jmv}]}
        if m["debito"] and f == "2026-11-13" and monto == 1000:
            return {"nota": "Devolución parcial de préstamo a JMV",
                    "contrapartidas": [{"cuenta": CTA["prestamo_socio"], "monto": monto, "glosa": "Devolución préstamo JMV", "partner_id": jmv}]}
        if m["debito"] and f == "2026-09-22" and monto == 1000:
            return {"nota": "POR IDENTIFICAR: pago a terceros sin sustento (consultar a JMV)",
                    "contrapartidas": [{"cuenta": CTA["por_identificar"], "monto": monto, "glosa": "Pago a terceros por identificar"}]}
        # honorarios socios
        hp = SAN["pagos_honorarios"]
        if m["debito"] and f in hp:
            return {"nota": f"Pago honorarios {hp[f]}",
                    "contrapartidas": [{"cuenta": "CXP_PARTNER", "monto": monto, "glosa": f"Pago {hp[f]}", "partner_id": jmv}]}
        # pago de tarjeta de crédito propia
        if m["debito"] and "tarjeta" in d:
            return {"nota": "Pago tarjeta de crédito VIX Visa …7722 (corte 28-oct)",
                    "contrapartidas": [{"cuenta": CTA["tarjeta_credito"], "monto": monto, "glosa": "Pago tarjeta BG", "partner_id": bg}]}
        # inversiones
        if m["debito"] and ("ahorro inversi" in d or "inversion p" in d or "inversión p" in d):
            return {"nota": "Traspaso a inversión propia (" + ("póliza" if "liza" in d else "cuenta ahorro inversión …3841") + ")",
                    "contrapartidas": [{"cuenta": CTA["inversiones"], "monto": monto, "glosa": "Inversión temporal"}]}
        # comisiones BG (se pagan contra sus facturas SRI)
        if m["debito"] and any(x in d for x in ("chequera", "token", "comis", "iva servicios")):
            return {"nota": "Comisión/servicio Banco Guayaquil (contra su factura SRI)",
                    "contrapartidas": [{"cuenta": "CXP_PARTNER", "monto": monto, "glosa": "Pago a Banco Guayaquil", "partner_id": bg}]}
        return None


def main():
    if ESCRIBIR and not REGLAS["escritura"]["habilitada"]:
        sys.exit("escritura.habilitada = false en vix_reglas.json")
    print(("ESCRITURA (borradores)" if ESCRIBIR else "SIMULACIÓN") + f" — VIX cia {CIA}")
    r = Reg()
    r.facturas()
    r.tarjeta()
    r.banco()
    (AQUI / "bitacora").mkdir(exist_ok=True)
    f = AQUI / "bitacora" / f"registro_{dt.datetime.now():%Y-%m-%d_%H%M}{'' if ESCRIBIR else '_simulacion'}.json"
    f.write_text(json.dumps(LOG, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"\nBitácora: {f}")


if __name__ == "__main__":
    main()
