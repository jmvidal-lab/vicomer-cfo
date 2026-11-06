import json, collections, datetime, sys, statistics
S=sys.argv[1]; sys.path.insert(0,S); from cats import cat, brand
L=lambda n: json.load(open(f"{S}/odoo/{n}.json"))
inv=L("invoices"); lines=L("invoice_lines"); prods={p["id"]:p for p in L("products")}; quants=L("quants"); locs={l["id"]:l for l in L("locations")}
svl=L("svl"); so=L("sale_orders"); sol=L("sale_lines"); pick=L("pickings"); partners={p["id"]:p for p in L("partners")}
CO={1:"Colombia",2:"Ecuador",3:"Costa Rica",11:"VIX",12:"PN-MRV",13:"PN-JMV"}
TODAY=datetime.date(2026,11,6)
def d(s): return datetime.date.fromisoformat(s[:10]) if s else None
IC=lambda name: any(k in (name or "").upper() for k in ["VICOMER","VINTRAL","3-102-940094","VIX S.A.S"])
inv_by={i["id"]:i for i in inv}
out={}
print("="*30,"VENTAS ODOO por compañía/mes (untaxed signed, out_invoice+out_refund)")
for c in (2,1,3):
    rows=[i for i in inv if i["company_id"][0]==c and i["move_type"] in ("out_invoice","out_refund")]
    m=collections.defaultdict(float); mic=collections.defaultdict(float); n=collections.Counter()
    for i in rows:
        k=i["invoice_date"][:7]; v=i["amount_untaxed_signed"]; m[k]+=v; n[k]+=1
        if IC(i["partner_id"][1]): mic[k]+=v
    print(f"\n{CO[c]}:")
    for k in sorted(m): print(f"  {k} ventas {m[k]:>16,.0f}  (intercompañía {mic[k]:>14,.0f} | terceros {m[k]-mic[k]:>16,.0f})  docs {n[k]}")
    out[f"ventas_mes_{c}"]={k:[round(m[k]),round(mic[k])] for k in sorted(m)}
    # clientes
    cl=collections.defaultdict(float)
    for i in rows: cl[i["partner_id"][1]]+=i["amount_untaxed_signed"]
    tot=sum(cl.values()); tot3=sum(v for k,v in cl.items() if not IC(k))
    hhi=sum((v/tot3*100)**2 for k,v in cl.items() if not IC(k) and v>0) if tot3 else 0
    print(f"  CLIENTES (total {tot:,.0f}; terceros {tot3:,.0f}; HHI terceros {hhi:,.0f}; n={len(cl)})")
    for k,v in sorted(cl.items(),key=lambda kv:-kv[1])[:12]: print(f"     {v:>16,.0f} {v/tot*100:5.1f}%  {k[:45]}{'  [IC]' if IC(k) else ''}")
    out[f"clientes_{c}"]=sorted(((k,round(v)) for k,v in cl.items()),key=lambda kv:-kv[1])
    # vendedores
    vd=collections.defaultdict(float)
    for i in rows: vd[(i["invoice_user_id"] or [0,"(sin vendedor)"])[1]]+=i["amount_untaxed_signed"]
    print("  VENDEDORES:",{k[:22]:round(v) for k,v in sorted(vd.items(),key=lambda kv:-kv[1])})
    # términos de pago
    pt=collections.defaultdict(float)
    for i in rows: pt[(i["invoice_payment_term_id"] or [0,"(sin término)"])[1]]+=i["amount_untaxed_signed"]
    print("  TÉRMINOS PAGO:",{k[:30]:round(v) for k,v in sorted(pt.items(),key=lambda kv:-kv[1])[:6]})
    # plazo real de cobro: facturas pagadas -> no tenemos fecha pago; usamos DSO: cartera / ventas 90d *90
    cart=[i for i in rows if abs(i["amount_residual_signed"])>0.5]
    ar=sum(i["amount_residual_signed"] for i in cart)
    v90=sum(i["amount_untaxed_signed"]*(1.15 if c==2 else 1.19 if c==1 else 1.13) for i in rows if d(i["invoice_date"])>=TODAY-datetime.timedelta(days=90))
    print(f"  CARTERA abierta {ar:,.0f} | ventas c/IVA aprox 90d {v90:,.0f} | DSO aprox {ar/v90*90 if v90 else 0:.0f} d")
    buckets=collections.defaultdict(float); bypart=collections.defaultdict(lambda:[0.0,0.0])
    for i in cart:
        due=d(i["invoice_date_due"]) or d(i["invoice_date"]); dpd=(TODAY-due).days
        b="no vencido" if dpd<=0 else "1-30" if dpd<=30 else "31-60" if dpd<=60 else "61-90" if dpd<=90 else "91-180" if dpd<=180 else ">180"
        buckets[b]+=i["amount_residual_signed"]; bypart[i["partner_id"][1]][0]+=i["amount_residual_signed"]
        if dpd>0: bypart[i["partner_id"][1]][1]+=i["amount_residual_signed"]
    print("  AGING:",{k:round(v) for k,v in buckets.items()}, f"| vencido {sum(v for k,v in buckets.items() if k!='no vencido')/ar*100 if ar else 0:.0f}%")
    for k,v in sorted(bypart.items(),key=lambda kv:-kv[1][0])[:8]: print(f"     cartera {v[0]:>14,.0f} vencido {v[1]:>14,.0f}  {k[:40]}")
    out[f"aging_{c}"]=dict(buckets); out[f"cartera_cli_{c}"]={k:v for k,v in sorted(bypart.items(),key=lambda kv:-kv[1][0])[:15]}
    # CxP
    ap=[i for i in inv if i["company_id"][0]==c and i["move_type"] in ("in_invoice","in_refund") and abs(i["amount_residual_signed"])>0.5]
    apt=sum(-i["amount_residual_signed"] for i in ap); byp=collections.defaultdict(lambda:[0.0,0.0])
    for i in ap:
        due=d(i["invoice_date_due"]) or d(i["invoice_date"]); byp[i["partner_id"][1]][0]+=-i["amount_residual_signed"]
        if (TODAY-due).days>0: byp[i["partner_id"][1]][1]+=-i["amount_residual_signed"]
    compras12=sum(-i["amount_untaxed_signed"] for i in inv if i["company_id"][0]==c and i["move_type"] in ("in_invoice","in_refund") and d(i["invoice_date"])>=TODAY-datetime.timedelta(days=90))
    print(f"  CxP abierta {apt:,.0f} | compras 90d {compras12:,.0f} | DPO aprox {apt/compras12*90 if compras12 else 0:.0f} d | vencido {sum(v[1] for v in byp.values())/apt*100 if apt else 0:.0f}%")
    for k,v in sorted(byp.items(),key=lambda kv:-kv[1][0])[:8]: print(f"     cxp {v[0]:>14,.0f} vencido {v[1]:>14,.0f}  {k[:40]}{'  [IC]' if IC(k) else ''}")
    out[f"cxp_{c}"]={k:v for k,v in sorted(byp.items(),key=lambda kv:-kv[1][0])[:15]}
    # proveedores (compras 2026 total)
    pv=collections.defaultdict(float)
    for i in inv:
        if i["company_id"][0]==c and i["move_type"] in ("in_invoice","in_refund"): pv[i["partner_id"][1]]+=-i["amount_untaxed_signed"]
    print("  COMPRAS por proveedor (top):",[(k[:28],round(v)) for k,v in sorted(pv.items(),key=lambda kv:-kv[1])[:10]])
    out[f"proveedores_{c}"]=sorted(((k,round(v)) for k,v in pv.items()),key=lambda kv:-kv[1])[:40]
