#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
casamagna_common.py — utilidades compartidas del pipeline Casa Magna.
 - carga de config (casamagna_config.json)
 - normalización de SKU (unifica los códigos de NetSuite / Odoo viejo / Odoo nuevo)
 - lectura de secretos desde archivos (chmod 600), nunca embebidos en el repo
"""
import os, json, re
from pathlib import Path

PROJ = Path(__file__).resolve().parent
CONFIG_PATH = PROJ / "casamagna_config.json"


def load_config():
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return cfg


def expand(p):
    return Path(os.path.expanduser(str(p)))


def read_secret(path):
    """Lee un secreto (API key / app password) de un archivo. Devuelve '' si no existe."""
    f = expand(path)
    if f.exists():
        return f.read_text(encoding="utf-8").strip()
    # Nube: si el archivo no existe, se busca la variable de entorno equivalente.
    nombre = Path(str(path)).name
    for patron, var in (("vintral1", "ODOO_APIKEY_VINTRAL1"), ("apikey", "ODOO_APIKEY"),
                        ("apppass", "GMAIL_APP_PASSWORD")):
        if patron in nombre and os.environ.get(var):
            return os.environ[var].strip()
    return ""


# --------------------------------------------------------------- normalización SKU
def make_normalizer(alias=None, exclude=None):
    alias = {k.upper(): v.upper() for k, v in (alias or {}).items()}
    exclude = {e.upper() for e in (exclude or [])}

    def norm(s):
        s = re.sub(r"[^A-Z0-9]", "", (s or "").upper().strip())
        s = re.sub(r"M1$", "", s)          # sufijo de variante "-M1"
        return alias.get(s, s)

    def is_excluded(s):
        return norm(s) in exclude

    return norm, is_excluded


def out_dir(cfg):
    d = expand(cfg.get("salida_dir", PROJ / "CasaMagna"))
    d.mkdir(parents=True, exist_ok=True)
    return d
