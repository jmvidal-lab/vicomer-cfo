#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
odoo_margen.py
==============
MARGEN BRUTO por compañía desde Odoo (VINTRAL = Colombia, Costa Rica).
Fuente contable real: cuentas de RESULTADO del mayor, no la factura.

  Ventas (income)        = account_type in ('income','income_other')
  Costo de ventas (COGS) = account_type == 'expense_direct_cost'
  Utilidad bruta = Ventas - Costo
  Margen bruto   = Utilidad bruta / Ventas

Reutiliza EXACTAMENTE la misma config/clave que odoo_ventas.py
(~/.odoo_config.json | odoo_config.json  +  ~/.odoo_apikey | odoo_apikey.txt).

USO:
    cd ~/Claude/Projects/CFO\ VICOMER
    python3 odoo_margen.py diag     # revisa tipos de cuenta y sumas crudas
    python3 odoo_margen.py 2026     # calcula margen y guarda JSON

Solo stdlib. Consolida COP->USD con COP_USD (default 3700).
"""
import os, sys, json, ssl, datetime, xmlrpc.client
try:  # proxy HTTPS para xmlrpc (no-op en el Mac)
    import sys as _s, os as _o
    _d = _o.path.dirname(_o.path.abspath(__file__))
    for _p in (_d, _o.path.dirname(_d)):
        if _o.path.exists(_o.path.join(_p, 'odoo_proxy.py')) and _p not in _s.path: _s.path.append(_p)
    import odoo_proxy
except ImportError:
    pass
from pathlib import Path

HOME = Path.home()
PROJ = HOME / "Claude" / "Projects" / "CFO VICOMER"
OUT_DIR = Path(os.environ.get("ODOO_OUT_DIR", PROJ / "OdooVentas"))
FX = float(os.environ.get("COP_USD", "3700"))
INCOME = ("income", "income_other")
COGS = ("expense_direct_cost",)

def load_config():
    cfg = {"url": os.environ.get("ODOO_URL"), "db": os.environ.get("ODOO_DB"),
           "login": os.environ.get("ODOO_LOGIN"), "apikey": os.environ.get("ODOO_APIKEY")}
    for f in (HOME / ".odoo_config.json", PROJ / "odoo_config.json"):
        if f.exists():
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                for k in ("url", "db", "login", "apikey"):
                    cfg[k] = cfg[k] or d.get(k)
            except Exception as e:
                print(f"[WARN] no se pudo leer {f}: {e}")
    for kf in (HOME / ".odoo_apikey", PROJ / "odoo_apikey.txt"):
        if not cfg["apikey"] and kf.exists():
            cfg["apikey"] = kf.read_text(encoding="utf-8").strip()
    if cfg.get("url"):
        cfg["url"] = cfg["url"].rstrip("/")
    for k in ("url", "db", "login", "apikey"):
        if not cfg.get(k):
            sys.exit(f"ERROR: falta '{k}' de Odoo. Revisa odoo_config.json / odoo_apikey.txt")
    return cfg

class Odoo:
    def __init__(self, cfg):
        self.cfg = cfg
        ctx = ssl.create_default_context()
        self.common = xmlrpc.client.ServerProxy(f"{cfg['url']}/xmlrpc/2/common", allow_none=True, context=ctx)
        self.models = xmlrpc.client.ServerProxy(f"{cfg['url']}/xmlrpc/2/object", allow_none=True, context=ctx)
        self.uid = None
    def authenticate(self):
        self.uid = self.common.authenticate(self.cfg["db"], self.cfg["login"], self.cfg["apikey"], {})
        if not self.uid:
            sys.exit("ERROR: no autenticó. Revisa db/login/apikey (odoo_ventas.py diag debe funcionar).")
        return self.uid
    def kw(self, model, method, args, kwargs=None):
        return self.models.execute_kw(self.cfg["db"], self.uid, self.cfg["apikey"], model, method, args, kwargs or {})

def companies(od):
    comps = od.kw("res.company", "search_read", [[]], {"fields": ["id", "name", "currency_id"]})
    return comps, [c["id"] for c in comps]

# Patrones para rescatar el costo de ventas cuando está mal tipificado en Odoo.
# Caso real (VICOMER, jul-2026): "COSTO DE LA MERCANCIA VENDIDA" existe pero está
# como `expense` genérico, no como `expense_direct_cost`, así que el margen salía
# 100% en Colombia y Costa Rica. Un margen de 100% en distribución es imposible:
# antes que reportarlo, el script lo detecta y avisa.
COGS_NOMBRE = ("COSTO DE VENTA", "COSTO DE LA MERCANCIA", "COSTO DE MERCANCIA",
               "COSTO DE VENTAS", "COSTO MERCADERIA", "COST OF GOODS")


def account_ids(od, comp_ids):
    """Devuelve (ingresos, costo_de_ventas, todas, rescatadas_por_nombre)."""
    tipos = list(INCOME) + list(COGS) + ["expense"]
    accts = od.kw("account.account", "search_read",
                  [[["account_type", "in", tipos]]],
                  {"fields": ["id", "code", "name", "account_type"],
                   "context": {"allowed_company_ids": comp_ids}})
    inc = [a["id"] for a in accts if a["account_type"] in INCOME]
    cog = [a["id"] for a in accts if a["account_type"] in COGS]
    rescatadas = []
    if not cog:
        for a in accts:
            if a["account_type"] == "expense" and \
                    any(p in (a.get("name") or "").upper() for p in COGS_NOMBRE):
                cog.append(a["id"]); rescatadas.append(a)
    return inc, cog, accts, rescatadas

def sum_balance(od, comp_ids, acct_ids, year):
    if not acct_ids:
        return {}
    dom = [["parent_state", "=", "posted"], ["date", ">=", f"{year}-01-01"],
           ["date", "<=", f"{year}-12-31"], ["account_id", "in", acct_ids]]
    rows = od.kw("account.move.line", "read_group",
                 [dom, ["balance:sum"], ["company_id"]],
                 {"lazy": False, "context": {"allowed_company_ids": comp_ids}})
    out = {}
    for r in rows:
        cid = (r.get("company_id") or [0, "?"])[0]
        out[cid] = r.get("balance", 0.0)
    return out

def run(year):
    od = Odoo(load_config()); od.authenticate()
    comps, comp_ids = companies(od)
    inc_ids, cog_ids, _, rescatadas = account_ids(od, comp_ids)
    rev = sum_balance(od, comp_ids, inc_ids, year)   # income: balance negativo (crédito)
    cog = sum_balance(od, comp_ids, cog_ids, year)   # cogs: balance positivo (débito)
    print(f"\nMARGEN BRUTO {year} — por compañía (fuente: mayor Odoo)\n" + "=" * 64)
    alertas = []
    if rescatadas:
        alertas.append("Ninguna cuenta está tipificada como 'expense_direct_cost'. Se rescató "
                       "el costo por NOMBRE de estas cuentas (corregir su tipo en Odoo):")
        for a in rescatadas:
            alertas.append(f"     · {a.get('code') or '(sin código)'}  {a.get('name')}")
    out = {}
    cons = {"ventas_usd": 0.0, "costo_usd": 0.0}
    for c in comps:
        cid, name, cur = c["id"], c["name"], (c.get("currency_id") or [0, "?"])[1]
        ventas = -float(rev.get(cid, 0.0))   # a positivo
        costo = float(cog.get(cid, 0.0))
        if abs(ventas) < 1 and abs(costo) < 1:
            continue
        ub = ventas - costo
        m = (ub / ventas) if ventas else None
        vusd = ventas / FX if cur == "COP" else ventas
        cusd = costo / FX if cur == "COP" else costo
        cons["ventas_usd"] += vusd; cons["costo_usd"] += cusd
        # Controles de sanidad: un margen de 100% o negativo no es un dato, es un aviso.
        if ventas and costo == 0:
            alertas.append(f"{name[:34]}: costo de ventas = 0 -> margen 100%. Imposible en "
                           f"distribución; el costo no se está registrando o está mal tipificado.")
        elif m is not None and m > 0.90:
            alertas.append(f"{name[:34]}: margen bruto {m*100:.0f}% — revisar, es implausiblemente alto.")
        elif m is not None and m < 0:
            alertas.append(f"{name[:34]}: margen bruto NEGATIVO ({m*100:.0f}%) — revisar.")
        mtxt = f"{m*100:5.1f}%" if m is not None else "  n/a"
        print(f"  {name[:34]:<34} [{cur}]")
        print(f"     Ventas {ventas:>16,.0f} | Costo {costo:>16,.0f} | Ut.Bruta {ub:>16,.0f} | Margen {mtxt}")
        if cur == "COP":
            print(f"     (~USD  {vusd:>13,.0f} | {cusd:>13,.0f} | {ub/FX:>13,.0f}  @ {FX:.0f})")
        out[name] = {"moneda": cur, "ventas": round(ventas, 2), "costo": round(costo, 2),
                     "util_bruta": round(ub, 2), "margen": round(m, 4) if m is not None else None,
                     "ventas_usd": round(vusd, 2), "costo_usd": round(cusd, 2)}
    ub_usd = cons["ventas_usd"] - cons["costo_usd"]
    mg = (ub_usd / cons["ventas_usd"]) if cons["ventas_usd"] else None
    print("-" * 64)
    print(f"  CONSOLIDADO GRUPO (USD @ {FX:.0f}): Ventas ${cons['ventas_usd']:,.0f} | "
          f"Costo ${cons['costo_usd']:,.0f} | Margen {mg*100:.1f}%" if mg else "  (sin datos)")
    if alertas:
        print("\n  " + "!" * 62)
        print("  ALERTAS DE CALIDAD DEL DATO — no uses estas cifras para decidir:")
        for a in alertas:
            print("   · " + a if not a.startswith("     ") else a)
        print("  " + "!" * 62)
    print("\n  NOTA: desde agosto 2026 Ecuador (VICOMER) también está en Odoo, así que")
    print("        el consolidado ya incluye los 3 países. Contrástalo con los EEFF")
    print("        (odoo_estados_financieros.py) antes de usarlo para decidir.")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dest = OUT_DIR / f"odoo_margen_{year}.json"
    dest.write_text(json.dumps({"generado": datetime.datetime.now().isoformat(timespec="seconds"),
                                "anio": year, "fx_cop_usd": FX, "companias": out,
                                "companias_incluidas": sorted(out.keys()),
                                "consolidado_grupo_usd": {"ventas": round(cons["ventas_usd"], 2),
                                                          "costo": round(cons["costo_usd"], 2),
                                                          "util_bruta": round(ub_usd, 2),
                                                          "margen": round(mg, 4) if mg else None}},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[OK] -> {dest}")

def diag():
    """Vuelca TODA la cuenta de resultado (P&L) con saldo del anio, por compania,
    y la guarda en OdooVentas/odoo_margen_diag.json para ubicar donde vive el costo."""
    od = Odoo(load_config()); od.authenticate()
    comps, comp_ids = companies(od)
    PL = ["income", "income_other", "expense", "expense_direct_cost",
          "expense_depreciation", "cost_of_revenue"]
    accts = od.kw("account.account", "search_read",
                  [[["account_type", "in", PL]]],
                  {"fields": ["id", "code", "name", "account_type"],
                   "context": {"allowed_company_ids": comp_ids}})
    meta = {a["id"]: (a.get("code", ""), a.get("name", ""), a["account_type"]) for a in accts}
    year = datetime.date.today().year
    dom = [["parent_state", "=", "posted"], ["date", ">=", f"{year}-01-01"],
           ["date", "<=", f"{year}-12-31"], ["account_id", "in", list(meta.keys())]]
    rows = od.kw("account.move.line", "read_group",
                 [dom, ["balance:sum"], ["account_id", "company_id"]],
                 {"lazy": False, "context": {"allowed_company_ids": comp_ids}})
    dump = {}
    for r in rows:
        aid = (r.get("account_id") or [0, "?"])[0]
        cname = (r.get("company_id") or [0, "?"])[1]
        code, name, atype = meta.get(aid, ("", "", ""))
        bal = r.get("balance", 0.0)
        if abs(bal) < 1:
            continue
        dump.setdefault(cname, []).append({"code": code, "cuenta": name,
                                           "tipo": atype, "balance": round(bal, 2)})
    for cname in dump:
        dump[cname].sort(key=lambda x: (x["tipo"], str(x["code"])))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dest = OUT_DIR / "odoo_margen_diag.json"
    dest.write_text(json.dumps({"generado": datetime.datetime.now().isoformat(timespec="seconds"),
                                "anio": year, "cuentas_por_compania": dump},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    tipos = {}
    for a in accts:
        tipos[a["account_type"]] = tipos.get(a["account_type"], 0) + 1
    print("Compañías:", [(c["id"], c["name"]) for c in comps])
    print("Cuentas P&L por tipo:", tipos)
    for cname, rowsc in dump.items():
        print(f"\n== {cname} ==")
        for x in rowsc[:60]:
            print(f"  {x['tipo']:<20} {str(x['code']):<10} {str(x['cuenta'])[:34]:<34} {x['balance']:>16,.0f}")
    print(f"\n[OK] -> {dest}")

if __name__ == "__main__":
    a = sys.argv[1] if len(sys.argv) > 1 else "2026"
    if a == "diag":
        diag()
    else:
        run(int(a) if a.isdigit() else 2026)
