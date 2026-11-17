#!/usr/bin/env python3
"""meta_ads.py — conexión de SOLO LECTURA a Meta (Facebook + Instagram Ads).

Usa la Graph API / Marketing API con un token de System User del Business
Manager (permiso ads_read). Igual que Odoo: este script NUNCA crea, edita ni
pausa nada. Solo hace GET; cualquier otro método se rechaza en código.

Variables (environment de la nube o ~/.meta_token en el Mac):
  META_ACCESS_TOKEN     token de System User (obligatorio)
  META_AD_ACCOUNT_IDS   cuentas a leer, separadas por coma: act_123,act_456
                        (opcional: si falta, usa todas las que el token ve)
  META_APP_SECRET       opcional: firma appsecret_proof (recomendado)
  META_API_VERSION      opcional, por defecto v24.0
  META_OUT_DIR          opcional, por defecto ./Meta

Uso:
  python3 meta_ads.py check                         # token, permisos y cuentas visibles
  python3 meta_ads.py insights                      # campañas, últimos 30 días
  python3 meta_ads.py insights --dias 7 --nivel adset --resultado compras
  python3 meta_ads.py insights --desde 2026-10-01 --hasta 2026-10-31

Salida de `insights`: Meta/meta_insights_<cuenta>_<desde>_<hasta>.json (crudo +
normalizado) y un .csv con los encabezados que lee el artefacto
"Copiloto de Pauta Meta" (paso 2).
"""
import argparse, csv, datetime as dt, hashlib, hmac, json, os, sys, time
import urllib.error, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
API = os.environ.get("META_API_VERSION", "v24.0")
BASE = f"https://graph.facebook.com/{API}"
OUT = Path(os.environ.get("META_OUT_DIR", ROOT / "Meta"))

# Tipos de acción de Meta → "resultado" del negocio.
ACCIONES = {
    "conversaciones": ["onsite_conversion.messaging_conversation_started_7d"],
    "leads": ["lead", "onsite_conversion.lead_grouped", "offsite_conversion.fb_pixel_lead"],
    "compras": ["purchase", "omni_purchase", "offsite_conversion.fb_pixel_purchase",
                "onsite_web_purchase"],
}
CAMPOS = ["account_id", "account_name", "account_currency", "campaign_id", "campaign_name",
          "adset_id", "adset_name", "ad_id", "ad_name", "objective",
          "spend", "impressions", "reach", "frequency", "inline_link_clicks", "cpm", "ctr",
          "actions", "action_values", "date_start", "date_stop"]


# ── credenciales ────────────────────────────────────────────────────
def token():
    t = os.environ.get("META_ACCESS_TOKEN")
    if not t:
        f = Path.home() / ".meta_token"
        t = f.read_text().strip() if f.exists() else None
    if not t:
        sys.exit("✘ Falta META_ACCESS_TOKEN en el environment (o ~/.meta_token en el Mac).")
    return t


def _proof(tok):
    sec = os.environ.get("META_APP_SECRET")
    return hmac.new(sec.encode(), tok.encode(), hashlib.sha256).hexdigest() if sec else None


# ── cliente GET-only ───────────────────────────────────────────────
class MetaError(Exception):
    pass


