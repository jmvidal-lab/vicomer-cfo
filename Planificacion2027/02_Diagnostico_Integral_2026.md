# DIAGNÓSTICO INTEGRAL DEL GRUPO VICOMER — base para la planificación 2027

**Fecha de corte:** 6 de noviembre de 2026 · **Elaborado por:** CFO externo (Claude) · **Para:** Juan Marcelo Vidal Torres
**Fuentes primarias:** Perseo API (1.904 documentos de venta 2021–jul 2026; 43.247 líneas de mayor deduplicadas 2021–2026), Odoo XML-RPC (1.025 facturas, 1.877 líneas, 5.519 quants, mayor, CRM, proyectos, helpdesk, listas de precios, 3 países), repositorio CFO (migración, importaciones, term sheets, corridas EEFF).
**Regla:** cada cifra tiene fuente; cuando es estimación se dice; los huecos se declaran, no se rellenan.

---

## 0. Resumen ejecutivo

| Dimensión | Veredicto | Evidencia clave |
|---|---|---|
| Comercial | **Volumen comprado, no construido** | Ecuador +12 % 2026E pero NC 9,3 %; Sukasa 65 %; retención de clientes < 15 %; Colombia al 41 % de su presupuesto; Costa Rica al 35 % |
| Financiera | **Margen incremental cero** | EC resultado operativo de gestión (antes de remuneración al accionista vía gerencia/arriendo e impuestos): 194 k (2023) → 161 k → 201 k (2025) con venta ×2,65. Margen bruto −10 pp; opex real 18,6 % → 27,7 % de la venta (`05_Analisis_Gastos`) |
| Capital de trabajo | **Caja secuestrada** | Inventario grupo ≈ USD 720 k; cartera ≈ USD 460 k (61 % vencida CO, 100 % CR); ciclo de caja 154 d EC / 347 d CO; deuda bancaria EC USD 245 k financia a Colombia vía intercompañía (COP 735 M) |
| Contable / datos | **El ERP no sabe cuánto cuesta lo que vende** | 705/745 productos con costo 0; COGS por ajuste periódico; intercompañía descuadrada USD 50–100 k; transitorias > USD 100 k; 800 M COP de capital no pagado en CO; tasa implícita de deuda 2,4 % (subregistro de intereses) |
| Sistemas / procesos | **Odoo instalado, no adoptado** | 393 tareas abiertas, 125 actividades vencidas; CRM con 19 oportunidades; 0 clientes con límite de crédito; helpdesk 37 tickets abiertos de 48; 27 % de entregas a tiempo en EC, 40 % en CO; pipelines en nube bloqueados por credenciales |
| Logística / inventario | **Sobrestock crónico + obsolescencia** | CO: 701 M COP, 12 meses de cobertura, 42 % > 180 d; EC: 586 SKU, 505 sin venta en 12 m, 115 k con > 12 m de cobertura; 48 % de las entregas EC llegan tarde |
| Riesgo | **Tres puntos únicos de falla** | Cliente ancla por país; proveedor único (Hyxion, con contrato a oct-2029 y mínimo USD 600 k); valoración aduanera 2023–2024 con brechas FOB de hasta +129 % |

---

## 1. Comercial

### 1.1 Ecuador — la historia en números (Perseo, USD sin IVA, facturas − NC)

