#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cartera_dashboard.py — Genera el dashboard de cartera de Casa Magna desde Odoo.

Produce:
  cartera_dashboard.html   <- la pagina (se publica como Artifact)
  cartera_dashboard.json   <- los datos crudos (para Claude Code / auditoria)
  cartera_real_<slug>_<AAAAMMDD>.csv

No consulta el modelo account.move: la base tiene el modulo l10n_ec a medio
instalar (falta account_move.l10n_ec_sri_import_withhold) y cualquier lectura
de facturas revienta. Todo sale de account.move.line.

Ajustes manuales (pagos con comprobante que contabilidad aun no registro):
  cartera_ajustes.json  en la misma carpeta, formato:
    {"pendientes": [
       {"ce": "CE2860", "fecha": "2026-10-02", "facturas": ["FE315","FE316"]}
    ]}
  Esas facturas se marcan como pagadas y se descuentan del total.

Uso:
    python3 cartera_dashboard.py
    python3 cartera_dashboard.py --cliente "casa magna" --meses 18
    python3 cartera_dashboard.py --from-csv archivo.csv    (modo offline, pruebas)

Solo lectura: NO modifica nada en Odoo.
"""

import os, sys, json, ssl, csv, argparse, datetime, xmlrpc.client
from pathlib import Path
from collections import defaultdict

HOME = Path.home()
PROJ = HOME / "Claude" / "Projects" / "CFO VICOMER"
OUT_DIR = Path(os.environ.get("ODOO_OUT_DIR", PROJ / "OdooVentas"))

BUCKETS = ["Corriente", "1-30", "31-60", "61-90", "91-180", ">180"]


# ----------------------------------------------------------------- config
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
                print(f"[WARN] {f}: {e}")
    for kf in (HOME / ".odoo_apikey", PROJ / "odoo_apikey.txt"):
        if not cfg["apikey"] and kf.exists():
            cfg["apikey"] = kf.read_text(encoding="utf-8").strip()
    if cfg.get("url"):
        cfg["url"] = cfg["url"].rstrip("/")
    falta = [k for k in ("url", "login", "apikey") if not cfg.get(k)]
    if falta:
        sys.exit("ERROR: faltan credenciales de Odoo: " + ", ".join(falta))
    return cfg


class Odoo:
    def __init__(self, cfg):
        self.cfg = cfg
        ctx = ssl.create_default_context()
        self.common = xmlrpc.client.ServerProxy(f"{cfg['url']}/xmlrpc/2/common", allow_none=True, context=ctx)
        self.models = xmlrpc.client.ServerProxy(f"{cfg['url']}/xmlrpc/2/object", allow_none=True, context=ctx)
        self.uid = None

    def authenticate(self):
        host = self.cfg["url"].split("//")[-1].split("/")[0]
        last = None
        for db in [d for d in (self.cfg.get("db"), host.split(".")[0], host) if d]:
            try:
                uid = self.common.authenticate(db, self.cfg["login"], self.cfg["apikey"], {})
            except Exception as e:
                last = str(e)[:200]; continue
            if uid:
                self.cfg["db"] = db; self.uid = uid
                return uid
        sys.exit(f"ERROR: no autentico. Ultimo error: {last}")

    def sr(self, model, domain, fields, limit=0, ctx=None):
        kw = {"fields": fields}
        if limit: kw["limit"] = limit
        if ctx: kw["context"] = ctx
        return self.models.execute_kw(self.cfg["db"], self.uid, self.cfg["apikey"],
                                      model, "search_read", [domain], kw)

    def sr_drop(self, model, domain, fields, **kw):
        f = list(fields)
        while f:
            try:
                return self.sr(model, domain, f, **kw)
            except Exception as e:
                msg = str(e)
                drop = next((c for c in f if c in msg and c != "id"), f[-1] if len(f) > 1 else None)
                if drop is None: raise
                f.remove(drop)
                print(f"    [.] campo '{drop}' no disponible, se omite")
        raise RuntimeError("no se pudo consultar " + model)


# ----------------------------------------------------------------- utils
def d(s):
    try: return datetime.date.fromisoformat(str(s)[:10])
    except Exception: return None

def chunks(l, n=400):
    for i in range(0, len(l), n): yield l[i:i+n]

def clasificar(nombre):
    n = (nombre or "").upper().strip()
    if not n: return "otro"
    if n.startswith(("RNC", "NC", "RC")): return "nota_credito"
    if "MISC" in n or n.startswith(("CE", "TEF", "BNK", "CSH", "PAY")): return "refinanciada"
    if n.startswith(("FE", "FV", "INV", "FAC")): return "factura"
    return "otro"

def bucket(dias):
    if dias <= 0: return BUCKETS[0]
    if dias <= 30: return BUCKETS[1]
    if dias <= 60: return BUCKETS[2]
    if dias <= 90: return BUCKETS[3]
    if dias <= 180: return BUCKETS[4]
    return BUCKETS[5]


# ----------------------------------------------------------------- extraccion
def extraer(args):
    cfg = load_config()
    od = Odoo(cfg); od.authenticate()
    print(f"[OK] {cfg['url']} db='{cfg['db']}'")

    hoy = datetime.date.today()
    desde = (hoy.replace(day=1) - datetime.timedelta(days=31 * args.meses)).replace(day=1)

    term = args.cliente.replace(" ", "%")
    ps = od.sr("res.partner", ["|", ("name", "ilike", term), ("name", "ilike", args.cliente)],
               ["id", "name"], ctx={"active_test": False})
    pids = [p["id"] for p in ps]
    if not pids:
        sys.exit(f"No se encontro cliente '{args.cliente}'")
    print(f"[OK] {len(pids)} contacto(s)")

    base = [("partner_id", "child_of", pids), ("parent_state", "=", "posted")]
    dom = None
    for cond in [("account_id.account_type", "=", "asset_receivable"),
                 ("account_id.internal_type", "=", "receivable"),
                 ("account_id.user_type_id.type", "=", "receivable")]:
        try:
            od.sr("account.move.line", base + [cond], ["id"], limit=1)
            dom = base + [cond]; break
        except Exception:
            continue
    if dom is None:
        sys.exit("ERROR: no pude identificar la cuenta por cobrar.")

    CAMPOS = ["id", "move_name", "date", "date_maturity", "amount_residual", "debit", "credit"]
    abiertas = od.sr_drop("account.move.line",
                          dom + [("reconciled", "=", False), ("amount_residual", "!=", 0)], CAMPOS)

    filas = []
    for l in abiertas:
        s = l.get("amount_residual") or 0.0
        if abs(s) < 1000: continue
        nom = l.get("move_name") or ""
        venc = l.get("date_maturity") or l.get("date")
        v = d(venc)
        dias = (hoy - v).days if v else 0
        filas.append({"doc": nom, "tipo": clasificar(nom), "fecha": l.get("date"),
                      "vence": venc, "dias": dias, "saldo": s, "aging": bucket(dias)})

    # Ids de los asientos para enlazar a Odoo. Se piden SOLO id y name: no hay
    # many2one de por medio, asi que no se dispara el display_name de
    # account.move que es lo que revienta con el modulo l10n_ec incompleto.
    # Si aun asi falla, seguimos sin enlaces en vez de romper el reporte.
    nombres = sorted({f["doc"] for f in filas if f["doc"]})
    oids = {}
    for ch in chunks(nombres, 200):
        try:
            for m in od.sr("account.move", [("name", "in", ch)], ["id", "name"]):
                oids[m["name"]] = m["id"]
        except Exception as e:
            print(f"    [.] sin enlaces a Odoo: {str(e)[:80]}")
            oids = {}; break
    for f in filas:
        f["oid"] = oids.get(f["doc"], 0)
    if oids:
        print(f"[OK] {len(oids)} documentos enlazados a Odoo")

    # historico
    hist = od.sr_drop("account.move.line",
                      dom + [("debit", ">", 0), ("date", ">=", desde.isoformat())],
                      ["id", "move_name", "date", "date_maturity", "debit"])
    hmap = {l["id"]: l for l in hist}
    fact_mes = defaultdict(float)
    for l in hist:
        if clasificar(l.get("move_name")) != "factura": continue
        fd = d(l.get("date"))
        if fd: fact_mes[fd.strftime("%Y-%m")] += l.get("debit") or 0.0

    partials = []
    for ch in chunks(list(hmap.keys())):
        try:
            partials += od.sr("account.partial.reconcile", [("debit_move_id", "in", ch)],
                              ["debit_move_id", "amount", "max_date"])
        except Exception as e:
            print(f"    [.] conciliaciones no legibles: {str(e)[:70]}"); break

    cobr_mes = defaultdict(float); num = den = 0.0
    for p in partials:
        li = (p.get("debit_move_id") or [None])[0]
        l = hmap.get(li)
        if not l: continue
        fp = d(p.get("max_date")); amt = p.get("amount") or 0.0
        if fp: cobr_mes[fp.strftime("%Y-%m")] += amt
        fv = d(l.get("date_maturity") or l.get("date"))
        if fp and fv and amt > 0:
            num += amt * (fp - fv).days; den += amt

    return {"filas": filas, "fact_mes": dict(fact_mes), "cobr_mes": dict(cobr_mes),
            "mora_pond": (num / den) if den else None, "corte": hoy.isoformat(),
            "base_url": cfg["url"], "partner_id": pids[0] if pids else 0}


def desde_csv(path):
    hoy = datetime.date.today()
    filas = []
    for r in csv.DictReader(open(path, encoding="utf-8-sig"), delimiter=";"):
        s = float(r["saldo"].replace(",", "."))
        if abs(s) < 1000: continue
        filas.append({"doc": r["documento"], "tipo": "factura" if r["tipo"] == "factura" else "refinanciada",
                      "fecha": r["fecha"], "vence": r["vence"], "dias": int(r["dias_vencido"]),
                      "saldo": s, "aging": r["aging"],
                      "oid": int(r.get("odoo_id") or 0)})
    mens = Path(str(path).replace(".csv", "_mensual.csv"))
    fact, cobr = {}, {}
    if mens.exists():
        for r in csv.DictReader(open(mens, encoding="utf-8-sig"), delimiter=";"):
            fact[r["mes"]] = float(r["facturado"].replace(",", "."))
            cobr[r["mes"]] = float(r["cobrado"].replace(",", "."))
    return {"filas": filas, "fact_mes": fact, "cobr_mes": cobr,
            "mora_pond": None, "corte": hoy.isoformat(),
            "base_url": os.environ.get("ODOO_URL", ""), "partner_id": 0}


# ----------------------------------------------------------------- armado
def armar(raw, ajustes):
    pend = {}
    for p in ajustes.get("pendientes", []):
        for f in p.get("facturas", []):
            pend[f.upper()] = {"ce": p.get("ce", ""), "fecha": p.get("fecha", "")}

    base = (raw.get("base_url") or "").rstrip("/")
    for f in raw["filas"]:
        ref = pend.get(f["doc"].upper())
        f["pagada"] = bool(ref)
        f["ce"] = ref["ce"] if ref else ""
        oid = f.get("oid") or 0
        f["url"] = f"{base}/web#id={oid}&model=account.move&view_type=form" if (base and oid) else ""

    vivas = [f for f in raw["filas"] if not f["pagada"]]
    pagadas = [f for f in raw["filas"] if f["pagada"]]
    fac = [f for f in vivas if f["tipo"] == "factura"]

    ag = defaultdict(float); agn = defaultdict(int)
    for f in fac:
        ag[f["aging"]] += f["saldo"]; agn[f["aging"]] += 1

    emision = defaultdict(lambda: {"saldo": 0.0, "n": 0, "mora": -999})
    for f in fac:
        k = (f["fecha"] or "")[:7]
        e = emision[k]; e["saldo"] += f["saldo"]; e["n"] += 1
        e["mora"] = max(e["mora"], f["dias"])

    t_fac = sum(f["saldo"] for f in fac)
    t_ref = sum(f["saldo"] for f in vivas if f["tipo"] != "factura")
    vencido = sum(v for k, v in ag.items() if k != "Corriente")

    meses = sorted(set(list(raw["fact_mes"].keys()) + list(raw["cobr_mes"].keys())))
    serie = [{"mes": m, "fact": raw["fact_mes"].get(m, 0.0), "cobr": raw["cobr_mes"].get(m, 0.0)}
             for m in meses]
    # DSO sobre los ultimos meses CERRADOS: incluir el mes en curso, que va a
    # medias, hunde la venta diaria y dispara el indicador sin que nada cambie.
    mes_actual = datetime.date.today().strftime("%Y-%m")
    cerrados = [x for x in serie if x["mes"] < mes_actual]
    ult = cerrados[-3:] if len(cerrados) >= 3 else cerrados
    vta_dia = (sum(x["fact"] for x in ult) / (30.44 * len(ult))) if ult else 0
    dso = (t_fac / vta_dia) if vta_dia else 0

    return {
        "corte": raw["corte"],
        "odoo": base,
        "url_cliente": (f"{base}/web#id={raw.get('partner_id')}&model=res.partner&view_type=form"
                        if base and raw.get("partner_id") else ""),
        "total": t_fac + t_ref,
        "facturas": t_fac, "n_facturas": len(fac),
        "refinanciada": t_ref,
        "vencido": vencido,
        "pct_vencido": (vencido / t_fac * 100) if t_fac else 0,
        "vigente": t_fac - vencido,
        "dso": dso,
        "aging": [{"k": b, "v": ag[b], "n": agn[b]} for b in BUCKETS if b in ag],
        "emision": [{"mes": k, **v} for k, v in sorted(emision.items())],
        "serie": serie,
        "pendientes": [{"doc": f["doc"], "ce": f["ce"], "saldo": f["saldo"]} for f in pagadas],
        "total_pendiente": sum(f["saldo"] for f in pagadas),
        "docs": sorted(raw["filas"], key=lambda x: (-x["pagada"], -x["dias"])),
    }


# ----------------------------------------------------------------- HTML
TPL = r"""<title>Cartera Casa Magna</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700&family=Source+Sans+3:wght@400;500;600&display=swap">
<style>
/* Layout: riel de indicadores arriba, barra de antiguedad como control, detalle denso abajo */
:root{
  --ink:#16191c; --ink-2:#565e66; --ink-3:#8b949c;
  --paper:#f6f6f4; --card:#ffffff; --rule:#e2e3df;
  --accent:#1d4e6f; --accent-soft:#e8eff4;
  --ok:#0f7149; --ok-soft:#e6f2ec;
  --warn:#8a6109; --warn-soft:#faf1dd;
  --bad:#a8322a; --bad-soft:#fbeae8;
  --deep:#5a3d78; --deep-soft:#f0ebf6;
  --display:"Archivo",system-ui,sans-serif;
  --body:"Source Sans 3",system-ui,sans-serif;
}
@media (prefers-color-scheme: dark){ :root:not([data-theme="light"]){
  --ink:#eceef0; --ink-2:#a4acb4; --ink-3:#737d86;
  --paper:#131618; --card:#1b1f22; --rule:#2c3236;
  --accent:#78b2d6; --accent-soft:#1a2b36;
  --ok:#5fc396; --ok-soft:#14271f;
  --warn:#dcac4c; --warn-soft:#2a2316;
  --bad:#ef8b80; --bad-soft:#2d1b19;
  --deep:#b296d8; --deep-soft:#241c30;
  color-scheme:dark;
}}
:root[data-theme="dark"]{
  --ink:#eceef0; --ink-2:#a4acb4; --ink-3:#737d86;
  --paper:#131618; --card:#1b1f22; --rule:#2c3236;
  --accent:#78b2d6; --accent-soft:#1a2b36;
  --ok:#5fc396; --ok-soft:#14271f;
  --warn:#dcac4c; --warn-soft:#2a2316;
  --bad:#ef8b80; --bad-soft:#2d1b19;
  --deep:#b296d8; --deep-soft:#241c30;
  color-scheme:dark;
}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--body);
  font-size:15px;line-height:1.5;-webkit-font-smoothing:antialiased}
