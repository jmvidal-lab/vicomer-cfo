#!/bin/bash
# =====================================================================
#  Instala el LaunchAgent com.vcomer.dashboard.ventas (diario 07:30)
#  y corre el pipeline una vez para dejar los dashboards al dia.
#  NO toca los agentes existentes.
# =====================================================================
set -u
PROJ="/Users/juanmarcelo/Claude/Projects/CFO VICOMER"
PLIST="com.vcomer.dashboard.ventas.plist"
DEST="$HOME/Library/LaunchAgents/$PLIST"

echo "======================================================================"
echo "  Dashboards de Ventas — instalacion del agente diario"
echo "======================================================================"
mkdir -p "$HOME/Library/LaunchAgents" "$PROJ/OdooVentas" "$PROJ/automatizacion"

if [ ! -f "$PROJ/automatizacion/$PLIST" ]; then
  echo "ERROR: no encuentro $PROJ/automatizacion/$PLIST"; exit 1
fi

cp "$PROJ/automatizacion/$PLIST" "$DEST"
launchctl unload "$DEST" 2>/dev/null || true
launchctl load "$DEST" || { echo "No se pudo cargar el agente."; }

echo ""
echo "==> Agentes VICOMER cargados ahora mismo:"
launchctl list | grep vcomer || echo "   (ninguno)"

echo ""
echo "==> Corriendo el pipeline una vez para dejar los dashboards al dia..."
cd "$PROJ" || exit 1
/usr/bin/python3 ventas_dashboard_pipeline.py 2>&1 | tee "$PROJ/OdooVentas/dashboard_run.log"

echo ""
echo "======================================================================"
echo "  LISTO. El agente corre solo todos los dias a las 07:30."
echo ""
echo "  Dashboards:"
ls -1 "$PROJ/OdooVentas/"Dashboard_Ventas_*.html 2>/dev/null | sed 's/^/     /'
echo ""
echo "  Para forzar una corrida:   launchctl start com.vcomer.dashboard.ventas"
echo "  Para ver el log:           tail -f \"$PROJ/OdooVentas/dashboard_run.log\""
echo "  Para desinstalar:          launchctl unload \"$DEST\" && rm \"$DEST\""
echo "======================================================================"
echo ""
echo "Ya puedes cerrar esta ventana."