| Año | Venta neta | Facturas | NC % | Clientes | HHI | Cliente principal | MB (mayor) | GV+GA | Resultado | Res. % |
|---|---|---|---|---|---|---|---|---|---|---|
| 2021 | 66.520 | 69 | 0,0 % | 56 | 478 | Prodesigns 17 % | 47,0 % | 3.782 | 28.939 | 43,5 % |
| 2022 | 236.934 | 163 | 0,0 % | 107 | 1.003 | Prodesigns 25 % | 51,5 % | 27.795 | 83.166 | 35,1 % |
| 2023 | 621.442 | 378 | 1,7 % | 234 | 2.293 | Comohogar 46 % | 49,5 % | 122.563 | 170.641 | 27,5 % |
| 2024 | 1.205.752 | 344 | 2,6 % | 188 | 4.569 | Comohogar 66 % | 41,3 % | 393.270 | 68.659 | 5,7 % |
| 2025 | 1.649.918 | 478 | 6,5 % | 223 | 4.738 | Comohogar 68 % | 39,7 % | 535.538 | 48.916 | 3,0 % |
| 2026 ene–jul | 1.113.374 | 324 | 9,3 % | 163 | 4.112 | Comohogar 63 % | 41,8 % | 329.144 | 98.862 | 8,9 % |
| 2026 ago–nov (Odoo) | 503.959 | 212 | 5,7 % | 108 | 5.379 | Comohogar 71 % | n/f | n/f | n/f | |

**Lectura crítica.**
- El salto 2023→2024 (×1,9) vino de un solo cliente: Comohogar pasó de 292 k a 798 k. Ese año el margen bruto perdió 8 puntos (precio de lista Sukasa = PVP −38 %: TRG3601 2.020 vs 3.273) y el gasto operativo se triplicó (promotoría Sukasa, exhibición en mostradores, logística retail, sueldos). **La venta a Sukasa es casi "break-even" después de promotoría, exhibición, transporte y NC.** Hay que medirla por cuenta: hoy el ERP no lo permite.
- Las **notas de crédito** crecen más rápido que la venta: 10,8 k (2023) → 31 k → 108 k (2025) → 103 k en siete meses de 2026. En 2025–2026, 65 facturas se anularon al 100 % (USD 157 k, informe de importaciones). Esto es devolución de retail o reprecio posterior; en ambos casos es margen que no existió.
- **Retención**: de 122 clientes con compras > USD 500 en 2025, solo 17 repitieron en 2026. El negocio fuera de Sukasa es transaccional; no hay base de clientes, hay flujo de proyectos.
- **Estacionalidad real** (índice 2023–2025): marzo 1,10 · junio 1,04 · agosto 1,33 · septiembre 1,50 · noviembre 1,22 · diciembre 1,30; valles abril 0,58 y julio 0,70. Los picos coinciden con pedidos de reposición de Sukasa, no con demanda final.
- **Mix y margen por categoría (Perseo 2026 ene–jul, costo de kardex):** hielo iGlace 22 % de la venta al 46 % MB; cocinas 13 % al 35 %; refrigeración 10 % al 40 %; microondas 10 % al 41 %; hornos 9 % al 33 %; cafeteras 9 % al 51 %; vineras 8 % al 37 %; repuestos 7 % al 43 %; encimeras 2,5 % al 66 %. **Lo que más margen deja (hielo, cafeteras, encimeras, lavavajillas 48 %) pesa un tercio de la venta; lo que menos deja (cocinas, hornos) es lo que Sukasa empuja.**
- **Marcas**: Thor Kitchen 67 % (MB 38 %), iGlace 20 % (MB 52 %), cafeteras 9 % (MB 51 %). iGlace era el 92 % en 2022: el grupo cambió de negocio sin cambiar de estructura de margen.
- **Canales 2026E** (ene–nov): Sukasa 65 %, Prodesigns 8 %, consumidor final 9 %, B2B/HORECA 7 %, otros retail/dealers 6 %, intercompañía 2 %. Consumidores finales únicos: 113 en 7 meses, ticket medio USD 815 (bajando desde 993 en 2024).
- **Vendedores (Odoo ago–nov)**: Katherine Zhuin (contable) factura el 72 % porque emite las facturas de Sukasa; el equipo comercial real factura USD 140 k en tres meses. Las comisiones y metas no pueden calcularse desde Odoo así.
- **Listas de precios**: 8 listas en Ecuador (PVP, D2–D8) con descuentos escalonados coherentes (D3 Sukasa −38 %, D4 Proyectos −36 %, D6 dealers −28 %, D2 −10 %). Costa Rica ≈ Sukasa +10 %. **Colombia lista "Default" TRG3601 = COP 10,59 M ≈ USD 3.300: 63 % sobre el precio Sukasa y 35 % sobre el PVP ecuatoriano.** Esto confirma el diagnóstico de agosto (lista 23 % desalineada) y explica el 41 % de cumplimiento.