.wrap{max-width:1140px;margin:0 auto;padding-block:26px 72px;padding-left:18px;padding-right:18px}
.num{font-variant-numeric:tabular-nums}

header{display:flex;justify-content:space-between;align-items:baseline;gap:14px;flex-wrap:wrap;
  border-bottom:2px solid var(--ink);padding-bottom:12px;margin-bottom:22px}
h1{font-family:var(--display);font-weight:700;font-size:clamp(22px,4vw,28px);margin:0;
  letter-spacing:-.025em;text-wrap:balance}
.meta{color:var(--ink-2);font-size:13px}
.meta b{color:var(--ink);font-weight:600}

h2{font-family:var(--display);font-size:11px;font-weight:600;text-transform:uppercase;
  letter-spacing:.11em;color:var(--ink-3);margin:30px 0 11px}

.rail{display:grid;grid-template-columns:repeat(auto-fit,minmax(168px,1fr));gap:10px}
.kpi{background:var(--card);border:1px solid var(--rule);border-radius:4px;padding:14px 15px;min-width:0}
.kpi .lab{font-size:10.5px;text-transform:uppercase;letter-spacing:.08em;color:var(--ink-3);
  font-weight:600;margin-bottom:6px}
.kpi .val{font-family:var(--display);font-size:24px;font-weight:600;letter-spacing:-.02em;
  font-variant-numeric:tabular-nums;line-height:1.1}
