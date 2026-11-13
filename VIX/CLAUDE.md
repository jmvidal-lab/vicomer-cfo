# VIX S.A.S. — contabilidad asistida (léelo antes de tocar algo en VIX/)

VIX S.A.S. (RUC 0195183759001, Ecuador, USD) es la holding del grupo. Odoo compañía **id 11**.
Este módulo lleva su contabilidad con Claude como preparador y un contador humano como revisor y firmante.

## Roles

| Quién | Hace | No hace |
|---|---|---|
| Claude | Diagnóstico, propuestas de asiento, borradores en Odoo (cuando se habilite), cierre mensual, borradores de declaraciones | Publicar asientos, pagar, presentar al SRI, firmar EEFF |
| Contador | Revisa borradores, publica, presenta declaraciones, firma | — |
| JMV | Aprueba cambios de reglas y la habilitación de escritura; aprueba pagos | — |

## Candados (en `vix_odoo.py`, no se saltan)

1. **Compañía**: toda llamada va con `allowed_company_ids=[11]`; los modelos contables se filtran por `company_id=11`.
2. **Escritura apagada** mientras `vix_reglas.json → escritura.habilitada = false`. Para escribir hacen falta las tres:
   ese flag en `true` (aprobado en PR) y `VIX_ESCRIBIR=1` en la corrida. Se usa el **mismo usuario de Odoo** de JMV
   (decisión 2026-11-13): los asientos quedan a su nombre, por eso cada corrida con escritura deja bitácora en `VIX/bitacora/`.
3. **Solo borradores**: `action_post`, `unlink`, `reconcile`, cambios de `state` → prohibidos por código.
4. Fuera de `escribir()` (con sus candados), la key es **solo lectura**, como en todo el repo.

## Scripts

| Script | Qué hace | Escribe |
|---|---|---|
| `vix_diagnostico.py` | Estado de libros, cuentas mal usadas, cuadre intercompañía vs. VICOMER/VINTRAL, meses sin factura | No |
| `vix_banco.py inspeccionar <archivo>` | Muestra la estructura de un extracto para mapear columnas | No |
| `vix_banco.py proponer` | Extracto → movimientos normalizados → control de saldos → propuesta de conciliación | No |

Salidas en `VIX/salida/` (ignorada por git). Bitácora de cada corrida con escritura en `VIX/bitacora/`.

## Banco (Banco Guayaquil, cuenta …3043)

- **Fuente principal (en evaluación)**: API de integraciones BG, servicio *Movimientos* (Consulta v1).
  OAuth2 *client credentials* vía Entra ID **+ mTLS** (certificado de cliente; producción lo exige).
  Por el mTLS, **el conector corre en el Mac**, deja los movimientos normalizados en Drive y la nube los consume.
  Credenciales (`BG_CLIENT_ID`, `BG_CLIENT_SECRET`, `BG_SCOPE`, `BG_CERT`, `BG_CERT_KEY`, `BG_CUENTA`) **solo** en el entorno del Mac.
- **Respaldo**: export de Banca Empresas → Cash Management (Excel/CSV) en Drive `VIX_Contabilidad/banco/`.
- La API es de **consulta**. Nada de este módulo inicia pagos.

## Reglas contables

Todas en `vix_reglas.json`. Las que más importan:
- VICOMER y VINTRAL son **partes relacionadas** → CxC `11020601` (local) / `11020602` (exterior).
- Fee mensual: VICOMER 10.000 + IVA 15% (`410201`), VINTRAL 2.500 IVA 0% exportación (`410102`). Nunca `410101` (venta de bienes).
- Una cifra sin documento fuente no entra. Los descuadres se muestran, no se corrigen.

## Pendientes de arranque

1. ~~Usuario Odoo dedicado~~ → se usa el mismo usuario (decisión 2026-11-13).
2. ~~Definición OpenAPI 3 del servicio Movimientos~~ → cargada en `vix_banco.py` (2026-11-13).
3. Alta del servicio con BG: solicitada a Carolina Maldonado (oficial BG) el 2026-11-13 para VIX (consulta) y VICOMER (consulta + órdenes de pago).
4. Extractos jul–nov 2026 de la cuenta …3043 (respaldo mientras la API no esté).
5. Contrato intercompañía que respalda el fee (sustancia / precios de transferencia).
