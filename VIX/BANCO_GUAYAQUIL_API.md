# Conectar la API de Banco Guayaquil (movimientos de VIX) — paso a paso

Objetivo: que los movimientos de la cuenta de VIX (…3043) lleguen solos, cada día, a la contabilidad.
La API es de **consulta**: no puede mover dinero.

Arquitectura: **Mac → banco (mTLS) → movimientos normalizados en Drive → Claude en la nube concilia.**
El certificado y las claves del banco viven **solo en el Mac**, igual que hoy los datos bancarios.

---

## Paso 1 — Definición de la API ✅ HECHO (2026-11-13)

`current-account-api-v1.json` (Drive `VIX/CONTABILIDAD`). El conector ya está construido con esa
especificación. **Ojo: el servicio es para CUENTA CORRIENTE.** Si la …3043 es de ahorros, pedir al banco el servicio equivalente.

## Paso 2 — Pedir el alta al banco (tú o tu asistente, por correo al oficial de cuenta)

Pide **ambiente de desarrollo primero** y, al validar, producción. Preguntas exactas:

1. Alta de la empresa **VIX S.A.S. (RUC 0195183759001)** como consumidor del servicio *Movimientos – Consulta v1*.
2. Que la aplicación vea **solo la cuenta …3043** y tenga **solo permiso de consulta**.
3. Entrega de credenciales: `client_id`, `client_secret` y **scope** de cada ambiente.
4. **Certificado de cliente (mTLS)**: ¿lo emite el banco o debemos enviar un CSR? Formato y vigencia.
5. ¿Hay **lista blanca de IP**? (importante: la IP del Mac puede cambiar; si exigen IP fija, avísame).
6. Límites de consulta (llamadas/día, rango máximo de fechas) y horario de corte de movimientos.
7. Costo del servicio, si lo tiene.

## Paso 3 — Certificado (si el banco pide CSR) (10 min, en el Mac)

La llave privada se genera en el Mac y **nunca sale de ahí**; al banco solo va el `.csr`.

```bash
mkdir -p ~/.bg && chmod 700 ~/.bg && cd ~/.bg
```

```bash
openssl req -new -newkey rsa:2048 -nodes -keyout bg_vix.key -out bg_vix.csr -subj "/C=EC/O=VIX S.A.S./CN=vix-integraciones"
```

```bash
chmod 600 ~/.bg/bg_vix.key
```

Envía `bg_vix.csr` al banco. Te devolverán el certificado firmado → guárdalo como `~/.bg/bg_vix.pem`.

## Paso 4 — Guardar las credenciales en el Mac (5 min)

Archivo `~/.bg/bg_vix.env` (permisos 600, fuera del repo). Plantilla, con TUS valores:

```
BG_ENV=dev
BG_CLIENT_ID=...
BG_CLIENT_SECRET=...
BG_SCOPE=api://.../.default
BG_CERT=/Users/juanmarcelo/.bg/bg_vix.pem
BG_CERT_KEY=/Users/juanmarcelo/.bg/bg_vix.key
BG_CUENTA=...
```

```bash
chmod 600 ~/.bg/bg_vix.env
```

**Nunca** pegues estos valores en el chat ni en el repo.

## Paso 5 — Prueba (en el Mac, desde la carpeta del proyecto)

Prueba 1, solo credenciales:

```bash
set -a; source ~/.bg/bg_vix.env; set +a; python3 VIX/vix_banco.py api-token
```

Prueba 2, una semana de movimientos (compárala contra Banca Empresas):

```bash
set -a; source ~/.bg/bg_vix.env; set +a; python3 VIX/vix_banco.py api-bajar 2026-11-01 2026-11-07
```

Si cuadra, cambia `BG_ENV=prod` en `~/.bg/bg_vix.env` y repite.
Errores típicos: `9992` = la app no está autorizada para esa cuenta; `9993` = client_id mal; HTTP 403 "Client certificate is missing" = falta el certificado.

## Paso 6 — Automatizar (yo)

`launchd` diario en el Mac: baja los movimientos del día anterior → JSON en Drive `VIX_Contabilidad/banco/`.
La tarea de la nube los toma, concilia y te reporta descuadres.

---

### Mientras tanto (no bloquea)

Descarga de **Banca Empresas → Cash Management** los movimientos jul–nov 2026 de la cuenta …3043 (Excel)
y súbelos a Drive `VIX_Contabilidad/banco/`. Con eso sanea los libros sin esperar al banco.
