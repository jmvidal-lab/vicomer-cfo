# Estados Financieros Grupo VICOMER — traspaso a Claude Code

**Qué es:** un tablero HTML de una sola página con el balance general y el estado de
resultados de VICOMER (Ecuador) y VINTRAL (Colombia), más una vista de grupo.
Nació para una reunión con un asesor externo —ex CEO de Marcimex y Jaher— y su criterio
de diseño fue ese: que un operador con oficio pueda leer los estados en treinta segundos
y que las preguntas incómodas estén contestadas antes de que las haga.

**Estado al 7 de octubre de 2026:** corte **7-oct-2026**, extraído directo del mayor de
Odoo con `generar_eeff.py`. Ecuador reproduce el estado firmado de julio al centavo
(resultado 98.861,50 y patrimonio 549.628,41); Colombia **no**, y la diferencia está
medida en el panel de conciliación de la pestaña Grupo. El corte de julio desde los
estados del contador se conserva en `datos/eeff_2026-07.json`.

---

## 1. Estructura

```
EstadosFinancieros/
├── CLAUDE.md                  convenciones que Claude Code debe respetar aquí
├── HANDOFF.md                 este documento
├── build.py                   verifica los datos y arma el HTML
├── datos/
│   └── eeff_2026-07.json      TODAS las cifras. Única fuente de verdad.
├── src/
│   └── eeff_template.html     markup + estilos + lógica de presentación
└── dist/
    ├── eeff_artifact.html     para publicar como artefacto (sin doctype/head/body)
    └── eeff_standalone.html   documento completo, abrir con doble clic
```

**La separación datos / presentación es el punto.** El tablero nació como un HTML escrito
a mano con las cifras incrustadas en el JavaScript. Eso funciona una vez y se rompe la
segunda: alguien corrige un renglón del P&G, olvida el subtotal, y la página muestra un
estado financiero que no cuadra —con tipografía impecable y total seguridad—. Nadie lo
nota hasta que lo suma un tercero en una reunión.

## 2. Cómo se corre

```bash
cd EstadosFinancieros
python3 build.py --check     # solo verifica los datos, no escribe
python3 build.py             # verifica y reconstruye dist/
python3 build.py 2026-09     # otro corte: lee datos/eeff_2026-09.json
```

Solo biblioteca estándar. Sin dependencias, sin entorno virtual, sin red.

`build.py` **se niega a construir si los datos no cuadran**. Hoy corre 19 comprobaciones:

| Comprobación | Qué atrapa |
|---|---|
| Cada subtotal del P&G se reconstruye desde las líneas anteriores | editar un renglón y olvidar el total |
| Los `%` del P&G son sobre ventas netas | mezclar la base del porcentaje |
| Activo = pasivo + patrimonio | un balance que no cierra |
| El resultado del ejercicio del balance es el del P&G | los dos estados contándose distinto |
| Razón corriente y endeudamiento coinciden con el balance | indicadores escritos a mano |
| Margen neto coincide con el P&G | lo mismo |
| Ciclo de caja = cobro + inventario − pago | un componente cambiado sin recalcular |
| La TRM es plausible y está fechada | publicar con una tasa inventada |
| `meta.corte_iso` existe y tiene forma de fecha | que el badge de antigüedad deje de funcionar |

Tolerancias: 1 unidad de moneda, 0,15 puntos porcentuales, 1,5 días. Los días de ciclo se
presentan redondeados, así que 145 + 298 − 198 da 245 mientras el valor sin redondear es
244,3. Esa es la razón de la tolerancia, no un descuido.

## 3. Contrato de datos

`datos/eeff_<corte>.json` tiene tres bloques de primer nivel:

- **`meta`** — `corte` (texto), `corte_iso` (`AAAA-MM-DD`, alimenta el badge de
  antigüedad), `trm`, `trm_fecha`, `trm_fuente`, `dias` (días transcurridos del período:
  212 para enero–julio), `tc_contable` (histórico, ya no se usa para presentar).
