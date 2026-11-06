# Estados Financieros Grupo VICOMER

Tablero de balance general y estado de resultados de VICOMER (Ecuador) y VINTRAL
(Colombia). Lee `HANDOFF.md` antes de tocar nada: ahí está de dónde salió cada cifra y
qué trampas ya costaron una versión equivocada.

**Para actualizarlo, sigue `ACTUALIZAR.md`.** Los datos salen de Odoo por XML-RPC con las
credenciales en variables de entorno (`ODOO_URL`, `ODOO_DB`, `ODOO_LOGIN`, `ODOO_APIKEY`);
no hace falta la computadora del usuario. Corre solo, los viernes a las 9:00.

## Reglas de este directorio

- **Las cifras viven en `datos/eeff_<corte>.json`. Nunca en el HTML.** Si encuentras un
  número escrito a mano en `src/eeff_template.html`, eso es una regresión: muévelo al
  JSON — y eso incluye las notas de "Puntos de atención", que viven en `notas[]` de cada
  país como `[nivel, título, texto]`. La plantilla ya no tiene ningún país ni ninguna
  cifra escrita a mano: `grupo()` recorre las claves de `DATA`, así que agregar Costa Rica
  es agregar un bloque al JSON.
- **Después de cualquier cambio, corre `python3 build.py`.** Verifica 37 cosas y se niega
  a construir si los datos no cuadran. No publiques ni entregues nada que no haya pasado.
- **`dist/` es generado.** No lo edites a mano; edita `src/` o `datos/` y reconstruye.
- **`dist/eeff_artifact.html` no lleva `<!doctype>`, `<html>`, `<head>` ni `<body>`.** La
  plataforma de artefactos envuelve la página al publicar. El standalone sí los lleva.
- **Solo biblioteca estándar de Python.** Sin pandas, sin openpyxl, sin requests.
- **Para un corte nuevo, no cargues cifras a mano.** `eeff_odoo.py corte|serie <fecha>` saca
  todo de Odoo y `armar_datos.py` lo pega con los textos arrastrados. Antes de extraer, corre
  `eeff_odoo.py regresion`: si la diferencia contra el estado firmado cambió, no publiques.
- **`eeff_odoo.py` es autocontenido a propósito.** No importes `finanzas_dashboard.py` ni
  leas JSON de la carpeta padre desde él: esa dependencia ya rompió el ecosistema una vez.
- **La página es autocontenida.** Sin CDN, sin fuentes externas, sin `localStorage`.
- **El filtro de rango tiene tres reglas que no se negocian.** (1) El estado de resultados
  se suma sobre el rango; el balance es la foto del cierre del último mes y nunca se suma.
  (2) El patrimonio de esa foto carga el resultado **acumulado del año**, no el del rango, o
  el balance no cierra. (3) Un bucket de la serie entra solo si el período que cubre está
  **entero** dentro del rango: el bloque de la migración no se trocea, se declara como hueco.
- **El margen no se publica si el costo del rango no es creíble.** El costo de ventas entra
  por ajustes periódicos, no contra cada venta: Colombia registró 0% en abril y mayo y 462%
  en julio. Si el costo del rango se aparta más de 20 puntos del ratio del año, o es cero con
  ventas, los porcentajes salen en «—». Nunca 100% de margen bruto.
- **El histórico previo a la migración es un snapshot congelado, no un cálculo.** Vive en
  `ventas.<país>.historico` (Ecuador Ene–Jul desde Perseo, Colombia Ene–Mar desde la
  instancia anterior). Odoo no lo conoce; `armar_datos.py` lo arrastra y aborta si se
  solapa con el primer mes que Odoo sí tiene. Trae el total del mes, **nunca** clientes:
  la concentración y la tabla de clientes se miden solo sobre lo facturado en el ERP.
- **Al cambiar de corte, actualiza `meta.corte`, `meta.corte_iso`, `meta.dias`, `meta.trm`
  y `meta.trm_fecha`.** El badge de antigüedad sale de `corte_iso`; si queda viejo, el
  tablero miente sobre su propia frescura.

- **La salud de inventario se calcula en el navegador, no en Python.** El JSON solo trae
  existencias y demanda por SKU (`inventario.<país>.items`); el ABC, el XYZ, la cobertura,
  las clases de salud y el capital dormido salen de `invCalc()` en la plantilla, para que el
  filtro de rango los recalcule sin volver a Odoo. Si agregás un método, va ahí.
- **El stock no se recorta con el rango; la demanda sí.** La extracción no guarda histórico
  de existencias. La página lo declara cuando el rango no termina en el último mes. No
  inventes un stock pasado ni "ajustes" la cobertura para que se vea mejor.
- **El XYZ no se estima.** Menos de 3 meses con venta: «sin clasificar». Cero ventas: fuera
  de la matriz, en su propio bloque con su cifra. Mezclarlos esconde el hallazgo.
- **La poda de referencias es por ficha vacía, nunca por tope.** Si cortás las primeras N,
  la suma de `stock_val` deja de llegar al `stock_total` y `build.py` falla — como debe.
- **La política de inventario vive en `INV_POL`** (30 / 180 / 90 días) y se muestra en
  pantalla. Es una política declarada, no un dato: si cambia, cambia el número y se dice.

- **Ecuador se presenta con impuestos estimados y marcados.** El ERP no provisiona
  participación de trabajadores (15%) ni renta (25%). `eeff_odoo.py` las estima —devolviendo
  los no deducibles a la base— y el tablero muestra "Utilidad neta estimada" con la etiqueta
  «est.». Nunca presentes la utilidad del ERP como utilidad neta de Ecuador.
- **El detalle por cuenta y el bloque fiscal existen solo para el corte completo.** Si el
  usuario elige un rango parcial, la expansión se desactiva y la pantalla lo dice. No
  muestres el detalle del corte junto a un P&G de otro período.

## Reglas de contenido

- Una cifra sin fuente verificable no entra. Antes de estimar, muestra el hueco marcado
  como hueco. Un cero real y un dato faltante deben verse distintos.
- No ajustes cifras para que cuadren. Los descuadres van a "Puntos de atención".
- El USD de Colombia es de presentación, con TRM fechada en pantalla. No es consolidación.
- Antes de cargar un estado de resultados nuevo, comprueba contra
  `../OdooVentas/dashboard_ventas.json` a qué período corresponde de verdad. Ya pasó una
  vez que un archivo rotulado "a julio" era solo el mes de julio.

## Estilo del texto en pantalla

Español neutro, tono ejecutivo, directo. Los "Puntos de atención" se escriben para que un
tercero con oficio los lea y entienda el problema sin explicación adicional: el titular
dice qué pasa, el cuerpo da la cifra y la consecuencia. Nada de lenguaje motivacional.