### 1.2 Colombia (Odoo, COP sin IVA)

| Mes 2026 | Facturado | Casa Magna | USA Electro | Intercompañía |
|---|---|---|---|---|
| Q1 (vintral1) | 262,3 M | 186,6 M | 69,8 M | 0 |
| Abr | 329,0 M | 201,7 M | 112,3 M | 0 |
| May | 121,8 M | 85,2 M | 36,6 M | 0 |
| Jun | 159,5 M | 95,4 M | 59,1 M | 0 |
| Jul | 60,5 M | 43,8 M | 15,5 M | 0 |
| Ago | 192,3 M | 62,9 M | 17,6 M | 100,3 M |
| Sep | 203,4 M | 84,8 M | 115,7 M | 0 |
| Oct | 123,2 M | 30,5 M | 92,4 M | 0 |
| **YTD oct** | **1.455 M** | **791 M (54 %)** | **519 M (36 %)** | **100 M (7 %)** |

- **10 clientes en todo el país.** Casa Magna + USA = 89 % de terceros, HHI 4.787. Tres personas naturales con una factura cada una. Inverdescuentos 2,4 %.
- **Precio sin disciplina**: TMO24H vendido entre 2,94 M y 5,24 M (+78 %); TIM1501 entre 2,94 M y 5,24 M; H9 entre 2,64 M y 4,53 M; MK04SS304 entre 3,24 M y 4,73 M. Con dos clientes, cada factura es una negociación.
- **Términos de pago 60 días** en el 82 % de la venta; **DSO real 104 días**, 61 % de la cartera vencida (691 M). Casa Magna debe 412 M con 320 M vencidos; USA 175 M al día.
- **Entregas**: 29 días de retraso medio contra fecha programada; 40 % a tiempo.
- **Costo comercial**: transporte 54,7 M (3,8 % de la venta), publicidad 29,9 M, servicio técnico tercerizado 33,8 M (Lógica, Mafra, Tecnicenter, varios: 2,3 %), KAM 9,7 M, La Forja (incentivo piso). Más la comisión propuesta a Felipe. El tope de 6 % variable ya está comprometido antes de empezar.
- **Margen bruto (mayor) 52,6 % YTD**, pero con meses al 100 % y a −362 %: el costo entra por ajustes de inventario. El margen por SKU con costo estándar da 40–67 %, consistente con una lista cara.
- **Proyecto "Comercial Vintral" en Odoo: 155 tareas, 50 abiertas.** La actividad existe; la conversión no (CRM Colombia: 1 oportunidad).

### 1.3 Costa Rica (Odoo, USD)

- Venta 2026: 105.748 en 6 facturas (Cemaco 86.680 en junio y octubre; Panafoto 2 × 9.534 en octubre). Presupuesto 300 k.
- **Cartera 47.017, 100 % vencida** (Cemaco 27.949 con > 90 d; Panafoto 19.068). Sin término de pago cargado en ningún cliente.
- Gastos 40 k: certificación CSA 16,1 k (activo regional, debería cargarse al grupo), publicidad 12,1 k, legal 7,3 k. **No registra costo de ventas**: el margen del mayor es 100 %, el resultado "66 k" es ficticio.
- No hay inventario ni vendedor en el país. Es una cuenta administrada desde Ecuador con un contenedor directo.

### 1.4 Hallazgos comerciales transversales

