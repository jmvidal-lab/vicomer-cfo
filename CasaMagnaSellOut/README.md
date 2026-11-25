# Casa Magna — Sell Out vs Sell In (agente en la nube)

Tarea semanal (lunes) que cruza el **sell out** de Casa Magna (reportes NetSuite que llegan a Gmail) con
**Odoo VINTRAL** (facturas, consignación, stock, entregas, compras), publica el dashboard y manda el correo
de acciones al equipo. Reemplaza la tarea de Cowork (navegador) y la versión IMAP/SMTP del Mac (`casamagna_pipeline.py`).

## Qué mejora frente a la versión anterior
| Antes | Ahora |
|---|---|
| Sell in: copiado a mano en JSON, con semilla desfasada | Odoo en vivo cada corrida (XML-RPC, solo lectura, filtrado a VINTRAL) |
| "Falta pedir" = vendió > facturado | Modelo por SKU: inventario estimado en CM, rotación 12 semanas, cobertura, **reponer** a 8 semanas |
| Stock propio sin filtrar compañía (mezclaba Ecuador) | Solo VINTRAL, sin consignación ni "Existencias Tipo O", disponible = cantidad − reservado |
| Consignación invisible | **80 u en consignación en Casa Magna** detectadas; si vende más de lo facturado → **Facturar consignación** |
| Tránsito desde un artefacto externo | Órdenes de compra VINTRAL sin recibir, con bandera de **ETA vencida** |
| — | Entregas abiertas, pedidos/cotizaciones de CM sin cerrar, SKUs sin match en Odoo, semanas faltantes, picos anómalos |
| Parser por posición de columna | Por **nombre** de encabezado; rechaza adjunto duplicado (sha256) y fechas fuera de rango |
| Histórico en el paquete | Histórico en el artefacto (datos fuera de git), reconstruible desde Gmail |

## Archivos
| Ruta | Para qué |
|---|---|
| `config.json` | Query Gmail, destinatarios, `envio.modo` (borrador/enviar), URL del artefacto, parámetros del modelo, alias SKU |
| `scripts/ingest_netsuite.py` | Adjunto NetSuite → `work/datos/sellout_history.json` (idempotente) |
| `scripts/odoo_extract.py` | Odoo → `work/inputs/odoo.json` (solo `search_read`/`read`; bloquea cualquier otro método) |
| `scripts/analyze.py` | Cruce + modelo + puertas → `work/output/analysis.json`, `estado.json` |
| `scripts/build_dashboard.py` / `build_email.py` | `index.html` (artefacto), `Sell_Out_CasaMagna.html` (adjunto), `email.json` |
| `scripts/run.sh` | Odoo → análisis → dashboard → correo → zip |
| `scripts/selftest.py` | Autoprueba offline: debe decir `SELFTEST OK` |
| `scripts/bitacora.py` | Registro de corridas en `datos/corridas.json` del artefacto |

`work/` está en `.gitignore`. Los datos persistentes viven en el artefacto (`datos/*.json`).

## Runbook de la corrida (lo sigue la tarea programada)
Variables: `REPO` = raíz del repo; `export CM_WORK=$REPO/CasaMagnaSellOut/work`; URL = `config.json → artefacto.url`.

**0. Puertas.** `source cloud/setup.sh`; `python3 cloud/check_red.py` (Odoo principal debe decir CONEXION OK);
`python3 CasaMagnaSellOut/scripts/selftest.py` debe decir `SELFTEST OK`. Herramientas: Gmail (search_threads,
get_message, download_gmail_attachment, create_draft, send_message, get_draft), Artifact, PushNotification.

**1. Estado previo.** Artifact `read` de la URL (sin path) y luego `read` con `paths` =
`["datos/sellout_history.json","datos/sellin_vieja.json","datos/corridas.json"]`, `out_dir` = `$CM_WORK`.
Si el histórico no se puede leer: NO sigas con uno vacío (ver *Recuperación*).

**2. Sell out (Gmail).** `search_threads` con `config.json → gmail.query`, pageSize 50 (y página 2 si hay).
Nuevos = hilos cuyo id no está en `processed[].thread`. Procésalos del más viejo al más nuevo:
`get_message` → `download_gmail_attachment` (messageId, attachmentId, filename, mimeType) →
`python3 scripts/ingest_netsuite.py <ruta descargada> <date del mensaje> <threadId>`.
Código 2 = **freno** (archivo inválido o duplicado): anótalo y no envíes el correo.

**3. Pipeline.** `bash CasaMagnaSellOut/scripts/run.sh`. Lee `work/output/estado.json` (`enviable`, `frenos`, `alertas`).

**4. Publicar.** Artifact publish: `url`, `file_path` = `$CM_WORK/output/index.html`, `files` =
`{"datos/sellout_history.json", "datos/sellin_vieja.json", "datos/estado.json" ← output/estado.json, "datos/corridas.json"}`, label `Corte <fecha>`.

**5. Correo** (`work/output/email.json`; adjunto `Sell_Out_CasaMagna.zip` como referencia `sha256:<hash>:<ruta>`).
- `enviable` y `envio.modo = "enviar"` → `send_message` (to, cc, subject, htmlBody, body, adjunto). Verifica en `in:sent newer_than:1d`.
- Cualquier otro caso → `create_draft` con el mismo contenido y explica el motivo en la notificación.

**6. Cierre.** `python3 scripts/bitacora.py <ENVIADO|BORRADOR|FALLA> "<detalle>"`, publica solo `datos/corridas.json`,
y `PushNotification` con el resumen.

## Puertas (frenos → nunca se envía, queda borrador)
- Último reporte NetSuite procesado con más de 9 días (no llegó el de la semana).
- Extracción de Odoo que no es de hoy o que falló.
- Adjunto inválido, con encabezados irreconocibles, idéntico a otra semana, o con fechas fuera de rango.

## Recuperación
Si el artefacto se pierde: crea `work/datos/` vacío, copia `sellin_vieja.json` desde un respaldo (o define
`ODOO_APIKEY_VINTRAL1` en el environment para consultarlo en vivo) y reingiere **todos** los hilos de Gmail
(paso 2 con todos los hilos, del más viejo al más nuevo). El parser es idempotente.

## Supuestos a validar
- Inv. CM es estimado: el sell in arranca jun-2025 y el sell out ago-2025 (sobrestima algo el inventario en CM).
- "Facturar consignación" asume que Casa Magna vende primero las unidades en consignación cuando ya agotó lo facturado.
- Las cotizaciones abiertas cuentan como "pedido abierto" para no duplicar reposición.
