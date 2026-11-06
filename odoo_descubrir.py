#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
odoo_descubrir.py
=================
DESCUBRIMIENTO de la instancia Odoo del Grupo VICOMER tras la migración de Ecuador.

Este script NO cambia nada: sólo lee Odoo y vuelca un retrato completo de la
instancia para poder migrar con datos, no con supuestos. Es el paso 0 de la
migración Perseo -> Odoo.

Responde las preguntas que bloquean la migración:
  1. ¿Qué compañías existen, con qué id, nombre y moneda?
  2. ¿Cuál es la compañía de Ecuador y desde qué fecha tiene movimientos?
  3. ¿Qué plan de cuentas usa Ecuador? (códigos, tipos, ¿PUC de Perseo o catálogo SRI?)
  4. ¿Los partners traen RUC/cédula en `vat`? (clave para mapear canales del presupuesto)
  5. ¿Existe la localización ecuatoriana (l10n_ec) y sus campos de autorización SRI?
  6. ¿Cuántas facturas de cliente y de proveedor hay por compañía?
  7. ¿Los saldos de apertura migrados de Perseo, con qué fecha y diario entraron?

USO (en el Mac, con red hacia Odoo):
    cd ~/Claude/Projects/CFO\\ VICOMER
    python3 odoo_descubrir.py              # descubre todo y guarda el JSON
    python3 odoo_descubrir.py cuentas      # sólo vuelca el plan de cuentas a CSV
    python3 odoo_descubrir.py resumen      # imprime el resumen del último JSON

SALIDA:
    OdooVentas/descubrimiento_odoo.json    # retrato completo (lo lee el resto de scripts)
    OdooVentas/plan_cuentas_odoo.csv       # plan de cuentas para revisar a ojo

