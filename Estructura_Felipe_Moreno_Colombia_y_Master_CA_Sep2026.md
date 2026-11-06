# ESTRUCTURA FELIPE MORENO — Bono Colombia + Máster Licenciatario Centroamérica
## Documento CFO interno · preparación reunión viernes 25-sep-2026

**Fecha:** 21 de septiembre de 2026
**Preparado para:** Juan Marcelo Vidal Torres
**Rol del análisis:** CFO — diseño de estructura comercial, riesgo y caja
**Datos duros:** Odoo, dashboard_ventas.json, corte contable 31-ago-2026, TC ref. 3.700 COP/USD
**Confidencial — no compartir con la contraparte.** El documento presentable es el *Term Sheet*.

---

## 1. CONTEXTO — lo primero es separar dos negocios que hoy viajan en la misma conversación

En la reunión de hace dos días quedaron mezclados dos acuerdos que no comparten riesgo, ni duración, ni economía, ni ley aplicable:

| | **Acuerdo A — Colombia** | **Acuerdo B — Centroamérica** |
|---|---|---|
| Qué es | Felipe origina oportunidades en un mercado que ya operas | Vicomer se convierte en máster licenciatario y **no opera** |
| Activo en juego | Cuentas y relaciones | **Territorio cedido por Hyxion** |
| Capital de Vicomer | El de siempre (inventario, cartera) | Idealmente cero |
| Riesgo dominante | Conflicto de canal con David Tafur + cartera | Compromiso de mínimos con Hyxion |
| Horizonte | 12–24 meses, renovable | 3–5 años, atado al contrato Hyxion (oct-2029) |
| Ley y foro | Colombia (peligroso — §4.6) | Panamá / arbitraje, ley neutra |
| Si fracasa | Cortas y sigues | Pierdes un territorio que costó negociar |

**Decisión estructural #1: dos contratos separados, no uno.** Cross-default solo en una dirección —fraude, competencia o violación de exclusividad rompen ambos; el bajo desempeño en Colombia **no** debe tocar Centroamérica, y viceversa. Si firmas un solo instrumento, cualquier disputa en Colombia te pone el territorio centroamericano de rehén.

---

## 2. DIAGNÓSTICO CFO — lo que los datos dicen antes de repartir comisiones

### 2.1 Colombia no tiene un problema de oportunidades

Odoo, corte 31-ago-2026:

| Indicador | COP | USD ref. |
|---|---|---|
| Venta YTD (ene–ago) | 1.125.563.011 | 304.206 |
| Presupuesto YTD | 1.985.790.715 | 536.700 |
| **Brecha YTD** | **860.227.704** | **232.494** |
| Presupuesto anual | 3.671.996.149 | 992.431 |
| Run-rate anual | 1.688.344.516 | 456.309 |
| **Brecha anual proyectada** | **1.983.651.633** | **536.122** |

**Cumplimiento YTD 56,7% · run-rate 46,0% del presupuesto.**

**Nota sobre el primer trimestre (corregida el 21-sep):** la venta de ene–mar 2026 **sí está incluida** en las cifras de arriba. Vive en `odoo_config.json → colombia_hist_mensual` (COP 262.321.141, capturado por API de la instancia anterior `vintral1.odoo.com`) y el dashboard la suma como histórico pre-migración. Los totales de venta y de cumplimiento no cambian.

**Lo que sí faltaba era el desglose por cliente de Q1** — el bloque de concentración del dashboard cubría solo el 79,5% del año porque el detalle por cliente solo existe en el Odoo nuevo, desde abril. Reconstruido con `VENTAS VINTRAL 2026 HASTA MARZO.xlsx`, la foto completa ene–sep 2026 es:

| Cliente | Q1 (ene–mar) | Abr–sep | **Total ene–sep** | **% real** | *% que leía el dashboard* |
|---|---|---|---|---|---|
| **CASAMAGNA S.A.S** | 186.590.601 | 530.434.758 | **717.025.359** | **55,95%** | *52,04%* |
| **USA ELECTRODOMÉSTICOS SAS** | 69.823.330 | 352.721.700 | **422.545.029** | **32,97%** | *34,61%* |
| Vicomer S.A.S. (intercompañía) | 0 | 100.301.041 | 100.301.041 | 7,83% | *9,84%* |
| INVERDESCUENTOS SAS | 5.907.997 | 29.090.336 | 34.998.333 | 2,73% | *2,85%* |
| Resto (4 cuentas menores) | 0 | 6.653.782 | 6.653.782 | 0,52% | *0,65%* |
| **Total** | **262.321.141** | **1.019.201.617** | **1.281.522.757** | 100% | |

**HHI 4.286 (todos) · 4.973 (solo terceros).** Casa Magna + USA Electrodomésticos = **88,9% de la facturación del país** y **96,5% de la venta a terceros**.

