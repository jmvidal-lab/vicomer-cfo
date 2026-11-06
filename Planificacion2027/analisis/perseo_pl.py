import gzip, json, collections, sys
S=sys.argv[1]
cu={str(c["codigocontable"]).replace(".","").strip():c for c in json.load(open(f"{S}/perseo/cuentas.json"))["cuenta"]}
lines=[]; seen=set()
for y in range(2021,2027):
    try: a=json.load(gzip.open(f"{S}/perseo/asientos_{y}.json.gz","rt")).get("asiento",[])
    except Exception as e: print(y,e); continue
    for x in a:
        if x["libros_diariosid"] in seen: continue
        seen.add(x["libros_diariosid"])
        if x.get("anulado") or str(x.get("concepto","")).upper().startswith("ASIENTO DE CIERRE"): continue
        f=str(x["fecha"])[:8]
        for d in x.get("detalle") or []:
            if d.get("anulado"): continue
            cod=str(d.get("codigocontable") or "").replace(".","").strip()
            if cod: lines.append((f,cod,float(d.get("importe") or 0)))
print("lineas",len(lines))
def agg(pred):
    s=collections.defaultdict(float)
    for f,c,i in lines:
        if pred(f): s[c]+=i
    return s
def P(s,p): return sum(v for k,v in s.items() if k.startswith(p))
out={}
for y in range(2021,2027):
    s=agg(lambda f:f[:4]==str(y))
    acum=agg(lambda f:f[:4]<=str(y))
    ventas=-P(s,"41"); otros=-P(s,"42"); costo=P(s,"51"); gv=P(s,"52"); ga=P(s,"53"); gf=P(s,"54"); gnd=P(s,"55"); g5=P(s,"5")
    res=-(P(s,"4")+P(s,"5"))
    bal=dict(activo=P(acum,"1"), act_corr=P(acum,"11"), efectivo=P(acum,"1101"), clientes=P(acum,"1102"), inventarios=P(acum,"1103"), act_nc=P(acum,"12"), pasivo=-P(acum,"2"), pas_corr=-P(acum,"21"), proveedores=-P(acum,"2101")-P(acum,"2102"), deuda_fin=-(P(acum,"2104")+P(acum,"2203")), pas_nc=-P(acum,"22"), patrim3=-P(acum,"3"), result_acum=-(P(acum,"4")+P(acum,"5")))
    out[y]=dict(ventas=ventas,otros_ing=otros,costo=costo,ub=ventas-costo,gv=gv,ga=ga,gf=gf,gnd=gnd,gastos5=g5,resultado=res,bal=bal)
    print(f"\n{y}: ventas {ventas:,.0f} | costo {costo:,.0f} MB {(ventas-costo)/ventas*100 if ventas else 0:.1f}% | GV {gv:,.0f} GA {ga:,.0f} GF {gf:,.0f} GND {gnd:,.0f} | otros {otros:,.0f} | RESULTADO {res:,.0f} ({res/ventas*100 if ventas else 0:.1f}%)")
    print(f"   BAL activo {bal['activo']:,.0f} (efect {bal['efectivo']:,.0f} cli {bal['clientes']:,.0f} inv {bal['inventarios']:,.0f}) pasivo {bal['pasivo']:,.0f} (prov {bal['proveedores']:,.0f} deudaF {bal['deuda_fin']:,.0f}) patrim {bal['patrim3']+bal['result_acum']:,.0f} cuadre {bal['activo']-bal['pasivo']-bal['patrim3']-bal['result_acum']:,.0f}")
    # top cuentas de gasto
    top=sorted(((k,v) for k,v in s.items() if k.startswith("5") and not k.startswith("51")),key=lambda kv:-abs(kv[1]))[:18]
    for k,v in top: print(f"      {k:14s} {cu.get(k,{}).get('descripcion','?')[:45]:45s} {v:>12,.0f}")
    top=sorted(((k,v) for k,v in s.items() if k.startswith("21") or k.startswith("22")),key=lambda kv:-abs(kv[1]))[:0]
# mensual 2025-2026 ventas/costo/gastos
print("\nMENSUAL")
mm=collections.defaultdict(lambda:collections.defaultdict(float))
for f,c,i in lines:
    if f[:4] in ("2024","2025","2026"):
        k=f[:6]
        if c.startswith("41"): mm[k]["ventas"]-=i
        elif c.startswith("51"): mm[k]["costo"]+=i
        elif c.startswith("5"): mm[k]["gastos"]+=i
        elif c.startswith("42"): mm[k]["otros"]-=i
for k in sorted(mm):
    v=mm[k]; print(f"  {k} ventas {v['ventas']:>10,.0f} costo {v['costo']:>10,.0f} MB {(v['ventas']-v['costo'])/v['ventas']*100 if v['ventas'] else 0:5.1f}% gastos {v['gastos']:>9,.0f} res {v['ventas']-v['costo']-v['gastos']+v['otros']:>9,.0f}")
out["mensual"]={k:dict(v) for k,v in mm.items()}
# balance detalle fin 2025 y jul 2026 cuentas top
for corte in ("20251231","20260731"):
    acum=agg(lambda f:f<=corte); print(f"\nBALANCE detalle al {corte} (cuentas > 10k)")
    for k,v in sorted(acum.items(),key=lambda kv:kv[0]):
        if (k.startswith("1") or k.startswith("2") or k.startswith("3")) and abs(v)>10000 and len(k)>=6: print(f"   {k:14s} {cu.get(k,{}).get('descripcion','?')[:48]:48s} {v:>13,.0f}")
json.dump(out,open(f"{S}/out/perseo_pl.json","w"),indent=1,default=str)
