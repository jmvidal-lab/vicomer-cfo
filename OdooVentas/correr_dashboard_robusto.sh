#!/bin/bash
# correr_dashboard_robusto.sh — generado por arreglar_agente.sh
#
# Espera a que Odoo sea alcanzable antes de correr el pipeline, y reintenta.
# La causa del apagon del 21-ago fue DNS al despertar el Mac, no Odoo.

PROY="$HOME/Claude/Projects/CFO VICOMER/OdooVentas"
CONFIG="$PROY/comando_original.txt"
LOG="$PROY/agente_robusto.log"
HOST="vicomer.odoo.com"

ESPERA_RED_MAX=300     # 5 min esperando que la red levante
INTENTOS=3
ESPERA_ENTRE=90        # 1.5 min entre reintentos

log() { echo "$(date '+%Y-%m-%d %H:%M:%S')  $*" | tee -a "$LOG"; }

log "===================================================================="
log "Arranque del agente robusto"

if [ ! -s "$CONFIG" ]; then
    log "ERROR: falta $CONFIG. Corre arreglar_agente.sh de nuevo."
    exit 1
fi

# Reconstruye el comando original, una linea por argumento (soporta espacios).
CMD=()
while IFS= read -r linea; do
    [ -n "$linea" ] && CMD+=("$linea")
done < "$CONFIG"

# ---- Esperar a que el host resuelva Y responda -----------------------------
inicio=$(date +%s)
red_ok=0
while true; do
    if /usr/bin/curl -s -o /dev/null -m 10 "https://$HOST" 2>/dev/null; then
        red_ok=1
        break
    fi
    ahora=$(date +%s)
    if [ $((ahora - inicio)) -ge $ESPERA_RED_MAX ]; then
        break
    fi
    log "  red aun no disponible ($HOST), reintento en 15s..."
    sleep 15
done

if [ "$red_ok" = "1" ]; then
    log "Red OK: $HOST alcanzable tras $(( $(date +%s) - inicio ))s"
else
    log "AVISO: $HOST no respondio en ${ESPERA_RED_MAX}s. Se intenta igual."
fi

# ---- Correr el pipeline con reintentos -------------------------------------
n=1
while [ $n -le $INTENTOS ]; do
    log "Intento $n/$INTENTOS: ${CMD[*]}"
    "${CMD[@]}"
    rc=$?
    if [ $rc -eq 0 ]; then
        log "OK: el pipeline termino bien en el intento $n"
        exit 0
    fi
    log "FALLO (codigo $rc) en el intento $n"
    if [ $n -lt $INTENTOS ]; then
        log "  esperando ${ESPERA_ENTRE}s antes de reintentar..."
        sleep $ESPERA_ENTRE
    fi
    n=$((n + 1))
done

log "ERROR: el pipeline fallo en los $INTENTOS intentos."
exit 1
