# Diagnóstico CFO — Comité de Pagos VICOMER

**Fecha:** 15 de septiembre de 2026 · **Semana de datos:** 2026-W37 (generada 11-sep 08:05)
**Alcance:** ecosistema completo de CxP y órdenes de pago — EC, CR, CO

---

## 1. CONTEXTO

El Comité de Pagos fue diseñado como un circuito cerrado de 5 eslabones:

```
[1] Mac vie 08:00  pagos_cxp.py -> Odoo -> cxp_semana_actual.json
[2] Claude 08:45   sube el JSON a Drive
[3] Artefacto      tú apruebas/rechazas -> genera orden de pago
[4] Claude 12:30   baja las órdenes -> Pagos/salida/
[5] Mac WatchPath  pagos_correo.py -> correo a ti y a los responsables
```

La tesis del diseño era buena: separar **extracción** (automática, sin criterio) de
**decisión** (tú, con criterio) y de **ejecución** (banco). El diagnóstico de hoy es que
sólo los eslabones 1 y 2 están vivos, y el 1 funciona a medias.

---

## 2. DIAGNÓSTICO CFO

### 2.1 El circuito está roto en el eslabón que genera valor

`Pagos/correo.log` registra **34 corridas consecutivas de "Sin archivos pendientes"**.
La última orden de pago emitida por este sistema es del **6 de julio de 2026**.

| Eslabón | Estado | Evidencia |
|---|---|---|
| 1. Extracción CxP | ⚠️ Errática | 5 archivos en 10 semanas (W28, W32, W34, W35, W37). Faltan W29-31, W33, W36 |
| 2. Subida a Drive | ✅ Vivo | Subida de hoy correcta, 45.092 bytes |
| 3. Artefacto → orden | ❌ Sin uso | Cero órdenes generadas desde 6-jul |
| 4. Bajada de órdenes | ❌ Deshabilitada | Apagada desde 13-jul (documentado en ORDEN_PAGO_SETUP.md) |
| 5. Correo/ejecución | ❌ Inactivo | 34 corridas vacías |

**Lectura:** el sistema produce información que nadie consume. Diez semanas de reporting
sin una sola decisión registrada. Esto no es un problema técnico — es que el comité no
está operando como comité.

### 2.2 Bug de agregación multi-moneda en Costa Rica

`pagos_cxp.py` línea 408:

```python
total_local = round(sum(f["monto"] for f in facts), 2)
```

Suma los montos **sin discriminar moneda** y luego etiqueta el resultado con la moneda
esperada del país (`p["moneda"]`). En Costa Rica, donde conviven facturas en CRC y en USD,
el resultado es una cifra sin significado: 239.427,05 CRC + 1.450,36 USD = "240.877,41 CRC".

Dos agravantes:

- **Línea 395** exculpa explícitamente al USD de la detección de monedas raras:
  `raras = monedas - {p["moneda"], "USD"}`. El único caso que rompe el total es justo el
  que el validador deja pasar sin advertencia.
- **El autotest (línea 569) prueba CR con una sola factura en CRC.** Nunca ejerce el caso mixto.

**Alcance histórico:** el defecto está presente en **las 5 semanas** del histórico. Nunca ha
existido una cifra correcta de Costa Rica en este sistema.

| Semana | CR reportado | CR real |
|---|---|---|
| W28 | 4.574.279,52 "CRC" | 4.574.279,52 CRC + 3.711,37 USD |
| W32 | 4.325.011,42 "CRC" | 4.322.204,05 CRC + 2.807,37 USD |
| W34 | 345.131,31 "CRC" | 341.776,41 CRC + 3.354,90 USD |
| W35 | 345.131,31 "CRC" | 341.776,41 CRC + 3.354,90 USD |
| W37 | 240.877,41 "CRC" | 239.427,05 CRC + 1.450,36 USD |

*Nota:* el `total_usd` sí se calcula factura por factura y es correcto. El daño está
concentrado en la cifra que el propio diseño declara autoritativa.

### 2.3 El tipo de cambio del peso colombiano está 19% desactualizado

`pagos_reglas_depto.json` fija `COP: 0.00027027` → **3.700 COP/USD**, anotado como
"jul-2026". La TRM del 15-sep-2026 es **3.109,30**.

Con tasas reales de mercado:

| País | Local | TC usado | TC real | USD reportado | USD real |
|---|---|---|---|---|---|
| CO | 516.976.080,81 COP | 3.700 | **3.109,30** | 139.723 | **166.268** |
| CR | 239.427,05 CRC | 452,49 | 449,94 | 1.979 | **1.982** |
| EC | 32.321,12 USD | — | — | 32.321 | 32.321 |
| **Grupo** | | | | **174.024** | **200.571** |

La CxP del grupo está **subvaluada en USD 26.548 (15,3%)**. El peso real de Colombia no es
80% sino **82,9%** de la deuda comercial del grupo.

