#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
perseo_historico.py — Descarga TODO el histórico de facturas desde el API de Perseo
y guarda el JSON crudo (con detalle de ítems si el API lo incluye) en el proyecto CFO VICOMER.

Uso:  python3 "/Users/juanmarcelo/Claude/Projects/CFO VICOMER/perseo_historico.py" [dias]
      (dias por defecto = 1890, cubre desde 2021-05)
"""
import os, sys, json, ssl, gzip, datetime, urllib.request, urllib.error
from pathlib import Path

API_URL = "https://perseo-data-c1.app/api/facturas_consulta"
OUT_DIR = Path.home() / "Claude" / "Projects" / "CFO VICOMER" / "PerseoVentas"

def get_api_key():
    k = os.environ.get("PERSEO_API_KEY")
    if k: return k.strip()
    for p in (Path.home()/".perseo_apikey",
              Path.home()/"Claude"/"Projects"/"CFO VICOMER"/"perseo_apikey.txt"):
        if p.exists(): return p.read_text(encoding="utf-8").strip()
    sys.exit("ERROR: no se encontró el api_key")

def fetch(api_key, dias):
    body = json.dumps({"api_key": api_key, "dias": dias, "generarpdf": False}).encode()
    req = urllib.request.Request(API_URL, data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=600, context=ctx) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        sys.exit(f"ERROR HTTP {e.code}: {e.read().decode('utf-8','ignore')[:300]}")
    except urllib.error.URLError as e:
        sys.exit(f"ERROR de conexión: {e.reason}")

def main():
    dias = int(sys.argv[1]) if len(sys.argv) > 1 else 1890
    data = fetch(get_api_key(), dias)
    if isinstance(data, dict) and data.get("fault"):
        sys.exit(f"ERROR API: {data['fault'].get('faultstring')}")
    facturas = data.get("facturas", []) if isinstance(data, dict) else data
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    hoy = datetime.date.today().isoformat()
    out = OUT_DIR / f"historico_raw_{hoy}.json.gz"
    with gzip.open(out, "wt", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    print(f"[OK] documentos={len(facturas)}  ->  {out}")
    if facturas:
        keys = sorted(facturas[0].keys())
        print("CAMPOS por factura:", ", ".join(keys))
        det = next((k for k in keys if "detal" in k.lower() or "item" in k.lower()
                    or "producto" in k.lower()), None)
        print("¿Detalle de ítems incluido?:", det or "NO VISIBLE — revisar")
    # tamaño y fechas extremas
    fes = [str(x.get("emision",""))[:10] for x in facturas if x.get("emision")]
    if fes: print("rango emisión:", min(fes), "->", max(fes))

if __name__ == "__main__":
    main()
