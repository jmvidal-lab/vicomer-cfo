#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compras_fix_paises.py  ·  Grupo VICOMER
=======================================
Asigna `country_id` a los proveedores que no lo tienen, para que la regla
local/exterior del dashboard de compras funcione.

FILOSOFIA DE SEGURIDAD (esto escribe en Odoo — lee esto antes de correrlo):

  * Solo propone el pais de la COMPANIA QUE LE FACTURO, y unicamente cuando el
    formato del RUC/NIT/cedula juridica lo CORROBORA. Nunca infiere un pais
    extranjero: si el proveedor parece de afuera, lo deja para revision manual.
  * Nunca sobrescribe un country_id ya cargado.
  * Sin `--aplicar` no escribe nada: imprime el plan y sale.
  * Deja bitacora en OdooVentas/compras_fix_paises.log con el antes y el despues.

Formatos que reconoce:
  Ecuador     RUC 13 digitos terminado en 001 · cedula 10 digitos (3er digito 0-5)
  Colombia    NIT 9-10 digitos (con o sin digito de verificacion tras guion)
  Costa Rica  cedula juridica 10 digitos que empieza en 3 · cedula fisica 9 digitos

Uso:
    python3 compras_fix_paises.py             # plan, no escribe
    python3 compras_fix_paises.py --aplicar   # escribe en Odoo
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

HOME = Path.home()
PROJ = Path(os.environ.get("VICOMER_PROJ", HOME / "Claude" / "Projects" / "CFO VICOMER"))
OUT = PROJ / "OdooVentas"
BITACORA = OUT / "compras_fix_paises.log"

PAIS_DE_COMPANIA = {"VICOMER": "EC", "VINTRAL": "CO", "3-102-940094": "CR",
                    "SOCIEDAD DE RESPONSABILIDAD": "CR"}
EXCLUIR = ("VIX",)


def solo_digitos(s):
    return re.sub(r"\D", "", s or "")


def formato_vat(vat):
    """Devuelve el conjunto de paises compatibles con ese identificador."""
    d = solo_digitos(vat)
    out = set()
    if not d:
        return out
    if len(d) == 13 and d.endswith("001"):
        out.add("EC")
    if len(d) == 10 and d[0] != "3" and (d[2] in "012345"):
        out.add("EC")               # cedula ecuatoriana
    if len(d) in (9, 10):
        out.add("CO")               # NIT colombiano
    if len(d) == 10 and d[0] == "3":
        out.add("CR")               # cedula juridica CR
        out.discard("EC")
    if len(d) == 9:
        out.add("CR")               # cedula fisica CR
    return out


# Sufijos societarios que delatan una sociedad NO domiciliada en EC/CO/CR. Un
# identificador de 9-10 digitos es compatible con Colombia y con Ecuador a la vez,
# asi que el formato solo no alcanza: si el nombre huele a extranjero, va a revision
# manual aunque el numero cuadre. Es el caso de GLOBAL TRADE BRANDS CORP.
SUFIJOS_EXTRANJEROS = (" CORP", " CORP.", " INC", " INC.", " LLC", " LTD", " LTD.",
                       " CO., LTD", " GMBH", " PTE", " S.R.O.", " SRO", " B.V.", " BV",
                       " N.V.", " PLC", " AG", " SPA", " S.P.A.", " KFT", " OY", " AB",
                       " LIMITED", " HOLDINGS", " INTERNATIONAL", " GROUP CO")

# Sufijos societarios locales, que si corroboran domicilio en la region.
SUFIJOS_LOCALES = ("S.A.S", "SAS", "CIA. LTDA", "CIA LTDA", "C.A.", " CA",
                   "S.A.", " SA", "LTDA", "SOCIEDAD ANONIMA", "E.U.", "S. EN C.")


def huele_a_extranjero(nombre):
    n = " " + (nombre or "").upper().strip()
    if any(n.endswith(x) or (x + " ") in n for x in SUFIJOS_EXTRANJEROS):
        return True
    return False


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
        sys.exit("ERROR: no autentico contra Odoo.")

    def kw(self, model, method, args, kwargs=None):
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


def pais_de(nombre):
    n = (nombre or "").upper()
    if any(x in n for x in EXCLUIR) and "VICOMER" not in n and "VINTRAL" not in n:
        return None
    best, bl = None, -1
    for frag, code in PAIS_DE_COMPANIA.items():
        if frag in n and len(frag) > bl:
            best, bl = code, len(frag)
    return best


