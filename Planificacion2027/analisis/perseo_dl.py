import os, json, gzip, urllib.request, sys
key=os.environ["PERSEO_API_KEY"]
S=sys.argv[1]
def post(url, payload, timeout=900):
    req=urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type":"application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r: return r.status, r.read().decode("utf-8","ignore")
    except urllib.error.HTTPError as e: return e.code, e.read().decode("utf-8","ignore")
# facturas: todo el histórico
st, raw = post("https://perseo-data-c1.app/api/facturas_consulta", {"api_key":key,"dias":2100,"generarpdf":False})
print("facturas HTTP", st, len(raw))
with gzip.open(f"{S}/perseo/facturas_raw.json.gz","wt",encoding="utf-8") as f: f.write(raw)
# plan de cuentas
st, raw = post("https://perseo-data-c1.app/api/cuentascontables_consulta", {"api_key":key})
print("cuentas HTTP", st, len(raw))
open(f"{S}/perseo/cuentas.json","w").write(raw)
# asientos por año
for y in range(2019, 2027):
    st, raw = post("https://perseo-data-c1.app/api/asientoscontables_consulta", {"api_key":key,"fechadesde":f"{y}0101","fechahasta":f"{y}1231"})
    print("asientos", y, "HTTP", st, len(raw))
    with gzip.open(f"{S}/perseo/asientos_{y}.json.gz","wt",encoding="utf-8") as f: f.write(raw)
print("DONE")
