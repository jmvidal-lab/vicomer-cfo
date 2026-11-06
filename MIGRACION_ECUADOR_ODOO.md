# Migración Ecuador: Perseo → Odoo

Actualizado 2026-08-03 · Estado: **verificado contra Odoo · migración recién iniciada**

---

## RESULTADOS DE LA VERIFICACIÓN (2026-08-03 15:35)

Reporte completo en `Migracion/verificacion_odoo.txt`. Cinco hallazgos que cambian el plan:

> **Actualización 2026-08-03 18:50** — resueltos los puntos 4 y 5 y cargado el histórico:
> - `ecuador_hist_mensual` completo Ene–Jul = **USD 1.117.243,89** (102% del presupuesto YTD).
>   Verificado que agosto entra por Odoo y no se cuenta dos veces.
> - Los 6 LaunchAgents vuelven a salir con código 0.
> - Causa raíz de las fallas: `PermissionError` de macOS sobre `~/Desktop/VICOMER COMERCIAL`.
>   Falta confirmar que el agente `com.vcomer.presupuesto` escriba bien en la corrida
>   automática de las 10:00 (correr a mano no prueba nada: la Terminal sí tiene permiso).

### 1. La migración de Ecuador tiene 3 días y NO tiene transacciones

`VICOMER S.A.S.` (id=2) tiene asientos sólo del **2026-08-01 al 2026-08-03** (3.365 líneas,
casi con seguridad los saldos de apertura) y **cero facturas de cliente y cero de proveedor**.

Consecuencia directa: **todo Ene–Jul 2026 vive únicamente en Perseo.** Ecuador no puede ser
fuente de ventas, presupuesto ni estados financieros para ningún mes anterior a agosto.
`ecuador_hist_mensual` dejó de ser opcional: sin él, el YTD de Ecuador desde Odoo es cero.

Esto valida haber conservado el respaldo Perseo en vez de hacer un corte limpio.

### 2. CORREGIDO — el plan de cuentas SÍ conserva la codificación PUC (14 de 17)

**La primera lectura decía 0/17 y era un error mío**, no de Odoo: desde Odoo 17 el campo
`code` de `account.account` es *company-dependent*, y al leerlo con las cuatro compañías en
el contexto Odoo devuelve el código vacío para las que no son de la compañía principal.
2.173 de 2.823 cuentas salían sin código.

Corregido el bug (se lee una compañía a la vez), la segunda corrida da:

```
OK 11  71 · 1101 11 · 1102 20 · 1103 11 · 12  58 · 21  63 · 2104 2
OK 22  14 · 2203  2 · 3    78 · 41   11 · 42   1 · 51  78 · 52 193
!! 53   0 · 54     0 · 55    0
```

Es decir: **los EEFF sí se pueden mapear por prefijo**, que es la vía comparable con la serie
histórica de Perseo. El mismo bug estaba en `odoo_estados_financieros.py` y también se corrigió;
por eso el `diag` del terminal todavía mostraba `MODO = TIPO`. Al volver a correrlo debe decir
`MODO = PUC`.

**Salvedad importante:** no existen los prefijos 53, 54 ni 55, y el 52 concentra 193 cuentas.
El gasto operativo **total** será correcto, pero su **apertura** no: gastos de administración,
financieros y no deducibles saldrán en cero y todo aparecerá como gasto de ventas. El script
ahora lo advierte explícitamente. Para separarlos hay que subdividir el 52 o mapear por
`account_type`.

### 3. Apareció una cuarta compañía: VIX S.A.S.

`VIX S.A.S.` (id=11, Ecuador, USD, 1 factura desde el 30-jul). No estaba en el mapeo.
Por decisión de gerencia queda como **`ignore`**: no entra a ningún consolidado.
Si eso cambia, basta editar `company_map` en `odoo_config.json`.

*(`VICOMER LOGISTICA` no existe en Odoo; la clave queda como guarda porque el match es por
fragmento y `VICOMER` la capturaría si alguien la creara.)*

### 4. Odoo no mantiene tipos de cambio — y estaba inflando Colombia ~24%

`res.currency` devuelve **la misma tasa para COP, CRC y EUR** (0.00031805). La CxP de Colombia
son 481.610.209 COP: a esa tasa daba ~$153.000 USD, cuando al cambio real ronda los $123.000.

**Decisión adoptada:** cada país se reporta en **su moneda** como cifra autoritativa. El total
en USD pasa a ser **referencial**, calculado con los overrides de `pagos_reglas_depto.json`, y
así aparece marcado en el artefacto, en el JSON (`tc_confiable: false`) y en la orden de pago.

### 5. Por qué murió el pipeline de pagos

El CxP tiene **583 horas** (semana 2026-W28 contra la W32 en curso). El agente
`com.vcomer.pagos.cxp` está cargado y su último código de salida fue 0 — corrió bien el 10-jul
y no volvió a dispararse los viernes siguientes. La causa más probable es que el Mac estuviera
suspendido a las 08:00.

**Además hay tres agentes fallando con código 1** (no relacionados con esta migración):
`com.vcomer.perseoventas`, `com.vcomer.presupuesto` y `com.vcomer.presupuesto.correo`.
Conviene revisarlos aparte.

