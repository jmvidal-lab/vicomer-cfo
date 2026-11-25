"""Utilidades compartidas del agente Casa Magna (nube)."""
import json, os, re, datetime as dt
from zoneinfo import ZoneInfo

PKG = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
WORK = os.path.abspath(os.environ.get('CM_WORK') or os.path.join(PKG, 'work'))
TZ = ZoneInfo('America/Bogota')


def cfg():
    return json.load(open(os.path.join(PKG, 'config.json'), encoding='utf-8'))


def hoy():
    return dt.datetime.now(TZ).date().isoformat()


def norm_sku(s, aliases=None):
    """Mayúsculas, solo alfanuméricos, sin sufijo M1, con alias (HI-O16 -> HIO16, TMO30H -> TMO30)."""
    s = re.sub(r'[^A-Z0-9]', '', str(s or '').upper())
    if s.endswith('M1') and len(s) > 4:
        s = s[:-2]
    return (aliases or {}).get(s, s)


def excluded(sku, c):
    return any(sku.startswith(e) for e in c['exclude_skus'])


def wpath(rel):
    return os.path.join(WORK, rel)


def jload(rel, default=None):
    p = wpath(rel)
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else default


def jsave(rel, obj, pretty=False):
    p = wpath(rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=1 if pretty else None,
                  separators=None if pretty else (',', ':'))
