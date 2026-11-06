import json, collections, sys, datetime
S=sys.argv[1]
L=lambda n: json.load(open(f"{S}/odoo/{n}.json"))
accts=L("accounts"); glm=L("gl_month"); glj=L("gl_journal"); rates=L("rates"); bank=L("bank_lines"); journals={j["id"]:j for j in L("journals")}
CO={1:"Colombia",2:"Ecuador",3:"Costa Rica",11:"VIX",12:"PN-MRV",13:"PN-JMV"}
MES={"enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,"julio":7,"agosto":8,"septiembre":9,"octubre":10,"noviembre":11,"diciembre":12}
def ym(s):
    m,y=s.split(); return f"{y}-{MES[m]:02d}"
def acc(aid,c):
    a=accts.get(str(aid),{}); return a.get(str(c)) or next(iter(a.values()),{})
EXCL=lambda a: "APERTURA" in (a.get("name") or "").upper() or "AJUSTE INICIAL" in (a.get("name") or "").upper()
out={}
for c in (2,1,3,11):
    print("\n"+"="*20,CO[c])
    pl=collections.defaultdict(lambda:collections.defaultdict(float)); byacc=collections.defaultdict(float); excl=collections.defaultdict(float)
    for g in glm:
        if not g["company_id"] or g["company_id"][0]!=c or not g["account_id"]: continue
        a=acc(g["account_id"][0],c); t=a.get("account_type"); k=ym(g["date:month"]); b=g["balance"]
        if t in ("income","income_other","expense","expense_direct_cost","expense_depreciation"):
            if EXCL(a): excl[k]+=b; continue
            name=(a.get("name") or "").upper(); code=a.get("code") or ""
            if t=="income": pl[k]["ventas"]-=b
            elif t=="income_other": pl[k]["otros_ing"]-=b
            elif t=="expense_direct_cost" or "COSTO DE" in name or "COSTO DE LA MERCANCIA" in name or code.startswith("51") or code.startswith("61"): pl[k]["costo"]+=b
            elif t=="expense_depreciation": pl[k]["deprec"]+=b
            else:
                if code.startswith("502.01") or code.startswith("5201") or "GV -" in name or "VENTA" in name and "GASTO" in name: pl[k]["gv"]+=b
                elif code.startswith("502.03") or code.startswith("5301") and "F" in name[:3] or "FINANCIER" in name or "INTERES" in name or "BANCARIO" in name: pl[k]["gf"]+=b
                elif code.startswith("502.04") or "NO DEDUCIBLE" in name or "RENTA" in name: pl[k]["gnd_imp"]+=b
                else: pl[k]["ga"]+=b
            byacc[(code,a.get("name"),t)]+=b
    ks=sorted(pl); tot=collections.defaultdict(float)
    print("  mes      ventas      costo   MB%     GV      GA      GF   GND/imp   otros  resultado")
    for k in ks:
        v=pl[k]; res=v["ventas"]-v["costo"]-v["gv"]-v["ga"]-v["gf"]-v["gnd_imp"]-v["deprec"]+v["otros_ing"]
        for kk in v: tot[kk]+=v[kk]
        print(f"  {k} {v['ventas']:>12,.0f} {v['costo']:>10,.0f} {(v['ventas']-v['costo'])/v['ventas']*100 if v['ventas'] else 0:5.1f}% {v['gv']:>9,.0f} {v['ga']:>9,.0f} {v['gf']:>7,.0f} {v['gnd_imp']:>8,.0f} {v['otros_ing']:>7,.0f} {res:>11,.0f}   excl.apertura {excl.get(k,0):,.0f}")
    v=tot; res=v["ventas"]-v["costo"]-v["gv"]-v["ga"]-v["gf"]-v["gnd_imp"]-v["deprec"]+v["otros_ing"]
    print(f"  TOTAL {v['ventas']:>12,.0f} {v['costo']:>10,.0f} {(v['ventas']-v['costo'])/v['ventas']*100 if v['ventas'] else 0:5.1f}% {v['gv']:>9,.0f} {v['ga']:>9,.0f} {v['gf']:>7,.0f} {v['gnd_imp']:>8,.0f} {v['otros_ing']:>7,.0f} {res:>11,.0f}")
    out[f"pl_{c}"]={k:dict(pl[k]) for k in ks}; out[f"pl_tot_{c}"]=dict(tot)
    print("  GASTOS por cuenta (top 30, año):")
    for (code,name,t),b in sorted(byacc.items(),key=lambda kv:-abs(kv[1]))[:30]:
        if t.startswith("expense"): print(f"     {code:12s} {(name or '')[:48]:48s} {b:>14,.0f}")
    out[f"gastos_{c}"]=[(code,name,t,round(b)) for (code,name,t),b in sorted(byacc.items(),key=lambda kv:-abs(kv[1]))[:60]]
    # balance acumulado
    bal=collections.defaultdict(float); balacc=collections.defaultdict(float)
    for g in glm:
        if not g["company_id"] or g["company_id"][0]!=c or not g["account_id"]: continue
        a=acc(g["account_id"][0],c); t=a.get("account_type") or "?"; bal[t]+=g["balance"]; balacc[(a.get("code"),a.get("name"),t)]+=g["balance"]
    print("  BALANCE por tipo:",{k:round(v) for k,v in sorted(bal.items(),key=lambda kv:-abs(kv[1]))})
    print("  BALANCE cuentas principales (|saldo| top 35):")
    for (code,name,t),b in sorted(balacc.items(),key=lambda kv:-abs(kv[1]))[:35]:
        if not t.startswith("expense") and not t.startswith("income"): print(f"     {str(code):12s} {(name or '')[:48]:48s} {t:22s} {b:>16,.0f}")
    out[f"bal_{c}"]=[(code,name,t,round(b)) for (code,name,t),b in sorted(balacc.items(),key=lambda kv:-abs(kv[1]))[:80] if not t.startswith("expense") and not t.startswith("income")]
    ic=[(code,name,round(b)) for (code,name,t),b in balacc.items() if any(k in (name or "").upper() for k in ["VICOMER","VINTRAL","COSTA RICA","VIX","INTERCOMP","RELACIONAD","ACCIONISTA","SOCIO"]) and abs(b)>1]
    print("  INTERCOMPAÑÍA/relacionadas:",ic)
    # journals
    jj=collections.defaultdict(float)
    for g in glj:
        if g["company_id"] and g["company_id"][0]==c and g["account_id"]:
            a=acc(g["account_id"][0],c)
            if (a.get("account_type") or "").startswith(("income","expense")): jj[g["journal_id"][1]]+=g["balance"]
    print("  P&L por diario:",{k[:25]:round(v) for k,v in sorted(jj.items(),key=lambda kv:-abs(kv[1]))[:8]})
# tasas
print("\nTASAS res.currency.rate (últimas por moneda/compañía):")
last={}
for r in rates:
    k=(r["currency_id"][1], r["company_id"][1][:12] if r["company_id"] else "global")
    if k not in last or r["name"]>last[k]["name"]: last[k]=r
for k,r in sorted(last.items()): print("  ",k,r["name"],"inverse_company_rate",r.get("inverse_company_rate"),"rate",r.get("rate"))
# bancos: flujo mensual por compañía
print("\nMOVIMIENTO BANCARIO por compañía/mes (entradas / salidas):")
bk=collections.defaultdict(lambda:[0.0,0.0])
for b in bank:
    k=(b["company_id"][0] if b["company_id"] else 0,b["date"][:7]); 
    if b["amount"]>0: bk[k][0]+=b["amount"]
    else: bk[k][1]+=b["amount"]
for k in sorted(bk): print(f"  {CO.get(k[0],k[0]):10s} {k[1]} +{bk[k][0]:>14,.0f}  {bk[k][1]:>14,.0f}  neto {bk[k][0]+bk[k][1]:>14,.0f}")
rec=collections.Counter((b["company_id"][0] if b["company_id"] else 0,b["is_reconciled"]) for b in bank); print("  conciliación:",{f"{CO.get(k[0])}-{k[1]}":v for k,v in rec.items()})
json.dump(out,open(f"{S}/out/odoo_gl.json","w"),ensure_ascii=False,indent=1,default=str)
