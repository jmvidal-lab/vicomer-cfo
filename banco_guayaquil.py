#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
banco_guayaquil.py
==================
Genera el archivo de CARGA MASIVA DE PAGOS A TERCEROS de Banco Guayaquil (Ecuador)
a partir de la orden de pago aprobada en el Comité de Pagos.

Salidas (en Pagos/salida/, de donde el LaunchAgent de correo las adjunta):
  banco_bg_<SEMANA>_<AAAAMMDD>_NN.txt    <-- ESTE es el que se sube a Banca Empresas
  banco_bg_<SEMANA>_<AAAAMMDD>_NN.xlsm   <-- plantilla oficial llena (respaldo auditable)
  banco_bg_<SEMANA>_<AAAAMMDD>_NN.log    <-- qué entró, qué se excluyó y por qué

FORMATO DEL TXT
---------------
20 campos separados por TABULADOR, un pago por línea. Verificado contra dos fuentes
independientes que coinciden campo por campo:
  1. El macro `CreaArchTxt` extraído de la plantilla oficial `Plantilla pago a
     proveedores 8.xlsm` que entrega el banco.
  2. La especificación pública de BG: "¿Cuál es el formato para cargar una orden de
     Cash Management para pago a terceros en mi Banca Empresas?"

  1  Código Orientación .... "PA"                          obligatorio
  2  Cuenta Empresa ....... 10 dígitos con ceros a la izq.  obligatorio
  3  Secuencial Pago ...... desde 1                         obligatorio
  4  Comprobante de Pago .. máx 20                          opcional
  5  Código ............... CTA: nº de cuenta · EFE/CHQ: id obligatorio
  6  Moneda ............... "USD"                           obligatorio
  7  Valor ................ 13 dígitos, centavos            obligatorio
  8  Forma de Pago ........ CTA / CHQ / EFE                 obligatorio
  9  Cód. Institución ..... 4 dígitos (BG = 0017)           obligatorio
 10  Tipo de Cuenta ....... CTE / AHO (vacío si EFE/CHQ)    obligatorio si CTA
 11  Número de Cuenta ..... (vacío si EFE/CHQ)              obligatorio si CTA
 12  Tipo ID Beneficiario . C / R / P                       obligatorio
 13  Número ID ............ cédula 10 · RUC 13              obligatorio
 14  Nombre Beneficiario .. máx 40                          obligatorio
 15  Dirección ............ máx 40                          opcional
 16  Ciudad ............... máx 20                          opcional
 17  Teléfono ............. máx 20                          opcional
 18  Localidad de pago .... vacío si CTA                    opcional
 19  Referencia ........... máx 200                         OBLIGATORIO
 20  Referencia Adicional . "PAGOS VARIOS|correo"           opcional

SUBIDA EN LA WEB DE BANCO GUAYAQUIL
-----------------------------------
  Banca Empresas > Cash Management > Cargar > Carga de órdenes
  > Cargar archivo > elegir el .txt > Procesar > Revisar
  > y DESPUÉS aprobar la orden (sin aprobación no se procesa).
Ayuda del banco: 3730100 ext. 86300.

USO
---
  python3 banco_guayaquil.py maestro <export_BG.xlsx>   # importa beneficiarios del banco
  python3 banco_guayaquil.py diag                       # cobertura del maestro vs la CxP
  python3 banco_guayaquil.py generar [orden.json]       # genera TXT + xlsm
  python3 banco_guayaquil.py autotest                   # pruebas offline