.kpi .sub{font-size:12px;color:var(--ink-2);margin-top:4px}
.kpi.k-bad{background:var(--bad-soft);border-color:transparent} .k-bad .val{color:var(--bad)}
.kpi.k-ok{background:var(--ok-soft);border-color:transparent} .k-ok .val{color:var(--ok)}
.kpi.k-warn{background:var(--warn-soft);border-color:transparent} .k-warn .val{color:var(--warn)}

.panel{background:var(--card);border:1px solid var(--rule);border-radius:4px;padding:17px 19px;min-width:0}
.panel.fill{display:flex;flex-direction:column}
.panel.fill .plot{flex:1}
.panel h3{font-family:var(--display);font-size:14px;font-weight:600;margin:0 0 3px;letter-spacing:-.01em}
.panel .hint{font-size:12.5px;color:var(--ink-2);margin:0}

.band{display:flex;height:13px;border-radius:2px;overflow:hidden;margin:15px 0 11px}
.band button{border:0;padding:0;cursor:pointer;transition:opacity .15s;height:100%}
.band button:hover{opacity:.72}
.band button:focus-visible{outline:2px solid var(--ink);outline-offset:2px}
.chips{display:flex;flex-wrap:wrap;gap:7px}
.chip{display:inline-flex;align-items:center;gap:7px;background:transparent;color:var(--ink);
  border:1px solid var(--rule);border-radius:3px;padding:5px 10px;font:inherit;font-size:12.5px;
  cursor:pointer;font-variant-numeric:tabular-nums}