def get(path_or_url, params=None, _intentos=4):
    """GET a la Graph API. El token va en el header, nunca en la URL ni en logs."""
    tok = token()
    if path_or_url.startswith("https://"):
        url = path_or_url  # paging.next ya trae sus parámetros
        # quitar access_token si Meta lo incluyó en el cursor
        p = urllib.parse.urlsplit(url)
        q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query) if k != "access_token"]
        url = urllib.parse.urlunsplit(p._replace(query=urllib.parse.urlencode(q)))
    else:
        params = dict(params or {})
        pr = _proof(tok)
        if pr:
            params["appsecret_proof"] = pr
        url = f"{BASE}/{path_or_url.lstrip('/')}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, method="GET",
                                 headers={"Authorization": f"Bearer {tok}"})
    assert req.get_method() == "GET"  # solo lectura, siempre
    for i in range(_intentos):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            try:
                err = json.loads(e.read().decode()).get("error", {})
            except Exception:
                err = {"message": f"HTTP {e.code}"}
            code = err.get("code")
            # 4/17/32/613/80004: límites de uso → esperar y reintentar
            if code in (4, 17, 32, 613, 80000, 80004) and i < _intentos - 1:
                time.sleep(30 * (i + 1)); continue
            raise MetaError(f"[{code}] {err.get('type','')}: {err.get('message','')}"[:300])
        except urllib.error.URLError as e:
            if i < _intentos - 1:
                time.sleep(5 * (i + 1)); continue
            raise MetaError(f"Red: {e.reason}")


def paginar(path, params):
    d = get(path, params)
    while True:
        yield from d.get("data", [])
        nxt = d.get("paging", {}).get("next")
        if not nxt:
            break
        d = get(nxt)


# ── comandos ───────────────────────────────────────────────────────
def cuentas():
    ids = [x.strip() for x in os.environ.get("META_AD_ACCOUNT_IDS", "").split(",") if x.strip()]
    campos = "account_id,name,currency,account_status,timezone_name,business{name}"
    if ids:
        return [get(i if i.startswith("act_") else f"act_{i}", {"fields": campos}) for i in ids]
    return list(paginar("me/adaccounts", {"fields": campos, "limit": 100}))


ESTADO = {1: "activa", 2: "deshabilitada", 3: "sin pago", 7: "en revisión", 9: "en gracia",
          100: "cierre pendiente", 101: "cerrada"}


def cmd_check(_):
    me = get("me", {"fields": "id,name"})
    print(f"✔ Token válido · identidad: {me.get('name')} (id {me.get('id')})")
    try:
        perms = [p["permission"] for p in get("me/permissions").get("data", [])
                 if p.get("status") == "granted"]
        print("  Permisos:", ", ".join(perms) or "(no listados para este tipo de token)")
        if "ads_management" in perms:
            print("  ⚠ El token tiene ads_management (escritura). Para este conector basta ads_read.")
    except MetaError:
        print("  · Permisos: no consultables con este tipo de token")
    cs = cuentas()
    if not cs:
        print("✘ El token no ve ninguna cuenta publicitaria. Asígnalas al System User en el Business Manager.")
        return 1
    print(f"✔ {len(cs)} cuenta(s) publicitaria(s):")
    for c in cs:
        print(f"  · {c.get('id')}  {c.get('name')}  [{c.get('currency')}]  "
              f"{ESTADO.get(c.get('account_status'), c.get('account_status'))}  "
              f"{(c.get('business') or {}).get('name','')}")
    return 0


def _suma(lista, tipos):
    tot = 0.0
    for a in lista or []:
        if a.get("action_type") in tipos:
            tot += float(a.get("value") or 0)
    return tot


def normalizar(row, resultado):
    acts, vals = row.get("actions"), row.get("action_values")
    n = {
        "conversaciones": _suma(acts, ACCIONES["conversaciones"]),
        "leads": _suma(acts, ACCIONES["leads"]),
        # Meta repite la compra en varios action_type; se toma el mayor, no la suma
        "compras": max([_suma(acts, [t]) for t in ACCIONES["compras"]] or [0]),
        "valor_compras": max([_suma(vals, [t]) for t in ACCIONES["compras"]] or [0]),
    }
    nombre = row.get("ad_name") or row.get("adset_name") or row.get("campaign_name")
    return {
        "nombre": nombre, "campana": row.get("campaign_name"), "objetivo": row.get("objective"),
        "gasto": float(row.get("spend") or 0), "impresiones": int(row.get("impressions") or 0),
        "alcance": int(row.get("reach") or 0), "frecuencia": float(row.get("frequency") or 0),
        "clics_enlace": int(row.get("inline_link_clicks") or 0),
        "resultados": n[resultado], **n,
        "desde": row.get("date_start"), "hasta": row.get("date_stop"),
    }


