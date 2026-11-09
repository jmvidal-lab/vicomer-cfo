import os, sys, json, xmlrpc.client, collections
sys.path.insert(0, "/workspace/vicomer-cfo"); import odoo_proxy
URL=os.environ["ODOO_URL"]; DB=os.environ["ODOO_DB"]; LOGIN=os.environ["ODOO_LOGIN"]; KEY=os.environ["ODOO_APIKEY"]
OUT=sys.argv[1]
uid=xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common").authenticate(DB,LOGIN,KEY,{})
M=xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object", allow_none=True)
res={}
for c in (1,2,3):
    ctx={"allowed_company_ids":[c],"company_id":c}
    r=M.execute_kw(DB,uid,KEY,"product.product","search_read",[[("active","in",[True,False])]],{"fields":["default_code","name","standard_price","list_price","categ_id"],"context":ctx})
    res[c]={p["id"]:p for p in r}
    nz=sum(1 for p in r if p["standard_price"]); print("cia",c,"productos",len(r),"con costo>0:",nz)
json.dump(res,open(f"{OUT}/odoo/std_by_company.json","w"),ensure_ascii=False)
# historial de costo
try:
    h=M.execute_kw(DB,uid,KEY,"product.price.history","search_count",[[]],{})
    print("price.history",h)
except Exception as e: print("no price.history")