.chip:hover{border-color:var(--ink-3)}
.chip[aria-pressed="true"]{background:var(--ink);color:var(--paper);border-color:var(--ink)}
.swatch{width:9px;height:9px;border-radius:2px;flex:none}

.cols{display:grid;grid-template-columns:1.25fr 1fr;gap:11px}
@media(max-width:880px){.cols{grid-template-columns:1fr}}

.plot{display:flex;align-items:flex-end;gap:7px;min-height:132px;margin-top:14px}
.plot .col{flex:1;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;height:100%;min-width:0}
.plot .pair{width:100%;display:flex;gap:2px;align-items:flex-end;height:100%}
.plot .b{flex:1;border-radius:1px 1px 0 0;min-height:2px}
.plot .b-f{background:var(--accent)} .plot .b-c{background:var(--ok)}
.plot .tick{font-size:10.5px;color:var(--ink-3);margin-top:6px;font-weight:600}
.key{display:flex;gap:15px;margin-top:10px;font-size:12px;color:var(--ink-2)}
.key span{display:inline-flex;align-items:center;gap:6px}

table{width:100%;border-collapse:collapse;font-size:13.5px}
th{text-align:left;font-size:10.5px;text-transform:uppercase;letter-spacing:.07em;color:var(--ink-3);
  font-weight:600;padding:0 10px 8px 0;border-bottom:1px solid var(--rule);white-space:nowrap}
