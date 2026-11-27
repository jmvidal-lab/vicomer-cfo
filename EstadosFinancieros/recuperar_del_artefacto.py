#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
recuperar_del_artefacto.py · reconstruye src/eeff_template.html y datos/eeff_<corte>.json
a partir del HTML del tablero publicado (Artifact action "read").

El tablero publicado ES la plantilla con los datos inyectados entre /*__DATOS__*/ y
/*__FIN__*/. Por eso es la fuente mas confiable del "corte anterior": es exactamente lo
que se publico y paso las 37 comprobaciones. build.py vuelve a reemplazar ese bloque.

Uso: python3 recuperar_del_artefacto.py <artefacto.html>
Escribe src/eeff_template.html y datos/eeff_<AAAA-MM-DD>.json (fecha = meta.corte_iso).
"""
import json, re, sys
from pathlib import Path

h = Path(sys.argv[1]).read_text(encoding="utf-8")
i = h.find("<title>")
if i < 0:
    sys.exit("no encuentro <title>: no parece el tablero")
h = h[i:]
fin = h.rfind("</body>")
if fin >= 0:
    h = h[:fin]
h = h.rstrip("\n") + "\n"
m = re.search(r"/\*__DATOS__\*/(.*?)/\*__FIN__\*/", h, re.S)
if not m:
    sys.exit("el HTML perdio el marcador /*__DATOS__*/ ... /*__FIN__*/")
datos = json.loads(m.group(1))
corte = datos["meta"]["corte_iso"]
Path("src").mkdir(exist_ok=True); Path("datos").mkdir(exist_ok=True)
Path("src/eeff_template.html").write_text(h, encoding="utf-8")
out = Path("datos/eeff_%s.json" % corte)
out.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
print("plantilla: src/eeff_template.html  ·  corte anterior: %s" % out)
