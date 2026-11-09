# CFO VICOMER — manual del ecosistema (léelo primero)

Repositorio del sistema financiero y de reporting del **Grupo VICOMER**:
VICOMER S.A.S. (Ecuador, USD), VINTRAL S.A.S. (Colombia, COP), la sociedad de Costa Rica
y VIX S.A.S. (holding). Lo usa Juan Marcelo Vidal Torres (Gerente General) con Claude
como CFO externo. Responde siempre en **español neutro**, ejecutivo y directo.

## 1. Dónde vive cada cosa

| Capa | Qué guarda | Dónde |
|---|---|---|
| **Este repo** | Código de los pipelines, reglas, plantillas, procedimientos | GitHub (privado) |
| **Proyecto claude.ai "CFO VICOMER"** | Estrategia, análisis, decisiones, term sheets, bitácoras de corridas (`claude/eeff/Corrida_*.md`) | Herramienta *Projects* |
| **Memoria** | Contexto del grupo, personas, áreas abiertas, preferencias | Memoria de Claude |
| **Google Drive** | Datos de entrada (Excel de presupuesto, gastos) y salidas publicadas | Conector Drive; carpeta del tablero EEFF: `VICOMER_EEFF_pipeline` |
| **Secretos** | API keys y contraseñas | **Solo** variables del environment de la nube. Nunca en el repo ni en el chat |
| **Datos bancarios** (cuentas de beneficiarios, maestro de proveedores) | Pagos | **Solo** en el Mac. Excluidos del repo a propósito |

Antes de un análisis estratégico, busca en el Proyecto (`project_search`): ahí están las cifras
oficiales y las decisiones ya tomadas. No recalcules lo que ya tiene cifra firmada.

## 2. Arranque de una sesión en la nube

```bash
source cloud/setup.sh        # deps + rutas + secretos → archivos que esperan los scripts
python3 cloud/check_red.py   # Odoo principal, Odoo vintral1 y Perseo: CONEXION OK
```

Si `check_red.py` falla con 403 / `host_not_allowed`: en el environment →
*Network access → Custom → Allowed domains* agrega (manteniendo el listado por defecto):
`vicomer.odoo.com`, `vintral1.odoo.com`, `perseo-data-c1.app`.

Variables: ver `.env.example`. Los scripts leen primero el entorno y luego, por herencia del Mac,
`~/.odoo_apikey`, `~/.perseo_apikey`, `~/.gmail_jmvidal_apppass`; `setup.sh` crea esos archivos
desde el entorno, así que **ningún script necesita cambios para correr en la nube**.

## 3. Fuentes de datos — reglas que ya costaron errores

- **Odoo principal** `vicomer.odoo.com` (db `intitecnologia-v-comer-main-27740127`): multicompañía.
  Mapeo de compañías en `odoo_config.json` → `company_map` (VICOMER=Ecuador, VINTRAL=Colombia,
  3-102-940094=Costa Rica; VIX, VICOMER LOGISTICA y personas naturales = ignore).
- **Ecuador**: Odoo es fuente de verdad **desde 2026-08-01** (`ecuador_corte_migracion`).
  Antes de esa fecha → **Perseo** (API `perseo-data-c1.app`, solo consultas históricas).
  Ene–jul 2026 de Ecuador congelado en `odoo_config.json` → `ecuador_hist_mensual`.
- **Colombia histórico** jun-2025 a mar-2026 → instancia `vintral1.odoo.com` (solo Casa Magna sell-in).
- **No leas el asiento de apertura de Odoo como estado de resultados** (error ya cometido:
  ver doc del Proyecto `eeff-ecuador-cifra-oficial`). Resultado oficial Ecuador Ene–Jul 2026: +154.542.
- **Odoo es SOLO LECTURA.** Prohibido `create`, `write`, `unlink`, `action_post`. Única excepción
  histórica: `compras_fix_paises.py` (asigna `country_id`), y solo con aprobación explícita.
- Ventas siempre **sin IVA**. Ecuador en USD; Colombia en COP con ~USD de presentación (TRM del día,
  Banco de la República, nunca reutilizada).
- Ecuador: la utilidad del ERP es **antes** de participación (15%) e IR (25%); preséntalas estimadas y marcadas.
- Landed cost: factor **por categoría** (arancel por partida + flete por volumen; `CBM_POR_MODELO`), nunca un factor único.
- Una cifra sin fuente verificable no entra. Los descuadres se muestran, no se corrigen.
- `odoo_proxy.py`: impórtalo antes de crear `ServerProxy`; enruta XML-RPC por el proxy de la nube.

## 4. Pipelines

