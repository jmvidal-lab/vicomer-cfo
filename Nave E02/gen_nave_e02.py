# Genera el plano individual de la Nave E02-1 (A3, escala 1:200) en SVG + PDF + PNG.
# Uso: python3 gen_nave_e02.py
import os
import fitz

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "Nave_E02_plano_v1")

# ---------- Datos de la nave (m), tomados de GALPONES_INMOSERVICIOS 2026 ----------
W, D = 36.52, 32.00              # frente x fondo
COL_W, COL_D = 0.40, 0.60        # sección de columna
COL_X = [0.20 + 9.03 * i for i in range(5)]     # ejes A-E (centros)
COL_Y = [0.30 + 6.28 * i for i in range(6)]     # ejes 1-6 (centros)
DOORS = [(11.99, 3.50), (21.02, 3.50)]          # (x inicio, ancho) en fachada frontal
EAVE, RIDGE, GLASS_H, DOOR_H = 6.00, 9.00, 3.50, 3.50

S = 5.0                          # 1:200 -> 1 m = 5 mm
PX, PY = 32, 30                  # origen papel (mm) esquina sup-izq de la planta
EX, EY = 32, 262                 # elevación: x izq, y de nivel ±0.00

def px(x): return PX + x * S
def py(y): return PY + (D - y) * S      # y=0 es la fachada frontal (abajo)