th[data-k]{cursor:pointer;user-select:none}
th[data-k]:hover{color:var(--ink)}
td{padding:8px 10px 8px 0;border-bottom:1px solid var(--rule);font-variant-numeric:tabular-nums}
tbody tr:last-child td{border-bottom:none}
tfoot td{font-weight:600;border-top:2px solid var(--ink);border-bottom:none;padding-top:10px}
.r{text-align:right;white-space:nowrap}
.dt{white-space:nowrap;color:var(--ink-2);font-size:12.5px}
@media(max-width:560px){td,th{padding-right:8px}}
.doc{font-weight:600;letter-spacing:.01em}
a.doc{color:var(--accent);text-decoration:none;border-bottom:1px solid transparent;
  display:inline-flex;align-items:center;gap:5px}
a.doc:hover{border-bottom-color:var(--accent)}
a.doc:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:2px}
a.doc svg{width:11px;height:11px;flex:none;opacity:.55}
a.doc:hover svg{opacity:1}
.odoo{font-size:12.5px;color:var(--accent);text-decoration:none;border-bottom:1px solid currentColor;
  padding-bottom:1px}
.odoo:hover{color:var(--ink)}
.paid{color:var(--ink-3)} .paid .amt{text-decoration:line-through}
.tag{display:inline-block;font-size:10px;font-weight:600;padding:2px 7px;border-radius:2px;
  text-transform:uppercase;letter-spacing:.04em;white-space:nowrap}
.scroll{overflow-x:auto;max-height:450px;overflow-y:auto}
.search{width:100%;padding:9px 12px;border:1px solid var(--rule);border-radius:3px;
  background:var(--card);color:var(--ink);font:inherit;font-size:14px;margin-bottom:10px}
.search:focus{outline:2px solid var(--accent);outline-offset:-1px;border-color:transparent}

.note{border-left:3px solid var(--rule);padding:11px 0 11px 14px;margin-bottom:11px;font-size:13.5px}
.note b{display:block;font-family:var(--display);font-weight:600;margin-bottom:2px;font-size:13.5px}
.note.n-bad{border-color:var(--bad)} .note.n-warn{border-color:var(--warn)} .note.n-ok{border-color:var(--ok)}

footer{margin-top:34px;padding-top:13px;border-top:1px solid var(--rule);
  font-size:11.5px;color:var(--ink-3);line-height:1.6}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.92em}
@media (prefers-reduced-motion: reduce){*{transition:none!important}}
</style>

<div class="wrap">
<header>
  <div>
    <h1>Cartera Casa Magna</h1>
    <div class="meta">VINTRAL S.A.S. &middot; CASAMAGNA S.A.S. NIT 811.031.313-5 &middot; corte <b>__CORTE__</b></div>
  </div>
  <div class="meta">__NDOCS__ facturas abiertas &middot; plazo 60 días__LINKCLIENTE__</div>
</header>

<div class="rail" id="rail"></div>
<div id="aviso"></div>

<h2>Antigüedad</h2>
<div class="panel">
  <h3>Composición por tramo</h3>
  <p class="hint">Días transcurridos desde el vencimiento, no desde la emisión. Toca un tramo para filtrar el detalle.</p>
  <div class="band" id="band"></div>
  <div class="chips" id="chips"></div>
</div>

<h2>Movimiento</h2>
<div class="cols">
  <div class="panel fill">
    <h3>Facturado contra cobrado</h3>
    <p class="hint">Valores brutos con IVA, por mes de registro en Odoo.</p>
    <div class="plot" id="plot"></div>
    <div class="key">
      <span><i class="swatch" style="background:var(--accent)"></i>Facturado</span>
      <span><i class="swatch" style="background:var(--ok)"></i>Cobrado</span>
    </div>
  </div>
  <div class="panel">
    <h3>Saldo por mes de emisión</h3>
    <p class="hint">Dónde está parada la cartera y cuánto lleva esperando el lote más viejo de cada mes.</p>
    <table style="margin-top:13px">
      <thead><tr><th>Emitidas</th><th class="r">Saldo</th><th class="r">Fact.</th><th class="r">Mora máx</th></tr></thead>
      <tbody id="emision"></tbody>
    </table>
  </div>
