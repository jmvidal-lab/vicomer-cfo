# Reporte de conciliación — Dashboards de Ventas VICOMER

Extracción: **2026-08-19T22:36:24** · Año 2026 · Mes de cierre **Jul**

Fuente: Odoo `https://vicomer.odoo.com`, db `intitecnologia-v-comer-main-27740127`, 79 llamadas XML-RPC.

## 1. Cuadre línea por línea

| | País | Concepto | Dashboard | Referencia | Diferencia |
|---|---|---|---|---|---|
| ✅ | Ecuador | YTD real vs estado_grupo.json | 1.117.243,89 | 1.117.243,89 | 0,00 |
| ✅ | Ecuador | Histórico pre-migración vs ecuador_hist_mensual | 1.117.243,89 | 1.117.243,89 | 0,00 |
| ✅ | Ecuador | Curva mensual de presupuesto vs presupuesto anual | 2.290.147,00 | 2.290.147,00 | 0,00 |
| ✅ | Colombia | YTD real vs estado_grupo.json | 933.278.870,49 | 933.278.870,49 | 0,00 |
| ✅ | Colombia | Histórico pre-migración vs colombia_hist_mensual | 262.321.140,79 | 262.321.140,79 | 0,00 |
| ✅ | Colombia | Curva mensual de presupuesto vs presupuesto anual | 3.671.996.149,00 | 3.671.996.149,00 | 0,00 |
| ✅ | Costa Rica | YTD real vs estado_grupo.json | 83.947,00 | 83.947,00 | 0,00 |
| ✅ | Costa Rica | Curva mensual de presupuesto vs presupuesto anual | 300.002,00 | 300.002,00 | 0,00 |

**Resultado: TODO CUADRA** — 8 de 8 líneas al centavo.

## 2. Cifras por país

| País | Moneda | YTD real | Ppto YTD | Cumpl. | MTD Ago | Ppto Ago | Cumpl. mes | Run-rate anual | vs ppto anual |
|---|---|---|---|---|---|---|---|---|---|
| Ecuador | USD | 1.117.243,89 | 1.095.845,00 | 102.0% | 110.277,95 | 259.382,00 | 42.5% | 1.915.275,24 | 83.6% |
| Colombia | COP | 933.278.870,49 | 1.566.617.209,00 | 59.6% | 158.932.301,62 | 419.173.505,50 | 37.9% | 1.599.906.635,13 | 43.6% |
| Costa Rica | USD | 83.947,00 | 129.167,00 | 65.0% | 2.250,00 | 34.167,00 | 6.6% | 143.909,14 | 48.0% |

Consolidado (USD **referencial**, COP 3,700 / USD, CRC 452): YTD **1.453.428,17**, ppto YTD 1.648.421,63 = **88.2%**. Run-rate 2.491.591,15 contra ppto anual 3.582.579,40.

## 3. Curva mensual de presupuesto — fila localizada por validación

| País | Hoja | Fila | Columnas | Suma anual | Coincide con | Error |
|---|---|---|---|---|---|---|
| Ecuador | ECUADOR 2026 | 39 | 4-15 | 2.290.147,00 | estado_grupo.json | 0 |
| Colombia | COLOMBIA 2026 | 23 | 4-15 | 3.671.996.149,00 | estado_grupo.json | 0 |
| Costa Rica | COSTA RICA 2026 | 14 | 4-15 | 300.002,00 | estado_grupo.json | 0 |

## 4. Margen bruto

| País | Estado | Margen YTD | Venta contable | COGS | Desglose mensual |
|---|---|---|---|---|---|
| Ecuador | calculable | 43.3% | 1.227.676,01 | 695.716,84 | confiable |
| Colombia | calculable | 58.2% | 1.092.808.894,00 | 457.168.901,13 | **no confiable** |
| Costa Rica | **NO calculable** | — | — | — | **no confiable** |

## 5. Cartera, DSO y concentración

| País | Cartera | % vencido | % vencido +30d | DSO puntual | Días de pago real | HHI | HHI terceros | Cobertura del detalle |
|---|---|---|---|---|---|---|---|---|
| Ecuador | 293.627,48 | 16.2% | 12.7% | 43 d | 4 d | 7,205 | 7,209 | 9% |
| Colombia | 859.501.280,55 | 61.1% | 42.2% | 181 d | 80 d | 4,049 | 5,049 | 76% |
| Costa Rica | 69.001,28 | 100.0% | 91.2% | 64 d | 31 d | 10,000 | 10,000 | 100% |

## 6. Avisos vigentes (22)

### Críticos

