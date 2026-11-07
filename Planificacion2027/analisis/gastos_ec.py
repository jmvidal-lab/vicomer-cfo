import gzip, json, collections, sys
S=sys.argv[1]
cu={str(c["codigocontable"]).replace(".","").strip():c for c in json.load(open(f"{S}/perseo/cuentas.json"))["cuenta"]}
lines=[]; seen=set()
for y in range(2021,2027):
    a=json.load(gzip.open(f"{S}/perseo/asientos_{y}.json.gz","rt")).get("asiento",[])
    for x in a:
        if x["libros_diariosid"] in seen: continue
        seen.add(x["libros_diariosid"])
        if x.get("anulado") or str(x.get("concepto","")).upper().startswith("ASIENTO DE CIERRE"): continue
        f=str(x["fecha"])[:8]
        for d in x.get("detalle") or []:
            if d.get("anulado"): continue
            cod=str(d.get("codigocontable") or "").replace(".","").strip()
            if cod: lines.append((f,cod,float(d.get("importe") or 0)))
YEARS=["2021","2022","2023","2024","2025","2025_7","2026_7"]
def per(f):
    y=f[:4]; m=int(f[4:6])
    out=[y]
    if y=="2025" and m<=7: out.append("2025_7")
    if y=="2026" and m<=7: out.append("2026_7")
    return out
acc=collections.defaultdict(lambda:collections.defaultdict(float)); ventas=collections.defaultdict(float)
for f,c,i in lines:
    for p in per(f):
        if c.startswith("41"): ventas[p]-=i
        elif c.startswith("5") and not c.startswith("51"): acc[c][p]+=i
json.dump({"ventas":ventas,"cuentas":{c:{"nombre":cu.get(c,{}).get("descripcion","?"),"valores":dict(v)} for c,v in acc.items()}},open(f"{S}/out/gastos_ec.json","w"),ensure_ascii=False,indent=1)
print("VENTAS:",{k:round(v) for k,v in ventas.items()})
print(f"{'cuenta':14s} {'nombre':46s} "+" ".join(f"{y:>9s}" for y in YEARS))
for c,v in sorted(acc.items(),key=lambda kv:-(kv[1]['2025']+kv[1]['2026_7'])):
    if max(abs(x) for x in v.values())<2000: continue
    print(f"{c:14s} {cu.get(c,{}).get('descripcion','?')[:46]:46s} "+" ".join(f"{v.get(y,0):>9,.0f}" for y in YEARS))