> **La corrección empeora el cuadro, no lo mejora.** Casa Magna no pesa 52% — pesa **casi 56%**, cuatro puntos más de lo que mostraba el tablero. Y la venta de terceros real ene–sep es COP 1.181M ≈ **USD 319K**, con 96,5% en dos cuentas. Esto refuerza directamente §4.4: abrir Corona sin acuerdo marco previo con Casa Magna es más riesgoso de lo que escribí en la primera versión.

**Hallazgo de calidad de dato (nuevo, anotar):** el Q1 medido sobre `sale.report` (base **pedido**) da COP 301.427.023; medido sobre `account.move` (base **factura**) da COP 262.321.141. **14,9% de discrepancia entre los dos objetos de Odoo.** No es un error: son cosas distintas. Pero significa que el mix de clientes de Q1 de esta tabla es una **reconstrucción proporcional** (participaciones de la base pedido aplicadas al total facturado), no una medición directa. Para el bono hay que fijar por contrato que la base es **factura cobrada**, nunca pedido.

**Hueco mayor, fuera de alcance de este documento:** el desglose por cliente de **Ecuador cubre solo el 15,9%** del YTD — cuatro veces peor que el de Colombia antes de esta corrección. Vale una revisión aparte.

El diagnóstico vigente desde agosto no ha cambiado y no es de demanda: **lista 23,4% desalineada, cuatro SKU driver 36,2% fuera de precio, DSO 183,7 días y 61,1% de la cartera vencida.** La decisión D2 —aprobar el reprecio estructural— tenía límite 15-sep y sigue abierta.

> **Punto incómodo:** pagarle a alguien por abrir puertas en un mercado donde el producto está 23% caro y la cartera tarda seis meses en volver, produce leads que no cierran y, si cierran, cierran mal. **El reprecio va antes que el originador.** No después, no en paralelo. Si el viernes acuerdas el fee sin haber cerrado D2, estás comprando actividad, no resultado.

### 2.2 Felipe ya había salido de la estructura de Colombia

El `Plan de Ejecución Comercial v4` (20-ago-2026) registra la decisión: *"David Tafur — KAM Colombia. Felipe Moreno fuera del equipo."* Hace cinco semanas.

Reintegrarlo tan rápido no es necesariamente un error —la oportunidad centroamericana es información nueva y legítima— pero obliga a responder una pregunta con honestidad antes del viernes:

**¿El valor de Felipe es acceso o ejecución?**

- **Si es acceso** (relación con Corona, con retailers centroamericanos, con el ecosistema): se paga **por puerta abierta**, fuerte, una vez, y con decaimiento. No genera estructura permanente.
- **Si es ejecución** (gestionar la cuenta, seguimiento, cobro): ya tienes a David, y estarías pagando dos veces por la misma función.

Todo lo que viene asume **acceso**. Si en la conversación del viernes Felipe empuja hacia gestión de cuenta, es una señal de que quiere un puesto, no un fee — y eso cambia el análisis completo.

### 2.3 Costa Rica ya está operada por el grupo

Odoo: Costa Rica YTD USD 86.197, **CEMACO = 100% de la venta (HHI 10.000)**, 52,8% del presupuesto, cartera 100% vencida.

**Costa Rica no puede entrar al territorio de Felipe.** Ya es una operación propia con una cuenta ancla. Si entra, pagas override sobre negocio que ya tienes. Carve-out explícito: **Costa Rica y CEMACO quedan fuera del Acuerdo B**, sin excepción, incluso si en el futuro se agrega un segundo cliente costarricense.

---

## 3. LA OPORTUNIDAD REAL — por qué el Acuerdo B vale más que el A

El Acuerdo A pelea por una fracción del margen de un país que rinde 46%. El Acuerdo B es un negocio distinto: **vender derecho de territorio y soporte, no electrodomésticos.**

Modelo capital-light (override sobre FOB, Vicomer no toca contenedor, no inmoviliza inventario, no asume crédito):

| Escenario | FOB anual | Override | Override Vicomer | Fee Felipe (25%) | **Neto Vicomer** |
|---|---|---|---|---|---|
| Año 1 conservador — 2 distrib. × $120K | 240.000 | 12% | 28.800 | 7.200 | **21.600** |
| **Año 1 base — 3 distrib. × $120K** | **360.000** | **12%** | **43.200** | **10.800** | **32.400** |
| Año 2 — 4 distrib. × $180K | 720.000 | 11% | 79.200 | 19.800 | **59.400** |
| Año 3 — 5 distrib. × $250K | 1.250.000 | 10% | 125.000 | 31.250 | **93.750** |

