# Estados Financieros Ejecutivos — Perseo (Ecuador)

Resumen ejecutivo de estados financieros de **VICOMER S.A.S.**, construido
**directamente desde el mayor contable de Perseo** (asientos), sin intermediarios.

## Qué produce
Un **one-pager en Excel** con:
- **Síntesis ejecutiva (8 KPIs):** Ventas Netas, Utilidad Bruta, Utilidad Operativa,
  Utilidad Neta, Margen Bruto, Margen Neto, Liquidez Corriente, Endeudamiento.
- **Estado de Resultados:** último mes cerrado + acumulado del año (YTD) + % sobre ventas.
- **Balance General:** activo/pasivo corriente y no corriente, patrimonio y
  resultado del ejercicio, con **cuadre contable** visible.
- **Indicadores clave:** liquidez, prueba ácida, capital de trabajo, endeudamiento,
  deuda financiera/patrimonio, márgenes, ROE, ROA.

Salida en `Finanzas/`:
- `Estados_Financieros_Ejecutivo_YYYY-MM.xlsx` (histórico por mes)
- `Estados_Financieros_Ejecutivo_ULTIMO.xlsx` (siempre el más reciente)

## Cómo funciona (lógica contable)
- Endpoint: `POST https://perseo-data-c1.app/api/asientoscontables_consulta`
  (filtra por rango de fechas; devuelve `detalle[]` con `codigocontable` e `importe`).
- El `codigocontable` de Perseo = plan de cuentas **sin puntos**
  (`1.1.02.05.01` → `11020501` = Clientes).
- `importe > 0` = débito, `importe < 0` = crédito.
- Estructura PUC: `1` Activo · `2` Pasivo · `3` Patrimonio · `4` Ingresos ·
  `5` Egresos (`51` Costo, `52` G.Ventas, `53` G.Admin, `54` G.Financieros, `55` No Deducibles).
- **Balance** = saldos acumulados (cuentas 1/2/3) hasta el corte.
  **Estado de Resultados** = movimientos (cuentas 4/5) del período.
- Como todo asiento cuadra, la identidad **Activo = Pasivo + Patrimonio** se cumple
  por construcción. Si `Cuadre ≠ 0`, revisar el `AÑO_ARRANQUE` (deben incluirse los
  saldos de apertura).

## Instalación (una sola vez)
Doble clic en **`instalar_eeff.command`** (o en Terminal):
```
bash "/Users/juanmarcelo/Claude/Projects/CFO VICOMER/instalar_eeff.command"
```
Instala el LaunchAgent `com.vcomer.eeff` → corre el **día 4 de cada mes a las 08:00**.

Requiere el `api_key` de Perseo en `~/.perseo_apikey` (el mismo que usan tus otras
automatizaciones de Perseo).

## Uso manual
```
python3 "…/perseo_estados_financieros.py"            # último mes cerrado + YTD
python3 "…/perseo_estados_financieros.py" 2026-06     # corte a fin de jun-2026
python3 "…/perseo_estados_financieros.py" 2026-06 2019 # + año de arranque del mayor
```

## Notas
- La muestra `Estados_Financieros_Ejecutivo_MUESTRA_2025-08.xlsx` se generó con datos
  del **modelo de Tesorería** (hasta ago-2025) para ver el formato; el script la
  reemplaza con datos **en vivo de Perseo** al ejecutarse.
- El cuadre de la muestra (−14.6k) es un artefacto de reclasificación del modelo;
  con asientos de Perseo el cuadre es ~$0.
- Ratios y estructura alineados con el `Modelo de Analisis Financiero.xlsm`.
