#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
productos_dashboard.py  ·  Grupo VICOMER
========================================
EXTRACCION -> CONTRATO JSON  del dashboard de MARGENES Y VENTAS POR PRODUCTO.

Este script NO dibuja nada. Deja en OdooVentas/dashboard_productos.json un
documento auto-descriptivo con las cifras, la FUENTE de cada una, la ventana de
tiempo real de cada pais y los huecos declarados como huecos.

POR QUE NO SE USA EL MAYOR
--------------------------
El bloque 'mix' de dashboard_ventas.json agrupa account.move.line por producto.
Medido el 2026-09-10 eso da, en Ecuador, 1.114.344 de 1.325.554 en la fila
"(sin producto)": el 84% de la venta. La razon es que el traslado de saldos de
la migracion entro por asiento resumen, sin producto. El mayor sirve para el
P&G; para analisis por SKU es inservible.

Aqui la venta por producto sale de las LINEAS DE FACTURA (account.move.line de
facturas out_invoice/out_refund posted), que si llevan producto, cantidad y
precio unitario. Eso acota la ventana: en Ecuador el detalle por producto solo
existe desde la migracion (ago-2026), en Colombia desde abr-2026. El dashboard
declara esa ventana en cada bloque; NO la disfraza de "el ano".

REGLAS NO NEGOCIABLES
  * Una cifra sin fuente verificable no entra. Antes de estimar, se muestra el
    hueco marcado como hueco.
  * Venta por producto = price_subtotal de la linea (neto sin IVA), con signo
    invertido en notas de credito.
  * El COSTO tiene cuatro fuentes posibles. Se mide la COBERTURA de todas y se
    elige por pais la mejor. Se declara cual se uso y cuanto cubre.
      A. stock.valuation.layer  -> costo real de la salida de inventario
      B. sale.order.line.purchase_price -> costo teorico del pedido
      C. COGS del mayor por producto -> prorrateo, solo si lleva producto
      D. product.standard_price -> costo ACTUAL, no historico (ultimo recurso)
  * Si la cobertura de costo < UMBRAL_MARGEN (85%) el margen se marca parcial.
    Si < UMBRAL_MINIMO (50%) NO se publica margen: solo mix de venta.
  * VIX S.A.S. se excluye del consolidado.
  * El USD consolidado es REFERENCIAL (tc_manual de pagos_reglas_depto.json).
  * Un cero real y un dato faltante deben verse distintos.

MODOS
    python3 productos_dashboard.py autotest   # offline, sin red
    python3 productos_dashboard.py diag       # cobertura de fuentes, no escribe
    python3 productos_dashboard.py 2026       # extraccion completa
    python3 productos_dashboard.py            # ano en curso