Contraste que hay que tener en la cabeza el viernes: el **margen bruto anual de toda Colombia**, a run-rate de terceros y GM 45%, es ≈ **USD 189.000** — y consume inventario, cartera de 184 días y una estructura completa.

- **CA año 1 = USD 32.400 neto = 17% del margen bruto de Colombia, con capital de trabajo ≈ 0.**
- **CA año 3 = USD 93.750 neto = 50% del margen bruto de Colombia, con capital de trabajo ≈ 0.**

Ese es el argumento. No es un negocio de comisiones: es el primer escalón de *distribuidor → plataforma*, y es exactamente la jugada que ya tenías escrita para Chile/Perú. Centroamérica la adelanta.

---

## 4. RIESGOS OCULTOS — lo que probablemente no está en la mesa

### 4.1 El mínimo de compra migra hacia ti, no hacia los distribuidores ⚠️ CRÍTICO

El contrato Hyxion (16-oct-2024) impone **USD 600.000/año de compra mínima** por Ecuador + Colombia + Costa Rica, con terminación si no alcanzas el 75% ($450K) dos años seguidos.

Es razonable esperar que Hyxion **exija un mínimo adicional por Centroamérica**. Y aquí está la trampa del modelo máster: **el mínimo lo asumes tú; los distribuidores, si no lo pactas, no asumen nada.** Firmas un compromiso de volumen en mercados que no operas, con gente que puedes no conocer.

**Regla dura, innegociable:** Vicomer nunca compromete ante Hyxion más del **75% de la suma de los mínimos back-to-back ya firmados** por sub-distribuidores. Ningún mínimo con Hyxion antes de tener contratos firmados que lo cubran. Si Hyxion pide el mínimo primero, se negocia un **período de gracia de 12 meses** o un mínimo escalonado que arranque en cero.

### 4.2 La adenda no está firmada

Dijiste que hay derecho o adenda en trámite. Hasta que esté firmada y apostillada, **no existe**. El contrato con Felipe se firma con **condición suspensiva**: el Acuerdo B solo entra en vigor cuando la cesión de territorio de Hyxion esté perfeccionada. Si no se perfecciona en X meses, el acuerdo caduca sin indemnización ni reclamo.

Es tu terreno como abogado y es la protección más barata de todo el paquete. No la cedas por entusiasmo de reunión.

### 4.3 Apilamiento de costo comercial variable

Hoy en Colombia ya conviven: variable de David Tafur + **La Forja de Thor** (incentivo a asesores de piso, ~0,99% del sell-out del canal, ~1,47% del sell-in) + rebates de sell-in propuestos (M2, M5, M7 — que consumen margen, no A&P). Si encima entra el fee de Felipe sin techo, terminas entre **4% y 6% de la venta en variable comercial**, sobre cuentas con 184 días de DSO.

**Regla:** un solo **techo global de costo comercial variable por cuenta = 6% de la venta neta cobrada.** Todo lo que se pague —David, Felipe, piso, rebates— sale del mismo pote. Si Felipe entra, alguien cede o el pote crece por resultado, no por acumulación.

### 4.4 Corona puede costar más de lo que trae

Corona es un comprador sofisticado con marcas propias e importación directa. Tres riesgos concretos:

1. **Conflicto de canal.** Casa Magna es el **55,95%** de Colombia (no el 52% que mostraba el tablero — ver §2.1), y junto con USA Electrodomésticos suma el 96,5% de la venta a terceros. Abrir Corona sin acuerdo marco previo con Casa Magna es una forma eficiente de deteriorar la cuenta que te sostiene el país. El acuerdo marco con Casa Magna sigue sin existir (semáforo en rojo desde agosto).
2. **Caja.** Una cuenta corporativa de ese tamaño paga a 60–90 días *en el mejor caso*, y exige volumen para nacer. Con la caja del grupo y Colombia en 184 días de DSO, una apertura grande sin condiciones es una salida de caja disfrazada de buena noticia.
3. **Precio.** Va a pedir precio de volumen sobre una lista que ya está 23% desalineada. Sin el reprecio de D2 no tienes con qué negociar sin regalar margen.

**No prohíbas Corona — condiciónala:** apertura sujeta a (a) reprecio aprobado, (b) acuerdo marco con Casa Magna firmado o notificación previa acordada, (c) condiciones de pago ≤60 días con garantía o carta de crédito en el primer año.

### 4.5 Abrir stock en Zona Libre de Colón es un uso de caja, no una decisión logística

Un inventario en ZLC es capital de Vicomer inmovilizado en un país donde no vendes, expuesto a obsolescencia y a un solo canal de salida. Con Colombia en 46% de run-rate y 61% de cartera vencida, **no es el momento de fondear inventario en Panamá con balance propio.** Ver §6.3: Colón entra en Fase 2 y se financia con anticipos de los propios distribuidores.

