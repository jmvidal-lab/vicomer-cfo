# Sistema de Dashboards de Ventas — Grupo VICOMER

Documentación técnica y de operación. Última revisión: 2026-08-19.

---

## 1. Qué es y qué NO es

Es un instrumento de decisión gerencial que se actualiza solo y **declara sus propios
huecos**. La regla rectora es una: *una cifra sin fuente verificable no entra al
dashboard*. Antes que estimar, muestra el hueco marcado como hueco.

No es un reporte de facturación bonito ni un reemplazo del ERP. No proyecta, no
interpola, no rellena meses vacíos. Un **cero real** y un **dato faltante** se ven
distintos, siempre.

---

## 2. Arquitectura

```
Odoo (XML-RPC)  ──►  ventas_dashboard.py  ──►  OdooVentas/dashboard_ventas.json
                            │                              │
                            │                              ├─► OdooVentas/historico/dashboard_ventas_AAAAMMDD.json
                            │                              │   (un snapshot por día: de aquí sale la tendencia de cartera y DSO)
                            ▼                              ▼
                   ventas_dashboard_pipeline.py   ventas_dashboard_render.py
                            │                              │
                            │                              ▼
                            │                4 HTML autocontenidos
                            │                (Ecuador · Colombia · Costa Rica · Consolidado)
                            ▼
              LaunchAgent com.vcomer.dashboard.ventas — diario 07:30
                            │
                            ▼
              Tarea Cowork 08:00 — lectura CFO + bitácora en el proyecto
```

**Separación estricta extracción → JSON → render.** El JSON es el contrato: si mañana
cambia el diseño, no se vuelve a tocar Odoo. Si cambia Odoo, no se toca el diseño.

### Dónde corre cada cosa, y por qué

| Pieza | Dónde corre | Por qué ahí |
|---|---|---|
| Extracción de Odoo | **macOS nativo** (LaunchAgent o Terminal) | Es el único entorno con red hacia `vicomer.odoo.com` **y** la API key |
| Render de los HTML | macOS nativo | Va pegado a la extracción; no necesita red |
| Lectura CFO diaria | Sesión Cowork en la nube | Solo lee el JSON por la carpeta conectada |

**Restricciones verificadas el 2026-08-19 — no intentar sortearlas:**

- El sandbox de Cowork **resuelve** `vicomer.odoo.com` pero su proxy de salida devuelve
  `403 Forbidden` en el túnel. No hay extracción desde la nube.
- `device_bash` **no corre en el Mac**: corre en una VM Linux aislada que solo tiene
  montada la carpeta del proyecto, y **no tiene red**. Sirve para leer y escribir
  archivos, no para hablar con Odoo.
- Terminal solo admite permiso de **clic** en computer-use: no se puede teclear en él
  desde una sesión. Por eso la ejecución manual se hace pegando un bloque de comandos.

---

## 3. Archivos

| Archivo | Qué hace |
|---|---|
| `ventas_dashboard.py` | Extracción Odoo → JSON. Modos `test`, `diag`, `<año>` |
| `ventas_dashboard_render.py` | JSON → 4 HTML. No toca Odoo |
| `ventas_dashboard_pipeline.py` | Encadena los dos, con degradación elegante. Lo que corre el agente |
| `automatizacion/com.vcomer.dashboard.ventas.plist` | LaunchAgent diario 07:30 |
| `instalar_dashboard_ventas.command` | Instala el agente y corre una vez |
| `actualizar_dashboard_ventas.command` | Corrida manual completa con log |

Todo es **biblioteca estándar de Python 3**: `xmlrpc`, `zipfile`, `xml.etree`. Sin
pandas, sin requests, sin openpyxl. El lector de `.xlsx` está escrito a mano
(`xlsx_read`, ~60 líneas de zip + XML) precisamente para no arrastrar dependencias que
rompan el LaunchAgent.

