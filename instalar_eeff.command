#!/bin/bash
# Instala el LaunchAgent de Estados Financieros Ejecutivos (Perseo).
# Corre el dia 4 de cada mes a las 08:00 y genera el one-pager en Finanzas/.
set -e
PROJ="/Users/juanmarcelo/Claude/Projects/CFO VICOMER"
PLIST="com.vcomer.eeff.plist"
DEST="$HOME/Library/LaunchAgents/$PLIST"

echo "==> Preparando carpetas"
mkdir -p "$HOME/Library/LaunchAgents" "$PROJ/Finanzas"

echo "==> Verificando dependencia openpyxl"
python3 -c "import openpyxl" 2>/dev/null || pip3 install --user openpyxl

echo "==> Instalando $PLIST"
cp "$PROJ/automatizacion/$PLIST" "$DEST"
launchctl unload "$DEST" 2>/dev/null || true
launchctl load "$DEST"

echo "==> Cargado. Agenda:"
launchctl list | grep vcomer.eeff || true

echo ""
echo "Listo. Se ejecuta el DIA 4 de cada mes a las 08:00."
echo ""
echo "Probar AHORA (ultimo mes cerrado):"
echo "    python3 \"$PROJ/perseo_estados_financieros.py\""
echo "Corte a un mes especifico:"
echo "    python3 \"$PROJ/perseo_estados_financieros.py\" 2026-06"
echo "Salida:"
echo "    $PROJ/Finanzas/Estados_Financieros_Ejecutivo_ULTIMO.xlsx"
echo "Logs:"
echo "    tail -f \"$PROJ/Finanzas/run.log\" \"$PROJ/Finanzas/error.log\""
