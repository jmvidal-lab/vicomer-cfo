#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
casamagna_pipeline.py — orquestador del análisis Casa Magna (corre semanal).

Pasos:
  1) SELL IN  : casamagna_sellin.run_extract()      (Odoo XML-RPC, 2 instancias)
  2) SELL OUT : casamagna_sellout.fetch_sellout()   (Gmail IMAP, reportes NetSuite)
  3) BUILD    : casamagna_build.main()              (dashboard + zip + correo)

Cada extractor va en try/except: si uno falla (p. ej. sin API key aún), se registra
y se sigue; el build usa lo último disponible.

USO:
    python3 casamagna_pipeline.py            # todo + envía correo
    python3 casamagna_pipeline.py --no-mail  # todo menos el correo
"""
import sys, datetime, traceback

def log(m): print(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {m}", flush=True)

def main():
    no_mail = "--no-mail" in sys.argv
    log("== PIPELINE CASA MAGNA ==")

    try:
        import casamagna_sellin
        log("SELL IN (Odoo)…"); casamagna_sellin.run_extract()
    except Exception:
        log("[ERROR] sell in falló:\n" + traceback.format_exc())

    try:
        import casamagna_sellout
        log("SELL OUT (Gmail IMAP)…"); casamagna_sellout.fetch_sellout()
    except Exception:
        log("[ERROR] sell out falló:\n" + traceback.format_exc())

    try:
        import casamagna_build
        log("BUILD dashboard + correo…"); casamagna_build.main(no_mail=no_mail)
    except Exception:
        log("[ERROR] build/correo falló:\n" + traceback.format_exc())
        sys.exit(1)

    log("== FIN ==")

if __name__ == "__main__":
    main()
