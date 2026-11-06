#!/bin/bash
# ============================================================================
# REPARAR LOS AGENTES AUTOMÁTICOS  ·  VICOMER
# ============================================================================
# Diagnostica y repara las dos fallas detectadas el 2026-08-03:
#   1. Los agentes que escriben en ~/Desktop/VICOMER COMERCIAL fallan con
#      "Operation not permitted" — macOS bloquea a launchd el acceso al
#      Escritorio hasta que se le concede Acceso Total al Disco a python3.
#   2. com.vcomer.pagos.cxp no se dispara los viernes 08:00 si el Mac está
#      suspendido a esa hora.
# No borra nada. Deja el reporte en Migracion/reparacion_agentes.txt
# ============================================================================
PROJ="/Users/juanmarcelo/Claude/Projects/CFO VICOMER"
OUT_DIR="$PROJ/Migracion"
OUT="$OUT_DIR/reparacion_agentes.txt"
mkdir -p "$OUT_DIR"
cd "$PROJ" || exit 1

{
echo "==================================================================="
echo " REPARACIÓN DE AGENTES — $(date '+%Y-%m-%d %H:%M:%S')"
echo "==================================================================="
echo

echo "### 1. Estado actual de los agentes ###"
echo "(la primera columna es el último código de salida: 0 = bien, otro = falla)"
launchctl list 2>/dev/null | grep vcomer || echo "   (ninguno cargado)"
echo

echo "### 2. Prueba de escritura en el Escritorio ###"
DEST="$HOME/Desktop/VICOMER COMERCIAL"
if [ -d "$DEST" ]; then
  if touch "$DEST/.permiso_test" 2>/dev/null; then
    rm -f "$DEST/.permiso_test"
    echo "   OK: esta terminal SÍ puede escribir en VICOMER COMERCIAL."
    echo "   (launchd usa otro contexto de permisos; ver paso 3)"
  else
    echo "   !! Ni esta terminal puede escribir ahí."
  fi
else
  echo "   !! No existe la carpeta: $DEST"
fi
echo

echo "### 3. Acceso Total al Disco para python3 ###"
echo "   launchd ejecuta: /usr/bin/python3"
echo "   Ruta real      : $(readlink -f /usr/bin/python3 2>/dev/null || echo /usr/bin/python3)"
echo
echo "   ACCIÓN MANUAL (una sola vez, no se puede automatizar por seguridad):"
echo "     1. Ajustes del Sistema > Privacidad y seguridad > Acceso total al disco"
echo "     2. Pulsa +  y en el diálogo pulsa Cmd+Shift+G"
echo "     3. Pega:  /usr/bin/python3     y dale Abrir"
echo "     4. Deja el interruptor ENCENDIDO"
echo "     5. Vuelve a ejecutar este archivo para comprobar"
echo

echo "### 4. Recargar los agentes ###"
for A in com.vcomer.presupuesto com.vcomer.presupuesto.correo com.vcomer.perseoventas \
         com.vcomer.pagos.cxp com.vcomer.pagos.correo com.vcomer.eeff com.vcomer.odoo \
         com.vcomer.casamagna; do
  P="$HOME/Library/LaunchAgents/$A.plist"
  [ -f "$P" ] || continue
  launchctl bootout "gui/$(id -u)/$A" 2>/dev/null
  if launchctl bootstrap "gui/$(id -u)" "$P" 2>/dev/null; then
    echo "   recargado: $A"
  else
    echo "   !! no pude recargar: $A"
  fi
done
echo

echo "### 5. Forzar una corrida del pipeline de pagos ###"
launchctl kickstart -k "gui/$(id -u)/com.vcomer.pagos.cxp" 2>/dev/null \
  && echo "   lanzado com.vcomer.pagos.cxp" \
  || echo "   !! no pude lanzarlo"
sleep 6
echo "   -- Pagos/run.log:"
tail -n 8 "$PROJ/Pagos/run.log" 2>/dev/null | sed 's/^/     /'
echo

echo "### 6. Refrescar el histórico de Ecuador desde Perseo ###"
echo "   (para completar julio, que quedó parcial en el archivo del 21-jul)"
python3 perseo_presupuesto.py 2>&1 | tail -n 12 | sed 's/^/     /'
echo
if [ -f "$PROJ/PresupuestoAuto/estado_presupuesto.json" ]; then
  python3 - <<'PY' 2>&1 | sed 's/^/     /'
import json, pathlib
p = pathlib.Path.home()/"Claude/Projects/CFO VICOMER/PresupuestoAuto/estado_presupuesto.json"
d = json.loads(p.read_text(encoding="utf-8"))
m = d.get("total_mensual_neto") or []
print("Ventas netas Ecuador (Perseo), generado", d.get("generado"), "· mes_cierre", d.get("mes_cierre"))
MES = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]
for i, v in enumerate(m[:8]):
    print(f"  {MES[i]}: {v:>14,.2f}")
print()
print("Para odoo_config.json -> ecuador_hist_mensual (copia este bloque y pásaselo a Claude):")
print(json.dumps({str(i+1): round(v,2) for i,v in enumerate(m) if v}, indent=1))
PY
fi
echo

echo "### 7. Estado del asunto de los viernes ###"
echo "   com.vcomer.pagos.cxp usa StartCalendarInterval (viernes 08:00)."
echo "   Si el Mac está suspendido a esa hora, launchd NO lo dispara al despertar"
echo "   de forma fiable. Opciones:"
echo "     a) Ajustes del Sistema > Batería/Energía > programar encendido los viernes"
echo "     b) Mover el agente a una hora en que el Mac esté seguro despierto"
echo "     c) Dejar el Mac enchufado y sin suspender los viernes por la mañana"
echo "   La tarea de Claude ya se niega a subir un CxP obsoleto, así que un fallo"
echo "   ahora se detecta el mismo día en vez de a las 3 semanas."
echo
echo "==================================================================="
echo " FIN. Dile a Claude: \"corrí la reparación\""
echo "==================================================================="
} 2>&1 | tee "$OUT"

echo
echo "Reporte guardado en: $OUT"