- **`EC` y `CO`** — cada uno con:
  - `pl[]` — el estado de resultados **en orden de lectura**. Cada línea lleva `k`
    (etiqueta), `v` (monto con signo: los egresos van negativos) y `t`:
    - `h` encabezado · `r` resta · `g` suma · `s` subtotal de ventas netas
    - `S` subtotal intermedio · `F` resultado final
    - `pct` opcional: porcentaje sobre ventas netas, solo en subtotales.
  - `bg` — balance en cinco listas: `activo`, `activo_nc`, `pasivo`, `pasivo_nc`,
    `patrimonio`. Cada partida: `k`, `v`, `sub` (el desglose que se lee en gris) y
    `flag: true` para marcar una partida que merece explicación.
  - `ind` — indicadores. Los derivables del balance **se comprueban**; los que requieren
    datos externos (DSO, DIO, DPO, EBITDA) se declaran y hay que recalcularlos a mano al
    cambiar de corte.

**Agregar un país** es agregar una clave más junto a `EC` y `CO`. La vista de grupo
(`grupo()` en la plantilla) tiene Ecuador y Colombia escritos a mano: ese es el punto que
hay que generalizar primero si entra Costa Rica.

## 4. De dónde salió cada cifra

Todo viene de cuatro archivos de contabilidad entregados el 10 de septiembre de 2026:

| Archivo | Qué aportó |
|---|---|
| `Balance General Vicomer de enero a julio 2026.xls` | balance Ecuador |
| `Balance De Resultados Vicomer de enero a julio 2026.xls` | P&G Ecuador |
| `balance_general Vintral del enero a julio 2026.xlsx` | balance Colombia |
| `estado_de_resultados Vintral a julio 2026.xlsx` | P&G Colombia |

**Lo que se verificó, no lo que se supuso:**

- La venta neta de Colombia, **933.278.870,49**, coincide **al centavo** con la suma
  enero–julio de `OdooVentas/dashboard_ventas.json`, que a su vez ya estaba conciliado
  contra el EEFF oficial. Es el amarre más fuerte que tiene este tablero.
- La utilidad de Colombia, **193.781.946,08**, es idéntica en el P&G y en el balance.
- El balance de Ecuador cierra con descuadre de un centavo; el de Colombia, exacto.

**Una trampa que ya costó una versión equivocada:** el primer archivo de resultados de
Vintral que llegó era de **julio solo**, no del acumulado, y el encabezado decía
únicamente "jul 2026". Cargaba 279.728.301 de costo de mercancía contra 60.526.085 de
ingreso del mes —4,6 veces— y arrojaba una pérdida de 262 millones que contradecía la
utilidad del balance. Se detectó porque el ingreso coincidía con la venta de julio del
reporte conciliado, no con la del acumulado. **Antes de cargar cualquier estado de
resultados nuevo, comprobar contra `dashboard_ventas.json` a qué período corresponde.**

## 5. Reglas no negociables

Son las mismas de todo el ecosistema CFO VICOMER y aquí mandan igual:

1. **Una cifra sin fuente verificable no entra.** Antes de estimar, se muestra el hueco
   marcado como hueco. Un cero real y un dato faltante tienen que verse distintos.
2. **Las cifras no se ajustan.** Los descuadres y las partidas discutibles se muestran en
   "Puntos de atención", no se corrigen en silencio.
3. **El USD de Colombia es de presentación, no contable.** Se convierte con la TRM del
   Banco de la República, fechada y visible en pantalla. Una consolidación formal exige
   además tasa de cierre para el balance y tasa promedio para el resultado: este tablero
   no la hace y lo dice.
4. **La conversión no reemplaza la consolidación.** La vista de grupo suma sin eliminar
   intercompañía y lo declara.
5. **VIX S.A.S. se excluye** del consolidado del grupo (decisión de gerencia).

## 6. Convenciones técnicas