o = []
def add(s): o.append(s)
def line(x1, y1, x2, y2, w=0.25, c="#000", dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    add(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="{c}" stroke-width="{w}"{d}/>')
def rect(x, y, w, h, sw=0.2, fill="none", c="#000"):
    add(f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" fill="{fill}" stroke="{c}" stroke-width="{sw}"/>')
def text(x, y, t, size=2.2, anchor="middle", weight="normal", rot=0, c="#000"):
    tr = f' transform="rotate({rot} {x:.2f} {y:.2f})"' if rot else ""
    add(f'<text x="{x:.2f}" y="{y:.2f}" font-family="Helvetica, Arial" font-size="{size}" '
        f'text-anchor="{anchor}" font-weight="{weight}" fill="{c}"{tr}>{t}</text>')

def hdim(x1, x2, y, label=None, size=1.9):
    line(x1, y, x2, y, 0.15)
    for x in (x1, x2):
        line(x - 0.8, y + 0.8, x + 0.8, y - 0.8, 0.2)
        line(x, y - 1.2, x, y + 1.2, 0.1)
    text((x1 + x2) / 2, y - 0.8, label or f"{(x2 - x1) / S:.2f}", size)

def vdim(y1, y2, x, label=None, size=1.9):
    line(x, y1, x, y2, 0.15)
    for y in (y1, y2):
        line(x - 0.8, y + 0.8, x + 0.8, y - 0.8, 0.2)
        line(x - 1.2, y, x + 1.2, y, 0.1)
    text(x - 0.8, (y1 + y2) / 2, label or f"{abs(y2 - y1) / S:.2f}", size, rot=-90)

add('<svg xmlns="http://www.w3.org/2000/svg" width="420mm" height="297mm" viewBox="0 0 420 297">')
add('<rect width="420" height="297" fill="#fff"/>')
rect(8, 8, 404, 281, 0.5)

# ---------- PLANTA ----------
# Ejes estructurales
for i, x in enumerate(COL_X):
    line(px(x), py(D) - 9, px(x), py(0) + 3, 0.1, "#c00", "3 1 0.6 1")
    add(f'<circle cx="{px(x):.2f}" cy="{py(D) - 11:.2f}" r="2" fill="#fff" stroke="#c00" stroke-width="0.2"/>')
    text(px(x), py(D) - 10.3, "ABCDE"[i], 2.2, c="#c00")
for j, y in enumerate(COL_Y):
    line(px(0) - 14, py(y), px(W) + 3, py(y), 0.1, "#c00", "3 1 0.6 1")
    add(f'<circle cx="{px(0) - 16:.2f}" cy="{py(y):.2f}" r="2" fill="#fff" stroke="#c00" stroke-width="0.2"/>')
    text(px(0) - 16, py(y) + 0.8, str(j + 1), 2.2, c="#c00")

# Piso interior
rect(px(0), py(D), W * S, D * S, 0, "#f4f1ea")
# Muros: posterior, laterales (gruesos)
for (x1, y1, x2, y2) in [(0, D, W, D), (0, 0, 0, D), (W, 0, W, D)]:
    line(px(x1), py(y1), px(x2), py(y2), 0.9)
# Fachada frontal acristalada con montantes cada ~1.20 m (excepto puertas)
line(px(0), py(0), px(W), py(0), 0.35)
line(px(0), py(0) - 0.6, px(W), py(0) - 0.6, 0.15)
x = 0.4
while x < W - 0.4:
    if not any(d0 - 0.05 <= x <= d0 + dw + 0.05 for d0, dw in DOORS):
        rect(px(x) - 0.3, py(0) - 0.6, 0.6, 0.6, 0.1, "#000")
    x += 1.22
# Puertas dobles abatibles
for d0, dw in DOORS:
    x0, x1, y0 = px(d0), px(d0 + dw), py(0)
    add(f'<rect x="{x0:.2f}" y="{y0 - 0.7:.2f}" width="{dw * S:.2f}" height="1.4" fill="#fff"/>')
    r = dw * S / 2
    line(x0, y0, x0, y0 - r, 0.2); line(x1, y0, x1, y0 - r, 0.2)
    add(f'<path d="M{x0:.2f},{y0 - r:.2f} A{r:.2f},{r:.2f} 0 0 1 {x0 + r:.2f},{y0:.2f}" fill="none" stroke="#000" stroke-width="0.15"/>')
    add(f'<path d="M{x1:.2f},{y0 - r:.2f} A{r:.2f},{r:.2f} 0 0 0 {x1 - r:.2f},{y0:.2f}" fill="none" stroke="#000" stroke-width="0.15"/>')
    text((x0 + x1) / 2, y0 - r - 1.2, "P 3.50×3.50", 1.6)
# Columnas: perimetrales + fila central (eje C)
cols = set()
for x in COL_X:
    cols |= {(x, COL_Y[0]), (x, COL_Y[-1])}
for y in COL_Y:
    cols |= {(COL_X[0], y), (COL_X[-1], y), (COL_X[2], y)}
for (x, y) in cols:
    rect(px(x) - COL_W * S / 2, py(y) - COL_D * S / 2, COL_W * S, COL_D * S, 0.2, "#9a9a9a")

# Textos interiores
text(px(COL_X[1]), py(D / 2) - 14, "NAVE E02-1", 5, weight="bold")
text(px(COL_X[1]), py(D / 2) - 8, f"Área bruta: {W * D:,.2f} m²", 3)
text(px(W / 2), py(D / 2) + 38, "N.P.T. ±0.00", 2.2)
text(px(W / 2), py(0) + 14, "▲ FACHADA FRONTAL / ACCESO", 2.6, weight="bold")
text(px(W) + 9, py(D / 2), "Colinda: corredor de servicio + baños (6.00 m) → Nave E02-2", 2, rot=-90, c="#555")
text(px(0) - 22, py(D / 2), "Lindero / retiro lateral", 2, rot=-90, c="#555")

# Cotas
hdim(px(0), px(W), py(D) - 17, "36.52")
for a, b in zip(COL_X, COL_X[1:]):
    hdim(px(a), px(b), py(D) - 4, "9.03")
fr = [0.40, 8.63, 0.40, 2.56, 3.50, 2.56, 0.40, 2.56, 3.50, 2.56, 0.40, 8.63, 0.40]
acc = 0.0
for v in fr:
    hdim(px(acc), px(acc + v), py(0) + 5, f"{v:.2f}", 1.6)
    acc += v
hdim(px(0), px(W), py(0) + 9.5, "36.52")
vdim(py(D), py(0), px(0) - 25, "32.00")
for a, b in zip(COL_Y, COL_Y[1:]):
    vdim(py(b), py(a), px(W) + 4, "6.28")

text(px(0), py(0) + 20, "PLANTA BAJA — NAVE E02-1", 3.2, "start", "bold")
text(px(W), py(0) + 20, "ESC. 1:200", 2.6, "end")

# ---------- ELEVACIÓN FRONTAL ----------
def ex(x): return EX + x * S
def ey(z): return EY - z * S
line(ex(-3), ey(0), ex(W + 3), ey(0), 0.4)
# Cubierta a dos aguas + cercha
ov = 0.6
add(f'<polyline points="{ex(-ov):.2f},{ey(EAVE - 0.1):.2f} {ex(W / 2):.2f},{ey(RIDGE):.2f} {ex(W + ov):.2f},{ey(EAVE - 0.1):.2f}" fill="none" stroke="#000" stroke-width="0.45"/>')
line(ex(0), ey(EAVE), ex(W), ey(EAVE), 0.25)
n = 8
for k in range(1, n):
    xk = W * k / n
    zk = EAVE + (RIDGE - EAVE) * (1 - abs(xk - W / 2) / (W / 2))
    line(ex(xk), ey(EAVE), ex(xk), ey(zk), 0.15)
    xm = W / 2 if k in (n // 2 - 1, n // 2 + 1) else (W * (k + (1 if k < n / 2 else -1)) / n)
    zm = EAVE + (RIDGE - EAVE) * (1 - abs(xm - W / 2) / (W / 2))
    if k != n // 2:
        line(ex(xk), ey(EAVE), ex(xm), ey(zm), 0.12)
# Columnas en fachada
for x in COL_X:
    rect(ex(x) - COL_W * S / 2, ey(EAVE), COL_W * S, EAVE * S, 0.2, "#eee")
# Mamparas de vidrio + puertas
for a, b in zip(COL_X, COL_X[1:]):
    x0, x1 = a + COL_W / 2 + 0.1, b - COL_W / 2 - 0.1
    rect(ex(x0), ey(GLASS_H), (x1 - x0) * S, GLASS_H * S, 0.2, "#e6f0f5")
    line(ex(x0), ey(GLASS_H / 2), ex(x1), ey(GLASS_H / 2), 0.12)
    m = round((x1 - x0) / 1.22)
    for k in range(1, m):
        line(ex(x0 + (x1 - x0) * k / m), ey(GLASS_H), ex(x0 + (x1 - x0) * k / m), ey(0), 0.12)
for d0, dw in DOORS:
    rect(ex(d0), ey(DOOR_H), dw * S, DOOR_H * S, 0.3, "#fff")
    line(ex(d0 + dw / 2), ey(DOOR_H), ex(d0 + dw / 2), ey(0), 0.2)
    line(ex(d0), ey(DOOR_H), ex(d0 + dw), ey(0), 0.1); line(ex(d0 + dw), ey(DOOR_H), ex(d0), ey(0), 0.1)
# Niveles
for z, lab in [(0, "±0.00"), (EAVE, "+6.00"), (RIDGE, "+9.00")]:
    line(ex(-3), ey(z), ex(W + 8), ey(z), 0.1, "#666", "1.5 1")
    text(ex(W + 8.5), ey(z) + 0.7, lab, 2, "start")
vdim(ey(EAVE), ey(0), ex(-4), "6.00")
vdim(ey(RIDGE), ey(EAVE), ex(-4), "3.00")
text(ex(0), EY + 9, "ELEVACIÓN FRONTAL — NAVE E02-1", 3.2, "start", "bold")
text(ex(W), EY + 9, "ESC. 1:200", 2.6, "end")

# ---------- CUADRO DE DATOS / CAJETÍN ----------
BX, BY, BW = 268, 20, 136
rect(BX, BY, BW, 262, 0.35)
text(BX + 4, BY + 9, "VICOMER — NAVE E02-1", 5, "start", "bold")
text(BX + 4, BY + 15, "Plano individual (extraído del conjunto Inmoservicios)", 2.3, "start", c="#444")
line(BX, BY + 19, BX + BW, BY + 19, 0.3)
rows = [
    ("Bloque", "E-02 (fila superior de la planta general)"),
    ("Posición", "1.ª nave del bloque (extremo izquierdo)"),
    ("Frente", "36.52 m"),
    ("Fondo", "32.00 m"),
    ("Área bruta", f"{W * D:,.2f} m²"),
    ("Altura a alero", "6.00 m"),
    ("Altura a cumbrera", "9.00 m"),
    ("Cubierta", "Dos aguas sobre cerchas metálicas"),
    ("Columnas", "0.40 × 0.60 m — 18 perimetrales + 4 interiores"),
    ("Modulación", "Ejes A–E @ 9.03 m · Ejes 1–6 @ 6.28 m"),
    ("Fachada frontal", "Mampara de vidrio h = 3.50 m"),
    ("Accesos", "2 puertas dobles 3.50 × 3.50 m"),
    ("Servicios", "Baños en corredor compartido junto al eje E"),
]
yy = BY + 26
for k, v in rows:
    text(BX + 4, yy, k, 2.4, "start", "bold")
    text(BX + 40, yy, v, 2.4, "start")
    line(BX + 2, yy + 2, BX + BW - 2, yy + 2, 0.08, "#bbb")
    yy += 6.6
yy += 4
text(BX + 4, yy, "NOTAS", 2.8, "start", "bold"); yy += 5.5
for nline in [
    "1. Medidas tomadas del plano general GALPONES_INMOSERVICIOS",
    "    2026 (C.D.&C. Construcciones, julio 2026). Verificar en sitio.",
    "2. Área bruta a ejes exteriores; área útil se descuenta columnas.",
    "3. Distribución interior: pendiente (en blanco para diseño).",
    "4. Columnas interiores sólo en eje C (luz libre 9.03 + 9.03 m).",
]:
    text(BX + 4, yy, nline, 2.2, "start"); yy += 4.6
# Cajetín inferior
line(BX, 250, BX + BW, 250, 0.3)
text(BX + 4, 257, "Proyecto: Nave industrial Vicomer", 2.4, "start")
text(BX + 4, 263, "Contiene: Planta baja · Elevación frontal", 2.4, "start")
text(BX + 4, 269, "Escala: 1:200 (A3)", 2.4, "start")
text(BX + 4, 275, "Fecha: octubre 2026 · Versión v1", 2.4, "start")
text(BX + BW - 4, 275, "Lámina 1/1", 2.4, "end", "bold")
add('</svg>')

svg = "\n".join(o)
with open(OUT + ".svg", "w") as f:
    f.write(svg)
doc = fitz.open(OUT + ".svg")
pdf = fitz.open("pdf", doc.convert_to_pdf())
pdf.save(OUT + ".pdf")
pdf[0].get_pixmap(dpi=150).save(OUT + ".png")
print("ok", OUT)
