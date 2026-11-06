# Archivo de pagos Banco Guayaquil — Ecuador

Actualizado 2026-08-03 · Estado: **listo, falta un dato (el número de cuenta de VICOMER)**

Cierra el circuito del Comité de Pagos: la orden aprobada en el artefacto se convierte en el
archivo que se sube a Banca Empresas como carga masiva, sin retipear nada.

---

## Falta un solo dato para que funcione

Abre `Pagos/banco/bg_config.json` y pon el número de cuenta de VICOMER en Banco Guayaquil
desde la que salen los pagos:

```json
"cuenta_empresa": "1234567"
```

Sin eso el generador se niega a correr — a propósito: una cuenta equivocada en el campo 2
haría que el banco rechace el archivo entero o, peor, lo debite de otra cuenta.

---

## Flujo

```
Comité de pagos (artefacto)  ->  orden_pago_<SEMANA>.json  ->  Pagos/salida/
                                          |
                                          v
                              python3 banco_guayaquil.py generar
                                          |
              +---------------------------+---------------------------+
              v                           v                           v
   banco_bg_..._NN.txt          banco_bg_..._NN.xlsm        banco_bg_..._NN.log
   (se sube al banco)         (respaldo auditable)      (incluidos y excluidos)
```

`pagos_correo.py` ya adjunta automáticamente lo que aparezca en `Pagos/salida/`.

---

## Cómo se sube en la web de Banco Guayaquil

1. **Banca Empresas > Cash Management > Cargar > Carga de órdenes**
2. **Cargar archivo** → elige el `.txt` → **Procesar**
3. **Revisar** para validar el resultado de la carga
4. **Aprobar la orden.** Sin aprobación no se procesa — es el paso que más se olvida.

Soporte del banco: **3730100 ext. 86300** o tu oficial de cuenta.

---

## El maestro de beneficiarios

Se importa del export propio del banco, así que por construcción coincide con lo que BG
tiene registrado:

**Banca Empresas > Pagos a terceros > Beneficiarios > Exportar** → luego:

```bash
python3 banco_guayaquil.py maestro "Pagos/banco/Beneficiarios-de-pagos-a-terceros-AAAAMMDD.xlsx"
```

Importación del 2026-08-03: **189 beneficiarios únicos de 208 filas**, todos con cuenta
bancaria, 100 con correo, sin ningún banco fuera del Anexo 4.

Las 19 filas de diferencia son beneficiarios que estaban duplicados con dos formas de pago
(una en efectivo y otra a cuenta). **Se prefiere siempre la cuenta**: deja rastro bancario y
no obliga al proveedor a ir a una agencia con su cédula. Las alternativas quedan guardadas en
el campo `alternativas` de cada registro por si hay que cambiarlas a mano.

Para ver qué proveedores con deuda todavía no están registrados en el banco:

```bash
python3 banco_guayaquil.py diag
```

---

## El emparejamiento se hace por RUC, no por nombre

`pagos_cxp.py` ahora trae el RUC de cada proveedor desde `res.partner.vat` de Odoo, y viaja
por la orden de pago hasta el archivo del banco. El nombre queda sólo como segundo criterio.

Esto importa: en Odoo un proveedor puede estar como «Entregas Especiales S.A.» y en el banco
como «Entregas Especiales». Emparejar por nombre significaría, tarde o temprano, pagarle al
beneficiario equivocado.

Si un pago no encuentra beneficiario, **no se inventa nada**: queda fuera del `.txt` y aparece
en el `.log` con el motivo. Es preferible que falte un pago a que salga uno mal dirigido.

---

## El formato del archivo

20 campos separados por tabulador, un pago por línea, ASCII puro, saltos CRLF.

Verificado contra **dos fuentes independientes que coinciden campo por campo**:

1. El macro `CreaArchTxt` extraído del VBA de la plantilla oficial que entrega el banco.
2. La [especificación pública de BG para pago a terceros](https://ayudaempresas.bancoguayaquil.com/hc/es/articles/11032985670804--Cu%C3%A1l-es-el-formato-para-cargar-una-orden-de-Cash-Management-para-pago-a-terceros-en-mi-Banca-Empresas).

Detalles que el generador respeta y que son fáciles de equivocar a mano:

- **Valor**: 13 dígitos en centavos, sin punto. `12.645,76` → `0000001264576`.
  El cálculo redondea explícitamente para que `0.07 × 3` dé 21 centavos y no 20.
- **Cuenta de la empresa**: siempre 10 dígitos con ceros a la izquierda.
- **Número de cuenta del beneficiario**: se rellena a 10 dígitos **sólo** si el banco es
  Guayaquil (0017). Para otras instituciones va tal cual — rellenarlo la haría inválida.
- **Campo 5 (Código)**: número de cuenta si es transferencia; identificación si es ventanilla.
- **Tipo de ID**: cédula = 10 dígitos → `C`, RUC = 13 → `R`, resto → `P`.
- **Campo 18 (Localidad)**: vacío obligatorio cuando la forma de pago es CTA.
- **Campo 20**: `PAGOS VARIOS|correo`. El pipe sólo va si hay correo; si no, se omite.
- Acentos y eñes se transliteran a ASCII y se eliminan tabuladores del contenido, que
  romperían la separación de campos.

`python3 banco_guayaquil.py autotest` verifica los 30 puntos anteriores sin tocar la red.

---

## Validaciones que dejan un pago fuera

- El proveedor no está en el maestro de beneficiarios del banco
- Sin referencia (BG la exige; es lo que el proveedor ve como número de factura)
- Monto cero, negativo o de más de 13 dígitos
- Transferencia sin número de cuenta, sin tipo de cuenta válido o sin código de institución
- Cédula que no tiene 10 dígitos o RUC que no tiene 13

---

## Archivos

| Archivo | Función |
|---|---|
| `banco_guayaquil.py` | Generador, importador del maestro, diagnóstico y autotest |
| `Pagos/banco/bg_config.json` | Cuenta de la empresa y prefijo del archivo |
| `Pagos/banco/maestro_proveedores.json` | 189 beneficiarios importados del banco |
| `Pagos/banco/bg_bancos.json` | 460 códigos de institución financiera (Anexo 4) |
| `Pagos/banco/plantilla_bg_pago_proveedores.xlsm` | Plantilla oficial, base del `.xlsm` de respaldo |

---

## Pendientes

1. **Poner `cuenta_empresa`** en `bg_config.json`.
2. Correr `banco_guayaquil.py diag` cuando haya CxP de Ecuador, para ver qué proveedores
   con deuda faltan por registrar como beneficiarios en Banca Empresas.
3. Probar la primera carga real con **un solo pago de monto pequeño** antes de mandar una
   orden completa. El banco valida al procesar, pero un archivo bien formado con datos
   equivocados se procesa igual.
4. Opcional: encadenar la generación al pipeline (`pagos_correo.py` ya adjunta lo que haya
   en `Pagos/salida/`), para que el archivo salga solo al aprobar la orden.
