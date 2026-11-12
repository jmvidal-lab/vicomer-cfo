# Protocolo maestro de importaciones — Grupo VICOMER

Documento de control para numerar, archivar, contabilizar y cerrar cada importación de
VICOMER (EC), VINTRAL (CO) y la sociedad de Costa Rica.

- **Registro de control (aplicativo):** artefacto "Control de Importaciones VICOMER"
  → https://claude.ai/artifact/KbkUpvHxjBMzfcBMyBHiGr (fuente: `control_importaciones.html`).
  Las fichas viven en la base de datos del artefacto (`impos`, `tareas`, `meta/cruce`), no en este repo.
- **Archivo de soporte:** Drive → `VICOMER LOGISTICA / IMPORTACIONES / {PAÍS} / {AÑO}`.
- **Libro contable:** Odoo, cuentas `101.03.07.xx` (solo lectura para Claude).

Una importación se cierra solo cuando registro, Drive y Odoo coinciden.

## 1. Numeración
- Código `{PAÍS}-IMPO{NNN}`, un consecutivo por país (`EC-IMPO053`, `CO-IMPO011`, `CR-IMPO002`).
- Se asigna en el registro al emitir la OC o proforma, antes del primer pago. No se reutiliza ni se toma de otro país.
- Intercompañía: un código por país, citados entre sí (`EC-IMPO056 ↔ VINTRAL FE371`).
- El mismo código va en la carpeta de Drive, la cuenta 101.03.07, la OC (Referencia del proveedor) y la glosa de cada pago.

## 2. Carpetas en Drive
```
{PAÍS}/{AÑO}/{CÓDIGO} - {PROVEEDOR} - {REF}/
  01_COMPRA/          proforma, OC, contrato
  02_PAGOS/           transferencias y SWIFT
  03_EMBARQUE/        factura comercial, packing list, BL/guía, certificado de origen
  04_ADUANA/          DAI / DIM / DUA, liquidación, levante, observaciones
  05_GASTOS_LOCALES/  agente, flete, bodegaje, puerto, INEN, transporte interno
  06_COSTEO/          un solo COSTEO vigente (borradores en 06_COSTEO/_borradores)
```

## 3. Nombre de archivo
`{CÓDIGO}_{TIPO}_{AAAAMMDD}_{detalle}.{ext}` — tipos: `PI`, `OC`, `PAGO-n`, `CI`, `PL`, `BL`, `DAI`, `LIQ`, `GASTO`, `COSTEO`.
Un documento existe una sola vez; si sirve a dos importaciones se archiva en la que lo originó y la otra lo cita en su ficha.

## 4. Etapas (stage gates)

| Etapa | Requisitos | Responsable |
|---|---|---|
| Orden / proforma | Proforma, OC en Odoo | Logística |
| Anticipo pagado | + comprobante de pago | Logística + Tesorería |
| Embarcada | Factura comercial, packing list, BL | Logística |
| Nacionalizada | DAI/DIM/DUA, liquidación, gastos de agente | Logística + Agente |
| Recibida en Odoo | Recepción registrada el día del levante | Bodega |
| Costeada | COSTEO cuadrado contra la declaración (≤ 15 días del levante) | Contabilidad |
| Cerrada | Cuenta 101.03.07 en cero (tolerancia USD 50 / COP 200.000) | Contabilidad |

## 5. Reglas contables
- Una cuenta `101.03.07.xx` por importación; nada se imputa a la cuenta de otra.
- Sin recepción en Odoo la mercadería no existe para ventas ni costo de ventas (modo anglosajón desde 01-nov-2026).
- Tributos: una sola vez, desde la liquidación aduanera contra el pago bancario.
- La OC se crea en la compañía que importa; si la mercadería va a otro país, venta intercompañía.

## 6. COSTEO
- La DAI es la última palabra (FOB, flete, seguro); toda diferencia se explica en la ficha.
- Factor por categoría (arancel por partida + flete por CBM), nunca factor único.
- IVA de importación = crédito tributario, fuera del costo unitario.
- TRM / tipo de cambio de la declaración de esa importación.

## 7. Rutina semanal
1. Logística actualiza etapa y documentos en el registro.
2. Contabilidad verifica saldo 101.03.07 vs etapa.
3. Viernes: Claude cruza Odoo y Drive contra el registro y deja hallazgos en cada ficha.
4. Comité de pagos: ningún pago de importación sin código asignado.
