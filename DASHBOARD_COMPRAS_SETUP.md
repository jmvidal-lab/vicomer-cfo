# Sistema de Dashboards de Compras y Cuentas por Pagar — Grupo VICOMER

Documentación técnica y de operación. Última revisión: 2026-08-20.

---

## 1. Qué contesta y qué no

Tres preguntas de gerencia que antes no estaban en un solo lugar:

1. **¿En qué se me va la plata con proveedores locales, y contra qué presupuesto?**
2. **¿Cuánto debo, a quién, y cuán vencido está?**
3. **¿Qué tengo que pagar en las próximas semanas y me alcanza la caja?**

Regla rectora: *una cifra sin fuente verificable no entra*. Antes de estimar, se muestra
el hueco marcado como hueco.

### Los tres números que NUNCA se suman

Este es el error que hunde a la mayoría de tableros de compras. Aquí viven separados,
con nombre distinto y color distinto, y la autoprueba verifica que no se mezclen:

| Métrica | Qué es | De dónde sale |
|---|---|---|
| **Compra devengada** | Flujo del período: lo causado, esté pagado o no | Líneas de factura de proveedor con cuenta de gasto, por fecha de emisión |
| **Saldo de CxP** | Stock de deuda a hoy | `amount_residual_signed` de facturas posted, en moneda de la compañía |
| **Pagos ejecutados** | Salida real de caja | `account.payment` (partner_type = supplier) |

Se puede pagar más de lo que se compró en el período (deuda vieja) o comprar más de lo
que se pagó (deuda nueva). Compararlos directamente no dice nada.

---

## 2. Arquitectura

```
Odoo (XML-RPC) ──┐
Excels de ppto ──┼→ compras_dashboard.py → OdooVentas/dashboard_compras.json
EEFF oficial EC ─┘                                   ↓
                                    compras_dashboard_render.py
                                                     ↓
              Dashboard_Compras_VICOMER.html  (uno solo, con selector de país)
              + 4 HTML individuales por si se necesitan enlazados aparte
                                                     ↓
                       LaunchAgent com.vcomer.dashboard.compras — diario 07:45
```

**Separación estricta extracción → JSON → render.** El JSON es el contrato.

### Dónde corre cada cosa

| Pieza | Dónde | Por qué |
|---|---|---|
| Extracción | **macOS nativo** | Único entorno con red a `vicomer.odoo.com` y la API key |
| Render | macOS nativo | Va pegado a la extracción; no necesita red |

Restricciones verificadas: el sandbox de Cowork resuelve el dominio pero su proxy
devuelve **403**; `device_bash` corre en una VM Linux **sin red**; Terminal solo admite
permiso de clic. Por eso la ejecución manual se hace pegando un bloque de comandos.

---

## 3. Archivos

| Archivo | Qué hace |
|---|---|
| `compras_dashboard.py` | Extracción → JSON. Modos `autotest`, `diag`, `<año>` |
| `compras_reglas.json` | **Clasificación editable a mano.** Ver §5 |
| `compras_dashboard_render.py` | JSON → HTML. No toca Odoo |
| `compras_dashboard_pipeline.py` | Encadena ambos con degradación elegante |
| `compras_diag.py` | Paso 0: mide cobertura y estado de los datos. No construye nada |
| `compras_fix_paises.py` | Asigna `country_id` a proveedores. **Escribe en Odoo** (ver §7) |
| `automatizacion/com.vcomer.dashboard.compras.plist` | LaunchAgent 07:45 |
| `instalar_dashboard_compras.command` | Instalador de doble clic |

Todo es **biblioteca estándar de Python 3**: `xmlrpc`, `zipfile`, `xml.etree`. El lector
de `.xlsx` está escrito a mano (zip + XML) para no depender de openpyxl.

**Logs:** `OdooVentas/compras_run.log` y `compras_error.log`. Deliberadamente distintos
de los de ventas y de `com.vcomer.odoo`, para que un agente no pise los logs de otro.

---

## 4. Alcance: qué entra y qué no

### Proveedor local
`res.partner.country_id` **igual** al país de la compañía que registra la factura. Todo
lo demás es exterior y sale del bloque de compras — pero **no de la CxP**: la deuda hay
que pagarla venga de donde venga.

El monto excluido se muestra explícitamente, separado en dos naturalezas distintas:

- **Importación de mercadería y su cadena** — HYXION, navieras, agentes. No es gasto
  operativo: entra a inventario en tránsito (`101.03.07 IMPORTACION`).
- **Servicios del exterior** — Odoo Inc., AGODA, Celonis. Sí es gasto operativo, pero de
  fuera. Con la regla estricta habría quedado invisible.

Los **agentes locales de comercio exterior** (agencias de aduana, forwarders, navieras
representadas) entran como locales porque el proveedor lo es, y se **marcan** con una
etiqueta para aislarlos de un clic. No se excluyen por cuenta propia.

### Compras operativas
Solo cuentan las líneas cuyo `account_type` esté en `expense`, `expense_direct_cost` o
`cost_of_revenue`. Fuera: bancos y tarjetas, impuestos y retenciones, nómina y aportes,
intercompañía y préstamos a socios — todos visibles en su propia tarjeta con monto y
motivo.

