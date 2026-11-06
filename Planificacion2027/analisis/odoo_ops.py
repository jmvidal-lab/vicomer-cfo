import json, collections, sys, datetime, statistics
S=sys.argv[1]
L=lambda n: json.load(open(f"{S}/odoo/{n}.json"))
CO={1:"Colombia",2:"Ecuador",3:"Costa Rica",11:"VIX",12:"PN-MRV",13:"PN-JMV",0:"(sin cia)"}
TODAY=datetime.date(2026,11,6)
def d(s): return datetime.date.fromisoformat(s[:10]) if s else None
hd=L("helpdesk"); print("="*20,"HELPDESK",len(hd))
print(" por etapa:",collections.Counter(t["stage_id"][1] if t["stage_id"] else "?" for t in hd))
print(" por tipo:",collections.Counter(t["ticket_type_id"][1] if t.get("ticket_type_id") else "?" for t in hd))
print(" por equipo:",collections.Counter(t["team_id"][1] if t.get("team_id") else "?" for t in hd))
print(" por mes creación:",dict(sorted(collections.Counter(t["create_date"][:7] for t in hd).items())))
print(" por compañía:",collections.Counter(CO.get(t["company_id"][0] if t["company_id"] else 0) for t in hd))
ch=[t.get("close_hours") for t in hd if t.get("close_hours")]; print(f" horas a cierre: n={len(ch)} mediana {statistics.median(ch) if ch else 0:.0f}h media {statistics.mean(ch) if ch else 0:.0f}h")
print(" productos:",collections.Counter(t["product_id"][1][:30] if t.get("product_id") else "?" for t in hd).most_common(10))
print(" clientes:",collections.Counter(t["partner_id"][1][:25] if t.get("partner_id") else "?" for t in hd).most_common(8))
for t in hd[:48]: print("   ",t["create_date"][:10],(t["stage_id"] or ["","?"])[1][:12],"|",t["name"][:70])
tk=L("tasks"); pj={p["id"]:p for p in L("projects")}; print("\n"+"="*20,"PROYECTOS",len(pj),"TAREAS",len(tk))
for p in sorted(pj.values(),key=lambda p:-(p.get("task_count") or 0)):
    tt=[t for t in tk if t["project_id"] and t["project_id"][0]==p["id"]]
    op=[t for t in tt if t["state"] in ("01_in_progress","02_changes_requested","03_approved","04_waiting_normal")]
    late=[t for t in op if t.get("date_deadline") and d(t["date_deadline"])<TODAY]
    print(f"  {p['name'][:45]:45s} cia={CO.get(p['company_id'][0] if p['company_id'] else 0):10s} tareas={len(tt):3d} abiertas={len(op):3d} vencidas={len(late):3d} estado={p.get('last_update_status')} resp={(p['user_id'] or ['','-'])[1][:18]}")
print(" tareas por estado:",collections.Counter(t["state"] for t in tk))
print(" tareas por mes creación:",dict(sorted(collections.Counter(t["create_date"][:7] for t in tk).items())))
ua=collections.Counter()
for t in tk:
    if t["state"] in ("01_in_progress","04_waiting_normal"): ua[tuple(t.get("user_ids") or [])]+=1