| Pipeline | Entrada → salida | Script principal | Horario Mac (launchd) | Estado nube |
|---|---|---|---|---|
| **Estados financieros (tablero)** | Odoo → artefacto "Dashboards Generales Vicomer" | `EstadosFinancieros/` (lee su `CLAUDE.md`, `ACTUALIZAR.md`, `HANDOFF.md`) | — | ✅ **Ya en la nube**: tarea programada viernes 7:47 |
| **Informe CFO semanal** | Tablero + Odoo → correo a jmvidal | (prompt de la tarea) | — | ✅ **Ya en la nube**: viernes 11:23 |
| Dashboard ventas | Odoo + presupuesto → 4 HTML + Drive | `ventas_dashboard_pipeline.py` → `ventas_dashboard.py` + `_render.py` | diario 07:30 | ⏳ Migrable (necesita Excel de presupuesto desde Drive) |
| Dashboard compras / CxP | Odoo + presupuesto gastos → HTML | `compras_dashboard_pipeline.py` | diario 07:45 | ⏳ Migrable (necesita `VICOMER_PERSONAL` desde Drive) |
| Dashboard finanzas / productos | Odoo → JSON/HTML | `finanzas_dashboard.py`, `productos_dashboard.py` | (manual) | ⏳ Migrable |
| Estado presupuesto grupo | Odoo + libros → reporte | `estado_grupo.py` | diario 10:00 | ⏳ Migrable (Excel desde Drive) |
| Presupuesto vs real | Odoo → libro compañero | `odoo_presupuesto.py` | diario 10:05 | ⏳ Migrable |
| Correo semanal presupuesto | reporte → correo | `perseo_correo_semanal.py` | lunes 10:10 | ⚠️ Usa SMTP: en la nube, enviar con el conector Gmail |
| Casa Magna sell-out / sell-in | Gmail IMAP (NetSuite) + Odoo ×2 → dashboard + correo | `casamagna_pipeline.py` | lunes 13:30 | ⚠️ IMAP/SMTP no salen por el proxy: reemplazar por conector Gmail |
| Cartera Casa Magna | Odoo → dashboard | `OdooVentas/cartera_dashboard.py` (v3 de referencia) | (manual) | ⏳ Migrable |
| Comité de pagos — CxP | Odoo → `Pagos/cxp/cxp_<semana>.json` | `pagos_cxp.py` | viernes 08:00 | ⏳ Migrable (último, por riesgo) |
| Comité de pagos — correos | JSON aprobados → correos | `pagos_correo.py` | por evento | ⚠️ SMTP → conector Gmail |
| Carga masiva Banco Guayaquil | orden aprobada → archivo MULTICASH | `banco_guayaquil.py` (+ `BANCO_GUAYAQUIL_SETUP.md`) | manual | 🔒 **Se queda en el Mac**: usa cuentas bancarias de terceros |
| Stock / ABC-XYZ | Odoo → `stock_odoo_<fecha>.json` | `odoo_stock.py` | manual | ⏳ Migrable |
| Perseo histórico | API Perseo → JSON crudo | `perseo_historico.py`, `perseo_estados_financieros.py`, `perseo_ventas.py`, `perseo_presupuesto.py` | (legado) | ✅ Solo consultas históricas (pre-ago-2026) |
| Nave E02 (Tarqui) | planos / RFQ racks | `Nave E02/gen_*.py` | manual | ✅ Corre en cualquier lado |

Los `.plist` de `automatizacion/` documentan los horarios del Mac. Mientras una pipeline no esté
validada en la nube, **la del Mac sigue siendo la oficial**.

### Protocolo para migrar una pipeline a la nube
1. Correrla aquí con `*_DRYRUN=1` (sin correo) y comparar el JSON de salida contra el del Mac del mismo día.
2. Si cuadra dos corridas seguidas → crear la tarea programada en la nube (prompt autocontenido, con puertas
   de credenciales y red, y bitácora en el Proyecto).
3. Solo entonces desactivar el `.plist` del Mac. Anotar la fecha en la tabla de arriba.

## 5. Restricciones de la nube

- La red sale por un proxy HTTP(S) con lista de dominios permitidos: **IMAP (993) y SMTP (465) no funcionan**.
  El correo se envía con el conector Gmail (`send_message` / `create_draft`).
- Cada tarea programada arranca una sesión limpia: clona el repo, `source cloud/setup.sh`, corre.
- Los Excel de entrada no están en el repo: bájalos de Drive a `data/` (ignorado por git).

## 6. Reglas de trabajo en este repo

- Nunca imprimas el valor de un secreto; verifica por nombre (`env | cut -d= -f1`).
- Nunca subas datos: `.gitignore` excluye Excel, JSON de salida, logs, datos bancarios. Antes de cada commit:
  `git diff --cached --stat` y `bash cloud/scan_secretos.sh`.
- El repo espeja la estructura de carpetas del Mac (`~/Claude/Projects/CFO VICOMER`) para que copiar cambios
  en ambos sentidos sea trivial. No reorganices carpetas sin actualizar ambos lados.
- Cambios al tablero EEFF: solo datos y textos en la tarea semanal; diseño en sesión aparte (ver `EstadosFinancieros/CLAUDE.md`).

## 7. Planificación 2027

Carpeta `Planificacion2027/`: plan estratégico (`01`), diagnóstico integral con evidencia (`02`), guía metodológica (`03`),
resumen del presupuesto comercial (`04`), análisis de gastos de Ecuador por driver (`05`), marco de la reunión de Colombia (`06`), rentabilidad estructurada de gestión (`07`), estructura y equipo (`08`), generador del libro Excel (`presupuesto_2027.py`) y scripts de extracción/análisis
(`analisis/`, con su README). Corte de datos: 2026-11-06. Reglas nuevas que salieron de ese trabajo:
- La API de asientos de Perseo devuelve asientos duplicados (hasta ×22): deduplicar por `libros_diariosid` y excluir «Asiento de Cierre».
- El presupuesto se mide sobre factura, sin intercompañía; Colombia jun–dic 2025 no existe en la nube (falta `ODOO_APIKEY_VINTRAL1`).
- `standard_price` es dependiente de la compañía: léelo con `allowed_company_ids=[<una sola compañía>]` o devuelve el costo de otra (error cometido el 06-nov). El landed real por SKU está en el maestro de importaciones armonizado (Drive, carpeta VICOMER LOGISTICA).
