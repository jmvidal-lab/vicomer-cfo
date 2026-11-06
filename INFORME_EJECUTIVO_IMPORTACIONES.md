# Informe Ejecutivo — Documento Maestro de Importaciones
**VICOMER / VINTRAL · Generado: 2026-07-01 (trabajo nocturno) · Analista: Claude (CFO asistente)**

Archivo principal: `MAESTRO_IMPORTACIONES_VICOMER.xlsx` (9 hojas). Este informe resume método, números y hallazgos. Regla acordada: **el DAI es la última palabra**.

---

## 1. Alcance procesado

| | Ecuador | Colombia | Costa Rica |
|---|---|---|---|
| Entidad | VICOMER S.A.S. (RUC 0190499332001) | VINTRAL S.A.S. (NIT 901918160-1) | 3-102-940094 SRL |
| Carpetas de impo analizadas | 55 (001–054 + USA Coolers, 037 en 2 embarques) | 11 | 1 |
| Ítems (líneas modelo-impo) | 510 | 78 | 14 |
| Unidades ingresadas | **10.219** | **1.785** | **187** |
| Costo total costeado | **USD 3.066.983** | USD ~423K equiv. (3 costeadas; 006 en COP 293,1M) | Sin costeo (DUA: CIF 35.360,76 + imp. 7.655,90) |
| DAIs/DUAs validados | 46 | vía DIAN/recibos (parcial, varios escaneados) | DUA 005-2026-343069 |

Se procesaron 68 archivos de costeo, 111 documentos aduaneros, el Libro Mayor completo (51 cuentas de importación) y 1.843 facturas + 143 NC + 126 anuladas.

**Nota técnica:** ~40% de los archivos eran placeholders de iCloud sin descargar; se forzó la descarga automáticamente. Quedaron ~40 PDFs no críticos (manuales/etiquetas) sin materializar.

## 2. Validación contra DAI — hallazgo principal

**FOB pagado vs FOB declarado.** En 2023–2024 el FOB de los costeos (pagos reales a proveedor) supera sistemáticamente el FOB declarado en aduana:

| Impo | Brecha | Impo | Brecha |
|---|---|---|---|
| 007 | **+129%** | 016 | +23% |
| 015 | **+116%** | 012 | +23% |
| 011 | +42% | 009 | +19% |
| 020 | +39% | 013 | +16% |
| 021 | +26% | 014 | +12% |

En 2025–2026 la brecha prácticamente desaparece (cuadres exactos en 027, 036, 041, 048, 049, 054). Esto es un **riesgo de valoración aduanera/tributario** sobre el período 2023–2024 que merece evaluación con tu agente de aduana. La impo **006 (2022)** además no tiene DAI ni liquidación legible en carpeta y la factura del proveedor es menor a lo realmente pagado (21.992 vs 27.849).

## 3. Errores detectados en costeos (los que pediste no confiar)

1. **Unidades "invisibles"**: el DAI declara unidades que el costeo no incluye → impo **051**: 555 repuestos (FOB 277,50); **047**: 1 IGMAX; **046**: 17 repuestos; **034**: 10 paneles DKXRF. Efecto: costo unitario levemente sobrestimado y unidades que no existirán en kardex.
2. **Impo 039** (knobs/spare parts): el pago de $755 se absorbió en el costeo de la **032**, pero las 10 unidades no están costeadas en ninguna impo.
3. **Impo 052/050**: pago de $2.653,50 con glosa "29 H9" archivado en la carpeta 050 — cruzar a qué impo pertenece.
4. **Posible tasa INEN duplicada** en impo 051 ($247, liquidaciones L000023975 y L000023453).
5. **Plantillas recicladas**: hojas tituladas "IMP 022"/"IMP 031"/"IMP 037-2" en costeos de otras impos; el "COSTEO IMP 010" es en realidad una versión previa del de la 013 (la 010 quedó **sin costeo real**); "FORMATO COSTEO IMPO 051" es copia del 047. Riesgo alto de arrastre de errores.
6. **Códigos alias** entre costeos (TRF2401≡TRF24U, HRT3618U≡HRT3606-LP, IG-20≡IG20…) — normalizados en la hoja KARDEX ENTRADAS.
7. **Costa Rica impo 001**: pagos a Hyxion por **$72.617** vs CIF declarado **$35.361** (49%) y 90 bultos vs 187 unidades — verificar si es nacionalización parcial o factura multi-embarque.
8. **Seguro**: el costeo casi nunca coincide con el seguro del DAI (el DAI aplica ~1% FOB). Impacto menor pero sistemático.