def main():
    aplicar = "--aplicar" in sys.argv
    year = datetime.date.today().year
    cfg = load_config()
    od = Odoo(cfg); od.authenticate()

    comps = {}
    for r in od.sr("res.company", [], ["id", "name"]):
        comps[r["id"]] = {"name": r["name"], "pais": pais_de(r["name"])}
    ctx = {"allowed_company_ids": list(comps.keys())}

    paises = {}
    for r in od.sr("res.country", [["code", "in", ["EC", "CO", "CR"]]], ["id", "code", "name"]):
        paises[r["code"]] = {"id": r["id"], "name": r["name"]}

    # facturas de proveedor del anio -> partner + compania que facturo
    dom = [["move_type", "in", ["in_invoice", "in_refund"]], ["state", "=", "posted"],
           ["invoice_date", ">=", "%d-01-01" % year]]
    facturas = od.sr("account.move", dom,
                     ["partner_id", "company_id", "amount_untaxed_signed"], ctx=ctx)
    porpartner = {}
    for f in facturas:
        pid, pname = m2o(f.get("partner_id"))
        cid, cname = m2o(f.get("company_id"))
        if not pid:
            continue
        a = porpartner.setdefault(pid, {"nombre": pname, "companias": {}, "monto": 0.0, "n": 0})
        a["monto"] += -float(f.get("amount_untaxed_signed") or 0)
        a["n"] += 1
        a["companias"][comps.get(cid, {}).get("pais")] = a["companias"].get(comps.get(cid, {}).get("pais"), 0) + 1

    ids = sorted(porpartner.keys())
    info = {}
    for i in range(0, len(ids), 300):
        for p in od.sr("res.partner", [["id", "in", ids[i:i + 300]]],
                       ["id", "name", "vat", "country_id"], ctx=ctx):
            info[p["id"]] = p

    sin_pais = [i for i in ids if not (info.get(i, {}).get("country_id"))]

    W = 100
    print("=" * W)
    print("  ASIGNACION DE PAIS A PROVEEDORES  —  %s" % ("APLICAR (escribe en Odoo)" if aplicar else "PLAN (no escribe nada)"))
    print("=" * W)
    print("  Proveedores con factura %d: %d   ·   sin country_id: %d" % (year, len(ids), len(sin_pais)))
    print()

    plan, manual = [], []
    for pid in sin_pais:
        a = porpartner[pid]
        p = info.get(pid, {})
        vat = (p.get("vat") or "").strip()
        compat = formato_vat(vat)
        cand = sorted(a["companias"].items(), key=lambda x: -x[1])
        pais_comp = cand[0][0] if cand else None
        if pais_comp and pais_comp in compat and not huele_a_extranjero(a["nombre"]):
            plan.append({"id": pid, "nombre": a["nombre"], "vat": vat, "pais": pais_comp,
                         "monto": round(a["monto"], 2), "n": a["n"],
                         "motivo": "el identificador tiene formato de %s y le facturo la compania de %s" % (pais_comp, pais_comp)})
        else:
            motivo = ("nombre societario de sociedad extranjera" if huele_a_extranjero(a["nombre"])
                      else ("sin RUC/NIT cargado" if not vat
                            else "el formato del identificador no corrobora el pais de la compania que facturo"))
            manual.append({"id": pid, "nombre": a["nombre"], "vat": vat, "motivo": motivo,
                           "pais_compania": pais_comp, "compatible_con": sorted(compat) or ["(indeterminado)"],
                           "monto": round(a["monto"], 2), "n": a["n"]})

    print("  A CORREGIR AUTOMATICAMENTE (%d) — el identificador corrobora el pais:" % len(plan))
    print("  %-5s %-46s %-16s %-4s %14s %4s" % ("id", "proveedor", "RUC/NIT", "pais", "monto", "docs"))
    for r in plan:
        print("  %-5s %-46s %-16s %-4s %14.2f %4d" % (r["id"], r["nombre"][:46], r["vat"][:16], r["pais"], r["monto"], r["n"]))
    if not plan:
        print("    (ninguno)")

    print()
    print("  PARA REVISION MANUAL (%d) — NO se tocan:" % len(manual))
    print("  %-5s %-42s %-15s %-8s %14s  %s" % ("id", "proveedor", "RUC/NIT", "facturo", "monto", "por que"))
    for r in manual:
        print("  %-5s %-42s %-15s %-8s %14.2f  %s" % (r["id"], r["nombre"][:42], (r["vat"] or "(sin RUC)")[:15],
                                                      r["pais_compania"] or "?", r["monto"], r["motivo"]))
    if not manual:
        print("    (ninguno)")

    print()
    if not aplicar:
        print("  Esto fue un PLAN. Para escribirlo en Odoo, vuelve a correrlo con:  --aplicar")
        print("=" * W)
        return

    escritos, errores = [], []
    for r in plan:
        try:
            od.kw("res.partner", "write", [[r["id"]], {"country_id": paises[r["pais"]]["id"]}], {"context": ctx})
            escritos.append(r)
            print("  [OK]    %-46s -> %s" % (r["nombre"][:46], paises[r["pais"]]["name"]))
        except Exception as e:
            errores.append({"r": r, "error": str(e)[:160]})
            print("  [FALLO] %-46s : %s" % (r["nombre"][:46], str(e)[:100]))

    # verificacion: releer y confirmar
    print()
    print("  VERIFICACION (relectura desde Odoo):")
    ver = od.sr("res.partner", [["id", "in", [r["id"] for r in escritos]]], ["id", "name", "country_id"], ctx=ctx)
    for p in ver:
        _, cn = m2o(p.get("country_id"))
        print("     %-46s country_id = %s" % ((p.get("name") or "")[:46], cn or "SIGUE VACIO"))
    nuevos_sin = len(sin_pais) - len(escritos)
    cob = (len(ids) - nuevos_sin) / float(len(ids)) if ids else 0
    print()
    print("  Cobertura de country_id: %.1f%%  (%d de %d proveedores)" % (cob * 100, len(ids) - nuevos_sin, len(ids)))
    print("=" * W)

    OUT.mkdir(parents=True, exist_ok=True)
    with open(str(BITACORA), "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"cuando": datetime.datetime.now().isoformat(timespec="seconds"),
                             "escritos": escritos, "errores": errores, "manual": manual,
                             "cobertura_resultante": round(cob, 4)}, ensure_ascii=False) + "\n")
    print("  Bitacora -> %s" % BITACORA)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(traceback.format_exc()); sys.exit(1)
