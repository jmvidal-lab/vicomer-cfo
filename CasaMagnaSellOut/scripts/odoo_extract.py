#!/usr/bin/env python3
"""Odoo (SOLO LECTURA) -> work/inputs/odoo.json: todo lo que el cruce necesita de VINTRAL.

  sellin        facturas posted a Casa Magna (out_invoice - out_refund) desde `sellin_desde`, por SKU y mes
  stock         disponible VINTRAL (ubicaciones internas, sin consignación ni no vendibles) = cantidad - reservado
  consignacion  unidades de VINTRAL en CONSIGNACION/DESPACHO a nombre de Casa Magna (neto de movimientos)
  por_despachar facturado/pedido a Casa Magna con entrega pendiente (pickings de salida abiertos)
  pedidos       órdenes de venta de Casa Magna abiertas (cotización o por facturar)
  transito      líneas de compra VINTRAL confirmadas sin recibir (con ETA y bandera de ETA vencida)
  vieja         sell in de vintral1 (si hay ODOO_APIKEY_VINTRAL1; si no, se usa datos/sellin_vieja.json)
  catalogo      default_code de productos activos (para detectar SKUs vendidos que no existen en Odoo)

Solo usa search_read/read. Nunca create/write/unlink. Sale 0 si OK, 1 si Odoo principal falla."""
import os, sys, json, collections, datetime as dt
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import odoo_proxy  # noqa: F401  (enruta XML-RPC por el proxy de la nube)
import xmlrpc.client as X
from common import cfg, jsave, hoy

PERMITIDOS = {'search_read', 'read', 'search_count', 'fields_get'}


class Odoo:
    def __init__(self, url, db, login, key):
        self.url, self.db, self.key = url.rstrip('/'), db, key
        self.uid = X.ServerProxy(f'{self.url}/xmlrpc/2/common').authenticate(db, login, key, {})
        if not self.uid:
            raise RuntimeError(f'no autentica en {self.url}')
        self.m = X.ServerProxy(f'{self.url}/xmlrpc/2/object', allow_none=True)

    def __call__(self, model, method, args, kw=None):
        assert method in PERMITIDOS, f'método no permitido (solo lectura): {method}'
        return self.m.execute_kw(self.db, self.uid, self.key, model, method, args, kw or {})

    def sr(self, model, dom, fields, **kw):
        return self(model, 'search_read', [dom], {'fields': fields, **kw})


def code_of(od, pids, ctx):
    pids = sorted(set(pids))
    return {p['id']: (p.get('default_code') or f'ID{p["id"]}').strip()
            for p in (od('product.product', 'read', [pids, ['default_code']], {'context': ctx}) if pids else [])}


def sellin(od, partners, desde, hasta=None, company=None, ctx=None):
    dom = [['partner_id', 'child_of', partners], ['move_type', 'in', ['out_invoice', 'out_refund']], ['state', '=', 'posted']]
    if company:
        dom.append(['company_id', '=', company])
    moves = od.sr('account.move', dom, ['name', 'move_type', 'invoice_date'], context=ctx or {})
    previas = [m for m in moves if desde and (m['invoice_date'] or '') < desde]
    moves = [m for m in moves if not desde or (m['invoice_date'] or '') >= desde]
    if hasta:
        moves = [m for m in moves if (m['invoice_date'] or '') <= hasta]
    meta = {m['id']: m for m in moves}
    lines = od.sr('account.move.line', [['move_id', 'in', list(meta)], ['product_id', '!=', False], ['display_type', '=', 'product']],
                  ['product_id', 'quantity', 'price_subtotal', 'move_id'], context=ctx or {}) if meta else []
    code = code_of(od, [l['product_id'][0] for l in lines], ctx or {})
    skus = collections.defaultdict(lambda: [0.0, 0.0]); mes = collections.defaultdict(lambda: collections.defaultdict(float))
    ult = {}
    for l in lines:
        m = meta[l['move_id'][0]]; s = -1 if m['move_type'] == 'out_refund' else 1; k = code[l['product_id'][0]]
        skus[k][0] += s * l['quantity']; skus[k][1] += s * l['price_subtotal']
        mes[k][(m['invoice_date'] or '')[:7]] += s * l['quantity']
        ult[k] = max(ult.get(k, ''), m['invoice_date'] or '')
    fechas = sorted(m['invoice_date'] for m in moves if m['invoice_date'])
    return {'facturas': len(moves), 'notas_credito': sum(m['move_type'] == 'out_refund' for m in moves),
            'lineas': len(lines), 'primera': fechas[0] if fechas else None, 'ultima': fechas[-1] if fechas else None,
            'excluidas_antes_de_desde': len(previas),
            'skus': {k: [round(u, 2), round(v, 2)] for k, (u, v) in skus.items()},
            'por_mes': {k: dict(v) for k, v in mes.items()}, 'ultima_factura': ult}