**Logs:** `OdooVentas/dashboard_run.log` y `dashboard_error.log`. Deliberadamente
**no** son `run.log`/`error.log`: esos ya los usa `com.vcomer.odoo` y compartirlos
haría que un agente pise los logs del otro.

---

## 4. Reglas de negocio cableadas

1. **Venta = `amount_untaxed_signed`** (neta sin IVA, con signo), solo `out_invoice` +
   `out_refund` en estado `posted`. Las notas de crédito restan.
2. **Ecuador tiene doble fuente.** Ene–Jul 2026 vive únicamente en Perseo y se lee de
   `odoo_config.json → ecuador_hist_mensual` (YTD = 1.117.243,89). Odoo es fuente de
   verdad desde `ecuador_corte_migracion` = 2026-08-01.
   **Nunca agregar la clave `"8"` a ese diccionario**: agosto se contaría dos veces.
   El script tiene una **guarda anti-doble-conteo**: si un mes tiene a la vez cifra
   histórica y facturas en Odoo, conserva Odoo, descarta el histórico y emite un aviso
   crítico. La autoprueba verifica exactamente ese escenario.
3. **Colombia también.** Ene–Mar 2026 en `colombia_hist_mensual` (instancia vieja
   `vintral1`, COP); Abril en adelante en la instancia actual.
4. **VIX S.A.S. se excluye** del consolidado. `VICOMER LOGISTICA` no existe en Odoo;
   la clave queda en `company_map` como guarda porque el match es por fragmento.
5. **Moneda.** Cada país reporta en su moneda como cifra autoritativa. El consolidado
   en USD es **REFERENCIAL** y lleva badge visible con la tasa, porque Odoo no mantiene
   tipos de cambio (COP, CRC y EUR devuelven todas 0,00031805). Las tasas salen de
   `pagos_reglas_depto.json → tc_manual`.

---

## 5. Fórmulas

```
venta_neta      = Σ amount_untaxed_signed   (posted, out_invoice + out_refund)
cumpl_ytd       = venta_neta_ytd / ppto_ytd
margen_bruto_%  = (venta_neta − COGS) / venta_neta        [del mayor, no de la factura]
DSO_puntual     = cartera_al_corte / venta_neta_periodo × días_periodo
días_pago_real  = Σ(monto × días_desde_vencimiento) / Σ monto   [conciliaciones 12 meses]
aging_bucket    = hoy − invoice_date_due
HHI             = Σ (participación_cliente_%)²            [>2.500 = crítico]
run_rate_anual  = venta_ytd / meses_cerrados × 12
```

**Sobre el DSO:** Odoo no guarda fotos de cartera pasada, así que no existe una
"cartera promedio" histórica y el DSO que se muestra es **puntual, no promedio**. Está
etiquetado como tal. La serie temporal se construye sola desde la primera corrida, un
punto por día, leyendo `OdooVentas/historico/`.

---

## 6. Fuente de cada bloque

| Bloque | Fuente | Notas |
|---|---|---|
| Venta mensual y YTD | `account.move` + histórico de `odoo_config.json` | Mixta en EC y CO |
| Presupuesto YTD / anual | `PresupuestoAuto/estado_grupo.json` | Lo genera `com.vcomer.presupuesto` |
| Curva mensual de presupuesto | Libro Regional, hoja del país | **Fila localizada por validación**, ver abajo |
| Margen bruto | `account.move.line` sobre cuentas de resultado | Por compañía, no por factura |
| Mix de producto | `account.move.line` agrupado por `product_id` | |
| Cartera y aging | `account.move.line`, cuentas por cobrar abiertas | **Nunca `account.move`** |
| Clientes y HHI | `account.move` del año | Solo lo que está en Odoo |
| Tendencia cartera/DSO | `OdooVentas/historico/*.json` | Se acumula día a día |

### La fila del presupuesto no se busca por número de fila

Se barren **todas las filas** y **todas las ventanas de 12 columnas consecutivas** de la
hoja del país, y se acepta la que cumpla las tres condiciones:

