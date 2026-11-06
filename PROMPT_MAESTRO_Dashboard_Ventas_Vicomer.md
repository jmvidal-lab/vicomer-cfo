# PROMPT MAESTRO — Dashboard Ejecutivo de Ventas (Grupo VICOMER)

> **Cómo usarlo:** abre una tarea nueva en el proyecto *CFO VICOMER* y pega TODO el contenido desde la línea `--- INICIO DEL PROMPT ---` hasta el final. No lo resumas: la precisión de las secciones 2 y 3 es lo que evita que el dashboard salga con cifras falsas.

---

--- INICIO DEL PROMPT ---

## 0. ROL Y MISIÓN

Actúas como **CFO + ingeniero de datos financieros** del Grupo VICOMER. Tu misión en esta tarea es construir un **sistema de dashboards ejecutivos de ventas**: no un reporte bonito, sino un instrumento de decisión gerencial que se actualiza solo, declara sus propios huecos de datos y obliga a mirar lo que duele (concentración, margen real, cartera).

Regla rectora: **una cifra sin fuente verificable no entra al dashboard.** Antes de estimar, prefieres mostrar el hueco marcado como hueco.

---

## 1. ENTORNO REAL (no lo asumas, ya está verificado)

**Máquina y rutas**
- Todo el ecosistema CFO corre en el Mac del usuario: `~/Claude/Projects/CFO VICOMER/` (montado en esta sesión como carpeta conectada).
- El sandbox de Cowork **NO alcanza `vicomer.odoo.com`** (DNS bloqueado) y no tiene la API key. Toda extracción de Odoo se ejecuta en el Mac vía `device_bash`; los JSON caen en la carpeta montada y desde ahí sí se leen.
- Salidas de datos: `OdooVentas/`. Salidas de presupuesto: `PresupuestoAuto/`. Salidas contables: `Finanzas/`.

**Conexión Odoo** (`odoo_config.json`, no la re-descubras)
- URL `https://vicomer.odoo.com` · DB `intitecnologia-v-comer-main-27740127` · login `jmvidal@v-comer.com` · API key en `odoo_apikey.txt` · Odoo **18.0+e**, XML-RPC, solo stdlib de Python.
- 4 compañías: **VICOMER S.A.S.** (id=2, Ecuador, USD) · **VINTRAL S.A.S.** (id=1, Colombia, COP) · **3-102-940094 SRL** (id=3, Costa Rica, USD) · **VIX S.A.S.** (id=11, Ecuador) → **VIX se EXCLUYE del consolidado por decisión de gerencia.**

**Activos que YA existen — reutilízalos, no los reescribas**

| Archivo | Qué hace | Salida |
|---|---|---|
| `odoo_ventas.py` | Facturas de venta por compañía/mes (`out_invoice`/`out_refund`, posted) | `OdooVentas/odoo_facturas_2026.json` |
| `estado_grupo.py` | Consolidado 3 países real vs presupuesto | `PresupuestoAuto/estado_grupo.json` |
| `odoo_presupuesto.py` | Ecuador por canal comercial (RUC × DIM_Clients) | `PresupuestoAuto/estado_presupuesto.json` |
| `odoo_margen.py` | Margen bruto (ventas − COGS) | `OdooVentas/odoo_margen_2026.json` |
| `cartera_v3.py` | Cartera real por cliente desde `account.move.line` | CSV/JSON en `OdooVentas/` |
| `odoo_descubrir.py` | Retrato de la instancia (compañías, plan de cuentas, RUCs) | `OdooVentas/descubrimiento_odoo.json` |
| `casamagna_*.py` + `casamagna_dashboard_template.html` | **Patrón de referencia**: pipeline → template HTML → correo | `CasaMagna/` |

**Trampas técnicas confirmadas (te ahorran horas)**
1. **`account.move` revienta** en lecturas amplias: el módulo `l10n_ec` está a medio instalar y falta la columna `account_move.l10n_ec_sri_import_withhold`. Para cartera y cualquier consulta ancha, **usa `account.move.line`** e infiere el tipo de documento por prefijo del nombre (así lo resolvió `cartera_v3.py`).
2. **`account.account.code` es company-dependent desde Odoo 17**: hay que leerlo con **UNA sola compañía en el contexto** o 2.173 de 2.823 cuentas salen sin código.
3. **El COGS de VINTRAL está en `account_type = expense`**, no en `expense_direct_cost` (cuenta "COSTO DE LA MERCANCÍA VENDIDA"). Si filtras por `expense_direct_cost` el margen te da 100% — falso.
4. **Odoo NO mantiene tipos de cambio**: COP, CRC y EUR devuelven todas `0.00031805`. Usa los overrides de `pagos_reglas_depto.json → tc_manual` (`COP 0.00027027`, `CRC 0.00221`).
5. Los LaunchAgents fallan con `PermissionError` si `/usr/bin/python3` no tiene **Acceso Total al Disco**. Ya está resuelto; no lo rompas.

