#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compras_dashboard_pipeline.py
=============================
Lo que corre el LaunchAgent com.vcomer.dashboard.compras todos los dias a las 07:45
(despues del de ventas, antes de la jornada).

    1) compras_dashboard.py <anio>     -> OdooVentas/dashboard_compras.json
    2) compras_dashboard_render.py     -> los HTML autocontenidos

Degradacion elegante: si la extraccion falla (Mac dormida, sin red, Odoo caido), NO se
toca el JSON bueno del dia anterior y se vuelve a renderizar con el. Nunca se escribe
un JSON vacio encima de uno con datos.

Uso:  python3 compras_dashboard_pipeline.py [anio]
"""
import os, sys, json, subprocess, datetime, traceback
from pathlib import Path

HOME = Path.home()
PROJ = Path(os.environ.get("VICOMER_PROJ", HOME / "Claude" / "Projects" / "CFO VICOMER"))
OUT = PROJ / "OdooVentas"
PY = sys.executable or "/usr/bin/python3"


def log(m):
    print("[%s] %s" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), m), flush=True)


def corre(script, args):
    cmd = [PY, str(PROJ / script)] + [str(a) for a in args]
    log("$ " + " ".join(cmd))
    p = subprocess.run(cmd, cwd=str(PROJ), capture_output=True, text=True)
    if p.stdout:
        print(p.stdout, flush=True)
    if p.returncode != 0:
        log("[FALLO] %s devolvio %d" % (script, p.returncode))
        if p.stderr:
            print(p.stderr[-4000:], flush=True)
    return p.returncode == 0


def main():
    anio = sys.argv[1] if len(sys.argv) > 1 else str(datetime.date.today().year)
    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / "dashboard_compras.json"
    antes = None
    if dest.exists():
        try:
            antes = json.loads(dest.read_text(encoding="utf-8")).get("generado")
        except Exception:
            pass

    ok = corre("compras_dashboard.py", [anio])
    if not ok:
        if dest.exists():
            log("[DEGRADADO] La extraccion fallo. Se conserva el JSON del %s y se vuelve a renderizar con el; "
                "el dashboard mostrara su fecha real, no la de hoy." % antes)
        else:
            log("[ERROR] La extraccion fallo y no hay JSON previo: no hay nada que renderizar.")
            return 1

    if not corre("compras_dashboard_render.py", []):
        return 1

    try:
        d = json.loads(dest.read_text(encoding="utf-8"))
        av = d.get("avisos") or []
        crit = [a for a in av if a.get("nivel") == "critico"]
        log("Datos del %s | avisos: %d (%d criticos) | conciliacion: %s"
            % (d.get("generado"), len(av), len(crit),
               "CUADRA" if (d.get("conciliacion") or {}).get("todo_cuadra") else "CON DIFERENCIAS"))
        for a in crit:
            log("   [CRITICO] %s/%s: %s" % (a.get("pais") or "GRUPO", a.get("bloque"), a.get("texto")))
        c = d.get("consolidado") or {}
        log("Grupo (USD ref.): compra %s | CxP %s (%s vencido) | pagos %s | vence en 7 dias %s"
            % ("{:,.0f}".format(c.get("compra_ytd") or 0), "{:,.0f}".format(c.get("cxp_total") or 0),
               "{:.0%}".format(c.get("pct_vencido") or 0), "{:,.0f}".format(c.get("pagos_ytd") or 0),
               "{:,.0f}".format(c.get("a_pagar_7_dias") or 0)))
    except Exception:
        pass
    return 0 if ok else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        log("[ERROR]\n" + traceback.format_exc())
        sys.exit(1)
