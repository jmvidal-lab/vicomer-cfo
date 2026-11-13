#!/usr/bin/env python3
"""
vix_subcuenta_banco.py — Crea la subcuenta contable de la cuenta corriente BG de VIX y mueve a ella
las líneas de los asientos BORRADOR que se registraron en la cuenta genérica 11010204 Bank.

    python3 VIX/vix_subcuenta_banco.py                 # simulación
    VIX_ESCRIBIR=1 python3 VIX/vix_subcuenta_banco.py  # aplica

El número de cuenta completo vive SOLO en Odoo (nombre de la cuenta) y en el entorno (BG_CUENTA);
en el repo solo va el código contable. Pásalo con VIX_BG_CTE=<número>.
"""
import os, sys
from vix_odoo import OdooVIX, CIA, REGLAS

ESCRIBIR = os.environ.get("VIX_ESCRIBIR") == "1"
SUB = REGLAS["saneamiento"]["subcuenta_banco"]
num = os.environ.get("VIX_BG_CTE") or sys.exit("Falta VIX_BG_CTE (número de la cuenta corriente).")
if not num.endswith(REGLAS["banco"]["cuenta_ultimos4"]):
    sys.exit("VIX_BG_CTE no termina en los 4 dígitos registrados en vix_reglas.json.")

od = OdooVIX()
acc = {a["code"]: a for a in od.leer("account.account", "search_read",
                                      [["company_ids", "in", [CIA]], ["code", "in", [SUB["padre"], SUB["codigo"]]]],
                                      fields=["id", "code", "name", "account_type"])}
padre = acc[SUB["padre"]]
nombre = f"{SUB['nombre']} {num}"
if SUB["codigo"] in acc:
    nueva = acc[SUB["codigo"]]["id"]
    print(f"· Ya existe {SUB['codigo']} {acc[SUB['codigo']]['name']} (id {nueva})")
elif ESCRIBIR:
    nueva = od.escribir("account.account", "create", {"code": SUB["codigo"], "name": nombre,
                                                      "account_type": padre["account_type"], "reconcile": False})
    print(f"✔ Creada {SUB['codigo']} {nombre} (id {nueva})")
else:
    nueva = None
    print(f"· Se crearía {SUB['codigo']} {nombre} ({padre['account_type']})")

lineas = od.leer("account.move.line", "search_read",
                 [["company_id", "=", CIA], ["account_id", "=", padre["id"]], ["parent_state", "=", "draft"],
                  ["move_id.ref", "=like", "VIXBANCO:%"]], fields=["id", "move_id", "debit", "credit"])
publicadas = od.leer("account.move.line", "search_count",
                     [["company_id", "=", CIA], ["account_id", "=", padre["id"]], ["parent_state", "=", "posted"]])
print(f"Líneas en borrador a mover: {len(lineas)} · saldo {sum(l['debit'] - l['credit'] for l in lineas):,.2f}"
      f" · líneas PUBLICADAS en {SUB['padre']} (no se tocan): {publicadas}")
if ESCRIBIR and nueva and lineas:
    od.escribir("account.move.line", "write", [l["id"] for l in lineas], {"account_id": nueva})
    print(f"✔ {len(lineas)} líneas movidas a {SUB['codigo']}")