### 4.6 Agencia comercial colombiana — la cláusula que puede costarte años de comisión ⚠️

Si el Acuerdo A se estructura, se redacta o se ejecuta como **contrato de agencia comercial bajo ley colombiana**, el art. 1324 del Código de Comercio otorga al agente, a la terminación, una prestación equivalente a **1/12 del promedio de comisión por cada año de vigencia**, más una eventual indemnización equitativa si la terminación es sin justa causa. La disponibilidad/renunciabilidad de esa prestación ha sido discutida por la Corte Suprema y por tribunales arbitrales; **no la des por renunciada solo porque el contrato lo diga.**

**Mitigación (a validar con Ocampo Gómez Abogados — ya los tienes contratados para el régimen cambiario del mismo país):**

- No denominar ni estructurar el contrato como agencia comercial. Usar **corretaje / prestación de servicios de intermediación**, sin representación, sin facultad de obligar a Vicomer, sin zona exclusiva asignada.
- Felipe **no** negocia ni firma en nombre de Vicomer. Presenta, conecta y acompaña; Vicomer aprueba, cotiza, factura y cobra.
- Contratar a Felipe a través de un **vehículo no colombiano**, con ley y foro neutros (Panamá o arbitraje CCI), si su situación lo permite.
- Verificar el tratamiento cambiario del pago de comisiones al exterior desde Vintral — es exactamente el frente que Ocampo Gómez ya tiene abierto.

### 4.7 Atribución: quién se lleva el crédito

Sin reglas, cada venta en Colombia se vuelve una discusión entre Felipe y David. El único antídoto es un **registro de cuentas ex-ante** (§5.3). Sin registro aprobado por escrito antes del primer contacto, no hay fee. Sin excepciones, ni siquiera la primera vez.

### 4.8 Fiscalidad y vehículo — el costo de pagar mal

Rutas de pago de la comisión, por costo fiscal esperado (**rangos a validar con tu tributarista — no son cifras firmes**):

| Desde | Costo adicional estimado | Observación |
|---|---|---|
| **Vicomer Ecuador** | ISD 5% + retención a no residentes por servicios | La ruta más cara. Evitar. |
| **Vintral Colombia** | Retención sobre pagos al exterior por servicios + registro cambiario | Añade el riesgo de agencia comercial (§4.6) |
| **SRL Costa Rica** | Impuesto sobre remesas al exterior | **Además revienta el umbral PYME (~USD 263K).** Descartar. |
| **Vehículo Panamá** | Territorialidad: renta de fuente extranjera no gravada | Ruta natural para CA — **pero** verificar si Panamá está en la lista de regímenes fiscales preferentes del SRI ecuatoriano (retención agravada y escrutinio de precios de transferencia) |

Esto se cruza con el frente de holding que ya tienes abierto (VIX). **Acción:** decidir el vehículo *antes* de firmar, no después. Cambiar de vehículo con el contrato firmado cuesta renegociar.

### 4.9 El soporte gratis es como se desangra un máster licenciatario

Marketing, capacitación, servicio técnico y repuestos tienen costo real y demanda tiempo de tu gente (Sebastián, Logística, Marketing). Si se entregan gratis como argumento de venta, en 18 meses tienes cinco distribuidores consumiendo estructura ecuatoriana sin pagarla. Ver §6.4: todo soporte se monetiza o se cofinancia.

---

## 5. ACUERDO A — COLOMBIA: estructura propuesta

### 5.1 Principio: Felipe participa del **margen que genera**, no de la venta

Pagar sobre facturación premia actividad. Pagar sobre margen bruto cobrado premia el negocio que efectivamente entra a la caja. Con DSO de 184 días y 61% de cartera vencida, esto no es elegancia técnica: es supervivencia.

**Base de cálculo:** margen bruto (venta neta − COGS) **efectivamente cobrado**, de clientes terceros, medido sobre **factura** (`account.move`), nunca sobre pedido (`sale.report`) — los dos objetos difieren 14,9% en Colombia (§2.1). Excluye intercompañía Vicomer↔Vintral (7,83% de la venta de Colombia — no es venta, es traslado).

### 5.2 Tarifas — abre acá, tu techo es otro

| Concepto | **Apertura (lo que propones)** | **Techo (no pasar de aquí)** |
|---|---|---|
| Cuenta **nueva** registrada — meses 1–12 | **12% del MB cobrado** | 18% |
| Cuenta **nueva** — meses 13–24 | **6% del MB cobrado** | 9% |
| Cuenta nueva — mes 25 en adelante | **0%** | 0% — no negociable |
| Cuenta **existente** (Casa Magna, USA Electrodomésticos) | **8% del MB incremental cobrado** | 12% |
| Umbral de activación en cuentas existentes | **+10%** sobre baseline | +5% |
| Techo anual global Acuerdo A | **USD 25.000** | USD 35.000 con revisión escrita |

