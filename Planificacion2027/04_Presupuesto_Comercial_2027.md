# PRESUPUESTO COMERCIAL 2027 — RESUMEN

**Libro:** `Planificacion2027/salida/Presupuesto_Comercial_2027.xlsx` (se regenera con `python3 Planificacion2027/presupuesto_2027.py <carpeta_datos>`; 796 fórmulas, 0 errores). Todo supuesto es editable en la hoja `Supuestos`; el escenario se cambia en una celda.
**Convención:** venta neta sin IVA, **sin intercompañía**. Ecuador y Costa Rica en USD; Colombia en COP (USD solo de presentación a TRM 3.200).

## 1. Cómo se construyó (y por qué no se parece al presupuesto 2026)

| País | Presupuesto 2026 | Real 2026E | Cumplimiento | Lección |
|---|---|---|---|---|
| Ecuador | USD 2.290.147 | ≈ 1.830.000 | ~80 % | Creció 12 % sobre 2025, pero el presupuesto pedía +40 % |
| Colombia | COP 3.672 M | ≈ 1.512 M | ~41 % | Cifra de deseo; destruyó la utilidad del presupuesto como herramienta |
| Costa Rica | USD 300.002 | ≈ 106.000 | ~35 % | Un cliente y un contenedor no son un plan |

El 2027 se arma **de abajo hacia arriba por cuenta/canal**, desde el run-rate 2026 medido en el ERP, con tres factores por canal (conservador / base / ambicioso) y una estacionalidad explícita.

## 2. Ecuador (USD)

| Canal | Real 2025 | 2026E | **2027 base** | Δ | MB obj. | Qué tiene que ser verdad |
|---|---|---|---|---|---|---|
| Retail Sukasa (Comohogar) | 1.123.494 | 1.195.000 | **1.255.000** | +5 % | 36 % | Techo deliberado. Exhibición y promotoría mantienen; no se compra crecimiento con NC |
| Proyectos (Prodesigns) | 148.624 | 156.000 | **185.000** | +19 % | 40 % | Pipeline CRM (Otero 3B, Neo Muebles) cerrado en H1 |
| Consumidor final + digital | 145.215 | 200.000 | **280.000** | +40 % | 48 % | Web/marketplaces activos (lista D5), showroom, servicio técnico como puerta de entrada |
| B2B / HORECA / constructoras | 116.859 | 153.000 | **215.000** | +40 % | 42 % | Un vendedor dedicado a cuentas corporativas |
| Otros retail y dealers | 99.699 | 125.000 | **215.000** | +72 % | 38 % | 2 cuentas nuevas con exhibición (Colineal ampliado, Favorita, Marcimex) |
| **Total** | **1.633.892** | **1.829.000** | **2.150.000** | **+18 %** | **38,7 %** | Sukasa baja de 65 % a 58 % del total |

Conservador 1,91 M · Ambicioso 2,41 M. Estacionalidad: índice 2023–2025 (picos marzo, junio, agosto–septiembre, noviembre–diciembre; valles abril y julio).

## 3. Colombia (COP)

| Cuenta / canal | 2026E | **2027 base** | Δ | MB obj. | Qué tiene que ser verdad |
|---|---|---|---|---|---|
| Casa Magna | 881 M | **980 M** | +11 % | 45 % | Acuerdo marco firmado en Q1; cartera < 60 d; comisión Felipe solo sobre cobrado |
| USA Electrodomésticos | 579 M | **640 M** | +11 % | 45 % | Reposición mensual y exhibición |
| Inverdescuentos | 40 M | **60 M** | +50 % | 42 % | Portafolio ampliado |
| Nuevos distribuidores | 12 M | **250 M** | — | 40 % | 1 cuenta regional facturando desde abril, **después** del reprecio |
| Proyectos / constructoras / dealers | 0 | **90 M** | — | 45 % | KAM con meta propia; sin histórico |
| **Total** | **1.512 M** | **2.020 M** (≈ USD 631 k) | **+34 %** | **44,3 %** | Casa Magna baja de 58 % a 49 % |

Conservador 1.654 M · Ambicioso 2.389 M. 2026E = Q1 (instancia vintral1, 262 M) + Odoo abr–oct (1.193 M menos 100 M intercompañía) + nov–dic estimados 157 M. **Hueco declarado:** no existe en la nube la venta jun–dic 2025 (vintral1 sin credencial), por eso no hay columna 2025.

## 4. Costa Rica (USD)

| Cuenta | 2026E | **2027 base** | MB obj. | Qué tiene que ser verdad |
|---|---|---|---|---|
| Cemaco | 86.680 | **170.000** | 35 % | Reposición trimestral; cartera al día (hoy 100 % vencida) |
| Panafoto | 19.068 | **70.000** | 35 % | Arrancó en octubre con dos entidades; segunda compra en Q1 |
| Proyectos y dealers nuevos | 0 | **40.000** | 40 % | Alguien vende en el país (hoy nadie) |
| **Total** | **105.748** | **280.000** | **35,7 %** | Costa Rica registra costo de ventas (hoy margen 100 % en el mayor) |

Conservador 201 k · Ambicioso 355 k.

## 5. Grupo (USD de presentación)

| | 2026E | Conservador | **Base** | Ambicioso |
|---|---|---|---|---|
| Ecuador | 1.829.000 | 1.913.850 | **2.150.000** | 2.405.800 |
| Colombia | 472.500 | 516.875 | **631.250** | 746.563 |
| Costa Rica | 105.748 | 201.000 | **280.000** | 355.000 |
| **Grupo** | **2.407.248** | **2.631.725** | **3.061.250** | **3.507.363** |
| Margen bruto base | | | **≈ 1,21 M (39,6 %)** | |
| Compras Hyxion implícitas | | | ≈ 1,48 M (mín. contractual 0,6 M) | |

## 6. Plan de compras por SKU (extracto, Ecuador)

Demanda 12 meses real (Perseo + Odoo) × 1,15 − stock, con 2 meses de seguridad. Los cinco SKU que más compra exigen: **TEW30ES** (180 uds, ≈ USD 136 k), **TMO30H** (147), **TRG3601** (68, ≈ 88 k), **TRF3601FD** (55, ≈ 91 k), **H9** (166, ≈ 56 k). En Colombia el plan dice **no comprar** TEW30ES, TMO30H, HRT3618U-M1 ni HDW2401SS en H1 (12–16 meses de cobertura) y sí MK04SS304, TMO24H y TRG3601. Detalle en la hoja `Plan compras SKU`.

## 7. Reglas del presupuesto (para que sirva de algo)

1. **Se mide sobre factura (account.move), nunca sobre pedido** (en Colombia difieren 15 %).
2. **Las comisiones se liquidan sobre cobrado**, con clawback a 90 días (term sheet Felipe).
3. **Re-forecast en abril y agosto**: los factores por canal se ajustan con datos; el presupuesto no se reescribe.
4. **Un canal que lleve dos meses por debajo del 70 % dispara revisión** de precio, exhibición o vendedor, no una excusa.
5. **Costo comercial variable total por cuenta ≤ 6 % de la venta cobrada** (vendedor + Felipe + piso + rebates).
6. **Ninguna cuenta nueva sin límite de crédito en Odoo y término de pago cargado** (hoy: 0 clientes con límite, 4 con término).
