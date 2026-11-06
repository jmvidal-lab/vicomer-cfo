# PROMPT MAESTRO — Dashboard Ejecutivo de Compras Locales y Cuentas por Pagar (Grupo VICOMER)

> **Cómo usarlo:** abre una tarea nueva en el proyecto *CFO VICOMER* y pega TODO desde `--- INICIO DEL PROMPT ---`. Las secciones 2 y 3 son las que evitan que el dashboard mezcle tres cosas distintas (gasto, deuda y caja) y produzca cifras falsas.

---

--- INICIO DEL PROMPT ---

## 0. ROL Y MISIÓN

Actúas como **CFO + ingeniero de datos financieros** del Grupo VICOMER. Construyes un **sistema de dashboards ejecutivos de compras locales y cuentas por pagar**: la contracara del dashboard de ventas. Responde tres preguntas de gerencia que hoy nadie puede contestar en un solo lugar:

1. **¿En qué se me va la plata con proveedores locales, y contra qué presupuesto?**
2. **¿Cuánto debo, a quién, y cuán vencido está?**
3. **¿Qué tengo que pagar en las próximas semanas y me alcanza la caja?**

Regla rectora: **una cifra sin fuente verificable no entra al dashboard.** Antes de estimar, muestras el hueco marcado como hueco.

---

## 1. ENTORNO REAL (ya verificado — no lo re-descubras)

**Máquina y rutas**
- Todo corre en el Mac del usuario: `~/Claude/Projects/CFO VICOMER/`. Carpetas conectadas adicionales: `~/Desktop/VICOMER LOGISTICA` y `~/Desktop/VICOMER PERSONAL`.
- El sandbox de Cowork **NO alcanza `vicomer.odoo.com`** (DNS bloqueado) y `device_bash` **no tiene red**. Toda extracción de Odoo se ejecuta en el Mac (`.command` de doble clic o LaunchAgent); los JSON caen en la carpeta montada y desde ahí sí se leen.

**Conexión Odoo** (`odoo_config.json`)
- URL `https://vicomer.odoo.com` · DB `intitecnologia-v-comer-main-27740127` · login `jmvidal@v-comer.com` · API key en `odoo_apikey.txt` · Odoo **18.0+e**, XML-RPC, solo stdlib.
- 4 compañías: **VICOMER S.A.S.** (id=2, EC, USD) · **VINTRAL S.A.S.** (id=1, CO, COP) · **3-102-940094 SRL** (id=3, CR, CRC) · **VIX S.A.S.** (id=11) → **VIX se EXCLUYE.**

**Activos que YA existen — reutilízalos, no los reescribas**

| Archivo | Qué hace | Salida |
|---|---|---|
| `pagos_cxp.py` v3 | **Base del dashboard.** CxP de los 3 países desde Odoo, NC de proveedor restando, depto por reglas, TC manual, modos `diag`/`autotest` | `Pagos/cxp/cxp_semana_actual.json` + `cxp_YYYY-Www.json` |
| `pagos_reglas_depto.json` | Proveedor → departamento (Comercial/Operaciones/Gerencia) + `tc_manual` | — |
| `pagos_correo.py` | Correo del Comité de Pagos (viernes) | `Pagos/enviados/` |
| `banco_guayaquil.py` | Genera el .txt de carga masiva (20 campos, 189 beneficiarios). **`cuenta_empresa` sigue en `null`** | `Pagos/banco/` |
| `odoo_estados_financieros.py` | EEFF desde Odoo, modo `puc` por prefijo, tiene modo `conciliar` | `Finanzas/` |
| `odoo_descubrir.py` | Retrato de la instancia (partners, plan de cuentas) | `OdooVentas/descubrimiento_odoo.json` |

**Estructura del JSON de CxP que ya existe** (extiéndelo, no lo reinventes):
```
semana, generado, version, fuente, tc_usd{COP,CRC,USD}, tc_confiable(false),
tc_origen, notas[], companias_odoo, consolidado{total_usd, vencido_usd,
n_documentos, referencial, por_pais_local}, paises[{code, nombre, sistema,
origen, moneda, advertencias[], resumen{...}, facturas[{id, proveedor, ruc,
factura, emision, vence, monto, moneda, tipo, compania, depto, dias_vencida}]}]
```

