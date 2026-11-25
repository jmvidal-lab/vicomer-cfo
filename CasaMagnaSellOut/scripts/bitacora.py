#!/usr/bin/env python3
"""Agrega una línea a work/datos/corridas.json (se publica con el artefacto).
Uso: python3 bitacora.py <ENVIADO|BORRADOR|FALLA> "<detalle corto>" """
import sys, datetime as dt
from common import jload, jsave, TZ
if len(sys.argv) != 3:
    sys.exit(__doc__)
L = jload('datos/corridas.json', []); E = jload('output/estado.json', {})
L.append({'cuando': dt.datetime.now(TZ).isoformat(timespec='minutes'), 'resultado': sys.argv[1], 'detalle': sys.argv[2][:300],
          'corte': E.get('fecha_corte'), 'frenos': len(E.get('frenos', [])), 'alertas': len(E.get('alertas', []))})
jsave('datos/corridas.json', L[-200:], pretty=True); print('OK bitácora', L[-1])
