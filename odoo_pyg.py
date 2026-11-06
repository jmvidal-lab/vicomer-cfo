#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
odoo_pyg.py
===========
ESTADO DE RESULTADOS REAL desde el mayor de Odoo, compañía por compañía.

Reemplaza el diagnóstico anterior (odoo_margen.py diag), que leía el plan de
cuentas con TODAS las compañías en el contexto. Desde Odoo 17 los campos `code`
y `name` de account.account son company-dependent: leídos así, Odoo devuelve
código vacío y puede cruzar etiquetas entre compañías. Por eso los reportes
salían con cuentas sin código y con saldos absurdos atribuidos a nombres que no
correspondían.

Este script:
  - lee el plan de cuentas UNA compañía a la vez (contexto correcto)
  - suma el mayor por cuenta con `parent_state = posted`
  - separa los asientos de APERTURA/MIGRACIÓN del movimiento del período
    (son la causa habitual de gastos absurdos: saldos iniciales tipificados
     como cuentas de resultado)
  - clasifica por account_type Y por prefijo de código, y muestra ambos
  - no “corrige” nada por su cuenta: muestra lo que hay y señala lo raro

USO
---
  python3 odoo_pyg.py                    # año en curso, todas las compañías
  python3 odoo_pyg.py 2026               # un año
  python3 odoo_pyg.py 2026-01-01 2026-07-31   # rango exacto
  python3 odoo_pyg.py 2026 --detalle     # además, todas las cuentas con saldo
  python3 odoo_pyg.py 2026 --con-apertura  # NO excluir los asientos de apertura

SALIDA
------
  Migracion/pyg_odoo.txt      reporte legible (Claude lo lee directo)
  Migracion/pyg_odoo.json     mismo contenido en JSON

Sólo stdlib.
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
from collections import defaultdict
from pathlib import Path

HOME = Path.home()
PROJ = Path(__file__).resolve().parent
OUT_DIR = PROJ / "Migracion"

INCOME = ("income", "income_other")
COGS = ("expense_direct_cost", "cost_of_revenue")
EXPENSE = ("expense", "expense_depreciation")

# Diarios / asientos que NO son operación del período. Se detectan por nombre.
APERTURA_PAT = ("APERTURA", "OPENING", "MIGRA", "AJUSTE INICIAL", "SALDO INICIAL",
                "SALDOS INICIALES", "INICIAL")


def log(m):
    print(f"[{datetime.datetime.now():%H:%M:%S}] {m}", flush=True)


def load_config():
    cfg = {"url": os.environ.get("ODOO_URL"), "db": os.environ.get("ODOO_DB"),
           "login": os.environ.get("ODOO_LOGIN"), "apikey": os.environ.get("ODOO_APIKEY")}
    for f in (PROJ / "odoo_config.json", HOME / ".odoo_config.json"):
        if f.exists():
            d = json.loads(f.read_text(encoding="utf-8"))
            for k in ("url", "db", "login", "apikey"):
                cfg[k] = cfg[k] or d.get(k)
            cfg["company_map"] = d.get("company_map", {})
            break
    for kf in (PROJ / "odoo_apikey.txt", HOME / ".odoo_apikey"):
        if not cfg["apikey"] and kf.exists():
            cfg["apikey"] = kf.read_text(encoding="utf-8").strip()
    if cfg.get("url"):
        cfg["url"] = cfg["url"].rstrip("/")
    for k in ("url", "db", "login", "apikey"):
        if not cfg.get(k):
            sys.exit(f"ERROR: falta '{k}' de Odoo (odoo_config.json / odoo_apikey.txt)")
    return cfg


class Odoo:
    def __init__(self, cfg):
        self.cfg = cfg
        ctx = ssl.create_default_context()
        self.common = xmlrpc.client.ServerProxy(f"{cfg['url']}/xmlrpc/2/common",
                                                allow_none=True, context=ctx)
        self.models = xmlrpc.client.ServerProxy(f"{cfg['url']}/xmlrpc/2/object",
                                                allow_none=True, context=ctx)
        self.uid = None

    def auth(self):
        self.uid = self.common.authenticate(self.cfg["db"], self.cfg["login"],
                                            self.cfg["apikey"], {})
        if not self.uid:
            sys.exit("ERROR: no autenticó en Odoo.")
        return self.uid

    def kw(self, model, method, args, kwargs=None):
        return self.models.execute_kw(self.cfg["db"], self.uid, self.cfg["apikey"],
                                      model, method, args, kwargs or {})