### El puente
La diferencia entre el neto facturado por proveedores locales y el gasto operativo no se
pierde: son líneas que van a cuentas de balance (inventario, IVA, activos de importación)
más lo excluido por no operativo. El dashboard muestra ese puente y la conciliación lo
verifica en cero.

---

## 5. `compras_reglas.json` — editable sin tocar código

| Bloque | Para qué |
|---|---|
| `tipos_cuenta_gasto` | Qué `account_type` cuenta como gasto |
| `excluir_no_operativo` | Financieros, impuestos, nómina, intercompañía, socios, bancos |
| `cuentas_contaminadas` | Cuentas mal clasificadas conocidas, por país |
| `comercio_exterior` | Cómo distinguir importación de servicios del exterior |
| `agentes_locales_de_comercio_exterior` | A quién marcar con la etiqueta |
| `categorias_criticas` | Transporte, logística, aduana, servicio técnico, contabilidad, tecnología |
| `plazos_pactados_manuales` | Plazo en días para proveedores sin `payment_term` en Odoo |
| `umbrales` | HHI crítico, días vencido crítico, frescura de la CxP, semanas del calendario |

`plazos_pactados_manuales` está **vacío a propósito**: lo que no esté ahí no se supone.

---

## 6. Fórmulas

```
compra_local     = Σ líneas de factura de proveedor local con cuenta de gasto (in_invoice − in_refund)
saldo_cxp        = Σ −amount_residual_signed de facturas posted   [moneda de la compañía]
dias_vencida     = hoy − invoice_date_due
DPO_puntual      = saldo_cxp / compra_del_período × días_del_período
dias_pago_real   = Σ(monto × días desde vencimiento) / Σ monto    [conciliaciones 12 meses]
HHI              = Σ (participación_proveedor_%)²                 [>2.500 = crítico]
run_rate_H2      = real_H2 / (días transcurridos del semestre / días del semestre)
```

**Sobre el DPO:** Odoo no guarda fotos de CxP pasada, así que no existe una "CxP promedio"
y el DPO que se muestra es **puntual, no promedio**. Está etiquetado como tal.

**Sobre la moneda:** el saldo se agrega en moneda de la compañía. Costa Rica factura en
CRC y en USD a la vez; sumar `amount_residual` entre monedas distintas — que es lo que
hace `pagos_cxp.py` — produce un total que no significa nada.

---

## 7. El corrector de países (`compras_fix_paises.py`)

**Escribe en Odoo.** Salvaguardas:

- Solo propone el país de la compañía que facturó, y únicamente cuando el formato del
  RUC/NIT/cédula jurídica lo corrobora.
- Nunca infiere un país extranjero: un nombre con sufijo societario extranjero (`CORP`,
  `INC`, `LTD`, `PTE`, `S.R.O.`…) va a revisión manual aunque el número cuadre.
- Nunca sobrescribe un `country_id` ya cargado.
- Sin `--aplicar` imprime el plan y sale.
- Bitácora en `OdooVentas/compras_fix_paises.log`.

Corrida del 2026-08-20: 10 proveedores corregidos, cobertura de 90,0% → **99,1%**. Queda
uno para revisión manual: **GLOBAL TRADE BRANDS CORP** (5.083.400 COP, sin RUC).

---

## 8. Trampas de la instancia (confirmadas)

| Trampa | Cómo se sortea |
|---|---|
| **Filtrar líneas por `move_id.move_type` devuelve VACÍO sin lanzar error** — atraviesa `account.move`, roto por el `l10n_ec` incompleto | Se pasan los **ids de factura explícitos**. Esta trampa es peor que la documentada: la conocida revienta, ésta miente |
| `account.account.code` es company-dependent desde Odoo 17 | Plan de cuentas leído **una compañía por contexto** |
| Odoo no mantiene tipos de cambio | Overrides de `pagos_reglas_depto.json → tc_manual`; todo USD va marcado como referencial |
| El COGS no está tipificado en ninguna compañía | Rescate por nombre de cuenta, con aviso |
| Los LaunchAgents fallan si `/usr/bin/python3` no tiene Acceso Total al Disco | Ya resuelto |

### El cruce de códigos del presupuesto

**No era un problema de puntos.** Verificado contra los dos catálogos:

```
Excel 5.2.01.06.05  <->  Odoo 502.01.06.05     (gastos de ventas)
Excel 5.3.01.09.05  <->  Odoo 502.02.09.05     (administrativos)
Excel 5.4.01.01.02  <->  Odoo 502.03.01.02     (financieros)
Excel 5.5.01.01.01  <->  Odoo 502.04.01.01     (no deducibles)
```

Los tres primeros segmentos del Excel `5.G.01` colapsan en `502.0(G-1)` de Odoo. Quitar
los puntos y comparar dígitos (`52010605` contra `502010605`) **no cruza nada**: se
perdería el 100% del presupuesto en silencio.

