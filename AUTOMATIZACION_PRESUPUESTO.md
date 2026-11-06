# Automatización del Presupuesto Comercial — Ecuador (Perseo)

Actualiza **automáticamente** los documentos comerciales de VICOMER con las ventas
reales de **Perseo** y envía un **correo semanal** con el estado del presupuesto.

> **Alcance: los 3 países.** Ecuador vía **Perseo**; Colombia (VINTRAL) y Costa Rica
> vía **Odoo** (`odoo_presupuesto.py`). Todo sin IVA. Colombia usa el histórico Ene-May
> del Regional + Odoo desde junio (VINTRAL empezó en el Odoo actual en abril).

---

## 1. Qué hace

| Cuándo | Tarea | Resultado |
|---|---|---|
| **Todos los días 10:00** | `perseo_presupuesto.py` (`com.vcomer.presupuesto`) | Refresca los libros Regional + Análisis con las facturas de Ecuador. **Desde ago-2026 Ecuador está en Odoo**: este paso sigue vivo sólo mientras se concilia la migración (ver `MIGRACION_ECUADOR_ODOO.md`). |
| **Todos los días 10:05** | `odoo_presupuesto.py` (`com.vcomer.odoo`) | Baja **los 3 países** desde Odoo (Ecuador incluido) y genera `ESTADO_PRESUPUESTO_ODOO.xlsx` en `OdooVentas/` (no toca los libros curados). |
| **Lunes 10:10** | `perseo_correo_semanal.py` (`com.vcomer.presupuesto.correo`) | Envía a `dir.comercial@v-comer.com` (cc `jmvidal@v-comer.com`) el estado de los 3 países, con los Excel adjuntos. |

### Documentos que se actualizan (solo la parte de Ecuador)
- **PRESUPUESTO COMERCIAL REGIONAL 2026 - GRUPO VICOMER.xlsx** → hoja **`Ventas Reales EC`**.
  Al reescribir esa hoja, las fórmulas nativas recalculan solas: fila **REAL FACTURADO**
  de `ECUADOR 2026`, **variación vs presupuesto**, `YTD vs Presupuesto`, `DASHBOARD` y `RESUMEN`.
- **ANALISIS COMERCIAL VICOMER 2026.xlsx** → hoja/tabla **`BD` (TablaVentas)**.
  El canal se autoasigna con el `VLOOKUP` a `DIM_Clients`, y la **tabla dinámica** se
  refresca al abrir el archivo.
- **El archivo de Colombia NO se toca.**

Además genera, en `PresupuestoAuto/`:
- `ESTADO_PRESUPUESTO_ECUADOR.xlsx` — libro limpio real vs presupuesto por canal (se adjunta al correo).
- `estado_presupuesto.json` — datos que consume el correo.

---

## 2. Cómo se leen los datos (reglas de negocio)

- **Monto** = campo `subtotal` de Perseo = **base imponible SIN IVA** (igual que el presupuesto).
  **Factura (01)** suma; **Nota de Crédito (04)** resta. La fila REAL de `ECUADOR 2026` y la
  venta neta de `YTD vs Presupuesto` se repuntaron a la columna **SubTotal**; el Análisis suma
  **SubTotal** (fórmulas y tabla dinámica). *Cuadre verificado: enero neto sin IVA = $196.899,91 exacto.*
- **Canal** por cliente: se toma de `BD`/`DIM_Clients` (RUC o razón social). Los clientes
  nuevos que no estén en `DIM_Clients` caen en **"SIN CANAL"** y el correo los lista como
  acción pendiente (agregarlos a `DIM_Clients`).
- **YTD** = hasta el **último mes cerrado** (convención CFO). El mes en curso se muestra
  aparte como *"mes en curso (parcial)"* para no distorsionar el cumplimiento.

---

## 3. Instalación (una sola vez)

1. Ejecuta el instalador (doble clic en Finder o en Terminal):
   ```bash
   bash "/Users/juanmarcelo/Claude/Projects/CFO VICOMER/automatizacion/instalar_automatizacion.command"
   ```
   Programa las dos tareas, instala `openpyxl` si falta y corre una primera actualización.

2. **Contraseña SMTP para el correo** (Google Workspace). Crea una *Contraseña de aplicación*
   en <https://myaccount.google.com/apppasswords> (requiere verificación en 2 pasos) y guárdala:
   ```bash
   printf 'TU_APP_PASSWORD' > ~/.perseo_smtp && chmod 600 ~/.perseo_smtp
   ```
   > La clave del API de Perseo ya vive en `~/.perseo_apikey` (no la escribe el asistente).

---

## 4. Probar

```bash
cd "/Users/juanmarcelo/Claude/Projects/CFO VICOMER"

# Solo actualizar documentos (sin correo):
/usr/bin/python3 perseo_presupuesto.py

# Ver el correo SIN enviarlo (genera PresupuestoAuto/preview_correo.html):
PERSEO_MAIL_DRYRUN=1 /usr/bin/python3 perseo_correo_semanal.py

# Enviar el correo ahora (prueba real):
/usr/bin/python3 perseo_correo_semanal.py
```

---

## 5. Seguridad operativa

- **Backup** con timestamp de cada libro antes de escribir → `PresupuestoAuto/_backups/`.
- **Validación** posterior: si el archivo resultante no abre o pierde gráficos/dinámica,
  se **descarta** y se conserva el original (reemplazo atómico). El error queda en el log.
- Gráficos, formato, fórmulas y tabla dinámica se **preservan** (edición quirúrgica de XML,
  no se re-serializa el libro completo).

---

## 6. Requisitos y notas

- La Mac debe estar **encendida y con red** a las 10:00 (las tareas no despiertan el equipo).
- Interfaz Python: `/usr/bin/python3` con `openpyxl`.
- Logs: `PresupuestoAuto/run.log`, `correo.log`, `error.log`, `correo_error.log`.

### Variables de entorno (opcionales)
`PERSEO_FILES_DIR`, `PERSEO_OUT_DIR`, `PERSEO_YEAR`, `SMTP_USER`, `SMTP_HOST`,
`SMTP_PORT`, `SMTP_APP_PASSWORD`, `PERSEO_MAIL_TO`, `PERSEO_MAIL_CC`, `PERSEO_MAIL_DRYRUN`.

---

## 7. Desinstalar

```bash
launchctl unload ~/Library/LaunchAgents/com.vcomer.presupuesto.plist
launchctl unload ~/Library/LaunchAgents/com.vcomer.presupuesto.correo.plist
rm ~/Library/LaunchAgents/com.vcomer.presupuesto*.plist
```

---

## 8. Próximo paso (Colombia y Costa Rica vía Odoo)

El pipeline separa **extracción → normalización → escritura → resumen/correo**. Para sumar
Colombia/CR bastará con una función `fetch` contra Odoo que devuelva las mismas transacciones
normalizadas (cliente, canal, fecha, monto, moneda) y mapear sus hojas destino. El correo y el
formato ya están listos para incorporarlas.