print(" tareas abiertas por asignados (ids):",ua.most_common(8))
us={u["id"]:u["name"] for u in L("users")}; print(" usuarios:",{k:v[:18] for k,v in us.items()})
print(" muestra tareas abiertas vencidas:")
for t in sorted([t for t in tk if t["state"] in ("01_in_progress","04_waiting_normal") and t.get("date_deadline") and d(t["date_deadline"])<TODAY],key=lambda t:t["date_deadline"])[:25]: print("   ",t["date_deadline"][:10],(t["project_id"] or ['','-'])[1][:25],"|",t["name"][:60])
cr=L("crm"); print("\n"+"="*20,"CRM",len(cr))
for l in cr: print("   ",l["create_date"][:10],(l["stage_id"] or ['','?'])[1][:15],f"{l.get('expected_revenue') or 0:>12,.0f}",l.get("probability"),CO.get(l["company_id"][0] if l["company_id"] else 0),"|",l["name"][:50],"|",(l["partner_id"] or ['',''])[1][:25],(l["user_id"] or ['',''])[1][:18])
em=L("employees"); print("\n"+"="*20,"EMPLEADOS",len(em))
for e in sorted(em,key=lambda e:(e["company_id"][0] if e["company_id"] else 0)): print("   ",CO.get(e["company_id"][0] if e["company_id"] else 0),"|",e["name"][:28],"|",(e.get("job_title") or (e["job_id"] or ['',''])[1] or "")[:30],"|",(e["department_id"] or ['',''])[1][:20],"| activo" if e["active"] else "| inactivo")
cal=L("calendar_month"); cu=collections.defaultdict(int)
for g in cal: cu[(g["user_id"] or [0,"?"])[1]]+=g["__count"]
print("\nCALENDARIO eventos por usuario:",dict(sorted(cu.items(),key=lambda kv:-kv[1])[:10]))
act=L("activities"); print("ACTIVIDADES pendientes:",len(act),"vencidas:",sum(1 for a in act if d(a["date_deadline"])<TODAY),"por modelo:",collections.Counter(a["res_model"] for a in act).most_common(6),"por usuario:",collections.Counter((a["user_id"] or ['','?'])[1][:15] for a in act).most_common(6))
pt=L("partners"); print("\n"+"="*20,"PARTNERS",len(pt))
cust=[p for p in pt if p["customer_rank"]>0]; sup=[p for p in pt if p["supplier_rank"]>0]
print(" clientes:",len(cust),"por país:",collections.Counter((p["country_id"] or ['','?'])[1] for p in cust).most_common(6),"| empresas:",sum(1 for p in cust if p["is_company"]))
print(" clientes con límite de crédito:",sum(1 for p in cust if p.get("credit_limit")), "| con término de pago:",sum(1 for p in cust if p.get("property_payment_term_id")))
print(" clientes creados por mes:",dict(sorted(collections.Counter(p["create_date"][:7] for p in cust).items())))
print(" proveedores:",len(sup),"por país:",collections.Counter((p["country_id"] or ['','?'])[1] for p in sup).most_common(6))
print(" etiquetas clientes:",collections.Counter(tuple(p.get("category_id") or []) for p in cust).most_common(5))
pls=L("pricelists"); pli=L("pricelist_items"); tm={t["id"]:t for t in L("tmpl")}
print("\n"+"="*20,"LISTAS DE PRECIOS",len(pls))
for p in pls: print("   ",p["id"],p["name"][:40],(p["currency_id"] or ['',''])[1],CO.get(p["company_id"][0] if p["company_id"] else 0),"items",len(p.get("item_ids") or []))
# comparación de precio por SKU entre listas (fixed_price)
bysku=collections.defaultdict(dict); plname={p["id"]:p["name"] for p in pls}
for it in pli:
    if it["compute_price"]=="fixed" and it.get("product_tmpl_id"):
        code=tm.get(it["product_tmpl_id"][0],{}).get("default_code") or it["product_tmpl_id"][1][:20]
        bysku[code][plname.get(it["pricelist_id"][0],"?")[:28]]=it["fixed_price"]
top=["TRG3601","TEW30ES","TMO30H","TMO24H","HDW2401SS","MK04SS304","HRT3618U-M1","HRT4806U-M1","TRH3606","HRH3607","PIH36","H9","H7","S7","IG35","TIM1501","TIM1502","TRF3601FD","TGC3601","RSG36B","XRD48E","HRG4808ULP","TEC36","IGMAX"]
for k in top:
    if k in bysku: print(f"   {k:12s}",{a:round(b) for a,b in bysku[k].items()})
# costo estándar y precio lista por template
print("\nTEMPLATES: ",len(tm),"activos",sum(1 for t in tm.values() if t["active"]),"vendibles",sum(1 for t in tm.values() if t["sale_ok"]),"con costo 0:",sum(1 for t in tm.values() if t["active"] and t["sale_ok"] and not t["standard_price"]),"con precio 0:",sum(1 for t in tm.values() if t["active"] and t["sale_ok"] and not t["list_price"]))
print(" por categoría:",collections.Counter((t["categ_id"] or ['','?'])[1][:25] for t in tm.values() if t["active"]).most_common(12))
si=L("supplierinfo"); print("\nSUPPLIERINFO",len(si),"por proveedor:",collections.Counter((s["partner_id"] or ['','?'])[1][:25] for s in si).most_common(6))
for s in si[:0]: pass
hy={}
for s in si:
    code=tm.get(s["product_tmpl_id"][0],{}).get("default_code") if s.get("product_tmpl_id") else None
    if code in top: hy[code]=(s["partner_id"][1][:15],s["price"],(s["currency_id"] or ['',''])[1],s.get("delay"))
print(" precios proveedor SKUs top:",hy)
po=L("purchase_orders"); print("\nCOMPRAS (PO):",len(po),[(p["date_order"][:10],(p["partner_id"] or ['','?'])[1][:20],round(p["amount_untaxed"]),(p["currency_id"] or ['',''])[1],CO.get(p["company_id"][0]),p["state"]) for p in po])
lots=L("lots"); print("\nLOTES/SERIES:",len(lots),"por cia:",collections.Counter(CO.get(l["company_id"][0] if l["company_id"] else 0) for l in lots))
orp=L("orderpoints"); print("REGLAS DE REABASTECIMIENTO:",len(orp))
asts=L("assets"); print("ACTIVOS FIJOS:",[(a["name"][:30],round(a["original_value"]),round(a["book_value"]),CO.get(a["company_id"][0])) for a in asts])