def main():
    c = cfg(); o = c['odoo']; comp = o['company_id']; ctx = {'allowed_company_ids': [comp]}
    env = {k: os.environ.get(k) for k in ('ODOO_URL', 'ODOO_DB', 'ODOO_LOGIN', 'ODOO_APIKEY')}
    if not all(env.values()):
        print('FRENO: faltan variables ODOO_* en el environment:', [k for k, v in env.items() if not v])
        return 1
    od = Odoo(env['ODOO_URL'], env['ODOO_DB'], env['ODOO_LOGIN'], env['ODOO_APIKEY'])
    out = {'asof': hoy(), 'generado': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'), 'company_id': comp}

    out['sellin'] = sellin(od, o['partner_casa_magna'], o['sellin_desde'], company=comp, ctx=ctx)

    # stock propio disponible (excluye consignación y ubicaciones no vendibles)
    cons = o['ubicacion_consignacion_id']
    q = od.sr('stock.quant', [['company_id', '=', comp], ['location_id.usage', '=', 'internal'], ['quantity', '!=', 0]],
              ['product_id', 'location_id', 'quantity', 'reserved_quantity'], context=ctx)
    code = code_of(od, [x['product_id'][0] for x in q], ctx)
    stock = collections.defaultdict(lambda: {'onhand': 0.0, 'reservado': 0.0, 'available': 0.0, 'no_vendible': 0.0})
    for x in q:
        if x['location_id'][0] == cons:
            continue
        s = stock[code[x['product_id'][0]]]
        if x['location_id'][1] in o['ubicaciones_no_vendibles']:
            s['no_vendible'] += x['quantity']; continue
        s['onhand'] += x['quantity']; s['reservado'] += x['reserved_quantity']; s['available'] += x['quantity'] - x['reserved_quantity']
    out['stock'] = dict(stock)

    # consignación: neto de movimientos hechos hacia/desde la ubicación, por socio; se cuadra contra los quants
    mv = od.sr('stock.move', ['|', ['location_dest_id', '=', cons], ['location_id', '=', cons], ['state', '=', 'done'], ['company_id', '=', comp]],
               ['product_id', 'quantity', 'location_dest_id', 'partner_id', 'picking_id'], context=ctx)
    pk = {p['id']: p for p in od('stock.picking', 'read', [sorted({m['picking_id'][0] for m in mv if m['picking_id']}), ['partner_id']], {'context': ctx})} if mv else {}
    cm_ids = {p['id'] for p in od.sr('res.partner', [['id', 'child_of', o['partner_casa_magna']]], ['id'], context={'active_test': False})}
    code.update(code_of(od, [m['product_id'][0] for m in mv], ctx))
    por_socio = collections.defaultdict(lambda: collections.defaultdict(float))
    for m in mv:
        p = m['partner_id'] or (m['picking_id'] and pk[m['picking_id'][0]]['partner_id']) or [0, 'SIN SOCIO']
        s = 1 if m['location_dest_id'][0] == cons else -1
        por_socio[('CM' if p[0] in cm_ids else p[1])][code[m['product_id'][0]]] += s * m['quantity']
    quant_cons = collections.defaultdict(float)
    for x in q:
        if x['location_id'][0] == cons:
            quant_cons[code[x['product_id'][0]]] += x['quantity']
    neto = collections.defaultdict(float)
    for d in por_socio.values():
        for k, v in d.items():
            neto[k] += v
    descuadre = {k: [round(neto.get(k, 0), 2), round(quant_cons.get(k, 0), 2)] for k in set(neto) | set(quant_cons)
                 if abs(neto.get(k, 0) - quant_cons.get(k, 0)) > 0.01}
    out['consignacion'] = {'casa_magna': {k: v for k, v in por_socio.get('CM', {}).items() if abs(v) > 0.01},
                           'otros_socios': {s: {k: v for k, v in d.items() if abs(v) > 0.01} for s, d in por_socio.items() if s != 'CM'},
                           'descuadre_vs_quants': descuadre}

    # entregas pendientes a Casa Magna
    pks = od.sr('stock.picking', [['partner_id', 'child_of', o['partner_casa_magna']], ['picking_type_code', '=', 'outgoing'],
                                  ['state', 'not in', ['done', 'cancel']], ['company_id', '=', comp]],
                ['name', 'origin', 'scheduled_date', 'state'], context=ctx)
    pm = od.sr('stock.move', [['picking_id', 'in', [p['id'] for p in pks]], ['state', 'not in', ['done', 'cancel']]],
               ['picking_id', 'product_id', 'product_uom_qty'], context=ctx) if pks else []
    code.update(code_of(od, [m['product_id'][0] for m in pm], ctx))
    pki = {p['id']: p for p in pks}
    out['por_despachar'] = [{'sku': code[m['product_id'][0]], 'u': m['product_uom_qty'], 'picking': m['picking_id'][1],
                             'origen': pki[m['picking_id'][0]]['origin'], 'fecha': (pki[m['picking_id'][0]]['scheduled_date'] or '')[:10],
                             'estado': pki[m['picking_id'][0]]['state']} for m in pm]

    # pedidos de venta abiertos de Casa Magna
    so = od.sr('sale.order', [['partner_id', 'child_of', o['partner_casa_magna']], ['company_id', '=', comp],
                              '|', ['state', 'in', ['draft', 'sent']], '&', ['state', '=', 'sale'], ['invoice_status', '=', 'to invoice']],
               ['name', 'state', 'date_order', 'amount_untaxed', 'invoice_status'], context=ctx)
    sol = od.sr('sale.order.line', [['order_id', 'in', [s['id'] for s in so]], ['product_id', '!=', False]],
                ['order_id', 'product_id', 'product_uom_qty', 'qty_invoiced'], context=ctx) if so else []
    code.update(code_of(od, [l['product_id'][0] for l in sol], ctx))
    out['pedidos'] = [{'pedido': s['name'], 'estado': 'cotizacion' if s['state'] in ('draft', 'sent') else 'por_facturar',
                       'fecha': s['date_order'][:10], 'valor': s['amount_untaxed'],
                       'lineas': [{'sku': code[l['product_id'][0]], 'u': l['product_uom_qty'] - l['qty_invoiced']}
                                  for l in sol if l['order_id'][0] == s['id'] and l['product_uom_qty'] - l['qty_invoiced'] > 0]} for s in so]

    # tránsito: compras confirmadas sin recibir
    pol = od.sr('purchase.order.line', [['company_id', '=', comp], ['order_id.state', 'in', ['purchase', 'done']], ['product_id', '!=', False]],
                ['order_id', 'partner_id', 'product_id', 'product_qty', 'qty_received', 'date_planned'], context=ctx)
    pol = [l for l in pol if l['product_qty'] - l['qty_received'] > 0.001]
    code.update(code_of(od, [l['product_id'][0] for l in pol], ctx))
    out['transito'] = [{'sku': code[l['product_id'][0]], 'units': l['product_qty'] - l['qty_received'], 'eta': (l['date_planned'] or '')[:10],
                        'ref': l['order_id'][1], 'proveedor': l['partner_id'][1], 'eta_vencida': (l['date_planned'] or '9')[:10] < out['asof']}
                       for l in pol]

    out['catalogo'] = sorted({p['default_code'] for p in od.sr('product.product', [['default_code', '!=', False]], ['default_code'],
                                                                context={'active_test': False}) if p['default_code']})

    # instancia vieja (opcional)
    v = o['vieja']; key = os.environ.get(v['variable_entorno'])
    if key:
        try:
            ov = Odoo(v['url'], v['db'], env['ODOO_LOGIN'], key)
            out['vieja'] = {'asof': hoy(), **sellin(ov, v['partner_child_of'], v['desde'], v['hasta'])}
        except Exception as e:
            out['vieja_error'] = f'{type(e).__name__}: {str(e)[:150]}'

    jsave('inputs/odoo.json', out, pretty=True)
    s = out['sellin']; cmc = out['consignacion']['casa_magna']
    print(f"OK Odoo {out['asof']} | sell in {s['facturas']} facturas ({s['notas_credito']} NC) {s['primera']}..{s['ultima']}, "
          f"{sum(u for u, _ in s['skus'].values()):.0f} u | consignación CM {sum(cmc.values()):.0f} u | por despachar "
          f"{sum(x['u'] for x in out['por_despachar']):.0f} u | pedidos abiertos {len(out['pedidos'])} | tránsito "
          f"{sum(t['units'] for t in out['transito']):.0f} u | vieja {'consultada' if 'vieja' in out else 'congelada'}")
    if out['consignacion']['descuadre_vs_quants']:
        print('AVISO consignación: movimientos no cuadran con quants:', out['consignacion']['descuadre_vs_quants'])
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        print(f'FRENO Odoo: {type(e).__name__}: {str(e)[:200]}')
        sys.exit(1)
