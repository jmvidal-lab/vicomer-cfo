#!/usr/bin/env bash
# Prueba offline con los 5 Excel reales (26-oct a 23-nov 2026). Resultado esperado:
#   semana $126,233 (66 u) | reposición 52 SKU/921 u | faltantes 275
# Los Excel NO están en el repo (son datos): van en data/sukasa_samples/r20261026.xlsx ... r20261123.xlsx
# (bájalos de Gmail o del zip de migración). Uso: bash SellOutSukasa/scripts/selftest.sh [carpeta_samples]
set -euo pipefail
SK="$(cd "$(dirname "$0")/.." && pwd)"; SAMPLES="${1:-$SK/../data/sukasa_samples}"; W=$(mktemp -d)
ls "$SAMPLES"/r*.xlsx >/dev/null 2>&1 || { echo "No hay samples en $SAMPLES"; exit 1; }
python3 - "$SAMPLES" "$W" <<'PY'
import json,sys,glob,os
s,w=sys.argv[1:3]; b=os.path.basename
fs=sorted(glob.glob(os.path.join(s,"r*.xlsx")))
json.dump([{"date":f"{b(f)[1:5]}-{b(f)[5:7]}-{b(f)[7:9]}","file":f} for f in fs],open(w+"/weeks.json","w"))
PY
python3 "$SK/scripts/sukasa_parse.py" "$W/weeks.json" "$W/sukasa_data.json" "$SK/config.json"
python3 "$SK/scripts/build_report.py" "$W" "$SK/config.json" "$SK/templates"
echo "Salidas en $W"
