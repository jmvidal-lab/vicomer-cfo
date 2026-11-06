#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# cloud/setup.sh — prepara una sesión en la nube para correr los pipelines.
#
#   source cloud/setup.sh          # (source, no bash: deja las rutas exportadas)
#
# Qué hace:
#   1. Instala las 3 dependencias externas (openpyxl, python-docx, PyMuPDF).
#   2. Fija las rutas (VICOMER_PROJ, ODOO_OUT_DIR, PERSEO_FILES_DIR...) al repo,
#      en vez de ~/Claude/Projects/CFO VICOMER del Mac.
#   3. Materializa los secretos del environment en los archivos que algunos
#      scripts heredados todavía leen (~/.odoo_apikey, ~/.perseo_apikey,
#      ~/.gmail_jmvidal_apppass, ~/.odoo_vintral1_apikey), con chmod 600.
#      Así los 30+ scripts corren SIN modificarlos y el Mac sigue igual.
#   4. Verifica qué credenciales hay (por nombre, nunca imprime valores).
# ─────────────────────────────────────────────────────────────────────
_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

pip install -q --break-system-packages openpyxl python-docx PyMuPDF 2>/dev/null \
  || pip install -q openpyxl python-docx PyMuPDF

export VICOMER_PROJ="$_ROOT"
export ODOO_OUT_DIR="$_ROOT/OdooVentas"
export PERSEO_OUT_DIR="$_ROOT/PresupuestoAuto"
export PERSEO_FILES_DIR="${PERSEO_FILES_DIR:-$_ROOT/data/presupuesto}"
export VICOMER_PERSONAL="${VICOMER_PERSONAL:-$_ROOT/data/personal}"
mkdir -p "$ODOO_OUT_DIR" "$PERSEO_OUT_DIR" "$PERSEO_FILES_DIR" "$VICOMER_PERSONAL" \
         "$_ROOT/Finanzas" "$_ROOT/CasaMagna" "$_ROOT/Pagos/cxp" "$_ROOT/data"

_put() {  # _put <VAR> <archivo>
  local v="${!1}"
  if [ -n "$v" ]; then
    umask 077; printf '%s' "$v" > "$2"; chmod 600 "$2"
  fi
}
_put ODOO_APIKEY          "$HOME/.odoo_apikey"
_put ODOO_APIKEY_VINTRAL1 "$HOME/.odoo_vintral1_apikey"
_put PERSEO_API_KEY       "$HOME/.perseo_apikey"
_put GMAIL_APP_PASSWORD   "$HOME/.gmail_jmvidal_apppass"
[ -z "$SMTP_APP_PASSWORD" ] && [ -n "$GMAIL_APP_PASSWORD" ] && export SMTP_APP_PASSWORD="$GMAIL_APP_PASSWORD"

echo "── Credenciales en el environment (solo nombres) ──"
for k in ODOO_URL ODOO_DB ODOO_LOGIN; do
  if [ -n "${!k}" ]; then echo "  ✔ $k"; else echo "  · $k (usa odoo_config.json)"; fi
done
for k in ODOO_APIKEY ODOO_APIKEY_VINTRAL1 PERSEO_API_KEY SMTP_APP_PASSWORD GMAIL_APP_PASSWORD; do
  if [ -n "${!k}" ]; then echo "  ✔ $k"; else echo "  ✘ $k (falta)"; fi
done
echo "── Rutas ──"; echo "  VICOMER_PROJ=$VICOMER_PROJ"
echo "Listo. Prueba de red: python3 cloud/check_red.py"
