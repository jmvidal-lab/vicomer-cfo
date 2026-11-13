#!/usr/bin/env python3
"""
vix_diagnostico.py — Estado de los libros de VIX S.A.S. en Odoo. SOLO LECTURA.

    python3 VIX/vix_diagnostico.py            # imprime y guarda VIX/salida/diagnostico_<fecha>.md

Revisa:
  1. Inventario de asientos (estado, tipo, mes) y borradores vacíos.
  2. Cuentas usadas en facturas vs vix_reglas.json (ingreso y CxC de relacionadas).
  3. Cuadre intercompañía: cada factura de VIX contra la factura de proveedor en
     VICOMER (cia 2) y VINTRAL (cia 1): existencia, monto y estado de pago.
  4. Meses sin factura intercompañía.
  5. Banco, cobros, retenciones y gastos: ¿hay registros?
Los descuadres se muestran, no se corrigen.
"""
import datetime as dt
from collections import Counter, defaultdict
from pathlib import Path

from vix_odoo import OdooVIX, REGLAS, CIA, AQUI

HOY = dt.date.today()
L = []                      # líneas del informe
ALERTAS = []                # (severidad, texto)


def p(s=""):
    L.append(s)


def alerta(sev, txt):
    ALERTAS.append((sev, txt))


def usd(x):
    return f"{x:,.2f}"


