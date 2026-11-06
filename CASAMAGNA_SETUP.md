# Automatización Sell Out + Sell In — Casa Magna

Pipeline **100% por API** que corre en tu Mac (LaunchAgent, como Perseo). Cada lunes:

1. **Sell Out** — baja los reportes NetSuite ("VENTAS SEMANA ANTERIOR") de tu Gmail por **IMAP** y parsea el XML.
2. **Sell In** — trae lo facturado a Casa Magna desde **Odoo por XML-RPC**, en las **dos** instancias:
   - `vintral1.odoo.com` → histórico (jun-2025 … mar-2026)
   - `vicomer.odoo.com` (base `intitecnologia-v-comer-main-27740127`) → abril-2026 en adelante
3. **Dashboard** — arma `Sell_Out_CasaMagna.html` (con el cuadro Sell In vs Sell Out) y lo comprime en `.zip`.
4. **Correo** — lo envía por SMTP a `dir.comercial@v-comer.com` y `kamcolombia@v-comer.com`.

Sin dependencias externas (solo la librería estándar de Python 3). Notas de crédito **restan**; cifras **sin IVA**.

## Archivos
| Archivo | Qué hace |
|---|---|
| `casamagna_config.json` | Config (instancias Odoo, partner ids de Casa Magna, Gmail, destinatarios, alias de SKU). **Sin secretos.** |
| `casamagna_sellin.py` | Extractor Odoo (2 instancias). `diag` / `test`. |
| `casamagna_sellout.py` | Extractor Gmail IMAP. `test`. |
| `casamagna_build.py` | Fusiona, arma dashboard, zip y correo. `--no-mail`. |
| `casamagna_pipeline.py` | Orquestador (corre los 3 pasos). |
| `casamagna_dashboard_template.html` | Plantilla del dashboard. |
| `automatizacion/com.vcomer.casamagna.plist` | LaunchAgent (lunes 13:30). |
| `instalar_casamagna.command` | Instala el LaunchAgent. |
| `CasaMagna/` | Salidas: JSONs, TSV, HTML, ZIP y logs. |

## Credenciales a crear (una vez, en tu Mac — yo nunca las manejo)

Todas van en archivos aparte con `chmod 600`. **No las pongas en el repo.**

### 1) App Password de Gmail (jmvidal@v-comer.com) — para IMAP y SMTP
Los reportes de Casa Magna llegan a **jmvidal@v-comer.com**, así que el IMAP debe entrar con esa cuenta. En Google (cuenta de jmvidal) → *Seguridad* → *Contraseñas de aplicaciones* → genera una y guárdala:
```bash
printf 'TU_APP_PASSWORD_DE_GMAIL' > ~/.gmail_jmvidal_apppass && chmod 600 ~/.gmail_jmvidal_apppass
```
> Requiere verificación en 2 pasos activa. Sirve para IMAP (bajar reportes) y SMTP (enviar el correo), ambas desde jmvidal@v-comer.com.

### 2) API key Odoo sistema NUEVO (vicomer) — **ya la tienes**
Está en `odoo_apikey.txt` (la que configuraste). No hay que hacer nada.

### 3) API key Odoo sistema VIEJO (vintral1)
`vintral1.odoo.com` es una **instancia distinta**, con su propio login/clave. En vintral1 (con el usuario que tenga acceso; en tu navegador está `ventas@iglaceec.com`) → avatar → *Mi perfil* → *Seguridad de la cuenta* → *Nueva clave de API*:
```bash
printf 'TU_API_KEY_DE_VINTRAL1' > ~/.odoo_vintral1_apikey && chmod 600 ~/.odoo_vintral1_apikey
```
> En `casamagna_config.json`, la instancia `vintral1` usa `login: jmvidal@v-comer.com`. Si ese usuario **no** existe en vintral1, cambia ese `login` por el correcto (p. ej. `ventas@iglaceec.com`) y usa la key generada con ese usuario. El comando `diag` te dice si autenticó.

## Puesta en marcha
```bash
cd "/Users/juanmarcelo/Claude/Projects/CFO VICOMER"

# a) Autopruebas offline (no tocan red) — deben decir "SELFTEST OK"
python3 casamagna_sellin.py test
python3 casamagna_sellout.py test

# b) Diagnóstico Odoo (prueba ambas instancias)
python3 casamagna_sellin.py diag

# c) Primera corrida SIN enviar correo (revisa el dashboard en CasaMagna/)
python3 casamagna_pipeline.py --no-mail

# d) Cuando todo se vea bien, instala el LaunchAgent (lunes 13:30)
chmod +x instalar_casamagna.command
./instalar_casamagna.command

# Probar la corrida completa (con correo) ya instalado:
launchctl start com.vcomer.casamagna
tail -f "CasaMagna/run.log"
```

## Notas de negocio
- **Sell In** = `account.move` `out_invoice`/`out_refund` `posted`, líneas de producto, `price_subtotal` (sin IVA), NC negativa.
- Casa Magna = partner `child_of` `[10,11,12]` en vintral1 y `[496]` en vicomer (NIT 811031313-5).
- **Normalización de SKU** entre sistemas en `casamagna_config.json` → `sku_alias` (`TMO30H→TMO30`, `TMO24H→TMO24`, `TIM15→TIM1501`) y sufijo `-M1` que se elimina solo. `sku_excluir` saca líneas que no son producto (`DSTOCLI` descuento, `PROTMK04SS304` protector, `FT05`). Si aparecen SKU nuevos sin cruzar, agrégalos ahí.
- **Cobertura In/Out** ≥ 100% = Casa Magna te ha pedido todo (o más) de lo que ha vendido. "Falta pedir" en el dashboard = vendieron más de lo facturado (orden pendiente o stock previo a jun-2025).