**Trampas técnicas confirmadas**
1. **`account.move` revienta** en lecturas amplias (el módulo `l10n_ec` está a medio instalar: falta `account_move.l10n_ec_sri_import_withhold`). **Usa `account.move.line`** e infiere el tipo de documento por prefijo del nombre — así lo resolvió `cartera_v3.py`.
2. **`account.account.code` es company-dependent desde Odoo 17**: léelo con **UNA sola compañía en el contexto** o 2.173 de 2.823 cuentas salen sin código.
3. **Odoo NO mantiene tipos de cambio** (COP, CRC y EUR devuelven todas `0.00031805`, lo que inflaba la CxP de Colombia ~24%). Usa `pagos_reglas_depto.json → tc_manual` (`COP 0.00027027`, `CRC 0.00221`).
4. Los LaunchAgents fallan con `PermissionError` si `/usr/bin/python3` no tiene **Acceso Total al Disco**.
5. El agente `com.vcomer.pagos.cxp` **no dispara los viernes 08:00 si el Mac está suspendido**. No lo empeores: el dashboard debe mostrar la antigüedad del dato y gritar si el JSON tiene más de 3 días.

---

## 2. ALCANCE: QUÉ ENTRA Y QUÉ NO (esto define el dashboard)

### 2.1 "Proveedor local" = país del partner en Odoo
**Decisión del usuario:** local = `res.partner.country_id` **igual al país de la compañía** que registra la factura (EC→Ecuador, CO→Colombia, CR→Costa Rica). Todo lo demás es **exterior** y queda fuera del dashboard.

**Obligaciones que esta decisión te impone (no son opcionales):**
- **Paso 0 del pipeline: mide la cobertura.** Cuenta qué % de los partners proveedores tiene `country_id` cargado y repórtalo antes de construir nada. De 1.679 partners, solo el 85,8% tiene VAT; la cobertura de país **no está medida todavía**. Si la cobertura es **< 95%**, detente y avísale al usuario antes de seguir: un dashboard de compras con 10% de proveedores sin clasificar no sirve para decidir.
- **Bucket "SIN CLASIFICAR" siempre visible**, con su monto y su conteo, y un botón para exportar la lista. Nunca lo repartas ni lo escondas en "otros".
- **Declara el falso positivo conocido:** los agentes de aduana, navieras representadas y forwarders **constituidos localmente** (p. ej. agencias de aduana colombianas, `SERVICIOS INTEGRALES DE LOGISTICA GLOBAL` en CR) entrarán como **locales** aunque su factura sea gasto de importación. El dashboard debe marcarlos con una etiqueta "servicio de comercio exterior" derivada de la cuenta contable de la factura, para que se puedan aislar de un clic. No los excluyas por tu cuenta: márcalos.
- **Referencia de magnitud (CxP semana 2026-W34):** con esta regla, Colombia pierde a **HYXION (361M COP)** y a **VIAL SHIPPING (14,5M COP)** — juntos ~73% de la CxP colombiana. Eso es correcto y esperado: son compras de importación. Pero el dashboard debe decir **explícitamente cuánto quedó fuera**, en una tarjeta "Excluido por ser exterior: $X (N documentos)". Un usuario que ve $138M COP de CxP local sin saber que hay $376M de importación afuera, decide mal.

### 2.2 "Compras" = operativas, sin financieros ni impuestos
Entran: bienes y servicios de proveedores. **Salen:** bancos y tarjetas (Banco Diners, Banco Guayaquil, Banco Pichincha…), impuestos y retenciones, nómina y aportes de seguridad social, intercompañía (VICOMER↔VINTRAL↔CR↔VIX), y préstamos a socios.

Clasifica por **cuenta contable de la línea de factura** (`account.move.line.account_id`), no por el nombre del proveedor. El nombre es heurística de respaldo. Documenta el mapeo en un JSON editable `compras_reglas.json` — el usuario tiene que poder corregirlo sin tocar código.

### 2.3 Los tres números NO son el mismo número
Este es el error que hunde a la mayoría de dashboards de compras. Sepáralos visualmente y nómbralos distinto en toda la interfaz:

| Concepto | Qué es | De dónde sale |
|---|---|---|
| **Gasto / compra del período** | Flujo devengado del mes (contra presupuesto) | Líneas de factura de proveedor por fecha de emisión |
| **Saldo de CxP** | Stock de deuda a hoy | `pagos_cxp.py` (saldo pendiente) |
| **Pagos ejecutados** | Salida real de caja | `account.payment` / conciliaciones |