1. **Dependencia estructural**: el grupo factura ≈ USD 2,4 M y el 68 % pasa por tres compradores (Sukasa, Casa Magna, Cemaco) que pueden cambiar de criterio en una reunión.
2. **El precio de transferencia decide dónde hay utilidad**: Vintral compra a Vicomer (100 M en agosto) y a Hyxion (703 M en el año); Vicomer compra a Vintral (45 k USD en octubre, 31 k por pagar). El flujo cruzado sin política documentada es riesgo fiscal en los dos países.
3. **Servicio técnico es costo, no negocio**: 48 tickets desde septiembre (instalación 60 %, correctivo 35 %), 37 en curso; en Colombia se paga a 4 terceros 34 M. 493 SKU de repuestos en catálogo con 7 % de la venta al 43 % de margen en Ecuador: es la línea más rentable y la menos gestionada.
4. **Digital inexistente en el ERP**: CRM 19 oportunidades (18 en Ecuador), 9 fuentes UTM, 5 sitios web configurados, 0 ventas atribuidas a web/marketplace.

## 2. Financiero

### 2.1 Ecuador — evolución (mayor Perseo, deduplicado; 2026 ene–jul cuadra al centavo con el estado firmado: resultado 98.862)

| | 2023 | 2024 | 2025 | 2026 ene–jul |
|---|---|---|---|---|
| Ventas | 621.442 | 1.205.752 | 1.649.918 | 1.113.374 |
| Costo de ventas | 313.993 (50,5 %) | 708.065 (58,7 %) | 994.237 (60,3 %) | 647.898 (58,2 %) |
| Gasto de ventas | 58.077 | 256.525 | 281.002 | 179.832 |
| Gasto administrativo | 64.486 | 136.745 | 254.536 | 149.312 |
| Financiero + no deducible | 16.299 | 39.221 | 72.827 | 38.441 |
| **Resultado** | **170.641 (27,5 %)** | **68.659 (5,7 %)** | **48.916 (3,0 %)** | **98.862 (8,9 %)** |
| Opex / venta | 19,7 % | 32,6 % | 32,5 % | 29,6 % |

- **Diciembre es el agujero**: dic-2024 gastos 171 k (resultado −113 k), dic-2025 gastos 156 k (−100 k): deterioro de inventarios (27,7 k en 2025), participación, renta, bonos. El resultado de ene–nov siempre se ve mejor de lo que termina el año. **El 8,9 % de 2026 ene–jul no es el del año**: faltan participación 15 %, IR 25 % y el ajuste de diciembre.
- **Gastos fijos que pesan**: arriendo 60 k/año + gerencia general 60 k + gerente administrativo 11 k + Odoo 17 k + Facebook/web 32 k (de los cuales 24 k no deducibles en 2025) + sueldos ventas 32 k y admin 29 k. En 2026 aparece además VIX facturando 12,5 k/mes a las subsidiarias (47,5 k ene–oct): el grupo se cobra a sí mismo y la utilidad se mueve, no se crea.
- **Deuda**: préstamo Banco Guayaquil 300 k (saldo 245 k) + Procredit 20 k + préstamos de socios 56 k. Intereses registrados 6,5 k en ago–oct sobre 300 k de deuda: tasa implícita 2,4 %; el gasto financiero real está subregistrado (la corrida del 26-oct ya lo advirtió).

### 2.2 Balance y capital de trabajo (Odoo, nov-2026)

| USD | Ecuador | Colombia (COP → USD 3.200) | Costa Rica |
|---|---|---|---|
| Caja y bancos | 108.673 (+ transitorias 310 k sin depurar) | 133 M → 41.700 | 22.716 |
| Cartera clientes | 186.921 (+ Vintral 179.236, CR 10.984) | 716 M → 223.600 | 47.017 |
| Inventario | 313.651 en almacén + 190.679 en tránsito (053, 059, Panamá) | 695 M → 217.100 (+ anticipos a Hyxion 331 M) | 0 |
| Proveedores | 377.610 (Hyxion 84 k, Arda 44 k, Motricentro 36 k) | 358 M → 112.000 (Hyxion 264 M vencidos) | 2.624 |
| Deuda financiera | 244.786 + 32.500 socios | 0 | 0 |
| Intercompañía | por cobrar a Vintral 179.236 | por pagar a Vicomer 735 M → **229.800** | por pagar relacionadas 6.951 |