Sólo stdlib. Reutiliza odoo_config.json + odoo_apikey.txt.
"""
import os, sys, json, ssl, csv, datetime, xmlrpc.client
try:  # proxy HTTPS para xmlrpc (no-op en el Mac)
    import sys as _s, os as _o
    _d = _o.path.dirname(_o.path.abspath(__file__))
    for _p in (_d, _o.path.dirname(_d)):
        if _o.path.exists(_o.path.join(_p, 'odoo_proxy.py')) and _p not in _s.path: _s.path.append(_p)
    import odoo_proxy
except ImportError:
    pass
from collections import Counter, defaultdict
from pathlib import Path

HOME = Path.home()
PROJ = Path(__file__).resolve().parent
OUT_DIR = Path(os.environ.get("ODOO_OUT_DIR", PROJ / "OdooVentas"))
OUT_JSON = OUT_DIR / "descubrimiento_odoo.json"
OUT_CSV = OUT_DIR / "plan_cuentas_odoo.csv"

# Prefijos PUC que usan los Estados Financieros construidos sobre Perseo.
# Si el plan de cuentas de Odoo no los respeta, hay que remapear los EEFF.
PREFIJOS_PERSEO = ["11", "1101", "1102", "1103", "12", "21", "2104", "22", "2203",
                   "3", "41", "42", "51", "52", "53", "54", "55"]


def log(m):
    print(f"[{datetime.datetime.now():%H:%M:%S}] {m}", flush=True)


# --------------------------------------------------------------- conexión
def load_config():
    cfg = {"url": os.environ.get("ODOO_URL"), "db": os.environ.get("ODOO_DB"),
           "login": os.environ.get("ODOO_LOGIN"), "apikey": os.environ.get("ODOO_APIKEY")}
    extra = {}
    for f in (HOME / ".odoo_config.json", PROJ / "odoo_config.json"):
        if f.exists():
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                extra.update(d)
                for k in ("url", "db", "login", "apikey"):
                    cfg[k] = cfg[k] or d.get(k)
            except Exception as e:
                log(f"AVISO: no pude leer {f}: {e}")
    for kf in (HOME / ".odoo_apikey", PROJ / "odoo_apikey.txt"):
        if not cfg["apikey"] and kf.exists():
            cfg["apikey"] = kf.read_text(encoding="utf-8").strip()
    if cfg.get("url"):
        cfg["url"] = cfg["url"].rstrip("/")
    for k in ("url", "db", "login", "apikey"):
        if not cfg.get(k):
            sys.exit(f"ERROR: falta '{k}' de Odoo. Revisa odoo_config.json / odoo_apikey.txt")
    cfg["company_map"] = extra.get("company_map", {})
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
        self.version = {}

    def authenticate(self):
        try:
            self.version = self.common.version()
        except Exception as e:
            log(f"AVISO: no pude leer versión: {e}")
        self.uid = self.common.authenticate(self.cfg["db"], self.cfg["login"],
                                            self.cfg["apikey"], {})
        if not self.uid:
            sys.exit("ERROR: no autenticó en Odoo. Revisa db/login/apikey.")
        return self.uid

    def kw(self, model, method, args, kwargs=None):
        return self.models.execute_kw(self.cfg["db"], self.uid, self.cfg["apikey"],
                                      model, method, args, kwargs or {})

    def try_kw(self, model, method, args, kwargs=None, default=None):
        """Como kw() pero devuelve `default` en vez de reventar. Para sondeos."""
        try:
            return self.kw(model, method, args, kwargs)
        except Exception as e:
            log(f"  (sondeo {model}.{method} falló: {str(e)[:90]})")
            return default


# --------------------------------------------------------------- bloques
def d_compania(od):
    comps = od.kw("res.company", "search_read", [[]],
                  {"fields": ["id", "name", "currency_id", "country_id", "vat",
                              "partner_id"]})
    out = []
    for c in comps:
        out.append({
            "id": c["id"],
            "nombre": c["name"],
            "moneda": (c.get("currency_id") or [0, "?"])[1],
            "pais": (c.get("country_id") or [0, ""])[1],
            "vat": c.get("vat") or "",
        })
    return out


def d_rango_fechas(od, comp_ids):
    """Primera y última fecha de asiento contabilizado por compañía."""
    out = {}
    for cid in comp_ids:
        ctx = {"allowed_company_ids": comp_ids}
        dom = [["parent_state", "=", "posted"], ["company_id", "=", cid]]
        primero = od.try_kw("account.move.line", "search_read", [dom],
                            {"fields": ["date"], "limit": 1, "order": "date asc",
                             "context": ctx}, default=[])
        ultimo = od.try_kw("account.move.line", "search_read", [dom],
                           {"fields": ["date"], "limit": 1, "order": "date desc",
                            "context": ctx}, default=[])
        n = od.try_kw("account.move.line", "search_count", [dom], {"context": ctx}, default=0)
        out[str(cid)] = {
            "primer_asiento": primero[0]["date"] if primero else None,
            "ultimo_asiento": ultimo[0]["date"] if ultimo else None,
            "lineas_contabilizadas": n,
        }
    return out


def d_plan_cuentas(od, comp_ids):
    """Plan de cuentas completo + diagnóstico de compatibilidad con los prefijos Perseo.

    OJO: desde Odoo 17 el campo `code` de account.account es *company-dependent*.
    Si se lee con varias compañías activas, Odoo devuelve el código vacío para las
    cuentas que no pertenecen a la compañía principal del contexto. Por eso se lee
    UNA compañía a la vez y se fusiona: de lo contrario el 77% de las cuentas
    aparece sin código y el diagnóstico de prefijos da un falso negativo.
    """
    por_id = {}
    for cid in comp_ids:
        ctx = {"allowed_company_ids": [cid]}
        accts = od.try_kw("account.account", "search_read", [[]],
                          {"fields": ["id", "code", "name", "account_type", "company_ids"],
                           "context": ctx, "limit": 5000}, default=None)
        if accts is None:
            # Odoo < 17 usa company_id en vez de company_ids
            accts = od.try_kw("account.account", "search_read", [[]],
                              {"fields": ["id", "code", "name", "account_type", "company_id"],
                               "context": ctx, "limit": 5000}, default=[])
        for a in accts:
            prev = por_id.get(a["id"])
            # Nos quedamos con la lectura que SÍ trajo código.
            if prev and (prev.get("code") or "").strip() and not (a.get("code") or "").strip():
                continue
            a = dict(a)
            a["_visible_en"] = sorted(set((prev or {}).get("_visible_en", []) + [cid]))
            por_id[a["id"]] = a
    accts = list(por_id.values())

    norm = []
    for a in accts:
        comps = a.get("company_ids") or a.get("company_id") or []
        if isinstance(comps, list) and comps and isinstance(comps[0], int) and len(comps) == 2 \
                and isinstance(comps[1], str):
            comps = [comps[0]]          # formato many2one [id, nombre]
        norm.append({
            "id": a["id"],
            "code": (a.get("code") or "").strip(),
            "code_limpio": (a.get("code") or "").replace(".", "").replace("-", "").strip(),
            "name": a.get("name") or "",
            "account_type": a.get("account_type") or "",
            "company_ids": comps if isinstance(comps, list) else [],
            "visible_en": a.get("_visible_en", []),
        })

    sin_codigo = [a for a in norm if not a["code_limpio"]]
    tipos = Counter(a["account_type"] for a in norm)
    con_punto = sum(1 for a in norm if "." in a["code"])
    largos = Counter(len(a["code_limpio"]) for a in norm)
    cobertura = {}
    for p in PREFIJOS_PERSEO:
        cobertura[p] = sum(1 for a in norm if a["code_limpio"].startswith(p))
    primer_digito = Counter(a["code_limpio"][:1] for a in norm if a["code_limpio"])

    return {
        "total_cuentas": len(norm),
        "cuentas_sin_codigo": len(sin_codigo),
        "cuentas": norm,
        "tipos": dict(tipos),
        "codigos_con_punto": con_punto,
        "largo_codigo": dict(largos),
        "primer_digito": dict(primer_digito),
        "cobertura_prefijos_perseo": cobertura,
    }


def d_facturas(od, comp_ids):
    """Conteo de facturas por compañía y tipo, más CxP pendiente."""
    ctx = {"allowed_company_ids": comp_ids}
    out = defaultdict(dict)
    for mt, etiqueta in [("out_invoice", "facturas_cliente"), ("out_refund", "nc_cliente"),
                         ("in_invoice", "facturas_proveedor"), ("in_refund", "nc_proveedor")]:
        rows = od.try_kw("account.move", "read_group",
                         [[["move_type", "=", mt], ["state", "=", "posted"]],
                          ["id:count"], ["company_id"]],
                         {"lazy": False, "context": ctx}, default=[])
        for r in rows:
            cid = str((r.get("company_id") or [0, "?"])[0])
            out[cid][etiqueta] = r.get("__count") or r.get("id_count") or 0
    # CxP con saldo (lo que consume el comité de pagos)
    rows = od.try_kw("account.move", "read_group",
                     [[["move_type", "=", "in_invoice"], ["state", "=", "posted"],
                       ["amount_residual", ">", 0]],
                      ["amount_residual:sum", "id:count"], ["company_id"]],
                     {"lazy": False, "context": ctx}, default=[])
    for r in rows:
        cid = str((r.get("company_id") or [0, "?"])[0])
        out[cid]["cxp_pendientes"] = r.get("__count") or r.get("id_count") or 0
        out[cid]["cxp_saldo"] = round(float(r.get("amount_residual") or 0), 2)
    return dict(out)


def d_partners(od, comp_ids, muestra=25):
    """¿Los partners traen RUC/cédula en `vat`? Sin esto no se puede mapear canal."""
    ctx = {"allowed_company_ids": comp_ids}
    total = od.try_kw("res.partner", "search_count", [[["active", "=", True]]],
                      {"context": ctx}, default=0)
    con_vat = od.try_kw("res.partner", "search_count",
                        [[["active", "=", True], ["vat", "!=", False]]],
                        {"context": ctx}, default=0)
    ejemplos = od.try_kw("res.partner", "search_read",
                         [[["active", "=", True], ["customer_rank", ">", 0]]],
                         {"fields": ["name", "vat", "country_id"], "limit": muestra,
                          "context": ctx}, default=[])
    return {
        "total_partners": total,
        "con_vat": con_vat,
        "pct_con_vat": round(100.0 * con_vat / total, 1) if total else 0.0,
        "muestra_clientes": [{"name": e["name"], "vat": e.get("vat") or "",
                              "pais": (e.get("country_id") or [0, ""])[1]} for e in ejemplos],
    }


def d_localizacion(od):
    """¿Está instalada l10n_ec? ¿Qué campos SRI existen en account.move?"""
    mods = od.try_kw("ir.module.module", "search_read",
                     [[["name", "like", "l10n_"], ["state", "=", "installed"]]],
                     {"fields": ["name", "shortdesc"], "limit": 60}, default=[])
    campos = od.try_kw("account.move", "fields_get", [[], ["string", "type"]], {}, default={})
    sri = sorted(k for k in campos
                 if any(t in k.lower() for t in ("l10n_ec", "sri", "authorization", "autoriz")))
    return {
        "modulos_localizacion": [m["name"] for m in mods],
        "l10n_ec_instalado": any(m["name"].startswith("l10n_ec") for m in mods),
        "campos_sri_en_account_move": sri,
        "tiene_amount_tax": "amount_tax" in campos,
        "tiene_amount_untaxed_signed": "amount_untaxed_signed" in campos,
    }


def d_diarios(od, comp_ids):
    """Diarios por compañía — para detectar el diario de apertura/migración."""
    js = od.try_kw("account.journal", "search_read", [[]],
                   {"fields": ["id", "name", "code", "type", "company_id"],
                    "context": {"allowed_company_ids": comp_ids}, "limit": 200}, default=[])
    out = defaultdict(list)
    for j in js:
        cid = str((j.get("company_id") or [0, "?"])[0])
        out[cid].append({"id": j["id"], "code": j.get("code"), "name": j.get("name"),
                         "type": j.get("type")})
    return dict(out)


def d_monedas(od):
    curs = od.try_kw("res.currency", "search_read",
                     [[["name", "in", ["USD", "COP", "CRC", "EUR"]]]],
                     {"fields": ["name", "rate", "active"], "context": {"active_test": False}},
                     default=[])
    rates = {c["name"]: float(c["rate"]) for c in curs if c.get("rate")}
    tc_usd = {}
    if rates.get("USD"):
        for n, r in rates.items():
            if r > 0:
                tc_usd[n] = round(rates["USD"] / r, 8)
    return {"rates_crudos": rates, "tc_a_usd": tc_usd,
            "activas": [c["name"] for c in curs if c.get("active")]}


# --------------------------------------------------------------- orquestación
def identificar_ecuador(comps, cfg):
    """Adivina qué compañía es Ecuador: por country_id, por moneda USD, o por nombre."""
    candidatos = []
    for c in comps:
        score, razones = 0, []
        if (c.get("pais") or "").lower().startswith("ecuad"):
            score += 100; razones.append("country_id = Ecuador")
        if "VICOMER" in c["nombre"].upper():
            score += 40; razones.append("nombre contiene VICOMER")
        if c.get("moneda") == "USD":
            score += 10; razones.append("moneda USD")
        if "VINTRAL" in c["nombre"].upper():
            score -= 100; razones.append("es VINTRAL (Colombia)")
        if score > 0:
            candidatos.append({**c, "score": score, "razones": razones})
    candidatos.sort(key=lambda x: -x["score"])
    return candidatos


def run():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    od = Odoo(cfg); od.authenticate()
    log(f"Conectado a {cfg['url']} db={cfg['db']} uid={od.uid} v={od.version.get('server_version')}")

    log("1/8 compañías…")
    comps = d_compania(od)
    comp_ids = [c["id"] for c in comps]
    for c in comps:
        log(f"    id={c['id']:<3} {c['nombre'][:45]:45s} {c['moneda']:4s} {c['pais']}")

    log("2/8 rango de fechas por compañía…")
    fechas = d_rango_fechas(od, comp_ids)

    log("3/8 plan de cuentas…")
    plan = d_plan_cuentas(od, comp_ids)
    log(f"    {plan['total_cuentas']} cuentas · con punto: {plan['codigos_con_punto']}")

    log("4/8 facturas y CxP…")
    facturas = d_facturas(od, comp_ids)

    log("5/8 partners / RUC…")
    partners = d_partners(od, comp_ids)
    log(f"    {partners['con_vat']}/{partners['total_partners']} partners con vat "
        f"({partners['pct_con_vat']}%)")

    log("6/8 localización ecuatoriana…")
    loc = d_localizacion(od)
    log(f"    l10n_ec instalado: {loc['l10n_ec_instalado']}")

    log("7/8 diarios…")
    diarios = d_diarios(od, comp_ids)

    log("8/8 monedas…")
    monedas = d_monedas(od)

    ec_cand = identificar_ecuador(comps, cfg)

    doc = {
        "generado": datetime.datetime.now().isoformat(timespec="seconds"),
        "url": cfg["url"], "db": cfg["db"],
        "version_odoo": od.version.get("server_version"),
        "company_map_actual": cfg.get("company_map", {}),
        "companias": comps,
        "candidatos_ecuador": ec_cand,
        "fechas_por_compania": fechas,
        "facturas_por_compania": facturas,
        "diarios_por_compania": diarios,
        "partners": partners,
        "localizacion": loc,
        "monedas": monedas,
        "plan_cuentas": plan,
    }
    OUT_JSON.write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")

    with OUT_CSV.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["code", "code_limpio", "name", "account_type", "company_ids"])
        for a in sorted(plan["cuentas"], key=lambda x: x["code"]):
            w.writerow([a["code"], a["code_limpio"], a["name"], a["account_type"],
                        "|".join(str(i) for i in a["company_ids"])])

    log(f"OK -> {OUT_JSON}")
    log(f"OK -> {OUT_CSV}")
    resumen(doc)


def resumen(doc=None):
    if doc is None:
        if not OUT_JSON.exists():
            sys.exit(f"No existe {OUT_JSON}. Corre primero: python3 odoo_descubrir.py")
        doc = json.loads(OUT_JSON.read_text(encoding="utf-8"))

    print("\n" + "=" * 74)
    print("RESUMEN DE DESCUBRIMIENTO — ODOO GRUPO VICOMER")
    print("=" * 74)
    print(f"Instancia: {doc['url']}  ·  Odoo {doc.get('version_odoo')}")
    print(f"Generado : {doc['generado']}\n")

    print("COMPAÑÍAS")
    fechas = doc.get("fechas_por_compania", {})
    fact = doc.get("facturas_por_compania", {})
    cmap = doc.get("company_map_actual", {})
    for c in doc["companias"]:
        f = fechas.get(str(c["id"]), {})
        v = fact.get(str(c["id"]), {})
        pais = next((p for frag, p in cmap.items() if frag.upper() in c["nombre"].upper()),
                    "(SIN MAPEAR)")
        print(f"  id={c['id']:<3} {c['nombre'][:38]:38s} {c['moneda']:4s} "
              f"map={pais}")
        print(f"        asientos {f.get('primer_asiento')} → {f.get('ultimo_asiento')} "
              f"({f.get('lineas_contabilizadas', 0)} líneas)")
        print(f"        fact.cliente={v.get('facturas_cliente', 0)} "
              f"fact.prov={v.get('facturas_proveedor', 0)} "
              f"CxP pend={v.get('cxp_pendientes', 0)} (saldo {v.get('cxp_saldo', 0)})")

    print("\nCANDIDATOS A 'ECUADOR'")
    for c in doc.get("candidatos_ecuador", []):
        print(f"  score {c['score']:>4}  id={c['id']:<3} {c['nombre'][:40]:40s} "
              f"— {', '.join(c['razones'])}")

    plan = doc.get("plan_cuentas", {})
    print(f"\nPLAN DE CUENTAS — {plan.get('total_cuentas')} cuentas")
    sc = plan.get("cuentas_sin_codigo")
    if sc:
        print(f"  !! {sc} cuentas siguen sin código legible (revisar permisos del usuario Odoo)")
    print(f"  códigos con punto: {plan.get('codigos_con_punto')}")
    print(f"  largo de código  : {plan.get('largo_codigo')}")
    print(f"  primer dígito    : {plan.get('primer_digito')}")
    print("\n  COMPATIBILIDAD CON LOS PREFIJOS QUE USAN LOS EEFF (heredados de Perseo):")
    cob = plan.get("cobertura_prefijos_perseo", {})
    faltan = [p for p, n in cob.items() if n == 0]
    for p in PREFIJOS_PERSEO:
        n = cob.get(p, 0)
        marca = "  OK " if n else "  !! "
        print(f"  {marca}{p:<6} {n:>4} cuentas")
    if faltan:
        print(f"\n  >>> ALERTA: prefijos sin ninguna cuenta: {', '.join(faltan)}")
        print("      Los EEFF NO se pueden migrar por prefijo. Hay que remapear")
        print("      usando account_type de Odoo (ver odoo_estados_financieros.py).")
    else:
        print("\n  >>> El plan de cuentas conserva la codificación PUC: los EEFF")
        print("      se pueden migrar cambiando sólo la capa de extracción.")

    p = doc.get("partners", {})
    print(f"\nPARTNERS: {p.get('con_vat')}/{p.get('total_partners')} con RUC/cédula "
          f"({p.get('pct_con_vat')}%)")
    if (p.get("pct_con_vat") or 0) < 70:
        print("  >>> ALERTA: sin RUC no se puede mapear el canal comercial del presupuesto.")

    loc = doc.get("localizacion", {})
    print(f"\nLOCALIZACIÓN: l10n_ec instalado = {loc.get('l10n_ec_instalado')}")
    print(f"  módulos: {', '.join(loc.get('modulos_localizacion', [])) or '(ninguno)'}")
    print(f"  campos SRI: {', '.join(loc.get('campos_sri_en_account_move', [])) or '(ninguno)'}")
    if not loc.get("l10n_ec_instalado"):
        print("  >>> Sin l10n_ec no hay número de autorización ni estado SRI:")
        print("      el reporte diario de ventas EC pierde esas columnas.")

    print(f"\nTC A USD: {doc.get('monedas', {}).get('tc_a_usd')}")
    print("=" * 74 + "\n")


def solo_cuentas():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    od = Odoo(load_config()); od.authenticate()
    comps = d_compania(od)
    plan = d_plan_cuentas(od, [c["id"] for c in comps])
    with OUT_CSV.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["code", "code_limpio", "name", "account_type", "company_ids"])
        for a in sorted(plan["cuentas"], key=lambda x: x["code"]):
            w.writerow([a["code"], a["code_limpio"], a["name"], a["account_type"],
                        "|".join(str(i) for i in a["company_ids"])])
    log(f"OK -> {OUT_CSV} ({plan['total_cuentas']} cuentas)")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "cuentas":
        solo_cuentas()
    elif arg == "resumen":
        resumen()
    else:
        run()