---

## 2. REGLAS DE NEGOCIO NO NEGOCIABLES

Estas reglas ya fueron peleadas y verificadas. Violarlas produce cifras falsas que se ven perfectamente creíbles.

1. **Venta = `amount_untaxed_signed`** (neta, sin IVA, con signo). Las notas de crédito **restan**. Solo documentos `posted`.
2. **Ecuador tiene doble fuente por la migración:** Odoo EC solo tiene transacciones desde el **2026-08-01** (`ecuador_corte_migracion`). Ene–Jul 2026 vive **únicamente en Perseo** y se lee de `odoo_config.json → ecuador_hist_mensual` (YTD Ene–Jul = **USD 1.117.243,89**). **NUNCA agregues la clave "8" a ese diccionario** o agosto se cuenta dos veces.
3. **Colombia también tiene doble fuente:** Ene–Mar 2026 en `colombia_hist_mensual` (instancia vieja `vintral1`, COP); Abr en adelante en la instancia actual. YTD = suma de ambas.
4. **Moneda:** cada país reporta en **su moneda como cifra autoritativa**; el consolidado en USD es **REFERENCIAL**. Todo KPI consolidado en USD lleva un badge visible "TC referencial" con la tasa y la fecha usada.
5. **VIX S.A.S. se excluye.** VICOMER LOGISTICA no existe en Odoo.
6. **Huecos conocidos que el dashboard debe DECLARAR, no rellenar:**
   - Costa Rica **no registra COGS** en Odoo → su margen es **no calculable**, no 100%.
   - El P&L de VINTRAL está contaminado (cuentas "AJUSTE INICIAL…" mal clasificadas y un "PROMOCIÓN Y PUBLICIDAD" de 6.6B COP por misposting). El **margen bruto sí es confiable (55,4% Abr–Jul)**; la utilidad neta de Colombia **no lo es**.
   - El plan de cuentas no tiene prefijos 53/54/55 y el 52 concentra 193 cuentas → el gasto operativo total es correcto, su apertura no.
7. **Contexto de riesgo que el dashboard existe para vigilar:** concentración extrema de clientes (EC → COMOHOGAR ~77%; CO → Casa Magna 63% + USA Electrodomésticos 34%; CR → CEMACO ~100%). El grupo depende de ~5 clientes.

---

## 3. ARQUITECTURA OBLIGATORIA

**Decisión ya tomada: script en el Mac + datos embebidos.** El artefacto HTML **no** llama a Odoo (CORS + la API key quedaría expuesta en el HTML). El flujo es:

```
Odoo (XML-RPC)  →  ventas_dashboard.py  →  OdooVentas/dashboard_ventas.json
                                                        ↓
                                         ventas_dashboard_render.py
                                                        ↓
                    4 HTML autocontenidos (Ecuador · Colombia · Costa Rica · Consolidado)
                                                        ↓
                              LaunchAgent diario  +  publicación como artefacto
```

**Requisitos del pipeline**
- Python 3 **solo stdlib** (como el resto del ecosistema). Sin pandas, sin requests.
- Separación estricta **extracción → JSON → render**. El JSON es el contrato: si mañana cambia el diseño, no se vuelve a tocar Odoo.
- El JSON lleva siempre: `generado` (ISO), `anio`, `mes_cierre`, `fuentes` (por país: Odoo / Perseo-histórico / mixta), `tc_usado` con fecha, `avisos[]` (lista de huecos y advertencias), y los datos.
- **Modos CLI obligatorios:** `diag` (verifica conexión y muestra conteos crudos), `test` (autoprueba offline con servidor simulado, como `odoo_ventas.py test`), y ejecución normal por año.
- **Idempotencia:** correrlo dos veces el mismo día no duplica nada.
- **Degradación elegante:** si una fuente falla, el dashboard se genera igual con ese bloque marcado en rojo como "sin datos", nunca en cero silencioso. Un cero real y un dato faltante deben verse distinto.
- **LaunchAgent** `com.vcomer.dashboard.ventas`, diario **07:30**, con `run.log` y `error.log` en `OdooVentas/`. Instalador `.command` de doble clic, siguiendo el patrón de `instalar_casamagna.command`.
- No toques ni rompas los agentes existentes (`com.vcomer.presupuesto`, `com.vcomer.pagos.cxp`, `com.vcomer.perseoventas`, `com.vcomer.casamagna`).

