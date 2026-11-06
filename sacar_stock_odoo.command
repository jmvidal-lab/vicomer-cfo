#!/bin/bash
cd "$(dirname "$0")"
echo "== Extrayendo stock de Odoo =="
/usr/bin/python3 odoo_stock.py
echo
echo "Listo. Cierra esta ventana."
read -n 1 -s