Traducción a % de venta (GM 45%): 12% del MB ≈ **5,4% de la venta**; 8% del MB incremental ≈ **3,6%**. Dentro de la banda sana de un originador (3–7%), y consistente con el techo global de 6% de §4.3.

Escenarios (12 meses):

| Escenario | Venta USD | MB USD | Fee Felipe | % s/venta |
|---|---|---|---|---|
| Corona entrega $200K año 1 | 200.000 | 90.000 | **10.800** | 5,4% |
| Corona conservador $100K | 100.000 | 45.000 | **5.400** | 5,4% |
| Corona año 2 (tasa cae a 6%) | 200.000 | 90.000 | **5.400** | 2,7% |
| Casa Magna +$150K sobre baseline | 150.000 | 67.500 | **5.400** | 3,6% |
| *(referencia) techo 18%* | 200.000 | 90.000 | *16.200* | *8,1%* |

**El decaimiento (12% → 6% → 0%) es la pieza que más vas a tener que defender y la que más valor protege.** Un originador no cobra renta perpetua sobre una cuenta que otro atiende. Justificación para decirla en voz alta: *"el año 1 pagamos por abrir, el año 2 por acompañar la transición, del 3 en adelante la cuenta es de la casa."*

### 5.3 Baseline — no uses el presupuesto, es ficción

El presupuesto 2026 de Colombia (COP 3.672M ≈ USD 992K) va en 46%. Un bono atado a él es un placebo: nadie lo va a alcanzar y por lo tanto no incentiva nada.

**Baseline del período (oct-2026 → sep-2027)** = el **mayor** entre:
- (a) margen bruto cobrado de terceros de los 12 meses inmediatamente anteriores, y
- (b) un piso fijo construido sobre el run-rate actual de terceros: venta COP 1.556M ≈ **USD 421K** (run-rate anual COP 1.688M menos 7,83% de intercompañía, corregido con Q1 completo) → a GM 45%, **piso de margen bruto ≈ USD 189K / COP 700M**.

El piso (b) impide que una caída del desempeño *baje* el baseline y genere un bono por recuperar lo perdido. Revisión anual, al alza únicamente.

### 5.4 Registro de cuentas — la regla que evita la guerra con David

1. Felipe **registra por escrito** (correo basta) la cuenta antes del primer contacto comercial.
2. Vicomer confirma o rechaza **en 5 días hábiles**. Sin confirmación escrita, no hay registro.
3. El registro **vence a los 120 días** sin primer pedido. Renovable una sola vez si hay avance demostrable.
4. Cuentas ya facturadas, en pipeline documentado de David, o que Vicomer contactó antes: **no registrables**.
5. Toda negociación, cotización y condición comercial la aprueba Vicomer. Felipe no compromete precios, plazos ni descuentos.
6. Casa Magna y USA Electrodomésticos son **cuentas de la casa** — solo aplica el esquema de incremento, nunca el de cuenta nueva.

### 5.5 Pago y clawback

- Liquidación **mensual**, pago dentro de los 10 días siguientes.
- Se liquida sobre **cobrado**, no sobre facturado.
- **Clawback:** si una factura ya liquidada se devuelve, se anula, o entra a **mora >90 días**, el fee correspondiente se descuenta de la siguiente liquidación. Sin esto, Felipe es indiferente a la calidad del cliente que trae — que es exactamente el problema que ya tienes.
- Vigencia inicial **12 meses**, renovable por escrito. Terminación con **30 días** de preaviso por cualquiera de las partes.

---

## 6. ACUERDO B — CENTROAMÉRICA: máster licenciatario

### 6.1 La definición que hay que dejar clarísima el viernes

**Vicomer es máster licenciatario: consolida la marca, controla precio y posicionamiento, provee soporte. No opera el mercado, no importa, no vende al retail, no asume la cartera local. El distribuidor por país hace todo eso.**

Territorio propuesto: **Panamá, Guatemala, El Salvador, Honduras, Nicaragua** (+ República Dominicana si Hyxion la incluye). **Costa Rica excluida** (§2.3).

### 6.2 Escalera de exclusividad — exclusividad a cambio de volumen, siempre

Ningún distribuidor recibe exclusividad sin mínimo, y el incumplimiento del mínimo la degrada **automáticamente**, sin necesidad de notificar, negociar ni litigar:

| | Mínimo anual FOB | Exclusividad |
|---|---|---|
| Año 1 | USD 120.000 (≈2×40HQ) | Exclusiva condicionada |
| Año 2 | USD 180.000 | Exclusiva si cumplió año 1 |
| Año 3 | USD 250.000 | Exclusiva si cumplió año 2 |
| Incumplimiento | — | **Conversión automática a no exclusiva**, sin indemnización |

