#!/bin/bash
# Instala el LaunchAgent del pipeline Casa Magna (corre cada lunes 13:30).
set -e
PROJ="/Users/juanmarcelo/Claude/Projects/CFO VICOMER"
PLIST="com.vcomer.casamagna.plist"
DEST="$HOME/Library/LaunchAgents/$PLIST"

echo "==> Instalando $PLIST"
mkdir -p "$HOME/Library/LaunchAgents" "$PROJ/CasaMagna"
cp "$PROJ/automatizacion/$PLIST" "$DEST"

# Recargar
launchctl unload "$DEST" 2>/dev/null || true
launchctl load "$DEST"
echo "==> Cargado. Agenda:"
launchctl list | grep casamagna || true
echo ""
echo "Listo. Corre cada LUNES 13:30. Para probar ahora mismo:"
echo "    launchctl start com.vcomer.casamagna"
echo "    tail -f \"$PROJ/CasaMagna/run.log\""
