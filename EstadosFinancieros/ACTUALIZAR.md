# Actualizar el tablero — procedimiento

**Frecuencia:** viernes 9:00 (hora Ecuador/Colombia, UTC−5), automático.
**Fuente:** Odoo por XML-RPC, desde el contenedor en la nube.
**No necesita la computadora del usuario.** Las credenciales van por variable de entorno.

---

## 0. Credenciales

El contenedor llega a `vicomer.odoo.com` por su cuenta; lo único que necesita es con qué
autenticarse. Cuatro variables de entorno:

```
ODOO_URL=https://vicomer.odoo.com
ODOO_DB=intitecnologia-v-comer-main-27740127
ODOO_LOGIN=jmvidal@v-comer.com
ODOO_APIKEY=<la API key de Odoo>
```

`eeff_odoo.py` las lee primero y solo cae a `odoo_config.json` / `odoo_apikey.txt` si no
están. Si faltan, **se niega a correr con un mensaje explícito** en vez de producir un
JSON vacío. Nunca imprimas ni pegues la API key en una respuesta.

## 1. Conexión y regresión

```bash
python3 eeff_odoo.py check
python3 eeff_odoo.py regresion 2026-07-31
```

La regresión compara Odoo contra el estado firmado por contabilidad al 31-jul-2026.
**No exige identidad: exige que la diferencia siga siendo la misma** que el día que se
midió y se explicó. Ecuador cuadra el resultado y el patrimonio al centavo; Colombia tiene
tres diferencias documentadas (provisión de renta −43.581.990; balance −227M activo y
−183M pasivo).

**Si un delta cambia, la prueba falla y corta la corrida.** Significa que alguien posteó
asientos con fecha vieja o cambió el plan de cuentas. No publiques: averiguá qué pasó.

## 2. Extraer

```bash
HOY=$(date +%F)
python3 eeff_odoo.py corte  $HOY > corte.json    # balance y estado de resultados
python3 eeff_odoo.py serie  $HOY > serie.json    # serie mensual del P&G y del balance
python3 eeff_odoo.py ventas $HOY > ventas.json   # facturación por mes y cliente + cartera
python3 eeff_odoo.py inventario $HOY > inv.json  # existencias por SKU + demanda mensual
```

El modo `inventario` devuelve **todas** las fichas de producto de cada compañía con sus
existencias al corte (en el contexto de la compañía: `qty_available` × `standard_price`) y
la demanda mensual en unidades y en valor sacada de las líneas de factura. `armar_datos.py`
poda las fichas sin stock ni movimiento, declara los meses con demanda y concilia el
maestro contra el inventario en almacén del balance. **La poda es por ficha vacía, no por
tope:** cortar las primeras N referencias haría que la suma por SKU no llegue al inventario
del balance, y `build.py` lo rechaza.

## 3. TRM del día

Buscala en la web (Banco de la República). **No reutilices la de la semana pasada.**

## 4. Armar, construir, publicar

```bash
python3 armar_datos.py --corte corte.json --serie serie.json --ventas ventas.json \
  --inventario inv.json \
  --anterior datos/eeff_<anterior>.json --trm <TRM> --trm-fecha "<fecha>" \
  --salida datos/eeff_AAAA-MM.json

python3 build.py AAAA-MM
```

`armar_datos.py` arrastra del corte anterior las notas, el bloque `conc` y los textos de
`meta`; `build.py` corre 37 comprobaciones y se niega a construir si los datos no cuadran.

Publicá `dist/eeff_artifact.html` **pasando la URL existente** para no crear un artefacto
nuevo: `https://claude.ai/artifact/MYAf2trkLXcidH3CzBNEaY`

## 4-bis. El histórico previo a la migración NO se regenera

Los meses anteriores al ERP vienen de un **snapshot congelado** que vive en el JSON de
datos, en `ventas.<país>.historico`:

| País | Meses | Total | Fuente |
|---|---|---|---|
| Ecuador | Ene–Jul 2026 | 1.117.243,89 USD | Perseo, capturado 3-ago-2026 |
| Colombia | Ene–Mar 2026 | 262.321.140,79 COP | instancia `vintral1`, capturada 5-jul-2026 |
| Costa Rica | — | — | no hay operación anterior |

Odoo no los conoce y nunca los va a devolver. `armar_datos.py` los **arrastra** del archivo
anterior y, antes de pegarlos, comprueba que no se solapen con el primer mes que Odoo sí
tiene: si se solaparan, aborta en vez de contar dos veces la misma venta.

Traen el total facturado del mes pero **no el detalle por cliente**. En pantalla salen con
barra atenuada y la tabla de clientes declara que mide solo la parte que está en el ERP.
No conviertas esto en un cálculo: es un dato verificado y congelado.