El CRC (452,49 vs 449,94) está dentro de tolerancia — 0,6% de desvío.

### 2.4 Concentración extrema y deuda congelada en Colombia

Colombia es el 83% de la CxP del grupo, y dentro de Colombia:

| Proveedor | COP | USD | % CxP CO |
|---|---|---|---|
| HYXION | 361.462.928 | 116.252 | **69,9%** |
| DEPLOYMENT LOGISTICS | 87.521.356 | 28.148 | 16,9% |
| LOGICA INVERSIONES | 22.738.864 | 7.313 | 4,4% |
| **Top 3** | | | **91,2%** |

**HYXION lleva congelado desde julio.** Dos facturas, montos idénticos en las 5 semanas
del histórico: 250.669.479,16 (142 días vencida) y 110.793.449,20 (78 días). Su RUC
registrado es `11111111111111111` — dato inventado. Un proveedor que representa el 58% de
la CxP del grupo entero no tiene identificación fiscal válida en el maestro.

**DEPLOYMENT LOGISTICS** acumula 4 facturas de hasta **148 días**.

### 2.5 La CxP no baja: crece

| Semana | CO (COP) | Docs W28 aún abiertos |
|---|---|---|
| W28 | 359.305.855 | — |
| W32 | 513.588.557 | |
| W34 | 513.953.129 | |
| W35 | 512.175.158 | |
| W37 | 516.976.081 | **50%** de los docs de W28 siguen abiertos |

De los 36 documentos de la semana 28, **18 siguen vivos 9 semanas después**. De los 89 de
W32, 41 (46%) siguen abiertos. Colombia sumó 158 millones de COP entre julio y septiembre
sin amortizar el stock viejo.

**97,7% de la CxP del grupo está vencida** (112 de 116 documentos).

### 2.6 Aging real

| Bucket | EC (USD) | CR | CO (COP) |
|---|---|---|---|
| Por vencer | 2.248 | — | 7.940.935 |
| 1-30 d | 29.408 | 452 USD | 38.489.514 |
| 31-60 d | 665 | 452 USD | 45.420.218 |
| 61-90 d | — | 239.427 CRC + 225 USD | 111.501.617 |
| > 90 d | — | 321 USD | **315.052.096** |

En Colombia, **61% de la deuda tiene más de 90 días**. En Ecuador la cartera es joven
(efecto de la migración: se está cargando histórico reciente, de 6.960 a 32.321 USD en dos
semanas — no es deterioro, es visibilidad nueva).

---

## 3. RIESGOS OCULTOS

1. **Riesgo cambiario no medido en HYXION.** Un proveedor de importación con RUC falso y
   saldo en COP probablemente tiene una obligación subyacente en USD o CNY. Si es así, la
   devaluación/revaluación del peso ya movió esa deuda y nadie lo está midiendo. Con el
   peso apreciándose de 3.700 a 3.109 (-16%), una deuda en divisa se abarató en COP — pero
   si está registrada en COP a tasa histórica, el pasivo real difiere del contable.

2. **Riesgo reputacional y de suministro.** 148 días de mora con el operador logístico
   (DEPLOYMENT) y 142 con el proveedor principal. El siguiente embarque puede quedar
   retenido. Esto no aparece en ningún reporte financiero pero es el riesgo operativo
   más inmediato.

3. **Riesgo de decisión sobre dato falso.** Mientras el comité no opere, nadie decide sobre
   la cifra de CR mezclada ni sobre el USD subvaluado. En el momento en que el circuito se
   reactive, se decidirá sobre números malos. El bug es más peligroso *cuando el sistema
   vuelva a funcionar* que ahora.

4. **Riesgo de gobierno.** Cero trazabilidad de qué se pagó y por qué desde julio. Si los
   pagos se están ejecutando fuera del sistema (y con 158M COP de movimiento, algo se está
   pagando en algún lado), existe un proceso de pagos paralelo, informal y sin registro.
   **Ésta es la pregunta abierta más importante del diagnóstico.**

5. **Fragilidad del LaunchAgent.** El agente se descarga tras reinicios de macOS. Ya pasó el
   31-jul (21 días sin correr). El patrón de huecos (W29-31, W33, W36) sugiere que vuelve a
   pasar. Toda la cadena depende de que un Mac esté encendido un viernes a las 08:00.

---

## 4. OPORTUNIDADES

- **La infraestructura ya existe y es buena.** El extractor, las advertencias, el panel de
  diagnóstico, el bloqueo por dato obsoleto — el diseño es sólido. No hay que reconstruir,
  hay que reparar y usar.
- **Los 3 países ya están en una sola instancia Odoo.** Eso habilita saldo bancario,
  conciliación real y registro de pago desde el mismo origen. La migración pagó el costo;
  falta cobrar el beneficio.
- **91% de la CxP de Colombia son 3 proveedores.** Negociar 3 acuerdos de pago resuelve el
  problema estructural. No es un problema de 116 facturas, es un problema de 3 conversaciones.

