#!/usr/bin/env python3
"""Agrega un reporte semanal NetSuite de Casa Magna al histórico (work/datos/sellout_history.json).

Uso: python3 ingest_netsuite.py <archivo.xlsx|.xls> <fecha_correo_ISO_UTC> <threadId>
  fecha_correo: el campo `date` del mensaje Gmail (p. ej. 2026-11-23T11:00:18Z); la "semana"
  es esa fecha en America/Bogota (lunes del correo).

Robustez:
  - Columnas por NOMBRE de encabezado (si NetSuite reordena, no se rompe); posicional solo como respaldo.
  - Acepta xlsx (con fila "Total") y el XML SpreadsheetML antiguo (.xls).
  - Idempotente por threadId y por semana. Rechaza un archivo idéntico (sha256) a otra semana con líneas:
    es el error histórico de bajar el adjunto de OTRO hilo.
  - MARGEN en fracción (0,3), en % (30) o texto ("30%").
Sale con código 0 si agregó o ya estaba; 2 si el archivo es inválido o duplicado (freno)."""
import sys, re, html, hashlib, datetime as dt, unicodedata
from common import cfg, norm_sku, jload, jsave, TZ

POS = ['FECHA', 'MARCA', 'PLAZA', 'ALMACEN', 'UBICACION', 'ARTICULO', 'DESCRIPCION', 'CANTIDAD', 'PRECIO',
       'SUBTOTAL', 'TOTAL_IVA', 'COSTO_UNIT', 'COSTO_TOTAL', 'MARGEN', 'REP']
ALIAS = {'FECHA': 'FECHA', 'MARCA': 'MARCA', 'PLAZA': 'PLAZA', 'ALMACEN': 'ALMACEN', 'UBICACION': 'UBICACION',
         'ARTICULO': 'ARTICULO', 'DESCRIPCION': 'DESCRIPCION', 'CANTIDAD': 'CANTIDAD', 'PRECIOUNITARIO': 'PRECIO',
         'SUBTOTAL': 'SUBTOTAL', 'TOTALCONIVA': 'TOTAL_IVA', 'COSTOUNITARIO': 'COSTO_UNIT', 'COSTOTOTAL': 'COSTO_TOTAL',
         'MARGEN': 'MARGEN', 'REPRESENTANTEDEVENTAS': 'REP'}
REQ = {'FECHA', 'ARTICULO', 'CANTIDAD', 'COSTO_TOTAL', 'MARGEN'}


def key(h):
    h = unicodedata.normalize('NFKD', str(h or '')).encode('ascii', 'ignore').decode().upper()
    return re.sub(r'[^A-Z]', '', h)


def todate(v):
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    s = str(v or '').strip()
    if re.fullmatch(r'\d{5}(\.0+)?', s):
        return (dt.datetime(1899, 12, 30) + dt.timedelta(days=int(float(s)))).date()
    m = re.match(r'(\d{4})-(\d\d)-(\d\d)', s) or None
    if m:
        return dt.date(int(m[1]), int(m[2]), int(m[3]))
    m = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', s)  # d/m/aaaa (NetSuite Colombia)
    return dt.date(int(m[3]), int(m[2]), int(m[1])) if m else None


def num(x):
    if x is None:
        return 0.0
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().replace('$', '').replace(' ', '')
    pct = s.endswith('%')
    s = s.rstrip('%')
    if s.count(',') and s.count('.'):
        s = s.replace('.', '').replace(',', '.') if s.rfind(',') > s.rfind('.') else s.replace(',', '')
    elif s.count(','):
        s = s.replace(',', '.')
    try:
        v = float(s)
    except ValueError:
        return 0.0
    return v / 100 if pct else v


def read_table(path):
    with open(path, 'rb') as f:
        raw = f.read()
    if raw[:2] == b'PK':
        import openpyxl, warnings
        warnings.filterwarnings('ignore')
        ws = openpyxl.load_workbook(path, data_only=True).worksheets[0]
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
    else:
        t = raw.decode('utf-8', 'replace')
        rows = [[html.unescape(re.sub(r'<[^>]+>', '', m)) for m in re.findall(r'<Data[^>]*>([\s\S]*?)</Data>', rm)]
                for rm in t.split('<Row')[1:]]
    return raw, rows


def map_header(rows):
    for i, r in enumerate(rows[:10]):
        m = {ALIAS[key(h)]: j for j, h in enumerate(r) if key(h) in ALIAS}
        if REQ <= set(m):
            return i, m
    return None, {k: j for j, k in enumerate(POS)}


def main(path, fecha_iso, thread):
    c = cfg()
    w = dt.datetime.fromisoformat(fecha_iso.replace('Z', '+00:00')).astimezone(TZ).date().isoformat()
    H = jload('datos/sellout_history.json', {'processed': [], 'rows': [], 'desc': {}})
    if thread in {p['thread'] for p in H['processed']} or w in {p.get('date') for p in H['processed']}:
        print(f'YA PROCESADO {w} {thread}')
        return 0
    raw, rows = read_table(path)
    sha = hashlib.sha256(raw).hexdigest()
    hi, col = map_header(rows)
    modo = 'nombre'
    if hi is None:
        if not any(r and todate(r[0]) for r in rows):
            if len(rows) <= 1:  # semana sin ventas: solo encabezado (o vacío)
                hi = len(rows)
            else:
                print(f'FRENO {w}: encabezados no reconocidos {str(rows[:1])[:200]}')
                return 2
        else:
            hi, modo = -1, 'posicional'
    data = rows[hi + 1:]
    out = []
    for r in data:
        g = lambda k: r[col[k]] if k in col and col[k] < len(r) else None
        d = todate(g('FECHA'))
        if d is None:
            continue  # fila Total / vacía
        sku = norm_sku(g('ARTICULO'), c['sku_aliases'])
        m = num(g('MARGEN'))
        m = m / 100 if m > 1.5 else m
        ct = num(g('COSTO_TOTAL'))
        vn = ct / (1 - m) if m < 1 and ct else num(g('SUBTOTAL'))
        out.append({'f': d.isoformat(), 'w': w, 'marca': str(g('MARCA') or '').strip(), 'plaza': str(g('PLAZA') or '').strip(),
                    'sku': sku, 'q': num(g('CANTIDAD')), 'vn': round(vn, 2), 'ct': round(ct, 2), 'rep': str(g('REP') or '').strip(),
                    '_desc': html.unescape(str(g('DESCRIPCION') or '')).strip()})
    if out:
        dup = [p for p in H['processed'] if p.get('sha') == sha and p.get('rows')]
        if dup:
            print(f'FRENO {w}: archivo idéntico al de la semana {dup[0]["date"]} (adjunto de otro hilo?)')
            return 2
        fuera = [r for r in out if not (dt.date.fromisoformat(w) - dt.timedelta(days=21) <= dt.date.fromisoformat(r['f']) <= dt.date.fromisoformat(w))]
        if len(fuera) > len(out) / 2:
            print(f'FRENO {w}: {len(fuera)}/{len(out)} líneas con fecha fuera de las 3 semanas previas al correo')
            return 2
    for r in out:
        H['desc'].setdefault(r['sku'], r.pop('_desc'))
        r.pop('_desc', None)
        H['rows'].append(r)
    H['processed'].append({'thread': thread, 'date': w, 'rows': len(out), 'sha': sha,
                           'header': modo})
    jsave('datos/sellout_history.json', H)
    print(f'OK {w}: {len(out)} líneas (histórico {len(H["rows"])} líneas, {len(H["processed"])} correos)')
    return 0


if __name__ == '__main__':
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    sys.exit(main(*sys.argv[1:]))