Panamá puede arrancar más alto si Panafoto entra (ya tienes la estructura de costo CIF Manzanillo construida). Honduras y Nicaragua probablemente por debajo — ajusta por tamaño de mercado, nunca por entusiasmo del candidato.

**Los mínimos son back-to-back con lo que comprometas ante Hyxion (§4.1). Ese es su propósito principal; la exclusividad es el argumento de venta.**

### 6.3 Las dos listas de precios — no son dos opciones, son dos negocios

**LISTA A — Ex-China (FOB puerto chino). Es el canal estándar.**

- Precio = FOB Hyxion + **override Vicomer 12%** (banda 10–15%; baja a 8% sobre USD 500K/año acumulado por distribuidor, como rebate que premia escala y ancla la relación)
- MOQ: **1×40HQ por pedido**
- El distribuidor paga flete, seguro y nacionalización
- Pago: **100% anticipado o carta de crédito.** Sin crédito en año 1, sin excepciones
- Vicomer no inmoviliza capital, no asume obsolescencia, no asume riesgo de crédito

**LISTA B — Ex-warehouse Zona Libre de Colón. Es la cola, no el volumen.**

- Precio = costo landed Colón × **1,17** (banda 15–20%)
- Sin MOQ de contenedor: lotes pequeños
- Pago: anticipado o contra entrega

Spread sobre 1×40HQ (FOB $60K; flete China→CA ≈ $4.000, Colón→CA ≈ $1.200 — **estimados, validar con el MAESTRO_IMPORTACIONES y con Logística**):

| Margen ZLC | Costo distribuidor vía A | Costo distribuidor vía B | **Prima de B** |
|---|---|---|---|
| 15% | 71.200 | 78.480 | +10,2% |
| **17%** | **71.200** | **79.824** | **+12,1%** |
| 20% | 71.200 | 81.840 | +14,9% |
| 25% | 71.200 | 85.200 | +19,7% |

**Lectura que hay que decir en la reunión:** al 25% nadie compra en Colón — la prima se vuelve 20% y ningún distribuidor serio paga eso por su volumen regular. **La banda útil es 15–18%.** Y con eso claro, el posicionamiento correcto de Colón no es "la otra lista", sino:

1. **Reposición urgente** — el SKU que se agotó y no aguanta 60 días de tránsito
2. **Apertura y showroom** — las primeras 8–15 unidades antes de comprometer un contenedor
3. **Mercados que no dan para un contenedor** — Nicaragua, Honduras en fase temprana

> **Fase 1 (año 1): solo Lista A.** Colón se abre en Fase 2, cuando haya ≥2 distribuidores firmados y despachando —para que el inventario tenga más de una salida— y **se financia con anticipos de los propios distribuidores (pedido en firme con 50% de anticipo)**, no con el balance de Vicomer. Esta es la línea roja de caja del Acuerdo B.

### 6.4 El soporte se monetiza o se cofinancia — nunca gratis

| Servicio | Modelo |
|---|---|
| Material de marketing y A&P | **Fondo cooperativo: 2% del FOB aporta el distribuidor, Vicomer iguala 1:1.** Administra Vicomer, se gasta en el mercado del distribuidor |
| Capacitación comercial y técnica | **Una sesión inicial incluida** (remota o en la apertura). Adicionales: facturadas a costo + viáticos |
| Repuestos | **Kit de arranque gratis** — sale del 1% del valor de cada factura que Hyxion ya te entrega en repuestos. **No te cuesta nada y vale mucho en la mesa.** Reposición posterior: costo + 20% |
| Garantía y servicio técnico | **La ejecuta el distribuidor en su país.** Vicomer da protocolo, entrenamiento y backstop con Hyxion. La responsabilidad de postventa frente al cliente final es del distribuidor — esto es contractual, no cortesía |

El kit de repuestos es tu mejor carta gratuita del viernes. Guárdala para cuando Felipe empuje en el override.

### 6.5 Compensación de Felipe en Centroamérica

**Principio: Felipe participa del override neto de Vicomer, no de la venta.** Alineación perfecta, costo fijo cero, sin riesgo de caja: si no hay override cobrado, no hay fee.

| Concepto | **Apertura** | **Techo** |
|---|---|---|
| Participación en override neto cobrado | **25%** | 35% |
| Fee de apertura por distribuidor firmado | **USD 3.000** | 5.000 |
| Cuándo se paga el fee de apertura | **100% contra el *segundo* pedido despachado y cobrado** | contra el primero |
| Vigencia | 3 años renovables, atada al contrato Hyxion | — |

