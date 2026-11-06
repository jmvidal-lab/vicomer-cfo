# Comité de Pagos Semanal — Arquitectura (Fase 3)

Artefacto Cowork: `comite-pagos-vicomer` · Actualizado 2026-08-03

> **Ecuador migró de Perseo a Odoo.** Los tres países salen ahora de la misma instancia.
> Ver `MIGRACION_ECUADOR_ODOO.md` para el detalle y lo que falta verificar en el Mac.

## Flujo completo

```
VIERNES 08:00  Mac (LaunchAgent com.vcomer.pagos.cxp)
               pagos_cxp.py: Odoo XML-RPC (EC + CR + CO)
               (Perseo sólo como respaldo si Ecuador viene vacío)
               -> Pagos/cxp/cxp_semana_actual.json

VIERNES 08:45  Claude (tarea programada "pagos-subir-cxp")
             sube el JSON a Drive, carpeta "Ordenes de Pago VICOMER"

CUANDO SEA   Tú, en el artefacto "comite-pagos-vicomer":
             apruebas/rechazas (con motivo), pagos parciales, depto,
             comprobaciones -> genera orden de pago y solicitudes -> Drive

L-V 12:30    Claude (tarea programada "pagos-bajar-ordenes")
             baja órdenes/solicitudes nuevas de Drive -> Pagos/salida/

AL INSTANTE  Mac (LaunchAgent com.vcomer.pagos.correo, WatchPaths)
             pagos_correo.py envía:
               orden de pago -> jmvidal@v-comer.com (+ adjunto banco si existe)
               comprobaciones -> responsable de cada depto (CC jmvidal)
             y archiva en Pagos/enviados/
```

## Instalación (una vez, en tu Mac)

```
doble clic en:        instalar_pagos.command
retrato de Odoo:      python3 odoo_descubrir.py          <-- hazlo primero
verificar mapeo:      python3 pagos_cxp.py diag
pruebas offline:      python3 pagos_cxp.py autotest
generar CxP ya:       python3 pagos_cxp.py
correo en seco:       PAGOS_MAIL_DRYRUN=1 python3 pagos_correo.py
```

### Si el CxP no se actualiza (pasó el 31-jul-2026: 21 días sin correr)

```
launchctl list | grep com.vcomer.pagos.cxp
launchctl kickstart -k gui/$(id -u)/com.vcomer.pagos.cxp
# si no aparece en la lista, el agente se descargó (reinicio / update de macOS):
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.vcomer.pagos.cxp.plist
```

El artefacto ahora **bloquea la orden de pago** si el CxP tiene más de 36 h o es de otra
semana ISO, y la tarea programada se niega a subir un archivo viejo. Un CxP obsoleto en
Drive es peor que ninguno: se aprobarían pagos contra saldos que ya cambiaron.

## Componentes

| Archivo | Función |
|---|---|
| `pagos_cxp.py` | v3 — Extractor CxP de los 3 países desde Odoo (in_invoice + in_refund con saldo). TC a USD desde Odoo. Respaldo Perseo para EC. Modos `diag` y `autotest`. |
| `odoo_descubrir.py` | Retrato de la instancia Odoo: compañías, plan de cuentas, RUC de clientes, localización. Base de toda la migración. |
| `pagos_correo.py` | Envío SMTP de orden y comprobaciones (credenciales de correo_config.json). |
| `pagos_reglas_depto.json` | Regla proveedor→departamento (keywords, default Gerencia), `tc_manual` y `perseo_cxp_endpoint` (respaldo). |
| `odoo_config.json` | `company_map` (VICOMER→Ecuador) e histórico pre-migración por país. |
| `automatizacion/com.vcomer.pagos.cxp.plist` | Viernes 08:00. |
| `automatizacion/com.vcomer.pagos.correo.plist` | WatchPaths en Pagos/salida. |
| Tareas Claude | `pagos-subir-cxp` (vie 08:45), `pagos-bajar-ordenes` (L-V 12:30). |

## Responsables de comprobación

- Comercial: Daniela Vidal — dir.comercial@v-comer.com
- Operaciones: Juan Jose Quezada — jjquezada@v-comer.com
- Gerencia: Juan Marcelo Vidal — jmvidal@v-comer.com

## Artefacto v3 — funciones

Vencidas + por vencer (ventana 7 días), aprobación/rechazo con motivo, monto a pagar
editable (pagos parciales), depto editable, comprobación por pago, consolidado grupo en USD
(TC de Odoo), rechazadas con motivo dentro de la orden, botón "Marcar orden como ejecutada"
(genera `ejecucion_*.json` en Drive para conciliación).

Nuevo en v3:

- **Bloqueo por dato obsoleto**: si el CxP tiene más de 36 h o es de otra semana ISO, sale un
  banner rojo con el comando de recuperación y el botón de generar orden queda deshabilitado.
- **Badge de origen por país** (Odoo / Perseo respaldo / sin datos) y advertencias de extracción
  visibles sobre cada tabla.
- **Notas de crédito de proveedor** separadas de lo pagable, con el total a favor por país y el
  recordatorio de aplicarlas antes de girar.
- **Panel de diagnóstico** con las compañías Odoo, su país mapeado, documentos y saldo. Cualquier
  compañía "(SIN MAPEAR)" aparece en rojo.

## Pendientes

1. **Verificación en el Mac** (bloquea todo lo demás): `python3 odoo_descubrir.py` para confirmar
   la compañía de Ecuador, el plan de cuentas y el RUC de los clientes. Ver `MIGRACION_ECUADOR_ODOO.md`.
2. **Archivo Banco Guayaquil (EC)**: usuario entrega plantilla de carga masiva → generar
   `banco_*_SEMANA.txt` en Pagos/salida (pagos_correo.py ya lo adjunta automáticamente).
   Requiere maestro de datos bancarios de proveedores (cuenta, banco, tipo, RUC/cédula).
   Con Ecuador en Odoo esto es más fácil: `res.partner.bank_ids` puede tener las cuentas.
3. **Saldo bancario / liquidez** en el artefacto. Con los 3 países en Odoo ya hay fuente posible:
   `account.journal` de tipo `bank` + saldo de las cuentas `asset_cash`.
4. Conciliación real: usar `ejecucion_*.json` + registro de pago en Odoo.
5. `pagos-bajar-ordenes` está **deshabilitada** desde el 13-jul. Si vuelves a usar el circuito
   completo de correos, hay que reactivarla.
