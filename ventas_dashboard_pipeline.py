#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ventas_dashboard_pipeline.py
============================
Lo que corre el LaunchAgent com.vcomer.dashboard.ventas todos los dias a las 07:30.

    1) ventas_dashboard.py <anio>        -> OdooVentas/dashboard_ventas.json
    2) ventas_dashboard_render.py        -> los 4 HTML autocontenidos

Degradacion elegante: si la extraccion falla (Mac dormida, sin red, Odoo caido),
NO se toca el JSON bueno del dia anterior y se vuelve a renderizar con el, dejando
el aviso de antiguedad. Nunca se escribe un JSON vacio encima de uno con datos
(eso es lo que le pasa hoy a estado_grupo.json cuando el agente corre sin red).

Uso:  python3 ventas_dashboard_pipeline.py [anio]
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
    p = subprocess.run(cmd, cwd=str(PROJ), capture_output=True, text=True, env=dict(os.environ))
    if p.stdout:
        print(p.stdout, flush=True)
    if p.returncode != 0:
        log("[FALLO] %s devolvio %d" % (script, p.returncode))
        if p.stderr:
            print(p.stderr[-4000:], flush=True)
    return p.returncode == 0


def exportar_files_dir():
    """Deja PERSEO_FILES_DIR apuntando a donde de verdad viven los libros de presupuesto.

    ventas_dashboard.py detecta esa carpeta buscando el libro Regional por patron y la
    guarda en odoo_config.json. Sin esto, estado_grupo.py y perseo_presupuesto.py siguen
    mirando la ruta vieja y devuelven un presupuesto vacio en silencio, que es lo que
    paso cuando el Escritorio se reorganizo en "01 EMPRESAS/".
    """
    try:
        c = json.loads((PROJ / "odoo_config.json").read_text(encoding="utf-8"))
        fd = c.get("files_dir")
        if fd and Path(fd).exists():
            os.environ["PERSEO_FILES_DIR"] = fd
            log("PERSEO_FILES_DIR -> %s" % fd)
            return fd
    except Exception:
        pass
    return None


def main():
    anio = sys.argv[1] if len(sys.argv) > 1 else str(datetime.date.today().year)
    exportar_files_dir()
    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / "dashboard_ventas.json"
    antes = None
    if dest.exists():
        try:
            antes = json.loads(dest.read_text(encoding="utf-8")).get("generado")
        except Exception:
            pass

    ok = corre("ventas_dashboard.py", [anio])

    # ventas_dashboard.py pudo haber DESCUBIERTO la carpeta de los libros en esta corrida.
    # Si asi fue y el presupuesto no estaba, se regenera estado_grupo.py con la ruta buena
    # y se vuelve a extraer: asi una mudanza de carpetas se arregla sola en un ciclo.
    fd_antes = os.environ.get("PERSEO_FILES_DIR")
    fd_ahora = exportar_files_dir()
    if ok and fd_ahora and fd_ahora != fd_antes:
        log("[AUTO] Se detectó la carpeta de los libros de presupuesto; regenerando estado_grupo y re-extrayendo.")
        corre("estado_grupo.py", [anio])
        ok = corre("ventas_dashboard.py", [anio])

    if not ok:
        if dest.exists():
            log("[DEGRADADO] La extraccion fallo. Se conserva el JSON del %s y se vuelve a "
                "renderizar con el; el dashboard mostrara su fecha real, no la de hoy." % antes)
        else:
            log("[ERROR] La extraccion fallo y no hay JSON previo: no hay nada que renderizar.")
            return 1

    if not corre("ventas_dashboard_render.py", []):
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
    except Exception:
        pass
    return 0 if ok else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        log("[ERROR]\n" + traceback.format_exc())
        sys.exit(1)