def main():
    od = OdooVIX()
    reg = REGLAS
    cu = reg["cuentas"]
    rel = {k: v for k, v in reg["partes_relacionadas"].items() if not k.startswith("_")}

    p(f"# Diagnóstico contable VIX S.A.S. — {HOY.isoformat()}")
    p(f"Fuente: Odoo `{od.url}`, compañía id {CIA}. Solo lectura.\n")

    # ── 1. Inventario ──────────────────────────────────────────────────
    mv = od.sr("account.move", [], ["name", "date", "state", "move_type", "journal_id",
               "partner_id", "amount_untaxed", "amount_total", "amount_residual",
               "payment_state", "ref"], order="date asc")
    p("## 1. Inventario de asientos")
    p(f"Total: **{len(mv)}**\n")
    p("| Estado | Tipo | Cantidad |\n|---|---|---|")
    for (s, t), n in sorted(Counter((m["state"], m["move_type"]) for m in mv).items()):
        p(f"| {s} | {t} | {n} |")
    p("\n| Diario | Cantidad |\n|---|---|")
    for j, n in Counter(m["journal_id"][1] for m in mv).most_common():
        p(f"| {j} | {n} |")
    vacios = [m for m in mv if m["state"] == "draft" and not m["amount_total"]]
    if vacios:
        alerta("BAJA", f"{len(vacios)} borradores vacíos (ids {', '.join(str(m['id']) for m in vacios)}): eliminar.")

    tipos = Counter(m["move_type"] for m in mv if m["state"] == "posted")
    if not tipos.get("in_invoice"):
        alerta("ALTA", "Cero facturas de proveedor/gastos: la utilidad contable = 100% del ingreso.")
    entries_banco = [m for m in mv if m["journal_id"][0] == reg["diarios"]["banco"]]
    stl = od.sr("account.bank.statement.line", [], ["id"])
    pagos = od.sr("account.payment", [], ["id"])
    if not entries_banco and not stl and not pagos:
        alerta("ALTA", "Sin banco: cero extractos, cero pagos/cobros registrados.")
    ret = [m for m in mv if m["journal_id"][0] == reg["diarios"]["retenciones_clientes"]]
    if not ret:
        alerta("MEDIA", "Cero retenciones de clientes registradas (verificar si VICOMER retuvo IR/IVA).")

    # banco vinculado al diario
    j = od.sr("account.journal", [["id", "=", reg["diarios"]["banco"]]], ["bank_account_id"])
    if j and not j[0]["bank_account_id"]:
        alerta("MEDIA", f"El diario Bank (id {reg['diarios']['banco']}) no está vinculado a la cuenta "
                        f"{reg['banco']['banco']} …{reg['banco']['cuenta_ultimos4']}.")

    # ── 2. Cuentas usadas ─────────────────────────────────────────────
    fact = [m for m in mv if m["move_type"] == "out_invoice" and m["state"] == "posted"]
    ids = [m["id"] for m in fact]
    lineas = od.sr("account.move.line", [["move_id", "in", ids]],
                   ["move_id", "account_id", "display_type", "name", "balance", "partner_id"]) if ids else []
    p("\n## 2. Facturas emitidas y cuentas usadas")
    p("| Factura | Fecha | Cliente | Base | Total | Saldo VIX | Cta. ingreso | Cta. CxC |")
    p("|---|---|---|---|---|---|---|---|")
    por_mov = defaultdict(list)
    for ln in lineas:
        por_mov[ln["move_id"][0]].append(ln)
    for m in fact:
        lns = por_mov[m["id"]]
        ing = {ln["account_id"][1].split()[0] for ln in lns if ln["display_type"] == "product"}
        cxc = {ln["account_id"][1].split()[0] for ln in lns if ln["display_type"] == "payment_term"}
        cliente = m["partner_id"][1] if m["partner_id"] else "?"
        p(f"| {m['name']} | {m['date']} | {cliente} | {usd(m['amount_untaxed'])} | {usd(m['amount_total'])} "
          f"| {usd(m['amount_residual'])} | {', '.join(sorted(ing))} | {', '.join(sorted(cxc))} |")
        if cu["ingreso_venta_bienes_NO_USAR"] in ing:
            alerta("MEDIA", f"{m['name']}: ingreso en {cu['ingreso_venta_bienes_NO_USAR']} (venta de bienes); reclasificar a servicios.")
        if cliente in rel and rel[cliente]["cxc"] not in cxc:
            alerta("MEDIA", f"{m['name']}: CxC en {', '.join(cxc)} (no relacionada); debe ir a {rel[cliente]['cxc']}.")

    # ── 3. Cuadre intercompañía ───────────────────────────────────────
    p("\n## 3. Cuadre intercompañía (VIX vs. libros del cliente)")
    p("| Factura VIX | Cliente | Total VIX | Estado VIX | Doc. en cliente | Total en cliente | Estado en cliente | Nota |")
    p("|---|---|---|---|---|---|---|---|")
    contra = {}
    for nombre, info in rel.items():
        c = info["company_id"]
        contra[nombre] = od.sr("account.move",
                               [["company_id", "=", c], ["partner_id.name", "ilike", "VIX"],
                                ["move_type", "in", ["in_invoice", "in_refund"]]],
                               ["name", "ref", "date", "state", "amount_total", "amount_residual",
                                "payment_state", "currency_id"], cia=c)
    cxc_real = 0.0
    for m in fact:
        cliente = m["partner_id"][1] if m["partner_id"] else "?"
        num = m["name"].replace("Fact ", "")
        cand = [b for b in contra.get(cliente, []) if num in (b["name"] or "") or num in (b["ref"] or "")]
        if not cand:
            nota = "**No existe en el cliente**"
            if cliente == "VICOMER S.A.S." and m["date"] < "2026-08-01":
                nota += " (anterior a la migración: revisar en Perseo)"
            alerta("ALTA", f"{m['name']} ({cliente}, {usd(m['amount_total'])}) no está registrada en el cliente.")
            p(f"| {m['name']} | {cliente} | {usd(m['amount_total'])} | {m['payment_state']} | — | — | — | {nota} |")
            cxc_real += m["amount_residual"]
            continue
        b = cand[0]
        mon = b["currency_id"][1]
        nota = ""
        if mon == "USD" and abs(b["amount_total"] - m["amount_total"]) > reg["tolerancias"]["intercompania_usd"]:
            nota = f"Diferencia {usd(b['amount_total'] - m['amount_total'])}"
            alerta("ALTA", f"{m['name']}: monto distinto en {cliente}.")
        if mon != "USD":
            nota = f"TRM implícita {b['amount_total'] / m['amount_total']:,.2f}"
        pagada_cli = b["payment_state"] in ("paid", "in_payment")
        if pagada_cli and m["payment_state"] not in ("paid", "in_payment"):
            nota = (nota + "; " if nota else "") + "**Pagada por el cliente, cobro no registrado en VIX**"
            alerta("ALTA", f"{m['name']}: {cliente} la registra pagada; VIX la tiene por cobrar.")
        else:
            cxc_real += m["amount_residual"]
        p(f"| {m['name']} | {cliente} | {usd(m['amount_total'])} | {m['payment_state']} | {b['name']} "
          f"| {mon} {usd(b['amount_total'])} | {b['payment_state']} | {nota} |")

    cxc_libro = sum(m["amount_residual"] for m in fact)
    p(f"\n- CxC según libros VIX: **{usd(cxc_libro)}**")
    p(f"- CxC según los libros de los clientes: **{usd(cxc_real)}**")
    p(f"- Diferencia (cobros sin registrar en VIX): **{usd(cxc_libro - cxc_real)}**")

    # ── 4. Meses sin factura ──────────────────────────────────────────
    p("\n## 4. Continuidad de la facturación mensual")
    if fact:
        ini = dt.date.fromisoformat(fact[0]["date"]).replace(day=1)
        meses, d = [], ini
        ult_cerrado = (HOY.replace(day=1) - dt.timedelta(days=1)).replace(day=1)
        while d <= ult_cerrado:
            meses.append(d.strftime("%Y-%m"))
            d = (d + dt.timedelta(days=32)).replace(day=1)
        for nombre in reg["facturacion_intercompania"]:
            if nombre.startswith("_") or nombre == "dia_emision":
                continue
            tiene = {m["date"][:7] for m in fact if m["partner_id"] and m["partner_id"][1] == nombre}
            falt = [x for x in meses if x not in tiene]
            p(f"- {nombre}: meses facturados {', '.join(sorted(tiene)) or '—'}"
              + (f" · **sin factura: {', '.join(falt)}**" if falt else " · completo"))
            if falt:
                alerta("BAJA", f"{nombre}: meses sin factura {', '.join(falt)} (confirmar si es intencional).")

    # ── Resumen de alertas ────────────────────────────────────────────
    orden = {"ALTA": 0, "MEDIA": 1, "BAJA": 2}
    resumen = ["## Alertas", "| # | Severidad | Hallazgo |", "|---|---|---|"]
    for i, (s, t) in enumerate(sorted(ALERTAS, key=lambda a: orden[a[0]]), 1):
        resumen.append(f"| {i} | {s} | {t} |")
    resumen.append("")
    informe = "\n".join(L[:2] + resumen + L[2:])

    out = AQUI / "salida"
    out.mkdir(exist_ok=True)
    f = out / f"diagnostico_{HOY.isoformat()}.md"
    f.write_text(informe, encoding="utf-8")
    print(informe)
    print(f"\nGuardado en {f}")


if __name__ == "__main__":
    main()