</div>

<h2>Detalle · <span id="cuenta" style="color:var(--ink);text-transform:none;letter-spacing:0"></span></h2>
<input type="search" id="q" class="search" placeholder="Buscar factura (FE304, RNC…)" aria-label="Buscar documento">
<div class="panel" style="padding:15px 17px">
  <div class="scroll">
    <table>
      <thead><tr>
        <th data-k="doc">Documento</th><th data-k="fecha">Emisión</th><th data-k="vence">Vence</th>
        <th data-k="dias" class="r">Días</th><th data-k="saldo" class="r">Saldo</th><th>Tramo</th>
      </tr></thead>
      <tbody id="filas">__FILAS__</tbody>
      <tfoot><tr><td colspan="4">Total filtrado</td><td class="r" id="suma"></td><td></td></tr></tfoot>
    </table>
  </div>
</div>

<h2>Seguimiento</h2>
<div id="notas"></div>

<footer>
Fuente: Odoo <code>vicomer.odoo.com</code>, extracción vía XML-RPC sobre <code>account.move.line</code> &middot; cifras en COP con IVA &middot; excluidos residuos de conciliación menores a $1.000 &middot; los pagos marcados tienen comprobante de Casa Magna pendiente de registro en Odoo, y sus importes de comprobante van netos de la retención en la fuente del 2,5%.<br>
Cada número de factura abre su asiento en Odoo en una pestaña nueva; requiere sesión iniciada.<br>Generado por <code>cartera_dashboard.py</code>. Actualización automática cada 3 días.
</footer>
</div>

<script>
const D = __DATA__;
const CO = {"Corriente":"var(--ok)","1-30":"var(--accent)","31-60":"var(--warn)",
            "61-90":"var(--deep)","91-180":"var(--deep)",">180":"var(--bad)"};
const SOFT = {"Corriente":"var(--ok-soft)","1-30":"var(--accent-soft)","31-60":"var(--warn-soft)",
              "61-90":"var(--deep-soft)","91-180":"var(--deep-soft)",">180":"var(--bad-soft)"};
const cop = n => (n<0?"-":"") + Math.round(Math.abs(n)).toLocaleString("es-CO");
const mm  = n => "$" + (Math.abs(n)/1e6).toFixed(1).replace(".",",") + " M";
const MES = {"01":"Ene","02":"Feb","03":"Mar","04":"Abr","05":"May","06":"Jun",
             "07":"Jul","08":"Ago","09":"Sep","10":"Oct","11":"Nov","12":"Dic"};
const mesCorto = s => (MES[s.slice(5,7)]||s) + " " + s.slice(2,4);

let sel = new Set(), sk = "dias", sd = -1;



/* --- indicadores --- */
const kpis = [
  {l:"Cartera total", v:mm(D.total), s:cop(D.total)+" COP", c:"k-bad"},
  {l:"Vencido", v:D.pct_vencido.toFixed(1)+"%", s:cop(D.vencido)+" COP", c:"k-bad"},
  {l:"Vigente", v:mm(D.vigente), s:"dentro de plazo", c:"k-ok"},
  {l:"DSO", v:Math.round(D.dso)+" días", s:"contra plazo de 60", c:"k-warn"},
];
if (D.total_pendiente > 0) kpis.push(
  {l:"Pagos por registrar", v:mm(D.total_pendiente), s:D.pendientes.map(p=>p.ce).filter((x,i,a)=>a.indexOf(x)===i).join(" · "), c:"k-ok"});
document.getElementById("rail").innerHTML = kpis.map(k =>
  `<div class="kpi ${k.c}"><div class="lab">${k.l}</div><div class="val">${k.v}</div><div class="sub">${k.s}</div></div>`).join("");

if (D.total_pendiente > 0) {
  const ces = D.pendientes.map(p=>p.ce).filter((x,i,a)=>a.indexOf(x)===i).join(", ");
  document.getElementById("aviso").innerHTML =
    `<div class="note n-ok" style="margin-top:14px"><b>Ajuste aplicado</b>Odoo reporta ${cop(D.total + D.total_pendiente)}.
     Las facturas de ${ces} ya fueron pagadas con comprobante y están pendientes de registro, así que se descuentan:
     la cartera real es <b style="display:inline">${cop(D.total)}</b>. Aparecen tachadas en el detalle.</div>`;
}

/* --- antiguedad --- */
const TF = D.aging.reduce((a,x)=>a+x.v,0);
document.getElementById("band").innerHTML = D.aging.map(a =>
  `<button data-k="${a.k}" style="width:${a.v/TF*100}%;background:${CO[a.k]}"
     title="${a.k}: ${cop(a.v)}" aria-label="Filtrar ${a.k}"></button>`).join("");
document.getElementById("chips").innerHTML = D.aging.map(a =>
  `<button class="chip" data-k="${a.k}" aria-pressed="false">
     <i class="swatch" style="background:${CO[a.k]}"></i>${a.k} · ${cop(a.v)} · ${(a.v/TF*100).toFixed(1)}%</button>`).join("");