**Que el fee de apertura se pague contra el segundo pedido es deliberado.** Si se paga contra la firma, el incentivo de Felipe es firmar rápido y muchos —incluidos distribuidores débiles que te queman el país por tres años. El segundo pedido es la primera evidencia real de que el distribuidor funciona.

### 6.6 Terminación

- Si el contrato Hyxion termina o no se renueva (oct-2029), **el Acuerdo B termina automáticamente**, sin indemnización ni compensación de ningún tipo.
- Si la adenda de territorio no se perfecciona, el acuerdo **nunca entra en vigor** (condición suspensiva, §4.2).
- No competencia: Felipe no representa marcas de electrodomésticos de cocina competidoras en el territorio durante la vigencia y 12 meses después.
- Confidencialidad y no elusión: no contactar directamente a Hyxion ni a distribuidores del territorio fuera de Vicomer, durante la vigencia y 24 meses después. **Esta cláusula es tan importante como la económica** — Felipe va a conocer a tu fábrica y a tu red.

---

## 7. IMPACTO

| Dimensión | Acuerdo A — Colombia | Acuerdo B — Centroamérica |
|---|---|---|
| **Caja** | Neutro si se paga sobre cobrado. Negativo si se cede a pagar sobre facturación | Positivo desde el primer despacho en Fase 1. **Negativo si se abre Colón con balance propio** |
| **Impuestos** | Retención al exterior + régimen cambiario si se paga desde Vintral. Riesgo de agencia comercial | Depende del vehículo. Panamá es la ruta natural; verificar lista SRI |
| **Estructura** | Añade un actor sobre un país que acabas de simplificar | Añade un vehículo y un contrato marco. Es el escalón hacia plataforma |
| **Patrimonio** | Marginal | **Alto** — consolidar la marca en CA es el activo que se negocia en la renovación de 2029 |
| **Riesgo** | Conflicto de canal, doble pago, cartera, art. 1324 | Mínimo con Hyxion sin respaldo, distribuidor malo con exclusividad, inventario en Colón |
| **Escalabilidad** | Baja — es un país más | **Alta — es un modelo replicable a Chile/Perú sin capital** |

---

## 8. RECOMENDACIÓN EJECUTIVA

**Si yo fuera el CFO, el viernes hago cuatro cosas y ninguna más:**

1. **Le doy prioridad al Acuerdo B y le bajo la temperatura al A.** El Acuerdo B es capital-light, escalable y construye el activo que negocias en 2029. El A es marginal, riesgoso en atribución y, sobre todo, **llega antes que el reprecio**. Propón el A como piloto acotado de 12 meses con techo de USD 25.000, no como la pieza central.

2. **Condiciono todo a la adenda de Hyxion.** Pre-acuerdo con condición suspensiva. Nada de territorio prometido sobre una negociación en trámite.

3. **Fase 1 sin Colón.** Solo Lista A, ex-China, MOQ de contenedor, 100% anticipado o LC. Colón entra en Fase 2 financiado por anticipos de distribuidores.

4. **Cierro D2 (el reprecio de Colombia) antes o en la misma semana.** Con la lista 23% desalineada, cualquier puerta que Felipe abra en Colombia se cierra en la cotización. Es la decisión que estaba pendiente desde el 15-sep y la que más plata mueve de todo este paquete.

**Lo que NO recomiendo:** un contrato único, equity para Felipe en esta ronda, exclusividad sin mínimos, inventario en Colón con balance propio, y comisión sobre facturación.

---

## 9. GUION Y LÍNEAS ROJAS PARA EL VIERNES

**Orden de la conversación** (no lo inviertas — si empiezas por Colombia, la reunión se consume ahí):

1. Centroamérica primero: visión, territorio, modelo máster, escalera de exclusividad
2. Listas de precios y MOQ
3. Compensación CA (override compartido)
4. Colombia al final, como piloto acotado
5. Cierre: condición suspensiva + próximos pasos con fecha

**Las siete líneas rojas:**

| # | Línea roja | Si Felipe empuja |
|---|---|---|
| 1 | Dos contratos separados | No es negociable. Es protección mutua, véndelo así |
| 2 | Condición suspensiva sobre la adenda Hyxion | "No puedo comprometer lo que todavía no tengo — y tú tampoco querrías que lo hiciera" |
| 3 | Costa Rica y CEMACO fuera del territorio | No es negociable |
| 4 | Sin exclusividad sin mínimo con degradación automática | Puedes bajar el mínimo, nunca quitar la cláusula |
| 5 | Fee sobre cobrado, con clawback a >90 días | Puedes dar anticipo del 50% contra factura; el clawback se queda |
| 6 | Sin crédito a distribuidores CA en año 1 | Puedes ofrecer LC confirmada en lugar de anticipo |
| 7 | Sin inventario en Colón en Fase 1 | "Lo abrimos cuando haya dos distribuidores comprando — y lo financiamos con sus anticipos" |

