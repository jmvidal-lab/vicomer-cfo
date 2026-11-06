#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pagos_cxp.py  ·  v3 (2026-08-03) — Ecuador migrado a Odoo
=========================================================
Extrae las CUENTAS POR PAGAR (facturas de proveedor con saldo pendiente) para el
Comité de Pagos Semanal del Grupo VICOMER.

  Ecuador     -> Odoo XML-RPC  (compañía VICOMER)      [antes: Perseo]
  Costa Rica  -> Odoo XML-RPC
  Colombia    -> Odoo XML-RPC  (VINTRAL)

Perseo queda como RESPALDO: si Ecuador devuelve 0 facturas desde Odoo y hay un
endpoint de CxP configurado, se consulta Perseo y se marca el origen en el JSON.
Así la migración no puede dejar al comité a ciegas.

Novedades v3:
  - Los 3 países salen de Odoo con una sola llamada; ya no hay fuente mixta.
  - Cada país reporta `origen` ("odoo" | "perseo" | "sin_datos") y `advertencias`.
  - Notas de calidad: compañías sin mapear, moneda inesperada, TC sospechoso,
    país sin facturas.
  - Descuenta notas de crédito de proveedor (in_refund) al saldo del proveedor.
  - `diag` lista todas las compañías con su mapeo y saldo, para verificar el
    company_map en un vistazo.
  - `autotest` corre la lógica con datos sintéticos, sin red.

Salida:
  Pagos/cxp/cxp_semana_actual.json      (siempre el más reciente — lo sube Claude a Drive)
  Pagos/cxp/cxp_YYYY-Www.json           (copia histórica)

Config:
  - odoo_config.json + odoo_apikey.txt
  - pagos_reglas_depto.json             (proveedor -> departamento, tc_manual, respaldo Perseo)
  - ~/.perseo_apikey                    (sólo si se usa el respaldo)

Uso:
  python3 pagos_cxp.py            # extrae y genera JSON
  python3 pagos_cxp.py diag       # diagnóstico: compañías, mapeo, saldos, TC
  python3 pagos_cxp.py autotest   # pruebas offline de la lógica
