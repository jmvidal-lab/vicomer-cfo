#!/usr/bin/env python3
"""Autoprueba offline (sin Odoo ni Gmail). Uso: python3 selftest.py  -> 'SELFTEST OK'"""
import os, sys, json, tempfile, subprocess, datetime as dt
import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp(prefix='cm_selftest_'); env = {**os.environ, 'CM_WORK': tmp}
HEAD = ['FECHA', 'MARCA', 'PLAZA', 'ALMACEN', 'UBICACION', 'ARTICULO', 'DESCRIPCION', 'CANTIDAD', 'PRECIO UNITARIO', 'SUBTOTAL',
        'TOTAL CON IVA', 'COSTO UNITARIO', 'COSTO TOTAL', 'MARGEN', 'Representante de ventas']


def xlsx(name, rows, head=HEAD):
    wb = openpyxl.Workbook(); ws = wb.active; ws.append(head)
    for r in rows:
        ws.append(r)
    p = os.path.join(tmp, name); wb.save(p); return p


def run(*a, ok=(0,)):
    r = subprocess.run([sys.executable, '-W', 'ignore', *a], cwd=HERE, env=env, capture_output=True, text=True)
    assert r.returncode in ok, (a, r.returncode, r.stdout, r.stderr)
    return r.stdout


hoy = dt.date.today(); lun = hoy - dt.timedelta(days=hoy.weekday()); lp = lun - dt.timedelta(weeks=1)
row = lambda d, sku, q, ct, m: [dt.datetime.combine(d, dt.time()), 'THOR', 'BOGOTA', 'X', 'X CM', sku, 'DESC ' + sku, q, 0, 0, 0, 0, ct, m, 'REP']
# semana previa: 4 TMO30H-M1 (alias -> TMO30) y fila Total
a = xlsx('a.xlsx', [row(lp - dt.timedelta(days=3), 'TMO30H', 4, 700, 0.3), row(lp - dt.timedelta(days=2), 'TIM-15', 1, 100, '30%'), [None, 'Total']])
assert 'OK' in run('ingest_netsuite.py', a, f'{lp}T11:00:00Z', 'th1')
assert 'YA PROCESADO' in run('ingest_netsuite.py', a, f'{lp}T11:00:00Z', 'th1')           # idempotente
# mismo archivo como si fuera otra semana -> freno (adjunto de otro hilo)
assert 'FRENO' in run('ingest_netsuite.py', a, f'{lun}T11:00:00Z', 'th2', ok=(2,))
# columnas reordenadas: se leen por nombre
h2 = HEAD[::-1]; b = xlsx('b.xlsx', [row(lun - dt.timedelta(days=4), 'TMO30H', 2, 350, 0.3)[::-1]], h2)
assert 'OK' in run('ingest_netsuite.py', b, f'{lun}T11:00:00Z', 'th3')
H = json.load(open(os.path.join(tmp, 'datos', 'sellout_history.json')))
assert [r['sku'] for r in H['rows']] == ['TMO30', 'TIM1501', 'TMO30'], H['rows']
assert abs(H['rows'][0]['vn'] - 1000) < 0.01 and abs(H['rows'][1]['vn'] - 100 / 0.7) < 0.01
# semana vacía (solo encabezado)
assert 'OK' in run('ingest_netsuite.py', xlsx('c.xlsx', []), f'{lun - dt.timedelta(weeks=2)}T11:00:00Z', 'th4')
# Odoo simulado: facturado TMO30H 3, consignación 2 -> vendió 6: facturar 2, revisar 1
os.makedirs(os.path.join(tmp, 'inputs'), exist_ok=True)
json.dump({'asof': dt.datetime.now(__import__('zoneinfo').ZoneInfo('America/Bogota')).date().isoformat(),
           'sellin': {'skus': {'TMO30H': [3, 3000], 'TIM1501': [10, 1000]}, 'ultima_factura': {}},
           'stock': {'TIM1501': {'available': 5}}, 'consignacion': {'casa_magna': {'TMO30H': 2}, 'otros_socios': {}, 'descuadre_vs_quants': {}},
           'por_despachar': [], 'pedidos': [], 'transito': [], 'catalogo': ['TMO30H', 'TIM1501']},
          open(os.path.join(tmp, 'inputs', 'odoo.json'), 'w'))
run('analyze.py'); A = json.load(open(os.path.join(tmp, 'output', 'analysis.json')))
t = {x['sku']: x for x in A['cmp']}
assert t['TMO30']['facturar_cons'] == 2 and t['TMO30']['sin_respaldo'] == 1 and t['TMO30']['est'] == 'Facturar consignación', t['TMO30']
assert t['TIM1501']['inv_cm'] == 9 and t['TIM1501']['reponer'] == 0
E = json.load(open(os.path.join(tmp, 'output', 'estado.json'))); assert E['enviable'], E
run('build_dashboard.py'); run('build_email.py')
M = json.load(open(os.path.join(tmp, 'output', 'email.json'))); assert 'Facturar consignación' in M['html'] and M['to']
print('SELFTEST OK:', tmp)