print("\n","="*30,"PRODUCTOS / CATEGORÍAS por compañía (líneas de factura cliente)")
pl=collections.defaultdict(lambda:collections.defaultdict(lambda:[0.0,0.0,0.0]))  # company -> cat -> [q,rev,cost]
sku=collections.defaultdict(lambda:collections.defaultdict(lambda:[0.0,0.0,0.0,set()]))
price=collections.defaultdict(lambda:collections.defaultdict(list))
noprod=collections.defaultdict(float)
for l in lines:
    i=inv_by.get(l["move_id"][0])
    if not i or i["move_type"] not in ("out_invoice","out_refund"): continue
    c=i["company_id"][0]; sg=-1 if i["move_type"]=="out_refund" else 1
    if not l["product_id"]: noprod[c]+=sg*l["price_subtotal"]; continue
    p=prods.get(l["product_id"][0],{}); code=p.get("default_code") or ""; nom=p.get("name") or l["product_id"][1]
    cst=(p.get("standard_price") or 0)*l["quantity"]*sg
    k=cat(nom,code); a=pl[c][k]; a[0]+=sg*l["quantity"]; a[1]+=sg*l["price_subtotal"]; a[2]+=cst
    s=sku[c][code or nom[:25]]; s[0]+=sg*l["quantity"]; s[1]+=sg*l["price_subtotal"]; s[2]+=cst; s[3].add(nom[:40])
    if sg>0 and l["quantity"]>0 and not IC(i["partner_id"][1]): price[c][code or nom[:25]].append((l["price_subtotal"]/l["quantity"], i["partner_id"][1][:20], l["discount"]))