def es_apertura(txt):
    t = (txt or "").upper()
    return any(p in t for p in APERTURA_PAT)


def analizar_compania(od, comp, desde, hasta, excluir_apertura=True, detalle=False):
    """P&L de UNA compañía, leyendo su plan de cuentas con su propio contexto."""
    cid, nombre = comp["id"], comp["name"]
    moneda = (comp.get("currency_id") or [0, "?"])[1]
    ctx = {"allowed_company_ids": [cid]}      # <-- clave: una sola compañía

    cuentas = od.kw("account.account", "search_read",
                    [[["account_type", "in", list(INCOME) + list(COGS) + list(EXPENSE)]]],
                    {"fields": ["id", "code", "name", "account_type"], "context": ctx,
                     "limit": 5000})
    meta = {a["id"]: a for a in cuentas}
    if not meta:
        return {"id": cid, "nombre": nombre, "moneda": moneda, "sin_cuentas": True}

    # Diarios, para poder separar la apertura del movimiento real
    diarios = od.kw("account.journal", "search_read", [[["company_id", "=", cid]]],
                    {"fields": ["id", "name", "code", "type"], "context": ctx, "limit": 300})
    dmeta = {d["id"]: d for d in diarios}
    jr_apertura = {d["id"] for d in diarios if es_apertura(d["name"]) or es_apertura(d.get("code"))}

    dom = [["parent_state", "=", "posted"],
           ["company_id", "=", cid],
           ["date", ">=", desde], ["date", "<=", hasta],
           ["account_id", "in", list(meta.keys())]]
    filas = od.kw("account.move.line", "read_group",
                  [dom, ["balance:sum"], ["account_id", "journal_id"]],
                  {"lazy": False, "context": ctx})

    por_cuenta = defaultdict(lambda: {"oper": 0.0, "apert": 0.0})
    por_diario = defaultdict(float)
    for r in filas:
        aid = (r.get("account_id") or [0])[0]
        jid = (r.get("journal_id") or [0])[0]
        bal = float(r.get("balance") or 0)
        nombre_mov = (r.get("journal_id") or [0, ""])[1]
        ap = jid in jr_apertura or es_apertura(nombre_mov)
        por_cuenta[aid]["apert" if ap else "oper"] += bal
        por_diario[nombre_mov] += bal

    tot = {"ventas": 0.0, "costo": 0.0, "gasto": 0.0}
    tot_ap = {"ventas": 0.0, "costo": 0.0, "gasto": 0.0}
    lineas = []
    for aid, v in por_cuenta.items():
        a = meta.get(aid, {})
        t = a.get("account_type", "?")
        oper, apert = v["oper"], v["apert"]
        # También es apertura si la CUENTA se llama así, aunque el diario sea normal
        # (caso VICOMER: "5004 APERTURA INVENTARIOS" tipificada como gasto).
        if es_apertura(a.get("name")) or es_apertura(a.get("code")):
            oper, apert = 0.0, apert + oper
        if not excluir_apertura:      # con --con-apertura, todo cuenta como período
            oper, apert = oper + apert, 0.0
        grupo = "ventas" if t in INCOME else ("costo" if t in COGS else "gasto")
        signo = -1 if grupo == "ventas" else 1     # ingresos vienen en crédito (negativo)
        tot[grupo] += signo * oper
        tot_ap[grupo] += signo * apert
        if abs(oper) > 0.005 or abs(apert) > 0.005:
            lineas.append({
                "code": a.get("code") or "", "name": a.get("name") or "", "tipo": t,
                "grupo": grupo,
                "periodo": round(signo * oper, 2),
                "apertura": round(signo * apert, 2),
            })
    lineas.sort(key=lambda x: -abs(x["periodo"]))

    ventas, costo, gasto = tot["ventas"], tot["costo"], tot["gasto"]
    ub = ventas - costo
    res = {
        "id": cid, "nombre": nombre, "moneda": moneda,
        "desde": desde, "hasta": hasta,
        "excluye_apertura": excluir_apertura,
        "ventas": round(ventas, 2), "costo_ventas": round(costo, 2),
        "utilidad_bruta": round(ub, 2),
        "margen_bruto": round(ub / ventas, 4) if ventas else None,
        "gastos_operativos": round(gasto, 2),
        "resultado": round(ub - gasto, 2),
        "margen_neto": round((ub - gasto) / ventas, 4) if ventas else None,
        "apertura_excluida": {k: round(v, 2) for k, v in tot_ap.items()},
        "n_cuentas_con_saldo": len(lineas),
        "diarios": {k: round(v, 2) for k, v in sorted(por_diario.items(),
                                                      key=lambda x: -abs(x[1]))[:15]},
        "cuentas": lineas if detalle else lineas[:15],
        "alertas": [],
    }

    # ------- controles de sanidad -------
    if ventas and costo == 0:
        res["alertas"].append(
            "COSTO DE VENTAS = 0 -> margen 100%. O no hay cuentas tipificadas como "
            "'expense_direct_cost', o el costo está colgado de una cuenta de gasto.")
        sospechosas = [l for l in lineas if l["grupo"] == "gasto"
                       and any(p in l["name"].upper()
                               for p in ("COSTO DE VENTA", "COSTO DE LA MERCANCIA",
                                         "COSTO DE MERCANCIA", "COSTO MERCADERIA"))]
        for s in sospechosas:
            res["alertas"].append(
                f"   candidata a costo mal tipificada: {s['code']} {s['name']} "
                f"= {s['periodo']:,.2f} (hoy es '{s['tipo']}')")
    if ventas and gasto > ventas * 2:
        res["alertas"].append(
            f"Los gastos ({gasto:,.0f}) superan 2x las ventas ({ventas:,.0f}). "
            f"Casi siempre significa que hay saldos de apertura o asientos de ajuste "
            f"colgados de cuentas de resultado.")
    for l in lineas[:10]:
        if ventas and abs(l["periodo"]) > ventas:
            res["alertas"].append(
                f"Cuenta con saldo mayor que las ventas del período: "
                f"{l['code']} {l['name']} = {l['periodo']:,.2f}")
    if any(not l["code"] for l in lineas):
        n = sum(1 for l in lineas if not l["code"])
        res["alertas"].append(
            f"{n} cuentas sin código legible. Si esto aparece, la lectura del plan de "
            f"cuentas quedó mal y los nombres pueden no corresponder.")
    return res