---

## 4. ESPECIFICACIÓN DEL DASHBOARD

Genera **4 artefactos**: `Dashboard_Ventas_Ecuador`, `_Colombia`, `_CostaRica` y `_Consolidado_Grupo`. Mismo motor, misma estética, mismo JSON; cambia el filtro y el nivel de agregación.

### 4.1 Estructura de cada dashboard (orden fijo, de arriba hacia abajo)

**A. Barra de estado** (siempre visible, arriba)
`Datos al <fecha> · Fuente: <Odoo / mixta> · TC referencial COP 3.700 · N avisos` — con el contador de avisos clickeable que despliega la lista.

**B. Fila de KPIs (máximo 6, sin scroll)**
1. Venta YTD (moneda local) + Δ% vs presupuesto YTD
2. MTD del mes en curso + % de avance del mes
3. Cumplimiento presupuesto YTD (%) — semáforo
4. Margen bruto % YTD (o badge "no calculable" en CR)
5. Cartera total y % vencido > 30 días
6. DSO (días de cobro)

Cada KPI muestra **valor grande + comparativo pequeño + microtendencia (sparkline)**. Sin excepción: valor sin comparativo no informa nada.

**C. Real vs Presupuesto mensual** — barras mensuales (real) + línea (presupuesto) + área sombreada de acumulado. Meses futuros en gris punteado, nunca en cero sólido.

**D. Margen bruto y mix de producto**
- Margen % por mes (línea) sobre venta neta (barras) — para ver si crecer está costando margen.
- **Mix**: contribución por línea/categoría de producto — barras horizontales ordenadas por **margen absoluto aportado**, no por facturación. Marca las líneas de alta venta y bajo margen (el mix que destruye valor).
- Tabla top 15 productos: venta, COGS, margen $, margen %, % del total, Δ vs mes anterior.
- Si el COGS no existe para ese país (CR), el bloque completo se reemplaza por una tarjeta de advertencia explicando **por qué** no hay dato y **qué se necesita** para tenerlo.

**E. Cartera / Aging y DSO**
- Buckets: **Corriente · 1–30 · 31–60 · 61–90 · >90** — barras apiladas por cliente (top 10) y total.
- DSO mensual (línea) con la meta de política de crédito.
- Tabla de cartera por cliente: saldo, % vencido, días promedio, factura más antigua vencida.
- **Cruce que importa:** clientes que crecen en venta y se deterioran en cobro. Márcalo explícitamente — es la señal temprana de un problema de caja.

**F. Clientes y concentración** *(módulo mínimo, aunque no fue solicitado — lo incluyo porque es el riesgo estructural nº1 del grupo y un dashboard de ventas que lo oculta desinforma)*
- Top 10 clientes: venta YTD, % del total, Δ vs año anterior.
- **Índice de concentración HHI** con umbral de alerta y la frase de riesgo en lenguaje llano.

**G. Panel de integridad de datos** (pie, colapsable)
Lista de avisos, fuente de cada bloque, fecha de cada extracción, y qué NO está incluido. Este panel es obligatorio y no se puede omitir "por estética".

### 4.2 Extra solo del Consolidado
- Composición del grupo por país (% de la venta total, en USD referencial, con badge).
- Ranking de cumplimiento presupuestal por país.
- Alerta si un país concentra más del 60% de la venta o de la desviación del grupo.
- Tabla comparativa por país: venta local, venta USD, % ppto, margen %, DSO, concentración.

### 4.3 Fórmulas exactas (úsalas literalmente)
```
venta_neta        = Σ amount_untaxed_signed (posted, out_invoice + out_refund)
cumpl_ytd         = venta_neta_ytd / ppto_ytd
margen_bruto_%    = (venta_neta − COGS) / venta_neta
DSO               = (cartera_promedio / venta_neta_periodo) × días_periodo
aging_bucket      = hoy − fecha_vencimiento (invoice_date_due)
HHI               = Σ (participación_cliente_%)²      // >2.500 = concentración crítica
run_rate_anual    = venta_ytd / meses_cerrados × 12
```
Ante cualquier duda de definición, **pregunta antes de asumir**.

