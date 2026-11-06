#!/usr/bin/env python3
"""Genera revision_cartera_datos.json (datos de la pagina 'Revision Cartera Casa Magna')
desde cartera_dashboard.json + cartera_ajustes.json. Solo lectura sobre Odoo."""
import json
from pathlib import Path
A = Path(__file__).resolve().parent
d = json.loads((A / "cartera_dashboard.json").read_text(encoding="utf-8"))
aj = {}
if (A / "cartera_ajustes.json").exists():
    aj = json.loads((A / "cartera_ajustes.json").read_text(encoding="utf-8"))
filas = [[x["doc"], x["tipo"], x["fecha"], x["vence"], round(x["saldo"], 2),
          x.get("oid") or 0, 1 if x.get("pagada") else 0, x.get("ce", "")] for x in d["docs"]]
out = {"corte": d["corte"], "odoo": d.get("odoo", ""), "cliente_url": d.get("url_cliente", ""),
       "serie": d.get("serie", []), "filas": filas,
       "ajustes": [p for p in aj.get("pendientes", []) if p.get("facturas")],
       "notas_dashboard": d.get("notas", []), "dso_dashboard": d.get("dso"), "total_dashboard": d.get("total")}
(A / "revision_cartera_datos.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(f"OK corte {out['corte']} · {len(filas)} documentos · total {d.get('total'):,.0f}")