Nunca sumes uno con otro. Nunca compares gasto devengado contra presupuesto de caja.

---

## 3. REGLAS DE NEGOCIO NO NEGOCIABLES

1. **Notas de crédito de proveedor (`in_refund`) restan.** Solo documentos `posted`.
2. **Moneda:** cada país en **su moneda es la cifra autoritativa**; el consolidado USD es **REFERENCIAL** y lleva badge visible con tasa y fecha. Ya está así en `cxp_semana_actual.json` (`tc_confiable: false`).
3. **Corte de migración de Ecuador = 2026-08-01.** Odoo EC solo tiene movimientos desde esa fecha. Los **saldos de proveedor** sí se trasladaron en el asiento de apertura, así que la **CxP de EC en Odoo es válida**; pero el **gasto devengado Ene–Jul de EC NO está en Odoo** y hay que leerlo de las fuentes del punto 4.3.
4. **NUNCA leas el asiento de apertura de Odoo como estado de resultados.** Usa cuentas de resultado como vehículo (`5001 APERTURA ANTICIPO CLIENTE`, `5002 APERTURA SALDO PROVEEDOR`, `5004 APERTURA INVENTARIOS`) y leído como P&G da una pérdida ficticia de −232.908. La cifra oficial está en `Finanzas/eeff_ecuador_2026-07_OFICIAL.json`.
5. **VIX S.A.S. se excluye.** VICOMER LOGISTICA no existe en Odoo.
6. **Huecos que el dashboard DECLARA, no rellena:**
   - **Presupuesto de gastos solo existe para Ecuador.** Colombia y Costa Rica **no tienen presupuesto de gastos 2026**: sus dashboards muestran el bloque de presupuesto como "no disponible", nunca contra cero.
   - El P&L de VINTRAL está contaminado (cuentas "AJUSTE INICIAL…" mal clasificadas como `expense` y un "PROMOCIÓN Y PUBLICIDAD" de 6.6B COP por misposting ≈ $1,79M). **El dashboard de compras de Colombia debe filtrar esas cuentas y decirlo**, o el gasto colombiano sale inflado ~10x.
   - El plan de cuentas no tiene prefijos 53/54/55 y el 52 concentra 193 cuentas → el gasto operativo **total** es correcto, su **apertura** administrativo/financiero/no deducible no lo es.
   - Costa Rica no registra COGS en Odoo.

---

## 4. PRESUPUESTO DE GASTOS 2026 (Ecuador)

### 4.1 Los dos archivos y cuál manda
Ambos están en `~/Desktop/VICOMER PERSONAL/`:

| Archivo | Qué contiene | Uso |
|---|---|---|
| **`PRESUPUESTO GASTOS REVISADO 2026 OK OK.xlsx`** (jul-2026) | Hoja `Presupuesto Gastos H2 2026`: **Jul–Dic por cuenta** (Código, Cuenta, Jul…Dic, Total H2). Hoja `Resumen 2026`: H1 real vs H2 presupuesto. Hoja `Estado de Resultados Mensual`: real Ene–Jul por cuenta y mes | **PRESUPUESTO VIGENTE** para Jul–Dic |
| **`PRESUPUESTO COMPLETO 2026 - ADMINISTRATIVO.xlsx`** (mar-2026) | Hoja `Presupuesto Anual`: **Ene–Dic por cuenta**, presupuesto original | **PRESUPUESTO ORIGINAL** (base de comparación) |

**Insight que debes construir, no solo mostrar:** el dashboard compara **real vs vigente vs original**. La diferencia entre el presupuesto original y el resincerado de julio es una decisión de gerencia que hoy no está documentada en ningún tablero. Muéstrala como una barra de "resinceramiento" por línea de gasto.

### 4.2 Cifras de anclaje (si tu extracción no reproduce esto, hay un bug)
- Total gastos presupuestados **H2 2026 = USD 251.179,21** (5.2 + otros).
- Gastos de Ventas H2 = 118.905,28 · Administrativos H2 = 105.522,51 · Financieros H2 = 16.966,68 · No deducibles H2 = 9.784,74.
- Real H1 (Ene–Jun): Gastos de Ventas 125.016,61 · Administrativos 126.671,27.
- **Cifra oficial Ene–Jul 2026 (EC)** — `Finanzas/eeff_ecuador_2026-07_OFICIAL.json`: ventas netas 1.118.645,46 · costo de ventas 650.933,72 · gastos de ventas 142.154,78 · gastos administrativos 132.565,41 · financieros 12.715,76 · no deducibles 26.703,95 · **resultado +154.541,84**.

