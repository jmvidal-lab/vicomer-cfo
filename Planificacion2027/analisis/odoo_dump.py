import os, sys, json, xmlrpc.client, time, re
sys.path.insert(0, "/workspace/vicomer-cfo"); import odoo_proxy
URL=os.environ["ODOO_URL"]; DB=os.environ["ODOO_DB"]; LOGIN=os.environ["ODOO_LOGIN"]; KEY=os.environ["ODOO_APIKEY"]
OUT=sys.argv[1]
uid=xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common").authenticate(DB,LOGIN,KEY,{})
M=xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object", allow_none=True)
CIAS=[1,2,3,11,12,13]
CTX={"allowed_company_ids":CIAS}
def ex(model, method, *a, **kw):
    kw.setdefault("context",CTX)
    for i in range(4):
        try: return M.execute_kw(DB,uid,KEY,model,method,list(a),kw)
        except Exception as e:
            if i==3: raise
            print("retry",model,method,str(e)[:80]); time.sleep(3)
def sr(model, dom, fields, **kw):
    out=[]; off=0; fields=list(fields)
    while True:
        try:
            r=ex(model,"search_read",dom,fields=fields,limit=2000,offset=off,**kw)
        except Exception as e:
            m=re.search(r"Invalid field '([^']+)'",str(e))
            if m and m.group(1) in fields:
                print("drop field",model,m.group(1)); fields.remove(m.group(1)); continue
            print("ERR",model,str(e)[-300:]); return out
        out+=r
        if len(r)<2000: break
        off+=2000
    return out
def save(name,obj):
    if os.path.exists(f"{OUT}/{name}.json") and name in ("invoices","invoice_lines"): print("skip",name); return
    json.dump(obj,open(f"{OUT}/{name}.json","w"),ensure_ascii=False,default=str); print(name,len(obj) if hasattr(obj,"__len__") else "")
t0=time.time()
# 1. facturas cliente y proveedor
inv=json.load(open(f"{OUT}/invoices.json")) if os.path.exists(f"{OUT}/invoices.json") else sr("account.move",[("state","=","posted"),("move_type","in",["out_invoice","out_refund","in_invoice","in_refund"])],
   ["name","company_id","partner_id","move_type","invoice_date","date","invoice_date_due","amount_untaxed","amount_untaxed_signed","amount_total_signed","amount_residual_signed","currency_id","payment_state","invoice_user_id","team_id","invoice_origin","ref","journal_id","invoice_payment_term_id","partner_shipping_id","amount_total_in_currency_signed","l10n_latam_document_type_id"])
try: save("invoices",inv)
except Exception as e: print("ERR","invoices",str(e)[-200:])
ids=[i["id"] for i in inv]
lines=[]
for k in (range(0,len(ids),500) if not os.path.exists(f"{OUT}/invoice_lines.json") else []):
    lines+=sr("account.move.line",[("move_id","in",ids[k:k+500]),("display_type","=","product")],
      ["move_id","company_id","product_id","name","quantity","price_unit","discount","price_subtotal","balance","account_id","product_uom_id","analytic_distribution","sale_line_ids","tax_ids"])
try: save("invoice_lines",lines)
except Exception as e: print("ERR","invoice_lines",str(e)[-200:])
# 2. productos
prods=sr("product.product",[("active","in",[True,False])],["default_code","name","categ_id","standard_price","list_price","type","company_id","active","product_tmpl_id","barcode","weight","volume","sale_ok","purchase_ok","is_storable"])
try: save("products",prods)
except Exception as e: print("ERR","products",str(e)[-200:])
try: save("categories",sr("product.category",[],["name","complete_name","parent_id"]))
except Exception as e: print("ERR","categories",str(e)[-200:])
# 3. stock
try: save("quants",sr("stock.quant",[],["product_id","location_id","quantity","reserved_quantity","company_id","lot_id","in_date","value","inventory_quantity","inventory_date"]))
except Exception as e: print("ERR","quants",str(e)[-200:])
try: save("locations",sr("stock.location",[],["complete_name","usage","company_id","warehouse_id"]))
except Exception as e: print("ERR","locations",str(e)[-200:])
try: save("warehouses",sr("stock.warehouse",[],["name","code","company_id","lot_stock_id"]))
except Exception as e: print("ERR","warehouses",str(e)[-200:])
try: save("svl",sr("stock.valuation.layer",[],["product_id","company_id","quantity","value","unit_cost","create_date","stock_move_id","description","remaining_qty","remaining_value"]))
except Exception as e: print("ERR","svl",str(e)[-200:])
try: save("stock_moves",sr("stock.move",[],["product_id","product_uom_qty","quantity","date","state","location_id","location_dest_id","company_id","picking_id","origin","reference","picking_type_id","sale_line_id","purchase_line_id","price_unit"]))
except Exception as e: print("ERR","stock_moves",str(e)[-200:])
try: save("pickings",sr("stock.picking",[],["name","picking_type_id","state","scheduled_date","date_done","partner_id","company_id","origin","sale_id","purchase_id","picking_type_code"]))
except Exception as e: print("ERR","pickings",str(e)[-200:])
# 4. contabilidad: cuentas por compañía y mayor agrupado
accts={}
for c in CIAS:
    for a in ex("account.account","search_read",[("company_ids","in",[c])],fields=["code","name","account_type","reconcile","internal_group"],context={"allowed_company_ids":[c]}):
        accts.setdefault(str(a["id"]),{}); accts[str(a["id"])][str(c)]=a