Solo biblioteca estandar.
"""

import os, sys, json, ssl, math, datetime, traceback, xmlrpc.client
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
OUT_DIR = Path(os.environ.get("ODOO_OUT_DIR", PROJ / "OdooVentas"))
JSON_OUT = OUT_DIR / "dashboard_productos.json"
JSON_VENTAS = OUT_DIR / "dashboard_ventas.json"
REGLAS_F = PROJ / "productos_reglas.json"

MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
CHUNK = 200                 # ids de factura por llamada; mas alto revienta el XML-RPC
UMBRAL_MARGEN = 0.85        # bajo esto el margen se marca parcial
UMBRAL_MINIMO = 0.50        # bajo esto NO se publica margen
TOP_PRODUCTOS = 60
MARGEN_IMPOSIBLE = 0.90     # margen bruto por encima de esto en distribucion = misposting

COSTO_TIPOS = ("cost_of_revenue", "expense_direct_cost")


def log(m):
    sys.stderr.write("%s  %s\n" % (datetime.datetime.now().strftime("%H:%M:%S"), m))
    sys.stderr.flush()


def norm(t):
    t = (t or "").upper()
    for a, b in (("Á", "A"), ("É", "E"), ("Í", "I"), ("Ó", "O"), ("Ú", "U"), ("Ñ", "N")):
        t = t.replace(a, b)
    return " ".join(t.split())


def contiene(txt, pats):
    n = norm(txt)
    return any(norm(p) and norm(p) in n for p in (pats or []))


def r2(x):
    return None if x is None else round(float(x), 2)


def r4(x):
    return None if x is None else round(float(x), 4)


class Avisos(object):
    def __init__(self):
        self.items = []

    def add(self, nivel, pais, bloque, texto):
        self.items.append({"nivel": nivel, "pais": pais, "bloque": bloque, "texto": texto})
        log("  [%s] %s/%s: %s" % (nivel.upper(), pais or "GRUPO", bloque, texto))

    def dump(self):
        orden = {"critico": 0, "alerta": 1, "nota": 2}
        return sorted(self.items, key=lambda a: (orden.get(a["nivel"], 9), a["pais"] or "", a["bloque"]))


# =====================================================================
#  Configuracion
# =====================================================================
def load_config():
    cfg = {"url": os.environ.get("ODOO_URL"), "db": os.environ.get("ODOO_DB"),
           "login": os.environ.get("ODOO_LOGIN"), "apikey": os.environ.get("ODOO_APIKEY")}
    extra = {}
    for f in (Path(__file__).resolve().parent / "odoo_config.json",
              PROJ / "odoo_config.json", HOME / ".odoo_config.json"):
        if f.exists():
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                for k in ("url", "db", "login", "apikey"):
                    cfg[k] = cfg[k] or d.get(k)
                extra = extra or d
            except Exception as e:
                log("[WARN] no se pudo leer %s: %s" % (f, e))
    for kf in (PROJ / "odoo_apikey.txt", HOME / ".odoo_apikey"):
        if not cfg["apikey"] and kf.exists():
            cfg["apikey"] = kf.read_text(encoding="utf-8").strip()
    if cfg.get("url"):
        cfg["url"] = cfg["url"].rstrip("/")
    cfg["_raw"] = extra
    return cfg


DEFAULT_REGLAS = {
    "version": 1,
    "_nota": ("Reglas editables del dashboard de productos. Cambiar aqui NO exige tocar el "
              "codigo. Si una regla cambia el resultado, el JSON lo declara en 'reglas_aplicadas'."),
    "costo": {
        "precedencia": ["valuation_layer", "sale_line", "mayor", "standard_price"],
        "cogs_nombre_contiene": ["COSTO DE LA MERCANCIA VENDIDA", "COSTO DE VENTA",
                                 "COSTO DE MERCADERIA", "COSTO DE LOS BIENES"],
        "_nota": ("Odoo no tiene ninguna cuenta tipificada como costo directo en las tres "
                  "empresas. Mientras no se corrija el account_type, el COGS del mayor se "
                  "rescata por NOMBRE. Es un parche y esta declarado como tal.")
    },
    "producto": {
        "excluir_sku": [],
        "excluir_nombre_contiene": ["FLETE", "TRANSPORTE", "INSTALACION", "ANTICIPO",
                                    "DESCUENTO", "SERVICIO TECNICO", "REDONDEO"],
        "_nota": ("Servicios y ajustes distorsionan el margen por SKU: no llevan costo de "
                  "inventario y ensucian el Pareto. Se listan aparte, no se borran.")
    },
    "umbrales": {
        "margen_confiable": UMBRAL_MARGEN,
        "margen_minimo_publicable": UMBRAL_MINIMO,
        "margen_imposible": MARGEN_IMPOSIBLE,
        "dispersion_precio_alerta": 0.25,
        "pareto": 0.80
    }
}


def load_reglas():
    if REGLAS_F.exists():
        try:
            d = json.loads(REGLAS_F.read_text(encoding="utf-8"))
            base = json.loads(json.dumps(DEFAULT_REGLAS))
            for k, v in d.items():
                if isinstance(v, dict) and isinstance(base.get(k), dict):
                    base[k].update(v)
                else:
                    base[k] = v
            return base
        except Exception as e:
            log("[WARN] productos_reglas.json ilegible (%s), se usan los defaults" % e)
    return json.loads(json.dumps(DEFAULT_REGLAS))


def load_tc():
    tc = {"COP": 0.00027027, "CRC": 0.00221, "USD": 1.0}
    fuente = "default embebido"
    f = PROJ / "pagos_reglas_depto.json"
    if f.exists():
        try:
            man = (json.loads(f.read_text(encoding="utf-8")).get("tc_manual") or {})
            for k, v in man.items():
                tc[k] = float(v)
            fuente = "pagos_reglas_depto.json -> tc_manual"
        except Exception:
            pass
    tc["USD"] = 1.0
    return {"tasas": tc, "fuente": fuente, "referencial": True,
            "cop_por_usd": round(1.0 / tc["COP"], 2), "crc_por_usd": round(1.0 / tc["CRC"], 2),
            "_nota": ("Odoo devuelve 0.00031805 para COP, CRC y EUR por igual: no mantiene "
                      "tipos de cambio. Todo USD consolidado es REFERENCIAL.")}


# =====================================================================
#  Odoo
# =====================================================================
class Odoo(object):
    def __init__(self, cfg):
        self.cfg = cfg
        ctx = ssl.create_default_context()
        self.common = xmlrpc.client.ServerProxy(cfg["url"] + "/xmlrpc/2/common", allow_none=True, context=ctx)
        self.models = xmlrpc.client.ServerProxy(cfg["url"] + "/xmlrpc/2/object", allow_none=True, context=ctx)
        self.uid = None
        self.calls = 0

    def _dbs(self):
        cands = []
        if self.cfg.get("db"):
            cands.append(self.cfg["db"])
        host = self.cfg["url"].split("//")[-1].split("/")[0]
        cands += [host.split(".")[0], host.replace(".", "-"), host]
        seen, out = set(), []
        for c in cands:
            if c and c not in seen:
                seen.add(c); out.append(c)
        return out

    def authenticate(self):
        falta = [k for k in ("url", "login", "apikey") if not self.cfg.get(k)]
        if falta:
            raise RuntimeError("faltan credenciales de Odoo: " + ", ".join(falta))
        last = None
        for db in self._dbs():
            try:
                uid = self.common.authenticate(db, self.cfg["login"], self.cfg["apikey"], {})
            except Exception as e:
                last = str(e)[:200]; continue
            if uid:
                self.cfg["db"] = db; self.uid = uid; return uid
        raise RuntimeError("no autentico con ninguna base. Ultimo error: %s" % last)

    def kw(self, model, method, args, kwargs=None):
        self.calls += 1
        return self.models.execute_kw(self.cfg["db"], self.uid, self.cfg["apikey"],
                                      model, method, args, kwargs or {})

    def sr(self, model, domain, fields, limit=0, ctx=None):
        kw = {"fields": fields}
        if limit:
            kw["limit"] = limit
        if ctx:
            kw["context"] = ctx
        return self.kw(model, "search_read", [domain], kw)

    def sr_drop(self, model, domain, fields, ctx=None):
        """Reintenta quitando campos hasta que la consulta pase.

        Existe por l10n_ec: hay campos que revientan la lectura del modelo entero
        sin decir cual. Perder un campo es aceptable; perder la consulta no.
        """
        f = list(fields)
        omitidos = []
        while f:
            try:
                return self.sr(model, domain, f, ctx=ctx), omitidos
            except Exception as e:
                msg = str(e)
                drop = next((c for c in f if c in msg and c != "id"), None)
                if drop is None:
                    drop = f[-1] if len(f) > 1 else None
                if drop is None:
                    raise
                f.remove(drop); omitidos.append(drop)
        raise RuntimeError("no se pudo consultar " + model)


def _m2o(v):
    if isinstance(v, (list, tuple)) and len(v) == 2:
        return v[0], v[1]
    return None, None


def pais_de_empresa(nombre, company_map):
    n = norm(nombre)
    best, bl = None, -1
    for frag, pais in (company_map or {}).items():
        f = norm(frag)
        if f and f in n and len(f) > bl:
            best, bl = pais, len(f)
    return best


def companias(od, company_map):
    out = {}
    for r in od.sr("res.company", [], ["id", "name", "currency_id"]):
        _, cur = _m2o(r.get("currency_id"))
        p = pais_de_empresa(r.get("name"), company_map)
        out[r["id"]] = {"id": r["id"], "name": r.get("name"), "moneda": cur,
                        "pais": None if p in (None, "ignore") else p,
                        "excluida": p == "ignore"}
    return out


# =====================================================================
#  BLOQUE 1 — Lineas de factura: la unica fuente que lleva producto y cantidad
# =====================================================================
def facturas_del_ano(od, year, comp_ids):
    """Cabeceras de factura de venta. El filtro por move_type SI es seguro aqui:
    lo que revienta con l10n_ec es atravesar move_id.move_type DESDE la linea."""
    dom = [["move_type", "in", ["out_invoice", "out_refund"]],
           ["state", "=", "posted"],
           ["invoice_date", ">=", "%d-01-01" % year],
           ["invoice_date", "<=", "%d-12-31" % year]]
    recs, _om = od.sr_drop("account.move", dom,
                           ["id", "name", "invoice_date", "company_id", "move_type",
                            "currency_id", "amount_untaxed_signed", "partner_id"],
                           ctx={"allowed_company_ids": comp_ids})
    out = {}
    for r in recs:
        f = str(r.get("invoice_date") or "")[:10]
        if len(f) != 10:
            continue
        cid, _ = _m2o(r.get("company_id"))
        pid, pname = _m2o(r.get("partner_id"))
        out[r["id"]] = {"id": r["id"], "doc": r.get("name"), "fecha": f, "mes": int(f[5:7]),
                        "empresa_id": cid, "tipo": r.get("move_type"),
                        "signo": -1.0 if r.get("move_type") == "out_refund" else 1.0,
                        "neto": float(r.get("amount_untaxed_signed") or 0),
                        "cliente_id": pid, "cliente": pname or "(sin cliente)"}
    return out


def lineas_de_factura(od, moves, cid):
    """Lineas CON producto de las facturas de una compania.

    Se pasan los ids de factura explicitos en bloques. NUNCA se filtra por
    move_id.move_type desde account.move.line: eso atraviesa account.move, que
    l10n_ec deja roto, y devuelve VACIO sin lanzar error. Un dashboard que
    muestra cero porque la consulta se rompio es peor que uno que no muestra nada.
    """
    ids = [m["id"] for m in moves.values() if m["empresa_id"] == cid]
    campos = ["id", "move_id", "product_id", "quantity", "price_subtotal",
              "display_type", "product_uom_id", "name"]
    out = []
    omitidos = set()
    for i in range(0, len(ids), CHUNK):
        chunk = ids[i:i + CHUNK]
        recs, om = od.sr_drop("account.move.line",
                              [["move_id", "in", chunk], ["product_id", "!=", False]],
                              campos, ctx={"allowed_company_ids": [cid]})
        omitidos.update(om)
        for r in recs:
            dt = r.get("display_type")
            # display_type: 'product' en Odoo 17+, False en versiones previas. Cualquier
            # otro valor (tax, payment_term, line_section, line_note) NO es venta.
            if dt not in (False, None, "", "product"):
                continue
            mid, _ = _m2o(r.get("move_id"))
            mv = moves.get(mid)
            if not mv:
                continue
            pid, pname = _m2o(r.get("product_id"))
            if not pid:
                continue
            s = mv["signo"]
            out.append({"_line_id": r["id"],
                        "move_id": mid, "doc": mv["doc"], "fecha": mv["fecha"], "mes": mv["mes"],
                        "cliente_id": mv["cliente_id"], "cliente": mv["cliente"],
                        "producto_id": pid, "producto": pname or "(sin nombre)",
                        "unidades": float(r.get("quantity") or 0) * s,
                        "venta": float(r.get("price_subtotal") or 0) * s})
    return out, sorted(omitidos)


def maestro_productos(od, pids, cid):
    """Ficha del producto EN CONTEXTO DE UNA COMPANIA: standard_price y
    qty_available son company-dependent. Leerlos sin contexto mezcla los tres paises."""
    out = {}
    campos = ["id", "default_code", "name", "categ_id", "standard_price",
              "qty_available", "uom_id", "type", "active"]
    pids = list(pids)
    for i in range(0, len(pids), CHUNK):
        recs, _om = od.sr_drop("product.product", [["id", "in", pids[i:i + CHUNK]]], campos,
                               ctx={"allowed_company_ids": [cid]})
        for r in recs:
            _c, cname = _m2o(r.get("categ_id"))
            out[r["id"]] = {"id": r["id"], "sku": r.get("default_code") or "",
                            "nombre": r.get("name") or "",
                            "categoria": cname or "(sin categoria)",
                            "costo_std": float(r.get("standard_price") or 0),
                            "stock_unid": float(r.get("qty_available") or 0),
                            "tipo": r.get("type") or "",
                            "activo": bool(r.get("active", True))}
    return out


# =====================================================================
#  BLOQUE 2 — Costo por producto: cuatro fuentes, se mide y se elige
# =====================================================================
def costo_valuation(od, cid, desde, hasta, pids):
    """A. stock.valuation.layer — el costo REAL con que salio la unidad.

    Es la unica fuente que refleja lo que de verdad costo lo que se vendio.
    Si el modulo de valoracion no esta activo o la empresa no valora inventario,
    esto devuelve vacio y hay que decirlo, no inventarlo."""
    try:
        dom = [["company_id", "=", cid], ["product_id", "in", list(pids)],
               ["quantity", "<", 0], ["create_date", ">=", desde + " 00:00:00"],
               ["create_date", "<=", hasta + " 23:59:59"]]
        rows = od.kw("stock.valuation.layer", "read_group",
                     [dom, ["value:sum", "quantity:sum"], ["product_id"]],
                     {"lazy": False, "context": {"allowed_company_ids": [cid]}})
    except Exception as e:
        return {}, "stock.valuation.layer no disponible (%s)" % str(e)[:90]
    out = {}
    for r in rows:
        pid, _ = _m2o(r.get("product_id"))
        if not pid:
            continue
        # value viene negativo en la salida: el costo es su valor absoluto.
        out[pid] = {"cogs": abs(float(r.get("value") or 0)),
                    "unidades": abs(float(r.get("quantity") or 0))}
    return out, None


def costo_sale_line(od, cid, lineas, pids):
    """B. sale.order.line.purchase_price — el costo teorico con que se cotizo.

    Se llega por account.move.line.sale_line_ids. Si el campo no existe (venta
    facturada sin pedido) esto queda corto y la cobertura lo dira."""
    ids = list({l["_line_id"] for l in lineas if l.get("_line_id")})
    if not ids:
        return {}, "las lineas de factura no traen sale_line_ids"
    enlace = {}
    try:
        for i in range(0, len(ids), CHUNK):
            recs = od.sr("account.move.line", [["id", "in", ids[i:i + CHUNK]]],
                         ["id", "sale_line_ids", "product_id", "quantity"],
                         ctx={"allowed_company_ids": [cid]})
            for r in recs:
                sl = r.get("sale_line_ids") or []
                if sl:
                    enlace[r["id"]] = sl
    except Exception as e:
        return {}, "sale_line_ids ilegible (%s)" % str(e)[:80]
    if not enlace:
        return {}, "ninguna linea de factura esta enlazada a un pedido de venta"
    slids = sorted({s for v in enlace.values() for s in v})
    precio = {}
    try:
        for i in range(0, len(slids), CHUNK):
            for r in od.sr("sale.order.line", [["id", "in", slids[i:i + CHUNK]]],
                           ["id", "product_id", "purchase_price"],
                           ctx={"allowed_company_ids": [cid]}):
                pid, _ = _m2o(r.get("product_id"))
                precio[r["id"]] = (pid, float(r.get("purchase_price") or 0))
    except Exception as e:
        return {}, "purchase_price ilegible (%s)" % str(e)[:80]
    unit = {}
    for lid, sl in enlace.items():
        for s in sl:
            pid, pc = precio.get(s, (None, None))
            if pid and pc:
                unit.setdefault(pid, []).append(pc)
    return {p: {"costo_unitario": sum(v) / len(v)} for p, v in unit.items() if v}, None


def cuentas_costo(od, cid, reglas):
    """C. Cuentas de COGS. Ninguna de las tres empresas tiene account_type de costo
    directo, asi que se rescatan por NOMBRE. Parche declarado, no invisible."""
    porc, pornombre = [], []
    for a in od.sr("account.account", [], ["id", "code", "name", "account_type"],
                   ctx={"allowed_company_ids": [cid]}):
        if a.get("account_type") in COSTO_TIPOS:
            porc.append(a["id"])
        elif contiene(a.get("name"), (reglas.get("costo") or {}).get("cogs_nombre_contiene")):
            pornombre.append(a["id"])
    return porc, pornombre


def costo_mayor(od, cid, desde, hasta, acct_ids):
    """C. COGS del mayor agrupado por producto."""
    if not acct_ids:
        return {}, "no hay cuentas de costo identificables"
    try:
        rows = od.kw("account.move.line", "read_group",
                     [[["parent_state", "=", "posted"], ["company_id", "=", cid],
                       ["account_id", "in", acct_ids], ["date", ">=", desde], ["date", "<=", hasta]],
                      ["balance:sum"], ["product_id"]],
                     {"lazy": False, "context": {"allowed_company_ids": [cid]}})
    except Exception as e:
        return {}, "mayor ilegible (%s)" % str(e)[:80]
    out = {}
    for r in rows:
        pid, _ = _m2o(r.get("product_id"))
        if not pid:
            continue
        out[pid] = {"cogs": abs(float(r.get("balance") or 0))}
    return out, None


# =====================================================================
#  BLOQUE 3 — Eleccion de fuente de costo y armado del pais
# =====================================================================
def elegir_costo(venta_por_prod, candidatas, reglas):
    """Elige la fuente de costo por COBERTURA sobre la venta, no por preferencia.

    Cobertura = % de la venta con producto que esa fuente logra costear. Un costo
    que cubre el 30% de la venta no es un margen: es una opinion con decimales.
    """
    total = sum(abs(v["venta"]) for v in venta_por_prod.values()) or 0.0
    orden = (reglas.get("costo") or {}).get("precedencia") or ["valuation_layer", "sale_line", "mayor", "standard_price"]
    medidas = []
    for nombre in orden:
        c = candidatas.get(nombre) or {}
        datos, motivo = c.get("datos") or {}, c.get("motivo")
        cubierto = 0.0
        for pid, v in venta_por_prod.items():
            d = datos.get(pid)
            if not d:
                continue
            if d.get("cogs") is not None or d.get("costo_unitario") is not None:
                cubierto += abs(v["venta"])
        cob = (cubierto / total) if total else None
        medidas.append({"fuente": nombre, "cobertura_pct": r4(cob),
                        "n_productos": len(datos), "motivo": motivo,
                        "etiqueta": ETIQUETA_FUENTE.get(nombre, nombre)})
    # standard_price es el costo de HOY aplicado a unidades de ayer. Cubre siempre el
    # 100% y por eso ganaria toda comparacion por cobertura: seria elegir la fuente peor
    # justamente por ser la mas complaciente. Solo entra si ninguna fuente real llega al
    # minimo publicable.
    reales = [m for m in medidas if m["fuente"] != "standard_price"]
    mejor_real = max(reales, key=lambda m: (m["cobertura_pct"] or 0)) if reales else None
    elegida = None
    for m in reales:
        if (m["cobertura_pct"] or 0) >= UMBRAL_MARGEN:
            elegida = m["fuente"]; break
    if not elegida and mejor_real and (mejor_real["cobertura_pct"] or 0) >= UMBRAL_MINIMO:
        elegida = mejor_real["fuente"]
    if not elegida:
        std = next((m for m in medidas if m["fuente"] == "standard_price"), None)
        if std and (std["cobertura_pct"] or 0) > 0:
            elegida = "standard_price"
        elif mejor_real and (mejor_real["cobertura_pct"] or 0) > 0:
            elegida = mejor_real["fuente"]
    for m in medidas:
        m["elegida"] = (m["fuente"] == elegida)
    return elegida, medidas


ETIQUETA_FUENTE = {
    "valuation_layer": "stock.valuation.layer (costo real de la salida)",
    "sale_line": "sale.order.line.purchase_price (costo del pedido)",
    "mayor": "COGS del mayor por producto",
    "standard_price": "product.standard_price (costo ACTUAL, no historico)",
}


def hhi(pesos):
    t = sum(abs(p) for p in pesos) or 0.0
    if not t:
        return None
    return round(sum((abs(p) / t) ** 2 for p in pesos) * 10000, 1)


def es_excluible(prod, reglas):
    r = reglas.get("producto") or {}
    if prod["sku"] and prod["sku"] in (r.get("excluir_sku") or []):
        return True
    return bool(contiene(prod["nombre"], r.get("excluir_nombre_contiene")))


def construir_pais(od, cid, comp, pais, year, hoy, moves, reglas, avisos, tc):
    """Todo el pais en una funcion: lineas -> productos -> costo -> indicadores."""
    moneda = comp["moneda"] or "?"
    blk = {"moneda": moneda, "empresa": comp["name"], "empresa_id": cid}

    lineas, campos_omitidos = lineas_de_factura(od, moves, cid)
    if campos_omitidos:
        avisos.add("nota", pais, "extraccion",
                   "Odoo no devolvio estos campos de la linea de factura: %s. El bloque se "
                   "arma con lo que si vino." % ", ".join(campos_omitidos))
    blk["n_lineas"] = len(lineas)
    if not lineas:
        blk["disponible"] = False
        blk["motivo"] = ("Ninguna factura de venta de %s tiene lineas con producto en Odoo. "
                         "Sin lineas no hay unidades, ni precio unitario, ni margen por SKU." % pais)
        avisos.add("critico", pais, "productos", blk["motivo"])
        return blk
    blk["disponible"] = True

    # --- Ventana real. El detalle por producto NO cubre el ano: Ecuador migro en
    #     agosto y Colombia en abril. Presentar esto como "el ano" seria mentir.
    meses = sorted({l["mes"] for l in lineas})
    blk["ventana"] = {"mes_desde": meses[0], "mes_hasta": meses[-1],
                      "meses": [MESES[m - 1] for m in meses], "n_meses": len(meses),
                      "etiqueta": "%s-%s %d" % (MESES[meses[0] - 1], MESES[meses[-1] - 1], year),
                      "_nota": ("Es la ventana con detalle por producto, no el ano. Fuera de "
                                "ella la venta existe pero llego por asiento resumen, sin SKU.")}

    # --- Cuadre: cuanto de la venta facturada del periodo tiene producto
    mids = {l["move_id"] for l in lineas}
    neto_facturas = sum(m["neto"] for m in moves.values()
                        if m["empresa_id"] == cid and meses[0] <= m["mes"] <= meses[-1])
    venta_lineas = sum(l["venta"] for l in lineas)
    blk["cuadre"] = {
        "venta_lineas_con_producto": r2(venta_lineas),
        "venta_facturas_del_periodo": r2(neto_facturas),
        "diferencia": r2(neto_facturas - venta_lineas),
        "cobertura_producto_pct": r4(venta_lineas / neto_facturas) if neto_facturas else None,
        "n_facturas_con_producto": len(mids),
        "fuente": "account.move.line de facturas out_invoice/out_refund posted",
        "_nota": ("La diferencia son lineas de factura sin producto: fletes, servicios y "
                  "ajustes escritos a mano. No es un error mientras sea chica.")}
    cob = blk["cuadre"]["cobertura_producto_pct"]
    if cob is not None and cob < 0.90:
        avisos.add("alerta", pais, "cuadre",
                   "Solo el %.0f%% de la venta facturada de %s (%s) lleva producto en la linea. "
                   "El ranking por SKU no explica el %.0f%% restante."
                   % (cob * 100, blk["ventana"]["etiqueta"], moneda, (1 - cob) * 100))

    # --- Agregado por producto
    agg = {}
    for l in lineas:
        a = agg.setdefault(l["producto_id"], {"venta": 0.0, "unidades": 0.0, "clientes": set(),
                                              "mensual": defaultdict(float), "docs": set()})
        a["venta"] += l["venta"]
        a["unidades"] += l["unidades"]
        a["clientes"].add(l["cliente_id"])
        a["mensual"][l["mes"]] += l["venta"]
        a["docs"].add(l["move_id"])

    pids = list(agg.keys())
    maestro = maestro_productos(od, pids, cid)
    desde = "%d-%02d-01" % (year, meses[0])
    hasta = hoy.isoformat()

    # --- Las cuatro fuentes de costo, todas medidas
    val, mot_val = costo_valuation(od, cid, desde, hasta, pids)
    sl, mot_sl = costo_sale_line(od, cid, lineas, pids)
    porc, pornombre = cuentas_costo(od, cid, reglas)
    may, mot_may = costo_mayor(od, cid, desde, hasta, porc + pornombre)
    std = {p: {"costo_unitario": m["costo_std"]} for p, m in maestro.items() if m["costo_std"]}
    if porc:
        fuente_cogs = "account_type de costo directo (%d cuentas)" % len(porc)
    elif pornombre:
        fuente_cogs = "rescate por NOMBRE de cuenta (%d cuentas) — el account_type esta mal en Odoo" % len(pornombre)
        avisos.add("alerta", pais, "costo",
                   "%s no tiene ninguna cuenta tipificada como costo directo: el COGS se "
                   "rescata por nombre. Funciona hoy y se rompe el dia que alguien renombre "
                   "una cuenta. Corregir el account_type es trabajo de minutos." % comp["name"])
    else:
        fuente_cogs = None

    candidatas = {"valuation_layer": {"datos": val, "motivo": mot_val},
                  "sale_line": {"datos": sl, "motivo": mot_sl},
                  "mayor": {"datos": may, "motivo": mot_may},
                  "standard_price": {"datos": std,
                                     "motivo": "costo ACTUAL del producto, no el del momento de la venta"}}
    venta_prod = {p: {"venta": a["venta"]} for p, a in agg.items()}
    elegida, medidas = elegir_costo(venta_prod, candidatas, reglas)
    datos_costo = (candidatas.get(elegida) or {}).get("datos") or {}
    cobertura = next((m["cobertura_pct"] for m in medidas if m["fuente"] == elegida), None) or 0.0
    blk["costo"] = {"fuente_elegida": elegida, "etiqueta": ETIQUETA_FUENTE.get(elegida),
                    "cobertura_pct": r4(cobertura), "candidatas": medidas,
                    "cuentas_cogs": fuente_cogs,
                    "margen_publicable": cobertura >= UMBRAL_MINIMO,
                    "margen_confiable": cobertura >= UMBRAL_MARGEN}
    return _armar_productos(blk, agg, maestro, datos_costo, elegida, cobertura,
                            pais, moneda, meses, reglas, avisos, tc)


def _armar_productos(blk, agg, maestro, datos_costo, fuente, cobertura,
                     pais, moneda, meses, reglas, avisos, tc):
    umb = reglas.get("umbrales") or {}
    publicable = cobertura >= float(umb.get("margen_minimo_publicable", UMBRAL_MINIMO))
    # OJO: el denominador del mix son los PRODUCTOS, no todo lo facturado. Fletes,
    # instalaciones y ajustes se separan primero; si entran al total, los mix no
    # suman 100% y el error pasa desapercibido porque "casi" cuadra.
    venta_total_lineas = sum(a["venta"] for a in agg.values())
    total_venta = 0.0

    prods, servicios = [], []
    for pid, a in agg.items():
        m = maestro.get(pid) or {"sku": "", "nombre": "id=%s" % pid, "categoria": "(sin categoria)",
                                 "costo_std": 0.0, "stock_unid": 0.0, "tipo": "", "activo": True}
        d = datos_costo.get(pid) or {}
        cogs = d.get("cogs")
        if cogs is None and d.get("costo_unitario") is not None and a["unidades"]:
            cogs = float(d["costo_unitario"]) * a["unidades"]
        margen = (a["venta"] - cogs) if (publicable and cogs is not None) else None
        p = {
            "id": pid, "sku": m["sku"], "nombre": m["nombre"], "categoria": m["categoria"],
            "unidades": r2(a["unidades"]),
            "venta": r2(a["venta"]),
            "precio_prom": r2(a["venta"] / a["unidades"]) if a["unidades"] else None,
            "cogs": r2(cogs) if publicable else None,
            "costo_unit_prom": r2(cogs / a["unidades"]) if (publicable and cogs is not None and a["unidades"]) else None,
            "margen": r2(margen),
            "margen_pct": r4(margen / a["venta"]) if (margen is not None and a["venta"]) else None,
            "mix_venta_pct": None,
            "n_clientes": len(a["clientes"]),
            "n_facturas": len(a["docs"]),
            "mensual": {str(k): r2(v) for k, v in sorted(a["mensual"].items())},
            "stock_unid": r2(m["stock_unid"]),
            "stock_costo": r2(m["stock_unid"] * m["costo_std"]) if m["costo_std"] else None,
            "costo_std_actual": r2(m["costo_std"]),
            "fuente_costo": fuente if (publicable and cogs is not None) else None,
            "tiene_costo": cogs is not None,
        }
        if es_excluible(m, reglas):
            servicios.append(p)
        else:
            prods.append(p)
            total_venta += a["venta"]

    for p in prods:
        p["mix_venta_pct"] = r4(p["venta"] / total_venta) if total_venta else None

    # --- Mix de MARGEN. No es el mix de venta: ahi esta la mitad del oficio.
    total_margen = sum(p["margen"] for p in prods if p["margen"] is not None)
    for p in prods:
        p["mix_margen_pct"] = (r4(p["margen"] / total_margen)
                               if (p["margen"] is not None and total_margen) else None)
        # Rotacion y retorno del capital inmovilizado. El stock es el de HOY, no el
        # promedio del periodo: Odoo no guarda la serie. Se declara y no se disfraza.
        dias = max(1, len(meses) * 30)
        if p["cogs"] and p["stock_costo"]:
            p["dio"] = r2(p["stock_costo"] / (p["cogs"] / dias))
            p["gmroi"] = r2(p["margen"] / p["stock_costo"]) if p["margen"] is not None else None
        else:
            p["dio"] = None
            p["gmroi"] = None

    prods.sort(key=lambda p: abs(p["venta"] or 0), reverse=True)
    servicios.sort(key=lambda p: abs(p["venta"] or 0), reverse=True)

    # --- Pareto y concentracion
    corte = float(umb.get("pareto", 0.80))
    acum, n80 = 0.0, 0
    for p in prods:
        if total_venta and acum / total_venta >= corte:
            break
        acum += p["venta"] or 0
        n80 += 1
    blk["pareto"] = {"corte": corte, "n_skus_hasta_corte": n80, "n_skus_total": len(prods),
                     "pct_skus": r4(n80 / len(prods)) if prods else None,
                     "venta_acumulada": r2(acum),
                     "hhi_venta": hhi([p["venta"] or 0 for p in prods]),
                     "hhi_margen": hhi([p["margen"] or 0 for p in prods if p["margen"] is not None]) if total_margen else None,
                     "_nota": ("HHI sobre 2.500 = concentracion alta. Aqui mide dependencia de "
                               "pocos SKU, que en distribucion es riesgo de proveedor, no de cliente.")}

    # --- Categorias
    cat = {}
    for p in prods:
        c = cat.setdefault(p["categoria"], {"venta": 0.0, "margen": 0.0, "unidades": 0.0,
                                            "n_skus": 0, "con_margen": 0})
        c["venta"] += p["venta"] or 0
        c["unidades"] += p["unidades"] or 0
        c["n_skus"] += 1
        if p["margen"] is not None:
            c["margen"] += p["margen"]; c["con_margen"] += 1
    blk["categorias"] = sorted(
        [{"categoria": k, "venta": r2(v["venta"]), "unidades": r2(v["unidades"]),
          "n_skus": v["n_skus"],
          "margen": r2(v["margen"]) if v["con_margen"] else None,
          "margen_pct": r4(v["margen"] / v["venta"]) if (v["con_margen"] and v["venta"]) else None,
          "mix_venta_pct": r4(v["venta"] / total_venta) if total_venta else None}
         for k, v in cat.items()],
        key=lambda x: abs(x["venta"] or 0), reverse=True)

    # --- Alertas por producto: lo que un CFO quiere ver antes que el ranking
    imposible = float(umb.get("margen_imposible", MARGEN_IMPOSIBLE))
    negativos = [p for p in prods if p["margen"] is not None and p["margen"] < 0]
    raros = [p for p in prods if p["margen_pct"] is not None and p["margen_pct"] > imposible]
    sin_costo = [p for p in prods if not p["tiene_costo"]]
    stock_muerto = [p for p in prods
                    if (p["stock_costo"] or 0) > 0 and (p["dio"] is not None and p["dio"] > 365)]
    blk["alertas_producto"] = {
        "margen_negativo": {"n": len(negativos),
                            "venta": r2(sum(p["venta"] for p in negativos)),
                            "perdida": r2(sum(p["margen"] for p in negativos)),
                            "top": [{"sku": p["sku"], "nombre": p["nombre"], "venta": p["venta"],
                                     "margen": p["margen"], "margen_pct": p["margen_pct"]}
                                    for p in sorted(negativos, key=lambda x: x["margen"])[:10]]},
        "margen_imposible": {"n": len(raros), "umbral": imposible,
                             "top": [{"sku": p["sku"], "nombre": p["nombre"], "venta": p["venta"],
                                      "margen_pct": p["margen_pct"]} for p in raros[:10]],
                             "_nota": ("Margen bruto sobre %.0f%% en distribucion casi nunca es "
                                       "margen: es costo no contabilizado." % (imposible * 100))},
        "sin_costo": {"n": len(sin_costo),
                      "venta": r2(sum(p["venta"] for p in sin_costo)),
                      "pct_venta": r4(sum(p["venta"] for p in sin_costo) / total_venta) if total_venta else None,
                      "top": [{"sku": p["sku"], "nombre": p["nombre"], "venta": p["venta"]}
                              for p in sin_costo[:10]]},
        "stock_lento": {"n": len(stock_muerto),
                        "capital": r2(sum(p["stock_costo"] for p in stock_muerto)),
                        "top": [{"sku": p["sku"], "nombre": p["nombre"], "dio": p["dio"],
                                 "stock_costo": p["stock_costo"], "stock_unid": p["stock_unid"]}
                                for p in sorted(stock_muerto, key=lambda x: -(x["stock_costo"] or 0))[:10]]},
    }

    if negativos:
        avisos.add("critico", pais, "margen",
                   "%d SKU se vendieron con margen NEGATIVO en %s: %s de venta que destruye %s. "
                   "El primero es %s."
                   % (len(negativos), moneda,
                      "{:,.0f}".format(sum(p["venta"] for p in negativos)),
                      "{:,.0f}".format(abs(sum(p["margen"] for p in negativos))),
                      (sorted(negativos, key=lambda x: x["margen"])[0]["nombre"] or "?")[:50]))
    if raros:
        avisos.add("alerta", pais, "margen",
                   "%d SKU dan margen bruto sobre %.0f%%. En distribucion eso no es margen, "
                   "es costo que no se contabilizo contra la venta." % (len(raros), imposible * 100))
    if sin_costo and total_venta:
        pv = sum(p["venta"] for p in sin_costo) / total_venta
        if pv > 0.10:
            avisos.add("alerta", pais, "costo",
                       "El %.0f%% de la venta por producto de %s no tiene costo en ninguna de las "
                       "cuatro fuentes. Ese pedazo aparece sin margen, no con margen cero."
                       % (pv * 100, pais))
    if stock_muerto:
        avisos.add("alerta", pais, "inventario",
                   "%d SKU tienen mas de 365 dias de inventario al ritmo de venta actual: %s %s "
                   "de capital inmovilizado."
                   % (len(stock_muerto), moneda,
                      "{:,.0f}".format(sum(p["stock_costo"] for p in stock_muerto))))

    blk["productos"] = prods[:TOP_PRODUCTOS]
    blk["n_productos"] = len(prods)
    blk["servicios_y_ajustes"] = {"n": len(servicios), "venta": r2(sum(p["venta"] for p in servicios)),
                                  "items": servicios[:15],
                                  "_nota": ("Fletes, instalaciones y ajustes. No llevan costo de "
                                            "inventario: mezclarlos con los SKU deforma el margen.")}
    blk["totales"] = {
        "venta": r2(total_venta),
        "unidades": r2(sum(p["unidades"] or 0 for p in prods)),
        "cogs": r2(sum(p["cogs"] for p in prods if p["cogs"] is not None)) if publicable else None,
        "margen": r2(total_margen) if publicable else None,
        "margen_pct": r4(total_margen / sum(p["venta"] for p in prods if p["margen"] is not None))
                      if (publicable and total_margen) else None,
        "stock_costo": r2(sum(p["stock_costo"] for p in prods if p["stock_costo"])),
        "venta_lineas_incluyendo_servicios": r2(venta_total_lineas),
        "_nota_margen_pct": ("El margen % se calcula SOLO sobre la venta que tiene costo. "
                             "Dividirlo por la venta total lo hundiria artificialmente.")}
    if not publicable:
        blk["totales"]["motivo_sin_margen"] = (
            "La mejor fuente de costo cubre el %.0f%% de la venta por producto, por debajo del "
            "%.0f%% minimo. Se publica el MIX DE VENTA; el margen por SKU no se publica porque "
            "no se puede sostener." % (cobertura * 100, UMBRAL_MINIMO * 100))
        avisos.add("critico", pais, "margen", blk["totales"]["motivo_sin_margen"])
    elif cobertura < float(umb.get("margen_confiable", UMBRAL_MARGEN)):
        avisos.add("alerta", pais, "margen",
                   "El margen por SKU de %s se calcula sobre el %.0f%% de la venta con producto "
                   "(fuente: %s). Es direccional, no es la cifra de cierre."
                   % (pais, cobertura * 100, ETIQUETA_FUENTE.get(fuente, fuente)))
    return blk


# =====================================================================
#  BLOQUE 4 — Consolidado: el mismo SKU en tres paises
# =====================================================================
def comparativo_skus(paises, tc, reglas, avisos):
    """El mismo producto vendido en Ecuador, Colombia y Costa Rica.

    Es la pregunta que solo se puede hacer desde el holding: si el mismo horno
    deja 39% en Colombia y 22% en Ecuador, o el precio esta mal puesto o el costo
    de importacion no esta bien asignado. Los precios se llevan a USD con TC
    REFERENCIAL: sirven para comparar, no para facturar.
    """
    tasas = tc["tasas"]
    porsku = {}
    for pais, b in paises.items():
        if not b.get("disponible"):
            continue
        cur = b.get("moneda") or "USD"
        t = float(tasas.get(cur) or 1.0)
        for p in b.get("productos") or []:
            clave = p["sku"] or ("#%s" % p["id"])
            e = porsku.setdefault(clave, {"sku": p["sku"], "nombre": p["nombre"], "paises": {}})
            e["paises"][pais] = {
                "unidades": p["unidades"], "venta_usd": r2((p["venta"] or 0) * t),
                "precio_prom_usd": r2(p["precio_prom"] * t) if p["precio_prom"] else None,
                "margen_pct": p["margen_pct"], "moneda": cur}
    umbral = float((reglas.get("umbrales") or {}).get("dispersion_precio_alerta", 0.25))
    out = []
    for clave, e in porsku.items():
        if len(e["paises"]) < 2:
            continue
        precios = [v["precio_prom_usd"] for v in e["paises"].values() if v["precio_prom_usd"]]
        margenes = [v["margen_pct"] for v in e["paises"].values() if v["margen_pct"] is not None]
        disp = None
        if len(precios) >= 2 and min(precios) > 0:
            disp = (max(precios) - min(precios)) / min(precios)
        e["precio_min_usd"] = r2(min(precios)) if precios else None
        e["precio_max_usd"] = r2(max(precios)) if precios else None
        e["dispersion_precio_pct"] = r4(disp)
        e["brecha_margen_pp"] = r4(max(margenes) - min(margenes)) if len(margenes) >= 2 else None
        e["n_paises"] = len(e["paises"])
        e["venta_usd"] = r2(sum(v["venta_usd"] or 0 for v in e["paises"].values()))
        e["alerta_precio"] = bool(disp is not None and disp > umbral)
        out.append(e)
    out.sort(key=lambda x: abs(x["venta_usd"] or 0), reverse=True)
    disparejos = [e for e in out if e["alerta_precio"]]
    if disparejos:
        peor = max(disparejos, key=lambda e: e["dispersion_precio_pct"])
        avisos.add("alerta", None, "precios",
                   "%d SKU se venden en mas de un pais con precios que difieren mas de %.0f%%. "
                   "El extremo es %s: USD %s contra USD %s (%.0f%%). O el pricing es deliberado "
                   "y hay que decirlo, o hay dinero sobre la mesa."
                   % (len(disparejos), umbral * 100, (peor["nombre"] or peor["sku"])[:45],
                      "{:,.0f}".format(peor["precio_min_usd"] or 0),
                      "{:,.0f}".format(peor["precio_max_usd"] or 0),
                      (peor["dispersion_precio_pct"] or 0) * 100))
    return {"skus": out[:40], "n_skus_multipais": len(out), "n_alerta_precio": len(disparejos),
            "umbral_dispersion": umbral, "moneda": "USD referencial",
            "_nota": "TC referencial de pagos_reglas_depto.json. Comparar, no facturar."}


def consolidar(paises, tc, avisos):
    tasas = tc["tasas"]
    tot = {"venta_usd": 0.0, "margen_usd": 0.0, "cogs_usd": 0.0, "stock_usd": 0.0,
           "n_productos": 0, "unidades": 0.0}
    sin_margen = []
    for pais, b in paises.items():
        if not b.get("disponible"):
            continue
        t = float(tasas.get(b.get("moneda") or "USD") or 1.0)
        tt = b.get("totales") or {}
        tot["venta_usd"] += (tt.get("venta") or 0) * t
        tot["unidades"] += (tt.get("unidades") or 0)
        tot["stock_usd"] += (tt.get("stock_costo") or 0) * t
        tot["n_productos"] += b.get("n_productos") or 0
        if tt.get("margen") is None:
            sin_margen.append(pais)
        else:
            tot["margen_usd"] += tt["margen"] * t
            tot["cogs_usd"] += (tt.get("cogs") or 0) * t
    for k in ("venta_usd", "margen_usd", "cogs_usd", "stock_usd", "unidades"):
        tot[k] = r2(tot[k])
    base = (tot["margen_usd"] or 0) + (tot["cogs_usd"] or 0)
    tot["margen_pct"] = r4(tot["margen_usd"] / base) if base else None
    tot["paises_sin_margen"] = sin_margen
    tot["tc_referencial"] = True
    if sin_margen:
        avisos.add("alerta", None, "consolidado",
                   "El margen consolidado NO incluye a %s porque ahi el costo por producto no "
                   "alcanza el minimo publicable. La cifra existe, pero no es del grupo entero."
                   % ", ".join(sin_margen))
    return tot


def conciliar(paises, avisos):
    """Contra dashboard_ventas.json, que ya esta conciliado contra el EEFF oficial.

    No se concilia contra el ano: se concilia contra la MISMA VENTANA. Cuadrar
    contra una referencia sesgada no valida nada.
    """
    res = []
    if not JSON_VENTAS.exists():
        res.append({"ok": None, "pais": None, "prueba": "dashboard_ventas.json",
                    "detalle": "no existe: no hay contra que conciliar"})
        return res
    try:
        dv = json.loads(JSON_VENTAS.read_text(encoding="utf-8"))
    except Exception as e:
        res.append({"ok": False, "pais": None, "prueba": "dashboard_ventas.json",
                    "detalle": "ilegible: %s" % str(e)[:80]})
        return res
    for pais, b in paises.items():
        if not b.get("disponible"):
            continue
        ref = ((dv.get("paises") or {}).get(pais) or {})
        mensual = ref.get("mensual") or {}
        v = b["ventana"]
        esperado = 0.0
        faltan = []
        for m in range(v["mes_desde"], v["mes_hasta"] + 1):
            x = mensual.get(str(m), mensual.get(m))
            if x is None:
                faltan.append(m)
            else:
                esperado += float(x)
        real = b["cuadre"]["venta_facturas_del_periodo"] or 0.0
        dif = real - esperado
        tol = max(1.0, abs(esperado) * 0.005)
        res.append({"ok": abs(dif) <= tol if not faltan else None, "pais": pais,
                    "prueba": "Venta facturada %s vs dashboard_ventas.json" % v["etiqueta"],
                    "esperado": r2(esperado), "real": r2(real), "diferencia": r2(dif),
                    "detalle": ("faltan meses en el dashboard de ventas: %s" % faltan) if faltan else None})
        if not faltan and abs(dif) > tol:
            avisos.add("critico", pais, "conciliacion",
                       "La venta facturada de %s (%s) da %s contra %s del dashboard de ventas ya "
                       "conciliado: %s de diferencia. Uno de los dos esta mal y hasta saber cual, "
                       "el ranking por SKU se lee con reserva."
                       % (v["etiqueta"], b["moneda"], "{:,.2f}".format(real),
                          "{:,.2f}".format(esperado), "{:,.2f}".format(dif)))
    return res


# =====================================================================
#  Orquestacion
# =====================================================================
def construir(od, year, avisos, hoy=None, reglas=None):
    hoy = hoy or datetime.date.today()
    reglas = reglas or load_reglas()
    tc = load_tc()
    cfg_raw = (od.cfg.get("_raw") or {})
    comps = companias(od, cfg_raw.get("company_map") or {})
    activas = {cid: c for cid, c in comps.items() if c["pais"] and not c["excluida"]}
    excluidas = [c["name"] for c in comps.values() if c["excluida"]]
    sin_mapear = [c["name"] for c in comps.values() if not c["pais"] and not c["excluida"]]
    if sin_mapear:
        avisos.add("alerta", None, "empresas",
                   "Sin pais asignado en odoo_config.json -> company_map: %s. Quedan fuera del "
                   "dashboard." % ", ".join(sin_mapear))

    log("Facturas del ano...")
    moves = facturas_del_ano(od, year, list(activas.keys()))
    log("  %d facturas de venta" % len(moves))

    paises = {}
    for cid, c in sorted(activas.items(), key=lambda kv: kv[1]["pais"]):
        pais = c["pais"]
        log("Pais %s (%s)..." % (pais, c["name"]))
        b = construir_pais(od, cid, c, pais, year, hoy, moves, reglas, avisos, tc)
        if pais in paises and paises[pais].get("disponible"):
            # Dos empresas del mismo pais: se declara, no se suma en silencio.
            avisos.add("alerta", pais, "empresas",
                       "Hay mas de una empresa mapeada a %s. Se conserva la primera (%s); la "
                       "segunda (%s) NO se sumo." % (pais, paises[pais]["empresa"], c["name"]))
            continue
        paises[pais] = b

    comp = comparativo_skus(paises, tc, reglas, avisos)
    cons = consolidar(paises, tc, avisos)
    conc = conciliar(paises, avisos)

    return {
        "generado": datetime.datetime.now().isoformat(timespec="seconds"),
        "generado_fecha": hoy.isoformat(),
        "anio": year,
        "tc": tc,
        "reglas_aplicadas": {"version": reglas.get("version"),
                             "archivo": str(REGLAS_F) if REGLAS_F.exists() else "defaults embebidos",
                             "umbrales": reglas.get("umbrales"),
                             "precedencia_costo": (reglas.get("costo") or {}).get("precedencia")},
        "fuentes": {
            "venta_por_producto": "Odoo XML-RPC · account.move.line de facturas out_invoice/out_refund posted",
            "costo": "la mejor de cuatro fuentes por cobertura; declarada por pais en paises[X].costo",
            "inventario": "product.product.qty_available x standard_price, EN CONTEXTO DE CADA EMPRESA",
            "conciliacion": "OdooVentas/dashboard_ventas.json (ya conciliado contra el EEFF oficial)",
            "_por_que_no_el_mayor": ("account.move.line agrupado por producto deja el 84% de la "
                                     "venta de Ecuador en '(sin producto)': el traslado de saldos "
                                     "de la migracion entro por asiento resumen.")},
        "paises": paises,
        "comparativo_skus": comp,
        "consolidado": cons,
        "conciliacion": conc,
        "excluidas": excluidas,
        "odoo": {"url": od.cfg.get("url"), "db": od.cfg.get("db"), "llamadas": od.calls},
        "avisos": avisos.dump(),
    }


def escribir(doc):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = JSON_OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    # Degradacion elegante: el JSON bueno anterior se conserva. Si manana Odoo se cae,
    # el dashboard muestra datos viejos CON FECHA, no una pantalla vacia.
    if JSON_OUT.exists():
        hist = OUT_DIR / "historico_productos"
        hist.mkdir(exist_ok=True)
        try:
            prev = json.loads(JSON_OUT.read_text(encoding="utf-8"))
            (hist / ("dashboard_productos_%s.json" % str(prev.get("generado_fecha") or "prev"))).write_text(
                json.dumps(prev, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
    tmp.replace(JSON_OUT)
    log("Escrito %s (%.1f KB)" % (JSON_OUT, JSON_OUT.stat().st_size / 1024.0))


def _fmt(x, cur=""):
    if x is None:
        return "—"
    return ("{:,.2f}".format(x) if abs(x) < 1000 else "{:,.0f}".format(x)) + ((" " + cur) if cur else "")


def imprimir(doc):
    print("=" * 96)
    print("  MARGENES Y VENTAS POR PRODUCTO · GRUPO VICOMER · %s" % doc["anio"])
    print("  generado %s   ·   %s" % (doc["generado"], doc["fuentes"]["venta_por_producto"][:58]))
    print("=" * 96)
    for pais, b in doc["paises"].items():
        print("\n  %s  (%s)" % (pais.upper(), b.get("moneda")))
        if not b.get("disponible"):
            print("    SIN DETALLE POR PRODUCTO — %s" % b.get("motivo")); continue
        v, cu = b["ventana"], b["cuadre"]
        print("    ventana con detalle : %s   (%d mes(es))" % (v["etiqueta"], v["n_meses"]))
        print("    venta con producto  : %s de %s facturado  (%s)"
              % (_fmt(cu["venta_lineas_con_producto"]), _fmt(cu["venta_facturas_del_periodo"]),
                 "—" if cu["cobertura_producto_pct"] is None else "{:.0%}".format(cu["cobertura_producto_pct"])))
        c = b["costo"]
        print("    costo               : %s  cobertura %s  %s"
              % (c.get("etiqueta") or "SIN FUENTE",
                 "—" if c["cobertura_pct"] is None else "{:.0%}".format(c["cobertura_pct"]),
                 "" if c["margen_confiable"] else ("(PARCIAL)" if c["margen_publicable"] else "(NO PUBLICABLE)")))
        for m in c["candidatas"]:
            print("        %-52s %6s  %s" % (m["etiqueta"][:52],
                                             "—" if m["cobertura_pct"] is None else "{:.0%}".format(m["cobertura_pct"]),
                                             (m["motivo"] or "")[:34]))
        t = b["totales"]
        print("    venta %s   unidades %s   margen %s  (%s)"
              % (_fmt(t["venta"]), _fmt(t["unidades"]), _fmt(t["margen"]),
                 "—" if t["margen_pct"] is None else "{:.1%}".format(t["margen_pct"])))
        p = b["pareto"]
        print("    Pareto: %d de %d SKU hacen el %.0f%% de la venta   ·   HHI %s"
              % (p["n_skus_hasta_corte"], p["n_skus_total"], p["corte"] * 100, p["hhi_venta"]))
        a = b["alertas_producto"]
        print("    margen negativo %d SKU  ·  margen imposible %d  ·  sin costo %d  ·  stock lento %d"
              % (a["margen_negativo"]["n"], a["margen_imposible"]["n"],
                 a["sin_costo"]["n"], a["stock_lento"]["n"]))
        print("    top 5 por venta:")
        for x in (b["productos"] or [])[:5]:
            print("      %-42.42s u %8s  venta %14s  mg %6s"
                  % (x["nombre"] or x["sku"], _fmt(x["unidades"]), _fmt(x["venta"]),
                     "—" if x["margen_pct"] is None else "{:.1%}".format(x["margen_pct"])))
        conmg = [x for x in (b["productos"] or []) if x["margen"] is not None]
        if conmg:
            print("    top 5 por MARGEN aportado:")
            for x in sorted(conmg, key=lambda y: -(y["margen"] or 0))[:5]:
                print("      %-42.42s margen %13s  mix mg %6s"
                      % (x["nombre"] or x["sku"], _fmt(x["margen"]),
                         "—" if x["mix_margen_pct"] is None else "{:.1%}".format(x["mix_margen_pct"])))
    cs = doc["comparativo_skus"]
    print("\n  MISMO SKU EN VARIOS PAISES: %d  ·  con precio dispar (>%.0f%%): %d"
          % (cs["n_skus_multipais"], cs["umbral_dispersion"] * 100, cs["n_alerta_precio"]))
    for e in cs["skus"][:5]:
        print("    %-38.38s  USD %s .. %s   %s"
              % (e["nombre"] or e["sku"], _fmt(e["precio_min_usd"]), _fmt(e["precio_max_usd"]),
                 "  <== dispar" if e["alerta_precio"] else ""))
    c = doc["consolidado"]
    print("\n  GRUPO (USD referencial): venta %s · margen %s (%s) · inventario %s"
          % (_fmt(c["venta_usd"]), _fmt(c["margen_usd"]),
             "—" if c["margen_pct"] is None else "{:.1%}".format(c["margen_pct"]),
             _fmt(c["stock_usd"])))
    print("\n  CONCILIACION")
    for r in doc["conciliacion"]:
        marca = "OK " if r.get("ok") else ("!! " if r.get("ok") is False else " ? ")
        print("   %s %-11s %-52.52s dif %14s %s"
              % (marca, r.get("pais") or "", r.get("prueba"), _fmt(r.get("diferencia")),
                 r.get("detalle") or ""))
    av = doc["avisos"]
    print("\n  AVISOS (%d):" % len(av))
    for a in av:
        print("   [%-7s] %-11s %-12s %s" % (a["nivel"], a["pais"] or "GRUPO", a["bloque"], a["texto"][:118]))


# =====================================================================
#  DIAG — cobertura de fuentes, sin escribir nada
# =====================================================================
def diagnostico(year=None):
    cfg = load_config()
    od = Odoo(cfg); od.authenticate()
    reglas = load_reglas()
    year = int(year or datetime.date.today().year)
    hoy = datetime.date.today()
    print("=" * 96)
    print("  DIAG productos_dashboard.py   ano %d" % year)
    print("=" * 96)
    print("  Odoo %s  db=%s  uid=%s" % (cfg["url"], cfg["db"], od.uid))
    print("  Reglas: %s" % (REGLAS_F if REGLAS_F.exists() else "defaults embebidos"))
    comps = companias(od, (cfg.get("_raw") or {}).get("company_map") or {})
    activas = {cid: c for cid, c in comps.items() if c["pais"] and not c["excluida"]}
    moves = facturas_del_ano(od, year, list(activas.keys()))
    print("  Facturas de venta posted en %d: %d" % (year, len(moves)))
    for cid, c in sorted(activas.items(), key=lambda kv: kv[1]["pais"]):
        print("\n" + "-" * 96)
        print("  %s  [%s] %s  (%s)" % (c["pais"], cid, c["name"][:44], c["moneda"]))
        print("-" * 96)
        lineas, om = lineas_de_factura(od, moves, cid)
        if om:
            print("      campos que Odoo no devolvio: %s" % ", ".join(om))
        if not lineas:
            print("      SIN lineas con producto — el detalle por SKU no existe aqui"); continue
        meses = sorted({l["mes"] for l in lineas})
        neto = sum(m["neto"] for m in moves.values()
                   if m["empresa_id"] == cid and meses[0] <= m["mes"] <= meses[-1])
        vl = sum(l["venta"] for l in lineas)
        pids = sorted({l["producto_id"] for l in lineas})
        print("      lineas con producto : %d   SKU distintos: %d" % (len(lineas), len(pids)))
        print("      ventana             : %s-%s  (%d meses)"
              % (MESES[meses[0] - 1], MESES[meses[-1] - 1], len(meses)))
        print("      venta en lineas     : {:>18,.2f}".format(vl))
        print("      venta facturada     : {:>18,.2f}   cobertura producto {:.1%}".format(
            neto, (vl / neto) if neto else 0))
        maestro = maestro_productos(od, pids, cid)
        desde, hasta = "%d-%02d-01" % (year, meses[0]), hoy.isoformat()
        val, mv = costo_valuation(od, cid, desde, hasta, pids)
        sl, ms = costo_sale_line(od, cid, lineas, pids)
        porc, pornom = cuentas_costo(od, cid, reglas)
        may, mm = costo_mayor(od, cid, desde, hasta, porc + pornom)
        std = {p: {"costo_unitario": m["costo_std"]} for p, m in maestro.items() if m["costo_std"]}
        print("      cuentas de costo    : %d por account_type, %d rescatadas por nombre"
              % (len(porc), len(pornom)))
        vp = {}
        for l in lineas:
            vp.setdefault(l["producto_id"], {"venta": 0.0})["venta"] += l["venta"]
        cands = {"valuation_layer": {"datos": val, "motivo": mv}, "sale_line": {"datos": sl, "motivo": ms},
                 "mayor": {"datos": may, "motivo": mm},
                 "standard_price": {"datos": std, "motivo": "costo actual, no historico"}}
        eleg, med = elegir_costo(vp, cands, reglas)
        print("      COBERTURA DE COSTO:")
        for m in med:
            marca = "  <== elegida" if m["fuente"] == eleg else ""
            print("        %-50s %7s  n=%-4d %s%s"
                  % (m["etiqueta"][:50],
                     "—" if m["cobertura_pct"] is None else "{:.1%}".format(m["cobertura_pct"]),
                     m["n_productos"], (m["motivo"] or "")[:30], marca))
        stock = sum((m["stock_unid"] or 0) * (m["costo_std"] or 0) for m in maestro.values())
        print("      inventario a costo  : {:>18,.2f}  ({} SKU con stock)".format(
            stock, sum(1 for m in maestro.values() if (m["stock_unid"] or 0) > 0)))
    print("\n  Llamadas XML-RPC: %d" % od.calls)


# =====================================================================
#  AUTOPRUEBA — offline, sin red, con un Odoo falso
# =====================================================================
class _FakeOdoo(object):
    """Odoo de mentira con datos escogidos para que cada trampa conocida salte.

    Ecuador tiene valoracion de inventario (costo real). Colombia solo tiene el
    mayor y cubre parcial. Costa Rica no tiene costo de ninguna forma: ahi el
    margen NO se debe publicar.
    """
    def __init__(self):
        self.calls = 0
        self.cfg = {"url": "http://fake", "db": "fake", "_raw": {"company_map": {
            "VICOMER": "Ecuador", "VINTRAL": "Colombia", "3-102": "Costa Rica", "VIX": "ignore"}}}
        self.uid = 1
        self.companies = [
            {"id": 2, "name": "VICOMER S.A.S.", "currency_id": [1, "USD"]},
            {"id": 1, "name": "VINTRAL S.A.S.", "currency_id": [3, "COP"]},
            {"id": 3, "name": "3-102-940094 SRL", "currency_id": [5, "CRC"]},
            {"id": 11, "name": "VIX S.A.S.", "currency_id": [1, "USD"]},
        ]
        self.moves = [
            # Ecuador: agosto (post-migracion). Una NC para probar el signo.
            {"id": 100, "name": "EC/001", "invoice_date": "2026-08-05", "company_id": [2, "VICOMER S.A.S."],
             "move_type": "out_invoice", "amount_untaxed_signed": 30000.0, "partner_id": [7, "Cliente A"],
             "currency_id": [1, "USD"]},
            {"id": 101, "name": "EC/002", "invoice_date": "2026-08-20", "company_id": [2, "VICOMER S.A.S."],
             "move_type": "out_invoice", "amount_untaxed_signed": 12000.0, "partner_id": [8, "Cliente B"],
             "currency_id": [1, "USD"]},
            {"id": 102, "name": "EC/NC1", "invoice_date": "2026-08-28", "company_id": [2, "VICOMER S.A.S."],
             "move_type": "out_refund", "amount_untaxed_signed": -2000.0, "partner_id": [7, "Cliente A"],
             "currency_id": [1, "USD"]},
            # Una compra: NO debe entrar nunca.
            {"id": 199, "name": "BILL/1", "invoice_date": "2026-08-10", "company_id": [2, "VICOMER S.A.S."],
             "move_type": "in_invoice", "amount_untaxed_signed": -9999.0, "partner_id": [9, "Prov"],
             "currency_id": [1, "USD"]},
            # Colombia
            {"id": 200, "name": "CO/001", "invoice_date": "2026-05-10", "company_id": [1, "VINTRAL S.A.S."],
             "move_type": "out_invoice", "amount_untaxed_signed": 100000000.0, "partner_id": [10, "Cli CO"],
             "currency_id": [3, "COP"]},
            # Costa Rica
            {"id": 300, "name": "CR/001", "invoice_date": "2026-03-01", "company_id": [3, "3-102-940094 SRL"],
             "move_type": "out_invoice", "amount_untaxed_signed": 5000.0, "partner_id": [11, "Cli CR"],
             "currency_id": [5, "CRC"]},
            # VIX: excluida, no debe aparecer
            {"id": 400, "name": "VIX/1", "invoice_date": "2026-08-01", "company_id": [11, "VIX S.A.S."],
             "move_type": "out_invoice", "amount_untaxed_signed": 50000.0, "partner_id": [12, "X"],
             "currency_id": [1, "USD"]},
        ]
        self.lines = [
            # EC/001: horno (margen sano) + cocina (margen NEGATIVO) + flete (servicio)
            {"id": 1, "move_id": [100, "EC/001"], "product_id": [82, "[TEW30ES] HORNO"],
             "quantity": 10, "price_subtotal": 20000.0, "display_type": "product"},
            {"id": 2, "move_id": [100, "EC/001"], "product_id": [73, "[TRG3601] COCINA"],
             "quantity": 5, "price_subtotal": 9500.0, "display_type": "product"},
            {"id": 3, "move_id": [100, "EC/001"], "product_id": [90, "[FLE] FLETE NACIONAL"],
             "quantity": 1, "price_subtotal": 500.0, "display_type": "product"},
            # linea de impuesto: NO es venta
            {"id": 4, "move_id": [100, "EC/001"], "product_id": [82, "[TEW30ES] HORNO"],
             "quantity": 0, "price_subtotal": 3600.0, "display_type": "tax"},
            {"id": 5, "move_id": [101, "EC/002"], "product_id": [82, "[TEW30ES] HORNO"],
             "quantity": 6, "price_subtotal": 12000.0, "display_type": "product"},
            # nota de credito: debe restar
            {"id": 6, "move_id": [102, "EC/NC1"], "product_id": [82, "[TEW30ES] HORNO"],
             "quantity": 1, "price_subtotal": 2000.0, "display_type": "product"},
            # compra: no debe entrar
            {"id": 7, "move_id": [199, "BILL/1"], "product_id": [82, "[TEW30ES] HORNO"],
             "quantity": 50, "price_subtotal": 9999.0, "display_type": "product"},
            # Colombia: dos SKU, uno con margen imposible
            {"id": 10, "move_id": [200, "CO/001"], "product_id": [82, "[TEW30ES] HORNO"],
             "quantity": 100, "price_subtotal": 60000000.0, "display_type": "product"},
            {"id": 11, "move_id": [200, "CO/001"], "product_id": [95, "[XX] LINEA BLANCA"],
             "quantity": 40, "price_subtotal": 40000000.0, "display_type": "product"},
            # Costa Rica: un SKU, sin costo posible
            {"id": 20, "move_id": [300, "CR/001"], "product_id": [82, "[TEW30ES] HORNO"],
             "quantity": 4, "price_subtotal": 4000.0, "display_type": "product"},
        ]
        self.products = {
            82: {"id": 82, "default_code": "TEW30ES", "name": "HORNO ELECTRICO 30", "categ_id": [1, "Hornos"],
                 "standard_price": 1200.0, "qty_available": 5.0, "type": "product", "active": True},
            73: {"id": 73, "default_code": "TRG3601", "name": "COCINA A GAS 36", "categ_id": [2, "Cocinas"],
                 "standard_price": 2200.0, "qty_available": 100.0, "type": "product", "active": True},
            90: {"id": 90, "default_code": "FLE", "name": "FLETE NACIONAL", "categ_id": [3, "Servicios"],
                 "standard_price": 0.0, "qty_available": 0.0, "type": "service", "active": True},
            95: {"id": 95, "default_code": "XX", "name": "LINEA BLANCA", "categ_id": [1, "Hornos"],
                 "standard_price": 300000.0, "qty_available": 10.0, "type": "product", "active": True},
        }
        # Ecuador: capa de valoracion (costo real). Horno 800/u, cocina 2500/u (pierde plata).
        self.layers = {2: {82: {"value": -12000.0, "quantity": -15.0},
                           73: {"value": -12500.0, "quantity": -5.0}}}
        self.accounts = {
            2: [{"id": 501, "code": "5.1", "name": "COSTO DE LA MERCANCIA VENDIDA", "account_type": "expense"}],
            1: [{"id": 601, "code": "6135", "name": "COSTO DE LA MERCANCIA VENDIDA", "account_type": "expense"}],
            3: [],
        }
        # Colombia: el mayor solo cubre el horno (60% de la venta) -> parcial.
        self.mayor = {1: {82: -36000000.0}}

    def authenticate(self):
        return 1

    def sr(self, model, domain, fields, limit=0, ctx=None):
        self.calls += 1
        cids = (ctx or {}).get("allowed_company_ids") or []
        if model == "res.company":
            return [dict(c) for c in self.companies]
        if model == "account.move":
            tipos = next((d[2] for d in domain if d[0] == "move_type"), None)
            ids = next((d[2] for d in domain if d[0] == "id"), None)
            out = []
            for m in self.moves:
                if tipos and m["move_type"] not in tipos:
                    continue
                if ids is not None and m["id"] not in ids:
                    continue
                if cids and m["company_id"][0] not in cids:
                    continue
                out.append(dict(m))
            return out
        if model == "account.move.line":
            mids = next((d[2] for d in domain if d[0] == "move_id"), None)
            lids = next((d[2] for d in domain if d[0] == "id"), None)
            out = []
            for l in self.lines:
                if mids is not None and l["move_id"][0] not in mids:
                    continue
                if lids is not None and l["id"] not in lids:
                    continue
                r = dict(l)
                r["sale_line_ids"] = []      # el fake NO enlaza pedidos: sale_line queda en 0%
                out.append(r)
            return out
        if model == "product.product":
            ids = next((d[2] for d in domain if d[0] == "id"), [])
            out = []
            for i in ids:
                if i not in self.products:
                    continue
                r = dict(self.products[i])
                # Costa Rica no valora inventario: standard_price en cero. Es el caso real.
                if cids and cids[0] == 3:
                    r["standard_price"] = 0.0; r["qty_available"] = 0.0
                out.append(r)
            return out
        if model == "account.account":
            return [dict(a) for a in self.accounts.get(cids[0] if cids else 0, [])]
        if model == "sale.order.line":
            return []
        return []

    def sr_drop(self, model, domain, fields, ctx=None):
        return self.sr(model, domain, fields, ctx=ctx), []

    def kw(self, model, method, args, kwargs=None):
        self.calls += 1
        dom = args[0]
        cid = next((d[2] for d in dom if d[0] == "company_id"), None)
        if model == "stock.valuation.layer":
            capas = self.layers.get(cid) or {}
            if not capas:
                raise Exception("stock.valuation.layer no instalado")
            return [{"product_id": [p, ""], "value:sum": v["value"], "value": v["value"],
                     "quantity": v["quantity"], "__count": 1} for p, v in capas.items()]
        if model == "account.move.line" and method == "read_group":
            may = self.mayor.get(cid) or {}
            return [{"product_id": [p, ""], "balance": v, "__count": 1} for p, v in may.items()]
        return []


def _autotest():
    global JSON_VENTAS, OUT_DIR, JSON_OUT
    import tempfile
    fallos, n = [], [0]

    def chk(nombre, cond, detalle=""):
        n[0] += 1
        if not cond:
            fallos.append("%s  %s" % (nombre, detalle))
        print("   %s %-62s %s" % ("OK " if cond else "!! ", nombre, detalle if not cond else ""))

    tmp = Path(tempfile.mkdtemp(prefix="prodtest_"))
    OUT_DIR = tmp
    JSON_OUT = tmp / "dashboard_productos.json"
    # dashboard_ventas.json de referencia: Ecuador ago = 40.000 exactos (30.000+12.000-2.000)
    JSON_VENTAS = tmp / "dashboard_ventas.json"
    JSON_VENTAS.write_text(json.dumps({"paises": {
        "Ecuador": {"mensual": {"8": 40000.0}},
        "Colombia": {"mensual": {"5": 100000000.0}},
        "Costa Rica": {"mensual": {"3": 4500.0}}}}), encoding="utf-8")

    print("=" * 96)
    print("  AUTOPRUEBA productos_dashboard.py  (offline, Odoo falso)")
    print("=" * 96)
    od = _FakeOdoo()
    av = Avisos()
    reglas = load_reglas()
    doc = construir(od, 2026, av, hoy=datetime.date(2026, 9, 10), reglas=reglas)
    ec = doc["paises"].get("Ecuador") or {}
    co = doc["paises"].get("Colombia") or {}
    cr = doc["paises"].get("Costa Rica") or {}

    chk("1  VIX queda excluida del dashboard", "VIX S.A.S." in doc["excluidas"] and "VIX" not in doc["paises"])
    chk("2  los tres paises se construyen", set(doc["paises"]) == {"Ecuador", "Colombia", "Costa Rica"},
        str(sorted(doc["paises"])))
    prod_ec = {p["id"]: p for p in ec.get("productos") or []}
    chk("3  la factura de COMPRA no entra a la venta", abs((prod_ec.get(82) or {}).get("venta", 0) - 30000.0) < 0.01,
        "horno EC = %s (esperado 30.000)" % (prod_ec.get(82) or {}).get("venta"))
    chk("4  la nota de credito RESTA venta y unidades",
        abs((prod_ec.get(82) or {}).get("unidades", 0) - 15.0) < 0.01,
        "unidades = %s (10+6-1=15)" % (prod_ec.get(82) or {}).get("unidades"))
    chk("5  la linea de impuesto NO se cuenta como venta",
        (prod_ec.get(82) or {}).get("venta") == 30000.0)
    chk("6  el FLETE sale del ranking y va a servicios",
        90 not in prod_ec and (ec.get("servicios_y_ajustes") or {}).get("n") == 1)
    chk("7  la ventana de Ecuador es solo agosto",
        ec["ventana"]["mes_desde"] == 8 and ec["ventana"]["mes_hasta"] == 8, ec["ventana"]["etiqueta"])
    chk("8  cobertura de producto de Ecuador = 100%",
        abs((ec["cuadre"]["cobertura_producto_pct"] or 0) - 1.0) < 0.001,
        str(ec["cuadre"]["cobertura_producto_pct"]))
    chk("9  Ecuador elige el costo real de inventario",
        ec["costo"]["fuente_elegida"] == "valuation_layer", str(ec["costo"]["fuente_elegida"]))
    chk("10 Ecuador declara margen confiable", ec["costo"]["margen_confiable"] is True,
        "cobertura %s" % ec["costo"]["cobertura_pct"])
    coc = prod_ec.get(73) or {}
    chk("11 detecta el SKU que se vende con margen NEGATIVO",
        coc.get("margen") is not None and coc["margen"] < 0 and ec["alertas_producto"]["margen_negativo"]["n"] == 1,
        "cocina margen = %s" % coc.get("margen"))
    chk("12 la perdida del margen negativo se cuantifica",
        abs((ec["alertas_producto"]["margen_negativo"]["perdida"] or 0) - (9500.0 - 12500.0)) < 0.01,
        str(ec["alertas_producto"]["margen_negativo"]["perdida"]))
    chk("13 hay aviso critico por margen negativo",
        any(a["nivel"] == "critico" and a["bloque"] == "margen" and a["pais"] == "Ecuador" for a in doc["avisos"]))
    mixv = sum(p["mix_venta_pct"] or 0 for p in ec["productos"])
    chk("14 el mix de VENTA suma 100%", abs(mixv - 1.0) < 0.01, "suma %.4f" % mixv)
    mixm = sum(p["mix_margen_pct"] or 0 for p in ec["productos"] if p["mix_margen_pct"] is not None)
    chk("15 el mix de MARGEN suma 100%", abs(mixm - 1.0) < 0.01, "suma %.4f" % mixm)
    chk("16 mix de venta y mix de margen NO son iguales",
        abs((prod_ec[82]["mix_venta_pct"] or 0) - (prod_ec[82]["mix_margen_pct"] or 0)) > 0.05,
        "venta %.3f margen %.3f" % (prod_ec[82]["mix_venta_pct"] or 0, prod_ec[82]["mix_margen_pct"] or 0))
    chk("17 el precio promedio sale de unidades reales, no de facturas",
        abs((prod_ec[82]["precio_prom"] or 0) - 2000.0) < 0.01, str(prod_ec[82]["precio_prom"]))
    pv = sorted([p["venta"] for p in ec["productos"]], reverse=True)
    k, tv = ec["pareto"]["n_skus_hasta_corte"], sum(pv)
    chk("18 Pareto: k SKU llegan al 80% y k-1 no",
        sum(pv[:k]) / tv >= 0.80 and (k == 1 or sum(pv[:k - 1]) / tv < 0.80),
        "k=%d de %d, acum %.1f%%" % (k, ec["pareto"]["n_skus_total"], 100 * sum(pv[:k]) / tv))
    chk("19 HHI de venta calculado y en rango 0..10000",
        ec["pareto"]["hhi_venta"] is not None and 0 < ec["pareto"]["hhi_venta"] <= 10000,
        str(ec["pareto"]["hhi_venta"]))
    chk("20 DIO y GMROI existen donde hay stock y costo",
        (prod_ec[73]["dio"] is not None and prod_ec[73]["gmroi"] is not None),
        "dio %s gmroi %s" % (prod_ec[73]["dio"], prod_ec[73]["gmroi"]))
    chk("21 el stock lento se detecta y se cuantifica en dinero",
        ec["alertas_producto"]["stock_lento"]["n"] >= 1 and ec["alertas_producto"]["stock_lento"]["capital"],
        str(ec["alertas_producto"]["stock_lento"]))
    chk("22 Colombia cae al mayor: cobertura parcial, no confiable",
        co["costo"]["fuente_elegida"] == "mayor" and co["costo"]["margen_confiable"] is False
        and co["costo"]["margen_publicable"] is True,
        "%s cob=%s" % (co["costo"]["fuente_elegida"], co["costo"]["cobertura_pct"]))
    chk("23 standard_price NO gana por cobertura habiendo una fuente real",
        co["costo"]["fuente_elegida"] != "standard_price",
        "candidatas: %s" % {m["fuente"]: m["cobertura_pct"] for m in co["costo"]["candidatas"]})
    prod_co = {p["id"]: p for p in co.get("productos") or []}
    chk("24 el SKU sin costo aparece SIN margen, no con margen cero",
        prod_co[95]["margen"] is None and prod_co[95]["venta"] == 40000000.0,
        str(prod_co[95]["margen"]))
    chk("25 el margen % se calcula solo sobre la venta que tiene costo",
        abs((co["totales"]["margen_pct"] or 0) - (60000000.0 - 36000000.0) / 60000000.0) < 0.001,
        str(co["totales"]["margen_pct"]))
    chk("26 Costa Rica: sin costo en ninguna fuente, NO se publica margen",
        cr["costo"]["margen_publicable"] is False and cr["totales"]["margen"] is None
        and cr["totales"].get("motivo_sin_margen"),
        "fuente=%s cob=%s" % (cr["costo"]["fuente_elegida"], cr["costo"]["cobertura_pct"]))
    chk("27 Costa Rica conserva el mix de VENTA aunque no tenga margen",
        (cr.get("n_productos") or 0) >= 1 and (cr["totales"]["venta"] or 0) > 0)
    cs = doc["comparativo_skus"]
    horno = next((e for e in cs["skus"] if e["sku"] == "TEW30ES"), None)
    chk("28 el mismo SKU se compara entre los tres paises",
        horno is not None and horno["n_paises"] == 3, str(horno and horno["n_paises"]))
    chk("29 los precios del comparativo van a USD con TC referencial",
        horno is not None and horno["paises"]["Colombia"]["precio_prom_usd"] is not None
        and abs(horno["paises"]["Colombia"]["precio_prom_usd"] - 600000.0 * doc["tc"]["tasas"]["COP"]) < 0.5,
        str(horno and horno["paises"]["Colombia"]["precio_prom_usd"]))
    chk("30 detecta dispersion de precio entre paises",
        horno is not None and horno["alerta_precio"] is True,
        "dispersion %s" % (horno and horno["dispersion_precio_pct"]))
    chk("31 el consolidado excluye del MARGEN al pais sin costo, no de la venta",
        "Costa Rica" in (doc["consolidado"]["paises_sin_margen"] or [])
        and (doc["consolidado"]["venta_usd"] or 0) > 0,
        str(doc["consolidado"]["paises_sin_margen"]))
    chk("32 el consolidado marca el USD como referencial",
        doc["consolidado"]["tc_referencial"] is True and doc["tc"]["referencial"] is True)
    conc = {c["pais"]: c for c in doc["conciliacion"] if c.get("pais")}
    chk("33 concilia contra dashboard_ventas.json en la MISMA ventana",
        conc.get("Ecuador", {}).get("ok") is True and abs(conc["Ecuador"]["diferencia"]) < 0.01,
        str(conc.get("Ecuador")))
    chk("34 una diferencia contra ventas se marca y avisa",
        conc.get("Costa Rica", {}).get("ok") is False
        and any(a["bloque"] == "conciliacion" and a["pais"] == "Costa Rica" for a in doc["avisos"]),
        str(conc.get("Costa Rica")))
    chk("35 cada bloque declara su fuente",
        all(k in doc["fuentes"] for k in ("venta_por_producto", "costo", "inventario"))
        and ec["cuadre"].get("fuente"))
    chk("36 las cuatro fuentes de costo quedan medidas, no solo la elegida",
        len(ec["costo"]["candidatas"]) == 4 and all("cobertura_pct" in m for m in ec["costo"]["candidatas"]))
    chk("37 el JSON es serializable y se reabre igual",
        json.loads(json.dumps(doc, ensure_ascii=False))["anio"] == 2026)
    escribir(doc)
    chk("38 el JSON se escribe en disco", JSON_OUT.exists() and JSON_OUT.stat().st_size > 2000,
        str(JSON_OUT.stat().st_size if JSON_OUT.exists() else "no existe"))

    print("\n" + "-" * 96)
    if fallos:
        print("  AUTOPRUEBA FALLÓ — %d de %d" % (len(fallos), n[0]))
        for f in fallos:
            print("    · %s" % f)
        sys.exit(1)
    print("  AUTOPRUEBA OK — %d comprobaciones" % n[0])
    print("-" * 96)
    imprimir(doc)


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else str(datetime.date.today().year)
    if arg in ("autotest", "test"):
        _autotest(); return
    if arg == "diag":
        diagnostico(sys.argv[2] if len(sys.argv) > 2 else None); return
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
        traceback.print_exc()
        sys.exit(2)