- **Una sola página autocontenida.** Sin CDN, sin fuentes externas, sin `localStorage`
  (los artefactos publicados lo bloquean). Todo el CSS y el JS van dentro del archivo.
- **`dist/eeff_artifact.html` no lleva `<!doctype>`, `<html>`, `<head>` ni `<body>`**: la
  plataforma envuelve la página al publicarla. El standalone sí los lleva.
- **Claro y oscuro.** La paleta se define completa en `:root`, se redefine bajo
  `@media (prefers-color-scheme:dark)` con el guardia `:root:not([data-theme="light"])`,
  y otra vez bajo `:root[data-theme="dark"]`. Ningún color se define solo dentro de un
  media query.
- **Colores con significado fijo:** azul = activo y subtotales · naranja = pasivo y
  egresos · verde = patrimonio y resultado positivo · rojo = crítico · ámbar = alerta.
- **Responsive real.** `.grid2` colapsa a una columna bajo 900 px; las tablas van dentro
  de `.scroll` con `overflow-x:auto`.

## 6-bis. El traductor desde Odoo

`generar_eeff.py AAAA-MM-DD` lee `account.move.line` y emite el contrato de la sección 3.
Existe porque el diagnóstico de asientos contestó la pregunta que lo bloqueaba:

> El diario **"Apertura ER"** de Ecuador —1.114.344,15, el **74,2% del ingreso del año**—
> no es ruido: es el resultado de enero–julio trasladado desde Perseo en la migración. El
> error anterior no era incluirlo, era **sumarlo además** a la serie histórica cosida.
> Incluido una sola vez, Odoo reproduce el julio oficial al centavo. Lo mismo en Colombia
> con `MISCE/2026/03/0011` del 31-mar (enero–marzo, 262.356.597).

Prefijos de gasto, iguales en las dos compañías: `502.01` ventas · `502.02` administrativos
· `502.03` financieros · `502.04` Ecuador no deducibles, Colombia impuesto a la renta.

El **DPO se calcula solo sobre proveedores comerciales**. La deuda con la casa matriz no es
crédito de proveedor: incluirla llevaba el DPO de Colombia a 454 días e inventaba un
financiamiento que no existe.

## 6-ter. El filtro de rango

`datos/eeff_<corte>.json → serie` trae, por país y por mes, el **movimiento** del estado de
resultados y la **foto** del balance al cierre. La página arma cualquier rango sin volver a
Odoo. Tres reglas lo gobiernan:

1. **Flujo contra saldo.** El P&G se suma sobre el rango; el balance es la foto del cierre
   del último mes. Un selector que mueva los dos igual produce un balance inventado.
2. **El patrimonio carga el año, no el rango.** Si pedís agosto–octubre, el P&G es de ese
   rango pero la fila «Resultado del ejercicio» del balance sigue siendo enero–octubre, y la
   página lo dice en el subtítulo de esa fila. Sin eso el balance no cerraría.
3. **Los bloques de la migración no se parten.** Ecuador tiene enero–julio en un solo asiento
   de 10 líneas; Colombia enero–marzo en 13. Un bucket entra solo si su período cae entero en
   el rango; si no, se muestra como hueco con su monto. Antes de estimar, el hueco.

Barrido de verificación: 110 combinaciones de rango, **0 balances que no cierren**.

### El costo de ventas no sigue a la venta

Medido el 7-oct-2026, ratio costo/venta por mes:

| | Ene–Jul/Mar | Abr | May | Jun | Jul | Ago | Sep | Oct |
|---|---|---|---|---|---|---|---|---|
| Ecuador | 58,1% | — | — | — | — | 45,9% | 16,1% | 5,9% |
| Colombia | 54,1% | **0%** | **0%** | 13,5% | **462%** | 60,9% | 39,1% | 76,4% |

El costo entra por ajustes de inventario periódicos y no contra cada factura. En un rango
corto el margen mide el calendario del ajuste, no el negocio. Por eso la página **no publica
porcentajes de margen** cuando el costo del rango se aparta más de 20 puntos del ratio del
año o es cero con ventas: los deja en «—» y lo explica en pantalla.

