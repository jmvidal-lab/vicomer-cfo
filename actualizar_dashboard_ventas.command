#!/bin/bash
# =====================================================================
#  Dashboards de Ventas — Grupo VICOMER
#  Doble clic para: autoprueba -> diagnóstico -> extracción -> render
#  Todo queda en OdooVentas/dashboard_run.log
# =====================================================================
PROJ="/Users/juanmarcelo/Claude/Projects/CFO VICOMER"
PY=/usr/bin/python3
cd "$PROJ" || { echo "No encuentro $PROJ"; exit 1; }
mkdir -p "$PROJ/OdooVentas"
LOG="$PROJ/OdooVentas/dashboard_run.log"
ANIO=$(date +%Y)

{
  echo "======================================================================"
  echo "  ACTUALIZACION DASHBOARD DE VENTAS — $(date '+%Y-%m-%d %H:%M:%S')"
  echo "======================================================================"
  echo ""
  echo "----- 1/4  AUTOPRUEBA OFFLINE -------------------------------------"
  "$PY" ventas_dashboard.py test
  echo ""
  echo "----- 2/4  DIAGNOSTICO DE CONEXION Y DATOS CRUDOS -----------------"
  "$PY" ventas_dashboard.py diag
  echo ""
  echo "----- 3/4  EXTRACCION $ANIO ---------------------------------------"
  "$PY" ventas_dashboard.py "$ANIO"
  echo ""
  echo "----- 4/4  RENDER DE LOS 4 DASHBOARDS -----------------------------"
  if [ -f "$PROJ/ventas_dashboard_render.py" ]; then
      "$PY" ventas_dashboard_render.py
  else
      echo "(el motor de render todavia no esta instalado — se instala en el siguiente paso)"
  fi
  echo ""
  echo "======================================================================"
  echo "  FIN — $(date '+%Y-%m-%d %H:%M:%S')"
  echo "======================================================================"
} 2>&1 | tee "$LOG"

echo ""
echo "Log completo guardado en:"
echo "   $LOG"
echo ""
echo "Ya puedes cerrar esta ventana."
