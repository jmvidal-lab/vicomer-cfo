#!/bin/bash
# =====================================================================
#  Instala el LaunchAgent com.vcomer.dashboard.compras (diario 07:45)
#  y corre el pipeline una vez. NO toca los agentes existentes.
# =====================================================================
set -u
PROJ="/Users/juanmarcelo/Claude/Projects/CFO VICOMER"
PLIST="com.vcomer.dashboard.compras.plist"
DEST="$HOME/Library/LaunchAgents/$PLIST"

echo "======================================================================"
echo "  Dashboard de Compras y CxP — instalacion del agente diario"
echo "======================================================================"
mkdir -p "$HOME/Library/LaunchAgents" "$PROJ/OdooVentas" "$PROJ/automatizacion"

if [ ! -f "$PROJ/automatizacion/$PLIST" ]; then
  echo "ERROR: no encuentro $PROJ/automatizacion/$PLIST"; exit 1
fi

cp "$PROJ/automatizacion/$PLIST" "$DEST"
launchctl unload "$DEST" 2>/dev/null || true
launchctl load "$DEST" || echo "No se pudo cargar el agente."

echo ""
echo "==> Agentes VICOMER cargados:"
launchctl list | grep vcomer || echo "   (ninguno)"

echo ""
echo "==> Corriendo el pipeline una vez..."
cd "$PROJ" || exit 1
/usr/bin/python3 compras_dashboard_pipeline.py 2>&1 | tee "$PROJ/OdooVentas/compras_run.log"

echo ""
echo "======================================================================"
echo "  LISTO. Corre solo todos los dias a las 07:45."
echo ""
echo "  Dashboards:"
ls -1 "$PROJ/OdooVentas/"Dashboard_Compras_*.html 2>/dev/null | sed 's/^/     /'
echo ""
echo "  Forzar una corrida:  launchctl start com.vcomer.dashboard.compras"
echo "  Ver el log:          tail -f \"$PROJ/OdooVentas/compras_run.log\""
echo "  Desinstalar:         launchctl unload \"$DEST\" && rm \"$DEST\""
echo "======================================================================"
echo ""
echo "Ya puedes cerrar esta ventana."