for c in (2,1,3):
    tot=sum(v[1] for v in pl[c].values()); print(f"\n{CO[c]} (rev con producto {tot:,.0f}; sin producto {noprod[c]:,.0f})")
    for k,v in sorted(pl[c].items(),key=lambda kv:-kv[1][1]): print(f"   {k:22s} q={v[0]:6.0f} rev={v[1]:>14,.0f} {v[1]/tot*100 if tot else 0:5.1f}%  cost(std)={v[2]:>14,.0f} MB={(v[1]-v[2])/v[1]*100 if v[1] else 0:5.1f}%")
    out[f"cat_{c}"]={k:[round(x) for x in v] for k,v in pl[c].items()}
    print("   TOP SKU:")
    for k,v in sorted(sku[c].items(),key=lambda kv:-kv[1][1])[:20]:
        pr=price[c].get(k,[]); pu=[x[0] for x in pr]
        disp=f"precio min {min(pu):,.0f} max {max(pu):,.0f} med {statistics.median(pu):,.0f}" if pu else ""
        print(f"     {k:16s} q={v[0]:5.0f} rev={v[1]:>13,.0f} MB={(v[1]-v[2])/v[1]*100 if v[1] else 0:5.1f}% {disp}  {list(v[3])[0]}")
    out[f"sku_{c}"]={k:[round(v[0]),round(v[1]),round(v[2]),list(v[3])[0]] for k,v in sorted(sku[c].items(),key=lambda kv:-kv[1][1])[:80]}
    zero=[k for k,v in sku[c].items() if v[1]>0 and v[2]==0]; print(f"   SKUs vendidos con costo estándar 0: {len(zero)} de {len(sku[c])} -> {zero[:15]}")
print("\n","="*30,"INVENTARIO (quants internos)")
inv_c=collections.defaultdict(lambda:collections.defaultdict(lambda:[0.0,0.0]))  # company->sku->[qty,value]
loc_c=collections.defaultdict(lambda:collections.defaultdict(float)); age=collections.defaultdict(list)
for q in quants:
    loc=locs.get(q["location_id"][0],{})
    if loc.get("usage")!="internal": continue
    c=q["company_id"][0] if q["company_id"] else 0; p=prods.get(q["product_id"][0],{}); code=p.get("default_code") or (p.get("name") or "")[:25]
    val=q.get("value") if q.get("value") not in (None,False) else (p.get("standard_price") or 0)*q["quantity"]
    inv_c[c][code][0]+=q["quantity"]; inv_c[c][code][1]+=val; loc_c[c][loc.get("complete_name")]+=val
    if q.get("in_date"): age[c].append(((TODAY-d(q["in_date"])).days, val))
# demanda 12m por sku por compañía (Odoo) + Perseo para Ecuador
dem=collections.defaultdict(lambda:collections.defaultdict(float))
for l in lines:
    i=inv_by.get(l["move_id"][0])
    if not i or i["move_type"] not in ("out_invoice","out_refund") or not l["product_id"]: continue
    if d(i["invoice_date"])<TODAY-datetime.timedelta(days=365): continue
    p=prods.get(l["product_id"][0],{}); code=p.get("default_code") or (p.get("name") or "")[:25]
    dem[i["company_id"][0]][code]+= (-1 if i["move_type"]=="out_refund" else 1)*l["quantity"]
try:
    pr=json.load(open(f"{S}/out/perseo_ventas_an.json"))
    # perseo: nov-2025..jul-2026 demand ~ use 2026 skus q * (12/ (12)) approximation: 2025 q*(2/12)+2026 q
    for k,v in pr["skus_anual"].get("2026",{}).items(): dem[2][k]+=v["q"]
    for k,v in pr["skus_anual"].get("2025",{}).items(): dem[2][k]+=v["q"]*2/12