- **Costa Rica · margen** — Margen calculado 100% — implausible en distribución. El costo no se está registrando completo. Se declara como no confiable.
- **Ecuador · concentración** — El desglose por cliente sólo cubre el 9% del YTD de Ecuador: el resto viene del histórico pre-migración, que no trae cliente. El HHI y el top de clientes describen ESE 9%, no el año completo — no los leas como la foto anual.

### Alertas

- **Grupo · consolidado** — Ecuador concentra el 77% de la venta del grupo (USD referencial): el grupo es, en la práctica, ese país.
- **Grupo · consolidado** — Colombia explica el 72% de la desviación total contra presupuesto del grupo.
- **Grupo · presupuesto** — El presupuesto de referencia (estado_grupo.json) tiene 2 días de antigüedad (generado 2026-08-17T10:10:10). El real es de hoy; el presupuesto puede estar desfasado.
- **Colombia · clientes** — 12% de la venta registrada de Colombia es INTERCOMPAÑÍA (VICOMER S.A.S.): no es venta a terceros ni cartera de mercado. El HHI de terceros, sin ella, es 5049.
- **Colombia · concentración** — HHI 4048 (>2500 = concentración crítica). CASAMAGNA S.A.S pesa 55% de la venta de Colombia: si ese cliente se va o renegocia, el país no tiene con qué reemplazarlo en el año.
- **Colombia · concentración** — El desglose por cliente sólo cubre el 76% del YTD de Colombia: el resto viene del histórico pre-migración, que no trae cliente. El HHI y el top de clientes describen ESE 76%, no el año completo — no los leas como la foto anual.
- **Colombia · margen** — VINTRAL S.A.S. no tiene ninguna cuenta tipificada como costo directo. El COGS se rescató por NOMBRE de: COSTO DE LA MERCANCIA VENDIDA. Corregir el tipo de cuenta en Odoo.
- **Colombia · margen** — El COGS de Colombia no está mensualizado: 4 mes(es) dan margen imposible (Abr 100%, May 100%, Jul -362%, Ago 91%). El acumulado del año sí es utilizable; la curva mensual no. Se muestra el YTD y se oculta la sierra en vez de presentarla como tendencia.
- **Colombia · mix** — Colombia: 24% de la venta del mayor no tiene producto asignado en el asiento; el mix por producto es parcial.
- **Costa Rica · concentración** — HHI 10000 (>2500 = concentración crítica). CEMACO INTERNACIONAL SOCIEDAD ANON pesa 100% de la venta de Costa Rica: si ese cliente se va o renegocia, el país no tiene con qué reemplazarlo en el año.
- **Costa Rica · margen** — 3-102-940094 SOCIEDAD DE RESPONSABILIDAD LIMITADA no tiene ninguna cuenta tipificada como costo directo. El COGS se rescató por NOMBRE de: COSTO DE LA MERCANCIA VENDIDA. Corregir el tipo de cuenta en Odoo.
- **Costa Rica · mix** — Costa Rica: no hay COGS a nivel de producto. El ranking se ordena por venta, no por margen aportado.
- **Ecuador · concentración** — HHI 7205 (>2500 = concentración crítica). COMOHOGAR S.A pesa 85% de la venta de Ecuador: si ese cliente se va o renegocia, el país no tiene con qué reemplazarlo en el año.
- **Ecuador · mix** — Ecuador: 91% de la venta del mayor no tiene producto asignado en el asiento; el mix por producto es parcial.

### Notas

- **Grupo · alcance** — Compañías excluidas del consolidado por decisión de gerencia: VIX S.A.S..
- **Colombia · clientes** — Sin comparativo contra 2025: Odoo no tiene facturas de ese año para Colombia (la operación anterior vivía en otra instancia/ERP). La columna Δ vs año anterior queda vacía a propósito.
- **Colombia · margen** — El mayor de Colombia sólo tiene movimiento de resultado en 6 de 8 meses (migración a Odoo). El margen YTD compara la venta y el costo que SÍ están contabilizados, no el año calendario completo.
- **Costa Rica · clientes** — Sin comparativo contra 2025: Odoo no tiene facturas de ese año para Costa Rica (la operación anterior vivía en otra instancia/ERP). La columna Δ vs año anterior queda vacía a propósito.
- **Ecuador · clientes** — Sin comparativo contra 2025: Odoo no tiene facturas de ese año para Ecuador (la operación anterior vivía en otra instancia/ERP). La columna Δ vs año anterior queda vacía a propósito.
- **Ecuador · margen** — El mayor de Ecuador sólo tiene movimiento de resultado en 2 de 8 meses (migración a Odoo). El margen YTD compara la venta y el costo que SÍ están contabilizados, no el año calendario completo.