Sólo stdlib + openpyxl (éste último sólo para leer/escribir Excel).
"""
import os, sys, json, re, glob, unicodedata, datetime, shutil
from pathlib import Path

PROJ = Path(__file__).resolve().parent
BANCO_DIR = PROJ / "Pagos" / "banco"
SALIDA_DIR = PROJ / "Pagos" / "salida"
CXP_DIR = PROJ / "Pagos" / "cxp"
MAESTRO = BANCO_DIR / "maestro_proveedores.json"
BANCOS_JSON = BANCO_DIR / "bg_bancos.json"
PLANTILLA = BANCO_DIR / "plantilla_bg_pago_proveedores.xlsm"
CONFIG = BANCO_DIR / "bg_config.json"

COD_BG = "0017"
PREFIJO_ARCHIVO_DEFAULT = "PAGOS_MULTICASH"

# Longitudes máximas por campo (especificación BG)
MAX = {"comprobante": 20, "codigo": 20, "nombre": 40, "direccion": 40,
       "ciudad": 20, "telefono": 20, "localidad": 20, "referencia": 200,
       "ref_adicional": 100}


def log(m):
    print(f"[{datetime.datetime.now():%H:%M:%S}] {m}", flush=True)


# ------------------------------------------------------------------ utilidades
def norm(s):
    """Mayúsculas, sin acentos, sin puntuación, espacios colapsados."""
    s = str(s or "").upper().strip()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", " ", s)).strip()


def ascii_campo(s, largo):
    """Texto apto para el archivo del banco: ASCII, sin tabuladores ni saltos, truncado."""
    s = str(s or "").strip()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[\t\r\n]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:largo]


def solo_digitos(s):
    return re.sub(r"\D", "", str(s or ""))


def tipo_id(num):
    """C = cédula (10), R = RUC (13), P = pasaporte."""
    d = solo_digitos(num)
    if len(d) == 10:
        return "C", d
    if len(d) >= 13:
        return "R", d[:13]
    return "P", ascii_campo(num, 13)


def valor_13(monto):
    """11 enteros + 2 decimales, sin punto. 12645.76 -> 0000001264576"""
    centavos = int(round(float(monto) * 100))
    if centavos < 0:
        raise ValueError(f"monto negativo: {monto}")
    s = str(centavos)
    if len(s) > 13:
        raise ValueError(f"monto excede 13 dígitos: {monto}")
    return s.zfill(13)


def cfg():
    if CONFIG.exists():
        try:
            return json.loads(CONFIG.read_text(encoding="utf-8"))
        except Exception as e:
            log(f"[WARN] {CONFIG.name} inválido ({e})")
    return {}


def bancos_idx():
    if not BANCOS_JSON.exists():
        return {}
    d = json.loads(BANCOS_JSON.read_text(encoding="utf-8")).get("bancos", {})
    return {norm(k): v for k, v in d.items()}


# ------------------------------------------------------------------ maestro
def importar_maestro(ruta_xlsx):
    """Convierte el export «Beneficiarios de pagos a terceros» de BG en el maestro.

    El export trae una fila por CUENTA, así que un mismo beneficiario puede aparecer
    varias veces (p.ej. una fila Efectivo y otra CTE). Se agrupan por identificación y
    se prefiere siempre la transferencia a cuenta sobre el efectivo: pagar por cuenta
    deja rastro bancario y no obliga al proveedor a ir a una agencia.
    """
    import openpyxl
    idx = bancos_idx()
    wb = openpyxl.load_workbook(ruta_xlsx, data_only=True)
    ws = wb[wb.sheetnames[0]]

    # La cabecera no está en la fila 1: se busca la fila que contiene "Beneficiario".
    fila_hdr = None
    for r in ws.iter_rows(min_row=1, max_row=30):
        vals = [norm(c.value) for c in r]
        if "BENEFICIARIO" in vals and "CUENTA" in vals:
            fila_hdr = r[0].row
            cols = {norm(c.value): c.column for c in r if c.value}
            break
    if not fila_hdr:
        sys.exit("ERROR: no encuentro la cabecera (fila con 'Beneficiario' y 'Cuenta').")

    def val(row, nombre):
        c = cols.get(nombre)
        return row[c - 1] if c and c - 1 < len(row) else None

    provs, avisos = {}, []
    n_filas = 0
    for row in ws.iter_rows(min_row=fila_hdr + 1, values_only=True):
        nombre = val(row, "BENEFICIARIO")
        if not nombre or not str(nombre).strip():
            continue
        n_filas += 1
        nombre = str(nombre).strip()
        cuenta_raw = str(val(row, "CUENTA") or "").strip()
        banco_raw = str(val(row, "BANCO") or "").strip()
        ident_raw = str(val(row, "IDENTIFICACION") or "").strip()
        correo = str(val(row, "CORREO ELECTRONICO") or "").strip()

        # "Cédula -  0102042900"  /  "RUC -  1791959043001"
        m = re.match(r"\s*(\w+)\s*-\s*(.+)", ident_raw)
        id_num = solo_digitos(m.group(2)) if m else solo_digitos(ident_raw)
        if not id_num:
            avisos.append(f"«{nombre}»: sin identificación legible ({ident_raw!r})")
            continue
        tid, id_num = tipo_id(id_num)

        # "CTE - 0300191029" / "AHO - 2213100072" / "Efectivo"
        if norm(cuenta_raw).startswith("EFECTIVO") or norm(banco_raw) == "EFECTIVO":
            forma, tipo_cta, num_cta, cod_banco = "EFE", "", "", COD_BG
        else:
            mc = re.match(r"\s*(CTE|AHO|CM)\s*-\s*(\S+)", cuenta_raw, re.I)
            if not mc:
                avisos.append(f"«{nombre}»: cuenta no reconocida ({cuenta_raw!r})")
                continue
            forma = "CTA"
            tipo_cta = mc.group(1).upper()
            num_cta = solo_digitos(mc.group(2))
            cod_banco = idx.get(norm(banco_raw))
            if not cod_banco:
                avisos.append(f"«{nombre}»: banco sin código en el Anexo 4 ({banco_raw!r})")
                continue

        reg = {
            "nombre": nombre, "tipo_id": tid, "id": id_num,
            "forma_pago": forma, "tipo_cuenta": tipo_cta, "num_cuenta": num_cta,
            "banco": banco_raw, "cod_banco": cod_banco, "correo": correo,
            "nombre_norm": norm(nombre),
        }
        prev = provs.get(id_num)
        # Preferimos cuenta sobre efectivo; entre dos cuentas, la primera cargada.
        if prev is None or (prev["forma_pago"] == "EFE" and forma == "CTA"):
            if prev is not None:
                reg["alternativas"] = prev.get("alternativas", []) + [
                    {k: prev[k] for k in ("forma_pago", "tipo_cuenta", "num_cuenta", "banco")}]
            provs[id_num] = reg
        else:
            prev.setdefault("alternativas", []).append(
                {"forma_pago": forma, "tipo_cuenta": tipo_cta,
                 "num_cuenta": num_cta, "banco": banco_raw})

    BANCO_DIR.mkdir(parents=True, exist_ok=True)
    doc = {
        "_fuente": f"Export «Beneficiarios de pagos a terceros» de Banca Empresas BG: {Path(ruta_xlsx).name}",
        "_importado": datetime.datetime.now().isoformat(timespec="seconds"),
        "_nota": ("Clave = número de identificación (cédula/RUC). Un beneficiario con varias "
                  "cuentas queda con la de transferencia como principal y el resto en "
                  "'alternativas'. Para cambiar la cuenta preferida, edita este archivo."),
        "avisos_importacion": avisos,
        "proveedores": provs,
    }
    MAESTRO.write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")

    formas = {}
    for p in provs.values():
        formas[p["forma_pago"]] = formas.get(p["forma_pago"], 0) + 1
    log(f"Maestro: {len(provs)} beneficiarios únicos de {n_filas} filas -> {MAESTRO}")
    log(f"  formas de pago: {formas}")
    log(f"  con correo: {sum(1 for p in provs.values() if p['correo'])}")
    for a in avisos[:10]:
        log(f"  AVISO: {a}")
    if len(avisos) > 10:
        log(f"  … y {len(avisos)-10} avisos más (ver el JSON)")
    return doc


def cargar_maestro():
    if not MAESTRO.exists():
        sys.exit(f"ERROR: no existe {MAESTRO}\n"
                 f"  Impórtalo primero:  python3 banco_guayaquil.py maestro <export_BG.xlsx>\n"
                 f"  El export se descarga de Banca Empresas > Pagos a terceros > Beneficiarios.")
    d = json.loads(MAESTRO.read_text(encoding="utf-8"))
    provs = d.get("proveedores", {})
    por_nombre = {}
    for p in provs.values():
        por_nombre.setdefault(p.get("nombre_norm") or norm(p["nombre"]), p)
    return provs, por_nombre


def buscar_proveedor(pago, provs, por_nombre):
    """Empareja un pago con el maestro. Por RUC primero (exacto), por nombre después."""
    ruc = solo_digitos(pago.get("ruc") or pago.get("identificacion"))
    if ruc:
        if ruc in provs:
            return provs[ruc], "ruc"
        # cédula de 10 contenida en un RUC de 13, y viceversa
        for k, p in provs.items():
            if k.startswith(ruc[:10]) or ruc.startswith(k[:10]):
                return p, "ruc-parcial"
    n = norm(pago.get("proveedor"))
    if n in por_nombre:
        return por_nombre[n], "nombre"
    return None, None


# ------------------------------------------------------------------ generación del TXT
def linea_txt(seq, pago, prov, cuenta_empresa):
    """Construye una línea de 20 campos separados por tabulador."""
    forma = prov["forma_pago"]
    es_ventanilla = forma in ("EFE", "CHQ")
    num_cta = prov.get("num_cuenta") or ""
    # Cuentas de Banco Guayaquil: 10 dígitos con ceros a la izquierda.
    # Otras instituciones: se envía tal cual, sin rellenar.
    if not es_ventanilla and prov.get("cod_banco") == COD_BG:
        num_cta = num_cta.zfill(10)

    codigo = prov["id"] if es_ventanilla else num_cta

    campos = [
        "PA",
        solo_digitos(cuenta_empresa).zfill(10),
        str(seq),
        ascii_campo(pago.get("comprobante") or pago.get("factura"), MAX["comprobante"]),
        ascii_campo(codigo, MAX["codigo"]),
        "USD",
        valor_13(pago["monto_pagar"]),
        forma,
        prov.get("cod_banco") or COD_BG,
        "" if es_ventanilla else prov.get("tipo_cuenta", ""),
        "" if es_ventanilla else num_cta,
        prov["tipo_id"],
        prov["id"],
        ascii_campo(prov["nombre"], MAX["nombre"]),
        ascii_campo(prov.get("direccion"), MAX["direccion"]),
        ascii_campo(prov.get("ciudad"), MAX["ciudad"]),
        ascii_campo(prov.get("telefono"), MAX["telefono"]),
        "" if not es_ventanilla else ascii_campo(prov.get("localidad"), MAX["localidad"]),
        ascii_campo(pago.get("referencia") or pago.get("factura"), MAX["referencia"]),
    ]
    ref_ad = "PAGOS VARIOS"
    correo = (prov.get("correo") or "").strip()
    if correo:
        ref_ad += "|" + ascii_campo(correo, MAX["ref_adicional"] - len(ref_ad) - 1)
    campos.append(ref_ad)
    return "\t".join(campos)


def validar(pago, prov):
    """Devuelve lista de problemas que impiden incluir el pago. Vacía = OK."""
    p = []
    if not prov:
        return ["no está en el maestro de beneficiarios del banco"]
    if not (pago.get("referencia") or pago.get("factura")):
        p.append("sin referencia (campo obligatorio de BG)")
    try:
        if float(pago["monto_pagar"]) <= 0:
            p.append("monto menor o igual a cero")
        else:
            valor_13(pago["monto_pagar"])
    except (KeyError, TypeError, ValueError) as e:
        p.append(f"monto inválido ({e})")
    if prov["forma_pago"] == "CTA":
        if not prov.get("num_cuenta"):
            p.append("sin número de cuenta")
        if prov.get("tipo_cuenta") not in ("CTE", "AHO", "CM"):
            p.append(f"tipo de cuenta inválido ({prov.get('tipo_cuenta')!r})")
        if not prov.get("cod_banco"):
            p.append("sin código de institución financiera")
    if prov["tipo_id"] == "C" and len(prov["id"]) != 10:
        p.append(f"cédula con {len(prov['id'])} dígitos (deben ser 10)")
    if prov["tipo_id"] == "R" and len(prov["id"]) != 13:
        p.append(f"RUC con {len(prov['id'])} dígitos (deben ser 13)")
    return p


def pagos_de_ecuador(orden):
    """Extrae los pagos aprobados de Ecuador de una orden del comité."""
    out = []
    for p in orden.get("paises", []):
        if p.get("code") != "EC":
            continue
        if (p.get("moneda") or "USD") != "USD":
            log(f"[WARN] Ecuador con moneda {p.get('moneda')}: BG sólo acepta USD")
        for f in p.get("pagos", []):
            out.append(dict(f, referencia=f.get("factura")))
    return out


def siguiente_nombre(base, ext):
    SALIDA_DIR.mkdir(parents=True, exist_ok=True)
    n = 1
    while (SALIDA_DIR / f"{base}_{n:02d}{ext}").exists():
        n += 1
    return n


def generar(ruta_orden=None):
    c = cfg()
    cuenta = c.get("cuenta_empresa")
    if not cuenta:
        sys.exit(f"ERROR: falta 'cuenta_empresa' en {CONFIG}.\n"
                 f"  Es el número de cuenta de VICOMER en Banco Guayaquil de donde salen los "
                 f"pagos (10 dígitos; si tiene menos se completa con ceros a la izquierda).")

    if ruta_orden is None:
        cands = sorted(glob.glob(str(SALIDA_DIR / "orden_pago_*.json")) +
                       glob.glob(str(PROJ / "Pagos" / "enviados" / "*orden_pago_*.json")))
        if not cands:
            sys.exit("ERROR: no encuentro ninguna orden de pago. Genera una en el artefacto "
                     "«Comité de Pagos» o pásame la ruta:\n"
                     "  python3 banco_guayaquil.py generar ruta/orden_pago.json")
        ruta_orden = cands[-1]
    orden = json.loads(Path(ruta_orden).read_text(encoding="utf-8"))
    log(f"Orden: {ruta_orden}")

    provs, por_nombre = cargar_maestro()
    pagos = pagos_de_ecuador(orden)
    if not pagos:
        sys.exit("La orden no tiene pagos aprobados de Ecuador; no hay nada que generar.")

    incluidos, excluidos = [], []
    for pg in pagos:
        prov, via = buscar_proveedor(pg, provs, por_nombre)
        problemas = validar(pg, prov)
        if problemas:
            excluidos.append((pg, problemas))
        else:
            incluidos.append((pg, prov, via))

    semana = orden.get("semana", "SIN-SEMANA")
    hoy = datetime.date.today().strftime("%Y%m%d")
    prefijo = c.get("prefijo_archivo", PREFIJO_ARCHIVO_DEFAULT)
    base = f"banco_bg_{semana}_{hoy}"
    n = siguiente_nombre(base, ".txt")
    f_txt = SALIDA_DIR / f"{base}_{n:02d}.txt"
    f_log = SALIDA_DIR / f"{base}_{n:02d}.log"
    f_xls = SALIDA_DIR / f"{base}_{n:02d}.xlsm"

    lineas, total = [], 0.0
    for i, (pg, prov, _via) in enumerate(incluidos, start=1):
        lineas.append(linea_txt(i, pg, prov, cuenta))
        total += float(pg["monto_pagar"])

    if lineas:
        # Sin BOM y con salto \r\n, como escribe el macro original en Windows.
        f_txt.write_text("\r\n".join(lineas) + "\r\n", encoding="ascii", errors="replace")

    reporte = [
        f"ARCHIVO DE PAGOS BANCO GUAYAQUIL — {semana}",
        f"Generado    : {datetime.datetime.now():%Y-%m-%d %H:%M:%S}",
        f"Orden       : {ruta_orden}",
        f"Cuenta      : {solo_digitos(cuenta).zfill(10)}  ({c.get('nombre_empresa','')})",
        f"Prefijo BG  : {prefijo}",
        "",
        f"INCLUIDOS   : {len(incluidos)} pagos · USD {total:,.2f}",
        f"EXCLUIDOS   : {len(excluidos)}",
        "",
    ]
    for i, (pg, prov, via) in enumerate(incluidos, start=1):
        reporte.append(f"  {i:>3}  {prov['nombre'][:38]:38s} {prov['forma_pago']} "
                       f"{prov.get('tipo_cuenta',''):3s} {prov.get('num_cuenta',''):>14s} "
                       f"{prov.get('cod_banco','')}  USD {float(pg['monto_pagar']):>12,.2f}  "
                       f"[match: {via}]")
    if excluidos:
        reporte += ["", "EXCLUIDOS — NO se cargaron al banco:"]
        for pg, probs in excluidos:
            reporte.append(f"  · {str(pg.get('proveedor'))[:44]:44s} "
                           f"USD {float(pg.get('monto_pagar') or 0):>12,.2f}")
            for p in probs:
                reporte.append(f"      - {p}")
        reporte += ["", "Complétalos en el maestro (Pagos/banco/maestro_proveedores.json) o",
                    "regístralos como beneficiarios en Banca Empresas y vuelve a exportar."]
    f_log.write_text("\n".join(reporte) + "\n", encoding="utf-8")

    ok_xls = escribir_xlsm(f_xls, incluidos, cuenta, c, prefijo)

    log(f"OK: {len(incluidos)} pagos · USD {total:,.2f}")
    if lineas:
        log(f"    TXT  -> {f_txt}")
    else:
        log("    NO se generó TXT: ningún pago pasó la validación.")
    if ok_xls:
        log(f"    XLSM -> {f_xls}")
    log(f"    LOG  -> {f_log}")
    if excluidos:
        log(f"    ATENCIÓN: {len(excluidos)} pago(s) quedaron FUERA del archivo. Ver el .log")
    return f_txt if lineas else None


def escribir_xlsm(destino, incluidos, cuenta, c, prefijo):
    """Llena una copia de la plantilla oficial (respaldo legible de lo que se cargó)."""
    if not PLANTILLA.exists():
        log(f"[WARN] no está la plantilla {PLANTILLA.name}; se omite el .xlsm")
        return False
    try:
        import openpyxl
    except ImportError:
        log("[WARN] sin openpyxl; se omite el .xlsm")
        return False
    try:
        shutil.copy2(PLANTILLA, destino)
        wb = openpyxl.load_workbook(destino, keep_vba=True)
        bp, pg_ws = wb["Base Proveedores"], wb["PagosGenerados"]

        pg_ws["B1"] = int(solo_digitos(cuenta))
        pg_ws["D1"] = prefijo
        pg_ws["F1"] = c.get("nombre_empresa", "")

        for i, (pago, prov, _v) in enumerate(incluidos):
            r = 2 + i          # Base Proveedores: fila 1 = cabecera
            bp.cell(row=r, column=1, value=prov["nombre"])
            bp.cell(row=r, column=2, value=prov["id"])
            bp.cell(row=r, column=3, value="X")            # marcado para pago
            bp.cell(row=r, column=4, value=prov["forma_pago"])
            bp.cell(row=r, column=5, value=prov.get("num_cuenta", ""))
            bp.cell(row=r, column=6, value=prov.get("tipo_cuenta", ""))
            bp.cell(row=r, column=7, value=prov.get("banco", ""))
            bp.cell(row=r, column=8, value=prov.get("cod_banco", ""))
            bp.cell(row=r, column=9, value=prov.get("correo", ""))

            k = 3 + i          # PagosGenerados: filas 1-2 = cabeceras
            es_v = prov["forma_pago"] in ("EFE", "CHQ")
            num_cta = prov.get("num_cuenta", "")
            if not es_v and prov.get("cod_banco") == COD_BG:
                num_cta = num_cta.zfill(10)
            pg_ws.cell(row=k, column=1, value=i + 1)
            pg_ws.cell(row=k, column=2, value=ascii_campo(prov["nombre"], MAX["nombre"]))
            pg_ws.cell(row=k, column=3, value=round(float(pago["monto_pagar"]), 2))
            pg_ws.cell(row=k, column=4, value=ascii_campo(pago.get("factura"), MAX["comprobante"]))
            pg_ws.cell(row=k, column=5, value=ascii_campo(pago.get("referencia") or
                                                          pago.get("factura"), MAX["referencia"]))
            pg_ws.cell(row=k, column=6, value=num_cta)
            pg_ws.cell(row=k, column=7, value=prov["forma_pago"])
            pg_ws.cell(row=k, column=8, value="" if es_v else prov.get("tipo_cuenta", ""))
            pg_ws.cell(row=k, column=9, value=prov.get("cod_banco", COD_BG))
            pg_ws.cell(row=k, column=10, value=prov["id"])
            pg_ws.cell(row=k, column=11, value=prov["tipo_id"])
            pg_ws.cell(row=k, column=15, value=num_cta)     # Contrapartida
            pg_ws.cell(row=k, column=16, value=prov.get("correo", ""))

        pg_ws["A2001"] = len(incluidos) + 2   # el macro lo usa como contador de pagos
        wb.save(destino)
        return True
    except Exception as e:
        log(f"[WARN] no pude escribir el .xlsm ({e}); el .txt es lo que importa")
        return False


# ------------------------------------------------------------------ diagnóstico
def diag():
    provs, por_nombre = cargar_maestro()
    log(f"Maestro: {len(provs)} beneficiarios")
    formas = {}
    for p in provs.values():
        formas[p["forma_pago"]] = formas.get(p["forma_pago"], 0) + 1
    log(f"  formas: {formas} · con correo: {sum(1 for p in provs.values() if p['correo'])}")
    if not cfg().get("cuenta_empresa"):
        log(f"  !! FALTA 'cuenta_empresa' en {CONFIG.name} — sin eso no se puede generar")

    f = CXP_DIR / "cxp_semana_actual.json"
    if not f.exists():
        log("No hay CxP para contrastar."); return
    d = json.loads(f.read_text(encoding="utf-8"))
    ec = next((p for p in d.get("paises", []) if p["code"] == "EC"), None)
    if not ec or not ec.get("facturas"):
        log("La CxP de esta semana no tiene facturas de Ecuador que contrastar.")
        return
    prov_unicos, sin_match = {}, {}
    for fac in ec["facturas"]:
        if fac.get("monto", 0) <= 0:
            continue
        p, via = buscar_proveedor(fac, provs, por_nombre)
        key = fac.get("proveedor")
        if p:
            prov_unicos[key] = via
        else:
            sin_match[key] = sin_match.get(key, 0) + float(fac["monto"])
    log(f"CxP Ecuador: {len(prov_unicos)} proveedores con beneficiario · "
        f"{len(sin_match)} SIN beneficiario")
    for nombre, monto in sorted(sin_match.items(), key=lambda x: -x[1])[:20]:
        log(f"  !! {str(nombre)[:50]:50s} USD {monto:>12,.2f}")
    if sin_match:
        log("   Regístralos en Banca Empresas > Pagos a terceros > Beneficiarios,")
        log("   vuelve a exportar y corre: python3 banco_guayaquil.py maestro <export>.xlsx")


# ------------------------------------------------------------------ autotest
def autotest():
    fallos = []
    def check(cond, msg):
        (print(f"  ok  {msg}") if cond else fallos.append(msg))

    check(valor_13(12645.76) == "0000001264576", "valor 12.645,76 -> 0000001264576")
    check(valor_13(0.01) == "0000000000001", "un centavo")
    check(valor_13(1234.005) == "0000000123400" or valor_13(1234.005) == "0000000123401",
          "redondeo de centavos sin error de coma flotante")
    check(valor_13(0.07 * 3) == "0000000000021", "0.07*3 = 21 centavos (no 20 por float)")
    check(tipo_id("0102042900") == ("C", "0102042900"), "cédula de 10 -> C")
    check(tipo_id("1791959043001") == ("R", "1791959043001"), "RUC de 13 -> R")
    check(tipo_id("PX39582")[0] == "P", "pasaporte -> P")
    check(ascii_campo("Cía. Ñandú  S.A.\tX", 40) == "Cia. Nandu S.A. X",
          "normaliza acentos y elimina tabuladores")
    check(len(ascii_campo("A" * 60, 40)) == 40, "trunca a la longitud del campo")

    prov_bg = {"nombre": "PROVEEDOR ÑU S.A.", "tipo_id": "R", "id": "1791959043001",
               "forma_pago": "CTA", "tipo_cuenta": "CTE", "num_cuenta": "7420692",
               "cod_banco": "0017", "correo": "pagos@prov.ec"}
    prov_otro = dict(prov_bg, cod_banco="0010", num_cuenta="2213100072", tipo_cuenta="AHO")
    prov_efe = {"nombre": "JUAN PEREZ", "tipo_id": "C", "id": "0102042900",
                "forma_pago": "EFE", "tipo_cuenta": "", "num_cuenta": "",
                "cod_banco": "0017", "correo": ""}
    pago = {"proveedor": "PROVEEDOR ÑU S.A.", "factura": "FAC-001-002-000123",
            "monto_pagar": 1500.5, "referencia": "FAC-001-002-000123"}

    l = linea_txt(1, pago, prov_bg, "1234567").split("\t")
    check(len(l) == 20, "la línea tiene exactamente 20 campos")
    check(l[0] == "PA", "campo 1 = PA")
    check(l[1] == "0001234567", "campo 2 = cuenta de la empresa a 10 dígitos")
    check(l[5] == "USD", "campo 6 = USD")
    check(l[6] == "0000000150050", "campo 7 = valor en centavos a 13 dígitos")
    check(l[7] == "CTA", "campo 8 = forma de pago")
    check(l[10] == "0007420692", "cuenta de BG se rellena a 10 dígitos")
    check(l[4] == "0007420692", "campo 5 = número de cuenta cuando es CTA")
    check(l[11] == "R" and l[12] == "1791959043001", "campos 12-13 = tipo y número de ID")
    check(l[17] == "", "campo 18 (localidad) va vacío si es CTA")
    check(l[18] == "FAC-001-002-000123", "campo 19 = referencia")
    check(l[19] == "PAGOS VARIOS|pagos@prov.ec", "campo 20 = referencia|correo")

    lo = linea_txt(2, pago, prov_otro, "1234567").split("\t")
    check(lo[10] == "2213100072", "cuenta de OTRO banco NO se rellena con ceros")
    check(lo[8] == "0010", "campo 9 = código de la institución financiera")

    le = linea_txt(3, dict(pago, proveedor="JUAN PEREZ"), prov_efe, "1234567").split("\t")
    check(le[7] == "EFE", "efectivo conserva la forma de pago")
    check(le[9] == "" and le[10] == "", "efectivo deja tipo y número de cuenta vacíos")
    check(le[4] == "0102042900", "campo 5 = identificación cuando es ventanilla")
    check(le[19] == "PAGOS VARIOS", "sin correo no se agrega el pipe")

    check(validar({"monto_pagar": 10, "factura": "F1"}, None) ==
          ["no está en el maestro de beneficiarios del banco"], "detecta proveedor ausente")
    check("sin referencia (campo obligatorio de BG)" in
          validar({"monto_pagar": 10}, prov_bg), "exige referencia")
    check(any("cero" in x for x in validar({"monto_pagar": 0, "factura": "F"}, prov_bg)),
          "rechaza monto cero")
    check(any("dígitos" in x for x in
              validar({"monto_pagar": 1, "factura": "F"}, dict(prov_bg, id="123"))),
          "rechaza RUC con longitud incorrecta")

    provs = {"1791959043001": prov_bg}
    pn = {norm(prov_bg["nombre"]): prov_bg}
    check(buscar_proveedor({"ruc": "1791959043001"}, provs, pn)[1] == "ruc", "match por RUC")
    check(buscar_proveedor({"proveedor": "Proveedor Ñu S.A."}, provs, pn)[1] == "nombre",
          "match por nombre normalizado")
    check(buscar_proveedor({"proveedor": "OTRO"}, provs, pn)[0] is None, "no inventa match")

    print()
    if fallos:
        for f in fallos:
            print(f"  FALLA  {f}")
        sys.exit(f"AUTOTEST: {len(fallos)} fallas")
    print("AUTOTEST OK — formato BG de 20 campos, validaciones y emparejamiento.")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "maestro":
        if len(sys.argv) < 3:
            sys.exit("Uso: python3 banco_guayaquil.py maestro <export_BG.xlsx>")
        importar_maestro(sys.argv[2])
    elif arg == "diag":
        diag()
    elif arg == "autotest":
        autotest()
    elif arg == "generar":
        generar(sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        print(__doc__)
        sys.exit("Indica una acción: maestro | diag | generar | autotest")