- **La intercompañía no cuadra**: Vicomer registra 179 k por cobrar; Vintral 735 M por pagar (≈ 230 k). Diferencia ≈ USD 50 k (a 3.200) o 104 k (a la TRM de julio). Además Vicomer debe 31 k a Vintral y 11,5 k a VIX. Sin conciliación mensual no hay consolidado firmable.
- **Colombia tiene 800 M de capital suscrito y 800 M por cobrar a accionistas**: el patrimonio real es la utilidad acumulada (429 M). Deudas con socios 198 M. La compañía opera con el crédito de Vicomer (735 M) y de Hyxion (264 M vencidos): **toda la deuda del grupo está en Ecuador y toda la cartera lenta en Colombia.**
- **Ciclo de caja**: EC cobro 24 d (Sukasa paga rápido) · inventario ≈ 180 d · pago 80 d → ≈ 125–155 d. CO cobro 104 d · inventario ≈ 360 d · pago 262 d (Hyxion vencido) → 200–350 d. **El DPO de Colombia es mora, no crédito.** Intereses de mora 5,2 M + 4×1000 6,3 M = 11,5 M COP tirados en 2026.
- **Deterioro de inventario** reconocido en Ecuador: 21,9 k (2024), 27,7 k (2025), 22,5 k (ene–jul 2026). El informe de importaciones de julio cuantificó **117 modelos obsoletos, 1.214 uds, USD 120 k** y faltantes físicos relevantes (IGBEER −132 uds).

### 2.3 Rentabilidad por país (orden de magnitud 2026)

| | Ecuador | Colombia | Costa Rica |
|---|---|---|---|
| Venta 2026E (USD) | 1,83 M | 0,47 M | 0,11 M |
| Margen bruto | 42 % (kardex Perseo; Odoo no fiable) | ~45–52 % (mayor; sospechoso por lista cara) | no medible |
| Opex / venta | 29–32 % | 25 % (+ provisión renta 116 M) | 38 % |
| Resultado antes de impuestos | ≈ 5–9 % → después de participación e IR ≈ 3–5 % | ≈ 20 % contable (sin costo mensualizado; provisión renta duplica la del contador) | ficticio |
| Capital empleado | ≈ USD 700 k (inventario + cartera − proveedores) + deuda | ≈ USD 330 k financiado por Vicomer y Hyxion | ≈ 50 k |

**El grupo reconoce utilidad donde la tarifa es más alta (Colombia 35 %) y pérdida de margen donde está la deuda (Ecuador).** Esto no es solo contable: el reprecio de Colombia y la política de transferencia deben pensarse juntos.

## 3. Contabilidad y calidad del dato

| Hallazgo | Evidencia | Consecuencia |
|---|---|---|
| **Costo estándar en cero** | 705 de 745 productos vendibles; 65 de 90 SKU vendidos en EC ago–nov sin costo; CR 4 de 15 | Odoo no puede dar margen por SKU/cliente/vendedor; el tablero EEFF publica «—» |
| **COGS por ajuste periódico** | CO: abr 0 %, may 0 %, jul 462 %; EC: sep 16 %, oct 75 % | Resultado mensual sin significado; cierres tardíos |
| **Diario de apertura mezclado con resultados** | Apertura ER 1,114 M; cuentas 5001/5002/5004 | Ya costó una versión equivocada del EEFF; sigue siendo trampa para cualquiera que consulte el mayor |
| **Transitorias** | EC «Cuenta transitoria» 194 k y «Banco Guayaquil transitoria» 116 k en el balance; conciliaciones bancarias pendientes (60 líneas EC) | La caja reportada no es la caja real |
| **Intercompañía** | 179 k vs 735 M COP; VIX 11,5 k; CR 11 k | Consolidado no firmable; riesgo de precios de transferencia |
| **Tipos de cambio** | Vintral: tasa COP = 1,0; solo CR carga COP/CRC; Odoo devolvía la misma tasa para COP, CRC y EUR | Toda consolidación debe hacerse fuera de Odoo con TRM fechada |
| **Provisión de renta CO** | Odoo 115,8 M vs contador 72,2 M (diferencia 43,6 M) | Resultado de Colombia sobreestimado en el estado del contador o subestimado en Odoo; hay que decidir cuál es la verdad |
| **Intereses subregistrados EC** | Tasa implícita 2,4 % sobre 300 k | Utilidad sobreestimada ≈ 20–25 k/año |
| **Clasificación del plan de cuentas** | 193 cuentas bajo 52 en EC sin separar admin/ventas/financiero (prefijos 53–55 vacíos); CO sin cuenta tipificada como costo directo | Los reportes rescatan el costo «por nombre»: parche declarado |
| **Maestro de terceros** | Hyxion con RUC «1111111111111»; 967 clientes, 0 con límite de crédito, 4 con término de pago; 2.029 lotes/series sin compañía | Crédito sin control; trazabilidad por serie inservible para garantía y para la cláusula antirreventa del term sheet |
| **Duplicidad en la API Perseo** | `asientoscontables_consulta` devuelve cada asiento hasta 22 veces | Cualquier script que no deduplique por `libros_diariosid` triplica la cifra (corregido en `analisis/perseo_pl.py`) |

