# Fuente de datos: PerseoVentas (Ventas diarias automáticas)

> Documento de referencia del proyecto **CFO VICOMER**. Describe la fuente de datos de ventas que se genera automáticamente desde el sistema **Perseo**.

## 1. Ubicación

- **Carpeta:** `/Users/juanmarcelo/PerseoVentas/`
- Está en el *home* del Mac, **fuera** del folder del proyecto. Hoy el asistente CFO no la lee en vivo desde el sandbox (ver §5).

## 2. Qué hace la automatización

Un script Python (`perseo_ventas.py`) se ejecuta de forma programada (monitor/scheduler en el Mac, ~23:59 cada día) y:

1. Llama al API de Perseo: `POST https://perseo-data-c1.api/api/facturas_consulta`.
2. Autentica con un `api_key` leído de la variable de entorno `PERSEO_API_KEY` o del archivo `~/.perseo_apikey`.
3. Descarga las facturas del día (parámetro `dias`, default = 1).
4. Genera un Excel `Ventas_YYYY-MM-DD.xlsx` en la misma carpeta.

Tipos de documento manejados: `01` Factura, `04` Nota de Crédito, `05` Nota de Débito, `06` Guía de Remisión.

## 3. Estructura del Excel

Encabezado: **"REPORTE DE VENTAS DIARIAS - Perseo"** + fecha de generación y nº de documentos.

KPIs de cabecera: Ventas brutas · Devoluciones · Ventas netas · IVA total · Ticket promedio.

Tabla de detalle (una fila por documento):

| Fecha | Tipo | Secuencia | Cliente | Identificacion | Subtotal | Descuento | IVA | Total | Autorizado | Estado SRI |
|-------|------|-----------|---------|----------------|----------|-----------|-----|-------|------------|------------|

Cierra con fila **TOTAL**. El campo *Estado SRI* (autorización tributaria de Ecuador) indica que la facturación es electrónica y validada ante el SRI.

## 4. Archivos en la carpeta

| Archivo | Rol |
|---------|-----|
| `perseo_ventas.py` | Script de extracción (≈8 KB). |
| `Ventas_YYYY-MM-DD.xlsx` | Reporte diario generado. |
| `run.log` | Registro de corridas exitosas: `[OK] fecha documentos=N ventas=M -> ruta`. |
| `error.log` | Tracebacks cuando falla. |

## 5. Scheduler (el "monitor")

Es un **LaunchAgent** de macOS:

- Archivo: `~/Library/LaunchAgents/com.vcomer.perseoventas.plist`
- Label: `com.vcomer.perseoventas`
- Ejecuta: `/usr/bin/python3 /Users/juanmarcelo/PerseoVentas/perseo_ventas.py`
- `run.log` / `error.log` son el StandardOut/StandardError del agente (el script solo hace `print`).
- Editar requiere Terminal (`PlistBuddy` + `launchctl unload/load`); la carpeta `LaunchAgents` está protegida y no se monta en Cowork.

## 6. Diagnóstico y resolución (2026-06-30)

**Síntoma:** caída desde el 27-jun. Última corrida OK: **2026-06-26 23:59** → 4 documentos, ventas netas **$278.954,35**, IVA $36.385,35. `error.log`: `[Errno 8] nodename nor servname provided` + `JSONDecodeError`.

**Causa raíz:** NO era la URL (siempre fue `https://perseo-data-c1.app/...`, correcta) ni la llave. El agente disparaba a las **23:55 con la Mac dormida**, por lo que no había red → fallo de DNS al correr. Prueba manual `python3 ~/PerseoVentas/perseo_ventas.py 4` corrió OK.

**Cambios aplicados:**
1. **Auto-copia al proyecto:** `perseo_ventas.py` ahora guarda el Excel en `~/PerseoVentas/` **y** en `~/Claude/Projects/CFO VICOMER/PerseoVentas/` (config `EXTRA_OUT_DIRS`). Sin copiado manual.
2. **Horario:** LaunchAgent reprogramado de 23:55 → **15:00**, cuando la Mac suele estar encendida.
3. **Llave:** vive en `~/.perseo_apikey` (la gestiona el usuario).

**Pendiente / mejora futura:** añadir una alerta cuando una corrida falle (revisar `error.log` o notificar) para no acumular días sin datos sin enterarse.