try: save("accounts",accts)
except Exception as e: print("ERR","accounts",str(e)[-200:])
g=ex("account.move.line","read_group",[("parent_state","=","posted")],["balance:sum","debit:sum","credit:sum"],["company_id","account_id","date:month"],lazy=False)
try: save("gl_month",g)
except Exception as e: print("ERR","gl_month",str(e)[-200:])
g=ex("account.move.line","read_group",[("parent_state","=","posted")],["balance:sum"],["company_id","account_id","journal_id"],lazy=False)
try: save("gl_journal",g)
except Exception as e: print("ERR","gl_journal",str(e)[-200:])
# lineas de resultado detalle con partner y producto para analisis margen (income/expense)
pl=sr("account.move.line",[("parent_state","=","posted"),("account_id.account_type","in",["income","income_other","expense","expense_direct_cost","expense_depreciation"])],
  ["move_id","company_id","account_id","date","balance","partner_id","product_id","name","journal_id","quantity","analytic_distribution"])
try: save("pl_lines",pl)
except Exception as e: print("ERR","pl_lines",str(e)[-200:])
# 5. pagos, bancos
try: save("payments",sr("account.payment",[],["name","date","amount","payment_type","partner_type","partner_id","company_id","state","journal_id","currency_id"]))
except Exception as e: print("ERR","payments",str(e)[-200:])
try: save("bank_lines",sr("account.bank.statement.line",[],["date","amount","partner_id","payment_ref","journal_id","company_id","is_reconciled","amount_currency","currency_id"]))
except Exception as e: print("ERR","bank_lines",str(e)[-200:])
try: save("journals",sr("account.journal",[],["name","type","code","company_id","currency_id","bank_account_id","default_account_id"]))
except Exception as e: print("ERR","journals",str(e)[-200:])
try: save("rates",sr("res.currency.rate",[("currency_id.name","in",["COP","CRC","EUR","CNY"])],["name","rate","inverse_company_rate","company_rate","currency_id","company_id"]))
except Exception as e: print("ERR","rates",str(e)[-200:])
# 6. ventas / CRM / proyectos / helpdesk / RRHH / compras
try: save("sale_orders",sr("sale.order",[],["name","date_order","partner_id","amount_untaxed","amount_total","state","company_id","user_id","team_id","invoice_status","delivery_status","payment_term_id","commitment_date","origin","client_order_ref","currency_id"]))
except Exception as e: print("ERR","sale_orders",str(e)[-200:])
try: save("sale_lines",sr("sale.order.line",[],["order_id","product_id","product_uom_qty","qty_delivered","qty_invoiced","price_unit","discount","price_subtotal","company_id","state","name"]))
except Exception as e: print("ERR","sale_lines",str(e)[-200:])
try: save("purchase_orders",sr("purchase.order",[],["name","date_order","partner_id","amount_untaxed","amount_total","state","company_id","currency_id","date_planned","invoice_status","origin"]))
except Exception as e: print("ERR","purchase_orders",str(e)[-200:])
try: save("crm",sr("crm.lead",[("active","in",[True,False])],["name","stage_id","expected_revenue","probability","partner_id","create_date","company_id","user_id","team_id","type","won_status","date_closed","lost_reason_id","country_id","active","source_id","medium_id","campaign_id","tag_ids","date_deadline"]))
except Exception as e: print("ERR","crm",str(e)[-200:])
try: save("crm_stages",sr("crm.stage",[],["name","sequence","is_won"]))
except Exception as e: print("ERR","crm_stages",str(e)[-200:])
try: save("projects",sr("project.project",[],["name","company_id","task_count","user_id","date_start","date","partner_id","stage_id","description","active","tag_ids","last_update_status"]))
except Exception as e: print("ERR","projects",str(e)[-200:])
try: save("tasks",sr("project.task",[("active","in",[True,False])],["name","project_id","stage_id","create_date","date_deadline","user_ids","state","company_id","partner_id","priority","date_last_stage_update","tag_ids","parent_id","date_end","planned_hours" if False else "allocated_hours","description"]))
except Exception as e: print("ERR","tasks",str(e)[-200:])
try: save("helpdesk",sr("helpdesk.ticket",[("active","in",[True,False])],["name","stage_id","create_date","close_date","team_id","company_id","partner_id","ticket_type_id","priority","user_id","description","tag_ids","kanban_state","sla_deadline","product_id" ]))
except Exception as e: print("ERR","helpdesk",str(e)[-200:])
try: save("employees",sr("hr.employee",[("active","in",[True,False])],["name","job_title","department_id","company_id","active","work_email","parent_id","job_id"]))
except Exception as e: print("ERR","employees",str(e)[-200:])
try: save("partners",sr("res.partner",[("active","in",[True,False]),"|",("customer_rank",">",0),("supplier_rank",">",0)],["name","country_id","city","state_id","customer_rank","supplier_rank","company_id","is_company","vat","category_id","user_id","property_payment_term_id","property_supplier_payment_term_id","credit_limit","create_date","industry_id","parent_id","team_id"]))
except Exception as e: print("ERR","partners",str(e)[-200:])
g=ex("calendar.event","read_group",[],["id:count"],["user_id","start:month"],lazy=False); save("calendar_month",g)
try: save("activities",sr("mail.activity",[],["res_model","res_name","activity_type_id","summary","date_deadline","user_id","create_date"]))
except Exception as e: print("ERR","activities",str(e)[-200:])
try: save("assets",sr("account.asset",[],["name","original_value","book_value","company_id","acquisition_date","method_period","method_number","state","asset_type"]) if True else [])
except Exception as e: print("ERR","assets",str(e)[-200:])
print("DONE in",round(time.time()-t0),"s")