### 4.3 Trampa de mapeo (te va a morder)
Los códigos del Excel **llevan puntos**: `5.2.01.06.05`. Los códigos de Perseo/Odoo van **sin puntos**. Normaliza a un formato canónico antes de cruzar, y **reporta cuántas cuentas del presupuesto no encontraron pareja** en el real y viceversa. Un cruce silencioso que pierde el 30% del presupuesto se ve perfecto en pantalla.

Además, el presupuesto es **por cuenta contable** y la CxP es **por proveedor**. El puente es la **cuenta de gasto de cada línea de factura** (`account.move.line`). Sin ese puente no hay comparación real vs presupuesto por proveedor: dilo antes de prometerlo.

---

## 5. ARQUITECTURA OBLIGATORIA

**Script en el Mac + datos embebidos** (igual que el dashboard de ventas). El artefacto HTML **no** llama a Odoo: CORS y la API key quedaría expuesta en el HTML.

```
Odoo (XML-RPC) ──┐
Excels de ppto ──┼→ compras_dashboard.py → OdooVentas/dashboard_compras.json
EEFF oficial EC ─┘                                    ↓
                                      compras_dashboard_render.py
                                                      ↓
        4 HTML autocontenidos (Ecuador · Colombia · Costa Rica · Consolidado)
                                                      ↓
                     LaunchAgent diario + publicación como artefacto persistente
```

- Python 3 **solo stdlib** para la parte de Odoo. Para leer los Excel, `openpyxl` (ya instalado) aislado en su propio módulo, con **caché en JSON** para que el dashboard no dependa de que los Excel estén abiertos o sincronizados desde iCloud.
- Separación estricta **extracción → JSON → render**. El JSON es el contrato.
- El JSON lleva: `generado`, `periodo`, `fuentes` por bloque, `tc_usado` con fecha, `cobertura_clasificacion` (% de proveedores con país), `excluido_exterior` (monto y conteo), y `avisos[]`.
- **Modos CLI obligatorios:** `diag`, `autotest` (offline), y ejecución normal.
- **Degradación elegante:** si una fuente falla, el bloque sale marcado en rojo como "sin datos". **Cero real y dato faltante deben verse distinto.**
- **Alerta de frescura:** si el JSON de CxP tiene más de 3 días, banner ámbar en los 4 dashboards.
- **LaunchAgent** `com.vcomer.dashboard.compras`, diario **07:45** (después de ventas, antes de la jornada), con `run.log` y `error.log`. Instalador `.command` de doble clic siguiendo el patrón de `instalar_pagos.command`.
- **No rompas** `com.vcomer.pagos.cxp`, `com.vcomer.presupuesto`, `com.vcomer.casamagna` ni el correo del comité.

---

## 6. ESPECIFICACIÓN DEL DASHBOARD

Genera **4 artefactos**: `Dashboard_Compras_Ecuador`, `_Colombia`, `_CostaRica`, `_Consolidado_Grupo`. Mismo motor, misma estética, mismo JSON.

### 6.1 Estructura fija (de arriba hacia abajo)

**A. Barra de estado**
`Datos al <fecha> · CxP generada <fecha> · Clasificación de proveedores: N% con país · Excluido por exterior: $X · TC referencial · N avisos`

**B. Fila de KPIs (máximo 6)**
1. **Compra local del mes** (moneda local) + Δ% vs mes anterior
2. **Gasto YTD vs presupuesto** (solo EC) — semáforo
3. **Saldo CxP total** + % vencido
4. **Vencido > 30 días** (el número que duele)
5. **DPO** (días de pago) + Δ vs plazo pactado promedio
6. **A pagar próximos 7 días** — enlace directo al Comité de Pagos

Cada KPI: valor grande + comparativo + sparkline. Valor sin comparativo no informa.

**C. Aging de CxP**
- Buckets **Corriente · 1–30 · 31–60 · 61–90 · >90**, barras apiladas por total y por top 10 proveedores.
- Tabla por proveedor: saldo, % vencido, documento más antiguo, días vencidos, departamento.
- **Semáforo de riesgo por proveedor**: crítico si es proveedor único de un servicio esencial *y* está vencido > 60 días. Ese cruce es el que te deja sin transporte un lunes.

