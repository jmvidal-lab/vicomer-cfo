#!/usr/bin/env python3
"""
vix_ajuste_auditoria.py — Asientos de AJUSTE/RECLASIFICACIÓN de auditoría sobre asientos YA PUBLICADOS de VIX.
No reabre ni modifica el asiento original (preserva rastro): crea un asiento nuevo en BORRADOR que lo corrige.

    python3 VIX/vix_ajuste_auditoria.py                 # simulación
    VIX_ESCRIBIR=1 python3 VIX/vix_ajuste_auditoria.py  # crea los ajustes en borrador
Los ajustes se definen en vix_reglas.json → saneamiento.ajustes_auditoria. Idempotente (ref VIXAJUSTE:<n>).
"""
import os, sys
from vix_odoo import OdooVIX, CIA, REGLAS
ESC = os.environ.get("VIX_ESCRIBIR") == "1"
od = OdooVIX()
acc = lambda code: od.leer("account.account", "search_read", [["company_ids", "in", [CIA]], ["code", "=", code]], fields=["id"])[0]["id"]
hechos = {m["ref"] for m in od.sr("account.move", [["ref", "=like", "VIXAJUSTE:%"]], ["ref"])}
for a in REGLAS["saneamiento"].get("ajustes_auditoria", []):
    ref = f"VIXAJUSTE:{a['id']}"
    orig = od.sr("account.move", [["id", "=", a["asiento_original_id"]]], ["name", "state", "date"])[0]
    if ref in hechos:
        print(f"· {ref} ya existe"); continue
    if orig["state"] != "posted":
        print(f"· {orig['name']} ya no está publicado ({orig['state']}): corregir directo, no con ajuste"); continue
    lin = od.leer("account.move.line", "search_read", [["move_id", "=", a["asiento_original_id"]], ["account_id.code", "=", a["cuenta_origen"]]],
                  fields=["debit", "credit"])
    saldo = round(sum(l["debit"] - l["credit"] for l in lin), 2)
    if abs(saldo - a["monto"]) > 0.005:
        sys.exit(f"{ref}: el asiento original tiene {saldo} en {a['cuenta_origen']}, se esperaba {a['monto']}")
    d, c = (acc(a["cuenta_destino"]), acc(a["cuenta_origen"])) if saldo > 0 else (acc(a["cuenta_origen"]), acc(a["cuenta_destino"]))
    vals = {"move_type": "entry", "journal_id": REGLAS["diarios"]["varios"], "date": orig["date"], "ref": ref,
            "narration": f"AJUSTE DE AUDITORÍA sobre {orig['name']} (publicado). {a['motivo']} El asiento original no se modifica.",
            "line_ids": [(0, 0, {"name": f"Reclasificación de {orig['name']}", "account_id": d, "debit": abs(saldo), "credit": 0.0}),
                         (0, 0, {"name": f"Reclasificación de {orig['name']}", "account_id": c, "debit": 0.0, "credit": abs(saldo)})]}
    if ESC:
        mid = od.escribir("account.move", "create", vals)
        print(f"✔ {ref} creado en borrador (id {mid}): {a['cuenta_origen']} → {a['cuenta_destino']} {abs(saldo):,.2f}, fecha {orig['date']}")
    else:
        print(f"· {ref}: {a['cuenta_origen']} → {a['cuenta_destino']} {abs(saldo):,.2f}, fecha {orig['date']} (sobre {orig['name']})")
