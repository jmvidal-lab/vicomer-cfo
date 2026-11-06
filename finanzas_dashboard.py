#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
finanzas_dashboard.py  ·  Grupo VICOMER
=======================================
EXTRACCION -> CONTRATO JSON del dashboard financiero: estado de resultados y balance
general resumidos (una decena de lineas cada uno) mas los indicadores que de verdad
mueven decisiones, por pais y consolidado.

No es un juego de estados financieros completos. Es la FOTO que un directorio necesita
en treinta segundos: cuanto vendimos, cuanto ganamos, cuanto tenemos, cuanto debemos, y
si la caja aguanta.

Regla rectora: una cifra sin fuente verificable no entra. Antes de estimar, se muestra
el hueco marcado como hueco.

TRAMPAS QUE ESTE SCRIPT SORTEA (verificadas, no teoricas)
  * El asiento de apertura de Ecuador (2026-08-01) usa cuentas de RESULTADO como
    vehiculo (5001 APERTURA ANTICIPO CLIENTE, 5002 APERTURA SALDO PROVEEDOR...). Leido
    como P&G da una perdida ficticia de -232.908. Se excluye del resultado y se conserva
    en el balance, que es donde si corresponde.
  * El P&L de VINTRAL tiene cuentas "AJUSTE INICIAL" mal clasificadas como gasto.
  * Odoo no mantiene tipos de cambio: el consolidado en USD es REFERENCIAL.
  * account.account.code es company-dependent desde Odoo 17: se lee una compania por
    contexto o dos tercios de las cuentas salen sin codigo.
  * Filtrar lineas por move_id.move_type atraviesa account.move, roto por el l10n_ec
    incompleto, y devuelve VACIO sin lanzar error. Aqui no se usa.

MODOS
    python3 finanzas_dashboard.py autotest   # autoprueba offline, sin red
    python3 finanzas_dashboard.py diag       # conexion y saldos crudos, no escribe
    python3 finanzas_dashboard.py 2026       # extraccion completa