Amarre que lo valida: con el histórico, Colombia Ene–Jul da 933.278.870, la misma venta
neta del estado firmado por contabilidad.

## 4-ter. Inventario: lo que mide y lo que NO mide

La sección "Salud de inventario" calcula todo en el navegador a partir de
`inventario.<país>.items`. Tres cosas hay que tener presentes al leerla y al escribir el
reporte semanal:

1. **El stock no tiene histórico.** Las existencias son la foto del corte y no se mueven
   con el filtro de rango; la demanda sí. Cuando el rango no termina en el último mes, la
   página lo declara en pantalla. No inventes un stock pasado.
2. **La ventana de demanda es la que Odoo tenga**, y es distinta por país (Ecuador desde
   agosto, Colombia desde abril, Costa Rica desde junio). «Sin venta» quiere decir «no
   facturó en esos días», no «muerto». El tablero escribe la cifra de días en la etiqueta
   para que nadie la lea como un veredicto.
3. **El XYZ necesita 3 meses con venta.** Con menos, la referencia sale «sin clasificar»;
   con cero ventas, sale fuera de la matriz, en su propio bloque. No se estima una clase.

La política de salud (30 días = riesgo, 180 = sobrestock, 90 = objetivo para medir el
exceso dormido) está declarada en pantalla y vive en `INV_POL` de la plantilla. Es una
política, no un dato: si el negocio define otra, se cambia ahí y el número cambia.

## 5. Revisar el veredicto y las alertas — el paso que no se puede automatizar

El veredicto de "Lectura en 30 segundos" y las alertas (`titulo` / `vemos` / `hacer`) se
arrastran tal cual y **citan cifras**. Repasá que sigan siendo ciertas:

- ratio costo/venta por mes de los dos países
- saldo intercompañía de ambos lados y la diferencia en dólares
- capital suscrito de Colombia sin pagar
- ciclos de caja
- cuentas transitorias de Ecuador con saldo
- concentración de clientes y % de cartera vencida por país
- la provisión estimada de Ecuador (participación 15% + renta 25%) y su utilidad neta estimada
- la tasa implícita de la deuda y los intereses de mora de Colombia
- el capital dormido de cada país y la conciliación maestro vs balance (Colombia venía
  con +0,9% de diferencia; si pasa del 2% hay que decirlo y no valorar por SKU)

Si una cifra cambió, reescribí el texto. **Una nota con un número viejo es peor que no
tener nota.**

## 6. Guardar y reportar

Si la computadora del usuario está conectada, escribí los archivos de vuelta a
`~/Claude/Projects/CFO VICOMER/EstadosFinancieros/`. **Si no lo está, no pasa nada**: el
artefacto ya quedó publicado y los archivos actualizados se guardan en el proyecto.

Reportá breve y ejecutivo: qué cambió contra la semana pasada (ventas, resultado, caja,
ciclo de caja por país), si la regresión pasó, qué cifra contradice una nota, y qué hace
falta decidir.

---

## Reglas que no se negocian

1. Una cifra sin fuente verificable no entra. Antes de estimar, el hueco marcado como hueco.
2. Los descuadres se muestran, no se corrigen.
3. El margen no se publica si el costo del rango no es creíble.
4. El balance es la foto del cierre y jamás se suma.
5. El patrimonio de esa foto carga el resultado acumulado del año, no el del rango.
6. VIX S.A.S. se excluye del consolidado.
7. El USD de Colombia es de presentación, con TRM fechada. No es consolidación.

## Archivos

| Archivo | Qué hace |
|---|---|
| `eeff_odoo.py` | **Autocontenido.** Odoo → contrato de datos. `check` · `corte` · `serie` · `ventas` · `inventario` · `regresion`. El modo `corte` trae además EBITDA, depreciación, intereses separados de multas, inventario almacén/tránsito, cartera externa vs relacionadas, la carga tributaria y el detalle por cuenta para expandir |
| `armar_datos.py` | Pega corte + serie + textos arrastrados |
| `build.py` | 37 comprobaciones y arma `dist/` |
| `src/eeff_template.html` | Presentación. Sin países ni cifras en duro |

`eeff_odoo.py` **no importa nada del proyecto**: la configuración va embebida. Antes
dependía de `finanzas_dashboard.py` y de tres JSON de la carpeta padre; cuando el usuario
reorganizó su Escritorio en septiembre esas rutas se rompieron en silencio y el tablero
salió tres semanas con datos viejos sin que nada fallara. Una corrida automática no puede
depender de dónde esté cada archivo.