**D. Calendario de pagos y proyección de caja**
- Vista de **próximas 8 semanas**: barras por semana con lo que vence, apiladas por departamento.
- Detalle de **la semana en curso** ordenado por vencimiento — es el insumo directo del comité del viernes.
- **Escenarios**: pagar todo lo vencido / pagar solo lo corriente / diferir >60 días. Muestra el impacto en caja de cada uno.
- Enganche con `banco_guayaquil.py`: botón que exporta la selección al formato de carga masiva. **Advierte que `cuenta_empresa` sigue en `null` en `Pagos/banco/bg_config.json`** y que sin eso el archivo no carga en Banca Empresas.

**E. DPO y poder de negociación**
- DPO mensual (línea) vs plazo pactado promedio ponderado.
- **Matriz proveedor: días reales de pago (eje X) × volumen anual (eje Y)**, con cuadrantes:
  - alto volumen + pago rápido → **estás financiando gratis al proveedor**, aquí se negocia plazo
  - alto volumen + pago lento → riesgo de relación, revisar antes de que te corten
- Tabla: proveedor, plazo pactado, días reales, brecha, volumen, valor de la brecha en días-caja.
- **Si no logras extraer fechas de pago confiables** (`account.payment` / conciliación), dilo y degrada a "antigüedad de facturas ya liquidadas". No inventes un DPO.

**F. Concentración y dependencia de proveedores**
- Top 15 proveedores por gasto: monto, % del total, n° de documentos, departamento, Δ vs período anterior.
- **HHI** con umbral de alerta (>2.500 = crítico).
- **Proveedor único por categoría crítica** (transporte, aduana, bodega, mantenimiento): tarjeta de alerta con la exposición en dinero. Este es el riesgo operativo real de la operación local.

**G. Gasto por departamento y categoría**
- Distribución por departamento (Comercial / Operaciones / Gerencia) según `pagos_reglas_depto.json`, con tendencia mensual.
- Apertura por cuenta contable (nivel 3 del PUC), top movimientos y desviaciones.
- **% de gasto sin regla de departamento asignada** — visible, porque el default es "Gerencia" y eso ensucia el análisis silenciosamente.

**H. Real vs Presupuesto (solo Ecuador)**
- Waterfall: presupuesto original → resinceramiento → presupuesto vigente → real → desviación.
- Tabla por cuenta: ppto vigente, real, desviación $ y %, semáforo, y **cuentas sin pareja en el cruce** listadas aparte.
- Run-rate: proyección de cierre de año de gasto vs presupuesto vigente.
- En CO y CR este bloque se reemplaza por una tarjeta: "Sin presupuesto de gastos 2026 cargado — qué se necesita para tenerlo".

**I. Panel de integridad de datos** (pie, colapsable, obligatorio)
Fuente de cada bloque, fecha de cada extracción, cobertura de clasificación, monto excluido por exterior, cuentas sin mapear, proveedores sin departamento, y qué NO está incluido.

### 6.2 Extra solo del Consolidado
- Compras locales por país (% del total, USD referencial con badge).
- CxP y % vencido comparados entre países.
- DPO comparado — dónde el grupo paga más rápido de lo necesario.
- Alerta si un país concentra > 60% de la CxP vencida del grupo.

### 6.3 Fórmulas exactas
```
compra_local        = Σ líneas de factura de proveedor local, sin impuestos, in_invoice − in_refund
saldo_cxp           = Σ amount_residual de facturas de proveedor posted, no pagadas
dias_vencida        = hoy − invoice_date_due
DPO                 = (cxp_promedio / compras_del_período) × días_período
brecha_plazo        = días_reales_de_pago − plazo_pactado (payment_term)
HHI                 = Σ (participación_proveedor_%)²        // >2.500 = crítico
desviacion_ppto     = real − presupuesto_vigente            // + = sobregasto
run_rate_gasto      = gasto_ytd / meses_cerrados × 12
```
Ante cualquier duda de definición, **pregunta antes de asumir**.

---

## 7. DISEÑO