## 4. Sistemas, procesos y organización

- **Odoo**: 6 compañías (2 personas naturales creadas en octubre: decidir si entran al consolidado o se cierran), 80 usuarios (muchos externos: técnicos de servicio, contadores de Colombia), 33 proyectos, 769 tareas (393 abiertas, 50 vencidas), 153 actividades pendientes (125 vencidas, 87 sobre «consignación»), 3.340 eventos de calendario (1.675 del gerente general: la agenda del grupo es la agenda de una persona).
- **Consignación**: ubicaciones «CONSIGNACION/DESPACHO» con USD 34 k (EC) y COP 138 M (CO) de inventario en poder de retailers. Es inventario propio en bodega ajena: debe contarse, asegurarse y tener fecha de venta pactada.
- **Pipelines CFO**: 14 pipelines documentados; 2 ya corren en la nube (EEFF viernes, informe CFO), pero la corrida del 26-oct solo salió con credenciales traídas a mano; las tareas de Casa Magna están deshabilitadas (`device_absent`); IMAP/SMTP no salen por el proxy. **El sistema de reporting depende del Mac encendido y del usuario presente.**
- **Comité de pagos**: 34 corridas sin una orden emitida (diagnóstico sep-2026); el proceso produce información que nadie consume.
- **Personas**: Ecuador 12 activos (de 25 registrados: 13 bajas → rotación alta), Colombia 1 empleado (KAM) + servicios tercerizados, Costa Rica 0. La estructura comercial real son 4 personas en Ecuador. No hay nadie en Costa Rica ni en digital.

## 5. Logística e inventario

| | Ecuador | Colombia |
|---|---|---|
| Stock (quants internos) | 6.126 uds · USD 313.651 · 586 SKU (la mayoría repuestos) | 769 uds · COP 701 M · 60 SKU |
| Sin venta en 12 meses | 505 SKU · USD 61 k (20 %) | 35 SKU · COP 85 M (12 %) |
| Cobertura > 12 meses | 35 SKU · USD 115 k (37 %) | 13 SKU · COP 506 M (72 %) |
| Antigüedad > 180 d | no registrada (sin fecha de entrada) | 42 % del valor |
| Ejemplos | RF3621CTD00 25 m, PIH36 26 m, PIH30 25 m, IG120 72 m, IGBWR90 228 m | TEW30ES 18 m, TMO30H 21 m, HRT3618U 23 m, HDW2401SS 20 m, TWC24UL 48 m, PIH30 ∞, TGC3601 ∞ |
| Compras 2026 a Hyxion | 84 k + PO en borrador 81 k | **703 M COP facturados + PO sep 338 M** con 12 meses de cobertura |
| Entregas a tiempo | 27 % (retraso medio 2,9 d) | 40 % (retraso medio 29 d) |
| En tránsito | impo 053 (120 k), 059 (44 k), bodega Panamá (26 k) | — |