## 4. Cruce con Libro Mayor (sistema)

- Las **51 cuentas** 1.1.03.07.xx **cierran a saldo 0**: todo lo cargado fue transferido a inventario. Total procesado: **USD 3.266.347**.
- Diferencias mayor vs costeo (mayor > costeo, gastos registrados que el costeo no recoge o viceversa): 008 (+6.500), 035 (+5.127), 002 (+2.245), 004 (+2.033), 032 (+1.105), USA Coolers (+1.015), 026 (+660), 041 (+337), entre otras — detalle en hoja CRUCE LIBRO MAYOR.
- **Sin cuenta en el mayor**: impos 039, 042, 050, 052, 053 (en tránsito/sin nacionalizar) y las operaciones de Colombia/Costa Rica (entidades distintas — correcto).
- Asientos con glosa "IMPO 47"/"IMPO 54" cargados en la cuenta de la **049** — revisar reclasificación.

## 5. Ventas y devoluciones (2021 → 01-jul-2026)

| Año | Facturas | Ventas s/IVA | NC total | NC devolución 100% | Ventas netas c/IVA |
|---|---|---|---|---|---|
| 2021 | 77 | 71.277 | — | — | 76.456 |
| 2022 | 169 | 258.096 | — | — | 264.849 |
| 2023 | 412 | 685.300 | −12.142 | −6.775 | 714.163 |
| 2024 | 366 | 1.249.551 | −35.737 | −13.058 | 1.379.524 |
| 2025 | 500 | 1.763.344 | −120.848 | −56.248 | 1.895.001 |
| 2026* | 319 | 1.118.417 | −108.871 | −80.992 | 1.173.424 |
| **Total** | **1.843** | **5.145.984** | **−277.598** | **−157.073** | **5.503.418** |

Criterio aplicado (el tuyo): solo cuentan como devolución las NC que reversan el **100%** del valor de la factura (65 facturas, $157.073). Las 81 NC parciales (mediana 5,7% de la factura) se tratan como ajustes/descuentos, sin reingreso de producto. Las 126 facturas anuladas se excluyeron. Ojo con la aceleración de NC en 2025–2026 (~9,7% de la venta 2026) — vale revisar causa comercial.

## 6. Saldos de inventario — CERRADO (actualización 02-jul-2026)

Con el detalle de ítems por factura (API Perseo `facturas_consulta` + reporte "Venta facturas", validados 1:1 con 3.655 líneas idénticas) el kardex quedó **completo**, con códigos unificados (26 alias mapeados — hoja MAPEO ALIAS, ej.: iG-35P≡SK-35C, TMO30≡TMO30H, TRF2401≡TRF24U con cuadre exacto 25/25, combos explotados en componentes):

| Concepto | Valor |
|---|---|
| Entradas (impos, validadas DAI) | 10.219 uds |
| Salidas (facturas con ítems) | 7.318 uds |
| Reingresos (NC devolución 100%) | 282 uds |
| **Stock actual** | **3.824 uds (198 modelos) · USD 653.068 al costo de importación** |
| Inventario implícito contable (Mayor − COGS Perseo) | USD 482.788 |
| Brecha (códigos por corregir, costo Perseo ≠ costo impo, compras locales) | USD 170.280 |

**INVENTARIO PRODUCTOS TIPO O (OBSOLETOS)** — tu número final: modelos con stock **sin ventas en los últimos 12 meses**:

> **117 modelos · 1.214 unidades · USD 120.481 al costo** (hoja INVENTARIO TIPO O; criterio de 12 meses ajustable)

Top obsoletos por valor: IG35P/SK-35C ($13.470, última venta 2023), MK04SS304-typo ($11.024), KD23 kamado ($10.318), IG280 ($9.290), KD18 ($9.154), HRT4806LP ($8.503), IBBQ ($7.765, de 2021), montacargas impo 018 ($3.679, nunca vendido). Es el ~18% del valor del inventario — candidato a liquidación/promoción.

**Pendientes de aclarar** (hoja MAPEO ALIAS, en amarillo): IGW15 (ventas 150 "frigobar 32L" vs entradas 40 "beer cooler 170L"), S7/S9 (cafeteras vendidas > entradas; H7 con 130 uds sin venta — posible venta cruzada de código), IG35 vs IG35P (saldos espejo -25/+54).

**Traslados intercompañía identificados** (salen de VICOMER EC, entran a VINTRAL CO): facturas 1159 (USD 7.466), 1248 (USD 8.560), 1611 (USD 24.448) + terrestre 040/COL-001 (mismo DAI 073-2025-10-01704059, sin doble conteo). Nota pendiente en Colombia: "FALTA NC de 5 MK04" (impo 009 COL). El kardex de Colombia/Costa Rica requiere las ventas de VINTRAL (sistema aparte).

## 6.b Cruce contra conteo físico (Juan José, 01-jul-2026)

Triple cruce sobre los 78 códigos de equipos del REPORTE BODEGAS (hoja CRUCE CONTEO FÍSICO; kardex ajustado excluyendo impos en tránsito 042/050/052/053):

| | Físico | Sistema Perseo | Kardex teórico |
|---|---|---|---|
| Unidades (equipos) | **1.246** | 1.335 | 949 |

Valor del inventario físico de equipos al costo de importación: **USD 435.055**. Resultado del diagnóstico: 37 códigos cuadran (±3), 19 con **código cruzado en facturación** (sistema/kardex negativos con stock físico real: IGW15, S7, S9, IG35, IG36, IGBW, TMO30, TEW30ES…), 8 con **faltante físico** a investigar y 12 mixtos.

Los 3 faltantes gordos: **IGBEER −132 uds** (sistema 142-145 vs 13 físicas — la impo 046 ingresó 165 en feb-2026; ¿dónde están?), **HHTAZA −45** (tazas promo entregadas sin descargar del sistema) y **H9 −14**. El resto de ítems fuera del reporte de bodegas quedó clasificado en la hoja CATEGORIZACIÓN RESTO: repuestos/filtros (28), promocionales (709 uds en sistema, casi todo sin descargar al regalarse: TB-THR 200, TEMP/DNTL/NTBK/PEN 100 c/u), accesorios (412 uds), variantes de código duplicado a fusionar en Perseo (_US, _COL, -RS, KD-18 colores, combos), y productos locales/terceros (GE, Elica, Ooni).

## 7. Acciones recomendadas (prioridad)

1. **Alto**: evaluar exposición por valoración aduanera 2023–2024 (sección 2) y regularizar documentación de la impo 006.
2. ~~Conseguir ventas por producto~~ **HECHO** — kardex e inventario tipo O cerrados el 02-jul. Nuevo: decidir plan de liquidación de los $120K obsoletos y corregir en Perseo los 3 códigos pendientes (IGW15, S7/S9, IG35).
3. **Medio**: aclarar Costa Rica 001 (CIF vs pagos), reclasificar asientos de la 049, cruzar pago "29 H9" (050/052), verificar INEN duplicado (051).
4. **Medio**: registrar las unidades no costeadas (051, 047, 046, 034, 039) para que el kardex físico cuadre.
5. **Bajo**: unificar catálogo de códigos (alias) y dejar de reciclar plantillas de costeo — un formato estándar con validaciones evitaría el 80% de los errores detectados.
