#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compras_diag.py  ·  Grupo VICOMER
=================================
PASO 0 del dashboard de compras: MEDIR antes de construir.

No escribe ningun dashboard. Contesta, contra Odoo real, las preguntas que
deciden si el dashboard se puede construir o no:

  1. Cobertura de country_id en proveedores  -> ¿se puede separar local de exterior?
  2. Volumen de facturas de proveedor por compania, moneda y mes
  3. Que cuentas contables concentran el gasto -> insumo para compras_reglas.json
  4. Cuanto se va por "exterior" con la regla de country_id
  5. Existen account.payment y payment_term -> ¿se puede calcular DPO y brecha de plazo?
  6. Las cuentas contaminadas de Colombia (AJUSTE INICIAL, PROMOCION Y PUBLICIDAD)

Salida:  OdooVentas/compras_diagnostico.json   +   reporte legible en pantalla.

Uso:  python3 compras_diag.py
Solo biblioteca estandar.
"""
import os, sys, json, ssl, datetime, traceback, xmlrpc.client
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
OUT = PROJ / "OdooVentas"
DEST = OUT / "compras_diagnostico.json"
UMBRAL_COBERTURA = 0.95

PAIS_ESPERADO = {"Ecuador": "EC", "Colombia": "CO", "Costa Rica": "CR"}
CONTAMINADAS_CO = ("AJUSTE INICIAL", "PROMOCION Y PUBLICIDAD", "PROMOCIÓN Y PUBLICIDAD")


def log(m):
    print(m, flush=True)


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
                self.cfg["db"] = db
                self.uid = uid
                return uid
        sys.exit("ERROR: no autentico contra Odoo.")

    def kw(self, model, method, args, kwargs=None):
        self.calls += 1
        return self.models.execute_kw(self.cfg["db"], self.uid, self.cfg["apikey"],
                                      model, method, args, kwargs or {})

    def sr(self, model, dom, fields, limit=0, ctx=None):
        kw = {"fields": fields}
        if limit:
            kw["limit"] = limit
        if ctx:
            kw["context"] = ctx
        return self.kw(model, "search_read", [dom], kw)

    def sr_drop(self, model, dom, fields, ctx=None):
        f = list(fields)
        om = []
        while f:
            try:
                return self.sr(model, dom, f, ctx=ctx), om
            except Exception as e:
                msg = str(e)
                drop = next((c for c in f if c in msg and c != "id"), None) or (f[-1] if len(f) > 1 else None)
                if drop is None:
                    raise
                f.remove(drop); om.append(drop)
        raise RuntimeError("no se pudo consultar " + model)


def m2o(v):
    if isinstance(v, (list, tuple)) and len(v) == 2:
        return v[0], v[1]
    return None, None


def frag_pais(nombre, company_map):
    n = (nombre or "").upper()
    best, bl = None, -1
    for frag, pais in (company_map or {}).items():
        f = frag.upper()
        if f and f in n and len(f) > bl:
            best, bl = pais, len(f)
    return best


def main():
    year = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else datetime.date.today().year
    cfg = load_config()
    od = Odoo(cfg); od.authenticate()
    cmap = (cfg.get("_raw") or {}).get("company_map") or {}
    R = {"generado": datetime.datetime.now().isoformat(timespec="seconds"), "anio": year,
         "odoo": {"url": cfg["url"], "db": cfg["db"]}}

    log("=" * 86)
    log("  DIAGNOSTICO DE COMPRAS — Grupo VICOMER   (%s)" % R["generado"])
    log("=" * 86)

    # ---------------- companias ----------------
    comps = {}
    for r in od.sr("res.company", [], ["id", "name", "currency_id", "partner_id"]):
        _, cur = m2o(r.get("currency_id"))
        p = frag_pais(r.get("name"), cmap)
        comps[r["id"]] = {"id": r["id"], "name": r["name"], "moneda": cur,
                          "pais": None if p in (None, "ignore") else p, "excluida": p == "ignore",
                          "partner_id": (r.get("partner_id") or [None])[0]}
    ctx_all = {"allowed_company_ids": list(comps.keys())}
    log("\n1) COMPANIAS")
    for c in comps.values():
        log("   [%-3s] %-52s %-4s -> %s" % (c["id"], c["name"][:52], c["moneda"] or "?",
                                            "EXCLUIDA" if c["excluida"] else (c["pais"] or "SIN MAPEAR")))
    R["companias"] = list(comps.values())
    activas = [c for c in comps.values() if c["pais"] and not c["excluida"]]

    # ---------------- paises de Odoo ----------------
    paises_odoo = {}
    for r in od.sr("res.country", [["code", "in", ["EC", "CO", "CR"]]], ["id", "code", "name"]):
        paises_odoo[r["code"]] = r["id"]
    R["paises_odoo"] = paises_odoo
    log("\n2) PAISES en Odoo: %s" % paises_odoo)

    # ---------------- facturas de proveedor ----------------
    log("\n3) FACTURAS DE PROVEEDOR %d (in_invoice + in_refund, posted)" % year)
    dom = [["move_type", "in", ["in_invoice", "in_refund"]], ["state", "=", "posted"],
           ["invoice_date", ">=", "%d-01-01" % year], ["invoice_date", "<=", "%d-12-31" % year]]
    campos = ["name", "invoice_date", "invoice_date_due", "partner_id", "amount_untaxed_signed",
              "amount_total_signed", "amount_residual", "amount_residual_signed", "currency_id",
              "company_id", "move_type", "invoice_payment_term_id", "payment_state"]
    try:
        facturas, omitidos = od.sr_drop("account.move", dom, campos, ctx=ctx_all)
    except Exception as e:
        log("   [ERROR] account.move no responde: %s" % str(e)[:200])
        facturas, omitidos = [], campos
    R["campos_omitidos_account_move"] = omitidos
    if omitidos:
        log("   [!] Odoo rechazo estos campos y se omitieron: %s" % ", ".join(omitidos))

    porcomp = defaultdict(lambda: {"n": 0, "neto": 0.0, "residual": 0.0, "monedas": defaultdict(int),
                                   "meses": defaultdict(float), "nc": 0, "con_plazo": 0, "con_vence": 0,
                                   "por_moneda_residual": defaultdict(float),
                                   "residual_signed": 0.0})
    partners = set()
    moves_por_comp = defaultdict(list)
    for f in facturas:
        cid, _ = m2o(f.get("company_id"))
        a = porcomp[cid]
        a["n"] += 1
        a["neto"] += float(f.get("amount_untaxed_signed") or 0)
        a["residual"] += float(f.get("amount_residual") or 0)
        _, cur = m2o(f.get("currency_id"))
        a["monedas"][cur or "?"] += 1
        d = str(f.get("invoice_date") or "")[:7]
        if d:
            a["meses"][d] += float(f.get("amount_untaxed_signed") or 0)
        if f.get("move_type") == "in_refund":
            a["nc"] += 1
        if f.get("invoice_payment_term_id"):
            a["con_plazo"] += 1
        if f.get("invoice_date_due"):
            a["con_vence"] += 1
        a["por_moneda_residual"][cur or "?"] += float(f.get("amount_residual") or 0)
        a["residual_signed"] += float(f.get("amount_residual_signed") or 0)
        moves_por_comp[cid].append(f["id"])
        pid, _ = m2o(f.get("partner_id"))
        if pid:
            partners.add(pid)

    log("   %-30s %6s %6s %16s %16s  %-22s %s" % ("COMPANIA", "docs", "NC", "neto sin IVA", "saldo residual", "monedas", "con plazo/vence"))
    comp_out = {}
    for cid, a in porcomp.items():
        c = comps.get(cid, {"name": "?", "pais": None, "excluida": False})
        mon = ", ".join("%s:%d" % (k, v) for k, v in sorted(a["monedas"].items(), key=lambda x: -x[1]))
        log("   %-30s %6d %6d %16.2f %16.2f  %-22s %d/%d" %
            (c["name"][:30], a["n"], a["nc"], a["neto"], a["residual"], mon, a["con_plazo"], a["con_vence"]))
        comp_out[str(cid)] = {"compania": c["name"], "pais": c["pais"], "excluida": c.get("excluida"),
                              "n": a["n"], "nc": a["nc"], "neto": round(a["neto"], 2),
                              "residual_moneda_documento": round(a["residual"], 2),
                              "residual_moneda_compania": round(a["residual_signed"], 2),
                              "residual_por_moneda": dict((k, round(v, 2)) for k, v in a["por_moneda_residual"].items()),
                              "monedas": dict(a["monedas"]),
                              "por_mes": dict((k, round(v, 2)) for k, v in a["meses"].items()),
                              "con_payment_term": a["con_plazo"], "con_fecha_vence": a["con_vence"]}
    log("\n   SALDO PENDIENTE: moneda del documento vs moneda de la compania")
    log("   (si estas dos columnas difieren mucho, sumar amount_residual entre monedas esta mal)")
    for cid, a in porcomp.items():
        c = comps.get(cid, {"name": "?"})
        det = ", ".join("%s %.2f" % (k, v) for k, v in sorted(a["por_moneda_residual"].items(), key=lambda x: -abs(x[1])))
        log("   %-30s doc: %-42s   compania (%s): %16.2f"
            % (c["name"][:30], det[:42], c.get("moneda") or "?", a["residual_signed"]))
    R["facturas_por_compania"] = comp_out
    R["n_facturas"] = len(facturas)
    R["n_proveedores_con_factura"] = len(partners)

    # ---------------- cobertura de country_id ----------------
    log("\n4) COBERTURA DE country_id EN PROVEEDORES  (la regla local/exterior depende de esto)")
    pdata = {}
    ids = sorted(partners)
    for i in range(0, len(ids), 300):
        for p in od.sr("res.partner", [["id", "in", ids[i:i + 300]]],
                       ["id", "name", "vat", "country_id", "supplier_rank", "parent_id"], ctx=ctx_all):
            cid, cname = m2o(p.get("country_id"))
            pdata[p["id"]] = {"name": p.get("name"), "vat": (p.get("vat") or "").strip(),
                              "country_id": cid, "country": cname}
    con_pais = [p for p in pdata.values() if p["country_id"]]
    cob = (len(con_pais) / len(pdata)) if pdata else 0.0
    log("   Proveedores con factura en %d: %d" % (year, len(pdata)))
    log("   Con country_id cargado      : %d  (%.1f%%)" % (len(con_pais), cob * 100))
    log("   SIN country_id              : %d  (%.1f%%)" % (len(pdata) - len(con_pais), (1 - cob) * 100))
    R["cobertura_pais_proveedores"] = {"n_proveedores": len(pdata), "con_pais": len(con_pais),
                                       "cobertura": round(cob, 4), "umbral": UMBRAL_COBERTURA,
                                       "suficiente": cob >= UMBRAL_COBERTURA}
    dist = defaultdict(int)
    for p in pdata.values():
        dist[p["country"] or "(SIN PAIS)"] += 1
    R["distribucion_pais_proveedores"] = dict(dist)
    log("   Distribucion por pais del proveedor:")
    for k, v in sorted(dist.items(), key=lambda x: -x[1]):
        log("      %-34s %4d" % (k, v))

    # ---------------- local vs exterior con la regla ----------------
    log("\n5) LOCAL vs EXTERIOR con la regla country_id(proveedor) == pais(compania)")
    res = {}
    sin_pais_montos = defaultdict(float)
    for f in facturas:
        cid, _ = m2o(f.get("company_id"))
        c = comps.get(cid) or {}
        if c.get("excluida") or not c.get("pais"):
            continue
        pais = c["pais"]
        _, cur = m2o(f.get("currency_id"))
        b = res.setdefault(pais, {"moneda": cur, "local": 0.0, "n_local": 0, "exterior": 0.0,
                                  "n_ext": 0, "sin_clasificar": 0.0, "n_sin": 0, "ext_top": defaultdict(float)})
        pid, pname = m2o(f.get("partner_id"))
        pp = pdata.get(pid) or {}
        neto = float(f.get("amount_untaxed_signed") or 0)
        esperado = paises_odoo.get(PAIS_ESPERADO.get(pais))
        if not pp.get("country_id"):
            b["sin_clasificar"] += neto; b["n_sin"] += 1
            sin_pais_montos[pname or "?"] += neto
        elif pp["country_id"] == esperado:
            b["local"] += neto; b["n_local"] += 1
        else:
            b["exterior"] += neto; b["n_ext"] += 1
            b["ext_top"][(pname or "?") + "  [" + (pp.get("country") or "?") + "]"] += neto
    for pais, b in res.items():
        tot = b["local"] + b["exterior"] + b["sin_clasificar"]
        log("   %-11s (%s)  LOCAL %16.2f (%d docs)  EXTERIOR %16.2f (%d)  SIN CLASIF %14.2f (%d)   total %.2f"
            % (pais, b["moneda"], b["local"], b["n_local"], b["exterior"], b["n_ext"],
               b["sin_clasificar"], b["n_sin"], tot))
        top = sorted(b["ext_top"].items(), key=lambda x: -x[1])[:6]
        for nm, v in top:
            log("        exterior: %-58s %16.2f" % (nm[:58], v))
        b["ext_top"] = dict((k, round(v, 2)) for k, v in top)
        for k in ("local", "exterior", "sin_clasificar"):
            b[k] = round(b[k], 2)
    R["local_vs_exterior"] = res
    R["proveedores_sin_pais_top"] = dict((k, round(v, 2)) for k, v in
                                         sorted(sin_pais_montos.items(), key=lambda x: -x[1])[:25])
    if sin_pais_montos:
        log("   Proveedores SIN PAIS con mas monto:")
        for k, v in sorted(sin_pais_montos.items(), key=lambda x: -x[1])[:10]:
            log("      %-58s %16.2f" % (k[:58], v))

    # ---------------- cuentas de las lineas de factura ----------------
    log("\n6) CUENTAS CONTABLES QUE CONCENTRAN EL GASTO (insumo de compras_reglas.json)")
    cuentas_out = {}
    for c in activas:
        cid = c["id"]
        ctx1 = {"allowed_company_ids": [cid]}
        # OJO: filtrar por ["move_id.move_type", ...] atraviesa a account.move, que en esta
        # instancia esta roto (l10n_ec a medias) y devuelve VACIO sin lanzar error — parece
        # que no hay gasto cuando si lo hay. Se pasan los ids de factura explicitamente.
        mids = moves_por_comp.get(cid) or []
        if not mids:
            log("   --- %s: sin facturas de proveedor en %d" % (c["pais"], year))
            continue
        rg = []
        try:
            for i in range(0, len(mids), 200):
                rg += od.kw("account.move.line", "read_group",
                            [[["move_id", "in", mids[i:i + 200]], ["display_type", "not in", ["line_section", "line_note"]]],
                             ["balance:sum"], ["account_id"]],
                            {"lazy": False, "context": ctx1})
        except Exception as e:
            log("   [!] %s: read_group de lineas fallo (%s)" % (c["name"][:30], str(e)[:110]))
            continue
        acum = {}
        for r in rg:
            aid, aname = m2o(r.get("account_id"))
            k = aid or 0
            if k not in acum:
                acum[k] = {"account_id": r.get("account_id"), "balance": 0.0, "__count": 0}
            acum[k]["balance"] += float(r.get("balance") or 0)
            acum[k]["__count"] += (r.get("__count") or 0)
        rg = list(acum.values())
        aids = [m2o(r.get("account_id"))[0] for r in rg if m2o(r.get("account_id"))[0]]
        info = {}
        for i in range(0, len(aids), 200):
            for a in od.sr("account.account", [["id", "in", aids[i:i + 200]]],
                           ["id", "code", "name", "account_type"], ctx=ctx1):
                info[a["id"]] = a
        filas = []
        for r in rg:
            aid, aname = m2o(r.get("account_id"))
            a = info.get(aid, {})
            filas.append({"id": aid, "code": a.get("code"), "name": a.get("name") or aname,
                          "tipo": a.get("account_type"), "balance": round(float(r.get("balance") or 0), 2),
                          "n": r.get("__count") or r.get("account_id_count")})
        filas.sort(key=lambda x: -abs(x["balance"]))
        cuentas_out[c["pais"]] = filas
        log("   --- %s (%s) — %d cuentas con movimiento de compra" % (c["pais"], c["name"][:34], len(filas)))
        for f in filas[:14]:
            marca = ""
            up = (f["name"] or "").upper()
            if any(x in up for x in CONTAMINADAS_CO):
                marca = "   <== CONTAMINADA (filtrar)"
            log("       %-12s %-46s %-22s %16.2f%s" % (f["code"] or "?", (f["name"] or "")[:46],
                                                       f["tipo"] or "?", f["balance"], marca))
    R["cuentas_por_pais"] = cuentas_out

    # ---------------- pagos ejecutados y plazos ----------------
    log("\n7) PAGOS EJECUTADOS Y PLAZOS PACTADOS (¿se puede calcular DPO real?)")
    pay = {"account_payment": None, "payment_terms": None, "partials": None}
    try:
        n = od.kw("account.payment", "search_count",
                  [[["state", "in", ["posted", "paid", "in_process"]], ["partner_type", "=", "supplier"],
                    ["date", ">=", "%d-01-01" % year]]], {"context": ctx_all})
        pay["account_payment"] = n
        log("   account.payment (proveedor, %d): %d" % (year, n))
    except Exception as e:
        pay["account_payment"] = "ERROR: " + str(e)[:120]
        log("   account.payment NO disponible: %s" % str(e)[:120])
    try:
        pts = od.sr("account.payment.term", [], ["id", "name"], ctx=ctx_all)
        pay["payment_terms"] = [p["name"] for p in pts][:30]
        log("   Plazos de pago definidos (%d): %s" % (len(pts), ", ".join(pay["payment_terms"][:8])))
    except Exception as e:
        pay["payment_terms"] = "ERROR: " + str(e)[:120]
    try:
        n = od.kw("account.partial.reconcile", "search_count",
                  [[["max_date", ">=", "%d-01-01" % year]]], {"context": ctx_all})
        pay["partials"] = n
        log("   Conciliaciones parciales %d: %d" % (year, n))
    except Exception as e:
        pay["partials"] = "ERROR: " + str(e)[:120]
    try:
        muestra = od.sr("account.payment",
                        [["partner_type", "=", "supplier"], ["date", ">=", "%d-01-01" % year]],
                        ["id", "date", "amount", "currency_id", "company_id", "state"], ctx=ctx_all)
        pay["n_con_fecha"] = len([x for x in muestra if x.get("date")])
        pay["muestra"] = muestra[:5]
        log("   Pagos a proveedor con fecha: %d de %d  -> el DPO real %s" %
            (pay["n_con_fecha"], len(muestra),
             "SE PUEDE calcular" if pay["n_con_fecha"] >= 10 else "NO tiene base suficiente"))
    except Exception as e:
        log("   No pude leer el detalle de pagos: %s" % str(e)[:120])
    R["pagos"] = pay

    # ---------------- veredicto ----------------
    log("\n" + "=" * 86)
    log("  VEREDICTO")
    log("=" * 86)
    ok = R["cobertura_pais_proveedores"]["suficiente"]
    log("  Cobertura de country_id: %.1f%%  -> %s" %
        (cob * 100, "SUFICIENTE (>=95%)" if ok else "INSUFICIENTE (<95%) — hay que corregir Odoo antes de construir"))
    log("  Llamadas XML-RPC: %d" % od.calls)
    R["veredicto_cobertura_ok"] = ok
    OUT.mkdir(parents=True, exist_ok=True)
    DEST.write_text(json.dumps(R, ensure_ascii=False, indent=2), encoding="utf-8")
    log("  -> %s" % DEST)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(traceback.format_exc())
        sys.exit(1)
