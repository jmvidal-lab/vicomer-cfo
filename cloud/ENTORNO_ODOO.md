# Entorno en la nube con conexión a Odoo

En la cuenta Team, créelo en **claude.ai/code › Entornos › Nuevo entorno**. Esta es la configuración del entorno actual, «Odoo Def»:

| Campo | Valor |
|---|---|
| Nombre | `Odoo VICOMER` (o el que prefiera) |
| Acceso a red | **Limitado**, con los registros de paquetes permitidos y los servidores MCP permitidos |
| Dominios permitidos | `vicomer.odoo.com` y `www.datos.gov.co` (TRM oficial). Agregue `api.respond.io` solo si también migra el trabajo con respond.io. |
| Script de configuración | Ninguno. No hace falta: el pipeline usa solo la biblioteca estándar de Python. |

## Variables de entorno

| Variable | Valor |
|---|---|
| `ODOO_URL` | `https://vicomer.odoo.com` |
| `ODOO_DB` | `intitecnologia-v-comer-main-27740127` |
| `ODOO_LOGIN` | el usuario de Odoo con el que se conecta hoy (lo ve en el entorno «Odoo Def» de la cuenta personal) |
| `ODOO_APIKEY` | **genere una clave nueva** en Odoo: *Preferencias › Seguridad de la cuenta › Nueva clave API* |

**Las claves no van en este zip.** Tampoco las pegue en un chat ni en un documento.

Recomendaciones:

- Use una clave API nueva para la cuenta Team. Cuando la nueva funcione, revoque en Odoo la que usaba la cuenta personal.
- Idealmente, use un usuario de Odoo **solo de lectura**. Todas las tareas son de solo lectura.
- Si el entorno es **de organización**, cualquier miembro del Team con acceso al entorno puede usar la conexión a Odoo. Para datos financieros conviene que sea **personal**, o compartirlo solo con quien corresponda.

## Bloqueo de XML-RPC en Odoo

Su Odoo tiene instalado el módulo `block_xmlrpc` (INTI Tecnología). Desde la cuenta personal, las sesiones en la nube se conectan sin problema. Si en la cuenta Team `python3 eeff_odoo.py check` no responde «CONEXION OK», pida a INTI que autorice ese acceso.