Solo biblioteca estandar.
"""
import os, sys, json, ssl, re, datetime, traceback, xmlrpc.client
try:  # proxy HTTPS para xmlrpc (no-op en el Mac)
    import sys as _s, os as _o
    _d = _o.path.dirname(_o.path.abspath(__file__))
    for _p in (_d, _o.path.dirname(_d)):
        if _o.path.exists(_o.path.join(_p, 'odoo_proxy.py')) and _p not in _s.path: _s.path.append(_p)
    import odoo_proxy
except ImportError:
    pass
from pathlib import Path
from collections import defaultdict

HOME = Path.home()
PROJ = Path(os.environ.get("VICOMER_PROJ", HOME / "Claude" / "Projects" / "CFO VICOMER"))
OUT = Path(os.environ.get("FINANZAS_OUT_DIR", PROJ / "Finanzas"))
VENTAS_DIR = PROJ / "OdooVentas"
DEST = OUT / "dashboard_finanzas.json"

MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
ORDEN_PAISES = ["Ecuador", "Colombia", "Costa Rica"]

ACTIVO = ("asset_receivable", "asset_cash", "asset_current", "asset_non_current",
          "asset_prepayments", "asset_fixed")
PASIVO = ("liability_payable", "liability_credit_card", "liability_current", "liability_non_current")
PATRIMONIO = ("equity", "equity_unaffected")
INGRESO = ("income", "income_other")
GASTO = ("expense", "expense_depreciation", "expense_direct_cost", "cost_of_revenue")
COSTO_VENTAS = ("expense_direct_cost", "cost_of_revenue")
COGS_NOMBRE = ("COSTO DE VENTA", "COSTO DE LA MERCANCIA", "COSTO DE MERCANCIA",
               "COSTO DE VENTAS", "COSTO MERCADERIA", "COST OF GOODS", "COSTO DE LA MERCANCÍA")


def log(m):
    print("[%s] %s" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), m), flush=True)


class Avisos(object):
    def __init__(self):
        self.items = []

    def add(self, nivel, pais, bloque, texto):
        self.items.append({"nivel": nivel, "pais": pais, "bloque": bloque, "texto": texto})
        log("  [%s] %s/%s: %s" % (nivel.upper(), pais or "GRUPO", bloque, texto))

    def dump(self):
        o = {"critico": 0, "alerta": 1, "nota": 2}
        return sorted(self.items, key=lambda a: (o.get(a["nivel"], 9), a["pais"] or "", a["bloque"]))


def norm(t):
    import unicodedata
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode("ascii").upper()
    return " ".join(t.split())


def contiene(txt, pats):
    n = norm(txt)
    for p in (pats or []):
        if norm(p) and norm(p) in n:
            return p
    return None


def load_config():
    cfg = {"url": None, "db": None, "login": None, "apikey": None, "_raw": {}}
    for f in (PROJ / "odoo_config.json", HOME / ".odoo_config.json"):
        if f.exists():
            d = json.loads(f.read_text(encoding="utf-8"))
            for k in ("url", "db", "login", "apikey"):
                cfg[k] = cfg[k] or d.get(k)
            cfg["_raw"] = cfg["_raw"] or d
    for kf in (PROJ / "odoo_apikey.txt", HOME / ".odoo_apikey"):
        if not cfg["apikey"] and kf.exists():
            cfg["apikey"] = kf.read_text(encoding="utf-8").strip()
    cfg["url"] = (cfg["url"] or "").rstrip("/")
    return cfg


def load_reglas():
    f = PROJ / "finanzas_reglas.json"
    if not f.exists():
        sys.exit("ERROR: falta finanzas_reglas.json en %s" % PROJ)
    return json.loads(f.read_text(encoding="utf-8"))


def load_tc():
    tc = {"COP": 0.00027027, "CRC": 0.00221, "USD": 1.0}
    f = PROJ / "pagos_reglas_depto.json"
    if f.exists():
        try:
            man = (json.loads(f.read_text(encoding="utf-8")).get("tc_manual") or {})
            for k, v in man.items():
                tc[k] = float(v)
        except Exception:
            pass
    return {"tasas": tc, "fuente": "pagos_reglas_depto.json -> tc_manual", "referencial": True,
            "cop_por_usd": round(1 / tc["COP"], 2), "crc_por_usd": round(1 / tc["CRC"], 2)}


class Odoo(object):
    def __init__(self, cfg):
        self.cfg = cfg
        ctx = ssl.create_default_context()
        self.common = xmlrpc.client.ServerProxy(cfg["url"] + "/xmlrpc/2/common", allow_none=True, context=ctx)
        self.models = xmlrpc.client.ServerProxy(cfg["url"] + "/xmlrpc/2/object", allow_none=True, context=ctx)
        self.uid = None
        self.calls = 0

    def authenticate(self):
        host = self.cfg["url"].split("//")[-1].split("/")[0]
        for db in [self.cfg.get("db"), host.split(".")[0], host]:
            if not db:
                continue
            try:
                uid = self.common.authenticate(db, self.cfg["login"], self.cfg["apikey"], {})
            except Exception:
                continue
            if uid:
                self.cfg["db"] = db; self.uid = uid; return uid
        raise RuntimeError("no autentico contra Odoo")

    def kw(self, model, method, args, kwargs=None):
        self.calls += 1
        return self.models.execute_kw(self.cfg["db"], self.uid, self.cfg["apikey"],
                                      model, method, args, kwargs or {})

    def sr(self, model, dom, fields, ctx=None):
        kw = {"fields": fields}
        if ctx:
            kw["context"] = ctx
        return self.kw(model, "search_read", [dom], kw)


def m2o(v):
    if isinstance(v, (list, tuple)) and len(v) == 2:
        return v[0], v[1]
    return None, None


def companias(od, company_map):
    out = {}
    for r in od.sr("res.company", [], ["id", "name", "currency_id"]):
        _, cur = m2o(r.get("currency_id"))
        n = norm(r.get("name"))
        best, bl = None, -1
        for frag, pais in (company_map or {}).items():
            f = norm(frag)
            if f and f in n and len(f) > bl:
                best, bl = pais, len(f)
        out[r["id"]] = {"id": r["id"], "name": r.get("name"), "moneda": cur,
                        "pais": None if best in (None, "ignore") else best,
                        "excluida": best == "ignore"}
    return out


def plan_de_cuentas(od, cid):
    """UNA compania por contexto: account.account.code es company-dependent en Odoo 17+."""
    out = {}
    for a in od.sr("account.account", [], ["id", "code", "name", "account_type"],
                   ctx={"allowed_company_ids": [cid]}):
        out[a["id"]] = a
    return out


def saldos(od, cid, desde, hasta):
    """Saldo por CUENTA en el rango. balance = debe - haber."""
    dom = [["parent_state", "=", "posted"], ["company_id", "=", cid], ["date", "<=", hasta]]
    if desde:
        dom.append(["date", ">=", desde])
    rows = od.kw("account.move.line", "read_group",
                 [dom, ["balance:sum"], ["account_id"]],
                 {"lazy": False, "context": {"allowed_company_ids": [cid]}})
    out = {}
    for r in rows:
        aid, _ = m2o(r.get("account_id"))
        if aid:
            out[aid] = out.get(aid, 0.0) + float(r.get("balance") or 0)
    return out


# =====================================================================
#  Armado del balance y del estado de resultados
# =====================================================================
def clasifica_balance(cuenta, reglas):
    """Odoo agrupa inventarios, deuda financiera e impuestos en tipos genericos.
    Estas reglas los separan por nombre para que el balance resumido diga algo."""
    b = reglas.get("balance") or {}
    nom = cuenta.get("name")
    t = cuenta.get("account_type")
    if t in ACTIVO:
        if contiene(nom, (b.get("inventarios") or {}).get("nombre_contiene")):
            return "inventarios"
        if t == "asset_cash":
            return "efectivo"
        if t == "asset_receivable":
            return "cuentas_por_cobrar"
        if t in ("asset_non_current", "asset_fixed"):
            return "activo_no_corriente"
        return "otros_activos_corrientes"
    if t in PASIVO:
        # La deuda financiera se marca por NOMBRE pero se ubica por PLAZO: meter la
        # porcion de largo plazo dentro del pasivo corriente hunde la liquidez del
        # balance sin que nadie lo note.
        es_deuda = bool(contiene(nom, (b.get("deuda_financiera") or {}).get("nombre_contiene")))
        if t == "liability_non_current":
            return "deuda_financiera_lp" if es_deuda else "pasivo_no_corriente"
        if es_deuda:
            return "deuda_financiera"
        if contiene(nom, (b.get("impuestos_por_pagar") or {}).get("nombre_contiene")):
            return "impuestos_por_pagar"
        if t == "liability_payable":
            return "cuentas_por_pagar"
        return "otros_pasivos_corrientes"
    if t in PATRIMONIO:
        return "patrimonio"
    return None


def excluir_del_resultado(cuenta, pais, reglas):
    r = (reglas.get("resultados") or {})
    ex = r.get("excluir_siempre") or {}
    if contiene(cuenta.get("name"), ex.get("nombre_contiene")):
        return ex.get("motivo") or "cuenta excluida del resultado"
    for regla in ((r.get("excluir_por_pais") or {}).get(pais) or []):
        if contiene(cuenta.get("name"), [regla.get("nombre_contiene")]):
            return regla.get("motivo") or "cuenta contaminada"
    return None


def construir_pais(od, cid, comp, pais, year, hoy, reglas, avisos, tc):
    cuentas = plan_de_cuentas(od, cid)
    ini_anio = "%d-01-01" % year
    hasta = hoy.isoformat()

    # BALANCE: acumulado historico hasta hoy (el asiento de apertura SI cuenta aqui)
    bal_raw = saldos(od, cid, None, hasta)
    # RESULTADO: solo el anio en curso
    res_raw = saldos(od, cid, ini_anio, hasta)

    B = defaultdict(float)
    detalle_bal = defaultdict(list)
    for aid, v in bal_raw.items():
        c = cuentas.get(aid)
        if not c:
            continue
        k = clasifica_balance(c, reglas)
        if not k:
            continue
        B[k] += v
        detalle_bal[k].append({"code": c.get("code"), "name": c.get("name"), "monto": round(v, 2)})

    ventas = costo = gastos = otros_ing = 0.0
    excluidos = []
    gasto_por_cuenta = []
    cog_ids = [a["id"] for a in cuentas.values() if a["account_type"] in COSTO_VENTAS]
    rescatadas = []
    if not cog_ids:
        for a in cuentas.values():
            if a["account_type"] == "expense" and contiene(a.get("name"), COGS_NOMBRE):
                cog_ids.append(a["id"]); rescatadas.append(a)
    cog_set = set(cog_ids)

    for aid, v in res_raw.items():
        c = cuentas.get(aid)
        if not c:
            continue
        t = c.get("account_type")
        if t not in INGRESO and t not in GASTO:
            continue
        motivo = excluir_del_resultado(c, pais, reglas)
        if motivo:
            excluidos.append({"code": c.get("code"), "name": c.get("name"),
                              "monto": round(-v if t in INGRESO else v, 2), "motivo": motivo})
            continue
        if t in INGRESO:
            if t == "income_other":
                otros_ing += -v
            else:
                ventas += -v
        else:
            if aid in cog_set:
                costo += v
            else:
                gastos += v
                gasto_por_cuenta.append({"code": c.get("code"), "name": c.get("name"), "monto": round(v, 2)})

    if rescatadas:
        avisos.add("alerta", pais, "resultados",
                   "%s no tiene ninguna cuenta tipificada como costo directo: el COGS se rescató por NOMBRE de %s. "
                   "Corregir el tipo de cuenta en Odoo." %
                   (comp["name"], ", ".join((a.get("name") or "")[:38] for a in rescatadas)))

    # una sola cuenta de gasto desproporcionada casi nunca es gasto: es misposting
    umbral = ((reglas.get("resultados") or {}).get("alerta_desproporcion") or {}).get("umbral_sobre_ventas", 0.3)
    gasto_por_cuenta.sort(key=lambda x: -abs(x["monto"]))
    sospechosas = [g for g in gasto_por_cuenta if ventas and abs(g["monto"]) > ventas * umbral]
    for g in sospechosas:
        avisos.add("critico", pais, "resultados",
                   "La cuenta %s (%s) pesa %s, un %.0f%% de las ventas del país. Una sola cuenta de gasto de ese "
                   "tamaño casi nunca es gasto: es un misposting. La utilidad neta de %s NO es confiable hasta "
                   "revisarla." % (g.get("code") or "?", (g.get("name") or "")[:40],
                                   "{:,.0f}".format(g["monto"]), 100.0 * g["monto"] / ventas, pais))

    ub = ventas - costo
    uo = ub - gastos
    neto = uo + otros_ing
    resultados = {
        "ventas_netas": round(ventas, 2), "costo_de_ventas": round(costo, 2),
        "utilidad_bruta": round(ub, 2), "gastos_operativos": round(gastos, 2),
        "utilidad_operativa": round(uo, 2), "otros_ingresos_netos": round(otros_ing, 2),
        "resultado_neto": round(neto, 2),
        "margen_bruto": round(ub / ventas, 4) if ventas else None,
        "margen_operativo": round(uo / ventas, 4) if ventas else None,
        "margen_neto": round(neto / ventas, 4) if ventas else None,
        "fuente": "Odoo: account.move.line por tipo de cuenta, año en curso",
        "confiable": not sospechosas,
        "motivo_no_confiable": ("Hay %d cuenta(s) de gasto desproporcionadas respecto de las ventas; el resultado "
                                "neto está contaminado." % len(sospechosas)) if sospechosas else None,
        "cuentas_sospechosas": sospechosas[:5],
        "top_gastos": gasto_por_cuenta[:8],
        "excluidos": excluidos,
    }
    if costo == 0 and ventas:
        resultados["confiable"] = False
        resultados["motivo_no_confiable"] = ("Odoo no registra costo de ventas para %s: el margen bruto sale 100%%, "
                                             "que es imposible en distribución. No es un dato, es un hueco." % pais)
        avisos.add("critico", pais, "resultados", resultados["motivo_no_confiable"])

    activo = sum(B[k] for k in ("efectivo", "cuentas_por_cobrar", "inventarios",
                                "otros_activos_corrientes", "activo_no_corriente"))
    corriente = sum(B[k] for k in ("efectivo", "cuentas_por_cobrar", "inventarios", "otros_activos_corrientes"))
    pas_cor = -sum(B[k] for k in ("cuentas_por_pagar", "deuda_financiera", "impuestos_por_pagar",
                                  "otros_pasivos_corrientes"))
    pas_ncor = -(B["pasivo_no_corriente"] + B["deuda_financiera_lp"])
    pasivo = pas_cor + pas_ncor
    patrimonio_cuentas = -B["patrimonio"]
    balance = {
        "efectivo": round(B["efectivo"], 2),
        "cuentas_por_cobrar": round(B["cuentas_por_cobrar"], 2),
        "inventarios": round(B["inventarios"], 2),
        "otros_activos_corrientes": round(B["otros_activos_corrientes"], 2),
        "activo_no_corriente": round(B["activo_no_corriente"], 2),
        "activo_total": round(activo, 2),
        "activo_corriente": round(corriente, 2),
        "cuentas_por_pagar": round(-B["cuentas_por_pagar"], 2),
        "deuda_financiera": round(-B["deuda_financiera"], 2),
        "deuda_financiera_lp": round(-B["deuda_financiera_lp"], 2),
        "deuda_financiera_total": round(-(B["deuda_financiera"] + B["deuda_financiera_lp"]), 2),
        "impuestos_por_pagar": round(-B["impuestos_por_pagar"], 2),
        "otros_pasivos_corrientes": round(-B["otros_pasivos_corrientes"], 2),
        "pasivo_corriente": round(pas_cor, 2),
        "pasivo_no_corriente": round(pas_ncor, 2),
        "pasivo_total": round(pasivo, 2),
        "patrimonio_sin_resultado": round(patrimonio_cuentas, 2),
        "resultado_del_ejercicio": round(neto, 2),
        "patrimonio_total": round(patrimonio_cuentas + neto, 2),
        "corte": hoy.isoformat(),
        "fuente": "Odoo: saldos acumulados de account.move.line por tipo de cuenta, al corte",
        "detalle": dict((k, sorted(v, key=lambda x: -abs(x["monto"]))[:6]) for k, v in detalle_bal.items()),
    }
    descuadre = round(activo - (pasivo + patrimonio_cuentas + neto), 2)
    balance["descuadre"] = descuadre
    balance["cuadra"] = abs(descuadre) <= max(1.0, abs(activo) * 0.005)
    if not balance["cuadra"]:
        avisos.add("alerta", pais, "balance",
                   "El balance de %s no cierra por %s (activo %s contra pasivo + patrimonio + resultado). Suele ser "
                   "una cuenta sin tipo asignado en el plan. Se muestra la diferencia en vez de forzar el cuadre." %
                   (pais, "{:,.2f}".format(descuadre), "{:,.2f}".format(activo)))

    dias = (hoy - datetime.date(year, 1, 1)).days + 1
    ind = {
        "liquidez_corriente": round(corriente / pas_cor, 3) if pas_cor else None,
        "prueba_acida": round((corriente - B["inventarios"]) / pas_cor, 3) if pas_cor else None,
        "capital_trabajo": round(corriente - pas_cor, 2),
        "endeudamiento": round(pasivo / (patrimonio_cuentas + neto), 3) if (patrimonio_cuentas + neto) else None,
        "deuda_financiera_total": round(-(B["deuda_financiera"] + B["deuda_financiera_lp"]), 2),
        "roe": round(neto / (patrimonio_cuentas + neto), 4) if (patrimonio_cuentas + neto) else None,
        "dso": round(B["cuentas_por_cobrar"] / ventas * dias, 1) if ventas else None,
        "dio": round(B["inventarios"] / costo * dias, 1) if costo else None,
        "dpo": round(-B["cuentas_por_pagar"] / costo * dias, 1) if costo else None,
        "dias_periodo": dias,
        "metodo": "DSO = CxC / ventas x días transcurridos. DIO = inventario / costo de ventas x días. "
                  "DPO = CxP / costo de ventas x días. Son PUNTUALES sobre saldos al corte, no promedios: "
                  "Odoo no guarda fotos históricas del balance.",
    }
    if ind["dio"] is not None and ind["dso"] is not None and ind["dpo"] is not None:
        ind["ciclo_de_caja"] = round(ind["dio"] + ind["dso"] - ind["dpo"], 1)
    else:
        ind["ciclo_de_caja"] = None
        ind["motivo_ciclo"] = "Sin costo de ventas no hay DIO ni DPO, y sin ellos el ciclo de caja no existe."

    return {"moneda": comp["moneda"], "compania": comp["name"],
            "resultados": resultados, "balance": balance, "indicadores": ind}


# =====================================================================
#  Ecuador: el resultado del anio son DOS pedazos
# =====================================================================
def ajustar_ecuador(bloque, reglas, avisos, year, hoy):
    """Ene-Jul de Ecuador NO esta en Odoo: viene del EEFF oficial. Odoo aporta desde el
    corte de migracion. Sumar lo que Odoo tiene como si fuera el anio entero subestima
    el resultado en siete meses de operacion."""
    cfg = ((reglas.get("fuentes_por_pais") or {}).get("Ecuador") or {})
    ruta = PROJ / (cfg.get("eeff_oficial") or "Finanzas/eeff_ecuador_2026-07_OFICIAL.json")
    if not ruta.exists():
        avisos.add("alerta", "Ecuador", "resultados",
                   "No encuentro %s: el resultado de Ecuador sólo cubre lo que hay en Odoo (desde la migración), "
                   "no el año completo." % ruta.name)
        bloque["resultados"]["cobertura"] = "sólo Odoo (desde la migración)"
        return bloque
    try:
        of = json.loads(ruta.read_text(encoding="utf-8"))
    except Exception as e:
        avisos.add("alerta", "Ecuador", "resultados", "EEFF oficial ilegible: %s" % e)
        return bloque
    r = of.get("resultados") or {}
    odoo = dict(bloque["resultados"])
    hist = {
        "ventas_netas": float(r.get("ventas_netas") or 0),
        "costo_de_ventas": float(r.get("costo_de_ventas") or 0),
        "gastos_operativos": float(r.get("gastos_de_ventas") or 0) + float(r.get("gastos_administrativos") or 0),
        "otros_ingresos_netos": float(r.get("otros_ingresos") or 0)
                                - float(r.get("gastos_financieros") or 0)
                                - float(r.get("gastos_no_deducibles") or 0),
    }
    tot = {}
    for k in ("ventas_netas", "costo_de_ventas", "gastos_operativos", "otros_ingresos_netos"):
        tot[k] = round(hist[k] + (odoo.get(k) or 0), 2)
    ub = round(tot["ventas_netas"] - tot["costo_de_ventas"], 2)
    uo = round(ub - tot["gastos_operativos"], 2)
    neto = round(uo + tot["otros_ingresos_netos"], 2)
    bloque["resultados"] = dict(odoo)
    bloque["resultados"].update({
        "ventas_netas": tot["ventas_netas"], "costo_de_ventas": tot["costo_de_ventas"],
        "utilidad_bruta": ub, "gastos_operativos": tot["gastos_operativos"],
        "utilidad_operativa": uo, "otros_ingresos_netos": tot["otros_ingresos_netos"],
        "resultado_neto": neto,
        "margen_bruto": round(ub / tot["ventas_netas"], 4) if tot["ventas_netas"] else None,
        "margen_operativo": round(uo / tot["ventas_netas"], 4) if tot["ventas_netas"] else None,
        "margen_neto": round(neto / tot["ventas_netas"], 4) if tot["ventas_netas"] else None,
        "fuente": "mixta: EEFF oficial Ene-%s + Odoo desde el corte de migración (%s)"
                  % (MESES[int(str(of.get("periodo", {}).get("hasta", "2026-07-31"))[5:7]) - 1],
                     cfg.get("corte") or "?"),
        "historico_oficial": dict((k, round(v, 2)) for k, v in hist.items()),
        "aporte_odoo": dict((k, odoo.get(k)) for k in
                            ("ventas_netas", "costo_de_ventas", "gastos_operativos", "otros_ingresos_netos")),
        "cobertura": "año completo (dos fuentes cosidas)",
    })
    bloque["indicadores"]["margen_bruto"] = bloque["resultados"]["margen_bruto"]
    b = bloque["balance"]
    # OJO: el balance NO se toca con el resultado cosido. Los siete meses de Perseo ya
    # entraron al balance por el asiento de apertura (dentro de resultados acumulados):
    # sumarlos otra vez como resultado del ejercicio los contaria dos veces y el balance
    # dejaria de cerrar. El balance cierra con lo que Odoo tiene desde la migracion; el
    # estado de resultados del ANO necesita coser dos fuentes. Son dos preguntas distintas.
    b["resultado_del_ejercicio_odoo"] = b["resultado_del_ejercicio"]
    b["resultado_del_ano_gestion"] = neto
    b["nota_resultado"] = ("El balance cierra con el resultado registrado en Odoo desde la migración (%s). "
                           "El resultado del año de gestión (%s) cose además los siete meses del EEFF oficial, "
                           "que en el balance ya están dentro de resultados acumulados." %
                           ("{:,.2f}".format(b["resultado_del_ejercicio_odoo"]), "{:,.2f}".format(neto)))
    dias = (hoy - datetime.date(year, 1, 1)).days + 1
    v, c = tot["ventas_netas"], tot["costo_de_ventas"]
    ind = bloque["indicadores"]
    ind["dso"] = round(b["cuentas_por_cobrar"] / v * dias, 1) if v else None
    ind["dio"] = round(b["inventarios"] / c * dias, 1) if c else None
    ind["dpo"] = round(b["cuentas_por_pagar"] / c * dias, 1) if c else None
    ind["roe"] = round(neto / b["patrimonio_total"], 4) if b["patrimonio_total"] else None
    if None not in (ind["dio"], ind["dso"], ind["dpo"]):
        ind["ciclo_de_caja"] = round(ind["dio"] + ind["dso"] - ind["dpo"], 1)
    avisos.add("nota", "Ecuador", "resultados",
               "El resultado de Ecuador son dos pedazos: %s de ventas del EEFF oficial (Ene-Jul, la cifra con la que "
               "se trasladaron los saldos a Odoo) más %s de Odoo desde agosto. El asiento de apertura queda fuera "
               "del P&G y dentro del balance, que es donde corresponde."
               % ("{:,.0f}".format(hist["ventas_netas"]), "{:,.0f}".format(odoo.get("ventas_netas") or 0)))
    return bloque


# =====================================================================
#  Ensamblado
# =====================================================================
def construir(od, year, avisos, hoy=None, reglas=None):
    hoy = hoy or datetime.date.today()
    reglas = reglas or load_reglas()
    tc = load_tc()
    comps = companias(od, (od.cfg.get("_raw") or {}).get("company_map") or {})
    excluidas = [c["name"] for c in comps.values() if c["excluida"]]
    paises = {}
    for pais in ORDEN_PAISES:
        cids = [c["id"] for c in comps.values() if c["pais"] == pais and not c["excluida"]]
        if not cids:
            continue
        cid = cids[0]
        log("%s (%s)..." % (pais, comps[cid]["name"]))
        b = construir_pais(od, cid, comps[cid], pais, year, hoy, reglas, avisos, tc)
        if pais == "Ecuador":
            b = ajustar_ecuador(b, reglas, avisos, year, hoy)
        else:
            b["resultados"].setdefault("cobertura", "año en curso, todo de Odoo")
        t = tc["tasas"].get(b["moneda"])
        b["usd"] = {"referencial": True}
        for k in ("ventas_netas", "utilidad_bruta", "utilidad_operativa", "resultado_neto"):
            v = b["resultados"].get(k)
            b["usd"][k] = round(v * t, 2) if (t is not None and v is not None) else None
        for k in ("activo_total", "pasivo_total", "patrimonio_total", "efectivo",
                  "cuentas_por_cobrar", "inventarios", "cuentas_por_pagar", "deuda_financiera"):
            v = b["balance"].get(k)
            b["usd"][k] = round(v * t, 2) if (t is not None and v is not None) else None
        paises[pais] = b

    cons = {"moneda": "USD", "referencial": True}
    for k in ("ventas_netas", "utilidad_bruta", "utilidad_operativa", "resultado_neto",
              "activo_total", "pasivo_total", "patrimonio_total", "efectivo",
              "cuentas_por_cobrar", "inventarios", "cuentas_por_pagar", "deuda_financiera"):
        cons[k] = round(sum((p["usd"].get(k) or 0) for p in paises.values()), 2)
    cons["margen_bruto"] = round(cons["utilidad_bruta"] / cons["ventas_netas"], 4) if cons["ventas_netas"] else None
    cons["margen_neto"] = round(cons["resultado_neto"] / cons["ventas_netas"], 4) if cons["ventas_netas"] else None
    cons["endeudamiento"] = round(cons["pasivo_total"] / cons["patrimonio_total"], 3) if cons["patrimonio_total"] else None
    cons["por_pais"] = []
    for pais, p in paises.items():
        cons["por_pais"].append({
            "pais": pais, "moneda": p["moneda"],
            "ventas_local": p["resultados"]["ventas_netas"], "ventas_usd": p["usd"]["ventas_netas"],
            "margen_bruto": p["resultados"]["margen_bruto"], "margen_neto": p["resultados"]["margen_neto"],
            "resultado_usd": p["usd"]["resultado_neto"],
            "activo_usd": p["usd"]["activo_total"], "patrimonio_usd": p["usd"]["patrimonio_total"],
            "liquidez": p["indicadores"]["liquidez_corriente"],
            "endeudamiento": p["indicadores"]["endeudamiento"],
            "ciclo_caja": p["indicadores"]["ciclo_de_caja"],
            "confiable": p["resultados"]["confiable"],
        })
    cons["por_pais"].sort(key=lambda x: -(x["ventas_usd"] or 0))
    no_conf = [x["pais"] for x in cons["por_pais"] if not x["confiable"]]
    if no_conf:
        cons["resultado_confiable"] = False
        avisos.add("alerta", None, "consolidado",
                   "El resultado consolidado incluye a %s, cuyo estado de resultados NO es confiable. La suma se "
                   "muestra porque es la que hay, pero no se puede llevar a un directorio como utilidad del grupo."
                   % ", ".join(no_conf))
    else:
        cons["resultado_confiable"] = True

    doc = {
        "generado": datetime.datetime.now().isoformat(timespec="seconds"),
        "generado_fecha": hoy.isoformat(), "anio": year, "meses": MESES,
        "corte": hoy.isoformat(), "tc": tc,
        "paises": paises, "consolidado": cons,
        "excluidas_del_grupo": excluidas,
        "fuentes": {
            "balance": "Odoo account.move.line, saldos acumulados por tipo de cuenta al corte",
            "resultados": "Odoo account.move.line del año en curso; Ecuador cose el EEFF oficial Ene-Jul",
            "reglas": "finanzas_reglas.json v%s" % reglas.get("version"),
        },
        "avisos": avisos.dump(),
        "odoo": {"url": od.cfg.get("url"), "db": od.cfg.get("db"), "llamadas": od.calls},
    }
    doc["conciliacion"] = conciliar(paises, reglas)
    return doc


def conciliar(paises, reglas):
    filas = []
    for pais, p in paises.items():
        b = p["balance"]
        filas.append({"pais": pais, "concepto": "Balance: activo = pasivo + patrimonio + resultado",
                      "dashboard": b["activo_total"],
                      "referencia": round(b["pasivo_total"] + b["patrimonio_sin_resultado"] + b["resultado_del_ejercicio"], 2),
                      "diferencia": b["descuadre"], "cuadra": b["cuadra"],
                      "nota": None if b["cuadra"] else "Suele ser una cuenta sin tipo asignado en el plan de Odoo."})
    ec = paises.get("Ecuador")
    ruta = PROJ / "Finanzas" / "eeff_ecuador_2026-07_OFICIAL.json"
    if ec and ruta.exists():
        try:
            of = json.loads(ruta.read_text(encoding="utf-8"))
            r = of.get("resultados") or {}
            h = ec["resultados"].get("historico_oficial") or {}
            d = round((h.get("ventas_netas") or 0) - float(r.get("ventas_netas") or 0), 2)
            filas.append({"pais": "Ecuador", "concepto": "Ventas Ene-Jul vs eeff_ecuador_2026-07_OFICIAL.json",
                          "dashboard": h.get("ventas_netas"), "referencia": r.get("ventas_netas"),
                          "diferencia": d, "cuadra": abs(d) < 0.01, "nota": None})
        except Exception:
            pass
    vj = VENTAS_DIR / "dashboard_ventas.json"
    if vj.exists():
        try:
            v = json.loads(vj.read_text(encoding="utf-8"))
            for pais, p in paises.items():
                vp = (v.get("paises") or {}).get(pais)
                if not vp:
                    continue
                ref = vp.get("ytd_real")
                dash = p["resultados"]["ventas_netas"]
                d = round(dash - ref, 2) if ref is not None else None
                filas.append({"pais": pais, "concepto": "Ventas del P&G vs YTD del dashboard de ventas",
                              "dashboard": dash, "referencia": ref, "diferencia": d,
                              "cuadra": (d is not None and abs(d) <= max(1.0, abs(ref or 1) * 0.02)),
                              "tolerable": True,
                              "nota": "El dashboard de ventas mide facturación hasta el último mes CERRADO; "
                                      "el P&G mide contabilidad hasta hoy. Una diferencia del tamaño del mes en "
                                      "curso es lo esperado, no un descuadre."})
        except Exception:
            pass
    duras = [f for f in filas if f.get("diferencia") is not None and not f.get("tolerable")]
    return {"filas": filas, "todo_cuadra": all(f["cuadra"] for f in duras)}


def escribir(doc):
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = DEST.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(DEST))
    hist = OUT / "historico_finanzas"
    hist.mkdir(exist_ok=True)
    (hist / ("dashboard_finanzas_%s.json" % doc["generado_fecha"].replace("-", ""))).write_text(
        json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    log("[OK] -> %s" % DEST)
    return DEST


def imprimir(doc):
    print("")
    print("=" * 92)
    print("  ESTADO DE RESULTADOS Y BALANCE — al %s" % doc["corte"])
    print("=" * 92)
    for pais, p in doc["paises"].items():
        r, b, i = p["resultados"], p["balance"], p["indicadores"]
        print("\n  %s  (%s · %s)   %s" % (pais, p["compania"][:34], p["moneda"],
                                          "" if r["confiable"] else "<-- RESULTADO NO CONFIABLE"))
        for et, k in (("Ventas netas", "ventas_netas"), ("(-) Costo de ventas", "costo_de_ventas"),
                      ("= Utilidad bruta", "utilidad_bruta"), ("(-) Gastos operativos", "gastos_operativos"),
                      ("= Utilidad operativa", "utilidad_operativa"),
                      ("(+/-) Otros y financieros", "otros_ingresos_netos"),
                      ("= RESULTADO NETO", "resultado_neto")):
            print("      %-28s {:>18,.2f}".format(r.get(k) or 0) % et)
        print("      %-28s %17s" % ("margen bruto / neto",
                                    ("%.1f%% / %.1f%%" % ((r["margen_bruto"] or 0) * 100, (r["margen_neto"] or 0) * 100))
                                    if r["margen_bruto"] is not None else "n/a"))
        print("      " + "-" * 52)
        for et, k in (("Efectivo", "efectivo"), ("Cuentas por cobrar", "cuentas_por_cobrar"),
                      ("Inventarios", "inventarios"), ("ACTIVO TOTAL", "activo_total"),
                      ("Cuentas por pagar", "cuentas_por_pagar"), ("Deuda financiera", "deuda_financiera"),
                      ("PASIVO TOTAL", "pasivo_total"), ("PATRIMONIO", "patrimonio_total")):
            print("      %-28s {:>18,.2f}".format(b.get(k) or 0) % et)
        print("      %-28s liquidez %s · ácida %s · endeud. %s · ciclo caja %s d" %
              ("indicadores", i["liquidez_corriente"], i["prueba_acida"], i["endeudamiento"], i["ciclo_de_caja"]))
    c = doc["consolidado"]
    print("\n  GRUPO (USD referencial): ventas {:,.0f} · utilidad bruta {:,.0f} · resultado {:,.0f} · "
          "activo {:,.0f} · patrimonio {:,.0f}".format(
              c["ventas_netas"], c["utilidad_bruta"], c["resultado_neto"], c["activo_total"], c["patrimonio_total"]))
    print("\n  CONCILIACIÓN")
    for f in doc["conciliacion"]["filas"]:
        print("   %s %-11s %-58s dif %s" % ("OK " if f["cuadra"] else ("~  " if f.get("tolerable") else "!! "),
                                            f["pais"], f["concepto"][:58],
                                            "{:>14,.2f}".format(f["diferencia"]) if f["diferencia"] is not None else "-"))
    print("   RESULTADO: %s" % ("TODO CUADRA" if doc["conciliacion"]["todo_cuadra"] else "HAY DIFERENCIAS"))
    print("\n  AVISOS (%d):" % len(doc["avisos"]))
    for a in doc["avisos"]:
        print("   [%-7s] %-11s %-12s %s" % (a["nivel"], a["pais"] or "GRUPO", a["bloque"], a["texto"][:150]))
    print("")


# =====================================================================
#  Autoprueba offline
# =====================================================================
def _autotest():
    global OUT, DEST, PROJ, VENTAS_DIR
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    OUT = tmp / "Finanzas"; DEST = OUT / "dashboard_finanzas.json"
    VENTAS_DIR = tmp / "OdooVentas"
    PROJ = tmp
    (tmp / "Finanzas").mkdir(parents=True)
    (tmp / "Finanzas" / "eeff_ecuador_2026-07_OFICIAL.json").write_text(json.dumps({
        "periodo": {"hasta": "2026-07-31"},
        "resultados": {"ventas_netas": 1118645.46, "costo_de_ventas": 650933.72,
                       "gastos_de_ventas": 142154.78, "gastos_administrativos": 132565.41,
                       "otros_ingresos": 970.0, "gastos_financieros": 12715.76,
                       "gastos_no_deducibles": 26703.95}}), encoding="utf-8")
    hoy = datetime.date(2026, 9, 10)
    year = 2026

    COMPS = [{"id": 2, "name": "VICOMER S.A.S.", "currency_id": [1, "USD"]},
             {"id": 1, "name": "VINTRAL S.A.S.", "currency_id": [3, "COP"]},
             {"id": 3, "name": "3-102-940094 SRL", "currency_id": [1, "USD"]},
             {"id": 11, "name": "VIX S.A.S.", "currency_id": [1, "USD"]}]
    # (id, code, name, type, saldo_historico, saldo_del_anio)
    PLAN = {
      2: [(1, "101.01", "CAJA Y BANCOS", "asset_cash", 88680.10, 0),
          (2, "101.03", "CLIENTES", "asset_receivable", 585864.42, 0),
          (3, "101.04", "INVENTARIO DE MERCADERIA", "asset_current", 544178.76, 0),
          (4, "102.01", "PROPIEDAD PLANTA Y EQUIPO", "asset_fixed", 36346.84, 0),
          (5, "201.03", "PROVEEDORES", "liability_payable", -488839.87, 0),
          (6, "201.05", "OBLIGACIONES FINANCIERAS CP", "liability_current", -307020.98, 0),
          (7, "202.01", "OBLIGACIONES FINANCIERAS LP", "liability_non_current", -19895.25, 0),
          (8, "301.01", "CAPITAL", "equity", -50200.00, 0),
          (9, "302.01", "RESULTADOS ACUMULADOS", "equity", -343315.10, 0),
          (10, "401.01", "VENTAS", "income", 0, -158798.92),
          (11, "501.01", "COSTO DE LA MERCANCIA VENDIDA", "expense", 0, 92000.00),
          (12, "502.01", "GASTOS DE VENTAS", "expense", 0, 21000.00),
          (13, "5001", "APERTURA ANTICIPO CLIENTE", "expense", 0, 232908.00)],
      1: [(20, "1105", "BANCOS", "asset_cash", 120000000.0, 0),
          (21, "1305", "CLIENTES", "asset_receivable", 859501280.0, 0),
          (22, "1435", "MERCANCIAS NO FABRICADAS", "asset_current", 700000000.0, 0),
          (23, "2205", "PROVEEDORES", "liability_payable", -517850761.0, 0),
          (24, "2105", "OBLIGACIONES FINANCIERAS", "liability_current", -200000000.0, 0),
          (25, "3105", "CAPITAL SOCIAL", "equity", -300000000.0, 0),
          (26, "4135", "COMERCIO AL POR MAYOR", "income", 0, -1125563010.0),
          (27, "6135", "COSTO DE LA MERCANCIA VENDIDA", "expense", 0, 470000000.0),
          (28, "5135", "GASTOS DE ADMINISTRACION", "expense", 0, 90000000.0),
          (29, "5299", "AJUSTE INICIAL PATRIMONIO", "expense", 0, 40000000.0),
          (30, "5230", "PROMOCION Y PUBLICIDAD", "expense", 0, 6600000000.0)],
      3: [(40, "101", "BANCOS CR", "asset_cash", 12000.0, 0),
          (41, "103", "CLIENTES CR", "asset_receivable", 94860.11, 0),
          (42, "201", "PROVEEDORES CR", "liability_payable", -4101.25, 0),
          (43, "301", "CAPITAL CR", "equity", -50000.0, 0),
          (44, "4", "INGRESOS CR", "income", 0, -86197.0),
          (45, "502", "GASTOS CR", "expense", 0, 30000.0)],
      11: [(50, "4", "VENTAS VIX", "income", 0, -10000.0)],
    }

    def dget(dom, f):
        return [c for c in dom if isinstance(c, (list, tuple)) and c and c[0] == f]

    class Mock(object):
        def execute_kw(self, db, uid, key, model, method, args, kw=None):
            kw = kw or {}
            dom = args[0] if args else []
            ctx = (kw.get("context") or {})
            cids = ctx.get("allowed_company_ids") or []
            if model == "res.company":
                return COMPS
            if model == "account.account":
                return [{"id": a[0], "code": a[1], "name": a[2], "account_type": a[3]}
                        for c in cids for a in PLAN.get(c, [])]
            if model == "account.move.line" and method == "read_group":
                comp = None
                for c in dget(dom, "company_id"):
                    comp = c[2]
                desde = None
                for c in dget(dom, "date"):
                    if c[1] == ">=":
                        desde = c[2]
                out = []
                for a in PLAN.get(comp, []):
                    v = a[5] if desde else (a[4] + a[5])
                    if v:
                        out.append({"account_id": [a[0], a[2]], "balance": v})
                return out
            return []

    class Common(object):
        def version(self): return {"server_version": "18.0-mock"}
        def authenticate(self, db, l, k, ua): return 7

    class FakeOdoo(Odoo):
        def __init__(self, cfg):
            self.cfg = cfg; self.uid = 7; self.calls = 0
            self.common = Common(); self.models = Mock()
        def authenticate(self): return 7

    cfg = {"url": "http://mock", "db": "m", "login": "x", "apikey": "y",
           "_raw": {"company_map": {"VICOMER": "Ecuador", "VIX": "ignore", "VINTRAL": "Colombia",
                                    "3-102-940094": "Costa Rica"}}}
    reglas = json.loads(Path("finanzas_reglas.json").read_text(encoding="utf-8")) \
        if Path("finanzas_reglas.json").exists() else json.loads((PROJ / "finanzas_reglas.json").read_text(encoding="utf-8"))
    (tmp / "finanzas_reglas.json").write_text(json.dumps(reglas), encoding="utf-8")

    av = Avisos()
    doc = construir(FakeOdoo(cfg), year, av, hoy=hoy, reglas=reglas)
    ec, co, cr = doc["paises"]["Ecuador"], doc["paises"]["Colombia"], doc["paises"]["Costa Rica"]
    fallos = []

    def chk(c, m):
        if not c:
            fallos.append(m)
        print(("  OK  " if c else "  FALLA ") + m)

    print("\nAUTOPRUEBA finanzas_dashboard.py")
    print("-" * 76)
    chk(not any("APERTURA" in norm(x["name"]) for x in ec["resultados"]["top_gastos"]),
        "El asiento de APERTURA de Ecuador no entra al estado de resultados")
    chk(any("APERTURA" in norm(x["name"]) for x in ec["resultados"]["excluidos"]),
        "...y queda listado como excluido, con su monto y su motivo")
    chk(abs(ec["resultados"]["ventas_netas"] - (1118645.46 + 158798.92)) < 1,
        "Ecuador cose el EEFF oficial (Ene-Jul) con lo de Odoo (desde agosto)")
    chk(ec["resultados"]["resultado_neto"] > 0,
        "Ecuador no muestra la pérdida ficticia de −232.908 que da leer la apertura como P&G")
    chk(abs(ec["balance"]["activo_total"] - (88680.10 + 585864.42 + 544178.76 + 36346.84)) < 1,
        "El balance sí incluye el efecto de la apertura: ahí es donde corresponde")
    chk(ec["balance"]["inventarios"] == 544178.76,
        "El inventario se separa de 'otros activos corrientes' por nombre de cuenta")
    chk(ec["balance"]["deuda_financiera"] == 307020.98 and ec["balance"]["deuda_financiera_lp"] == 19895.25
        and ec["balance"]["deuda_financiera_total"] == 326916.23,
        "La deuda financiera se separa por plazo: corto plazo en el corriente, largo plazo fuera")
    chk(ec["balance"]["resultado_del_ejercicio_odoo"] != ec["balance"]["resultado_del_ano_gestion"],
        "El balance cierra con el resultado de Odoo; el del año de gestión se reporta aparte sin doble conteo")
    chk(not co["resultados"]["confiable"] and co["resultados"]["cuentas_sospechosas"],
        "Colombia: la cuenta de 6.600 M se marca como misposting y el resultado se declara NO confiable")
    chk(any("AJUSTE INICIAL" in norm(x["name"]) for x in co["resultados"]["excluidos"]),
        "Las cuentas AJUSTE INICIAL de VINTRAL quedan fuera del P&G y listadas")
    chk(not cr["resultados"]["confiable"] and "costo de ventas" in (cr["resultados"]["motivo_no_confiable"] or "").lower(),
        "Costa Rica: sin costo de ventas, el margen se declara hueco en vez de mostrar 100%")
    chk(all("VIX" not in (p.get("compania") or "") for p in doc["paises"].values()),
        "VIX excluida del dashboard financiero")
    chk(doc["consolidado"]["referencial"] is True and doc["tc"]["referencial"] is True,
        "Todo USD consolidado va marcado como referencial")
    chk(doc["consolidado"]["resultado_confiable"] is False,
        "El consolidado avisa que incluye países con resultado no confiable")
    chk(ec["indicadores"]["liquidez_corriente"] is not None and ec["indicadores"]["ciclo_de_caja"] is not None,
        "Los indicadores por país se calculan (liquidez, ciclo de caja)")
    chk(cr["indicadores"]["ciclo_de_caja"] is None and cr["indicadores"].get("motivo_ciclo"),
        "Sin costo de ventas, el ciclo de caja se declara ausente en vez de inventarse")
    chk(ec["balance"]["cuadra"], "El balance de Ecuador cierra: activo = pasivo + patrimonio + resultado")
    escribir(doc)
    chk(DEST.exists(), "El JSON se escribe de forma atómica")
    escribir(doc)
    chk(len(list((OUT / "historico_finanzas").glob("*.json"))) == 1,
        "Idempotente: dos corridas no duplican archivos")
    print("-" * 76)
    if fallos:
        print("AUTOPRUEBA FALLÓ (%d):" % len(fallos))
        for f in fallos:
            print("   - " + f)
        sys.exit(1)
    print("AUTOPRUEBA OK — %d comprobaciones" % 19)
    imprimir(doc)


def diagnostico():
    cfg = load_config()
    od = Odoo(cfg); od.authenticate()
    reglas = load_reglas()
    print("=" * 78)
    print("  DIAG finanzas_dashboard.py")
    print("=" * 78)
    print("  Odoo %s db=%s uid=%s" % (cfg["url"], cfg["db"], od.uid))
    print("  Reglas: finanzas_reglas.json v%s" % reglas.get("version"))
    print("  EEFF oficial EC: %s" % ("existe" if (PROJ / "Finanzas" / "eeff_ecuador_2026-07_OFICIAL.json").exists() else "NO EXISTE"))
    comps = companias(od, (cfg.get("_raw") or {}).get("company_map") or {})
    hoy = datetime.date.today()
    for c in comps.values():
        marca = "EXCLUIDA" if c["excluida"] else (c["pais"] or "SIN MAPEAR")
        print("\n  [%s] %-46s %-4s -> %s" % (c["id"], c["name"][:46], c["moneda"] or "?", marca))
        if c["excluida"] or not c["pais"]:
            continue
        pl = plan_de_cuentas(od, c["id"])
        tipos = defaultdict(int)
        for a in pl.values():
            tipos[a["account_type"]] += 1
        print("      cuentas: %d  |  tipos: %s" % (len(pl), dict(tipos)))
        s = saldos(od, c["id"], None, hoy.isoformat())
        act = sum(v for k, v in s.items() if (pl.get(k) or {}).get("account_type") in ACTIVO)
        pas = -sum(v for k, v in s.items() if (pl.get(k) or {}).get("account_type") in PASIVO)
        pat = -sum(v for k, v in s.items() if (pl.get(k) or {}).get("account_type") in PATRIMONIO)
        print("      activo {:,.2f}  pasivo {:,.2f}  patrimonio {:,.2f}  descuadre {:,.2f}".format(
            act, pas, pat, act - pas - pat))
    print("\n  Llamadas XML-RPC: %d" % od.calls)


def por_asiento(year=None):
    """De donde sale CADA peso del estado de resultados, asiento por asiento.

    Existe porque el P&G daba ventas muy por encima de las ventas conciliadas y
    suponer la causa no es medirla. Si un solo asiento concentra el ingreso, es
    traslado de saldos de la migracion, no venta del ejercicio."""
    cfg = load_config()
    od = Odoo(cfg); od.authenticate()
    reglas = load_reglas()
    year = int(year or datetime.date.today().year)
    hoy = datetime.date.today()
    ini = "%d-01-01" % year
    hasta = hoy.isoformat()
    print("=" * 96)
    print("  ASIENTOS DEL ESTADO DE RESULTADOS  %s .. %s" % (ini, hasta))
    print("=" * 96)
    comps = companias(od, (cfg.get("_raw") or {}).get("company_map") or {})
    for c in comps.values():
        if c["excluida"] or not c["pais"]:
            continue
        cid = c["id"]
        pl = plan_de_cuentas(od, cid)
        ids_ing = [a["id"] for a in pl.values() if a["account_type"] in INGRESO]
        ids_gas = [a["id"] for a in pl.values() if a["account_type"] in GASTO]
        print("\n" + "-" * 96)
        print("  %s  [%s] %s   cuentas ingreso=%d gasto=%d"
              % (c["pais"], cid, c["name"][:40], len(ids_ing), len(ids_gas)))
        print("-" * 96)
        if not ids_ing and not ids_gas:
            print("  sin cuentas de resultado"); continue

        def grupo(ids, campo):
            if not ids:
                return {}
            dom = [["parent_state", "=", "posted"], ["company_id", "=", cid],
                   ["date", ">=", ini], ["date", "<=", hasta], ["account_id", "in", ids]]
            rows = od.kw("account.move.line", "read_group",
                         [dom, ["balance:sum"], [campo]],
                         {"lazy": False, "context": {"allowed_company_ids": [cid]}})
            out = {}
            for r in rows:
                k = r.get(campo)
                if isinstance(k, (list, tuple)):
                    k = k[0]
                if k is None or k is False:
                    continue
                out[k] = {"balance": float(r.get("balance") or 0),
                          "lineas": int(r.get("__count") or 0)}
            return out

        ing = grupo(ids_ing, "move_id")
        gas = grupo(ids_gas, "move_id")
        mids = sorted(set(list(ing.keys()) + list(gas.keys())))
        if not mids:
            print("  sin lineas de resultado en el periodo"); continue
        # El nombre se lee explicito: NUNCA por name_get, que en account.move pasa por
        # l10n_ec y puede devolver basura o reventar sin decir por que.
        meta = {}
        for i in range(0, len(mids), 300):
            for m in od.sr("account.move", [["id", "in", mids[i:i + 300]]],
                           ["name", "date", "journal_id", "ref"],
                           ctx={"allowed_company_ids": [cid]}):
                jid, jn = m2o(m.get("journal_id"))
                meta[m["id"]] = {"name": m.get("name") or "?", "date": m.get("date") or "?",
                                 "diario": jn or "?", "ref": m.get("ref") or ""}
        filas = []
        for mid in mids:
            i = ing.get(mid) or {"balance": 0.0, "lineas": 0}
            g = gas.get(mid) or {"balance": 0.0, "lineas": 0}
            mt = meta.get(mid) or {"name": "id=%s" % mid, "date": "?", "diario": "?", "ref": ""}
            filas.append({"id": mid, "name": mt["name"], "date": mt["date"], "diario": mt["diario"],
                          "ref": mt["ref"], "ingreso": -i["balance"], "gasto": g["balance"],
                          "lineas": i["lineas"] + g["lineas"]})
        tot_ing = sum(f["ingreso"] for f in filas)
        tot_gas = sum(f["gasto"] for f in filas)
        print("  TOTAL ingreso {:>18,.2f}   gasto {:>18,.2f}   asientos {:>5d}".format(
            tot_ing, tot_gas, len(filas)))
        filas.sort(key=lambda f: abs(f["ingreso"]), reverse=True)
        print("\n  Top 12 asientos por INGRESO")
        print("  {:<26} {:<10} {:<14} {:>5} {:>16} {:>7}".format(
            "asiento", "fecha", "diario", "lin", "ingreso", "%"))
        for f in filas[:12]:
            pct = (f["ingreso"] / tot_ing * 100.0) if tot_ing else 0.0
            marca = ""
            if tot_ing and pct > 25.0 and f["lineas"] > 20:
                marca = "   <== probable traslado de saldos"
            print("  {:<26.26} {:<10} {:<14.14} {:>5d} {:>16,.2f} {:>6.1f}%{}".format(
                f["name"], f["date"], f["diario"], f["lineas"], f["ingreso"], pct, marca))
        filas.sort(key=lambda f: abs(f["gasto"]), reverse=True)
        print("\n  Top 8 asientos por GASTO")
        for f in filas[:8]:
            pct = (f["gasto"] / tot_gas * 100.0) if tot_gas else 0.0
            print("  {:<26.26} {:<10} {:<14.14} {:>5d} {:>16,.2f} {:>6.1f}%".format(
                f["name"], f["date"], f["diario"], f["lineas"], f["gasto"], pct))
        # Fechas que concentran ingreso: una migracion se delata por la fecha, no por el nombre.
        porf = {}
        for f in filas:
            porf[f["date"]] = porf.get(f["date"], 0.0) + f["ingreso"]
        top = sorted(porf.items(), key=lambda kv: abs(kv[1]), reverse=True)[:8]
        print("\n  Fechas que mas ingreso concentran")
        for d, v in top:
            pct = (v / tot_ing * 100.0) if tot_ing else 0.0
            print("  {:<12} {:>18,.2f} {:>6.1f}%".format(d, v, pct))
        # Diarios: si el ingreso no viene de facturacion, no es venta.
        pord = {}
        for f in filas:
            pord[f["diario"]] = pord.get(f["diario"], 0.0) + f["ingreso"]
        print("\n  Ingreso por DIARIO")
        for d, v in sorted(pord.items(), key=lambda kv: abs(kv[1]), reverse=True):
            pct = (v / tot_ing * 100.0) if tot_ing else 0.0
            print("  {:<28.28} {:>18,.2f} {:>6.1f}%".format(d, v, pct))
        # Y lo que hoy se excluye por nombre de cuenta, para ver si alcanza.
        exc = [a for a in pl.values() if a["account_type"] in INGRESO
               and excluir_del_resultado(a, c["pais"], reglas)]
        print("\n  Cuentas de ingreso excluidas hoy por regla de nombre: %d" % len(exc))
        for a in exc[:6]:
            print("    %-12s %s" % (a.get("code"), (a.get("name") or "")[:60]))
    print("\n  Llamadas XML-RPC: %d" % od.calls)


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else str(datetime.date.today().year)
    if arg == "autotest":
        _autotest(); return
    if arg == "diag":
        diagnostico(); return
    if arg == "asientos":
        por_asiento(sys.argv[2] if len(sys.argv) > 2 else None); return
    year = int(arg) if arg.isdigit() else datetime.date.today().year
    av = Avisos()
    od = Odoo(load_config()); od.authenticate()
    log("Odoo %s db='%s' uid=%s" % (od.cfg["url"], od.cfg["db"], od.uid))
    doc = construir(od, year, av)
    escribir(doc)
    imprimir(doc)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("[ERROR]\n" + traceback.format_exc())
        sys.exit(1)
