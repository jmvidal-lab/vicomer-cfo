#!/usr/bin/env python3
"""work/output/analysis.json -> work/output/email.json {to, cc, subject, html, text} (correo al equipo)."""
from common import jload, jsave, cfg

A = jload('output/analysis.json'); k = A['kpi']; c = cfg(); E = c['envio']
f0 = lambda n: f'{round(n or 0):,}'.replace(',', '.')
fm = lambda n: '$' + f'{(n or 0) / 1e6:,.1f}'.replace(',', 'X').replace('.', ',').replace('X', '.') + ' M'
x2 = lambda v: f'{v:.2f}'.replace('.', ',')
pc = lambda x: '—' if x is None else f'{x * 100:+.1f}'.replace('.', ',') + '%'
TH = 'padding:6px 8px;text-align:%s;background:#0f6b5c;color:#fff;font-weight:600;font-size:12px'
TD = 'padding:6px 8px;border-bottom:1px solid #dfe5e2;text-align:%s;font-size:13px'


def table(head, rows, al):
    h = ''.join(f'<th style="{TH % a}">{x}</th>' for x, a in zip(head, al))
    b = ''.join('<tr>' + ''.join(f'<td style="{TD % a}">{v}</td>' for v, a in zip(r, al)) + '</tr>' for r in rows)
    return f'<table style="border-collapse:collapse;width:100%;margin:6px 0 10px">{h and "<tr>" + h + "</tr>"}{b}</table>'


cmp = A['cmp']; top = c['params']['top_filas_correo']
fac = [x for x in cmp if x['facturar_cons'] > 0]
rep = sorted([x for x in cmp if x['reponer'] > 0], key=lambda x: -x['reponer'])
rev = [x for x in cmp if x['est'] == 'Revisar']
sob = sorted([x for x in cmp if x['est'] in ('Sobre-stock CM', 'Sin rotación') and x['inv_cm'] > 0], key=lambda x: -x['inv_cm'] * (x['inv'] / x['inu'] if x['inu'] else 0))

acciones = []
if fac:
    acciones.append(f'<b>Facturar consignación</b> ({f0(sum(x["facturar_cons"] for x in fac))} u): Casa Magna vendió más de lo facturado y tiene esas referencias en consignación. ' +
                    ', '.join(f'{x["sku"]} ×{f0(x["facturar_cons"])}' for x in fac) + '.')
if rep:
    acciones.append(f'<b>Reponer</b> ({f0(sum(x["reponer"] for x in rep))} u para {A["modelo"]["semanas_objetivo_cm"]} semanas de cobertura): ' +
                    ', '.join(f'{x["sku"]} ×{f0(x["reponer"])}' + (f' (comprar {f0(x["por_comprar"])})' if x['por_comprar'] else ' (hay stock VINTRAL)' if x['desde_stock'] else '') for x in rep) + '.')
if rev:
    acciones.append('<b>Revisar datos</b>: ' + ', '.join(f'{x["sku"]} (vendidas {f0(x["outu"])}, facturadas {f0(x["inu"])})' for x in rev) + '.')
if not acciones:
    acciones.append('Sin faltantes: ningún SKU necesita reposición ni facturación de consignación esta semana.')

blk_rows = [[f'<b>{x["sku"]}</b>', x['desc'][:38], f'<span style="color:#b3261e;font-weight:600">{x["est"]}</span>', f0(x['outu']), f0(x['inu']), f0(x['consig']),
             f0(x['inv_cm']), (f0(x['cob_sem']) if x['cob_sem'] is not None else '—'), f0(x['stock_propio']), f0(x['transito']), f0(x['facturar_cons'] or x['reponer'])]
            for x in (fac + rep + rev)[:top]]
head = ['SKU', 'Descripción', 'Acción', 'Vendidas', 'Facturadas', 'Consig.', 'Inv. CM', 'Cob. sem', 'Stock VINTRAL', 'Tránsito', 'Unid.']
al = ['left', 'left', 'left'] + ['right'] * 8
sob_rows = [[f'<b>{x["sku"]}</b>', x['desc'][:38], f0(x['inv_cm']), f0(x['consig']), (f0(x['cob_sem']) if x['cob_sem'] else 'sin rotación neta 12 sem.'), x['ult_venta'] or '—']
            for x in sob[:8]]
ops = []
if A['por_despachar']:
    ops.append(f'{f0(sum(x["u"] for x in A["por_despachar"]))} u facturadas/pedidas aún por despachar a Casa Magna ({len({x["picking"] for x in A["por_despachar"]})} entregas abiertas en Odoo).')
cot = [p for p in A['pedidos'] if p['estado'] == 'cotizacion' and p['valor']]
if cot:
    ops.append(f'{len(cot)} cotizaciones abiertas a Casa Magna por {fm(sum(p["valor"] for p in cot))}: ' + ', '.join(p['pedido'] for p in cot) + '.')
alertas = ''.join(f'<li>{a}</li>' for a in A['alertas'])