## 7. Lo primero que hay que hacer

1. **Cerrar la brecha de Colombia.** Al 31-jul el balance del contador y el de Odoo
   difieren en 227 millones de activo y 183 de pasivo: intercompañía −141,4M, proveedores
   nacionales −139,2M, proveedores del exterior +107,2M, impuesto a la renta +43,6M. El
   resultado difiere en 43.581.990, explicado íntegramente por la provisión de renta
   (Odoo 115.763.000 en el asiento `MISCE/2026/05/007` del 26-may contra 72.180.000 del
   estado oficial). Hasta cerrarlo, el grupo no tiene cifra consolidada firmable.
2. **Arreglar el registro del costo de ventas, en los dos países.** No es solo que falte
   costo en Ecuador desde agosto (27,8% contra 58,1% histórico, unos 117.906 que son el 41%
   de la utilidad reportada): es que el costo se registra por ajuste periódico y no contra la
   venta, lo que deja meses en 0% y meses en 462%. Mientras eso siga así, el grupo no puede
   medir margen por período, ni por producto, ni por cliente.
3. **Actualizar la TRM** del día en `meta.trm` y `meta.trm_fecha` en cada corte.
4. **Incorporar Costa Rica** cuando registre costo de ventas. La plantilla ya lo soporta:
   basta agregar el bloque al JSON.

## 8. Hallazgos abiertos — contenido, no código

Están en pantalla en "Puntos de atención" y siguen sin resolverse:

- **El capital suscrito de Colombia no está pagado.** 800.000.000 de capital contra una
  cuenta por cobrar a accionistas de exactamente 800.000.000. Sin ese renglón el
  patrimonio efectivo es 622.438.727 y la prueba ácida cae de 1,02 a **0,53**.
- **La cuenta intercompañía no cuadra.** VINTRAL registra por pagar a VICOMER
  876.691.003 COP (US$ 282.851 a la TRM usada); VICOMER registra por cobrar US$ 179.236.
  Diferencia **US$ 103.615**. Solo cuadraría a 4.891 COP/USD, tasa que no existió en
  2026: no es cambiario, faltan asientos de un lado.
- **El margen está del lado caro.** Colombia 52,5% bruto y 20,8% neto; Ecuador 41,8% y
  8,9%. Si el reparto viene del precio de transferencia, el grupo reconoce utilidad donde
  la tarifa de renta es más alta.
- **Los dos ciclos de caja.** Ecuador 130 días, Colombia 244. El grupo factura US$ 1,41
  millones en siete meses y tiene US$ 78 mil en caja.
- **Deuda y margen están en empresas distintas.** Toda la deuda financiera del grupo
  (US$ 326.865) está en Ecuador, que además le presta a Colombia; Colombia vende con
  margen alto y sin deuda bancaria.

## 9. Historial

| Fecha | Qué pasó |
|---|---|
| 10-sep-2026 | Primera versión, con el P&G de Colombia equivocado (julio en vez del acumulado) |
| 10-sep-2026 | Llega el acumulado correcto de Vintral; cuadra contra facturación y balance |
| 10-sep-2026 | Botón global COP/USD con la TRM del día (3.099,48) |
| 07-oct-2026 | TRM al día (3.216,01) y badge de antigüedad del corte |
| 07-oct-2026 | Filtro de rango dinámico con serie mensual, guardia de costo no creíble y barrido de 110 rangos |
| 07-oct-2026 | Conexión directa a Odoo. `generar_eeff.py`, corte 7-oct, panel de conciliación contra los estados firmados, plantilla sin países ni cifras en duro |
| 07-oct-2026 | Traspaso a Claude Code: datos separados de presentación, `build.py` con 18 comprobaciones, y se corrige una nota del tab Grupo que seguía diciendo "3.700 COP/USD" después de haberse adoptado la TRM |