1. la suma de las 12 celdas cuadra (±1%) con el presupuesto anual que ya reporta
   `estado_grupo.json`,
2. al menos **6 de los 12 meses** tienen cifra,
3. **ningún mes se lleva más del 45%** del año.

Con solo la primera condición no basta: en las hojas de Colombia y Costa Rica existen
filas donde *una sola celda* trae el total del año, y eso producía una "curva mensual"
con todo el presupuesto cargado en abril. Si ninguna fila cumple, **no se dibuja curva**
y se declara el hueco; el YTD y el anual siguen siendo válidos.

Filas encontradas y validadas el 2026-08-19: Ecuador hoja `ECUADOR 2026` fila 39,
Colombia `COLOMBIA 2026` fila 23, Costa Rica `COSTA RICA 2026` fila 14 — las tres con
los meses en las columnas D..O y error relativo 0.

---

## 7. Trampas de la instancia (confirmadas, no las redescubras)

| Trampa | Cómo se sortea aquí |
|---|---|
| `account.move` revienta en lecturas anchas: `l10n_ec` está a medio instalar y falta la columna `account_move.l10n_ec_sri_import_withhold` | Toda consulta ancha va contra `account.move.line`; el tipo de documento se infiere por prefijo del nombre. `sr_drop()` reintenta quitando de a un campo |
| `account.account.code` es *company-dependent* desde Odoo 17 | El plan de cuentas se lee **una compañía por vez**; si no, 2.173 de 2.823 cuentas salen sin código |
| El COGS no está tipificado como `expense_direct_cost` en ninguna compañía | Rescate por **nombre** de cuenta (`COSTO DE LA MERCANCIA VENDIDA`, etc.), y el dashboard avisa que hay que corregir el tipo en Odoo |
| Odoo no mantiene tipos de cambio | Overrides manuales; todo USD consolidado va marcado como referencial |
| Los LaunchAgents fallan con `PermissionError` si `/usr/bin/python3` no tiene Acceso Total al Disco | Ya resuelto en el sistema. No lo rompas |

---

## 8. Huecos declarados (a 2026-08-19)

Estos **no se rellenan**: aparecen en el panel de integridad de los cuatro dashboards.

- **Costa Rica no registra COGS.** Su margen es *no calculable* — no 100%, no 0%.
  Para tenerlo hace falta cargar el costo en Odoo y tipificar la cuenta.
- **El COGS de Colombia y Costa Rica no está mensualizado.** Se registra en asientos
  puntuales, lo que produce meses al 100% y julio en −362%. El **acumulado sí es
  utilizable**; la curva mensual se oculta con su explicación en vez de dibujar la sierra.
- **El mayor solo tiene resultado en pocos meses** por la migración: 2 de 8 en Ecuador,
  6 de 8 en Colombia. El margen YTD compara la venta y el costo *contabilizados*, no el
  año calendario completo.
- **El desglose por cliente cubre el 10% del YTD de Ecuador** (solo agosto está en Odoo)
  y el 89% de Colombia. El HHI y el ranking describen esa porción, no el año.
- **91% de la venta del mayor de Ecuador no tiene producto** en el asiento (es el asiento
  de apertura de la migración): el mix por producto de Ecuador es parcial. En Colombia, 24%.
- **No hay comparativo 2025**: Odoo tiene cero facturas de ese año. La columna Δ vs año
  anterior queda vacía a propósito.
- **12% de la venta de Colombia es intercompañía** (a VICOMER S.A.S.). Se detecta, se
  marca y se publica el HHI de terceros por separado.
- **No hay historia de cartera anterior** a la primera corrida de este pipeline.
- El P&L de VINTRAL está contaminado (cuentas `AJUSTE INICIAL…` mal clasificadas, un
  `PROMOCIÓN Y PUBLICIDAD` de 6.6B COP por misposting): la **utilidad neta** de Colombia
  no es confiable. Este dashboard no la usa.