/* --- series --- */
const S = D.serie.slice(-7);
const MX = Math.max(...S.flatMap(s=>[s.fact,s.cobr]), 1);
document.getElementById("plot").innerHTML = S.map(s =>
  `<div class="col"><div class="pair">
     <div class="b b-f" style="height:${s.fact/MX*100}%" title="Facturado ${cop(s.fact)}"></div>
     <div class="b b-c" style="height:${s.cobr/MX*100}%" title="Cobrado ${cop(s.cobr)}"></div>
   </div><div class="tick">${mesCorto(s.mes)}</div></div>`).join("");

document.getElementById("emision").innerHTML = D.emision.map(e => {
  const vencida = e.mora > 0;
  return `<tr><td>${mesCorto(e.mes)}</td><td class="r">${cop(e.saldo)}</td><td class="r">${e.n}</td>
    <td class="r">${vencida
      ? `<span class="tag" style="background:${e.mora>60?"var(--bad-soft)":"var(--warn-soft)"};color:${e.mora>60?"var(--bad)":"var(--warn)"}">${e.mora} d</span>`
      : `<span style="color:var(--ink-3)">en plazo</span>`}</td></tr>`;
}).join("");

/* --- tabla: las filas ya vienen en el HTML; aqui solo se filtran y reordenan --- */
const CUERPO = document.getElementById("filas");
const FILAS = Array.from(CUERPO.children);
const valor = (tr, k) => k === "dias" || k === "saldo"
  ? parseFloat(tr.dataset[k]) : (tr.dataset[k] || "");

function pinta(){
  const q = document.getElementById("q").value.trim().toLowerCase();
  const vistas = FILAS.filter(tr => {
    const ok = (!sel.size || sel.has(tr.dataset.aging)) &&
               (!q || tr.dataset.doc.toLowerCase().includes(q));
    tr.hidden = !ok;
    return ok;
  });
  vistas.sort((a,b) => {
    const x = valor(a, sk), y = valor(b, sk);
    return (typeof x === "number" ? x - y : String(x).localeCompare(String(y))) * sd;
  });
  vistas.forEach(tr => CUERPO.appendChild(tr));
  const suma = vistas.reduce((a,tr) => a + (tr.dataset.pagada ? 0 : parseFloat(tr.dataset.saldo)), 0);
  document.getElementById("suma").textContent = cop(suma);
  document.getElementById("cuenta").textContent =
    vistas.length + " documentos" + (sel.size ? " · " + [...sel].join(", ") : "");
  document.querySelectorAll(".chip").forEach(b =>
    b.setAttribute("aria-pressed", sel.has(b.dataset.k) ? "true" : "false"));
}
function alterna(k){ sel.has(k) ? sel.delete(k) : sel.add(k); pinta(); }
document.querySelectorAll("#band button, .chip").forEach(e => e.onclick = () => alterna(e.dataset.k));
document.getElementById("q").oninput = pinta;
document.querySelectorAll("th[data-k]").forEach(th => th.onclick = () => {
  const k = th.dataset.k; sd = (sk===k) ? -sd : -1; sk = k; pinta(); });

/* --- notas --- */
document.getElementById("notas").innerHTML = (D.notas||[]).map(n =>
  `<div class="note n-${n.t}"><b>${n.h}</b>${n.b}</div>`).join("");