except Exception as e: print("perseo demand skip",e)
for c in (2,1,3):
    items=inv_c[c]; totv=sum(v[1] for v in items.values()); totq=sum(v[0] for v in items.values())
    print(f"\n{CO[c]}: stock {totq:,.0f} uds, valor {totv:,.0f} en {len(items)} SKUs | por ubicación: {[(k[:35],round(v)) for k,v in sorted(loc_c[c].items(),key=lambda kv:-kv[1])[:6]]}")
    dead=[(k,v) for k,v in items.items() if v[0]>0 and dem[c].get(k,0)<=0]; deadv=sum(v[1] for k,v in dead)
    slow=[(k,v) for k,v in items.items() if v[0]>0 and dem[c].get(k,0)>0 and v[0]/(dem[c][k]/12)>12]; slowv=sum(v[1] for k,v in slow)
    print(f"   SIN VENTA 12m: {len(dead)} SKUs, {deadv:,.0f} ({deadv/totv*100 if totv else 0:.0f}% del valor) | cobertura >12 meses: {len(slow)} SKUs {slowv:,.0f}")
    for k,v in sorted(dead,key=lambda kv:-kv[1][1])[:12]: print(f"      muerto {k:18s} q={v[0]:5.0f} val={v[1]:>10,.0f}")
    print("   TOP valor:")
    for k,v in sorted(items.items(),key=lambda kv:-kv[1][1])[:15]:
        dm=dem[c].get(k,0); cob=v[0]/(dm/12) if dm>0 else None
        print(f"      {k:18s} q={v[0]:5.0f} val={v[1]:>10,.0f} demanda12m={dm:6.0f} cobertura={cob:.0f}m" if cob else f"      {k:18s} q={v[0]:5.0f} val={v[1]:>10,.0f} demanda12m={dm:6.0f} cobertura=∞")
    if age[c]:
        tv=sum(v for a,v in age[c]); print(f"   antigüedad valorada: >180d {sum(v for a,v in age[c] if a>180)/tv*100:.0f}% | >365d {sum(v for a,v in age[c] if a>365)/tv*100:.0f}%")
    out[f"stock_{c}"]=dict(total_q=totq,total_v=totv,n=len(items),dead_n=len(dead),dead_v=deadv,slow_v=slowv,top=[(k,round(v[0]),round(v[1]),round(dem[c].get(k,0))) for k,v in sorted(items.items(),key=lambda kv:-kv[1][1])[:40]],dead=[(k,round(v[0]),round(v[1])) for k,v in sorted(dead,key=lambda kv:-kv[1][1])[:40]])
# svl remaining value cross-check
sv=collections.defaultdict(float)
for s in svl: sv[s["company_id"][0]]+=s.get("remaining_value") or 0
print("SVL remaining_value por cia:",{CO.get(k,k):round(v) for k,v in sv.items()})
print("\n","="*30,"PEDIDOS DE VENTA / ENTREGAS")
for c in (2,1,3):
    rows=[o for o in so if o["company_id"][0]==c]; st=collections.Counter(o["state"] for o in rows)
    m=collections.defaultdict(float)
    for o in rows:
        if o["state"] in ("sale","done"): m[o["date_order"][:7]]+=o["amount_untaxed"]
    print(f"{CO[c]}: pedidos {len(rows)} estados {dict(st)} | confirmados por mes {dict(sorted(m.items()))}")
    pend=[o for o in rows if o["state"]=="sale" and o["invoice_status"]=="to invoice"]; print(f"   por facturar: {len(pend)} pedidos {sum(o['amount_untaxed'] for o in pend):,.0f}")
    pk=[p for p in pick if p["company_id"][0]==c and p["picking_type_code"]=="outgoing"]
    stp=collections.Counter(p["state"] for p in pk); lt=[(d(p["date_done"])-d(p["scheduled_date"])).days for p in pk if p["state"]=="done" and p["date_done"] and p["scheduled_date"]]
    print(f"   entregas: {dict(stp)} | retraso medio vs programado {statistics.mean(lt) if lt else 0:.1f} d, mediana {statistics.median(lt) if lt else 0:.0f}, % a tiempo {sum(1 for x in lt if x<=0)/len(lt)*100 if lt else 0:.0f}%")
json.dump(out,open(f"{S}/out/odoo_sales.json","w"),ensure_ascii=False,indent=1,default=str)