def fmt_money(v, moneda):
    return f"{v:>18,.2f} {moneda}"


def run(desde, hasta, excluir_apertura=True, detalle=False):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    od = Odoo(cfg); od.auth()
    cmap = cfg.get("company_map", {})
    comps = od.kw("res.company", "search_read", [[]],
                  {"fields": ["id", "name", "currency_id"]})
    log(f"Conectado · {len(comps)} compañías · período {desde} → {hasta}")

    out, lineas_rep = [], []
    lineas_rep.append("=" * 78)
    lineas_rep.append(f" ESTADO DE RESULTADOS DESDE EL MAYOR DE ODOO")
    lineas_rep.append(f" Período: {desde} → {hasta}   ·   Generado: "
                      f"{datetime.datetime.now():%Y-%m-%d %H:%M}")
    lineas_rep.append(f" Asientos de apertura/migración: "
                      f"{'EXCLUIDOS' if excluir_apertura else 'INCLUIDOS'}")
    lineas_rep.append("=" * 78)

    for c in comps:
        log(f"  analizando {c['name']}…")
        r = analizar_compania(od, c, desde, hasta, excluir_apertura, detalle)
        out.append(r)
        pais = next((p for frag, p in cmap.items()
                     if frag.upper() in c["name"].upper()), "(sin mapear)")
        m = r["moneda"]
        lineas_rep.append("")
        lineas_rep.append("-" * 78)
        lineas_rep.append(f"{r['nombre']}   [{m}]   país: {pais}")
        lineas_rep.append("-" * 78)
        if r.get("sin_cuentas"):
            lineas_rep.append("   (sin cuentas de resultado visibles para esta compañía)")
            continue
        lineas_rep.append(f"   Ventas netas        {fmt_money(r['ventas'], m)}")
        lineas_rep.append(f"   (-) Costo de ventas {fmt_money(r['costo_ventas'], m)}")
        mb = f"{r['margen_bruto']*100:.1f}%" if r["margen_bruto"] is not None else "n/a"
        lineas_rep.append(f"   = Utilidad bruta    {fmt_money(r['utilidad_bruta'], m)}"
                          f"   margen {mb}")
        lineas_rep.append(f"   (-) Gastos operat.  {fmt_money(r['gastos_operativos'], m)}")
        mn = f"{r['margen_neto']*100:.1f}%" if r["margen_neto"] is not None else "n/a"
        lineas_rep.append(f"   = Resultado         {fmt_money(r['resultado'], m)}"
                          f"   margen {mn}")
        ap = r["apertura_excluida"]
        if any(abs(v) > 0.01 for v in ap.values()):
            lineas_rep.append(f"   [apertura excluida: ventas {ap['ventas']:,.0f} · "
                              f"costo {ap['costo']:,.0f} · gasto {ap['gasto']:,.0f}]")
            lineas_rep.append("   OJO: el asiento de apertura NO es un estado de resultados.")
            lineas_rep.append("        Es un traslado de saldos que usa cuentas de resultado como")
            lineas_rep.append("        vehículo. Para el P&G previo a la migración usa la fuente")
            lineas_rep.append("        oficial: Finanzas/eeff_ecuador_2026-07_OFICIAL.json")
        lineas_rep.append("")
        lineas_rep.append(f"   Cuentas con mayor saldo del período ({r['n_cuentas_con_saldo']} con saldo):")
        lineas_rep.append(f"     {'código':<14}{'cuenta':<44}{'tipo':<22}{'saldo':>16}")
        for l in r["cuentas"]:
            lineas_rep.append(f"     {(l['code'] or '(sin cód)'):<14}{l['name'][:42]:<44}"
                              f"{l['tipo']:<22}{l['periodo']:>16,.2f}")
        if r["alertas"]:
            lineas_rep.append("")
            lineas_rep.append("   !! ALERTAS")
            for a in r["alertas"]:
                lineas_rep.append("      " + a)
        lineas_rep.append("")
        lineas_rep.append("   Movimiento por diario (top):")
        for d, v in list(r["diarios"].items())[:8]:
            lineas_rep.append(f"     {d[:52]:<54}{v:>18,.2f}")

    lineas_rep.append("")
    lineas_rep.append("=" * 78)
    lineas_rep.append(" FIN. Dile a Claude: \"corrí el P&G\"")
    lineas_rep.append("=" * 78)

    texto = "\n".join(lineas_rep)
    (OUT_DIR / "pyg_odoo.txt").write_text(texto + "\n", encoding="utf-8")
    (OUT_DIR / "pyg_odoo.json").write_text(
        json.dumps({"generado": datetime.datetime.now().isoformat(timespec="seconds"),
                    "desde": desde, "hasta": hasta,
                    "excluye_apertura": excluir_apertura,
                    "companias": out}, indent=1, ensure_ascii=False), encoding="utf-8")
    print()
    print(texto)
    print()
    log(f"-> {OUT_DIR / 'pyg_odoo.txt'}")
    log(f"-> {OUT_DIR / 'pyg_odoo.json'}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    hoy = datetime.date.today()
    if len(args) >= 2 and "-" in args[0]:
        desde, hasta = args[0], args[1]
    elif args and args[0].isdigit():
        y = int(args[0]); desde, hasta = f"{y}-01-01", f"{y}-12-31"
    else:
        desde, hasta = f"{hoy.year}-01-01", hoy.isoformat()
    try:
        run(desde, hasta,
            excluir_apertura="--con-apertura" not in flags,
            detalle="--detalle" in flags)
    except SystemExit:
        raise
    except Exception:
        import traceback
        log("[ERROR]\n" + traceback.format_exc())
        sys.exit(1)
