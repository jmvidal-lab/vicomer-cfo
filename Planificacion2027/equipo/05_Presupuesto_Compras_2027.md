# PRESUPUESTO DE COMPRAS 2027

**12-nov-2026** · **Libro:** `Presupuesto_2027_Ventas_Compras_Gastos.xlsx`, hojas `Compras 2027` y `Plan compras SKU`. Todo se recalcula desde el presupuesto de ventas y los supuestos en azul.

---

## 1. Cómo se construye

1. **Costo de ventas** = venta de cada canal × (1 − margen bruto objetivo del canal), mes a mes.
2. **Inventario objetivo:** baja o sube en línea recta desde el inventario actual hasta la cobertura objetivo al cierre de 2027.
3. **Recepciones** = costo de ventas del mes + (inventario objetivo − inventario del mes anterior). Nunca negativas: si sobra stock, no se compra.
4. **Compras FOB** = recepciones ÷ factor de costo puesto (landed / FOB) medido en el maestro de importaciones.
5. **Pedido** = se coloca tres meses antes de la recepción (producción + tránsito).

| Segmento | Inventario inicial | Cobertura objetivo | Factor landed / FOB | Proveedor principal |
|---|---|---|---|---|
| Ecuador núcleo (Thor, iGlace, cafeteras) | USD 504 k (almacén + tránsito) | 4 meses | 1,37 (medido) | Hyxion |
| Ecuador HiHeat | 0 | 4 meses | 1,35 (modelo HiHeat) | ARDA |
| Colombia | COP 1.025 M (almacén + impo 011 en tránsito) | 6 meses | 1,19 (medido) | Hyxion |
| Costa Rica | 0 | 0 (contra pedido) | 1,30 (supuesto) | Hyxion |

## 2. Resultado (escenario base)

| Segmento | Costo de ventas 2027 | Compras FOB 2027 (USD) | Inventario final | Cobertura final |
|---|---|---|---|---|
| Ecuador núcleo | USD 1.317.800 | **914.406** | USD 439.267 | 4,0 meses |
| Ecuador HiHeat | USD 162.000 | **160.000** | USD 54.000 | 4,0 meses |
| Colombia | COP 1.056 M | **146.709** (COP 469 M) | COP 528 M | 6,0 meses |
| Costa Rica | USD 168.000 | **129.231** | 0 | contra pedido |
| **Grupo** | | **≈ USD 1.350.000** | | |

**Por proveedor (FOB USD):**

| Hyxion (Thor) | iGlace (HICON, Candor y otros) | Ningbo Hawk (cafeteras) | ARDA (HiHeat) | Otros |
|---|---|---|---|---|
| **890.401** | 192.025 | 89.632 | 160.000 | 18.288 |

- **Hyxion:** USD 890 k frente al mínimo contractual de USD 600 k. Cumple con holgura.
- **Inventario del grupo:** de ≈ USD 825 k (incluye tránsito) a ≈ USD 658 k a fin de 2027, o **≈ USD 604 k sin HiHeat (−27 %)**, con 40 % más venta.

## 3. Calendario de compras

**Ecuador núcleo (recepciones landed, USD):** enero 80 k · febrero 77 k · marzo 115 k · abril 58 k · mayo 90 k · junio 109 k · julio 71 k · agosto 140 k · septiembre 159 k · octubre 89 k · noviembre 128 k · diciembre 137 k. Los picos de agosto–septiembre y noviembre–diciembre siguen la estacionalidad: **los pedidos de esos meses se colocan en mayo–junio y agosto–septiembre.**

**HiHeat:** primer contenedor del PO-ARDA-2026-002 (embarque 15-feb); reposiciones desde mayo según sell-out. El modelo reparte las compras en forma lineal; en la práctica llegan por contenedor completo.

**Colombia:** en el primer semestre casi no se compra: el inventario actual más la impo 011 en tránsito cubren la demanda. Desde el segundo semestre, el equivalente a **dos contenedores** concentrados en los SKU que rotan (MK04SS304, TMO24H, TRG3601). **No se compran** TEW30ES, TMO30H, HRT3618U-M1 ni HDW2401SS en el primer semestre.

**Costa Rica:** un contenedor por pedido confirmado de Cemaco o Panafoto; sin stock propio.

## 4. Reglas de compra 2027

1. **Ningún pedido sin la tabla de cobertura de los tres países** (stock, tránsito y demanda por SKU).
2. **Transferencias entre países antes que compras nuevas** cuando un país tiene sobrestock y otro quiebre.
3. **Firma doble** en proformas sobre USD 50 k.
4. **Cada embarque cierra con su expediente completo** (declaración, liquidación, certificaciones y costeo) antes del pago final al agente.
5. **Revisión mensual** de compras en el S&OP regional: lo que no rota en 90 días frena el siguiente pedido de ese SKU.

## 5. Supuestos a confirmar

- Nueva lista FOB de Hyxion: cambia el factor y el monto, no la lógica.
- Términos de pago por proveedor (Hyxion 20/40/40, ARDA 30/70).
- Mezcla por proveedor en Ecuador: se tomó la de 2026 (Thor 68 %, iGlace 21 %, cafeteras 9 %).