---

## 5. DISEÑO (el dashboard tiene que verse como Bloomberg, no como Excel)

- **Lee primero el skill `dataviz`** antes de escribir una sola línea de código de gráficos. No es opcional.
- **Un solo archivo HTML autocontenido**: todo el CSS y el JS inline, imágenes en `data:` URI. **Los artefactos publicados bloquean hosts externos** → nada de CDN, nada de Chart.js remoto. Gráficos en **SVG generado a mano** o `<canvas>`; se ve mejor y carga instantáneo.
- **Nada de `localStorage`/`sessionStorage`** (rompe el artefacto). Estado en variables JS.
- Estética: fondo oscuro profundo, tipografía condensada para números, jerarquía tipográfica agresiva (el KPI manda, la etiqueta susurra), densidad alta pero respirada. Paleta sobria con acentos: verde/rojo **solo** para semáforos, nunca decorativos.
- **Interactividad obligatoria:** hover con tooltip en todos los gráficos, filtros por período (YTD / mes / trimestre / rolling 12), toggle moneda local ↔ USD, tabs de navegación entre módulos, tablas ordenables, y botón "exportar CSV" del bloque visible.
- **Responsive real**: debe leerse en iPad y en iPhone. El usuario revisa esto fuera de la oficina.
- **Imprimible**: `@media print` limpio, para llevarlo a directorio.
- **Cada gráfico lleva una línea de lectura en texto** ("qué me está diciendo esto") generada desde los datos, no escrita a mano.

---

## 6. PROTOCOLO DE TRABAJO

1. **Empieza verificando, no construyendo.** Corre `odoo_ventas.py diag` y `odoo_descubrir.py resumen` en el Mac, revisa los JSON que ya existen y **reporta el estado real de los datos antes de escribir el dashboard**. Si algo no cuadra con lo que dice este prompt, **el dato manda sobre el prompt**: dilo y para.
2. **Construye por capas y entrega en cada capa:** (1) pipeline + JSON validado → (2) dashboard consolidado → (3) los 3 dashboards por país → (4) automatización. No me muestres el diseño antes de que las cifras estén cuadradas.
3. **Cuadre obligatorio antes de publicar:** el YTD de cada país debe reconciliar contra `estado_grupo.json` y contra `ecuador_hist_mensual` / `colombia_hist_mensual`. Muéstrame la conciliación línea por línea. Si no cuadra al centavo, explica la diferencia; no la maquilles.
4. **Cuestiona.** Si detectas que un KPI que pedí es engañoso, o que un dato no soporta el análisis que quiero, dilo antes de construirlo. Prefiero un dashboard con 4 KPIs verdaderos que 12 decorativos.
5. **Actualiza la memoria del proyecto** al terminar (patrón, rutas, trampas nuevas) y guarda la documentación técnica en el proyecto CFO VICOMER.

---

## 7. ENTREGABLES

1. `ventas_dashboard.py` — extracción Odoo → `dashboard_ventas.json` (con `diag` y `test`).
2. `ventas_dashboard_render.py` — JSON → 4 HTML autocontenidos.
3. Los 4 HTML, entregados en el chat **y publicados como artefactos persistentes**.
4. `com.vcomer.dashboard.ventas.plist` + `instalar_dashboard_ventas.command`.
5. `DASHBOARD_VENTAS_SETUP.md` — arquitectura, fuentes por bloque, fórmulas, cómo reparar cuando falle.
6. Reporte de conciliación de cifras (el del punto 6.3).

---

## 8. CRITERIOS DE ACEPTACIÓN (revísalos tú mismo antes de entregar)

- [ ] `python3 ventas_dashboard.py test` pasa sin conexión.
- [ ] Ecuador no duplica agosto ni pierde Ene–Jul. YTD EC Ene–Jul = 1.117.243,89.
- [ ] Colombia suma instancia vieja + nueva.
- [ ] VIX excluido en los 4 dashboards.
- [ ] Ningún USD consolidado aparece sin badge de TC referencial.
- [ ] Costa Rica muestra "margen no calculable", no 100% ni 0%.
- [ ] Cero silencioso ≠ dato faltante: se distinguen visualmente.
- [ ] Los 4 HTML abren sin internet y sin errores en consola.
- [ ] El panel de integridad lista todos los huecos de la sección 2.6.
- [ ] Se lee bien en móvil y en impresión.

--- FIN DEL PROMPT ---
