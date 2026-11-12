import os, sys, json, xmlrpc.client, time, re
sys.path.insert(0, "/workspace/vicomer-cfo"); import odoo_proxy
URL=os.environ["ODOO_URL"]; DB=os.environ["ODOO_DB"]; LOGIN=os.environ["ODOO_LOGIN"]; KEY=os.environ["ODOO_APIKEY"]
OUT=sys.argv[1]
uid=xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common").authenticate(DB,LOGIN,KEY,{})
M=xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object", allow_none=True)
CTX={"allowed_company_ids":[1,2,3,11,12,13]}
def ex(model, method, *a, **kw):
    kw.setdefault("context",CTX); return M.execute_kw(DB,uid,KEY,model,method,list(a),kw)
def fields_of(model):
    return ex(model,"fields_get",attributes=["type"])
def sr(model, dom, fields):
    have=fields_of(model); fields=[f for f in fields if f in have]
    out=[]; off=0
    while True:
        try: r=ex(model,"search_read",dom,fields=fields,limit=2000,offset=off)
        except Exception as e:
            m=re.search(r'campos "([^"]+)"',str(e))
            if m and m.group(1) in fields: fields.remove(m.group(1)); print("drop",model,m.group(1)); continue
            print("ERR",model,str(e)[-200:]); return out
        out+=r
        if len(r)<2000: break
        off+=2000
    return out
def save(name,obj): json.dump(obj,open(f"{OUT}/{name}.json","w"),ensure_ascii=False,default=str); print(name,len(obj))
save("helpdesk",sr("helpdesk.ticket",[("active","in",[True,False])],["name","stage_id","create_date","close_date","team_id","company_id","partner_id","ticket_type_id","priority","user_id","description","tag_ids","kanban_state","sla_deadline","product_id","sale_order_id","first_response_hours","assign_hours_to_close","close_hours","partner_name","rating_last_value"]))
save("helpdesk_stages",sr("helpdesk.stage",[],["name","sequence","fold"]))
save("partners",sr("res.partner",[("active","in",[True,False]),"|",("customer_rank",">",0),("supplier_rank",">",0)],["name","country_id","city","state_id","customer_rank","supplier_rank","company_id","is_company","vat","category_id","user_id","property_payment_term_id","property_supplier_payment_term_id","credit_limit","create_date","industry_id","parent_id","team_id","l10n_latam_identification_type_id","function","email","phone","mobile"]))
save("projects",sr("project.project",[("active","in",[True,False])],["name","company_id","task_count","user_id","date_start","date","partner_id","description","active","tag_ids","last_update_status","last_update_color"]))
save("task_stages",sr("project.task.type",[],["name","sequence","fold","project_ids"]))
save("assets",sr("account.asset",[],["name","original_value","book_value","company_id","acquisition_date","method_period","method_number","state"]))
save("payment_terms",sr("account.payment.term",[],["name","company_id"]))
save("users",sr("res.users",[("active","in",[True,False])],["name","login","company_id","active","share"]))
save("teams",sr("crm.team",[],["name","company_id","member_ids","user_id"]))
save("pricelists",sr("product.pricelist",[],["name","company_id","currency_id","item_ids"]))
save("pricelist_items",sr("product.pricelist.item",[],["pricelist_id","product_tmpl_id","product_id","fixed_price","percent_price","compute_price","min_quantity","applied_on","categ_id","date_start","date_end"]))
save("taxes",sr("account.tax",[],["name","amount","company_id","type_tax_use"]))
save("tmpl",sr("product.template",[("active","in",[True,False])],["name","default_code","categ_id","standard_price","list_price","company_id","active","type","sale_ok","purchase_ok","product_variant_count","description_sale","seller_ids","route_ids","tracking","responsible_id","weight","volume","taxes_id"]))
save("supplierinfo",sr("product.supplierinfo",[],["partner_id","product_tmpl_id","price","currency_id","min_qty","delay","company_id","product_code"]))
save("orderpoints",sr("stock.warehouse.orderpoint",[],["product_id","product_min_qty","product_max_qty","location_id","company_id","trigger"]))
save("lots",sr("stock.lot",[],["name","product_id","company_id","create_date"]))
print("DONE")
