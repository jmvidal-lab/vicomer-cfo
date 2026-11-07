import json, re, sys, collections
S=sys.argv[1]
d=json.load(open(f"{S}/out/gastos_ec.json")); V=d["ventas"]; C=d["cuentas"]
# grupo, subgrupo, driver esperado
RULES=[
 (r"Gerente General JMV|Arrendamiento De Oficina|Servicios de Administraci", "D. Partes relacionadas / remuneración al accionista","no es gasto operativo"),
 (r"Gerente Administrativo AFJ", "C. Estructura fija","sueldo directivo"),
 (r"Transporte|Logístic|Logistic|Servicio Logístico|Montacarga", "A. Variables ligados a la venta","transporte: ~venta"),
 (r"instalaci|mantenimiento (REP|FRI|ECU)|Servicios de Instalación", "A. Variables ligados a la venta","servicio técnico: ~venta"),
 (r"Promotor|Exhibici", "A. Variables ligados a la venta","promotoría/exhibición: ~venta Sukasa"),
 (r"Comisiones por ventas Tarjeta|Gastos Bancarios|Diferencia Cambiaria", "A. Variables ligados a la venta","~venta/cobros"),
 (r"Deterioro Inventarios", "A2. Ligados a inventario/compras","~inventario"),
 (r"Salida De Divisas|ISD", "A2. Ligados a inventario/compras","~importaciones"),
 (r"Participacion Trabajadores|Impuesto A La Renta", "E. Ligados a la utilidad","~utilidad"),
 (r"Intereses Bancarios", "F. Financieros","~deuda"),
 (r"Publicidad|FACEBOOK|PAGINAS WEB|Marketing|Medios Di|IVA SERVICIOS DIIGTALES|Feria|HORECA|Thor Kitchen", "B. Inversión comercial (publicidad, ferias)","decisión, no driver"),
 (r"Sueldos|Aporte Patronal|Decimo|Bonos|Refrigerio|Servicios Ocasionales", "C. Estructura fija","nómina"),
 (r"Deprec", "C. Estructura fija","depreciación"),
 (r"Seguros", "C. Estructura fija","seguros"),
 (r"ODOO|Bitrix|Sistema", "C. Estructura fija","sistemas"),
 (r"Bodega TURI|Arrendamiento", "C. Estructura fija","arriendos operativos"),
 (r"Legales|Contables|Profesionales|Asesor|Calidad|Patente|Municipal", "C. Estructura fija","servicios profesionales e impuestos municipales"),
 (r"Viaje|Hotel|Pasaje|Alimentaci|Hospedaje", "C. Estructura fija","viajes"),
]
def grp(n):
    for pat,g,dr in RULES:
        if re.search(pat,n,re.I): return g,dr
    return "G. Otros","—"
P=["2021","2022","2023","2024","2025","2025_7","2026_7"]
G=collections.defaultdict(lambda:collections.defaultdict(float)); rows=[]
for c,v in C.items():
    g,dr=grp(v["nombre"]); vals={p:v["valores"].get(p,0) for p in P}
    if max(abs(x) for x in vals.values())<1500: g2=g
    for p in P: G[g][p]+=vals[p]
    rows.append((g,c,v["nombre"],vals,dr))
def mult(a,b): return (b/a) if a and a>500 else None
print("VENTAS",{p:round(V[p]) for p in P}, "x2023→2025:",round(V["2025"]/V["2023"],2),"x2024→2025:",round(V["2025"]/V["2024"],2),"x ene-jul 25→26:",round(V["2026_7"]/V["2025_7"],2))
print("\nGRUPOS (USD y % de la venta)")
tot={p:0 for p in P}
for g in sorted(G):
    v=G[g]; 
    for p in P: tot[p]+=v[p]
    print(f"{g:48s} "+" ".join(f"{v[p]:>9,.0f}" for p in P)+" | %venta: "+" ".join(f"{v[p]/V[p]*100:5.1f}" for p in P)+f" | x23→25 {mult(v['2023'],v['2025']) or 0:5.1f} | x25→26(7m) {mult(v['2025_7'],v['2026_7']) or 0:5.2f}")
print(f"{'TOTAL gastos 52-55':48s} "+" ".join(f"{tot[p]:>9,.0f}" for p in P)+" | %venta: "+" ".join(f"{tot[p]/V[p]*100:5.1f}" for p in P))
ex=lambda p: tot[p]-G["D. Partes relacionadas / remuneración al accionista"][p]-G["E. Ligados a la utilidad"][p]
print(f"{'TOTAL sin D ni E':48s} "+" ".join(f"{ex(p):>9,.0f}" for p in P)+" | %venta: "+" ".join(f"{ex(p)/V[p]*100:5.1f}" for p in P))
print("\nDETALLE por cuenta (ordenado por grupo y 2025+2026)")
for g in sorted(G):
    print("\n==",g)
    for gg,c,n,vals,dr in sorted([r for r in rows if r[0]==g],key=lambda r:-(r[3]["2025"]+r[3]["2026_7"])):
        if max(abs(x) for x in vals.values())<1500: continue
        m=mult(vals["2023"],vals["2025"]); m2=mult(vals["2025_7"],vals["2026_7"])
        print(f"  {c:13s} {n[:44]:44s} "+" ".join(f"{vals[p]:>8,.0f}" for p in P)+f" | %v25 {vals['2025']/V['2025']*100:4.1f} %v26 {vals['2026_7']/V['2026_7']*100:4.1f} | x23→25 {m if m else 0:5.1f} | x7m {m2 if m2 else 0:4.2f} | {dr}")
json.dump({g:dict(v) for g,v in G.items()},open(f"{S}/out/gastos_grupos.json","w"),indent=1)
