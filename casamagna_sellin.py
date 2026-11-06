#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
casamagna_sellin.py
===================
Extrae el SELL IN de Casa Magna (lo que VINTRAL le ha FACTURADO) desde las DOS
instancias de Odoo por API (XML-RPC), lo normaliza por SKU y lo fusiona:

    - vintral1.odoo.com            -> histórico (jun-2025 .. mar-2026)
    - vicomer.odoo.com (nueva)     -> abril-2026 en adelante

Criterio (igual que odoo_ventas.py): account.move out_invoice/out_refund posted;
unidades y price_subtotal por línea de producto, con signo (nota de crédito resta),
SIN IVA, en la moneda de la compañía (COP para VINTRAL).

Reutiliza la clase Odoo (cliente XML-RPC) de odoo_ventas.py.

USO:
    python3 casamagna_sellin.py diag     # prueba conexión y muestra conteos por instancia
    python3 casamagna_sellin.py          # extrae y escribe CasaMagna/sellin_casamagna.json
    python3 casamagna_sellin.py test     # autoprueba offline (sin conectarse)

Config: casamagna_config.json (instancias, partner ids, alias/exclusiones de SKU).
Claves API: en archivos aparte (apikey_file de cada instancia), chmod 600.
"""
import sys, json, datetime
from collections import defaultdict

from casamagna_common import load_config, read_secret, make_normalizer, out_dir
from odoo_ventas import Odoo, _m2o


def _instance_cfg(inst):
    return {
        "url": inst["url"].rstrip("/"),
        "db": inst.get("db"),
        "login": inst["login"],
        "apikey": read_secret(inst["apikey_file"]),
    }


def fetch_sellin(od, partner_ids):
    """Devuelve dict default_code -> {'u':unidades_con_signo, 'val':subtotal_con_signo} y meta."""
    dom_move = [["move_type", "in", ["out_invoice", "out_refund"]],
                ["state", "=", "posted"],
                ["partner_id", "child_of", list(partner_ids)]]
    moves = od.search_read("account.move", dom_move, ["id", "move_type", "invoice_date"])
    meta = {m["id"]: (m["move_type"], m.get("invoice_date")) for m in moves}
    if not moves:
        return {}, {"facturas": 0, "primera": None, "ultima": None}
    ids = list(meta.keys())

    # líneas de producto (display_type='product' en v16/17; fallback si no)
    dom_line = [["move_id", "in", ids], ["product_id", "!=", False], ["display_type", "=", "product"]]
    lines = od.search_read("account.move.line", dom_line,
                           ["product_id", "quantity", "price_subtotal", "move_id"])
    if not lines:
        dom_line = [["move_id", "in", ids], ["product_id", "!=", False]]
        lines = od.search_read("account.move.line", dom_line,
                               ["product_id", "quantity", "price_subtotal", "move_id", "display_type"])
        lines = [l for l in lines if l.get("display_type") in (False, "product", None)]

    pids = sorted({l["product_id"][0] for l in lines})
    prods = od.execute("product.product", "read", [pids, ["default_code"]]) if pids else []
    code = {p["id"]: (p.get("default_code") or "").strip() for p in prods}

    agg = defaultdict(lambda: {"u": 0.0, "val": 0.0})
    for l in lines:
        mt, _d = meta[l["move_id"][0]]
        sign = -1.0 if mt == "out_refund" else 1.0
        sku = code.get(l["product_id"][0]) or ("ID%d" % l["product_id"][0])
        agg[sku]["u"] += sign * float(l.get("quantity") or 0)
        agg[sku]["val"] += sign * float(l.get("price_subtotal") or 0)

    dates = sorted([d for (_t, d) in meta.values() if d])
    info = {"facturas": len(moves), "lineas": len(lines),
            "primera": dates[0] if dates else None, "ultima": dates[-1] if dates else None}
    return dict(agg), info


def run_extract():
    cfg = load_config()
    norm, is_excluded = make_normalizer(cfg.get("sku_alias"), cfg.get("sku_excluir"))
    merged = defaultdict(lambda: {"u": 0.0, "val": 0.0, "raw": ""})
    instancias_info = []

    for inst in cfg["odoo_instancias"]:
        icfg = _instance_cfg(inst)
        if not icfg["apikey"]:
            print(f"[WARN] {inst['nombre']}: falta API key en {inst['apikey_file']} — se omite.")
            instancias_info.append({"nombre": inst["nombre"], "error": "sin apikey"})
            continue
        try:
            od = Odoo(icfg); od.authenticate()
            agg, info = fetch_sellin(od, inst["casa_magna_partner_ids"])
        except SystemExit as e:
            print(f"[ERROR] {inst['nombre']}: {e}")
            instancias_info.append({"nombre": inst["nombre"], "error": str(e)[:160]})
            continue
        except Exception as e:
            print(f"[ERROR] {inst['nombre']}: {type(e).__name__}: {str(e)[:160]}")
            instancias_info.append({"nombre": inst["nombre"], "error": str(e)[:160]})
            continue

        u_tot = 0.0
        for sku, o in agg.items():
            if is_excluded(sku):
                continue
            n = norm(sku)
            m = merged[n]
            m["u"] += o["u"]; m["val"] += o["val"]
            if not m["raw"]:
                m["raw"] = sku
            u_tot += o["u"]
        info["nombre"] = inst["nombre"]; info["unidades"] = round(u_tot)
        instancias_info.append(info)
        print(f"[OK] {inst['nombre']}: {info['facturas']} facturas, "
              f"{info.get('lineas','?')} líneas, {round(u_tot)} u  ({info['primera']} .. {info['ultima']})")

    sellin = {k: {"u": round(v["u"]), "val": round(v["val"]), "raw": v["raw"]}
              for k, v in merged.items()}
    payload = {
        "generado": datetime.datetime.now().isoformat(timespec="seconds"),
        "instancias": instancias_info,
        "total_unidades": sum(x["u"] for x in sellin.values()),
        "total_valor": sum(x["val"] for x in sellin.values()),
        "sellin": sellin,
    }
    dst = out_dir(cfg) / "sellin_casamagna.json"
    dst.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] -> {dst}  ({len(sellin)} SKU, {payload['total_unidades']} u, "
          f"{payload['total_valor']:,.0f} COP)")
    return payload


def diag():
    cfg = load_config()
    for inst in cfg["odoo_instancias"]:
        print("=" * 66)
        print(f"  {inst['nombre']}  [{inst['url']} db={inst['db']}]")
        icfg = _instance_cfg(inst)
        print(f"  login={icfg['login']}  apikey={'sí' if icfg['apikey'] else 'FALTA (' + inst['apikey_file'] + ')'}")
        if not icfg["apikey"]:
            continue
        try:
            od = Odoo(icfg)
            print(f"  servidor: {od.version().get('server_version')}")
            od.authenticate()
            print(f"  auth OK  uid={od.uid}")
            agg, info = fetch_sellin(od, inst["casa_magna_partner_ids"])
            print(f"  Casa Magna: {info['facturas']} facturas, {info.get('lineas','?')} líneas "
                  f"({info['primera']} .. {info['ultima']}); {len(agg)} SKU distintos")
        except Exception as e:
            print(f"  ERROR: {type(e).__name__}: {str(e)[:180]}")


def _selftest():
    """Valida la agregación con signo y la normalización, sin conectarse a Odoo."""
    cfg = {"sku_alias": {"TMO30H": "TMO30", "TIM15": "TIM1501"}, "sku_excluir": ["DSTOCLI"]}
    norm, is_excluded = make_normalizer(cfg["sku_alias"], cfg["sku_excluir"])
    assert norm("HRT3618U-M1") == "HRT3618U"
    assert norm("TMO30H") == "TMO30"
    assert norm("TIM-1501") == "TIM1501" and norm("TIM15") == "TIM1501"
    assert is_excluded("DSTOCLI")

    class FakeOdoo:
        MOVES = [{"id": 1, "move_type": "out_invoice", "invoice_date": "2025-09-10"},
                 {"id": 2, "move_type": "out_refund", "invoice_date": "2025-09-20"}]
        LINES = [{"product_id": [7, "x"], "quantity": 5, "price_subtotal": 1000, "move_id": [1, "F1"]},
                 {"product_id": [7, "x"], "quantity": 2, "price_subtotal": 400, "move_id": [2, "NC1"]}]

        def search_read(self, model, dom, fields, limit=0, context=None):
            if model == "account.move":
                return self.MOVES
            if model == "account.move.line":
                return self.LINES
            return []

        def execute(self, model, method, args, kw=None):
            if model == "product.product" and method == "read":
                return [{"id": 7, "default_code": "TMO30H"}]
            return []

    agg, info = fetch_sellin(FakeOdoo(), [10])
    assert info["facturas"] == 2
    # 5 factura - 2 nota crédito = 3 unidades netas; 1000-400=600 valor
    assert abs(agg["TMO30H"]["u"] - 3) < 1e-9, agg
    assert abs(agg["TMO30H"]["val"] - 600) < 1e-9, agg
    # tras normalizar+excluir a nivel merge, TMO30H -> TMO30
    assert norm("TMO30H") == "TMO30"
    print("SELFTEST OK: NC resta, agregación por SKU y normalización correctas.")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "diag":
        diag()
    elif arg == "test":
        _selftest()
    else:
        run_extract()
