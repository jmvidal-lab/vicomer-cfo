#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build.py  ·  Estados Financieros Grupo VICOMER
==============================================
Inyecta datos/eeff_<corte>.json dentro de src/eeff_template.html y deja en dist/
las dos salidas. Antes de escribir nada, VERIFICA las cifras: si el balance no
cierra o un subtotal del P&G no se reconstruye, el build falla y no publica.

Por que existe
--------------
El tablero nacio como un HTML escrito a mano con las cifras incrustadas. Eso
funciona una vez y se rompe la segunda: alguien cambia un numero del P&G, olvida
el subtotal, y el tablero muestra un estado financiero que no cuadra con una
seguridad perfecta. Separar DATOS de PRESENTACION y comprobar los datos antes de
renderizar es lo unico que impide ese error.

USO
    python3 build.py                 # verifica y construye el corte por defecto
    python3 build.py --check         # solo verifica, no escribe
    python3 build.py 2026-07         # elige el corte (datos/eeff_2026-07.json)

SALIDAS
    dist/eeff_artifact.html     para publicar como artefacto (SIN doctype/head/body:
                                la plataforma envuelve la pagina al publicar)
    dist/eeff_standalone.html   documento completo, para abrir con doble clic

Solo biblioteca estandar.
"""
import json, sys, re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
TPL = RAIZ / "src" / "eeff_template.html"
DIST = RAIZ / "dist"
CORTE_DEFECTO = "2026-07"

# Las cifras se redondean al presentarse; un indicador calculado con componentes
# ya redondeados puede desviarse una unidad. No es error: es redondeo.
TOL_DINERO = 1.0        # unidades de la moneda del pais
TOL_PCT = 0.0015        # 0,15 puntos porcentuales
TOL_DIAS = 1.5          # dias


class Fallo(Exception):
    pass


def cargar(corte):
    f = RAIZ / "datos" / ("eeff_%s.json" % corte)
    if not f.exists():
        raise Fallo("no existe %s" % f)
    return json.loads(f.read_text(encoding="utf-8")), f


def subtotales_del_pyg(pl):
    """Devuelve [(etiqueta, declarado, calculado)] por cada subtotal.

    Regla: un subtotal (t en s/S/F) vale el subtotal anterior mas todas las
    lineas sueltas desde entonces. Es exactamente como se lee en pantalla, y es
    la comprobacion que atrapa el error de editar un renglon y no el total.
    """
    out, acum, desde_ultimo, primero = [], 0.0, [], True
    for r in pl:
        if r.get("t") in ("s", "S", "F"):
            # Cuando la fuente ya entrega la venta NETA no hay renglones encima que sumar:
            # el primer subtotal es el punto de partida, no un total que deba reconstruirse.
            if primero and not desde_ultimo:
                acum, primero = r["v"], False
                continue
            calc = acum + sum(x["v"] for x in desde_ultimo)
            out.append((r["k"], r["v"], calc))
            acum, desde_ultimo, primero = r["v"], [], False
        else:
            desde_ultimo.append(r)
    return out


def base_ventas(pl):
    for r in pl:
        if r.get("t") == "s":
            return r["v"]
    return None


def suma(items):
    return sum(i["v"] for i in items)


def verificar(doc):
    errores, avisos, n = [], [], 0

    def chk(nombre, cond, detalle=""):
        nonlocal n
        n += 1
        if not cond:
            errores.append("%s  %s" % (nombre, detalle))
        print("   %s %-60s %s" % ("OK " if cond else "!! ", nombre, "" if cond else detalle))

    meta = doc.get("meta") or {}
    chk("meta declara corte, TRM y fecha de TRM",
        bool(meta.get("corte")) and meta.get("trm") and meta.get("trm_fecha"),
        str({k: meta.get(k) for k in ("corte", "trm", "trm_fecha")}))
    chk("la TRM es plausible (1.000–10.000 COP/USD)",
        1000 < float(meta.get("trm") or 0) < 10000, str(meta.get("trm")))
    chk("meta declara el corte en ISO para medir la antiguedad",
        bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", meta.get("corte_iso") or "")),
        str(meta.get("corte_iso")))
    # La antiguedad NO hace fallar el build: un corte viejo es una realidad, no un error.
    # Pero tiene que decirse en voz alta cada vez que se construye.
    try:
        import datetime as _dt
        d0 = _dt.date.fromisoformat(meta["corte_iso"])
        dias = (_dt.date.today() - d0).days
        if dias > 45:
            avisos.append("el corte tiene %d dias: las cifras del tablero NO son del dia de hoy, "
                          "solo la TRM lo es" % dias)
    except Exception:
        pass

    # Solo son paises las claves que traen estado de resultados. 'conc' y cualquier otro
    # bloque de metadatos no se verifican como si fueran una compania.
    for cod in [k for k in doc if isinstance(doc.get(k), dict) and doc[k].get("pl")]:
        d = doc[cod]
        pais = d.get("pais", cod)
        pl, bg, ind = d.get("pl") or [], d.get("bg") or {}, d.get("ind") or {}

        # --- P&G: cada subtotal se reconstruye
        malos = [(k, dec, cal) for k, dec, cal in subtotales_del_pyg(pl)
                 if abs(dec - cal) > TOL_DINERO]
        chk("%s · todos los subtotales del P&G se reconstruyen" % pais, not malos,
            "; ".join("%s: declarado %.2f, calculado %.2f" % (k, dec, cal) for k, dec, cal in malos))

        # --- P&G: los % declarados son sobre VENTAS NETAS
        base = base_ventas(pl)
        malos = [(r["k"], r["pct"], r["v"] / base) for r in pl
                 if r.get("pct") is not None and base and abs(r["pct"] - r["v"] / base) > TOL_PCT]
        chk("%s · los %% del P&G son sobre ventas netas" % pais, not malos,
            "; ".join("%s: %.4f vs %.4f" % m for m in malos))

        # --- Balance: activo = pasivo + patrimonio
        ac, anc = suma(bg.get("activo") or []), suma(bg.get("activo_nc") or [])
        pc, pnc = suma(bg.get("pasivo") or []), suma(bg.get("pasivo_nc") or [])
        pat = suma(bg.get("patrimonio") or [])
        at, pt = ac + anc, pc + pnc
        chk("%s · el balance cierra" % pais, abs(at - pt - pat) <= TOL_DINERO,
            "activo %.2f vs pasivo+patrimonio %.2f (dif %.2f)" % (at, pt + pat, at - pt - pat))

        # --- El resultado del ejercicio del balance es el del P&G
        neto = next((r["v"] for r in reversed(pl) if r.get("t") == "F"), None)
        res_bg = next((i["v"] for i in (bg.get("patrimonio") or [])
                       if "resultado del ejercicio" in (i.get("k") or "").lower()), None)
        chk("%s · el resultado del balance es el del P&G" % pais,
            neto is not None and res_bg is not None and abs(neto - res_bg) <= TOL_DINERO,
            "P&G %s vs balance %s" % (neto, res_bg))

        # --- Indicadores derivados: no se escriben a mano, se comprueban
        if pc:
            chk("%s · razon corriente coincide con el balance" % pais,
                abs((ind.get("liquidez") or 0) - ac / pc) <= 0.02,
                "declarada %s vs %.4f" % (ind.get("liquidez"), ac / pc))
        if at:
            chk("%s · endeudamiento coincide con el balance" % pais,
                abs((ind.get("endeud") or 0) - pt / at) <= 0.005,
                "declarado %s vs %.4f" % (ind.get("endeud"), pt / at))
        if base:
            for clave, etiqueta, idx in (("mn", "margen neto", neto),):
                if idx is not None and ind.get(clave) is not None:
                    chk("%s · %s coincide con el P&G" % (pais, etiqueta),
                        abs(ind[clave] - idx / base) <= TOL_PCT,
                        "declarado %s vs %.4f" % (ind[clave], idx / base))
        if all(ind.get(k) is not None for k in ("dso", "dio", "dpo", "ccc")):
            calc = ind["dso"] + ind["dio"] - ind["dpo"]
            chk("%s · ciclo de caja = cobro + inventario − pago" % pais,
                abs(ind["ccc"] - calc) <= TOL_DIAS,
                "declarado %s vs %s (los componentes van redondeados)" % (ind["ccc"], calc))

        # --- Huecos declarados, no rellenados
        sin_sub = [i["k"] for grupo in ("activo", "pasivo", "patrimonio")
                   for i in (bg.get(grupo) or []) if i.get("flag") and not i.get("sub")]
        if sin_sub:
            avisos.append("%s: partidas marcadas con bandera pero sin explicacion: %s"
                          % (pais, ", ".join(sin_sub)))

    # --- Inventario: el bloque que alimenta la seccion de salud de inventario.
    # Se comprueba el contrato, no se recalcula la salud: eso lo hace la pagina.
    inv = doc.get("inventario") or {}
    if inv:
        chk("inventario declara fuente y corte",
            bool((inv.get("meta") or {}).get("fuente")) and bool((inv.get("meta") or {}).get("corte_iso")),
            str((inv.get("meta") or {}).get("corte_iso")))
        for cod in [k for k in inv if k != "meta"]:
            b = inv[cod] or {}
            items = b.get("items") or []
            pais = b.get("pais", cod)
            chk("%s · inventario trae referencias" % pais, bool(items), "0 items")
            sv = round(sum(float(i.get("stock_val") or 0) for i in items), 2)
            chk("%s · la suma de valores por referencia es el stock total" % pais,
                abs(sv - float(b.get("stock_total") or 0)) <= 1.0,
                "items %.2f vs stock_total %.2f" % (sv, float(b.get("stock_total") or 0)))
            malos = [i.get("sku") for i in items
                     if abs(float(i.get("stock_val") or 0)
                            - float(i.get("stock_u") or 0) * float(i.get("costo_u") or 0)) > 1.0]
            chk("%s · valor = existencias x costo unitario en cada referencia" % pais,
                not malos, "no cuadran: %s" % malos[:5])
            malos = [i.get("sku") for i in items
                     if abs(sum(float(v) for v in (i.get("u") or {}).values())
                            - float(i.get("u_tot") or 0)) > 0.01]
            chk("%s · la demanda mensual suma el total declarado" % pais,
                not malos, "no cuadran: %s" % malos[:5])
            meses = b.get("meses_con_demanda") or []
            vistos = sorted({int(m) for i in items for m in (i.get("u") or {})})
            chk("%s · los meses con demanda declarados son los que traen los datos" % pais,
                set(meses) == set(vistos), "declarado %s vs visto %s" % (meses, vistos))
            c = b.get("conciliacion") or {}
            if c.get("balance_almacen") is not None:
                chk("%s · la conciliacion de inventario es aritmetica" % pais,
                    abs(float(c["maestro"]) - float(c["balance_almacen"]) - float(c["dif"])) <= 1.0,
                    "maestro %s - balance %s != dif %s" % (c.get("maestro"), c.get("balance_almacen"), c.get("dif")))
                if abs(float(c.get("pct") or 0)) > 0.02:
                    avisos.append("%s: el maestro de productos se aparta %.1f%% del inventario del balance; "
                                  "el valor por SKU sirve para priorizar, no para valorar"
                                  % (pais, float(c["pct"]) * 100))
            if len(meses) < 3:
                avisos.append("%s: solo %d mes(es) de demanda en Odoo; el coeficiente de variacion "
                              "necesita 3, asi que el XYZ sale como 'sin clasificar'" % (pais, len(meses)))
            if b.get("podado"):
                avisos.append("%s: se publican %d de %d fichas (se dejaron las que tienen stock o movimiento)"
                              % (pais, len(items), b.get("n_sku_origen") or 0))

    print()
    for a in avisos:
        print("   [aviso] %s" % a)
    if errores:
        print("\n  VERIFICACION FALLIDA — %d de %d" % (len(errores), n))
        for e in errores:
            print("    · %s" % e)
        raise Fallo("los datos no cuadran; no se construye nada")
    print("\n  VERIFICACION OK — %d comprobaciones" % n)
    return n


def construir(doc, corte):
    tpl = TPL.read_text(encoding="utf-8")
    marca = re.compile(r"/\*__DATOS__\*/.*?/\*__FIN__\*/", re.S)
    if not marca.search(tpl):
        raise Fallo("la plantilla perdio el marcador /*__DATOS__*/ ... /*__FIN__*/")
    datos = json.dumps(doc, ensure_ascii=False, indent=2)
    pagina = marca.sub(lambda _: "/*__DATOS__*/" + datos + "/*__FIN__*/", tpl, count=1)
    DIST.mkdir(exist_ok=True)
    (DIST / "eeff_artifact.html").write_text(pagina, encoding="utf-8")
    completo = ('<!doctype html><html lang="es"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                '<style>body{margin:0;font:14px system-ui}img{max-width:100%}'
                '[hidden]{display:none!important}</style>' + pagina + "</body></html>")
    (DIST / "eeff_standalone.html").write_text(completo, encoding="utf-8")
    print("  dist/eeff_artifact.html    %7.1f KB   (para publicar como artefacto)"
          % ((DIST / "eeff_artifact.html").stat().st_size / 1024))
    print("  dist/eeff_standalone.html  %7.1f KB   (para abrir en el navegador)"
          % ((DIST / "eeff_standalone.html").stat().st_size / 1024))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    solo_check = "--check" in sys.argv
    corte = args[0] if args else CORTE_DEFECTO
    doc, f = cargar(corte)
    print("=" * 84)
    print("  Estados Financieros Grupo VICOMER · corte %s" % corte)
    print("  datos: %s" % f.name)
    print("=" * 84)
    verificar(doc)
    if solo_check:
        print("\n  --check: no se escribio nada."); return
    print()
    construir(doc, corte)


if __name__ == "__main__":
    try:
        main()
    except Fallo as e:
        print("\n  ERROR: %s" % e); sys.exit(1)
