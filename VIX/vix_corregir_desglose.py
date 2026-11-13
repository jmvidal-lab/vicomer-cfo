#!/usr/bin/env python3
"""Corrige en facturas de proveedor BORRADOR de VIX el desglose IVA 15%/0% (líneas residuales de centavos).
    python3 VIX/vix_corregir_desglose.py   |   VIX_ESCRIBIR=1 python3 VIX/vix_corregir_desglose.py"""
import json, os
from vix_odoo import OdooVIX, AQUI, REGLAS
from vix_registrar import desglose_iva
ESC = os.environ.get("VIX_ESCRIBIR") == "1"
SAN = REGLAS["saneamiento"]
od = OdooVIX()
sri = {c["clave"]: c for c in json.loads((AQUI / "salida" / "compras_sri.json").read_text(encoding="utf-8"))}
bills = od.sr("account.move", [["move_type", "=", "in_invoice"], ["state", "=", "draft"], ["l10n_ec_authorization_number", "in", list(sri)]],
              ["id", "ref", "l10n_ec_authorization_number", "amount_total"])
for b in bills:
    c = sri[b["l10n_ec_authorization_number"]]
    ls = od.leer("account.move.line", "search_read", [["move_id", "=", b["id"]], ["display_type", "=", "product"]], fields=["id", "price_unit", "tax_ids"])
    g15 = [l for l in ls if SAN["iva15_compras"] in l["tax_ids"]]
    g0 = [l for l in ls if SAN["iva0_compras"] in l["tax_ids"]]
    gravada, cero = desglose_iva(c["base"], c["iva"])
    actual0 = sum(l["price_unit"] for l in g0)
    if abs(actual0 - cero) < 0.005 and abs(g15[0]["price_unit"] - gravada) < 0.005:
        continue
    cmds = [(1, g15[0]["id"], {"price_unit": gravada})] + [(2, l["id"]) for l in g0]
    if abs(cero) >= 0.005 and g0:
        cmds = [(1, g15[0]["id"], {"price_unit": gravada}), (1, g0[0]["id"], {"price_unit": cero})] + [(2, l["id"]) for l in g0[1:]]
    elif abs(cero) >= 0.005:
        acc = od.leer("account.move.line", "read", [g15[0]["id"]], fields=["account_id", "name"])[0]
        cmds = [(1, g15[0]["id"], {"price_unit": gravada}),
                (0, 0, {"name": acc["name"] + " (IVA 0%)", "quantity": 1, "price_unit": cero,
                        "account_id": acc["account_id"][0], "tax_ids": [(6, 0, [SAN["iva0_compras"]])]})]
    if ESC:
        od.escribir("account.move", "write", [b["id"]], {"invoice_line_ids": cmds})
        tot = od.leer("account.move", "read", [b["id"]], fields=["amount_total"])[0]["amount_total"]
        print(f"✔ {b['ref']}: 0% {actual0:+.2f} → {cero:.2f} · total Odoo {tot} vs SRI {c['total']} {'OK' if abs(tot-c['total'])<0.005 else 'DIFERENCIA'}")
    else:
        print(f"· {b['ref']}: línea 0% {actual0:+.2f} → {cero:.2f} (gravada {gravada})")