**Margen de concesión que tienes** (úsalo en este orden, de barato a caro): kit de repuestos gratis → una capacitación presencial en apertura → co-op de marketing 1:1 → subir override de Felipe de 25% a 30% → subir fee de apertura de $3.000 a $5.000 → subir tarifa de cuenta nueva Colombia de 12% a 15% del MB.

**Preguntas que tienes que hacerle tú** (y cuyas respuestas valen más que el term sheet):
- ¿Qué distribuidores específicos tiene identificados por país, y con cuáles ya habló?
- ¿Cuánto de su tiempo va a dedicar a esto, y de qué vive mientras arranca?
- ¿Tiene relación directa con Hyxion? *(Si la tiene, la cláusula de no elusión sube de importancia.)*
- En Corona, ¿quién es el contacto y a qué nivel? ¿Es compra de marca propia o de marca de terceros?
- ¿Bajo qué vehículo y en qué país quiere facturar?

---

## 10. PLAN DE ACCIÓN

| # | Acción | Responsable | Límite |
|---|---|---|---|
| 1 | **Cerrar D2 — reprecio de lista Colombia (−23,4%) y los 4 SKU driver (−36,2%)** | JMV + Tafur | **30-sep** |
| 2 | Reunión Felipe: presentar term sheet, no cerrar cifras en la mesa | JMV | 25-sep |
| 3 | Confirmar por escrito con Hyxion el alcance exacto de la adenda de territorio CA y si trae mínimo de compra | JMV | 10-oct |
| 4 | Construir las dos listas de precios reales por SKU con el `MAESTRO_IMPORTACIONES` + fletes verificados con Logística | JMV + Logística | 15-oct |
| 5 | Consulta a Ocampo Gómez: estructura no-agencia para Colombia (art. 1324) + régimen cambiario del pago de comisiones | JMV | 15-oct |
| 6 | Definir vehículo de facturación CA y validar tratamiento SRI de Panamá con el tributarista | JMV | 31-oct |
| 7 | Redactar borrador de contrato de sub-distribución CA (plantilla reutilizable por país) | Legal | 15-nov |
| 8 | Acuerdo marco Casa Magna firmado **antes** de abrir Corona | JMV + Tafur | 30-nov |

**Las tres que bloquean todo lo demás: #1, #3 y #6.**

---

## ANEXO — Datos base

- Colombia, Odoo corte 31-ago-2026: venta YTD COP 1.125.563.011 · ppto YTD COP 1.985.790.715 · cumplimiento 56,7% · run-rate anual COP 1.688.344.516 (46,0% del ppto anual COP 3.671.996.149)
- Concentración Colombia ene–sep 2026, **cobertura 100%** (Q1 reconstruido con `VENTAS VINTRAL 2026 HASTA MARZO.xlsx` + Odoo abr–sep): CASAMAGNA 55,95% · USA ELECTRODOMÉSTICOS 32,97% · Vicomer intercompañía 7,83% · INVERDESCUENTOS 2,73% · resto 0,52% · HHI 4.286 (terceros 4.973) · venta de terceros COP 1.181M ≈ USD 319K
- Colombia Q1 2026: COP 262.321.141 (base factura, `odoo_config.json → colombia_hist_mensual`, instancia `vintral1.odoo.com`) vs COP 301.427.023 (base pedido, `sale.report`) — **discrepancia 14,9% entre objetos de Odoo**
- Cobertura del desglose por cliente de **Ecuador: 15,9%** — hueco abierto, fuera del alcance de este documento
- Cartera Colombia: DSO 183,7 días · 61,1% vencida · 42,2% a más de 30 días vencidos
- Costa Rica: YTD USD 86.197 · CEMACO 100% (HHI 10.000) · 52,8% del ppto · cartera 100% vencida
- Contrato Hyxion 16-oct-2024: exclusividad Ecuador/Colombia/Costa Rica · vigencia hasta oct-2029 · mínimo USD 600.000/año (gatillo de terminación bajo 75% dos años seguidos) · pagos 20/50/30 · 1% de cada factura en repuestos gratis · multa por violación de exclusividad 20% del FOB comprado desde 2023
- Margen bruto usado para modelar: **45%** (Vintral 2025 ≈51%; el 58% YTD de Odoo no es confiable — COGS sin mensualizar)
- TC referencial: 3.700 COP/USD
- **Estimados no verificados (marcados como tales):** flete China→CA USD 4.000/40HQ · flete Colón→CA USD 1.200/40HQ · factor landed ZLC 1,12 · FOB de referencia por contenedor USD 60.000 · mínimos anuales por país CA
