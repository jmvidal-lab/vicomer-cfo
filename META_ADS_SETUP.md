# Meta Ads — conexión de solo lectura

Conecta a Claude con las cuentas publicitarias de Facebook e Instagram del grupo para
leer métricas (gasto, alcance, clics, conversaciones, compras). **No puede crear, editar,
pausar ni gastar**: `meta_ads.py` solo hace GET y el token solo tiene `ads_read`.

## 1. Crear el token (una sola vez, ~15 min, desde business.facebook.com)

| # | Dónde | Qué hacer |
|---|---|---|
| 1 | developers.facebook.com → Mis apps → Crear app | Tipo **Empresa (Business)**. Vincúlala al Business Manager de VICOMER. Nombre sugerido: `VICOMER CFO Lectura`. |
| 2 | En la app → Agregar producto | **Marketing API**. No hace falta pasar revisión de la app: el uso es interno. |
| 3 | Configuración del negocio → Usuarios → **Usuarios del sistema** → Agregar | Nombre `claude-lectura`, rol **Empleado** (no Administrador). |
| 4 | Ese usuario del sistema → **Asignar activos** | Cuentas publicitarias de VICOMER / VINTRAL / Costa Rica → permiso **Ver rendimiento** únicamente. |
| 5 | Mismo usuario → **Generar token** | App: la del paso 1. Caducidad: **Nunca**. Permisos: marca **solo `ads_read`** (y `read_insights` si aparece). **No** marques `ads_management` ni `business_management`. |
| 6 | Copia el token | No lo pegues en el chat ni en un archivo del repo. Va directo al paso 2. |
| 7 | (Opcional, recomendado) App → Configuración → Básica → **Clave secreta de la app** | Se guarda como `META_APP_SECRET`: firma cada llamada; si alguien roba el token sin el secreto, no le sirve. |

**Por qué System User y no tu usuario personal:** no caduca, no depende de tu sesión de
Facebook, se revoca solo sin tocar tu cuenta y tiene solo los permisos que le asignas.

## 2. Cargar en el environment de la nube

Menú del environment (barra de título de la sesión) → **Edit** → secretos / variables:

| Variable | Valor | Obligatoria |
|---|---|---|
| `META_ACCESS_TOKEN` | el token del paso 5 | Sí |
| `META_AD_ACCOUNT_IDS` | `act_123…,act_456…` (Ads Manager → selector de cuenta → ID) | No (si falta, lee todas las cuentas asignadas) |
| `META_APP_SECRET` | clave secreta del paso 7 | No |

Red: `graph.facebook.com` ya responde desde la nube (verificado 2026-11-17). Si algún día
da 403 / `host_not_allowed`, agrégalo en *Network access → Allowed domains*.

En el Mac: `printf '%s' 'TOKEN' > ~/.meta_token && chmod 600 ~/.meta_token`.

## 3. Verificar

```bash
source cloud/setup.sh            # debe listar ✔ META_ACCESS_TOKEN
python3 cloud/check_red.py       # ✔ Meta Ads: CONEXION OK (n cuentas)
python3 meta_ads.py check        # identidad, permisos y cuentas visibles
python3 meta_ads.py insights     # campañas, últimos 30 días → Meta/*.json + *.csv
```

`check` avisa si el token tiene `ads_management`: en ese caso, regenéralo solo con `ads_read`.

## Notas de datos

- **Atribución:** 7 días clic + 1 día vista (estándar de Meta). Es lo que Meta *se atribuye*,
  no la venta incremental: concíliala contra ventas de Odoo antes de tomar decisiones de presupuesto.
- **Resultados:** `--resultado conversaciones|leads|compras`. Las compras se toman como el máximo
  entre `purchase`, `omni_purchase` y `fb_pixel_purchase`, sin sumarlas (Meta repite la misma compra en varios tipos).
- **Moneda:** la de cada cuenta publicitaria (USD Ecuador, COP Colombia). No se convierte aquí.
- Las salidas (`Meta/`) están en `.gitignore`: son datos de la cuenta, no se suben al repo.
- El `.csv` de salida se puede pegar directo en el paso 2 del artefacto *Copiloto de Pauta Meta*.
