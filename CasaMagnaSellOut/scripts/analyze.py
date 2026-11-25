#!/usr/bin/env python3
"""Histórico sell out + Odoo -> work/output/analysis.json y work/output/estado.json (puertas de envío).

Modelo por SKU (unidades, SKU normalizado):
  inv_cm        = facturado (vieja+nueva) + consignación en CM - vendido     (inventario estimado en Casa Magna)
  facturar_cons = min(vendido - facturado, consignación)  -> CM vendió unidades en consignación: hay que FACTURAR
  sin_respaldo  = vendido - facturado - consignación (>0)  -> ventas sin abastecimiento registrado: REVISAR datos
  rotación      = unidades/semana de las últimas `semanas_rotacion` semanas de reporte
  reponer       = rotación x `semanas_objetivo_cm` - max(inv_cm,0) - pedidos abiertos   (>0)
                  se cubre con stock propio disponible -> tránsito -> POR COMPRAR
"""
import math, collections as C, datetime as dt
from common import cfg, norm_sku, excluded, jload, jsave, hoy


def main():
    c = cfg(); M = c['modelo']; al = c['sku_aliases']; N = lambda s: norm_sku(s, al)
    H = jload('datos/sellout_history.json'); O = jload('inputs/odoo.json')
    frenos, alertas = [], []
    if not H or not H.get('rows'):
        raise SystemExit('FRENO: sin histórico de sell out')
    if not O:
        frenos.append('No hay extracción de Odoo (inputs/odoo.json).'); O = {}
    elif O.get('asof') != hoy():
        frenos.append(f"La extracción de Odoo es del {O.get('asof')}, no de hoy ({hoy()}).")
    rows = [r for r in H['rows'] if not excluded(r['sku'], c)]; desc = H['desc']

    # ---- sell in
    vieja = O.get('vieja') or jload('datos/sellin_vieja.json') or {}
    if not vieja:
        alertas.append('Sin sell in de la instancia vieja (jun-25..mar-26): la cobertura queda subestimada.')
    sin = C.defaultdict(lambda: [0.0, 0.0]); ult_fact = {}
    for src in (vieja, O.get('sellin', {})):
        for k, (u, v) in src.get('skus', {}).items():
            n = N(k)
            if excluded(n, c):
                continue
            sin[n][0] += u; sin[n][1] += v
    for k, d in O.get('sellin', {}).get('ultima_factura', {}).items():
        ult_fact[N(k)] = max(ult_fact.get(N(k), ''), d)
    def suma(pairs):
        o = C.defaultdict(float)
        for k, v in pairs:
            o[N(k)] += v
        return o
    cons = suma((O.get('consignacion', {}).get('casa_magna') or {}).items())
    stock = suma((k, max(0.0, s['available'])) for k, s in (O.get('stock') or {}).items())
    desp = suma((x['sku'], x['u']) for x in O.get('por_despachar', []))
    ped = suma((l['sku'], l['u']) for p in O.get('pedidos', []) for l in p['lineas'])
    trans_l = O.get('transito', []); trans = suma((t['sku'], t['units']) for t in trans_l)

    # ---- sell out y rotación
    sout = C.defaultdict(lambda: [0.0, 0.0]); last_sale = {}
    for r in rows:
        sout[r['sku']][0] += r['q']; sout[r['sku']][1] += r['vn']; last_sale[r['sku']] = max(last_sale.get(r['sku'], ''), r['f'])
    semanas = sorted({p['date'] for p in H['processed'] if p.get('date')} | {r['w'] for r in H['rows']})
    ult = semanas[-1]
    ventana = [w for w in semanas if w > (dt.date.fromisoformat(ult) - dt.timedelta(weeks=M['semanas_rotacion'])).isoformat()]
    nwin = M['semanas_rotacion']; rot = C.defaultdict(float)  # semanas calendario (NetSuite reporta cada lunes)
    for r in rows:
        if r['w'] in ventana:
            rot[r['sku']] += r['q'] / nwin

    cmp = []
    for k in sorted(set(sin) | set(sout) | set(cons)):
        i, o = sin.get(k, [0, 0]), sout.get(k, [0, 0]); cg = cons.get(k, 0.0)
        inv_cm = i[0] + cg - o[0]; falta = max(0.0, o[0] - i[0])
        fc = min(falta, cg); sr = max(0.0, falta - cg); r8 = max(0.0, rot.get(k, 0.0))
        cob = (max(inv_cm, 0) / r8) if r8 > 0 else None
        rep = max(0, math.ceil(r8 * M['semanas_objetivo_cm'] - max(inv_cm, 0) - ped.get(k, 0))) if r8 > 0 else 0
        ds = min(rep, stock.get(k, 0)); dtr = min(rep - ds, trans.get(k, 0)); pc = rep - ds - dtr
        if fc > 0: est = 'Facturar consignación'
        elif sr > 0: est = 'Revisar'
        elif rep > 0: est = 'Reponer'
        elif inv_cm > 0 and (r8 == 0 or (cob or 0) > M['semanas_sobrestock']): est = 'Sobre-stock CM' if r8 > 0 else 'Sin rotación'
        else: est = 'OK'
        cmp.append({'sku': k, 'desc': desc.get(k, ''), 'inu': round(i[0], 2), 'outu': round(o[0], 2), 'inv': round(i[1]), 'outv': round(o[1]),
                    'gap': round(i[0] - o[0], 2), 'consig': cg, 'inv_cm': round(inv_cm, 2), 'facturar_cons': fc, 'sin_respaldo': sr,
                    'rot_sem': round(r8, 2), 'cob_sem': round(cob, 1) if cob is not None else None, 'pedido_abierto': ped.get(k, 0),
                    'por_despachar': desp.get(k, 0), 'stock_propio': stock.get(k, 0), 'transito': trans.get(k, 0),
                    'reponer': rep, 'desde_stock': ds, 'desde_transito': dtr, 'por_comprar': pc, 'est': est,
                    'ult_venta': last_sale.get(k), 'ult_factura': ult_fact.get(k)})

    # ---- KPIs
    vn = sum(r['vn'] for r in rows); ct = sum(r['ct'] for r in rows)
    sem_vn = C.defaultdict(float); sem_u = C.defaultdict(float)
    for r in rows:
        sem_vn[r['w']] += r['vn']; sem_u[r['w']] += r['q']
    serie = [(w, round(sem_vn.get(w, 0)), sem_u.get(w, 0)) for w in semanas]
    l4 = sum(sem_vn.get(w, 0) for w in semanas[-4:]); p4 = sum(sem_vn.get(w, 0) for w in semanas[-8:-4])
    TI = sum(x['inu'] for x in cmp); TO = sum(x['outu'] for x in cmp)
    def mix(key):
        o = C.Counter()
        for r in rows:
            o[r[key]] += r['vn']
        return o.most_common()
    proc = [p for p in H['processed'] if p.get('date')]
    kpi = {'venta_neta': vn, 'margen': 1 - ct / vn if vn else 0, 'unidades': sum(r['q'] for r in rows), 'lineas': len(rows),
           'in_u': TI, 'out_u': TO, 'cobertura': TI / TO if TO else 0, 'consig_cm_u': sum(cons.values()),
           'consig_cm_valor_est': round(sum(x['consig'] * (x['inv'] / x['inu']) for x in cmp if x['inu'] > 0 and x['consig'] > 0)),
           'facturar_cons_u': sum(x['facturar_cons'] for x in cmp), 'reponer_u': sum(x['reponer'] for x in cmp),
           'por_comprar_u': sum(x['por_comprar'] for x in cmp), 'por_despachar_u': sum(desp.values()),
           'ult_sem_u': sem_u.get(ult, 0), 'ult_sem_vn': sem_vn.get(ult, 0), 'l4_vn': l4, 'p4_vn': p4,
           'var_4s': (l4 / p4 - 1) if p4 else None, 'semanas_ventana': nwin,
           'periodo': [min(r['f'] for r in rows), max(r['f'] for r in rows)]}

    # ---- puertas y alertas
    fecha_corte = max((p['date'] for p in proc), default=ult)
    edad = (dt.date.fromisoformat(hoy()) - dt.date.fromisoformat(fecha_corte)).days
    if edad > c['gmail']['max_dias_ultimo_reporte']:
        frenos.append(f'El último reporte NetSuite procesado es del {fecha_corte} ({edad} días): no llegó el de esta semana.')
    lunes = dt.date.fromisoformat(fecha_corte)
    esperadas = [(lunes - dt.timedelta(weeks=j)).isoformat() for j in range(1, 8)]
    primera_fechada = min((p['date'] for p in proc), default=fecha_corte)
    faltan = [w for w in esperadas if w >= primera_fechada and w not in semanas]
    if faltan:
        alertas.append('Faltan reportes NetSuite de las semanas: ' + ', '.join(sorted(faltan)) + '.')
    prev = [v for w, v, _ in serie[-13:-1]]
    if prev and sem_vn.get(ult, 0) > M['factor_alerta_semana'] * max(1, sum(prev) / len(prev)):
        alertas.append(f'Venta de la semana {ult} es {sem_vn[ult] / (sum(prev) / len(prev)):.1f}x el promedio de 12 semanas: verificar.')
    cat = {N(x) for x in O.get('catalogo', [])}
    sin_match = sorted({r['sku'] for r in rows if r['w'] in ventana} - cat) if cat else []
    if sin_match:
        alertas.append('SKUs vendidos que no existen en Odoo (revisar alias en config.json): ' + ', '.join(sin_match) + '.')
    if O.get('consignacion', {}).get('descuadre_vs_quants'):
        alertas.append('La consignación por movimientos no cuadra con el saldo de la ubicación en Odoo: ' +
                       ', '.join(O['consignacion']['descuadre_vs_quants']) + '.')
    venc = sorted({f"{t['ref']} ({t['sku']}, ETA {t['eta']})" for t in trans_l if t['eta_vencida']})
    if venc:
        alertas.append('Compras en tránsito con ETA vencida en Odoo (¿recibidas sin registrar o atrasadas?): ' + '; '.join(venc) + '.')
    viejos = [p for p in O.get('pedidos', []) if p['estado'] == 'por_facturar' and p['fecha'] < (dt.date.fromisoformat(hoy()) - dt.timedelta(days=30)).isoformat()]
    if viejos:
        alertas.append('Pedidos confirmados de Casa Magna sin facturar hace >30 días: ' + ', '.join(f"{p['pedido']} ({p['fecha']})" for p in viejos) + '.')
    lim = (dt.date.fromisoformat(hoy()) - dt.timedelta(days=30)).isoformat()
    viejas = sorted({f"{x['picking']} ({x['sku']}, {x['fecha']})" for x in O.get('por_despachar', []) if x['fecha'] and x['fecha'] < lim})
    if viejas:
        alertas.append(f'Entregas a Casa Magna abiertas en Odoo hace >30 días ({len(viejas)}): ' + '; '.join(viejas) + '. ¿Despachadas sin validar o pendientes reales?')
    if O.get('vieja_error'):
        alertas.append('No se pudo consultar vintral1; se usó el histórico congelado. ' + O['vieja_error'])
    if O.get('sellin', {}).get('excluidas_antes_de_desde'):
        alertas.append(f"Odoo principal tiene {O['sellin']['excluidas_antes_de_desde']} facturas a Casa Magna antes de {c['odoo']['sellin_desde']} (excluidas para no duplicar con vintral1).")
    revisar = [x['sku'] for x in cmp if x['est'] == 'Revisar']
    if revisar:
        alertas.append('SKUs con ventas sin abastecimiento registrado (sell out > facturado + consignación): ' + ', '.join(revisar) +
                       '. Probable stock previo a jun-2025 o facturas fuera de Casa Magna.')

    res = {'fecha': fecha_corte, 'hoy': hoy(), 'ultima_semana': ult, 'n_correos': len(H['processed']),
           'asof_sellin': {'vieja': vieja.get('asof'), 'nueva': O.get('asof')}, 'odoo_sellin': {k: v for k, v in O.get('sellin', {}).items() if k not in ('skus', 'por_mes', 'ultima_factura')},
           'kpi': kpi, 'marca': mix('marca'), 'plaza': mix('plaza'), 'rep': mix('rep')[:10], 'semanas': serie,
           'cmp': cmp, 'pedidos': O.get('pedidos', []), 'por_despachar': O.get('por_despachar', []), 'transito': trans_l,
           'consig_otros': O.get('consignacion', {}).get('otros_socios', {}),
           'alertas': alertas, 'frenos': frenos, 'rows': rows, 'desc': desc, 'modelo': M}
    jsave('output/analysis.json', res)
    jsave('output/estado.json', {'fecha_corte': fecha_corte, 'hoy': hoy(), 'enviable': not frenos, 'frenos': frenos, 'alertas': alertas,
                                 'modo': c['envio']['modo']}, pretty=True)
    k = kpi
    print(f"OK corte {fecha_corte} | venta neta {k['venta_neta']:,.0f} | in {TI:.0f} / out {TO:.0f} u | consignación CM {k['consig_cm_u']:.0f} u | "
          f"facturar consignación {k['facturar_cons_u']:.0f} u | reponer {k['reponer_u']} u (comprar {k['por_comprar_u']}) | frenos {len(frenos)} alertas {len(alertas)}")
    for f in frenos: print('  FRENO:', f)
    for a in alertas: print('  ALERTA:', a)


if __name__ == '__main__':
    main()
