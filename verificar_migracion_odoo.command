#!/bin/bash
# ============================================================================
# VERIFICACIÓN DE LA MIGRACIÓN ECUADOR -> ODOO
# ============================================================================
# Doble clic para correr. NO cambia nada: sólo lee Odoo y guarda un reporte.
# La salida queda en Migracion/verificacion_odoo.txt, que Claude puede leer
# directamente (no necesitas copiar ni pegar nada).
# ============================================================================
PROJ="/Users/juanmarcelo/Claude/Projects/CFO VICOMER"
OUT_DIR="$PROJ/Migracion"
OUT="$OUT_DIR/verificacion_odoo.txt"
mkdir -p "$OUT_DIR"
cd "$PROJ" || exit 1

{
  echo "==================================================================="
  echo " VERIFICACIÓN MIGRACIÓN ECUADOR -> ODOO"
  echo " Fecha: $(date '+%Y-%m-%d %H:%M:%S')   ·   Host: $(hostname)"
  echo "==================================================================="
  echo

  echo "### [1/5] DESCUBRIMIENTO DE LA INSTANCIA ODOO ###"
  echo "(compañías, plan de cuentas, RUC de clientes, localización)"
  echo "-------------------------------------------------------------------"
  python3 odoo_descubrir.py 2>&1
  echo

  echo "### [2/5] MAPEO COMPAÑÍA -> PAÍS EN CUENTAS POR PAGAR ###"
  echo "-------------------------------------------------------------------"
  python3 pagos_cxp.py diag 2>&1
  echo

  echo "### [3/5] ESTADOS FINANCIEROS: MODO DE MAPEO DETECTADO ###"
  echo "-------------------------------------------------------------------"
  python3 odoo_estados_financieros.py diag 2>&1
  echo

  echo "### [4/5] ESTADO DE LOS AGENTES AUTOMÁTICOS ###"
  echo "-------------------------------------------------------------------"
  echo "-- LaunchAgents cargados:"
  launchctl list 2>/dev/null | grep vcomer || echo "   (ninguno cargado)"
  echo
  echo "-- Última corrida del pipeline de pagos (Pagos/run.log):"
  tail -n 6 "$PROJ/Pagos/run.log" 2>/dev/null || echo "   (sin log)"
  echo
  echo "-- Errores recientes (Pagos/error.log):"
  tail -n 6 "$PROJ/Pagos/error.log" 2>/dev/null || echo "   (sin errores)"
  echo
  echo "-- Antigüedad del CxP actual:"
  if [ -f "$PROJ/Pagos/cxp/cxp_semana_actual.json" ]; then
    python3 - <<'PY' 2>&1
import json, datetime, pathlib
p = pathlib.Path.home() / "Claude/Projects/CFO VICOMER/Pagos/cxp/cxp_semana_actual.json"
d = json.loads(p.read_text(encoding="utf-8"))
gen = d.get("generado", "?")
sem = d.get("semana", "?")
try:
    horas = (datetime.datetime.now() - datetime.datetime.fromisoformat(gen)).total_seconds() / 3600
    edad = f"{horas:.1f} h"
except Exception:
    edad = "?"
y, w, _ = datetime.date.today().isocalendar()
actual = f"{y}-W{w:02d}"
print(f"   generado: {gen}  ({edad})")
print(f"   semana del archivo: {sem}   ·   semana en curso: {actual}")
print("   ESTADO:", "OBSOLETO — el pipeline no corrió" if sem != actual else "al día")
PY
  else
    echo "   (no existe el archivo)"
  fi
  echo

  echo "### [5/5] PRUEBAS OFFLINE DE LA LÓGICA ###"
  echo "-------------------------------------------------------------------"
  for s in "pagos_cxp.py" "odoo_presupuesto.py" "odoo_estados_financieros.py"; do
    printf "%-34s " "$s autotest"
    if python3 "$s" autotest >/dev/null 2>&1; then echo "PASA"; else echo "FALLA"; fi
  done
  echo

  echo "==================================================================="
  echo " FIN. Dile a Claude: \"ya corrí la verificación\""
  echo "==================================================================="
} 2>&1 | tee "$OUT"

echo
echo "Reporte guardado en: $OUT"
echo "Puedes cerrar esta ventana."
