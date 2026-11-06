#!/bin/bash
# Instala los LaunchAgents del Comité de Pagos:
#   com.vcomer.pagos.cxp    -> viernes 08:00 extrae CxP (Odoo CR/CO + Perseo EC)
#   com.vcomer.pagos.correo -> se dispara al aparecer archivos en Pagos/salida
set -e
PROJ="/Users/juanmarcelo/Claude/Projects/CFO VICOMER"
mkdir -p "$HOME/Library/LaunchAgents" "$PROJ/Pagos/cxp" "$PROJ/Pagos/salida" "$PROJ/Pagos/enviados"

for PLIST in com.vcomer.pagos.cxp.plist com.vcomer.pagos.correo.plist; do
  DEST="$HOME/Library/LaunchAgents/$PLIST"
  echo "==> Instalando $PLIST"
  cp "$PROJ/automatizacion/$PLIST" "$DEST"
  launchctl unload "$DEST" 2>/dev/null || true
  launchctl load "$DEST"
done

echo ""
echo "==> Cargados:"
launchctl list | grep vcomer.pagos || true
echo ""
echo "Probar extracción CxP ahora:      launchctl start com.vcomer.pagos.cxp"
echo "  (o directamente)                python3 \"$PROJ/pagos_cxp.py\" diag"
echo "Probar correo sin enviar:         PAGOS_MAIL_DRYRUN=1 python3 \"$PROJ/pagos_correo.py\""
echo "Logs:                             tail -f \"$PROJ/Pagos/run.log\" \"$PROJ/Pagos/correo.log\""
