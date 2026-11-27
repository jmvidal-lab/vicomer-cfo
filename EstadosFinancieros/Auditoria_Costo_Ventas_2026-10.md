# Auditoría del costo de ventas y paso a contabilidad anglosajona — corte 28-oct-2026

Fuente: Odoo (lectura, sin modificar nada). Montos de Ecuador en USD y de Colombia en COP.
"Costo esperado a la factura" = cantidad facturada × costo promedio **actual** del producto. Es una
aproximación: Odoo usará el costo de la capa de inventario de cada entrega.

## 1. Diagnóstico

**El costo registrado es correcto para el método que Odoo tiene configurado hoy (continental).**
El costo de ventas sigue a las entregas y no a las facturas. Ningún mes tiene un error de valoración
material. Lo que se ve "raro" son desfases de tiempo, más cuatro errores puntuales.

### Ecuador — el costo cuadra con las entregas

| Mes | Costo registrado | Entregas − devoluciones | Costo esperado a la factura |
|---|---:|---:|---:|
| Ago | 73.090,27 | 73.112,87 | 92.514,99 |
| Sep | 33.738,43 | 33.738,43 | 109.317,57 |
| Oct | 81.845,61 | 81.845,61 | 79.168,67 |
| **Total** | **188.674,31** | | **281.001,23** |

- La brecha de ~92.000 es mercadería **facturada y todavía no entregada**: 76 líneas por un costo de
  **96.482**. Las órdenes más grandes son S00180 (48.774), S00263 (16.406) y S00236 (9.962).
- Margen bruto a la factura: 42,2% en agosto, 38,1% en septiembre y 38,3% en octubre. El 16% de
  septiembre que muestra el registro contable es un efecto de calendario, no de margen.

### Colombia — cuadra en el acumulado, no mes a mes

| Mes | Costo registrado | Costo esperado a la factura |
|---|---:|---:|
| Abr | 0 | 143,97 M |
| May | 0 | 49,47 M |
| Jun | 21,61 M | 75,14 M |
| Jul | 279,73 M | 26,67 M |
| Ago | 120,39 M | 131,33 M |
| Sep | 79,61 M | 91,06 M |
| Oct | 46,45 M | 34,10 M |
| **Total** | **547,79 M** | **551,74 M** |

- La diferencia acumulada es de 3,9 M (0,7%), que está dentro del error de usar el costo promedio actual.
- Abril y mayo: las entregas (11,66 M y 9,95 M) se contabilizaron en junio. El grueso de lo facturado
  se despachó en julio.
- Agosto: 93,38 M corresponden a la venta intercompañía a VICOMER S.A.S. (WH/OUT/00143, factura
  FE371 por 100,30 M, IMPO 056). La operación es legítima, con un margen de 6,9%, y explica el
  margen de 30% de ese mes. El tablero debería mostrarla aparte, porque en el consolidado se elimina.

### Errores puntuales (para que contabilidad los corrija)

| # | País | Hallazgo | Monto | Ajuste propuesto |
|---|---|---|---:|---|
| 1 | CO | Costo de VINERAS (TWC24UL, ago y oct) cargado a **502.01.23.03 "Costos de producción"**, que es una cuenta de gasto de ventas | 6.559.035,90 | Dr 501.06.01.01 / Cr 502.01.23.03 |
| 2 | CO | Facturas de proveedor imputadas directo a costo de ventas: CP/2026/09/0014 (FEIP-11009147) y CP/2026/09/0030 (SRP-267732) | 878.000 + 12.199,99 | Revisar el soporte. Si es flete de compra, va al costo del inventario (landed cost), no al costo de ventas |
| 3 | CO | Capas de inventario sin asiento contable (abr 1, jul 2, ago 1, oct 1) | revisar | Identificarlas y contabilizarlas |
| 4 | CO | 2 líneas entregadas sin facturar (S00137) | 1.046.652 de costo | Facturar o explicar |

## 2. Supuesto que conviene cuestionar

La contabilidad anglosajona **mueve el costo para que coincida con la factura. No vuelve correcto el
ingreso.** Si se factura antes de entregar (Ecuador tiene 96.000 de costo en esa situación), la NIIF 15
reconoce el ingreso cuando se transfiere el control, que normalmente es la entrega. La única excepción
es un *bill-and-hold* documentado. Con el método anglosajón, el margen va a "verse bien", pero el
ingreso y el costo pueden estar los dos adelantados.

**Recomendación:** que contabilidad defina la política. Lo ideal es facturar contra despacho; si no,
documentar los casos de bill-and-hold.

## 3. Configuración para el 1-nov (checklist)

**Bloqueantes: si no se arreglan antes de activar el método, el costo sale mal desde el primer día.**

1. **Ecuador: la cuenta de gasto de las categorías es 110307 "Mercaderías en tránsito"**, que es un
   activo. Con el método anglosajón, el costo de cada factura iría a esa cuenta. Debe cambiarse a
   **501.06.01.01.2 COSTO DE VENTAS** en todas las categorías vendibles.
2. **Cuenta de salida de stock:** hoy apunta a COSTO DE VENTAS (EC 501.06.01.01.2) y a
   502.01.23.03 (CO). Debe apuntar a una **cuenta puente nueva, "Mercadería entregada por facturar"**
   (pasivo o activo corriente transitorio; el código lo asigna contabilidad), una por empresa.
3. **Cuenta de entrada de stock:** debe ser una cuenta puente "Recibido por facturar", que hoy no existe.
4. **Todas las categorías vendibles en valoración automatizada y costo promedio.** Las siguientes
   están en periódica/manual y con el método anglosajón **no generarían costo**:
   - CO: ACCESORIOS, DISPENSADORES, All.
   - EC: All, OTROS.
   - CR: la mayoría.

   Las categorías de servicios y gastos pueden quedarse como están.
5. **Colombia: categorías sin cuenta de gasto** (MAQUINA DE HIELO, CAFETERAS, OTROS, Otros Cargos,
   VINERAS). Hay que asignarles 501.06.01.01.
6. Activar **Contabilidad anglosajona** en Ajustes de Contabilidad de cada empresa.

### Asientos de corte al 31-oct (para no duplicar ni perder costo)

Los documentos que cruzan la fecha de cambio necesitan un asiento manual. Los montos deben
recalcularse el 31-oct con los datos finales.

| Situación al 31-oct | Qué pasaría sin ajuste | Asiento al 31-oct |
|---|---|---|
| Facturado y no entregado (EC 96.482 · CO 29,28 M · CR 18.500) | La entrega de noviembre carga la cuenta puente y nadie la descarga; ese costo nunca llega al P&G | **Dr Costo de ventas / Cr Cuenta puente** |
| Entregado y no facturado (CO 1,05 M) | El costo ya entró en octubre y la factura de noviembre lo vuelve a cargar: **doble costo** | **Dr Cuenta puente / Cr Costo de ventas** |

Después del cambio, **conciliar la cuenta puente cada mes**. Su saldo debe ser igual al costo de lo
entregado y no facturado. Si no lo es, hay un error.

## 4. Qué cambia en el tablero desde noviembre

- La regla "el margen no se publica si el costo no es creíble" debería dejar de dispararse.
  Si se dispara, la configuración quedó mal.
- Se agrega un control: el saldo de la cuenta puente frente a la lista de entregas sin facturar.
- La venta intercompañía de Colombia se muestra aparte.
