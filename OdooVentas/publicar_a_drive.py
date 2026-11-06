#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
publicar_a_drive.py — Puente Mac -> Google Drive para el Dashboard de Ventas VICOMER.

QUE HACE
    Copia los artefactos que produjo ventas_dashboard_pipeline.py desde
    ~/Claude/Projects/CFO VICOMER/OdooVentas/ hacia la carpeta local que
    Google Drive para escritorio sincroniza. Drive sube los archivos solo.

    A partir de ahi, la lectura CFO de las 08:17 (tarea programada en la nube)
    puede leer el JSON aunque el Mac este cerrado, y la alerta llega al telefono.

POR QUE ASI
    Sin credenciales OAuth, sin API, sin dependencias externas. Solo copia de
    archivos. Si Google Drive para escritorio esta corriendo, el sync es
    automatico y toma segundos.

COMO SE INVOCA
    Al final de ventas_dashboard_pipeline.py, agregar:

        import subprocess, sys
        from pathlib import Path
        subprocess.run([sys.executable,
                        str(Path(__file__).with_name("publicar_a_drive.py"))],
                       check=False)

    O manualmente para probar:  python3 publicar_a_drive.py

SALIDA
    Codigo 0 = todo publicado.  Codigo 1 = no se encontro la carpeta de Drive.
    Codigo 2 = no se encontro el JSON de origen (el pipeline no corrio).
    Log en OdooVentas/drive_publish.log
"""

import glob
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional  # compatibilidad con el Python 3.9 de macOS

# ---------------------------------------------------------------- configuracion

ORIGEN = Path.home() / "Claude" / "Projects" / "CFO VICOMER" / "OdooVentas"

# Subcarpeta dentro de Drive donde aterrizan los archivos.
DESTINO_RELATIVO = Path("VICOMER") / "OdooVentas"

# El JSON es obligatorio: sin el, la lectura CFO no tiene nada que analizar.
ARCHIVO_CRITICO = "dashboard_ventas.json"

ARCHIVOS_OPCIONALES = [
    "Dashboard_Ventas_Consolidado_Grupo.html",
    "Dashboard_Ventas_Ecuador.html",
    "Dashboard_Ventas_Colombia.html",
    "Dashboard_Ventas_CostaRica.html",
    "dashboard_run.log",
    "dashboard_error.log",
]

LOG = ORIGEN / "drive_publish.log"


# ---------------------------------------------------------------- utilidades

def log(msg: str) -> None:
    linea = f"{datetime.now().isoformat(timespec='seconds')}  {msg}"
    print(linea)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(linea + "\n")
    except OSError:
        pass  # el log nunca debe tumbar la publicacion


def encontrar_carpeta_drive() -> Optional[Path]:
    """Ubica la raiz sincronizada de Google Drive para escritorio en macOS.

    Cubre el layout moderno (CloudStorage, Drive v60+), el legacy, y ambos
    idiomas de la unidad personal ('Mi unidad' / 'My Drive').
    """
    patrones = [
        "~/Library/CloudStorage/GoogleDrive-*/Mi unidad",
        "~/Library/CloudStorage/GoogleDrive-*/My Drive",
        "~/Google Drive/Mi unidad",
        "~/Google Drive/My Drive",
        "~/Google Drive",
    ]
    for patron in patrones:
        for hit in sorted(glob.glob(os.path.expanduser(patron))):
            ruta = Path(hit)
            if ruta.is_dir():
                return ruta
    return None


def copiar(origen: Path, destino_dir: Path) -> bool:
    """Copia preservando mtime. Devuelve True si copio algo."""
    if not origen.exists():
        return False
    destino = destino_dir / origen.name
    tmp = destino_dir / f".{origen.name}.tmp"
    # Copia a temporal y rename: Drive nunca ve un archivo a medio escribir.
    shutil.copy2(origen, tmp)
    os.replace(tmp, destino)
    return True


# ---------------------------------------------------------------- principal

def main() -> int:
    log("=" * 60)
    log("Publicacion a Drive — inicio")

    if not ORIGEN.is_dir():
        log(f"ERROR: no existe la carpeta de origen {ORIGEN}")
        return 2

    json_origen = ORIGEN / ARCHIVO_CRITICO
    if not json_origen.exists():
        log(f"ERROR: no existe {json_origen}. El pipeline de las 07:30 no dejo dato.")
        return 2

    # Frescura del dato de origen: se registra, no se bloquea.
    try:
        datos = json.loads(json_origen.read_text(encoding="utf-8"))
        generado = str(datos.get("generado_fecha", "(ausente)"))
    except (json.JSONDecodeError, OSError) as exc:
        log(f"AVISO: no se pudo leer generado_fecha ({exc}). Se publica igual.")
        generado = "(ilegible)"

    hoy = datetime.now().strftime("%Y-%m-%d")
    if not generado.startswith(hoy):
        log(f"AVISO: generado_fecha={generado} NO es de hoy ({hoy}). "
            "Se publica igual; la lectura CFO lo reportara como dato viejo.")
    else:
        log(f"OK: dato fresco, generado_fecha={generado}")

    raiz_drive = encontrar_carpeta_drive()
    if raiz_drive is None:
        log("ERROR: no se encontro la carpeta de Google Drive para escritorio. "
            "Verifica que la app este instalada y con sesion iniciada.")
        return 1
    log(f"Drive detectado en: {raiz_drive}")

    destino_dir = raiz_drive / DESTINO_RELATIVO
    destino_dir.mkdir(parents=True, exist_ok=True)

    copiados, faltantes = [], []

    if copiar(json_origen, destino_dir):
        copiados.append(ARCHIVO_CRITICO)
    else:
        log(f"ERROR: fallo la copia de {ARCHIVO_CRITICO}")
        return 2

    for nombre in ARCHIVOS_OPCIONALES:
        if copiar(ORIGEN / nombre, destino_dir):
            copiados.append(nombre)
        else:
            faltantes.append(nombre)

    # Sello de publicacion: le permite a la lectura CFO distinguir
    # "el pipeline no corrio" de "el pipeline corrio pero Drive no sincronizo".
    sello = {
        "publicado_en": datetime.now().isoformat(timespec="seconds"),
        "generado_fecha_del_json": generado,
        "archivos_publicados": copiados,
        "archivos_ausentes": faltantes,
        "origen": str(ORIGEN),
        "destino": str(destino_dir),
    }
    (destino_dir / "publicacion_sello.json").write_text(
        json.dumps(sello, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    log(f"Publicados {len(copiados)}: {', '.join(copiados)}")
    if faltantes:
        log(f"Ausentes en origen (no es error si no se generan): {', '.join(faltantes)}")
    log(f"Destino: {destino_dir}")
    log("Publicacion a Drive — fin OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # nunca tumbar el pipeline por esto
        log(f"ERROR no controlado: {type(exc).__name__}: {exc}")
        sys.exit(3)