---

Ecuador dejó Perseo y pasó a la instancia Odoo del grupo (`vicomer.odoo.com`, compañía
cuyo nombre contiene "VICOMER"). Este documento es el mapa de qué cambió, qué falta y
en qué orden hacerlo.

---

## Advertencia central

Todo el código nuevo se escribió y se probó **sin acceso a Odoo** (el entorno de Claude no
alcanza la red de Odoo; la extracción siempre corre en tu Mac). Eso significa que:

- La lógica está probada con autotests offline y es correcta.
- El **mapeo real** —qué compañía es Ecuador, qué plan de cuentas usa, si los clientes traen
  RUC— es una hipótesis hasta que corras `odoo_descubrir.py` en el Mac.

**No publiques cifras de Ecuador desde Odoo hasta completar el paso 1 y la conciliación.**

---

## Paso 1 — Descubrimiento (hazlo primero, 2 minutos)

```bash
cd ~/Claude/Projects/CFO\ VICOMER
python3 odoo_descubrir.py
```

Genera `OdooVentas/descubrimiento_odoo.json` y `plan_cuentas_odoo.csv`, e imprime un resumen
que responde las tres preguntas que bloquean todo lo demás:

| Pregunta | Dónde mirar en el resumen | Si sale mal |
|---|---|---|
| ¿Cuál es la compañía de Ecuador? | Bloque `CANDIDATOS A 'ECUADOR'` | Ajusta `company_map` en `odoo_config.json` |
| ¿El plan de cuentas conserva la codificación PUC? | `COMPATIBILIDAD CON LOS PREFIJOS` | Si hay prefijos en 0, los EEFF usarán el modo `tipo` (ver paso 4) |
| ¿Los clientes traen RUC? | `PARTNERS: n/m con RUC` | Bajo 70% el canal comercial de Ecuador no se puede reconstruir |

También te dice desde qué fecha hay asientos en Odoo. **Ese es el corte de migración**: los
meses anteriores hay que traerlos del histórico de Perseo (ver paso 3).

---

## Paso 2 — Comité de pagos (ya operativo)

`pagos_cxp.py` v3 saca los tres países de Odoo en una sola consulta.

```bash
python3 pagos_cxp.py diag       # verifica el mapeo compañía → país de un vistazo
python3 pagos_cxp.py            # genera el CxP de la semana
python3 pagos_cxp.py autotest   # pruebas offline de la lógica
```

Qué cambió respecto a la versión anterior:

- Ecuador sale de Odoo. Perseo queda sólo como **respaldo**: si Odoo devuelve 0 facturas para
  Ecuador y hay endpoint configurado, se consulta Perseo y el JSON lo marca con
  `origen: "perseo"`. Si no hay respaldo, se reporta como incidencia en vez de taparse.
- Se incluyen las **notas de crédito de proveedor** (`in_refund`) con monto negativo, para que
  el saldo por proveedor sea el real y no se pague de más.
- Cada país reporta `origen`, `advertencias` y un `resumen` con total local, total USD y vencido.
- El JSON trae `companias_odoo`: toda compañía con documentos pero sin mapear queda a la vista.

El artefacto **Comité de Pagos** ahora **bloquea la generación de la orden de pago si el archivo
de CxP está obsoleto** (más de 36 h o de otra semana ISO). Ése fue exactamente el fallo del
31 de julio: el pipeline del Mac no corrió durante 21 días y nadie se enteró.

La tarea programada `pagos-subir-cxp` se reescribió con el mismo criterio: verifica frescura por
fecha **y** por semana ISO, y si falla reporta el diagnóstico del LaunchAgent en vez de subir
un archivo viejo.

---

## Paso 3 — Presupuesto y consolidado del grupo

`odoo_presupuesto.py` v2 ahora cubre los tres países.

```bash
python3 odoo_presupuesto.py autotest
python3 odoo_presupuesto.py 2026
python3 estado_grupo.py 2026
```

Cambios:

- `company_map` mapea `VICOMER → Ecuador` (antes `ignore`). El match usa el **fragmento más
  largo** que coincida, para que una clave corta no capture otra compañía por accidente.
- El presupuesto de Ecuador se sigue leyendo del libro Regional (hoja `ECUADOR 2026`): el
  presupuesto vive en Excel, no en el ERP, así que la migración no lo toca.
- El **canal comercial** de Ecuador se reconstruye cruzando `res.partner.vat` (el RUC en Odoo)
  contra el maestro `DIM_Clients`. Si más del 10% de las ventas cae en `SIN CANAL`, el reporte
  lo dice en voz alta: significa que los nombres de Odoo no coinciden con el maestro.
- `estado_grupo.py` toma Ecuador de Odoo y sólo cae a Perseo si Odoo no devuelve nada,
  dejándolo señalado. Puedes forzar con `ESTADO_GRUPO_EC=perseo` o `=odoo`.

### Histórico pre-migración — pendiente tuyo

Si Odoo Ecuador **no** tiene cargada la facturación anterior al corte, el YTD queda subestimado.
Llena en `odoo_config.json`:

