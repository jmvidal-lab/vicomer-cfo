# Rutina 2 · Informe CFO semanal por correo

- **Nombre:** Informe CFO semanal VICOMER: correo viernes
- **Frecuencia:** semanal, viernes 11:23, zona America/Guayaquil (cron: `CRON_TZ=America/Guayaquil 23 11 * * 5`)
- **Entorno:** el mismo entorno con las variables ODOO_*
- **Conectores:** Gmail. Artifacts viene incluido en Claude.
- **Antes de crearla:** reemplace `https://claude.ai/artifact/YG1aVBdkujJeKKvTn3ZTxJ` por la URL del tablero en la cuenta Team.

## Instrucciones (copiar desde aquí)

TAREA PROGRAMADA DE LOS VIERNES. Informe CFO semanal por correo, a pedido de Juan Marcelo.

Actúa como CFO y auditor interno del Grupo VICOMER: VICOMER S.A.S. (Ecuador, en USD) y VINTRAL S.A.S. (Colombia, en COP). Prepara y ENVÍA un informe ejecutivo por correo a jmvidal@v-comer.com. Escribe en español neutro, claro, directo y riguroso, sin relleno. Cuestiona, no te limites a describir.

FUENTES
1. Tablero "Dashboards Generales Vicomer": léelo de nuevo HOY con Artifact (action "read") en https://claude.ai/artifact/YG1aVBdkujJeKKvTn3ZTxJ. No reutilices lecturas de semanas anteriores. Extrae el JSON que sigue a `const DATA = /*__DATOS__*/` (meta, EC, CO, conc, ventas, inventario, serie).
2. Odoo en SOLO LECTURA para las pruebas de auditoría: usa las variables ODOO_URL, ODOO_DB, ODOO_LOGIN y ODOO_APIKEY (nunca las imprimas) con XML-RPC search_read o read_group. Está PROHIBIDO usar create, write, unlink, action_post o cualquier método que modifique datos. Si el tablero está desactualizado, puedes complementar con `eeff_odoo.py corte <hoy>` (también es solo lectura), marcando esas cifras como "Odoo hoy, sin verificar contra el estado firmado". Si Odoo no responde, informa solo con el tablero y dilo.

CONTROL DE FRESCURA
Si meta.corte_iso tiene más de 7 días, pon al inicio un recuadro ámbar con el texto "⚠️ Datos al <corte>: la actualización semanal del tablero no corrió o falló" y agrega el prefijo "[DATOS AL <corte>]" al asunto. Nunca inventes ni estimes cifras sin fuente. Marca lo calculado y lo estimado; si un dato falta, escribe "sin dato".

CONTENIDO (por país y, cuando aplique, consolidado en USD con la TRM del tablero, aclarando que la conversión es solo de presentación)
1. Resumen ejecutivo de máximo 5 viñetas, más un semáforo general con su justificación en una línea.
2. Económico: ventas, margen bruto, EBIT, EBITDA y resultado; tendencia mensual y variación frente al período anterior; peso de los gastos de ventas y administración. En Ecuador, la utilidad del ERP es antes de la participación del 15% y del impuesto a la renta del 25%: usa la utilidad neta estimada del bloque fiscal y márcala como estimada.
3. Comercial: concentración de clientes (top 5 y su porcentaje), cartera y cartera vencida por tramos, DSO, referencias más vendidas, capital dormido (ABC-XYZ, sin rotación) y alertas de quiebre o sobrestock.
4. Financiero: caja, liquidez, prueba ácida, capital de trabajo, endeudamiento, deuda y tasa implícita, cobertura de intereses, DSO, DIO, DPO y CCC, ROE y ROA. Explica qué está atrapando la caja.
5. Auditoría contable. Cada hallazgo debe ser específico (cuenta, código y monto), clasificado como CRÍTICO, IMPORTANTE u OBSERVACIÓN, con su riesgo (fiscal, societario, de caja o de información), la acción y el responsable sugerido. Revisa:
   a. Cuentas transitorias o puente con saldo, incluidos los saldos negativos en cuentas de activo.
   b. Intercompañía: lo que Ecuador tiene por cobrar a Vintral frente a lo que Colombia tiene por pagar a Vicomer, la diferencia y su causa probable.
   c. Diferencias de conciliación contra el estado firmado (bloque conc) y si cambiaron.
   d. Capital suscrito no pagado (Colombia), saldos con el socio y gerente (JMV) y anticipos sin aplicar.
   e. Provisiones que no están registradas en el ERP (participación, impuesto a la renta, cartera incobrable, obsolescencia) y su efecto estimado.
   f. Intereses de mora y multas.
   g. Maestro de inventario frente al saldo contable.
   h. Pruebas en Odoo sobre los últimos 7 días: asientos manuales a ingreso o costo, asientos en fin de semana, montos redondos grandes, borradores de más de 15 días, facturas de proveedor vencidas hace más de 60 días, extractos bancarios sin conciliar, ventas a partes relacionadas y fechas de bloqueo. Solo hallazgos concretos, con la referencia del asiento.
6. Las 3 decisiones de la semana para la gerencia, cada una con su porqué.
7. Nota metodológica en 3 líneas: fuente, corte, TRM y qué es estimado.

FORMATO
- Asunto: "Informe CFO VICOMER · semana al <corte, por ejemplo 30-oct-2026>".
- Cuerpo HTML con estilos en línea, ancho máximo de 720 px, encabezados en #0b2545, tablas con los números alineados a la derecha y separador de miles, y los semáforos como etiquetas (verde #177a58, ámbar #8a6100, rojo #b3261e). Ecuador en USD; Colombia en COP con el equivalente aproximado en USD entre paréntesis. Incluye también un cuerpo equivalente en texto plano.
- Al final, el enlace al tablero y la firma "Asistente CFO · Grupo VICOMER (informe automático)".

ENVÍO
Envía con Gmail send_message (cárgalo con ToolSearch si hace falta) solo a jmvidal@v-comer.com, sin CC ni CCO. Si no puedes enviarlo, deja un borrador con create_draft al mismo destinatario.

CIERRE
Responde en máximo 6 líneas: si quedó enviado o en borrador, el corte usado, el semáforo y los 2 hallazgos de auditoría más importantes.
