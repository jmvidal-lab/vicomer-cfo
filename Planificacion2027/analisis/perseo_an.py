import gzip, json, collections, datetime, re, sys
S=sys.argv[1]
f=json.load(gzip.open(f"{S}/perseo/facturas_raw.json.gz","rt"))["facturas"]
def D(s): s=str(s); return datetime.date(int(s[:4]),int(s[4:6]),int(s[6:8]))
rows=[]
for x in f:
    code=x["sri_documentoscodigo"]; sg=-1 if code=="04" else 1
    d=D(x["emision"]); 
    items=[]
    for it in (x["facturasd"].get("detalles") or []):
        q=float(it.get("cantidad") or 0); p=float(it.get("precio") or 0); dv=float(it.get("descuentovalor") or 0); c=float(it.get("costo") or 0)
        items.append(dict(cod=str(it.get("productocodigo") or "").strip().upper(), nom=str(it.get("nombreproducto") or "").strip(), q=sg*q, rev=sg*(q*p-dv), cost=sg*q*c, serv=it.get("servicio")))
    rows.append(dict(code=code, d=d, y=d.year, m=d.month, cli=x["razonsocial"].strip().upper(), dni=str(x["identificacion"]), sub=sg*float(x["subtotal"] or 0), desc=sg*float(x["total_descuento"] or 0), neto=sg*float(x["subtotalneto"] or 0), total=sg*float(x["total"] or 0), vence=D(x["vence"]) if x.get("vence") and str(x["vence"])[:8].isdigit() else None, fpago=x.get("forma_pago_sri_codigo"), vend=x.get("vendedoresid"), alm=x.get("almacenesid"), items=items, concepto=x.get("concepto","")))
# calibración: 2026 ene-jul oficial 1,117,243.89
for name,fn in [("sub",lambda r:r["sub"]),("sub-desc",lambda r:r["sub"]-r["desc"]),("neto",lambda r:r["neto"]),("items_rev",lambda r:sum(i["rev"] for i in r["items"]))]:
    print("calib 2026 ene-jul",name, round(sum(fn(r) for r in rows if r["y"]==2026 and r["m"]<=7),2))
NET=lambda r:r["sub"]-r["desc"]
out={}
# por año / mes
ym=collections.defaultdict(float); yn=collections.Counter(); ync=collections.defaultdict(float); ycnt=collections.Counter()
for r in rows:
    ym[(r["y"],r["m"])]+=NET(r)
    if r["code"]=="01": yn[r["y"]]+=1
    else: ync[r["y"]]+=NET(r); ycnt[r["y"]]+=1
out["mensual"]={f"{y}-{m:02d}":round(v,2) for (y,m),v in sorted(ym.items())}
out["anual"]={y:dict(neto=round(sum(v for (yy,m),v in ym.items() if yy==y),2), facturas=yn[y], nc_monto=round(ync[y],2), nc_n=ycnt[y]) for y in sorted(set(r["y"] for r in rows))}
print("ANUAL",json.dumps(out["anual"],indent=0))
# clientes por año
cy=collections.defaultdict(lambda:collections.defaultdict(float))
for r in rows: cy[r["y"]][(r["cli"],r["dni"])]+=NET(r)
out["clientes_anual"]={}
for y in sorted(cy):
    tot=sum(cy[y].values()); top=sorted(cy[y].items(),key=lambda kv:-kv[1])
    hhi=sum((v/tot*100)**2 for v in cy[y].values() if tot)
    out["clientes_anual"][y]=dict(total=round(tot,2), n_clientes=sum(1 for v in cy[y].values() if v>0), hhi=round(hhi), top=[(k[0],k[1],round(v,2),round(v/tot*100,1)) for k,v in top[:12]])
    print(f"\n{y} total {tot:,.0f} clientes {len(cy[y])} HHI {hhi:.0f}")
    for k,v in top[:10]: print(f"   {v:>12,.0f} {v/tot*100:5.1f}%  {k[0][:40]} {k[1]}")
# retención clientes
sets={y:set(k for k,v in cy[y].items() if v>500) for y in cy}
for y in sorted(sets):
    if y-1 in sets:
        prev=sets[y-1]; cur=sets[y]
        print(f"{y}: clientes>500: {len(cur)} | retenidos de {y-1}: {len(cur&prev)}/{len(prev)} | nuevos {len(cur-prev)}")
# productos: categoría por keyword
sys.path.insert(0,S); from cats import cat, brand
py=collections.defaultdict(lambda:collections.defaultdict(lambda:[0,0.0,0.0]))  # (y) -> sku -> [q,rev,cost]
cy2=collections.defaultdict(lambda:collections.defaultdict(lambda:[0,0.0,0.0]))
names={}
for r in rows:
    for i in r["items"]:
        k=i["cod"] or i["nom"][:30]; names[k]=i["nom"]
        a=py[r["y"]][k]; a[0]+=i["q"]; a[1]+=i["rev"]; a[2]+=i["cost"]
        b=cy2[r["y"]][cat(i["nom"],i["cod"])]; b[0]+=i["q"]; b[1]+=i["rev"]; b[2]+=i["cost"]