- **Lee primero el skill `dataviz`** antes de escribir la primera línea de código de gráficos. No es opcional.
- **Un solo archivo HTML autocontenido**: CSS y JS inline, imágenes en `data:` URI. **Los artefactos publicados bloquean hosts externos** → nada de CDN. Gráficos en **SVG generado a mano** o `<canvas>`.
- **Nada de `localStorage`/`sessionStorage`** (rompe el artefacto). Estado en variables JS.
- Estética coherente con el dashboard de ventas: fondo oscuro, tipografía condensada para números, jerarquía agresiva, densidad alta. Rojo/ámbar/verde **solo** para semáforos.
- **Interactividad:** tooltips en todos los gráficos, filtros de período (mes / trimestre / YTD / rolling 12), toggle moneda local ↔ USD, toggle "incluir sin clasificar", tabs por módulo, tablas ordenables y filtrables por departamento, exportar CSV del bloque visible.
- **Responsive** (se revisa en iPhone) y **`@media print`** limpio para llevarlo a directorio y al comité del viernes.
- **Cada gráfico lleva una línea de lectura en texto**, generada desde los datos, no escrita a mano.

---

## 8. PROTOCOLO DE TRABAJO

1. **Empieza midiendo, no construyendo.** Corre `pagos_cxp.py diag` en el Mac, mide la cobertura de `country_id` en proveedores, y **repórtame el estado real de los datos antes de escribir el dashboard**. Si la cobertura de país es < 95%, para y avísame.
2. **Construye por capas, entregando en cada una:** (1) pipeline + JSON validado → (2) dashboard de Ecuador (el único con presupuesto) → (3) CO y CR → (4) consolidado → (5) automatización.
3. **Cuadre obligatorio antes de publicar:** el saldo de CxP por país debe reconciliar contra `cxp_semana_actual.json` al centavo, y el gasto YTD de Ecuador contra `eeff_ecuador_2026-07_OFICIAL.json`. Muéstrame la conciliación línea por línea. Si no cuadra, explica la diferencia; no la maquilles.
4. **Cuestiona.** Si un KPI que pedí es engañoso con los datos disponibles, dilo antes de construirlo. Prefiero 4 números verdaderos que 12 decorativos.
5. **Si el dato no existe, no lo estimes.** Especialmente en DPO y en plazos pactados.
6. **Actualiza la memoria del proyecto** al terminar y deja la documentación técnica en el proyecto CFO VICOMER.

---

## 9. ENTREGABLES

1. `compras_dashboard.py` — extracción Odoo + Excels → `dashboard_compras.json` (con `diag` y `autotest`).
2. `compras_reglas.json` — clasificación editable: cuentas excluidas (financieros/impuestos/nómina/intercompañía), etiquetas de comercio exterior, categorías críticas de proveedor, plazos pactados.
3. `compras_dashboard_render.py` — JSON → 4 HTML autocontenidos.
4. Los 4 HTML, entregados en el chat **y publicados como artefactos persistentes**.
5. `com.vcomer.dashboard.compras.plist` + `instalar_dashboard_compras.command`.
6. `DASHBOARD_COMPRAS_SETUP.md` — arquitectura, fuentes por bloque, fórmulas, reglas de clasificación, cómo reparar cuando falle.
7. Reporte de conciliación (punto 8.3) + reporte de cobertura de clasificación.

---

## 10. CRITERIOS DE ACEPTACIÓN (revísalos tú mismo antes de entregar)

- [ ] `python3 compras_dashboard.py autotest` pasa sin conexión.
- [ ] La cobertura de clasificación de proveedores está medida y visible en los 4 dashboards.
- [ ] El monto excluido por "proveedor del exterior" se muestra explícitamente (HYXION y VIAL SHIPPING deben quedar fuera y contabilizados como excluidos).
- [ ] Bancos, impuestos, nómina e intercompañía están fuera del gasto operativo, y se puede ver qué se excluyó.
- [ ] Gasto devengado, saldo de CxP y pagos ejecutados aparecen como tres métricas distintas, nunca sumadas.
- [ ] Colombia filtra las cuentas "AJUSTE INICIAL" y el misposting de PROMOCIÓN Y PUBLICIDAD, y lo declara.
- [ ] CO y CR muestran "sin presupuesto de gastos", no cero.
- [ ] El cruce de códigos con y sin puntos reporta las cuentas sin pareja.
- [ ] Ningún USD consolidado aparece sin badge de TC referencial.
- [ ] Cero real ≠ dato faltante: se distinguen visualmente.
- [ ] Banner de frescura si la CxP tiene más de 3 días.
- [ ] Los 4 HTML abren sin internet y sin errores en consola; se leen en móvil y en impresión.

--- FIN DEL PROMPT ---
