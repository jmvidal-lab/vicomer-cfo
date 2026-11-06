# Conexión Odoo — Colombia (VINTRAL) + Costa Rica

Extrae las **ventas facturadas sin IVA** de tu Odoo multicompañía, con el mismo
criterio que Perseo (notas de crédito restan). Archivo: `odoo_ventas.py`.

## 1. Datos que necesito (4, no 2)

El API de Odoo (XML-RPC) autentica con **URL + base de datos + usuario + API key**.
Tú ya tienes URL y key; faltan la **DB** y el **login**:

| Dato | Dónde encontrarlo |
|---|---|
| **URL** | La dirección de tu Odoo (p.ej. `https://vicomer.odoo.com`). *(ya la tienes)* |
| **API key** | En Odoo: avatar → *Mi perfil* → *Seguridad de la cuenta* → *Nueva clave de API*. *(ya la tienes)* |
| **DB** (base de datos) | En Odoo.sh: nombre del proyecto/branch de producción. También aparece en el selector de la pantalla de login, o pregúntalo a quien administra el servidor. |
| **LOGIN** | Tu correo de acceso a Odoo (el usuario con permiso a ver ambas compañías). |

## 2. Guardar credenciales (una vez, en tu Mac)

```bash
# Config (url, db, login)
cat > ~/.odoo_config.json <<'JSON'
{
  "url":   "https://TU-ODOO.odoo.com",
  "db":    "NOMBRE_BASE_DE_DATOS",
  "login": "tu_correo@v-comer.com"
}
JSON
chmod 600 ~/.odoo_config.json

# API key aparte
printf 'TU_API_KEY_DE_ODOO' > ~/.odoo_apikey && chmod 600 ~/.odoo_apikey
```

> Si no conoces la DB, deja `"db":""` y corre el diagnóstico: intentará listar
> las bases disponibles.

## 3. Correr el diagnóstico y enviármelo

```bash
cd "/Users/juanmarcelo/Claude/Projects/CFO VICOMER"
python3 odoo_ventas.py diag
```

Me devuelve: versión del servidor, **compañías y monedas visibles**, número de
facturas del año por compañía y una **muestra de 3 facturas** con sus campos.
Con eso confirmo la estructura real y **cableo Colombia y Costa Rica a los
presupuestos** (hoja `COLOMBIA 2026`, `COSTA RICA 2026` y el archivo de VINTRAL),
igual que hicimos con Ecuador.

## 4. Extraer datos (cuando ya conecte)

```bash
python3 odoo_ventas.py 2026     # genera OdooVentas/odoo_facturas_2026.json
```

## Detalle técnico

- Modelo: `account.move`, `move_type in (out_invoice, out_refund)`, `state = posted`.
- Monto: **`amount_untaxed_signed`** = base imponible SIN IVA, con signo (NC negativa),
  en la **moneda de cada compañía** (COP para VINTRAL; la que corresponda a CR).
- Multicompañía: consulta con `allowed_company_ids` para ver todas tus empresas.
- Autoprueba offline (sin conectarse a Odoo): `python3 odoo_ventas.py test`.