out["categorias_anual"]={y:{c:dict(q=round(v[0]),rev=round(v[1]),cost=round(v[2]),mb=round((v[1]-v[2])/v[1]*100,1) if v[1] else None) for c,v in sorted(cy2[y].items(),key=lambda kv:-kv[1][1])} for y in sorted(cy2)}
for y in sorted(cy2):
    tot=sum(v[1] for v in cy2[y].values()); print(f"\nCATEGORIAS {y} (rev items {tot:,.0f})")
    for c,v in sorted(cy2[y].items(),key=lambda kv:-kv[1][1]):
        mb=(v[1]-v[2])/v[1]*100 if v[1] else 0
        print(f"   {c:22s} q={v[0]:6.0f} rev={v[1]:>11,.0f} {v[1]/tot*100:5.1f}%  cost={v[2]:>11,.0f} MB={mb:5.1f}%")
by=collections.defaultdict(lambda:collections.defaultdict(lambda:[0,0.0,0.0]))
for r in rows:
    for i in r["items"]:
        b=by[r["y"]][brand(i["nom"],i["cod"])]; b[0]+=i["q"]; b[1]+=i["rev"]; b[2]+=i["cost"]
out["marcas_anual"]={y:{c:dict(q=round(v[0]),rev=round(v[1]),cost=round(v[2])) for c,v in sorted(by[y].items(),key=lambda kv:-kv[1][1])} for y in sorted(by)}
for y in sorted(by):
    tot=sum(v[1] for v in by[y].values()); print(f"MARCAS {y}: "+" | ".join(f"{c} {v[1]/tot*100:.0f}% MB {(v[1]-v[2])/v[1]*100 if v[1] else 0:.0f}%" for c,v in sorted(by[y].items(),key=lambda kv:-kv[1][1])))
out["skus_anual"]={y:{k:dict(nom=names[k],q=round(v[0]),rev=round(v[1]),cost=round(v[2])) for k,v in sorted(py[y].items(),key=lambda kv:-kv[1][1])[:60]} for y in sorted(py)}
for y in (2025,2026):
    print(f"\nTOP SKU {y}"); tot=sum(v[1] for v in py[y].values())
    for k,v in sorted(py[y].items(),key=lambda kv:-kv[1][1])[:25]:
        mb=(v[1]-v[2])/v[1]*100 if v[1] else 0
        print(f"   {k:16s} {names[k][:34]:34s} q={v[0]:5.0f} rev={v[1]:>10,.0f} {v[1]/tot*100:4.1f}% MB={mb:5.1f}%")
# cost coverage check: items with cost 0
for y in sorted(py):
    allq=sum(v[1] for v in py[y].values()); zc=sum(v[1] for v in py[y].values() if v[2]==0)
    print(f"{y}: rev items sin costo {zc:,.0f} de {allq:,.0f} ({zc/allq*100 if allq else 0:.1f}%)")
# plazo de crédito y forma de pago
for y in sorted(set(r["y"] for r in rows)):
    rr=[r for r in rows if r["y"]==y and r["code"]=="01" and r["vence"]]
    pl=[(r["vence"]-r["d"]).days for r in rr]; w=[NET(r) for r in rr]
    wavg=sum(p*x for p,x in zip(pl,w))/sum(w) if sum(w) else 0
    fp=collections.Counter(r["fpago"] for r in rr)
    print(f"{y}: plazo medio ponderado {wavg:.0f} d; >=60d share {sum(x for p,x in zip(pl,w) if p>=60)/sum(w)*100 if sum(w) else 0:.0f}% ; formas pago {dict(fp.most_common(4))}")
# estacionalidad índice (2023-2025)
mi=collections.defaultdict(float)
for (y,m),v in ym.items():
    if y in (2023,2024,2025): mi[m]+=v
tot=sum(mi.values()); out["estacionalidad_2023_25"]={m:round(mi[m]/tot*12,2) for m in range(1,13)}
print("estacionalidad idx:",out["estacionalidad_2023_25"])
# descuentos
for y in sorted(out["anual"]):
    s=sum(r["sub"] for r in rows if r["y"]==y); d=sum(r["desc"] for r in rows if r["y"]==y)
    print(f"{y}: descuento {d/s*100 if s else 0:.1f}% del subtotal; NC {abs(ync[y])/s*100 if s else 0:.1f}%")
# intercompañía
ic=collections.defaultdict(float)
for r in rows:
    if "VINTRAL" in r["cli"] or "3-102" in r["cli"] or "VIX" in r["cli"]: ic[(r["y"],r["cli"])]+=NET(r)
print("INTERCOMPANIA:",{f"{k[0]} {k[1]}":round(v) for k,v in sorted(ic.items())})
out["intercompania"]={f"{k[0]} {k[1]}":round(v) for k,v in sorted(ic.items())}
# ticket y num facturas por cliente clave
json.dump(out,open(f"{S}/out/perseo_ventas_an.json","w"),ensure_ascii=False,indent=1,default=str)
json.dump([dict(r,items=None,d=str(r["d"]),vence=str(r["vence"])) for r in rows],open(f"{S}/out/perseo_rows.json","w"),ensure_ascii=False,default=str)