Además, **el presupuesto está abierto a más niveles que la contabilidad** (4-5 contra 3).
El cruce sube el presupuesto hasta el nivel donde ambos existen y declara cuántas líneas
se agruparon. Cruzarlos hoja contra hoja dejaba el 95% del presupuesto huérfano.

---

## 9. Huecos declarados (a 2026-08-20)

- **Colombia y Costa Rica no tienen presupuesto de gastos 2026.** El bloque muestra la
  tarjeta con su motivo, nunca un cero.
- **El detalle por cuenta del real de Ecuador llega hasta junio.** La hoja `Estado de
  Resultados Mensual` está cortada a mitad de julio. Julio existe solo **agregado** en
  `eeff_ecuador_2026-07_OFICIAL.json`. No se prorratea.
- **La ejecución del H2 no es comparable todavía**: Odoo Ecuador arrancó el 1 de agosto.
  El run-rate se muestra marcado como no concluyente.
- **`5.3.01.05.02 Ga - Servicios Profesionales` declara 3.200 USD sin desglosar**: el
  subtotal supera la suma de sus hojas. Aparece como línea `(sin desglosar)`.
- **El plazo pactado está cargado en una minoría de facturas** (11% en Ecuador, 42% en
  Colombia, 23% en Costa Rica). La brecha se calcula sobre ese subconjunto.
- **El departamento por defecto domina la apertura**: 81% en Ecuador y 96% en Colombia
  caen en "Gerencia" porque el proveedor no tiene regla. Se arregla agregando palabras
  clave a `pagos_reglas_depto.json`.
- **La contaminación del P&L de VINTRAL no llega a compras.** El filtro de cuentas
  `AJUSTE INICIAL` y `PROMOCIÓN Y PUBLICIDAD` queda activo como guarda, pero no encontró
  ninguna línea en facturas de proveedor: esa contaminación vive en asientos de diario.
- **`cuenta_empresa` sigue en `null`** en `Pagos/banco/bg_config.json`. Sin ese dato el
  archivo de carga masiva del Banco Guayaquil se genera pero Banca Empresas lo rechaza.

---

## 10. Operación

```bash
cd ~/Claude/Projects/CFO\ VICOMER && \
{ echo "=== $(date '+%F %T') ==="; \
  python3 compras_dashboard.py autotest; \
  python3 compras_dashboard_pipeline.py; } 2>&1 | tee OdooVentas/compras_run.log
```

```bash
python3 compras_dashboard.py autotest    # 27 comprobaciones, sin red
python3 compras_dashboard.py diag        # conexión y conteos crudos
python3 compras_diag.py 2026             # medición completa de cobertura y datos
python3 compras_fix_paises.py            # plan de corrección de países (no escribe)
python3 compras_fix_paises.py --aplicar  # escribe en Odoo
launchctl start com.vcomer.dashboard.compras
```

**Idempotencia:** el JSON se escribe de forma atómica y el snapshot histórico es un
archivo por fecha.

---

## 11. Cómo reparar cuando falle

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| `no autentico` + `nodename nor servname` | Mac dormida o sin red | No es un bug: el pipeline conserva el JSON anterior. Correr a mano |
| Un bloque de cuentas sale vacío | Consulta que atraviesa `account.move` | Pasar ids explícitos, nunca `move_id.move_type` |
| El presupuesto no cuadra contra su TOTAL | Subtotales contados como hojas, o caché viejo | Subir `CACHE_VERSION` en `compras_dashboard.py` |
| Todo el presupuesto sale "sin pareja" | Cruce hoja contra hoja | Ya resuelto con `nivel_comun()`; verificar que los códigos traduzcan |
| CxP no cuadra contra `cxp_semana_actual.json` | Ese archivo suma monedas distintas y puede tener días | La conciliación compara en moneda de documento y marca la antigüedad como tolerable |
| Banner de frescura de la CxP | `com.vcomer.pagos.cxp` no disparó el viernes | Correr `python3 pagos_cxp.py` a mano |

---

## 12. Criterios de aceptación verificados

- [x] `compras_dashboard.py autotest` pasa sin conexión — 27 comprobaciones
- [x] Cobertura de clasificación medida y visible en todos los dashboards (99,1%)
- [x] El excluido por exterior se muestra explícito, con HYXION y VIAL SHIPPING dentro
- [x] Importación y servicios del exterior separados en tarjetas distintas
- [x] Bancos, impuestos, nómina e intercompañía fuera del gasto y visibles
- [x] Compra devengada, CxP y pagos como tres métricas distintas, nunca sumadas
- [x] Colombia y Costa Rica muestran "sin presupuesto", no cero
- [x] El cruce traduce los códigos y reporta huérfanas y gasto sin presupuesto
- [x] Ningún USD consolidado sin badge de TC referencial
- [x] Cero real ≠ dato faltante: se distinguen visualmente
- [x] Banner de frescura si la CxP tiene más de 3 días
- [x] Los HTML abren sin internet, sin errores de consola, y se leen en móvil e impresión
- [x] Un solo archivo con selector de país, más los individuales