---

## 5. IMPACTO

| Dimensión | Efecto |
|---|---|
| **Caja** | USD 200.571 de deuda comercial real, 97,7% vencida. Necesidad de caja inmediata mal dimensionada en -15% |
| **Impuestos** | Sin impacto directo; sí riesgo si HYXION no tiene soporte fiscal válido (RUC inválido → deducibilidad cuestionable en CO) |
| **Estructura** | Un proveedor sin identificar concentra el 58% de la CxP del grupo |
| **Patrimonio** | El pasivo corriente consolidado está subvaluado en USD 26.548 en el reporting interno |
| **Riesgo** | Alto: mora de 5 meses con proveedor y operador logístico críticos |
| **Escalabilidad** | El proceso depende de un Mac encendido y de un comité que no se reúne |

---

## 6. RECOMENDACIÓN EJECUTIVA

Si yo fuera el CFO, el orden sería éste — y no empezaría por el código.

**La pregunta previa:** ¿cómo se están pagando las facturas hoy? Si hay un circuito paralelo
funcionando, arreglar la herramienta es irrelevante hasta entenderlo. Si no hay circuito y
simplemente no se está pagando, entonces el problema es de caja y hay que decirlo así.

Después, en este orden:

1. **Reparar la cifra antes de reactivar el comité** (P0, técnico, bajo esfuerzo).
   Nadie debe aprobar pagos contra totales mezclados ni contra un USD 15% subvaluado.
2. **Resolver HYXION y DEPLOYMENT** (P0, negociación). 86,8% de la CxP colombiana en dos
   conversaciones. Acuerdo de pago con calendario, no goteo.
3. **Reactivar el circuito completo** (P1). Un comité que no emite órdenes no es un comité.
4. **Endurecer la automatización** (P1). Que el pipeline se auto-recupere y avise cuando
   no corre, en lugar de fallar en silencio.

---

## 7. PLAN DE ACCIÓN

### P0 — Esta semana

| # | Acción | Dónde | Esfuerzo |
|---|---|---|---|
| 1 | Separar `total_local` por moneda: `totales_por_moneda: {CRC: x, USD: y}` y marcar el país como multi-moneda | `pagos_cxp.py` L408 | 1 h |
| 2 | Quitar el USD de la whitelist de monedas raras; advertir siempre que un país tenga >1 moneda | `pagos_cxp.py` L395 | 15 min |
| 3 | Añadir caso de test mixto CRC+USD al autotest | `pagos_cxp.py` L569 | 30 min |
| 4 | Actualizar `tc_manual`: COP 0,0003216 (3.109,30) · CRC 0,0022225 (449,94) | `pagos_reglas_depto.json` | 5 min |
| 5 | Confirmar la identidad fiscal real de HYXION y corregir el RUC en Odoo | Odoo CO | — |
| 6 | Responder: ¿cómo se pagan hoy las facturas? | — | — |

### P1 — Próximas 2 semanas

| # | Acción | Esfuerzo |
|---|---|---|
| 7 | TC automático desde API (Banrep para COP, BCCR para CRC) con fallback al override manual y sello de fecha | 3 h |
| 8 | Reactivar `pagos-bajar-ordenes` y probar el circuito end-to-end con una orden real | 1 h |
| 9 | Watchdog: si el CxP tiene más de 8 días, correo de alerta automático | 1 h |
| 10 | `launchctl bootstrap` idempotente al inicio de sesión para que el agente sobreviva reinicios | 1 h |
| 11 | Acuerdo de pago documentado con HYXION y DEPLOYMENT | — |

### P2 — Mes

| # | Acción |
|---|---|
| 12 | Saldo bancario por país en el artefacto (`account.journal` tipo bank) — decidir pagos contra caja disponible, no contra deuda |
| 13 | Completar el archivo de carga masiva Banco Guayaquil (falta `cuenta_empresa`) |
| 14 | Conciliación: registrar el pago en Odoo desde `ejecucion_*.json` |
| 15 | KPI semanal: DPO por país, % vencido > 90 días, concentración top-3 |

---

## 8. DATO DE SEGUIMIENTO

Cifras autoritativas de la semana 2026-W37, ya corregidas:

- **Ecuador:** 32.321,12 USD · 47 docs · 46 vencidos
- **Costa Rica:** 239.427,05 CRC + 1.450,36 USD · 11 docs · 11 vencidos
- **Colombia:** 516.976.080,81 COP · 58 docs · 55 vencidos · 1 NC de 1.428.300 COP
- **Grupo (TC 15-sep):** USD 200.571 · 97,7% vencido

---

*Fuentes de tipo de cambio: [TRM Colombia 15-sep-2026](https://www.colombia.com/actualidad/economia/precio-del-dolar-hoy-en-colombia-martes-15-de-septiembre-de-2026-600616) · [Tipo de cambio BCCR 14-sep-2026](https://acontecer.co.cr/tipo-de-cambio)*
