#!/usr/bin/env bash
# Corre el pipeline completo sobre $CM_WORK (por defecto CasaMagnaSellOut/work).
# Prerrequisitos: work/datos/sellout_history.json (desde el artefacto) y los reportes nuevos ya ingeridos.
set -euo pipefail
cd "$(dirname "$0")"
export CM_WORK="${CM_WORK:-$(cd .. && pwd)/work}"
mkdir -p "$CM_WORK/output" "$CM_WORK/inputs" "$CM_WORK/datos"
python3 -W ignore odoo_extract.py
python3 -W ignore analyze.py
python3 -W ignore build_dashboard.py
python3 -W ignore build_email.py
cd "$CM_WORK/output" && rm -f Sell_Out_CasaMagna.zip && python3 -m zipfile -c Sell_Out_CasaMagna.zip Sell_Out_CasaMagna.html
sha256sum "$CM_WORK/output/Sell_Out_CasaMagna.zip"
cat "$CM_WORK/output/estado.json"