def cmd_insights(a):
    hoy = dt.date.today()
    hasta = dt.date.fromisoformat(a.hasta) if a.hasta else hoy - dt.timedelta(days=1)
    desde = dt.date.fromisoformat(a.desde) if a.desde else hasta - dt.timedelta(days=a.dias - 1)
    OUT.mkdir(parents=True, exist_ok=True)
    params = {
        "level": a.nivel, "fields": ",".join(CAMPOS), "limit": 200,
        "time_range": json.dumps({"since": desde.isoformat(), "until": hasta.isoformat()}),
        "action_attribution_windows": json.dumps(["7d_click", "1d_view"]),
    }
    rc = 0
    for c in cuentas():
        cid = c["id"]
        try:
            crudo = list(paginar(f"{cid}/insights", params))
        except MetaError as e:
            print(f"✘ {cid} {c.get('name')}: {e}"); rc = 1; continue
        filas = [normalizar(r, a.resultado) for r in crudo]
        filas.sort(key=lambda r: -r["gasto"])
        base = OUT / f"meta_insights_{cid}_{desde}_{hasta}"
        meta = {"cuenta": cid, "nombre": c.get("name"), "moneda": c.get("currency"),
                "desde": str(desde), "hasta": str(hasta), "nivel": a.nivel,
                "resultado": a.resultado, "atribucion": "7d_click + 1d_view",
                "generado": dt.datetime.now().isoformat(timespec="seconds"),
                "fuente": f"Meta Marketing API {API} (solo lectura)"}
        base.with_suffix(".json").write_text(json.dumps({"meta": meta, "filas": filas, "crudo": crudo},
                                                        ensure_ascii=False, indent=1), encoding="utf-8")
        with base.with_suffix(".csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Nombre de la campaña", f"Importe gastado ({c.get('currency')})", "Impresiones",
                        "Alcance", "Frecuencia", "Clics en el enlace", "Resultados",
                        "Valor de conversión de compras", "Conversaciones", "Leads", "Compras"])
            for r in filas:
                w.writerow([r["nombre"], f"{r['gasto']:.2f}", r["impresiones"], r["alcance"],
                            f"{r['frecuencia']:.2f}", r["clics_enlace"], f"{r['resultados']:.0f}",
                            f"{r['valor_compras']:.2f}", f"{r['conversaciones']:.0f}",
                            f"{r['leads']:.0f}", f"{r['compras']:.0f}"])
        g = sum(r["gasto"] for r in filas); res = sum(r["resultados"] for r in filas)
        print(f"✔ {cid} {c.get('name')} [{c.get('currency')}] {desde}→{hasta}: "
              f"{len(filas)} filas · gasto {g:,.2f} · {a.resultado} {res:,.0f}"
              + (f" · costo/{a.resultado[:-1] if a.resultado != 'compras' else 'compra'} {g/res:,.2f}" if res else ""))
        print(f"  → {base.with_suffix('.csv').relative_to(ROOT) if base.is_relative_to(ROOT) else base.with_suffix('.csv')}")
    return rc


def main():
    ap = argparse.ArgumentParser(description="Meta Ads — solo lectura")
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("check")
    i = sp.add_parser("insights")
    i.add_argument("--dias", type=int, default=30)
    i.add_argument("--desde"); i.add_argument("--hasta")
    i.add_argument("--nivel", choices=["campaign", "adset", "ad"], default="campaign")
    i.add_argument("--resultado", choices=list(ACCIONES), default="conversaciones")
    a = ap.parse_args()
    try:
        return {"check": cmd_check, "insights": cmd_insights}[a.cmd](a)
    except MetaError as e:
        print(f"✘ Meta: {e}")
        if "[190]" in str(e):
            print("  Token inválido o vencido: genera uno nuevo del System User y actualiza META_ACCESS_TOKEN.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
