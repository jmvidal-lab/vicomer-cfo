#!/bin/bash
# ============================================================================
#  Instalador de la automatizacion del Presupuesto Comercial (Perseo)
#  - Programa la actualizacion DIARIA 10:00 y el CORREO SEMANAL (lunes 10:10)
#  Ejecutar:  doble clic en Finder, o en Terminal:
#     bash "/Users/juanmarcelo/Claude/Projects/CFO VICOMER/automatizacion/instalar_automatizacion.command"
# ============================================================================
set -e
PROJ="/Users/juanmarcelo/Claude/Projects/CFO VICOMER"
LA="$HOME/Library/LaunchAgents"
OUT="$PROJ/PresupuestoAuto"

echo "======================================================================"
echo "  AUTOMATIZACION PRESUPUESTO COMERCIAL VICOMER (Ecuador / Perseo)"
echo "======================================================================"

# 1) Python + openpyxl -------------------------------------------------------
echo "-> Verificando Python y openpyxl..."
if ! /usr/bin/python3 -c "import openpyxl" 2>/dev/null; then
    echo "   openpyxl no esta instalado. Instalando (pip3 --user)..."
    /usr/bin/python3 -m pip install --user openpyxl || \
      { echo "   ERROR instalando openpyxl. Instalalo manualmente:"; \
        echo "   /usr/bin/python3 -m pip install --user openpyxl"; exit 1; }
fi
echo "   OK."

# 2) Scripts y carpetas ------------------------------------------------------
for f in "perseo_presupuesto.py" "perseo_correo_semanal.py"; do
    [ -f "$PROJ/$f" ] || { echo "ERROR: falta $PROJ/$f"; exit 1; }
done
mkdir -p "$OUT" "$LA"
echo "-> Carpeta de salidas: $OUT"

# 3) Credenciales ------------------------------------------------------------
if [ ! -f "$HOME/.perseo_apikey" ] && [ ! -f "$PROJ/perseo_apikey.txt" ]; then
    echo "   AVISO: no se encontro el API key de Perseo (~/.perseo_apikey)."
fi
if [ ! -f "$HOME/.perseo_smtp" ] && [ -z "$SMTP_APP_PASSWORD" ]; then
    echo ""
    echo "   >>> FALTA la contrasena SMTP para enviar el correo semanal."
    echo "   Crea una 'Contrasena de aplicacion' de Google (con verificacion en 2 pasos)"
    echo "   en https://myaccount.google.com/apppasswords y guardala asi:"
    echo ""
    echo "       printf 'TU_APP_PASSWORD' > ~/.perseo_smtp && chmod 600 ~/.perseo_smtp"
    echo ""
    echo "   (El correo diario/datos funcionara igual; solo el envio del lunes"
    echo "    requiere esta clave.)"
fi

# 4) Instalar LaunchAgents ---------------------------------------------------
echo "-> Instalando tareas programadas..."
# Retirar la tarea Odoo separada (ahora todo va en el consolidado diario)
launchctl unload "$LA/com.vcomer.odoo.plist" 2>/dev/null || true
rm -f "$LA/com.vcomer.odoo.plist"
for p in com.vcomer.presupuesto com.vcomer.presupuesto.correo; do
    cp "$PROJ/automatizacion/$p.plist" "$LA/$p.plist"
    launchctl unload "$LA/$p.plist" 2>/dev/null || true
    launchctl load -w "$LA/$p.plist"
    echo "   cargado: $p"
done

echo ""
echo "-> Generando el reporte consolidado (Ecuador + Colombia + Costa Rica)..."
cd "$PROJ" && /usr/bin/python3 "$PROJ/estado_grupo.py" || \
   echo "   (si fallo, revisa $OUT/run.log / error.log)"

echo ""
echo "-> Enviando el CORREO DE PRUEBA ahora mismo..."
if [ -f "$HOME/.perseo_smtp" ] || [ -n "$SMTP_APP_PASSWORD" ] || grep -q app_password "$PROJ/correo_config.json" 2>/dev/null; then
    cd "$PROJ" && /usr/bin/python3 "$PROJ/perseo_correo_semanal.py" && \
      echo "   correo enviado a dir.comercial@v-comer.com (cc jmvidal)" || \
      echo "   (fallo el envio; revisa $OUT/correo_error.log)"
else
    echo "   NO se pudo enviar aun: falta la contrasena de aplicacion."
    echo "   Crea la clave (App Password de Google) y corre estas 2 lineas:"
    echo "       printf 'TU_APP_PASSWORD' > ~/.perseo_smtp && chmod 600 ~/.perseo_smtp"
    echo "       cd \"$PROJ\" && /usr/bin/python3 perseo_correo_semanal.py"
fi

echo ""
echo "======================================================================"
echo "  LISTO."
echo "  - Reporte consolidado (EC + CO + CR, sin IVA) generado TODOS los dias 10:00"
echo "    en: VICOMER COMERCIAL/ESTADO PRESUPUESTO GRUPO VICOMER.xlsx"
echo "  - Tus Excel curados (Regional/Analisis) NO se tocan (quedan intactos)"
echo "  - Correo semanal a dir.comercial@v-comer.com (cc jmvidal): LUNES 10:10"
echo "  Logs: $OUT/run.log , correo.log , error.log"
echo ""
echo "  Para PROBAR el correo sin enviar:"
echo "    cd \"$PROJ\" && PERSEO_MAIL_DRYRUN=1 /usr/bin/python3 perseo_correo_semanal.py"
echo "  Para ENVIAR el correo ahora (prueba real):"
echo "    cd \"$PROJ\" && /usr/bin/python3 perseo_correo_semanal.py"
echo "======================================================================"
