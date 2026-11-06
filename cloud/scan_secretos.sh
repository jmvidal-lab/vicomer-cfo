#!/usr/bin/env bash
# Busca secretos en lo que va a entrar al repo. Sale con 1 si encuentra algo.
cd "$(dirname "$0")/.."
FILES=$(git ls-files -co --exclude-standard 2>/dev/null || find . -type f -not -path './.git/*')
HIT=0
# 1) claves largas tipo hex/base64 asignadas a variables sensibles
echo "$FILES" | tr '\n' '\0' | xargs -0 grep -nIE "(api_?key|apikey|password|app_password|secret|token)[\"']?\s*[:=]\s*[\"'][A-Za-z0-9_\-]{12,}[\"']" 2>/dev/null \
  | grep -vE "\.env\.example|scan_secretos" && HIT=1
# 2) App Password de Google (16 letras en grupos de 4)
echo "$FILES" | tr '\n' '\0' | xargs -0 grep -nIE "\b[a-z]{4} [a-z]{4} [a-z]{4} [a-z]{4}\b" 2>/dev/null | grep -v scan_secretos && HIT=1
# 3) hex de 40 caracteres (formato de API key de Odoo)
echo "$FILES" | tr '\n' '\0' | xargs -0 grep -nIE "\b[0-9a-f]{40}\b" 2>/dev/null && HIT=1
# 4) archivos prohibidos
echo "$FILES" | grep -E "apikey.*\.txt$|correo_config\.json$|maestro_proveedores|Beneficiarios|\.env$" && HIT=1
[ $HIT = 0 ] && echo "✔ Sin secretos detectados" || { echo "✘ Revisa lo anterior antes de hacer commit"; exit 1; }