- **Colombia compra como si vendiera COP 3.672 M.** Con venta real de ~1.500 M y COGS ~690 M, el inventario de 701 M es un año de ventas. Congelar compras de los SKU con > 6 meses de cobertura libera caja y reduce la deuda con Hyxion (264 M vencidos).
- **Ecuador tiene dos problemas distintos**: obsolescencia de cola larga (505 SKU, muchos repuestos y promocionales) y sobrecompra puntual de modelos caros (refrigeradores panelables, inducción).
- **Landed cost**: el informe de importaciones fijó factor por categoría (arancel + flete por CBM) y detectó brechas FOB pagado vs declarado de +12 % a +129 % en 2023–2024. Es riesgo tributario-aduanero latente que una fiscalización puede reabrir; la documentación de la impo 006 sigue sin regularizar.
- **Nave E02 (Tarqui)**: hay planos y RFQ de racks en el repo. Antes de invertir en bodega, reducir el inventario que la justificaría.

## 6. Riesgos ordenados por impacto × probabilidad

1. **Pérdida o recorte de un cliente ancla** (alto × medio). Sukasa concentra además la promotoría y exhibición pagadas por Vicomer: el costo de salida es doble.
2. **Dependencia de Hyxion** (alto × bajo-medio): contrato a oct-2029, mínimo USD 600 k/año (hoy se cumple con holgura), 264 M COP vencidos con ellos en Colombia; cualquier cambio de condiciones de crédito golpea la caja de inmediato.
3. **Fiscalización aduanera 2023–2024** (alto × bajo).
4. **Cartera Colombia** (medio × alto): 320 M vencidos de Casa Magna; sin garantías ni intereses pactados.
5. **Precios de transferencia e intercompañía** (medio × medio): flujos cruzados EC↔CO↔VIX sin política escrita.
6. **Dependencia tecnológica de una persona** (medio × alto): pipelines, credenciales, agenda.

## 7. Oportunidades cuantificadas (orden de magnitud anual)

| Oportunidad | Cómo | Valor estimado |
|---|---|---|
| Reducir NC de 9 % a 4 % en Ecuador | Política de devoluciones con Sukasa, control de calidad en entrega, reprecio documentado | +USD 90–100 k de margen |
| Reducir inventario 30 % | Liquidación obsoletos + compras por cobertura | +USD 220 k de caja una vez; −USD 20 k/año de deterioro |
| DSO Colombia 104 → 60 d | Límites, mora, confirming | +COP 270 M (≈ USD 85 k) de caja; −11 M/año de mora y 4×1000 |
| Mix hacia alto margen (hielo, cafeteras, encimeras, lavavajillas) | Metas por categoría, comisiones por margen | +2–3 pp de margen bruto ≈ USD 60–90 k |
| Servicio técnico y repuestos como línea de negocio | Planes pagados, stock mínimo de repuestos, venta online | +USD 50–80 k de margen |
| Máster licencia Centroamérica | Override 10–12 % sobre FOB, capital cero | USD 20–45 k neto año 1, 90 k año 3 |
| Opex Ecuador de 30 % a 26 % de la venta | Revisar promotoría/exhibición Sukasa contra margen de la cuenta, arriendo, publicidad no deducible | +USD 80 k |

Sumadas, estas palancas valen más que todo el resultado neto de 2025 (USD 49 k) multiplicado por seis. **El problema del grupo no es de ventas: es de margen, caja y datos.**

## 8. Huecos de información que este diagnóstico declara

- Ventas de Colombia jun–dic 2025 (instancia vintral1 sin credencial en la nube; `ODOO_APIKEY_VINTRAL1` ausente del environment).
- Sell-out de Casa Magna (adjuntos NetSuite en Gmail; la API del conector no entrega adjuntos).
- Costo real por SKU en Odoo (en cero) y valoración de Costa Rica.
- Estados firmados de Colombia posteriores a julio y conciliación de la provisión de renta.
- Presupuesto de gastos 2027 (los libros Excel viven en Drive, no en la nube).
