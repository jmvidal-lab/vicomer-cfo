# Rutina 1 · Tablero VICOMER: actualización de los viernes

- **Nombre:** Tablero VICOMER: actualización viernes (Odoo)
- **Frecuencia:** semanal, viernes 07:47, zona America/Guayaquil (cron: `CRON_TZ=America/Guayaquil 47 7 * * 5`)
- **Entorno:** el entorno con las variables ODOO_* (ver 4_entorno/ENTORNO_ODOO.md)
- **Conectores:** Google Drive (solo para subir la bitácora; opcional). Artifacts viene incluido en Claude.
- **Programas:** desde este repo (`EstadosFinancieros/`), no desde Drive. Cambio aprobado el 28-nov-2026.
- **Antes de crearla:** reemplace `https://claude.ai/artifact/YG1aVBdkujJeKKvTn3ZTxJ` por la URL del tablero que publicó en la cuenta Team, y `1y5aFWAYn_WrCdzJBbkRNZxNcBYJTqSXH` por la carpeta donde subió `1_proyecto/`. Si conectó la misma cuenta de Google, la carpeta actual es `1y5aFWAYn_WrCdzJBbkRNZxNcBYJTqSXH`.

## Instrucciones (copiar desde aquí)

Copia fiel del prompt de la tarea `trig_01M3FqVroiN6PvTHczP9SJmv` (cuenta Team), actualizado el 28-nov-2026.

TAREA PROGRAMADA DE LOS VIERNES. Actualizar el tablero "Dashboards Generales Vicomer" con datos frescos de Odoo, a pedido de Juan Marcelo. Corre desatendida: no hagas preguntas. Odoo es SOLO LECTURA. Nunca imprimas valores de credenciales. No hagas commits ni push.

PUERTAS (si alguna falla, NO publicar, escribir la bitácora y reportar en qué puerta falló)
1. Credenciales: `env | cut -d= -f1 | grep '^ODOO' | sort` debe mostrar ODOO_APIKEY, ODOO_DB, ODOO_LOGIN y ODOO_URL. Nunca imprimas los valores.
2. Programas (fuente única: el repo). Ubica el repo jmvidal-lab/vicomer-cfo en el workspace (si no está, usa mcp__claude-code-remote__add_repo y clónalo). Desde su raíz: `git fetch origin main` y `git checkout origin/main -- EstadosFinancieros`. Si en main no existe EstadosFinancieros/recuperar_del_artefacto.py, el PR de migración aún no se fusionó: trae la carpeta de la rama de trabajo con `git fetch origin claude/hopeful-fermat-odmoso && git checkout FETCH_HEAD -- EstadosFinancieros`. Trabaja dentro de EstadosFinancieros/. Lee ACTUALIZAR.md y CLAUDE.md completos: son el procedimiento y las reglas. NO uses los .py de la carpeta de Drive: pueden estar desactualizados.
3. Plantilla y corte anterior: lee el tablero con Artifact (action "read") en https://claude.ai/artifact/YG1aVBdkujJeKKvTn3ZTxJ, lee el archivo completo que te indique (es requisito para poder republicar) y corre `python3 recuperar_del_artefacto.py <ese archivo>`. Eso genera datos/eeff_<corte anterior>.json y sobrescribe src/eeff_template.html: después restaura la plantilla del repo con `git checkout -- src/eeff_template.html` (manda la del repo; la del artefacto solo sirve para los datos).
4. Red: `python3 eeff_odoo.py check` debe decir «CONEXION OK».

PROCEDIMIENTO
5. Corre `python3 eeff_odoo.py regresion 2026-07-31`. Si alguna diferencia cambió, NO publiques. Investiga la causa en Odoo en solo lectura: busca asientos con fecha hasta el 31-jul modificados recientemente y cambios de tipo de cuenta en mail.tracking.value. Revisa también si las empresas tienen fecha de bloqueo (fiscalyear_lock_date y hard_lock_date). Reporta la causa con cuenta, monto, fecha y usuario. Solo corrige la clasificación si el cambio es de presentación y la naturaleza contable de la cuenta es inequívoca, como pasó con ANTICIPOS RECIBIDOS el 28-oct, y documenta la decisión. Nunca cambies las diferencias esperadas ni la verificación para que pase. Si contabilidad entrega un estado de julio firmado de nuevo, las diferencias esperadas se actualizan solo con ese documento como fuente y con aprobación de Juan Marcelo.
6. Extrae con fecha de hoy el corte, la serie, las ventas y el inventario, en corte.json, serie.json, ventas.json e inv.json.
7. Toma la TRM del día de la Superintendencia Financiera (datos.gov.co, dataset 32sa-8pi3 o mcec-87by) o del Banco de la República, confirmada con al menos dos fuentes. Nunca reutilices la de una corrida anterior.
8. Corre `python3 armar_datos.py --corte corte.json --serie serie.json --ventas ventas.json --inventario inv.json --anterior datos/eeff_<corte anterior>.json --trm <TRM> --trm-fecha "<fecha>" --salida datos/eeff_AAAA-MM.json`
9. Revisión de textos, que no se puede automatizar: los 2 veredictos, todas las notas y el bloque conc (veredicto_ec, veredicto_co, texto_grupo y los valores odoo de las filas, que salen de la regresión) citan cifras. Verifica una por una contra los datos nuevos y reescribe toda nota cuya cifra haya cambiado. Una nota con un número viejo es peor que no tener nota.
10. Corre `python3 build.py AAAA-MM`. Son 37 comprobaciones. Si falla, arregla la causa en los datos o la extracción, nunca en la verificación.
11. Revisa la página con Playwright (dist/eeff_standalone.html): sin errores de consola, sin scroll horizontal a 390 px, y recorriendo las tres secciones y todas las pestañas.
12. Publica dist/eeff_artifact.html con Artifact usando url = https://claude.ai/artifact/YG1aVBdkujJeKKvTn3ZTxJ. Conserva el título. Vuelve a leer el tablero y confirma que meta.corte_iso es la fecha de hoy.
13. Bitácora `Corrida_AAAA-MM-DD_<Publicada|Abortada>.md`, con las puertas, la regresión, la TRM y sus fuentes, las comprobaciones, las notas reescritas y los hallazgos. Si Google Drive está disponible (ToolSearch "+Google_Drive"), súbela a la carpeta VICOMER_EEFF_pipeline (id 1y5aFWAYn_WrCdzJBbkRNZxNcBYJTqSXH). Si no lo está, incluye la bitácora completa en tu respuesta final. Si tuviste que cambiar algún .py, no lo subas: describe el cambio en la bitácora para aplicarlo en el repo.

REGLAS: una cifra sin fuente verificable no entra. Los descuadres se muestran, no se corrigen. El balance es una foto y no se suma. El histórico previo a la migración no se regenera. Ecuador se presenta con participación (15%) e impuesto a la renta (25%) estimados y marcados como estimados. Odoo es solo lectura.

CIERRE (máximo 10 líneas): si publicaste o no, y con qué corte; por país frente al corte anterior: ventas, resultado, caja, ciclo de caja e inventario dormido; resultado de la regresión; qué nota cambió; la decisión de la semana.
