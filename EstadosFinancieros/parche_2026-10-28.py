#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parche_2026-10-28.py · aplica sobre eeff_odoo.py (version hasta el 26-oct-2026) las dos
correcciones del 28-oct-2026. Idempotente: si ya estan aplicadas, no hace nada.

1. ANTICIPOS RECIBIDOS se presenta en el pasivo aunque Odoo la tipifique "Por cobrar"
   (cambio de plan de cuentas del 26-oct-2026 que movia la regresion de julio en 19.713,45).
2. La utilidad neta estimada de Ecuador resta los gastos no deducibles (antes quedaba
   sobrestimada en ~20.000 y contradecia la cascada de la pagina).

Uso: python3 parche_2026-10-28.py eeff_odoo.py
"""
import sys
from pathlib import Path

f = Path(sys.argv[1] if len(sys.argv) > 1 else "eeff_odoo.py")
s = f.read_text(encoding="utf-8")
CAMBIOS = [
 ('''                          "IMPUESTO A LA RENTA","IMPUESTOS POR PAGAR","ICA POR PAGAR"],
}''',
  '''                          "IMPUESTO A LA RENTA","IMPUESTOS POR PAGAR","ICA POR PAGAR"],
  "anticipos_recibidos": ["ANTICIPOS RECIBIDOS"],
}'''),
 ('''def clasifica(cuenta):
    nom, t = cuenta.get("name"), cuenta.get("account_type")
''',
  '''def clasifica(cuenta):
    nom, t = cuenta.get("name"), cuenta.get("account_type")
    # Un anticipo recibido de clientes es un pasivo por su naturaleza, aunque Odoo lo
    # tipifique "Por cobrar" para poder conciliarlo contra facturas. El 26-oct-2026 se
    # cambio asi la 201.03.01.02 en Ecuador; restarlo de la cartera achicaba activo y
    # pasivo a la vez y movia la regresion de julio en exactamente su saldo (19.713,45).
    if contiene(nom, REGLAS["anticipos_recibidos"]):
        return "otros_pasivos_corrientes"
'''),
 ('''        part = max(0.0, uai) * PARTICIPACION_EC
        base = max(0.0, uai) - part + y["g4"]      # los no deducibles vuelven a la base
        ir = base * IR_EC
        fiscal.update({"estimado": True, "registrado": False, "utilidad_antes": R(uai),
                       "participacion": R(part), "base_imponible": R(base),
                       "impuesto_renta": R(ir), "no_deducibles": R(y["g4"]),
                       "utilidad_neta_estimada": R(uai - part - ir),
                       "tasa_efectiva": R((part + ir)/uai, 4) if uai else None,''',
  '''        # Los no deducibles son gasto pagado: van contra la utilidad contable (base de la
        # participacion y de la neta) y solo vuelven a sumarse en la base del impuesto.
        # Hasta el 28-oct-2026 la neta se calculaba sobre uai sin restarlos y quedaba
        # sobrestimada en ~20.000, en contradiccion con la cascada de la pagina.
        uc = uai - y["g4"]                          # utilidad contable antes de part. e IR
        part = max(0.0, uc) * PARTICIPACION_EC
        base = max(0.0, uc) - part + y["g4"]       # los no deducibles vuelven a la base
        ir = base * IR_EC
        fiscal.update({"estimado": True, "registrado": False, "utilidad_antes": R(uc),
                       "participacion": R(part), "base_imponible": R(base),
                       "impuesto_renta": R(ir), "no_deducibles": R(y["g4"]),
                       "utilidad_neta_estimada": R(uc - part - ir),
                       "tasa_efectiva": R((part + ir)/uc, 4) if uc > 0 else None,'''),
]
n = 0
for viejo, nuevo in CAMBIOS:
    if nuevo in s:
        continue
    if s.count(viejo) != 1:
        sys.exit("PARCHE NO APLICABLE: no se encontro exactamente una vez:\n" + viejo[:120])
    s = s.replace(viejo, nuevo); n += 1
f.write_text(s, encoding="utf-8")
print("parche aplicado: %d cambio(s) nuevos" % n)
