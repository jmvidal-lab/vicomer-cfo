# Estado del CFO VICOMER al 27-nov-2026

## Tablero

- La última versión publicada es la **v16, con corte al 30-oct-2026** (TRM 3.166,91).
- **Desde el 6-nov no se actualiza (4 viernes seguidos).** La regresión contra el estado firmado al 31-jul-2026 falla porque contabilidad sigue registrando y modificando asientos con fecha de julio, y no hay fecha de bloqueo en Odoo (Ecuador ni Colombia).
- Diferencias de hoy contra las esperadas:

  | Concepto | Diferencia esperada | Diferencia hoy |
  |---|---:|---:|
  | Ecuador, resultado de julio | 0 | −705,07 |
  | Ecuador, patrimonio | −0,01 | −705,08 |
  | Ecuador, activo | −4.339 | +55.569 |
  | Colombia, activo | −227,0 M COP | −210,5 M COP |

- **Para destrabarlo:**
  1. Poner la fecha de bloqueo al 31-jul en las dos empresas.
  2. Elegir una de estas dos salidas:
     - re-firmar julio y actualizar las diferencias esperadas en `eeff_odoo.py`, usando el estado firmado como fuente;
     - registrar los ajustes pendientes con fecha del mes en curso.

## Hallazgos abiertos (informe CFO del 27-nov)

1. **Colombia debe a HYXION 263.782.546 COP**, vencidos desde el 16-sep (DS/2026/07/0011).
2. **Vehículos de Ecuador vendidos a socios.** El 13-nov se facturaron dos vehículos a Juan Marcelo Vidal Torres (001-001-000002155, por 12.754,67) y a María Daniela Vidal Torres (001-001-000002157, por 8.629,21).
   - Se registraron como venta de mercadería y siguen sin cobrar.
   - Deben registrarse como baja de activo fijo, con avalúo.
3. **Intercompañía descuadrada por 52.954 USD.** Ecuador tiene 179.236 por cobrar a VINTRAL y Colombia reconoce 735,3 M COP por pagar a VICOMER.
   - Además, la FE371 parece tener IVA del 19% en una exportación.
4. **Colombia tiene 800 M COP de capital suscrito sin pagar.**
5. **Cuenta 101.04.03.02 mal clasificada.** «Anticipo proveedores del exterior» está tipificada como «por pagar» desde el 5-nov; debería ser activo.
6. **Bancos de Ecuador.** Banco Guayaquil tiene 5 partidas sin conciliar y Produbanco 15. Procredit no tiene extractos después del 31-ago.
   - La Cuenta transitoria 11010201 bajó a 65.743.
7. **Provisiones que no están en el ERP.** Participación de trabajadores e impuesto a la renta de Ecuador (unos 77.000, estimado), cartera vencida a más de 90 días y obsolescencia de inventario.
8. **Contabilidad anglosajona.** Está activa desde el 1-nov en las 3 empresas.
   - Faltan categorías por configurar en Colombia (ACCESORIOS, DISPENSADORES) y en Costa Rica (9 categorías).
   - Las cuentas puente de mercadería entregada sin facturar deben conciliarse cada semana.

## Cifras al 27-nov (Odoo, sin verificar contra el estado firmado)

- **Ecuador:**
  - Ventas enero–noviembre: 1.714.840.
  - Margen bruto: 43,0%.
  - Resultado del ERP: 188.184.
  - Utilidad neta estimada: 111.224.
  - Caja: 109.224.
  - Ciclo de caja: 130 días.
- **Colombia:**
  - Ventas: 1.485,9 M COP.
  - Resultado: 254,8 M COP.
  - Caja: 133,3 M COP. Es un dato viejo: no hay extractos cargados desde el 31-oct.
  - Ciclo de caja: 310 días.

## Otros trabajos hechos

- **Auditoría de costo de ventas y paso a contabilidad anglosajona** (28-oct): `1_proyecto/Auditoria_Costo_Ventas_2026-10.md`.
- **Plan comercial de inventario para el equipo** (29-oct): `2_tablero/inventario_por_mover.html`.
- **Análisis de la compra de la nave en Tarqui.** Una nave de 200.000 con crédito del Banco del Austro a 36 meses al 9%. La recomendación fue esperar a que los bancos estén conciliados y a ver cómo cierra noviembre.