```json
"ecuador_hist_mensual": { "1": 123456.78, "2": 98765.43 },
"ecuador_corte_migracion": "2026-08-01"
```

con las ventas netas mensuales sin IVA que ya conoces de Perseo. El script avisa mientras esto
esté vacío. Es el mismo mecanismo que ya se usó para Colombia (Ene-Mar de la instancia anterior).

---

## Paso 4 — Estados financieros

`odoo_estados_financieros.py` es **nuevo**; `perseo_estados_financieros.py` queda intacto como
respaldo e histórico. Los EEFF eran lo más acoplado a Perseo porque el mapeo a rubros se hace
por prefijo de código PUC.

El script resuelve el riesgo con **doble modo**:

- **`puc`** — mapeo por prefijo, idéntico al de Perseo. Se usa si el plan de cuentas de Odoo
  conservó la codificación.
- **`tipo`** — mapeo por `account_type` nativo de Odoo. Se usa si Odoo Ecuador adoptó el
  catálogo SRI de la localización y los prefijos ya no significan lo mismo.

Se autodetecta y el modo elegido queda escrito en el Excel y en el log. Forzable con
`EEFF_MODO=puc|tipo`.

```bash
python3 odoo_estados_financieros.py diag         # compañía, cobertura de prefijos, modo elegido
python3 odoo_estados_financieros.py 2026-07      # genera los EEFF desde Odoo
python3 odoo_estados_financieros.py conciliar 2026-06   # <-- el paso que valida todo
```

**La conciliación es obligatoria antes de confiar en el cambio de fuente.** Toma un mes que
exista en ambos sistemas y compara rubro por rubro. Si las diferencias no son explicables,
el mapeo está mal y hay que corregirlo antes de usar estos estados para decidir.

---

## Lo que NO se migró (deliberadamente)

**`perseo_ventas.py` — reporte diario de ventas de Ecuador (LaunchAgent 15:00).**
Sigue leyendo de Perseo. No lo migré porque depende de campos que sólo existen con la
localización ecuatoriana instalada: número de autorización del SRI, estado del comprobante y
descuento por línea. `odoo_descubrir.py` te dice en el bloque `LOCALIZACIÓN` si `l10n_ec` está
instalado y qué campos SRI existen. Con esa respuesta se decide si el reporte se migra tal cual
o si pierde columnas.

Mientras tanto conviene mantenerlo: es la única fuente que valida contra el SRI, y sirve como
contraste independiente de Odoo durante la transición.

---

## Orden recomendado — actualizado tras la verificación

1. ~~`odoo_descubrir.py`~~ **hecho** (2026-08-03).
2. ~~Ajustar `company_map`~~ **hecho**: VIX en `ignore`, VICOMER → Ecuador.
3. **Recuperar el pipeline de pagos** (lo más urgente: 583 h sin CxP).
   ```
   launchctl kickstart -k gui/$(id -u)/com.vcomer.pagos.cxp
   ```
4. **Llenar `ecuador_hist_mensual`** con Ene–Jul 2026 desde Perseo. Sin esto el consolidado
   del grupo reporta Ecuador en cero. Es el paso que más distorsiona hoy las cifras.
5. **Revisar los 3 agentes que salen con código 1** (perseoventas, presupuesto, presupuesto.correo).
6. **A fin de agosto**: primer corte de EEFF posible desde Odoo (`odoo_estados_financieros.py 2026-08`)
   y conciliación contra Perseo.
7. Recién entonces: apagar los pipelines de Perseo duplicados.

**No apagues Perseo.** Con Ecuador teniendo 3 días de historia en Odoo, Perseo sigue siendo la
única fuente de 7 meses del año. Durante la transición, tener dos fuentes que se contrastan vale
más que la limpieza de tener una sola.

---

## Archivos tocados

| Archivo | Cambio |
|---|---|
| `odoo_descubrir.py` | **nuevo** — retrato de la instancia Odoo |
| `odoo_estados_financieros.py` | **nuevo** — EEFF desde Odoo, doble modo de mapeo |
| `pagos_cxp.py` | v3 — 3 países en Odoo, NC de proveedor, respaldo Perseo, autotest |
| `odoo_presupuesto.py` | v2 — Ecuador incluido, canal por RUC, histórico por país, autotest |
| `odoo_ventas.py` | trae el RUC del cliente (`res.partner.vat`) |
| `estado_grupo.py` | Ecuador desde Odoo con respaldo Perseo; fuentes y avisos dinámicos |
| `odoo_margen.py` | consolidado renombrado a grupo (ya incluye Ecuador) |
| `perseo_correo_semanal.py` | pie de página de fuentes dinámico |
| `odoo_config.json` | `VICOMER → Ecuador`; claves de histórico y corte de Ecuador |
| `pagos_reglas_depto.json` | Perseo documentado como respaldo |
| Artefacto `comite-pagos-vicomer` | bloqueo por dato obsoleto, origen por país, NC, diagnóstico |
| Tarea `pagos-subir-cxp` | verifica frescura por fecha y semana; diagnostica el LaunchAgent |