---

## 9. Operación

**Corrida manual completa** (pegar en Terminal):

```bash
cd ~/Claude/Projects/CFO\ VICOMER && \
{ echo "=== $(date '+%F %T') ==="; \
  python3 ventas_dashboard.py test; \
  python3 ventas_dashboard_pipeline.py; } 2>&1 | tee OdooVentas/dashboard_run.log
```

**Otros comandos:**

```bash
python3 ventas_dashboard.py test      # autoprueba offline, sin red — 24 comprobaciones
python3 ventas_dashboard.py diag      # conexión, compañías, conteos crudos. No escribe el JSON
python3 ventas_dashboard.py 2026      # solo extracción
python3 ventas_dashboard_render.py    # solo render
launchctl start com.vcomer.dashboard.ventas   # forzar el agente
launchctl list | grep vcomer                   # ver agentes cargados
```

**Idempotencia:** correrlo dos veces el mismo día no duplica nada. El JSON se escribe de
forma atómica (`.tmp` + `os.replace`) y el snapshot histórico es un archivo por fecha.

---

## 10. Cómo reparar cuando falle

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| `no autentico con ninguna base de datos` + `nodename nor servname` | El Mac estaba dormido o sin red a las 07:30 | No es un bug. El pipeline conserva el JSON del día anterior y el dashboard muestra su fecha real. Corre a mano |
| `no autentico` **con** red | API key revocada o cambiada | Regenerar en Odoo → Ajustes → cuenta → clave de API, y pegarla en `odoo_apikey.txt` |
| Un país desaparece del consolidado | `company_map` no reconoce el nombre de la compañía | `python3 ventas_dashboard.py diag` lista las compañías y su mapeo. Corregir `odoo_config.json`. El aviso crítico *"Compañías Odoo SIN mapear"* aparece solo |
| Aviso **DOBLE CONTEO** | Alguien agregó al histórico un mes que ya está en Odoo | Quitar esa clave de `<pais>_hist_mensual`. Mientras tanto el script ya descartó el histórico de ese mes: la cifra es correcta |
| El presupuesto YTD sale vacío | `estado_grupo.json` se sobrescribió vacío porque `com.vcomer.presupuesto` corrió sin red | Correr `python3 estado_grupo.py` con conexión. **Riesgo conocido de ese agente**, no de este |
| Margen 100% | El COGS no se registra o está mal tipificado | El dashboard ya lo declara como no confiable. Arreglar en Odoo, no en el script |
| El HTML abre en blanco | JSON corrupto a medias | Borrar `dashboard_ventas.json` y correr el pipeline; o renderizar desde `historico/` con `--json` |
| Se rompió el render pero el JSON está bien | — | `python3 ventas_dashboard_render.py --json OdooVentas/historico/dashboard_ventas_AAAAMMDD.json` |

---

## 11. Criterios de aceptación verificados

- [x] `ventas_dashboard.py test` pasa sin conexión — 24 comprobaciones
- [x] Ecuador no duplica agosto ni pierde Ene–Jul. YTD Ene–Jul = 1.117.243,89
- [x] Colombia suma instancia vieja + nueva = 933.278.870,49 COP
- [x] VIX excluida en los 4 dashboards
- [x] Ningún USD consolidado aparece sin badge de TC referencial
- [x] Costa Rica muestra *margen no calculable*, no 100% ni 0%
- [x] Cero real ≠ dato faltante: se distinguen visualmente
- [x] Los 4 HTML abren sin internet y sin errores en consola (verificado en navegador real)
- [x] El panel de integridad lista todos los huecos
- [x] Se lee en móvil (verificado a 430px) y tiene CSS de impresión
- [x] Conciliación: 8 de 8 líneas cuadran al centavo
- [x] Paleta validada con el validador de accesibilidad (categórica y rampa ordinal, modo oscuro)