pinta();
</script>
"""


FLECHA = ('<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" '
          'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
          '<path d="M6 3h7v7M13 3 5 11M11 9v4H3V5h4"/></svg>')

CO_JS = {"Corriente": "ok", "1-30": "accent", "31-60": "warn",
         "61-90": "deep", "91-180": "deep", ">180": "bad"}


def esc(t):
    return (str(t or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def pesos(n):
    return ("-" if n < 0 else "") + f"{abs(round(n)):,}".replace(",", ".")


def fila_html(r):
    """Una <tr> completa. El enlace a Odoo se escribe aqui, no en el navegador."""
    c = CO_JS.get(r["aging"], "accent")
    doc = esc(r["doc"])
    if r.get("url"):
        celda = (f'<a class="doc" href="{esc(r["url"])}" target="_blank" rel="noopener" '
                 f'title="Abrir {doc} en Odoo">{doc}{FLECHA}</a>')
    else:
        celda = f'<span class="doc">{doc}</span>'
    if r["pagada"]:
        celda += (f' <span class="tag" style="background:var(--ok-soft);color:var(--ok)">'
                  f'{esc(r["ce"])}</span>')
    mora = (f'<td class="r" style="color:var(--bad);font-weight:600">{r["dias"]}</td>'
            if r["dias"] > 0 and not r["pagada"]
            else f'<td class="r" style="color:var(--ink-3)">{r["dias"] if r["dias"] > 0 else "&mdash;"}</td>')
    return (
        f'<tr class="{"paid" if r["pagada"] else ""}" data-doc="{doc}" data-aging="{esc(r["aging"])}" '
        f'data-dias="{r["dias"]}" data-saldo="{r["saldo"]:.2f}" '
        f'data-fecha="{esc(r["fecha"])}" data-vence="{esc(r["vence"])}" '
        f'{"data-pagada=1" if r["pagada"] else ""}>'
        f'<td>{celda}</td>'
        f'<td class="dt">{esc(r["fecha"])}</td><td class="dt">{esc(r["vence"])}</td>'
        f'{mora}'
        f'<td class="r amt">{pesos(r["saldo"])}</td>'
        f'<td><span class="tag" style="background:var(--{c}-soft);color:var(--{c})">'
        f'{esc(r["aging"])}</span></td></tr>')



def notas(dd):
    out = []
    fac = [x for x in dd["docs"] if x["tipo"] == "factura" and not x["pagada"]]
    viejas = sorted([f for f in fac if f["dias"] > 60], key=lambda x: -x["dias"])
    if viejas:
        tot = sum(f["saldo"] for f in viejas)
        out.append({"t": "bad", "h": f"Lote más viejo: {len(viejas)} facturas por {int(tot):,}".replace(",", ".") + " COP",
                    "b": f"La más antigua es {viejas[0]['doc']} con {viejas[0]['dias']} días de mora. "
                         "Son las que rompen la regla de los 90 días: hay que cerrarlas antes de mirar cualquier otra cosa."})
    if dd["pct_vencido"] > 55:
        out.append({"t": "warn", "h": f"El vencido sigue en {dd['pct_vencido']:.1f}%",
                    "b": "El monto baja, la proporción no. Mientras el DSO siga por encima de 107 días, "
                         "la cartera vuelve a subir en cuanto la facturación se normalice."})
    out.append({"t": "warn", "h": "La garantía no cubre la exposición",
                "b": "Pagaré por $100.000.000 sobre la cartera actual, con la carta de instrucciones "
                     "a nombre de VICOMER cuando el título es de VINTRAL. Pendiente desde julio."})
    return out


def main():
    ap = argparse.ArgumentParser(description="Dashboard de cartera Casa Magna")
    ap.add_argument("--cliente", default="casa magna")
    ap.add_argument("--meses", type=int, default=18)
    ap.add_argument("--from-csv", default="")
    ap.add_argument("--out", default="cartera_dashboard.html")
    args = ap.parse_args()

    raw = desde_csv(args.from_csv) if args.from_csv else extraer(args)

    aj_path = OUT_DIR / "cartera_ajustes.json"
    ajustes = {}
    if aj_path.exists():
        try:
            ajustes = json.loads(aj_path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[WARN] cartera_ajustes.json: {e}")

    dd = armar(raw, ajustes)
    dd["notas"] = notas(dd)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.date.today().strftime("%Y%m%d")

    (OUT_DIR / "cartera_dashboard.json").write_text(
        json.dumps(dd, ensure_ascii=False, indent=2), encoding="utf-8")

    filas_html = "".join(fila_html(r) for r in dd["docs"])
    link_cli = (f' &middot; <a class="odoo" href="{esc(dd["url_cliente"])}" target="_blank" '
                f'rel="noopener">Ver cliente en Odoo</a>') if dd.get("url_cliente") else ""

    # el detalle ya viaja como HTML; no hace falta duplicarlo en el JSON de la pagina
    liviano = {k: v for k, v in dd.items() if k != "docs"}
    html = (TPL.replace("__DATA__", json.dumps(liviano, ensure_ascii=False, separators=(",", ":")))
               .replace("__FILAS__", filas_html)
               .replace("__LINKCLIENTE__", link_cli)
               .replace("__CORTE__", dd["corte"])
               .replace("__NDOCS__", str(dd["n_facturas"])))
    out = OUT_DIR / args.out
    out.write_text(html, encoding="utf-8")

    cpath = OUT_DIR / f"cartera_real_casa_magna_{stamp}.csv"
    with open(cpath, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["documento", "tipo", "fecha", "vence", "dias_vencido", "saldo", "aging", "pagada", "ce", "odoo_id"])
        for r in dd["docs"]:
            w.writerow([r["doc"], r["tipo"], r["fecha"], r["vence"], r["dias"],
                        f"{r['saldo']:.2f}".replace(".", ","), r["aging"],
                        "si" if r["pagada"] else "", r["ce"], r.get("oid") or ""])

    print(f"\nCartera total   {dd['total']:>16,.0f}")
    print(f"Vencido         {dd['vencido']:>16,.0f}  ({dd['pct_vencido']:.1f}%)")
    print(f"DSO             {dd['dso']:>16.0f} dias")
    if dd["total_pendiente"]:
        print(f"Por registrar   {dd['total_pendiente']:>16,.0f}")
    print(f"\nGuardado:\n  {out}\n  {OUT_DIR/'cartera_dashboard.json'}\n  {cpath}")


if __name__ == "__main__":
    main()