html = (f'<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#16201d;max-width:780px">'
        f'<p>Equipo,</p><p>Seguimiento semanal de Casa Magna con corte al lunes {A["fecha"]} (sell out NetSuite) y Odoo al {A["hoy"]}. '
        f'Primero lo que hay que hacer; abajo, el contexto.</p>'
        f'<div style="border:2px solid #0f6b5c;border-radius:8px;padding:12px 14px;margin:12px 0;background:#f2f8f6">'
        f'<h3 style="margin:0 0 6px;color:#0f6b5c">Acciones de la semana</h3><ul style="margin:0 0 6px 18px;padding:0">' + ''.join(f'<li style="margin:3px 0">{a}</li>' for a in acciones) + '</ul>'
        + (table(head, blk_rows, al) if blk_rows else '') +
        f'<p style="margin:6px 0 0;font-size:13px"><b>Inventario estimado en Casa Magna:</b> {f0(sum(max(0, x["inv_cm"]) for x in cmp))} u, de las cuales {f0(k["consig_cm_u"])} u son consignación de VINTRAL '
        f'(≈ {fm(k["consig_cm_valor_est"])} a precio de factura). Cobertura In/Out {x2(k["cobertura"])}x.</p></div>'
        + (f'<h3 style="margin:16px 0 4px">Mayor inventario parado en Casa Magna</h3>' + table(['SKU', 'Descripción', 'Inv. CM', 'Consig.', 'Cob. sem', 'Últ. venta'], sob_rows, ['left', 'left', 'right', 'right', 'right', 'right']) if sob_rows else '')
        + (f'<h3 style="margin:16px 0 4px">Operación</h3><ul style="margin:0 0 8px 18px;padding:0">' + ''.join(f'<li>{o}</li>' for o in ops) + '</ul>' if ops else '')
        + f'<h3 style="margin:16px 0 4px">Contexto comercial</h3><ul style="margin:0 0 8px 18px;padding:0">'
        f'<li>Últimas 4 semanas: <b>{fm(k["l4_vn"])}</b> ({pc(k["var_4s"])} vs las 4 previas). Última semana: {f0(k["ult_sem_u"])} u / {fm(k["ult_sem_vn"])}.</li>'
        f'<li>Acumulado desde {k["periodo"][0]}: {fm(k["venta_neta"])} sin IVA, {f0(k["unidades"])} u, margen Casa Magna {pc(k["margen"]).lstrip("+")}.</li>'
        f'<li>Marcas: ' + ', '.join(f'{a} {b / k["venta_neta"] * 100:.0f}%' for a, b in A['marca'][:3]) + '. Plazas: ' + ', '.join(f'{a} {b / k["venta_neta"] * 100:.0f}%' for a, b in A['plaza'][:4]) + '.</li></ul>'
        + (f'<h3 style="margin:16px 0 4px">Alertas de datos</h3><ul style="margin:0 0 8px 18px;padding:0;color:#5d6b66;font-size:13px">{alertas}</ul>' if alertas else '')
        + f'<p style="font-size:12px;color:#5d6b66">Fuentes: {A["n_correos"]} reportes NetSuite "Ventas semana anterior"; Odoo VINTRAL (facturas, consignación, stock, entregas, compras). '
        f'Inv. CM = facturado + consignación − vendido (estimado). Dashboard interactivo en el adjunto (.zip).</p><p>Saludos,<br>Juan Marcelo</p></div>')

def plain(a):
    import re, html as H
    return H.unescape(re.sub(r'<[^>]+>', '', a))
text = (f'Casa Magna - seguimiento semanal (corte {A["fecha"]}, Odoo al {A["hoy"]}).\n\nACCIONES\n' + '\n'.join('- ' + plain(a) for a in acciones) +
        f'\n\nInventario estimado en Casa Magna: {f0(sum(max(0, x["inv_cm"]) for x in cmp))} u ({f0(k["consig_cm_u"])} u en consignación). Cobertura In/Out {x2(k["cobertura"])}x.\n'
        + ('\nOPERACION\n' + '\n'.join('- ' + o for o in ops) + '\n' if ops else '')
        + f'\nCONTEXTO\n- Ultimas 4 semanas: {fm(k["l4_vn"])} ({pc(k["var_4s"])} vs 4 previas).\n- Acumulado: {fm(k["venta_neta"])} sin IVA.\n'
        + ('\nALERTAS\n' + '\n'.join('- ' + a for a in A['alertas']) + '\n' if A['alertas'] else '') + '\nDashboard interactivo adjunto (.zip).\n\nSaludos,\nJuan Marcelo')
subject = f'Casa Magna — Sell In vs Sell Out | semana al {A["fecha"]}' + (' | acciones: ' + ', '.join(
    s for s, n in (('facturar', len(fac)), ('reponer', len(rep)), ('revisar', len(rev))) if n) if (fac or rep or rev) else '')
jsave('output/email.json', {'to': E['to'], 'cc': E['cc'], 'subject': subject, 'html': html, 'text': text}, pretty=True)
print('OK correo:', subject)