"""
import os, sys, json, ssl, datetime, xmlrpc.client, urllib.request, urllib.error
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

PROJ = Path(__file__).resolve().parent
OUT_DIR = PROJ / "Pagos" / "cxp"
HOME = Path.home()

DEPTOS_VALIDOS = ["Comercial", "Operaciones", "Gerencia"]
DEPTO_DEFAULT = "Gerencia"

# Definición de los países del grupo. `moneda_esperada` sirve para detectar
# facturas en moneda rara (p.ej. una factura en USD dentro de Colombia).
PAISES = [
    {"code": "EC", "nombre": "Ecuador",    "bandera": "\U0001F1EA\U0001F1E8", "moneda": "USD"},
    {"code": "CR", "nombre": "Costa Rica", "bandera": "\U0001F1E8\U0001F1F7", "moneda": "CRC"},
    {"code": "CO", "nombre": "Colombia",   "bandera": "\U0001F1E8\U0001F1F4", "moneda": "COP"},
]
NOMBRE_A_CODE = {p["nombre"]: p["code"] for p in PAISES}


# ------------------------------------------------------------------ utilidades
def hoy():
    return datetime.date.today()


def iso_week(d=None):
    d = d or hoy()
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def log(msg):
    print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}", flush=True)


# ------------------------------------------------------------------ reglas de departamento
def load_reglas():
    f = PROJ / "pagos_reglas_depto.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            log(f"AVISO: pagos_reglas_depto.json inválido ({e}); uso default")
    return {"keywords": {}, "default": DEPTO_DEFAULT}


def depto_para(proveedor, reglas):
    p = (proveedor or "").lower()
    for kw, dep in reglas.get("keywords", {}).items():
        if kw.lower() in p and dep in DEPTOS_VALIDOS:
            return dep
    d = reglas.get("default", DEPTO_DEFAULT)
    return d if d in DEPTOS_VALIDOS else DEPTO_DEFAULT


# ------------------------------------------------------------------ ODOO
def odoo_cfg():
    cfg = None
    for p in (PROJ / "odoo_config.json", HOME / ".odoo_config.json"):
        if p.exists():
            cfg = json.loads(p.read_text(encoding="utf-8"))
            break
    if cfg is None:
        sys.exit("ERROR: no encuentro odoo_config.json")
    key = cfg.get("apikey")
    if not key:
        for p in (PROJ / "odoo_apikey.txt", HOME / ".odoo_apikey"):
            if p.exists():
                key = p.read_text(encoding="utf-8").strip()
                break
    if not key:
        sys.exit("ERROR: no encuentro odoo_apikey.txt")
    return cfg, key


def pais_de_company(cname, company_map):
    """Devuelve el nombre de país mapeado, 'ignore', o None si no está en el mapa."""
    cn = (cname or "").upper()
    mejor, mejor_len = None, -1
    for frag, pais in company_map.items():
        if frag.upper() in cn and len(frag) > mejor_len:
            mejor, mejor_len = pais, len(frag)
    return mejor


def odoo_conectar():
    cfg, key = odoo_cfg()
    url, db, login = cfg["url"].rstrip("/"), cfg["db"], cfg["login"]
    ctx = ssl.create_default_context()
    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common", allow_none=True, context=ctx)
    uid = common.authenticate(db, login, key, {})
    if not uid:
        sys.exit("ERROR: autenticación Odoo falló")
    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", allow_none=True, context=ctx)

    def kw(model, method, dom, **opts):
        return models.execute_kw(db, uid, key, model, method, [dom], opts)

    return cfg, kw


def odoo_cxp():
    """
    Devuelve (por_pais, tc_usd, companias, sin_mapear).
      por_pais   : {'Ecuador': [facturas], 'Costa Rica': [...], 'Colombia': [...]}
      companias  : [{id, nombre, moneda, pais_mapeado, n_facturas, saldo}]
      sin_mapear : [nombres de compañía con CxP que no están en company_map]
    """
    cfg, kw = odoo_conectar()
    cmap = cfg.get("company_map", {})

    comps = kw("res.company", "search_read", [], fields=["id", "name", "currency_id"])
    comp_ids = [c["id"] for c in comps]
    comp_por_id = {c["id"]: c for c in comps}

    campos = ["name", "ref", "partner_id", "invoice_date", "invoice_date_due",
              "amount_residual", "currency_id", "company_id", "move_type", "payment_state"]
    facts = kw("account.move", "search_read",
               [["move_type", "in", ["in_invoice", "in_refund"]],
                ["state", "=", "posted"], ["amount_residual", "!=", 0]],
               fields=campos, limit=5000,
               context={"allowed_company_ids": comp_ids})
    log(f"Odoo: {len(facts)} documentos de proveedor con saldo (facturas + NC)")

    # RUC/cédula de cada proveedor. Es lo que permite emparejar el pago con el
    # beneficiario registrado en el banco sin depender de que el nombre coincida.
    vats = {}
    pids = sorted({(f.get("partner_id") or [None])[0] for f in facts} - {None, False})
    if pids:
        try:
            for i in range(0, len(pids), 500):
                for p in kw("res.partner", "search_read", [["id", "in", pids[i:i + 500]]],
                            fields=["vat"], context={"allowed_company_ids": comp_ids}):
                    if (p.get("vat") or "").strip():
                        vats[p["id"]] = p["vat"].strip()
        except Exception as e:
            log(f"AVISO: no pude leer el RUC de los proveedores ({e}); "
                f"el archivo del banco tendrá que emparejar por nombre")

    por_pais = defaultdict(list)
    agg = defaultdict(lambda: {"n": 0, "saldo": 0.0})
    sin_mapear = {}

    for f in facts:
        comp_id = (f.get("company_id") or [0, ""])[0]
        comp_nom = (f.get("company_id") or [0, ""])[1]
        pais = pais_de_company(comp_nom, cmap)
        residual = round(float(f.get("amount_residual") or 0), 2)
        # El saldo por compañía usa el importe FIRMADO: las NC restan, no suman.
        firmado = -abs(residual) if f.get("move_type") == "in_refund" else residual
        agg[comp_id]["n"] += 1
        agg[comp_id]["saldo"] += firmado

        if pais is None:
            sin_mapear[comp_nom] = sin_mapear.get(comp_nom, 0) + 1
            continue
        if pais == "ignore":
            continue
        if pais not in NOMBRE_A_CODE:
            sin_mapear[f"{comp_nom} -> '{pais}' (país desconocido)"] = 1
            continue

        es_nc = f.get("move_type") == "in_refund"
        # Las NC de proveedor reducen lo que se le debe: monto negativo.
        monto = -abs(residual) if es_nc else residual
        pid, prov = (f.get("partner_id") or [0, "(sin proveedor)"])[:2]
        por_pais[pais].append({
            "id": f"OD-{f['id']}",
            "proveedor": prov,
            "ruc": vats.get(pid, ""),
            "factura": f.get("name") or f.get("ref") or "",
            "emision": f.get("invoice_date") or "",
            "vence": f.get("invoice_date_due") or f.get("invoice_date") or "",
            "monto": monto,
            "moneda": (f.get("currency_id") or [0, "?"])[1],
            "tipo": "NC" if es_nc else "FAC",
            "compania": comp_nom,
        })

    companias = []
    for c in comps:
        a = agg.get(c["id"], {"n": 0, "saldo": 0.0})
        companias.append({
            "id": c["id"],
            "nombre": c["name"],
            "moneda": (c.get("currency_id") or [0, "?"])[1],
            "pais_mapeado": pais_de_company(c["name"], cmap) or "(SIN MAPEAR)",
            "n_documentos": a["n"],
            "saldo": round(a["saldo"], 2),
        })

    # Tipo de cambio a USD (los rates comparten base => USD/cur = rate_USD / rate_cur)
    tc_usd = {}
    try:
        curs = kw("res.currency", "search_read",
                  [["name", "in", ["USD", "COP", "CRC"]]], fields=["name", "rate"],
                  context={"active_test": False})
        rates = {c["name"]: float(c["rate"]) for c in curs if c.get("rate")}
        if "USD" in rates:
            for name, r in rates.items():
                if r > 0:
                    tc_usd[name] = round(rates["USD"] / r, 8)
    except Exception as e:
        log(f"AVISO: no pude leer tipos de cambio de Odoo: {e}")

    _ = comp_por_id  # reservado para diagnósticos futuros
    return dict(por_pais), tc_usd, companias, sin_mapear


# ------------------------------------------------------------------ PERSEO (respaldo EC)
PERSEO_BASE = "https://perseo-data-c1.app/api/"
PERSEO_CANDIDATOS = ["cuentas_pagar_consulta", "cxp_consulta", "proveedores_saldos_consulta",
                     "compras_consulta", "facturas_compra_consulta"]


def perseo_key():
    k = os.environ.get("PERSEO_API_KEY")
    if k:
        return k.strip()
    f = HOME / ".perseo_apikey"
    return f.read_text(encoding="utf-8").strip() if f.exists() else None


def perseo_post(endpoint, extra=None):
    key = perseo_key()
    if not key:
        raise RuntimeError("sin ~/.perseo_apikey")
    body = {"api_key": key}
    body.update(extra or {})
    req = urllib.request.Request(PERSEO_BASE + endpoint,
                                 data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60, context=ssl.create_default_context()) as r:
        return json.loads(r.read().decode("utf-8"))


def perseo_cxp(reglas):
    """RESPALDO. Devuelve (facturas_ec, nota). Sólo se usa si Odoo EC vino vacío."""
    ep = reglas.get("perseo_cxp_endpoint")
    if not ep:
        return [], "Respaldo Perseo no disponible (perseo_cxp_endpoint sin configurar)"
    try:
        data = perseo_post(ep)
    except Exception as e:
        return [], f"Respaldo Perseo falló ({ep}): {e}"
    try:
        (OUT_DIR / "perseo_cxp_raw.json").write_text(
            json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    items = None
    if isinstance(data, dict):
        for k in ("cuentasporpagar", "cxp", "facturas", "documentos", "saldos", "data"):
            if isinstance(data.get(k), list):
                items = data[k]; break
    elif isinstance(data, list):
        items = data
    if items is None:
        return [], f"Respaldo Perseo ({ep}) sin lista reconocible — ver perseo_cxp_raw.json"

    out = []
    for i, it in enumerate(items):
        prov = it.get("proveedor") or it.get("razonsocial") or it.get("nombre") or "(sin proveedor)"
        num = (it.get("numerofactura") or it.get("documento") or it.get("numero")
               or it.get("factura") or "")
        vence = it.get("fechavencimiento") or it.get("vencimiento") or it.get("fecha") or ""
        if isinstance(vence, str) and len(vence) == 8 and vence.isdigit():
            vence = f"{vence[:4]}-{vence[4:6]}-{vence[6:]}"
        monto = it.get("saldo") or it.get("valorpendiente") or it.get("total") or 0
        try:
            monto = round(float(monto), 2)
        except (TypeError, ValueError):
            monto = 0.0
        if monto <= 0:
            continue
        out.append({"id": f"PE-{i}", "proveedor": str(prov).strip(), "factura": str(num).strip(),
                    "emision": "", "vence": str(vence)[:10], "monto": monto, "moneda": "USD",
                    "tipo": "FAC", "compania": "(Perseo)"})
    return out, None


# ------------------------------------------------------------------ armado del JSON
def enriquecer(facts, reglas, ref=None):
    """Añade depto y días vencida; ordena por vencimiento."""
    ref = ref or hoy()
    for f in facts:
        f["depto"] = depto_para(f["proveedor"], reglas)
        dias = 0
        v = f.get("vence")
        if v:
            try:
                dias = max(0, (ref - datetime.date.fromisoformat(str(v)[:10])).days)
            except ValueError:
                dias = 0
        f["dias_vencida"] = dias
    return sorted(facts, key=lambda x: x.get("vence") or "9999")


def construir_doc(por_pais, tc_usd, companias, sin_mapear, reglas, ec_respaldo=None):
    """Lógica pura de armado — sin red. Testeable con autotest()."""
    notas = []
    tc_usd = dict(tc_usd)
    tc_usd.setdefault("USD", 1.0)

    # Odoo de VICOMER NO mantiene tipos de cambio: COP, CRC y EUR devuelven todos la
    # misma tasa. Se detecta comparando las tasas CRUDAS: si dos monedas distintas
    # comparten valor, la tabla de Odoo no es usable.
    crudas = {c: v for c, v in tc_usd.items() if c != "USD"}
    degeneradas = sorted(c for c in crudas if list(crudas.values()).count(crudas[c]) > 1)
    manual = reglas.get("tc_manual") or {}
    for cur, v in manual.items():
        try:
            tc_usd[cur] = float(v)
        except (TypeError, ValueError):
            pass
    sin_override = [c for c in degeneradas if c not in manual]
    tc_confiable = not degeneradas
    if degeneradas:
        if sin_override:
            notas.append(f"TC NO CONFIABLE en Odoo ({', '.join(degeneradas)} comparten tasa) y "
                         f"SIN override para {', '.join(sin_override)}: el total en USD de esos "
                         f"países está mal. Fijar 'tc_manual' en pagos_reglas_depto.json.")
        else:
            notas.append(f"Odoo no mantiene tipos de cambio ({', '.join(degeneradas)} comparten "
                         f"tasa); se usaron los overrides manuales. El total en USD es REFERENCIAL: "
                         f"la cifra que manda es la de cada país en su moneda.")

    for nombre, n in (sin_mapear or {}).items():
        notas.append(f"Compañía sin mapear en company_map: «{nombre}» ({n} docs excluidos)")

    paises_out = []
    for p in PAISES:
        facts = list(por_pais.get(p["nombre"], []))
        origen = "odoo"
        adv = []

        if p["code"] == "EC" and not facts and ec_respaldo:
            facts_resp, nota_resp = ec_respaldo
            if facts_resp:
                facts = facts_resp
                origen = "perseo"
                adv.append("Ecuador salió del respaldo Perseo: Odoo no devolvió CxP. "
                           "Verificar el mapeo de la compañía VICOMER.")
                notas.append("Ecuador usó el RESPALDO Perseo — revisar la migración a Odoo")
            elif nota_resp:
                adv.append(nota_resp)

        if not facts:
            origen = "sin_datos"
            adv.append(f"{p['nombre']} no tiene cuentas por pagar pendientes. "
                       "Si esto es inesperado, revisar company_map y permisos del usuario Odoo.")

        monedas = {f.get("moneda") for f in facts}
        raras = monedas - {p["moneda"], "USD"}
        if raras:
            adv.append(f"Monedas inesperadas en {p['nombre']}: {', '.join(sorted(raras))}")
        sin_tc = sorted(m for m in monedas if m and m not in tc_usd)
        if sin_tc:
            adv.append(f"Sin tipo de cambio para: {', '.join(sin_tc)} — no entran al consolidado USD")

        facts = enriquecer(facts, reglas)
        # Los totales netean las NC (son saldo a favor), pero los CONTEOS sólo miran
        # facturas pagables: el artefacto excluye las NC de la ventana de decisión y
        # ambas cifras tienen que coincidir.
        pagables = [f for f in facts if f["monto"] > 0]
        ncs = [f for f in facts if f["monto"] < 0]
        total_local = round(sum(f["monto"] for f in facts), 2)
        total_usd = round(sum(f["monto"] * tc_usd.get(f.get("moneda"), 0.0) for f in facts), 2)
        vencidas = [f for f in pagables if f["dias_vencida"] > 0]

        paises_out.append({
            "code": p["code"], "nombre": p["nombre"], "sistema": "Odoo" if origen == "odoo" else
                                 ("Perseo (respaldo)" if origen == "perseo" else "Odoo"),
            "origen": origen, "moneda": p["moneda"], "bandera": p["bandera"],
            "advertencias": adv,
            "resumen": {
                "n_documentos": len(pagables),
                "n_notas_credito": len(ncs),
                "n_vencidas": len(vencidas),
                "nc_local": round(sum(abs(f["monto"]) for f in ncs), 2),
                "total_local": total_local,
                "total_usd": total_usd,
                "vencido_usd": round(sum(f["monto"] * tc_usd.get(f.get("moneda"), 0.0)
                                         for f in vencidas), 2),
            },
            "facturas": facts,
        })

    total_grupo_usd = round(sum(p["resumen"]["total_usd"] for p in paises_out), 2)
    return {
        "semana": iso_week(),
        "generado": datetime.datetime.now().isoformat(timespec="seconds"),
        "version": 3,
        "fuente": "odoo",
        "tc_usd": tc_usd,
        # La cifra autoritativa es la de cada país en SU moneda. El consolidado en USD
        # sirve para dimensionar, no para decidir, mientras tc_confiable sea falso.
        "tc_confiable": tc_confiable,
        "tc_origen": {c: ("manual" if c in manual else "odoo") for c in tc_usd},
        "notas": notas,
        "companias_odoo": companias,
        "consolidado": {
            "total_usd": total_grupo_usd,
            "vencido_usd": round(sum(p["resumen"]["vencido_usd"] for p in paises_out), 2),
            "n_documentos": sum(p["resumen"]["n_documentos"] for p in paises_out),
            "referencial": not tc_confiable,
            "por_pais_local": {p["code"]: {"moneda": p["moneda"],
                                           "total": p["resumen"]["total_local"]}
                               for p in paises_out},
        },
        "paises": paises_out,
    }


def build():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    reglas = load_reglas()
    por_pais, tc_usd, companias, sin_mapear = odoo_cxp()

    ec_respaldo = None
    if not por_pais.get("Ecuador"):
        log("Ecuador vino vacío desde Odoo — probando respaldo Perseo…")
        ec_respaldo = perseo_cxp(reglas)

    doc = construir_doc(por_pais, tc_usd, companias, sin_mapear, reglas, ec_respaldo)

    txt = json.dumps(doc, indent=1, ensure_ascii=False)
    (OUT_DIR / "cxp_semana_actual.json").write_text(txt, encoding="utf-8")
    (OUT_DIR / f"cxp_{doc['semana']}.json").write_text(txt, encoding="utf-8")

    detalle = ", ".join(f"{p['code']}={p['resumen']['n_documentos']}({p['origen']})"
                        for p in doc["paises"])
    log(f"OK: {doc['consolidado']['n_documentos']} docs [{detalle}]")
    for p in doc["paises"]:
        log(f"    {p['code']}: {p['resumen']['total_local']:>18,.2f} {p['moneda']}"
            f"   (vencido {p['resumen']['n_vencidas']} docs)")
    ref = " [REFERENCIAL — TC no confiable]" if doc["consolidado"]["referencial"] else ""
    log(f"    Grupo USD {doc['consolidado']['total_usd']:,.0f} "
        f"(vencido {doc['consolidado']['vencido_usd']:,.0f}){ref}")
    log(f"    -> {OUT_DIR / 'cxp_semana_actual.json'}")
    for n in doc["notas"]:
        log("NOTA: " + n)
    for p in doc["paises"]:
        for a in p["advertencias"]:
            log(f"AVISO [{p['code']}]: {a}")


# ------------------------------------------------------------------ diagnóstico
def diag():
    log("== Odoo: compañías, mapeo y saldos ==")
    por_pais, tc, companias, sin_mapear = odoo_cxp()
    print(f"\n{'id':>3}  {'compañía':40s} {'mon':4s} {'país mapeado':14s} {'docs':>5} {'saldo':>16}")
    print("-" * 92)
    for c in companias:
        marca = " " if c["pais_mapeado"] != "(SIN MAPEAR)" else "!"
        print(f"{marca}{c['id']:>2}  {c['nombre'][:40]:40s} {c['moneda']:4s} "
              f"{c['pais_mapeado']:14s} {c['n_documentos']:>5} {c['saldo']:>16,.2f}")
    print()
    for pais in [p["nombre"] for p in PAISES]:
        fs = por_pais.get(pais, [])
        log(f"  {pais}: {len(fs)} documentos con saldo")
        for f in fs[:5]:
            print(f"      {f['proveedor'][:32]:32s} {f['factura'][:20]:20s} "
                  f"vence {f['vence']} {f['monto']:>14,.2f} {f['moneda']} [{f['tipo']}]")
    if sin_mapear:
        print()
        for nombre, n in sin_mapear.items():
            log(f"  !! SIN MAPEAR: «{nombre}» — {n} documentos excluidos")
        log("     Añádelas a company_map en odoo_config.json (o pon 'ignore').")
    log(f"  TC USD: {tc}")

    reglas = load_reglas()
    if reglas.get("perseo_cxp_endpoint"):
        log("== Respaldo Perseo configurado: probando ==")
        fs, nota = perseo_cxp(reglas)
        log(f"  {len(fs)} documentos · {nota or 'OK'}")
    else:
        log("== Respaldo Perseo NO configurado (perseo_cxp_endpoint = null) ==")
        log("   Es lo esperado si Ecuador ya está 100% en Odoo.")


# ------------------------------------------------------------------ autotest offline
def autotest():
    """Verifica la lógica de armado sin tocar la red."""
    reglas = {"keywords": {"naviera": "Operaciones", "legal": "Gerencia"},
              "default": "Gerencia", "tc_manual": {"CRC": 0.00221, "COP": 0.00027027}}
    tc = {"USD": 1.0, "COP": 0.00025, "CRC": 0.00025}   # tasas degeneradas a propósito
                                                        # (así las devuelve el Odoo real)
    hace30 = (hoy() - datetime.timedelta(days=30)).isoformat()
    manana = (hoy() + datetime.timedelta(days=1)).isoformat()
    por_pais = {
        "Ecuador": [
            {"id": "OD-1", "proveedor": "NAVIERA DEL PACIFICO", "factura": "F-1",
             "emision": hace30, "vence": hace30, "monto": 1000.0, "moneda": "USD",
             "tipo": "FAC", "compania": "VICOMER S.A."},
            {"id": "OD-2", "proveedor": "NAVIERA DEL PACIFICO", "factura": "NC-1",
             "emision": hace30, "vence": hace30, "monto": -200.0, "moneda": "USD",
             "tipo": "NC", "compania": "VICOMER S.A."},
        ],
        "Costa Rica": [
            {"id": "OD-3", "proveedor": "CORPORATIVA LEGAL", "factura": "F-9",
             "emision": hace30, "vence": manana, "monto": 452000.0, "moneda": "CRC",
             "tipo": "FAC", "compania": "3-102-940094"},
        ],
    }
    comps = [{"id": 1, "nombre": "VICOMER S.A.", "moneda": "USD", "pais_mapeado": "Ecuador",
              "n_documentos": 2, "saldo": 800.0}]
    doc = construir_doc(por_pais, tc, comps, {"CASA MAGNA LTDA": 3}, reglas)

    fallos = []

    def check(cond, msg):
        (print(f"  ok  {msg}") if cond else fallos.append(msg))

    ec = next(p for p in doc["paises"] if p["code"] == "EC")
    cr = next(p for p in doc["paises"] if p["code"] == "CR")
    co = next(p for p in doc["paises"] if p["code"] == "CO")

    check(ec["resumen"]["total_local"] == 800.0, "NC de proveedor resta al saldo EC (1000-200=800)")
    check(ec["resumen"]["n_documentos"] == 1 and ec["resumen"]["n_notas_credito"] == 1,
          "los conteos separan facturas pagables de notas de crédito")
    check(ec["resumen"]["n_vencidas"] == 1, "las NC no cuentan como factura vencida")
    check(ec["resumen"]["total_usd"] == 800.0, "EC consolida a USD sin conversión")
    check(ec["origen"] == "odoo", "EC marcado con origen odoo")
    check(ec["facturas"][0]["depto"] == "Operaciones", "regla naviera -> Operaciones")
    check(all(f["dias_vencida"] >= 29 for f in ec["facturas"]), "días vencida calculados")
    check(cr["resumen"]["n_vencidas"] == 0, "factura que vence mañana no cuenta como vencida")
    check(abs(cr["resumen"]["total_usd"] - round(452000 * 0.00221, 2)) < 0.01,
          "tc_manual pisa el TC malo de Odoo para CRC")
    check(co["origen"] == "sin_datos", "país sin facturas marcado sin_datos")
    check(any("no tiene cuentas por pagar" in a for a in co["advertencias"]),
          "advertencia por país vacío")
    check(any("sin mapear" in n.lower() for n in doc["notas"]), "nota por compañía sin mapear")
    check(any("REFERENCIAL" in n for n in doc["notas"]),
          "declara el consolidado USD como referencial si Odoo no tiene TC reales")
    check(doc["tc_confiable"] is False and doc["consolidado"]["referencial"] is True,
          "marca tc_confiable=False y consolidado.referencial=True")
    check(doc["consolidado"]["por_pais_local"]["EC"] == {"moneda": "USD", "total": 800.0},
          "el consolidado expone el total de cada país en SU moneda")
    check(doc["tc_origen"]["CRC"] == "manual" and doc["tc_origen"]["USD"] == "odoo",
          "queda trazado qué tasa vino de Odoo y cuál se puso a mano")

    parcial = dict(reglas, tc_manual={"CRC": 0.00221})   # falta el override de COP
    doc_p = construir_doc(por_pais, tc, comps, {}, parcial)
    check(any("SIN override para COP" in n for n in doc_p["notas"]),
          "señala exactamente qué moneda quedó sin override")

    sin_override = {k: v for k, v in reglas.items() if k != "tc_manual"}
    doc_so = construir_doc(por_pais, tc, comps, {}, sin_override)
    check(any("SIN override" in n for n in doc_so["notas"]),
          "alerta fuerte si el TC está mal y nadie lo corrigió")
    cr_so = next(p for p in doc_so["paises"] if p["code"] == "CR")
    check(abs(cr_so["resumen"]["total_usd"] - round(452000 * 0.00025, 2)) < 0.01,
          "sin override se usa el TC (malo) de Odoo, no se inventa uno")
    check(doc["consolidado"]["n_documentos"] == 2,
          "el consolidado cuenta sólo facturas pagables (2), no las NC")
    check(len(doc["paises"]) == 3, "siempre salen los 3 países")

    # Respaldo Perseo
    doc2 = construir_doc({"Costa Rica": []}, tc, comps, {}, reglas,
                         ec_respaldo=([{"id": "PE-0", "proveedor": "X", "factura": "1",
                                        "emision": "", "vence": hace30, "monto": 50.0,
                                        "moneda": "USD", "tipo": "FAC",
                                        "compania": "(Perseo)"}], None))
    ec2 = next(p for p in doc2["paises"] if p["code"] == "EC")
    check(ec2["origen"] == "perseo", "respaldo Perseo se activa si Odoo EC viene vacío")
    check(any("RESPALDO" in n for n in doc2["notas"]), "nota visible cuando se usa el respaldo")

    print()
    if fallos:
        for f in fallos:
            print(f"  FALLA  {f}")
        sys.exit(f"AUTOTEST: {len(fallos)} fallas")
    print("AUTOTEST OK — toda la lógica de armado pasa.")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "diag":
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        diag()
    elif arg == "autotest":
        autotest()
    else:
        build()
