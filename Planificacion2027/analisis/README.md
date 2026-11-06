# Scripts de análisis — Planificación 2027

Extraen y analizan Perseo (Ecuador 2021–jul 2026) y Odoo (3 países) para el diagnóstico y el presupuesto.
Solo lectura. Credenciales únicamente desde el environment (`source cloud/setup.sh`).

```bash
S=/ruta/de/trabajo; mkdir -p $S/perseo $S/odoo $S/out
python3 analisis/perseo_dl.py  $S            # facturas + plan de cuentas + asientos por año → $S/perseo/
python3 analisis/odoo_dump.py  $S/odoo       # facturas, líneas, stock, mayor, pedidos, CRM, tareas…
python3 analisis/odoo_dump2.py $S/odoo       # helpdesk, partners, proyectos, listas de precios, proveedores
python3 -I analisis/perseo_an.py $S          # ventas EC por año/cliente/categoría/SKU/canal → $S/out/perseo_ventas_an.*
python3 -I analisis/perseo_pl.py $S          # P&L y balance EC 2021–2026 desde el mayor → $S/out/perseo_pl.*
python3 -I analisis/odoo_sales.py $S         # ventas, cartera, CxP, categorías, inventario, pedidos → $S/out/odoo_sales.*
python3 -I analisis/odoo_gl.py $S            # P&L mensual, gastos, balance, intercompañía, tasas, bancos → $S/out/odoo_gl.*
python3 -I analisis/odoo_ops.py $S           # helpdesk, proyectos, CRM, empleados, partners, listas de precios
python3 presupuesto_2027.py $S               # libro Excel → salida/
```

Reglas aprendidas (costaron horas):
- **Perseo `asientoscontables_consulta` devuelve cada asiento repetido hasta 22 veces**: deduplicar por `libros_diariosid` o la venta sale ×3.
- Excluir del P&L los asientos cuyo concepto empieza por «Asiento de Cierre» (el cierre anual se devuelve por cuenta).
- `facturas_consulta` con `dias` grande trae todo el histórico con detalle de ítems y costo (`facturasd.detalles`).
- En Odoo, `standard_price` leído con contexto multicompañía devuelve el valor de la compañía principal (COP) para Ecuador: el margen por SKU de Ecuador se calcula con el costo de kardex de Perseo, no con Odoo.
- `read_group` de `account.move.line` con `date:month` devuelve el mes en español («agosto 2026»).
