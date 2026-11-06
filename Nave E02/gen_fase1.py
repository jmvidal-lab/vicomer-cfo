# Genera los planos de la Fase 1 de la Nave E02-1 (Vicomer): L-01..L-04 en A3.
# Coordenadas del modelo en metros: x a lo largo del frente (0 = cara exterior muro izquierdo, eje A),
# y hacia el fondo (0 = fachada frontal, eje 1), z = altura sobre NPT ±0.00.
# Uso: python3 gen_fase1.py
import os
import math
import textwrap
import fitz

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "Nave_E02_Fase1_planos_v12")

# ---------------- Datos de diseño ----------------
COL_X = [0.20 + 9.03 * i for i in range(5)]          # ejes A..E
COL_Y = [0.30 + 6.28 * i for i in range(6)]          # ejes 1..6
AX_C = COL_X[2]                                       # 18.26 eje de división
PART = (18.185, 18.335)                               # muro divisorio nuevo
EAVE, RIDGE = 6.00, 9.00
FRONT_DOOR = (13.40, 16.86)                           # puerta enrollable nueva alineada al pasillo P3 (mitad A)
FRONT_DOOR_B = (21.02, 24.52)                         # puerta existente 3.50 (mitad B)

# Racks: 6 filas x 5 vanos, pasillos 3.50
ROWS = [("R1", 0.48, 1.58), ("R2", 5.08, 6.18), ("R3", 6.38, 7.48),
        ("R4", 10.98, 12.08), ("R5", 12.28, 13.38), ("R6", 16.88, 17.98)]
AISLES = [("P1", 1.58, 5.08), ("P2", 7.48, 10.98), ("P3", 13.38, 16.88)]
RY0, NB, BAY, UPR = 0.90, 6, 3.30, 0.10                # vanos de 3.30 m: 3 pallets por nivel
RY1 = RY0 + NB * BAY + (NB + 1) * UPR                 # 21.40
ROW_NB = {"R6": 5}                                    # R6 corta: libera espacio para carga y control
PPL = 3                                               # pallets por nivel
BEAMS = [1.35, 2.79, 4.23]                            # cara inferior de vigas (vano normal)
TALL_BEAMS = [2.05, 4.25]                             # vano alto: refrigeradoras y equipos > 1.05 m
TALL = {("R1", k) for k in range(6)} | {("R6", k) for k in range(4)}
BEAM_H, LOAD_H, RACK_H = 0.14, 1.20, 5.00

# Mezanine
MZ = (0.45, 25.40, 18.05, 31.40)                      # x0, y0, x1, y1
MZ_FFL, MZ_BOT = 3.20, 2.85
MZ_COLX = [0.60, 4.92, 9.23, 13.55, 17.90]
MZ_COLY = [25.55, 31.25]
STAIR = (8.05, 26.55, 9.15, 31.31)            # recta, adosada al eje B (sube hacia el frente)

# Muelle
DOCK_DOOR = (22.00, 25.00)
WELL_T = 0.25
DOCK_LVL, MID_LVL, GRADE = -1.25, -0.95, -0.20

INK, GREY, RED, BLUE, ORANGE, GREEN = "#111", "#777", "#c0392b", "#1f5fa8", "#e67e22", "#2e8b57"


# ---------------- Utilidades de dibujo ----------------
class Doc:
    def __init__(self):
        self.o = ['<svg xmlns="http://www.w3.org/2000/svg" width="420mm" height="297mm" viewBox="0 0 420 297">',
                  '<rect width="420" height="297" fill="#fff"/>']

    def add(self, s):
        self.o.append(s)

    def line(self, x1, y1, x2, y2, w=0.25, c=INK, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="{c}" stroke-width="{w}"{d}/>')

    def rect(self, x, y, w, h, sw=0.2, fill="none", c=INK, dash=None):
        if w < 0:
            x, w = x + w, -w
        if h < 0:
            y, h = y + h, -h
        d = f' stroke-dasharray="{dash}"' if dash else ""
        st = f'stroke="{c}" stroke-width="{sw}"' if sw else 'stroke="none"'
        self.add(f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" fill="{fill}" {st}{d}/>')

    def poly(self, pts, sw=0.2, fill="none", c=INK, closed=True, dash=None):
        p = " ".join(f"{a:.2f},{b:.2f}" for a, b in pts)
        tag = "polygon" if closed else "polyline"
        d = f' stroke-dasharray="{dash}"' if dash else ""
        st = f'stroke="{c}" stroke-width="{sw}"' if sw else 'stroke="none"'
        self.add(f'<{tag} points="{p}" fill="{fill}" {st}{d}/>')

    def circle(self, x, y, r, sw=0.2, fill="none", c=INK):
        self.add(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r:.2f}" fill="{fill}" stroke="{c}" stroke-width="{sw}"/>')

    def path(self, d, sw=0.15, c=INK, fill="none"):
        self.add(f'<path d="{d}" fill="{fill}" stroke="{c}" stroke-width="{sw}"/>')

    def text(self, x, y, t, size=2.2, anchor="middle", weight="normal", rot=0, c=INK, italic=False):
        t = str(t).replace("&", "&amp;").replace("<", "&lt;")
        tr = f' transform="rotate({rot} {x:.2f} {y:.2f})"' if rot else ""
        it = ' font-style="italic"' if italic else ""
        self.add(f'<text x="{x:.2f}" y="{y:.2f}" font-family="Helvetica, Arial" font-size="{size}" '
                 f'text-anchor="{anchor}" font-weight="{weight}" fill="{c}"{it}{tr}>{t}</text>')

    def svg(self):
        return "\n".join(self.o + ["</svg>"])


class View:
    """Mapea coordenadas de modelo (m) a papel (mm). v vertical hacia arriba."""

    def __init__(self, d, S, ox, oy):
        self.d, self.S, self.ox, self.oy = d, S, ox, oy

    def X(self, x):
        return self.ox + x * self.S

    def Y(self, y):
        return self.oy - y * self.S

    def line(self, x1, y1, x2, y2, w=0.25, c=INK, dash=None):
        self.d.line(self.X(x1), self.Y(y1), self.X(x2), self.Y(y2), w, c, dash)

    def rect(self, x1, y1, x2, y2, sw=0.2, fill="none", c=INK, dash=None):
        self.d.rect(self.X(x1), self.Y(y2), (x2 - x1) * self.S, (y2 - y1) * self.S, sw, fill, c, dash)

    def poly(self, pts, sw=0.2, fill="none", c=INK, closed=True, dash=None):
        self.d.poly([(self.X(a), self.Y(b)) for a, b in pts], sw, fill, c, closed, dash)

    def text(self, x, y, t, size=2.2, anchor="middle", weight="normal", rot=0, c=INK, italic=False):
        self.d.text(self.X(x), self.Y(y), t, size, anchor, weight, rot, c, italic)

    def circle(self, x, y, r_mm, sw=0.2, fill="none", c=INK):
        self.d.circle(self.X(x), self.Y(y), r_mm, sw, fill, c)

    def hdim(self, x1, x2, y, label=None, size=1.8, c=INK):
        X1, X2, Yp = self.X(x1), self.X(x2), self.Y(y)
        self.d.line(X1, Yp, X2, Yp, 0.12, c)
        for x in (X1, X2):
            self.d.line(x - 0.7, Yp + 0.7, x + 0.7, Yp - 0.7, 0.18, c)
            self.d.line(x, Yp - 1.0, x, Yp + 1.0, 0.1, c)
        self.d.text((X1 + X2) / 2, Yp - 0.7, label if label is not None else f"{x2 - x1:.2f}", size, c=c)

    def vdim(self, y1, y2, x, label=None, size=1.8, c=INK):
        Xp, Y1, Y2 = self.X(x), self.Y(y1), self.Y(y2)
        self.d.line(Xp, Y1, Xp, Y2, 0.12, c)
        for y in (Y1, Y2):
            self.d.line(Xp - 0.7, y + 0.7, Xp + 0.7, y - 0.7, 0.18, c)
            self.d.line(Xp - 1.0, y, Xp + 1.0, y, 0.1, c)
        self.d.text(Xp - 0.7, (Y1 + Y2) / 2, label if label is not None else f"{abs(y2 - y1):.2f}", size, rot=-90, c=c)

    def arrow(self, pts, c=GREEN, w=0.5, dash=None, head=2.2):
        P = [(self.X(a), self.Y(b)) for a, b in pts]
        self.d.poly(P, w, "none", c, closed=False, dash=dash)
        (x1, y1), (x2, y2) = P[-2], P[-1]
        ang = math.atan2(y2 - y1, x2 - x1)
        a1, a2 = ang + math.radians(155), ang - math.radians(155)
        self.d.poly([(x2, y2), (x2 + head * math.cos(a1), y2 + head * math.sin(a1)),
                     (x2 + head * math.cos(a2), y2 + head * math.sin(a2))], 0, c, c)

    def level(self, x, z, label, size=1.8, left=False):
        X, Z = self.X(x), self.Y(z)
        self.d.poly([(X, Z), (X - 1.0, Z - 1.4), (X + 1.0, Z - 1.4)], 0.15, "#fff")
        self.d.line(X - 1.5, Z, X + (-8 if left else 8), Z, 0.12)
        self.d.text(X + (-1.5 if left else 1.5), Z - 2.0, label, size, "end" if left else "start")


def wrap(t, size, width_mm):
    n = max(10, int(width_mm / (size * 0.50)))
    return textwrap.wrap(t, n) or [""]


def title_block(d, code, title, rows, notes, scale, n, total):
    BX, BY, BW, BH = 318, 12, 92, 273
    d.rect(BX, BY, BW, BH, 0.35)
    d.text(BX + 4, BY + 8, "VICOMER S.A.S.", 4.4, "start", "bold")
    d.text(BX + 4, BY + 13, "Nave E02-1 · Conjunto Inmoservicios · Fase 1", 2.2, "start", c="#444")
    d.line(BX, BY + 16.5, BX + BW, BY + 16.5, 0.3)
    y = BY + 23
    for ln in wrap(title, 3.3, BW - 8):
        d.text(BX + 4, y, ln, 3.3, "start", "bold")
        y += 4.4
    y += 1.5
    d.line(BX, y - 2.5, BX + BW, y - 2.5, 0.15, "#999")
    for k, v in rows:
        if k == "§":
            y += 1.5
            d.text(BX + 4, y, v, 2.4, "start", "bold")
            y += 4.2
            continue
        d.text(BX + 4, y, k, 2.0, "start", "bold")
        lines = wrap(v, 2.0, BW - 42)
        for i, ln in enumerate(lines):
            d.text(BX + 38, y + i * 3.0, ln, 2.0, "start")
        y += 3.0 * len(lines) + 1.2
    y += 2
    d.text(BX + 4, y, "NOTAS", 2.5, "start", "bold")
    y += 4
    for i, nt in enumerate(notes, 1):
        for j, ln in enumerate(wrap(nt, 1.85, BW - 12)):
            d.text(BX + (4 if j == 0 else 8), y, (f"{i}. " if j == 0 else "") + ln, 1.85, "start")
            y += 2.7
        y += 0.6
    # cajetín inferior
    d.line(BX, 252, BX + BW, 252, 0.3)
    d.text(BX + 4, 258, "Escala: " + scale, 2.2, "start")
    d.text(BX + 4, 263, "Fecha: 30-oct-2026 · Versión v12 (anteproyecto)", 2.2, "start")
    d.text(BX + 4, 268, "Base: plano general Inmoservicios jul-2026", 2.0, "start", c="#555")
    d.text(BX + 4, 273, "Verificar todas las medidas en sitio", 2.0, "start", c="#555")
    d.rect(BX + 60, 254, 28, 27, 0.3)
    d.text(BX + 74, 266, code, 6, weight="bold")
    d.text(BX + 74, 275, f"Lámina {n}/{total}", 2.1)


def frame(d):
    d.rect(8, 8, 404, 281, 0.5)


def axis_bubbles(v, xs=True, ys=True, ytop=35.6, xside=21.6, xmax=20.5, ymin=-1.0):
    if xs:
        for i, x in enumerate(COL_X):
            if x > xmax:
                continue
            v.line(x, ymin, x, ytop - 0.6, 0.08, RED, "3 1 0.6 1")
            v.circle(x, ytop, 2.0, 0.2, "#fff", RED)
            v.text(x, ytop - 0.15, "ABCDE"[i], 2.2, c=RED)
    if ys:
        for j, y in enumerate(COL_Y):
            v.line(-0.8, y, xside - 0.5, y, 0.08, RED, "3 1 0.6 1")
            v.circle(xside, y, 2.0, 0.2, "#fff", RED)
            v.text(xside, y - 0.15, str(j + 1), 2.2, c=RED)


def shell_plan(v, ymin=0.0, ymax=32.0, xmax=20.5, glazing=True, dock_door=True, office_door=True):
    """Muros, columnas y fachada de la nave (mitad A + franja o totalidad de la mitad B)."""
    # muro izquierdo con vanos
    gaps = []
    if dock_door:
        gaps.append(DOCK_DOOR)
    if office_door:
        gaps.append((27.60, 29.40))
    segs, y0 = [], max(ymin, 0.0)
    for g0, g1 in sorted(gaps):
        if g1 <= y0 or g0 >= ymax:
            continue
        segs.append((y0, g0))
        y0 = g1
    segs.append((y0, ymax))
    for a, b in segs:
        if b > a:
            v.rect(0.0, a, 0.15, b, 0, "#333")
    full = xmax >= 36.5
    xe = 36.52 if full else xmax
    if full:
        v.rect(36.37, max(ymin, 0.0), 36.52, ymax, 0, "#333")
    # muro posterior
    if ymax >= 32.0:
        v.rect(0.0, 31.85, xe, 32.0, 0, "#333")
    # fachada frontal acristalada con las puertas existentes
    if glazing and ymin <= 0:
        v.rect(0.0, 0.0, xe, 0.10, 0.1, "#cfe3ee", "#333")
        for x0, x1 in [FRONT_DOOR, FRONT_DOOR_B]:
            if x1 > xe:
                continue
            v.rect(x0, 0.0, x1, 0.10, 0, "#fff")
            if (x0, x1) == FRONT_DOOR:
                v.line(x0, 0.05, x1, 0.05, 0.3, INK, "0.8 0.4")
                continue
            r = (x1 - x0) / 2
            for sx, sgn in ((x0, 1), (x1, -1)):
                v.line(sx, 0.05, sx, 0.05 + r, 0.15)
                v.poly([(sx, 0.05 + r)] + [(sx + sgn * r * math.sin(t), 0.05 + r * math.cos(t))
                                           for t in [i * math.pi / 2 / 12 for i in range(13)]], 0.1, closed=False)
    # muro divisorio (nuevo)
    v.rect(PART[0], max(ymin, 0.0), PART[1], min(ymax, 32.0), 0.12, "#7a7a7a", "#000")
    # columnas
    for x in COL_X:
        if x > xe + 0.1:
            continue
        for y in COL_Y:
            perim = x in (COL_X[0], COL_X[-1]) or y in (COL_Y[0], COL_Y[-1]) or x == AX_C
            if not perim or y < ymin - 0.4 or y > ymax + 0.4:
                continue
            v.rect(x - 0.20, y - 0.30, x + 0.20, y + 0.30, 0.15, "#9a9a9a")


def rack_plan(v, y_lo=RY0, y_hi=RY1, labels=True):
    for name, x0, x1 in ROWS:
        nb = ROW_NB.get(name, NB)
        ry1 = RY0 + nb * BAY + (nb + 1) * UPR
        v.rect(x0, RY0, x1, ry1, 0.18, "#dfeaf6", BLUE)
        for k in range(nb + 1):
            y = RY0 + k * (BAY + UPR)
            v.rect(x0, y, x1, y + UPR, 0, BLUE)
            if k < nb and (name, k) in TALL:
                v.rect(x0, y + UPR, x1, y + UPR + BAY, 0, "#f6dcb8")
            if k < nb:
                yb = y + UPR
                cl = (BAY - PPL * 1.0) / (PPL + 1)
                for p in range(PPL):
                    py0 = yb + cl + p * (1.0 + cl)
                    v.rect(x0 - 0.05, py0, x1 + 0.05, py0 + 1.0, 0.08, "none", "#6b8fb8", "0.6 0.4")
        # barreras de protección en cabeceras
        v.rect(x0 - 0.05, ry1 + 0.10, x1 + 0.05, ry1 + 0.25, 0, ORANGE)
        if labels:
            v.text((x0 + x1) / 2, RY1 + 0.75, name, 1.9, weight="bold", c=BLUE)


# ---------------- Utilidades de mezanine ----------------
def door_swing(v, x, y, w, orient, sw=0.12):
    """orient: 'up','down','left','right' = hacia donde abre; x,y = bisagra."""
    import math as m
    if orient in ("up", "down"):
        s = 1 if orient == "up" else -1
        v.line(x, y, x, y + s * w, sw)
        v.poly([(x + w * m.sin(t), y + s * w * m.cos(t)) for t in [i * m.pi / 24 for i in range(13)]],
               0.08, closed=False)
    else:
        s = 1 if orient == "right" else -1
        v.line(x, y, x + s * w, y, sw)
        v.poly([(x + s * w * m.cos(t), y + w * m.sin(t)) for t in [i * m.pi / 24 for i in range(13)]],
               0.08, closed=False)


def wall(v, x0, y0, x1, y1, fill="#444"):
    v.rect(x0, y0, x1, y1, 0, fill)


def glass(v, x0, y0, x1, y1):
    v.rect(x0, y0, x1, y1, 0.1, "#cfe3ee", "#333")


def window(v, x0, y0, x1, y1):
    v.rect(x0, y0, x1, y1, 0.1, "#cfe3ee", "#333")
    if x1 - x0 > y1 - y0:
        v.line(x0, (y0 + y1) / 2, x1, (y0 + y1) / 2, 0.08)
    else:
        v.line((x0 + x1) / 2, y0, (x0 + x1) / 2, y1, 0.08)


def mz_shell(v, upper=False):
    v.rect(0.0, 24.0, 18.6, 32.0, 0, "#fbfaf7")
    v.rect(MZ[0], MZ[1], MZ[2], MZ[3], 0, "#ffffff")
    shell_plan(v, ymin=24.0, ymax=32.0, xmax=18.9, glazing=False, dock_door=False, office_door=not upper)
    if not upper:
        for x in MZ_COLX:
            for y in MZ_COLY:
                v.rect(x - 0.075, y - 0.075, x + 0.075, y + 0.075, 0.1, "#333")


def stair_treads(v, labels=True, upper=False):
    x0, y0, x1, y1 = STAIR
    v.rect(x0, y0, x1, y1, 0.15, "#fff")
    n = 17
    for i in range(n + 1):
        y = y0 + i * (y1 - y0) / n
        v.line(x0, y, x1, y, 0.06 if not upper else 0.05, INK if not upper else "#999")
    if upper:
        v.arrow([((x0 + x1) / 2, y1 - 0.5), ((x0 + x1) / 2, y0 + 0.15)], INK, 0.2, None, 1.3)
    else:
        v.arrow([((x0 + x1) / 2, y1 - 0.15), ((x0 + x1) / 2, y0 + 0.4)], INK, 0.2, None, 1.3)


def mezz_ground_simple(v):
    """Mezanine planta baja simplificado para las plantas generales (1:200)."""
    v.rect(MZ[0], MZ[1], MZ[2], MZ[3], 0.35, "#efe6f5", "#7b4a9e")
    v.rect(9.18, MZ[1], 9.28, MZ[3], 0, "#7b4a9e")
    v.rect(MZ[0], MZ[1], 9.18, MZ[1] + 0.12, 0, "#7b4a9e")
    v.rect(*STAIR, 0.12, "#fff")
    for i in range(0, 18, 2):
        y = STAIR[1] + i * 0.28
        v.line(STAIR[0], y, STAIR[2], y, 0.05)
    v.text(4.1, 29.2, "SHOWROOM", 2.0, weight="bold", c="#5b2d7a")
    v.text(4.1, 28.3, "45.6 m²", 1.6, c="#5b2d7a")
    v.text(13.6, 28.8, "LABORATORIO / TALLER", 1.9, weight="bold", c="#2d4d6b")
    v.text(13.6, 27.9, "50.0 m²", 1.6, c="#2d4d6b")
    v.rect(16.30, 25.55, MZ[2], 27.05, 0.1, "#dde7ef")
    v.text(17.2, 26.2, "½ baño", 1.2)
    v.rect(16.55, MZ[1] - 0.05, 17.25, MZ[1] + 0.12, 0, "#fff")
    v.text(13.6, 30.7, "Oficinas en PA +3.20 (L-03)", 1.4, c="#5b2d7a")
    v.rect(10.6, MZ[1] - 0.05, 13.0, MZ[1] + 0.12, 0, "#fff")
    v.line(10.6, MZ[1], 13.0, MZ[1], 0.1, "#7b4a9e", "0.6 0.4")


# ---------------- Planta general (nave completa o mitad Vicomer) ----------------
def general_plan(full):
    d = Doc()
    frame(d)
    if full:
        v = View(d, 5.0, 85, 200)
        XL, XR = -12.0, 38.6
    else:
        v = View(d, 5.0, 167, 200)
        XL, XR = -27.0, 20.5
    # entorno
    v.rect(XL, -8, XR, -3.2, 0, "#e3e3e3")
    v.text((XL + XR) / 2, -6.0, "VÍA INTERNA DEL CONJUNTO (referencial — confirmar con levantamiento)", 2.2, c="#555")
    v.rect(XL, -3.2, XR, 0, 0, "#f1efe9")
    v.rect(XL, 0, 0, 34, 0, "#eef3e6")
    if not full:
        v.text(-18, 14.5, "PATIO LATERAL / ÁREA DE MANIOBRA", 2.6, weight="bold", c="#4d6b3a")
        v.text(-18, 12.6, "(verificar linderos y derecho de uso con Inmoservicios)", 1.9, c="#4d6b3a")
    px0 = -12.0 if not full else -11.8
    for i in range(4):
        y0 = 21.0 + i * 2.5
        v.rect(px0 - 5.0 if not full else -11.8, y0, px0 if not full else -6.9, y0 + 2.5, 0.15, "#fff", GREY)
        v.text((px0 - 2.5) if not full else -9.35, y0 + 1.0, f"P{i + 1}", 1.8, c=GREY)
    v.text(-14.5 if not full else -9.35, 32.3, "Parqueo (4 u.)", 1.8, c="#555")
    v.rect(-2.2, 27.3, -0.1, 30.8, 0.15, "#f6f6f6", GREY, "1 0.6")
    v.text(-1.15, 29.0, "marquesina", 1.4, rot=-90, c="#555")
    if not full:
        v.arrow([(-11.8, 28.5), (-2.4, 28.5)], "#555", 0.3, "1 0.7", 1.6)
        v.text(-7.0, 29.0, "acceso peatonal", 1.4, c="#555")
    # pisos
    v.rect(0, 0, PART[0], 32, 0, "#f6f3ec")
    if full:
        v.rect(PART[1], 0, 36.37, 32, 0, "#eaf1f7")
        cx = (PART[1] + 36.37) / 2
        v.text(cx, 21.5, "NAVE E02-1B", 4.0, weight="bold", c="#2d5a85")
        v.text(cx, 19.4, "DISPONIBLE PARA ALQUILER", 3.0, weight="bold", c="#2d5a85")
        v.text(cx, 17.2, "18.26 × 32.00 = 584.3 m² (a ejes)", 2.2, c="#2d5a85")
        v.text(cx, 15.6, "planta libre: sin columnas interiores", 2.0, c="#2d5a85")
        v.text(cx, 14.0, "altura libre 6.00 m bajo cercha · cumbrera 9.00 m", 2.0, c="#2d5a85")
        v.text(cx, 12.4, "acceso propio: puerta frontal existente 3.50 × 3.50", 2.0, c="#2d5a85")
        v.text(cx, 10.8, "medidores de luz y agua independientes (a instalar)", 2.0, c="#2d5a85")
        v.text(36.9, 16.0, "→ corredor de servicio y baños compartidos (existente)", 1.5, rot=-90, c="#555")
        v.arrow([((FRONT_DOOR_B[0] + FRONT_DOOR_B[1]) / 2, -2.8), ((FRONT_DOOR_B[0] + FRONT_DOOR_B[1]) / 2, 4.0)], "#2d5a85", 0.5, None, 1.8)
        v.text((FRONT_DOOR_B[0] + FRONT_DOOR_B[1]) / 2 + 0.6, 4.6, "ingreso arrendatario", 1.6, c="#2d5a85", anchor="start")
    else:
        v.rect(PART[1], 0, XR, 32, 0, "#e9e9e9")
        v.text(19.45, 16, "NAVE E02-1B — ALQUILER", 2.0, rot=-90, c="#666", weight="bold")
    # zonas de operación
    v.rect(0.40, 22.35, 4.6, 25.30, 0.25, "none", "#d4a017", "1.2 0.8")
    v.text(2.5, 24.0, "RECEPCIÓN", 1.5, weight="bold", c="#8a6a00")
    v.text(2.5, 23.3, "desde el andén", 1.3, c="#8a6a00")
    v.rect(5.15, 24.55, 7.40, 25.30, 0.15, "#e4f3e8", GREEN)
    v.text(6.27, 24.8, "empaque + balanza", 1.2, c="#1f6b40")
    r6y = RY0 + 5 * (BAY + UPR) + UPR
    v.rect(16.92, r6y, 17.96, r6y + 1.9, 0.15, "#fde8d0", ORANGE)
    v.text(17.44, r6y + 0.95, "carga montac.", 1.1, rot=-90, c="#a04c00")
    v.rect(16.92, r6y + 2.0, 17.96, RY1, 0.15, "#fff")
    v.text(17.44, r6y + 2.75, "control", 1.1, rot=-90)
    for a, b in ((0.4, FRONT_DOOR[0] - 0.2), (FRONT_DOOR[1] + 0.2, 18.0)):
        v.line(a, 0.55, b, 0.55, 0.45, ORANGE)
    v.text(0.6, 0.20, "baranda antichoque + lámina opaca en vidrio (racks a 0.90 de la fachada)", 1.3, c=ORANGE, anchor="start")
    v.text(15.13, -0.9, "puerta enrollable 3.50 (nueva, alineada a P3)", 1.3, c=BLUE)
    shell_plan(v, xmax=36.52 if full else XR)
    # muelle
    dock_geom(v)
    v.text(-10.6 if not full else -6.95, 10.0, "MUELLE LATERAL — calle deprimida paralela al muro",
           2.2 if not full else 1.8, weight="bold", rot=-90)
    if not full:
        v.text(-7.3, 2.0, "rampa 7.5 %", 1.5, rot=-90, c="#555")
        v.text(-7.3, 13.5, "zona camión 2 %", 1.5, rot=-90, c="#555")
        v.text(-6.9, 7.0, "-0.95", 1.5, anchor="end")
        v.text(-6.9, 19.6, "-1.25", 1.5, anchor="end")
        v.text(-7.6, 18.0, "marquesina", 1.4, rot=-90, c="#555")
    v.text(-4.0, 13.75, "CONTENEDOR 40' HC", 1.7, rot=-90, c="#444")
    v.text(-4.0, 4.4, "tracto", 1.5, rot=-90, c="#444")
    v.text(-0.75, 9.0, "franja 1.50 protección cimentación", 1.3, rot=-90, c="#555")
    v.text(-3.25, 24.6, "ANDÉN ±0.00", 1.8, weight="bold")
    v.text(0.6, 23.5, "puerta muelle 3.00×3.20", 1.3, anchor="start", rot=-90)
    v.text(-4.0, 22.8, "niveladora", 1.3)
    v.text(-4.4, -2.4, "-0.20", 1.5, anchor="end")
    v.arrow([(2, -5.0), (XL + 1.0, -5.0)], "#555", 0.35, None, 1.8)
    v.text(-5, -4.5, "1. avanza por la vía", 1.6, c="#555")
    v.arrow([(XL + 1.0, -4.4), (-9.0, -4.0), (-4.0, -2.5), (-4.0, 1.0)], RED, 0.35, "1.5 0.8", 1.8)
    v.text(XL + 1.2, -2.4, "2. retrocede a la calle", 1.6, c=RED, anchor="start")
    # racks
    rack_plan(v)
    for nm, a, b in AISLES:
        v.text((a + b) / 2, (RY0 + RY1) / 2, f"PASILLO {nm} · 3.50", 2.0, rot=-90, c="#555")
    v.text(11.0, 23.0, f"PASILLO TRASERO {MZ[1] - RY1:.2f} — recepción, despacho y peatonal", 1.5, c="#555")
    mezz_ground_simple(v)
    # flujos
    v.arrow([(-4.0, 21.3), (-4.0, 22.6), (3.3, 22.6), (3.3, 13.0)], GREEN, 0.6, None, 2.0)
    v.arrow([(15.13, 12.0), (15.13, -1.6)], BLUE, 0.6, None, 2.0)
    v.text(3.9, 15.5, "ENTRADA", 1.8, c=GREEN, weight="bold", anchor="start")
    v.text(15.13, -2.5, "SALIDA / despacho", 1.7, c=BLUE, weight="bold")
    # cotas
    if full:
        v.hdim(0.0, AX_C, 33.0, "18.26 E02-1A Vicomer", 1.7)
        v.hdim(AX_C, 36.52, 33.0, "18.26 E02-1B alquiler", 1.7)
        v.hdim(0.0, 36.52, 34.4, "36.52", 1.8)
        v.vdim(0.0, 32.0, 37.9, "32.00", 1.7)
        axis_bubbles(v, ytop=36.6, xside=39.6, xmax=36.6)
    else:
        chain = [0.0, 0.48, 1.58, 5.08, 7.48, 10.98, 13.38, 16.88, 17.98, PART[0]]
        for a, b in zip(chain, chain[1:]):
            v.hdim(a, b, 33.0, f"{b - a:.2f}", 1.5)
        v.hdim(0.0, AX_C, 34.2, "18.26 (a eje C)", 1.7)
        ych = [0.0, RY0, RY1, MZ[1], MZ[3], 32.0]
        for a, b in zip(ych, ych[1:]):
            v.vdim(a, b, 20.2, f"{b - a:.2f}", 1.5)
        v.vdim(-3.0, 7.0, -9.0, "10.00", 1.5)
        v.vdim(7.0, 20.0, -9.0, "13.00", 1.5)
        v.vdim(20.0, 26.0, -9.0, "6.00", 1.5)
        v.hdim(-6.25, -1.75, 26.8, "4.50", 1.4)
        v.hdim(-1.5, 0.0, 26.8, "1.50", 1.3)
        axis_bubbles(v, ytop=35.6, xside=22.2)
    # leyenda
    lx, ly = 32, 247
    d.text(lx, ly, "PLANTA GENERAL — NAVE COMPLETA E02-1" if full else "PLANTA DE DISTRIBUCIÓN — E02-1A VICOMER (FASE 1)",
           3.4, "start", "bold")
    d.text(lx + 175, ly, "ESC. 1:200", 2.6, "start")
    items = [("#dfeaf6", BLUE, "Racks selectivos (35 vanos de 3.30 m)"), ("#f6dcb8", BLUE, "Vano alto (refrigeradoras / equipos > 1.05 m)"), ("#fff4d6", "#d4a017", "Zona de recepción"),
             ("#e4f3e8", GREEN, "Zona de despacho"), ("#efe6f5", "#7b4a9e", "Mezanine (2 niveles)"),
             ("#d3c9b2", "#555", "Calle deprimida del muelle"), ("#7a7a7a", "#000", "Muro divisorio nuevo"),
             (ORANGE, ORANGE, "Protecciones (barreras / baranda)")]
    if full:
        items.append(("#eaf1f7", "#2d5a85", "E02-1B disponible para alquiler"))
    for i, (f, c, t) in enumerate(items):
        xx, yy = lx + (i % 4) * 66, ly + 6 + (i // 4) * 6
        d.rect(xx, yy - 2.6, 5, 3, 0.2, f, c)
        d.text(xx + 7, yy, t, 2.0, "start")
    d.line(lx, ly + 19.6, lx + 8, ly + 19.6, 0.6, GREEN)
    d.text(lx + 10, ly + 20.3, "flujo entrada", 2.0, "start")
    d.line(lx + 40, ly + 19.6, lx + 48, ly + 19.6, 0.6, BLUE)
    d.text(lx + 50, ly + 20.3, "flujo salida", 2.0, "start")
    d.text(lx, ly + 26, "Flujo pasante: recepción por el andén lateral al fondo (junto al showroom) → almacenaje → despacho por el "
           "pasillo P3 y la puerta enrollable frontal. Los demás pasillos terminan en la fachada (sin pasillo frontal).", 1.9, "start", c="#333")
    d.text(lx, ly + 30, "Pallet de diseño 1.00 × 1.20 m, carga ≤ 1.20 m de alto y ≤ 800 kg. "
           "Vanos de 3.30 m, 3 pallets por nivel (≤ 800 kg c/u). Capacidad: 25 vanos normales × 12 + 10 altos × 9 = 390 posiciones (60 altas).", 1.9, "start", c="#333")
    if full:
        title_block(d, "L-01", "Planta general — nave completa: E02-1A Vicomer + E02-1B en alquiler", [
            ("§", "CUADRO DE ÁREAS"),
            ("Nave E02-1", "36.52 × 32.00 = 1,168.6 m²"),
            ("E02-1A", "Vicomer · 584.3 m² + mezanine 105.6 m²"),
            ("E02-1B", "Alquiler · 584.3 m² · planta libre"),
            ("Muelle", "Exclusivo de E02-1A (costado izquierdo)"),
            ("§", "CONDICIONES PARA ALQUILAR E02-1B"),
            ("Acceso", "Puerta frontal existente 3.50 × 3.50, independiente de Vicomer"),
            ("Servicios", "Medidores propios; baños en el corredor de servicio compartido"),
            ("Separación", "Muro cortafuego (RF-60) hasta la cubierta en el eje C"),
        ], [
            "Muro divisorio sobre las columnas del eje C: bloque hasta +3.00 y panel metálico hasta la cubierta, "
            "sellado bajo la cumbrera. Así cada lado queda independiente en seguridad, polvo e incendio.",
            "Instalar medidores de energía y agua independientes antes de alquilar; definir en el contrato el uso de la vía interna y del corredor de baños.",
            "La mitad B queda vacía y libre de columnas (6.00 m libres): sirve para bodega, distribución o taller liviano.",
            "Detalle de la mitad Vicomer en L-02; mezanine en L-03; muelle en L-04; cortes en L-05.",
        ], "1:200", 1, 5)
    else:
        title_block(d, "L-02", "Distribución E02-1A Vicomer — bodega, muelle y mezanine", [
            ("§", "CUADRO DE ÁREAS"),
            ("Nave E02-1A", "18.26 × 32.00 = 584.3 m² (a eje C)"),
            ("Bodega libre", "≈ 438 m²"),
            ("Racks", "6 filas · 35 vanos de 3.30 m (10 altos) · 140 m² de huella"),
            ("Recepción", "Andén cubierto 39 m² + pasillo trasero 4.00"),
            ("Despacho", "Por P3 y puerta enrollable frontal; staging en pasillo trasero"),
            ("Mezanine PB", "Showroom 45.6 · Laboratorio 50.0 · ½ baño 2.6 m²"),
            ("Mezanine PA", "Oficinas 105.6 m² (+3.20)"),
            ("§", "CAPACIDAD"),
            ("Posiciones", "390 pallets: 330 normales + 60 altas"),
            ("Muelle", "Calle deprimida paralela al muro + andén · 1 contenedor 20'/40'/40'HC"),
            ("Montacargas", "Eléctrico contrabalanceado 3 ruedas, 1.6–2.0 t, mástil triple ≥ 4.50 m"),
        ], [
            "Los racks cotizados (H 7.05 m) no entran: la cercha está a +6.00. Se proponen bastidores H 5.00 m (ver L-05).",
            "Pasillos de 3.50 m para montacargas contrabalanceado de 3 ruedas; con apilador retráctil (reach) bajarían a 2.80 m.",
            "Anclar los racks solo al piso. Antes de anclar, verificar el espesor y la resistencia de la losa (≥ 15 cm, f'c ≥ 280).",
            "El showroom no tiene paso a la bodega: muro ciego. La bodega se comunica solo con el laboratorio.",
            "Iluminación LED sobre los pasillos y extintores PQS cada 15 m.",
        ], "1:200", 2, 5)
    return d


def sheet_complete():
    return general_plan(True)


def sheet_vicomer():
    return general_plan(False)


# ---------------- Mezanine: plantas ----------------
def sheet_mezz():
    d = Doc()
    frame(d)
    # ======== PLANTA BAJA ========
    v = View(d, 10.0, 35, 351)
    mz_shell(v)
    v.text(4.3, 24.6, "pasillo trasero — recepción desde el andén", 1.6, c="#8a6a00")
    v.text(13.5, 24.6, "pasillo transversal de bodega", 1.8, c="#777")
    # frente hacia bodega: showroom ciego, lab con portón
    wall(v, MZ[0], 25.40, 9.28, 25.55)
    wall(v, 9.28, 25.40, 10.6, 25.55)
    wall(v, 13.0, 25.40, MZ[2], 25.55)
    v.rect(10.6, 25.40, 13.0, 25.55, 0.1, "#fff", "#333", "0.5 0.4")
    v.text(11.8, 25.0, "portón corredizo 2.40 × 2.40 (paso de equipos)", 1.5)
    # tabique eje B con puerta de servicio bajo el descanso superior
    wall(v, 9.18, 25.55, 9.28, 25.65)
    wall(v, 9.18, 26.55, 9.28, MZ[3])
    door_swing(v, 9.28, 25.65, 0.9, "right")
    v.text(10.0, 26.95, "puerta servicio", 1.2)
    v.text(10.0, 26.70, "(control de acceso)", 1.2)
    # escalera recta adosada al tabique del eje B
    stair_treads(v)
    wall(v, 7.95, 28.20, 8.05, 28.60)
    v.text(8.6, 31.0, "SUBE", 1.5, weight="bold")
    v.text(8.6, 27.4, "depósito", 1.2, rot=-90)
    wall(v, 7.95, 26.55, 8.05, 27.4)
    door_swing(v, 8.0, 27.45, 0.75, "up")
    # ---- SHOWROOM ----
    v.rect(0.7, 25.75, 7.4, 26.35, 0.12, "#ece4f2", "#7b4a9e")
    for i in range(5):
        v.line(0.7 + i * 1.34, 25.75, 0.7 + i * 1.34, 26.35, 0.06, "#7b4a9e")
    v.text(4.05, 25.95, "góndola mural de exhibición (5 módulos) — muro ciego hacia la bodega", 1.25, c="#5b2d7a")
    for (a, b) in ((2.3, 3.9), (4.8, 6.4)):
        v.rect(a, 26.85, b, 27.95, 0.15, "#e2d3ee", "#7b4a9e")
        v.circle((a + b) / 2, 27.4, 3.0, 0.1, "#fff", "#7b4a9e")
    v.text(3.1, 27.4, "", 1)
    v.text(4.35, 26.6, "2 tarimas iluminadas para equipos estrella", 1.3, c="#5b2d7a")
    v.rect(3.2, 31.05, 6.9, 31.35, 0.12, "#5b2d7a", "#5b2d7a")
    v.text(5.05, 30.7, "MURO DE MARCA retroiluminado + exhibición", 1.3, c="#5b2d7a", weight="bold")
    v.poly([(0.7, 30.0), (2.7, 30.0), (2.7, 30.6), (1.3, 30.6), (1.3, 31.3), (0.7, 31.3)], 0.12, "#efe7da", "#8a6a3a")
    v.text(1.75, 29.7, "counter atención", 1.3)
    v.rect(0.15, 31.05, 0.5, 31.4, 0.1, "#bbb")
    v.text(0.62, 31.2, "ducto", 1.0, anchor="start")
    v.circle(5.5, 29.6, 5.0, 0.12, "#efe7da", "#8a6a3a")
    for ang in (90, 210, 330):
        v.circle(5.5 + 0.8 * math.cos(math.radians(ang)), 29.6 + 0.8 * math.sin(math.radians(ang)), 2.0, 0.1)
    v.text(5.5, 28.75, "mesa de asesoría", 1.3)
    v.rect(MZ[0] + 0.02, 27.6, 0.2, 29.4, 0, "#fff")
    door_swing(v, 0.12, 27.6, 0.9, "right")
    v.line(0.12, 29.4, 1.02, 29.4, 0.12)
    v.poly([(0.12 + 0.9 * math.cos(t), 29.4 - 0.9 * math.sin(t)) for t in [i * math.pi / 24 for i in range(13)]],
           0.08, closed=False)
    v.text(7.45, 30.0, "arranque", 1.1)
    v.line(0.12, 28.5, 0.12, 29.4, 0.0)
    v.text(-0.9, 28.5, "INGRESO CLIENTES", 1.6, rot=-90, weight="bold")
    v.arrow([(-1.6, 28.5), (0.9, 28.5), (7.6, 28.5), (7.6, 30.9)], "#7b4a9e", 0.25, "1 0.6", 1.4)
    v.text(4.1, 28.15, "SHOWROOM", 2.6, weight="bold", c="#5b2d7a")
    v.text(1.2, 28.15, "", 1)
    # ---- LABORATORIO / TALLER ----
    v.rect(10.4, 25.75, 13.2, 27.6, 0.12, "#fff7e0", "#d4a017", "0.8 0.5")
    v.text(11.8, 27.15, "INGRESO / EGRESO", 1.4, weight="bold", c="#8a6a00")
    v.text(11.8, 26.75, "equipos en espera", 1.3, c="#8a6a00")
    v.text(11.8, 26.4, "(señalización de piso)", 1.2, c="#8a6a00")
    v.rect(17.35, 27.2, 18.0, 31.25, 0.12, "#e8eef3", "#406080")
    for yy in (28.55, 29.9):
        v.line(17.35, yy, 18.0, yy, 0.12, "#406080")
    v.rect(16.85, 27.2, 17.25, 31.25, 0.1, "#ddd", "#888", "0.4 0.3")
    v.text(17.7, 29.2, "BANCO DE PRUEBAS · 3 puestos: agua, desagüe, 110/220 V", 1.2,
           rot=-90, c="#2d4d6b")
    v.text(17.05, 29.2, "rejilla de piso", 1.1, rot=-90, c="#555")
    # medio baño para personal de bodega (acceso directo desde la bodega)
    wall(v, 16.30, 25.55, 16.40, 27.05)
    wall(v, 16.30, 26.95, MZ[2], 27.05)
    v.rect(16.55, 25.40, 17.25, 25.55, 0, "#fff")
    door_swing(v, 16.55, 25.48, 0.7, "up")
    v.rect(17.45, 26.05, 17.95, 26.55, 0.1, "#fff")
    v.rect(16.5, 26.45, 16.95, 26.85, 0.1, "#fff")
    v.text(17.2, 26.75, "½ BAÑO", 1.2, weight="bold")
    v.text(16.9, 25.0, "acceso desde bodega", 1.2)
    for (a, b) in ((10.9, 13.3), (13.6, 16.0)):
        v.rect(a, 30.7, b, 31.35, 0.12, "#e8eef3", "#406080")
        v.rect(a, 31.30, b, 31.4, 0, "#406080")
        v.circle((a + b) / 2, 30.25, 2.2, 0.1)
    v.text(13.45, 31.0, "2 estaciones de reparación ESD + tablero de herramientas", 1.2, c="#2d4d6b")
    v.rect(9.35, 27.4, 9.85, 30.4, 0.12, "#e8eef3", "#406080")
    v.line(9.35, 28.9, 9.85, 28.9, 0.1, "#406080")
    v.text(10.1, 28.9, "repuestos 2 × 1.50", 1.2, rot=-90, c="#2d4d6b")
    v.rect(13.5, 25.75, 15.7, 26.45, 0.12, "#efe7da", "#8a6a3a")
    v.circle(14.6, 26.9, 2.2, 0.1)
    v.text(14.6, 26.0, "puesto diagnóstico / PC", 1.2)
    v.rect(12.6, 28.4, 14.6, 29.3, 0.12, "#fff", "#406080")
    v.text(13.6, 28.75, "mesa de desarme rodable", 1.2)
    v.rect(15.75, 25.6, 16.25, 25.75, 0, "#c0392b")
    v.text(16.45, 30.0, "", 1)
    v.text(13.5, 29.5, "LABORATORIO DE PRUEBAS Y TALLER TÉCNICO", 1.7, weight="bold", c="#2d4d6b")
    v.text(13.5, 29.75 + 0.0, "", 1)
    v.text(16.0, 25.95, "tablero", 1.0, c="#c0392b")
    v.text(11.8, 28.0, "50.0 m² · h libre 2.85", 1.3, c="#2d4d6b")
    v.text(13.5, 29.65 - 0.95 + 0.0, "", 1)
    v.text(11.2, 29.55 - 1.2, "", 1)
    # cotas PB
    for a, b in ((MZ[0], 8.05), (8.05, 9.18), (9.28, MZ[2])):
        v.hdim(a, b, 32.6, f"{b - a:.2f}", 1.5)
    v.hdim(MZ[0], MZ[2], 33.4, "17.60 (plataforma)", 1.7)
    v.vdim(MZ[1], MZ[3], 18.9, "6.00", 1.7)
    v.vdim(27.6, 29.4, -1.7, "1.80", 1.4)
    d.text(35, 117, "PLANTA BAJA MEZANINE — Showroom · Laboratorio de pruebas y taller técnico", 3.0, "start", "bold")
    d.text(225, 117, "ESC. 1:100", 2.4, "end")

    # ======== PLANTA ALTA ========
    v = View(d, 10.0, 35, 466)
    mz_shell(v, upper=True)
    v.text(9.2, 24.6, "VACÍO SOBRE BODEGA — fachada interior de vidrio templado", 1.8, c="#777")
    glass(v, MZ[0], 25.40, MZ[2], 25.50)
    # ventanas exteriores nuevas
    window(v, 0.02, 25.9, 0.13, 28.4)
    window(v, 0.02, 30.0, 0.13, 31.0)
    window(v, 2.6, 31.87, 5.6, 31.98)
    window(v, 6.3, 31.87, 7.7, 31.98)
    window(v, 9.8, 31.87, 13.0, 31.98)
    window(v, 16.2, 31.87, 17.6, 31.98)
    # tabiques
    wall(v, 3.45, 25.50, 3.55, 28.90)
    wall(v, MZ[0], 28.80, 6.00, 28.90)
    wall(v, 5.90, 28.90, 6.00, 31.40)
    wall(v, 1.95, 28.90, 2.05, 31.40)
    wall(v, 7.95, 26.55, 8.05, 31.40)
    wall(v, 9.15, 26.55, 9.25, 31.40)
    glass(v, 9.25, 28.80, 14.90, 28.90)
    wall(v, 14.80, 28.90, 14.90, 31.40)
    wall(v, 15.90, 28.80, MZ[2], 28.90)
    wall(v, 15.90, 28.90, 16.00, 31.40)
    wall(v, 16.00, 30.10, MZ[2], 30.20)
    # escalera (vacío)
    stair_treads(v, upper=True)
    v.text(8.6, 26.0, "LLEGA", 1.4, weight="bold")
    v.line(8.05, 26.55, 9.15, 26.55, 0.35, ORANGE)
    # puertas
    v.rect(3.44, 26.75, 3.56, 27.65, 0, "#fff")
    door_swing(v, 3.5, 26.75, 0.9, "left")
    v.rect(0.6, 28.79, 1.35, 28.91, 0, "#fff")
    door_swing(v, 0.6, 28.85, 0.75, "up")
    v.rect(3.58, 28.79, 4.33, 28.91, 0, "#fff")
    door_swing(v, 3.58, 28.85, 0.75, "down")
    # la cafetería se abre desde el pasillo de servicio; los SS.HH. también, nunca hacia la cafetería
    v.rect(14.79, 29.2, 14.91, 30.05, 0, "#fff")
    door_swing(v, 14.85, 29.2, 0.85, "left")
    for y in (29.0, 30.3):
        v.rect(15.89, y, 16.01, y + 0.75, 0, "#fff")
        door_swing(v, 15.95, y, 0.75, "right")
    # gerencia (adelante, vista a la bodega)
    v.rect(0.9, 26.55, 2.7, 27.3, 0.12, "#efe7da", "#8a6a3a")
    v.circle(1.8, 27.7, 2.4, 0.1)
    v.circle(1.4, 26.15, 1.8, 0.1)
    v.circle(2.2, 26.15, 1.8, 0.1)
    v.text(1.95, 28.4, "GERENCIA · 9.9 m²", 1.4, weight="bold", c="#6b4a1a")
    v.text(3.0, 25.75, "vidrio a la bodega", 1.0, c="#6b4a1a")
    # baño de gerencia (compacto, con ducha)
    v.rect(0.5, 30.55, 1.3, 31.35, 0.12, "#dde7ef", "#406080")
    v.line(0.5, 30.55, 1.3, 31.35, 0.08, "#406080")
    v.line(0.5, 31.35, 1.3, 30.55, 0.08, "#406080")
    v.rect(1.4, 30.8, 1.9, 31.35, 0.1, "#fff")
    v.rect(1.45, 29.5, 1.9, 29.95, 0.1, "#fff")
    v.text(1.2, 30.2, "BAÑO GER.", 1.1, weight="bold")
    v.text(0.9, 29.85, "ducha", 1.0)
    # sala de reuniones (8 pers.)
    v.rect(3.0, 29.6, 5.0, 30.5, 0.12, "#efe7da", "#8a6a3a")
    for cx in (3.35, 4.0, 4.65):
        v.circle(cx, 29.25, 1.7, 0.1)
        v.circle(cx, 30.85, 1.7, 0.1)
    v.circle(2.6, 30.05, 1.7, 0.1)
    v.circle(5.4, 30.05, 1.7, 0.1)
    v.rect(5.8, 29.4, 5.9, 30.7, 0, INK)
    v.text(3.95, 31.15, "SALA DE REUNIONES · 8 pers. · 9.6 m²", 1.2, weight="bold", c="#6b4a1a")

    # coworking: puestos de 1.40 × 0.70 en islas paralelas al vidrio, con paso de 0.79 m junto a la fachada
    def desk_island(x0, nx, y0=26.85, dep=1.4, w=1.4):
        v.rect(x0, y0, x0 + nx * w, y0 + dep, 0.12, "#efe7da", "#8a6a3a")
        v.line(x0, y0 + dep / 2, x0 + nx * w, y0 + dep / 2, 0.15, "#8a6a3a")
        for i in range(nx):
            v.line(x0 + i * w, y0, x0 + i * w, y0 + dep, 0.08, "#8a6a3a")
            v.circle(x0 + w / 2 + i * w, y0 - 0.35, 2.1, 0.1)
            v.circle(x0 + w / 2 + i * w, y0 + dep + 0.3, 2.1, 0.1)
    desk_island(4.35, 2)
    desk_island(9.4, 4)
    desk_island(16.0, 1)
    v.rect(7.25, 29.3, 7.95, 30.7, 0.12, "#efe7da", "#8a6a3a")
    v.circle(6.9, 30.0, 2.1, 0.1)
    v.text(6.45, 30.0, "1 puesto", 1.1, rot=-90, c="#6b4a1a")
    v.text(5.75, 25.72, "COWORKING A — 5 puestos", 1.3, weight="bold", c="#6b4a1a")
    v.text(13.65, 25.8, "COWORKING B — 10 puestos, frente al vidrio de la bodega", 1.3, weight="bold", c="#6b4a1a")
    # cafetería al fondo, con ventanas al exterior
    v.rect(10.1, 29.6, 12.5, 30.5, 0.12, "#efe7da", "#8a6a3a")
    for cx in (10.5, 11.3, 12.1):
        v.circle(cx, 29.25, 1.7, 0.1)
        v.circle(cx, 30.85, 1.7, 0.1)
    v.circle(9.7, 30.05, 1.7, 0.1)
    v.circle(12.9, 30.05, 1.7, 0.1)
    v.rect(13.1, 30.8, 14.2, 31.4, 0.12, "#efe7da", "#8a6a3a")
    v.rect(13.4, 30.9, 13.9, 31.3, 0.1, "#fff")
    v.rect(14.22, 30.8, 14.8, 31.4, 0.1, "#ddd")
    v.text(13.95, 30.5, "kitchenette + refri", 1.1)
    v.text(11.4, 31.15, "CAFETERÍA · 8 pers. · 14.1 m² · ventanas al exterior", 1.2, weight="bold", c="#6b4a1a")
    # pasillo de servicio y SS.HH.
    v.text(15.4, 29.9, "pasillo", 1.0, rot=-90)
    v.rect(14.95, 30.85, 15.85, 31.35, 0.12, "#ddd")
    v.text(15.4, 31.1, "impresora", 1.0)
    for (y0, y1, nm) in ((28.90, 30.10, "SS.HH. 1"), (30.20, 31.4, "SS.HH. 2")):
        cy = (y0 + y1) / 2
        v.rect(17.45, cy - 0.2, 18.0, cy + 0.2, 0.1, "#fff")
        v.rect(16.9, y1 - 0.45, 17.35, y1 - 0.05, 0.1, "#fff")
        v.text(17.0, cy + 0.15, nm, 1.1, weight="bold")
    # cotas PA
    for a, b in ((MZ[0], 3.45), (3.55, 7.95), (7.95, 9.25), (9.25, 14.80), (14.90, 15.90), (16.00, MZ[2])):
        v.hdim(a, b, 32.6, f"{b - a:.2f}", 1.5)
    v.hdim(MZ[0], MZ[2], 33.4, "17.60 (plataforma)", 1.7)
    for a, b in ((MZ[1], 28.80), (28.90, MZ[3])):
        v.vdim(a, b, -0.8, f"{b - a:.2f}", 1.3)
    d.text(35, 232, "PLANTA ALTA MEZANINE (+3.20) — Oficinas administrativas", 3.0, "start", "bold")
    d.text(225, 232, "ESC. 1:100", 2.4, "end")

    # cuadro de ambientes
    tx, ty = 240, 30
    d.text(tx, ty, "CUADRO DE AMBIENTES", 2.8, "start", "bold")
    rows = [("PLANTA BAJA", None), ("Showroom", "45.6"), ("Escalera + depósito bajo escalera", "6.6"),
            ("Laboratorio de pruebas / taller", "50.0"),
            ("½ baño personal de bodega", "2.6"),
            ("PLANTA ALTA", None), ("Coworking A + B (15 puestos)", "48.4"),
            ("Gerencia (vista a la bodega)", "9.9"), ("Baño gerencia con ducha", "3.8"),
            ("Sala de reuniones (8 pers.)", "9.6"),
            ("Cafetería (8 pers.)", "14.1"), ("SS.HH. 1 y 2 + pasillo", "7.6"), ("Escalera (vacío)", "5.3"),
            ("Puestos de trabajo arriba", "16 (15 cowork + gerencia) + sala 8")]
    y = ty + 6
    for k, val in rows:
        if val is None:
            y += 1.5
            d.text(tx, y, k, 2.1, "start", "bold", c="#5b2d7a")
        else:
            d.text(tx + 2, y, k, 1.9, "start")
            d.text(tx + 68, y, val + (" m²" if val[0].isdigit() and "(" not in val else ""), 1.9, "end")
            d.line(tx, y + 1.0, tx + 68, y + 1.0, 0.06, "#bbb")
        y += 3.8
    y += 4
    d.text(tx, y, "CRITERIOS DE DISEÑO", 2.8, "start", "bold")
    y += 5
    for t in ["Escalera recta de un tramo (18 contrahuellas de 17.8 cm, huella 28 cm, ancho 1.10) adosada al tabique "
              "del eje B: no corta el showroom y llega al centro de la planta alta, sin hall.",
              "Showroom con muro ciego hacia la bodega: góndola mural, 2 tarimas para equipos estrella, muro de marca "
              "retroiluminado, counter y mesa de asesoría. Recorrido del cliente: ingreso → productos → escalera.",
              "Laboratorio por zonas: ingreso/egreso de equipos junto al portón, banco de pruebas con agua y desagüe "
              "sobre rejilla, 2 estaciones de reparación ESD, repuestos y puesto de diagnóstico.",
              "SS.HH. contra el muro divisorio, sobre el banco de pruebas, con una bajante común. La cocina queda a pocos metros, también sobre el laboratorio.",
              "Gerencia (9.9 m²) adelante, con vidrio hacia la bodega y ventana al patio; baño privado compacto "
              "con ducha detrás. Sala de reuniones para 8 al fondo, con ventana.",
              "15 puestos amplios de 1.40 × 0.70 (islas de 4, 8 y 2 + un puesto en el rincón), frente al vidrio de la "
              "bodega. Cafetería al fondo con ventanas exteriores; los SS.HH. abren a un pasillo, no a la cafetería."]:
        for j, ln in enumerate(wrap(t, 1.8, 68)):
            d.text(tx + (0 if j == 0 else 2.5), y, ("• " if j == 0 else "") + ln, 1.8, "start")
            y += 2.7
        y += 0.8
    title_block(d, "L-03", "Mezanine — planta baja (showroom, laboratorio) y planta alta (oficinas)", [
        ("Plataforma", "17.60 × 6.00 m = 105.6 m², estructura metálica independiente"),
        ("Niveles", "PB ±0.00 · PA +3.20 · bajo viga +2.85 · cielo raso PA +5.90"),
        ("Columnas", "10 tubos 150×150 solo en PB (5 frente + 5 fondo); planta alta libre"),
        ("Carga viva", "500 kg/m² (oficinas + archivo + tabiquería liviana)"),
        ("Escalera", "Recta 1.10 m, 18 contrahuellas, adosada al eje B"),
        ("Tabiques", "Gypsum acústico; vidrio templado hacia la bodega; SS.HH. en fibrocemento"),
    ], [
        "Medio baño en planta baja con puerta directa a la bodega: el personal de bodega no cruza el laboratorio ni el "
        "showroom. Comparte la bajante con el banco de pruebas, la cocina y los SS.HH. de arriba.",
        "Baño de gerencia: bajante propia en la esquina posterior izquierda (ducto oculto en el showroom) y "
        "calentador eléctrico para la ducha. Ventanas nuevas: confirmar con Inmoservicios.",
        "Climatización split en gerencia, reuniones y coworking; extracción mecánica en SS.HH., cocina y laboratorio.",
        "Laboratorio: tablero eléctrico propio, tomas industriales, iluminación de 500 lux y extintor CO2.",
    ], "1:100", 3, 5)
    return d


# ---------------- Muelle lateral paralelo al muro (geometría compartida) ----------------
LANE = (-6.25, -1.75)            # ancho libre de la calle deprimida (x)
LANE_Y = (-3.0, 7.0, 20.0)       # inicio en la vía, fin de rampa, cara del muelle (y)
ANDEN = (-6.5, 20.0, 0.0, 26.0)  # andén a ±0.00
LEV2 = (-5.0, 20.0, -3.0, 22.5)  # niveladora en el andén
CANOPY = (-7.0, 16.0, 0.0, 26.0)


def ground_z(y):
    y0, y1, y2 = LANE_Y
    if y <= y0:
        return GRADE
    if y <= y1:
        return GRADE + (MID_LVL - GRADE) * (y - y0) / (y1 - y0)
    return MID_LVL + (DOCK_LVL - MID_LVL) * (min(y, y2) - y1) / (y2 - y1)


class Swap:
    """Dibuja geometría de planta (x, y) en una vista girada: horizontal = y, vertical = x."""

    def __init__(self, v):
        self.v = v

    def rect(self, x1, y1, x2, y2, *a, **k):
        self.v.rect(y1, x1, y2, x2, *a, **k)

    def line(self, x1, y1, x2, y2, *a, **k):
        self.v.line(y1, x1, y2, x2, *a, **k)


def dock_geom(g):
    xa, xb = LANE
    y0, y1, y2 = LANE_Y
    g.rect(-1.5, y0, 0.0, y2, 0, "#e8e4da")
    g.rect(xa - WELL_T, y0, xa, y2, 0, "#555")
    g.rect(xb, y0, xb + WELL_T, y2, 0, "#555")
    g.rect(xa, y0, xb, y1, 0.1, "#e4ddcc")
    for yy in range(int(y0) + 1, int(y1)):
        g.line(xa, yy, xb, yy, 0.06, "#a99c7c")
    g.rect(xa, y1, xb, y2, 0.1, "#d3c9b2")
    g.rect(xa, 19.1, xb, 19.4, 0.1, "#999")
    g.rect(xa, 18.5, xa + 0.6, 19.1, 0.15, "#bbb")
    for i in range(6):
        g.line(xb - 0.8, 16.6 + i * 0.28, xb, 16.6 + i * 0.28, 0.1)
    for xx in (-5.5, -2.5):
        g.line(xx, 15.5, xx, 19.7, 0.3, "#d4a017")
    g.rect(*ANDEN, 0.2, "#f3efe6")
    g.rect(*LEV2, 0.2, "#fff")
    g.line(LEV2[0], LEV2[1], LEV2[2], LEV2[3], 0.1)
    g.line(LEV2[0], LEV2[3], LEV2[2], LEV2[1], 0.1)
    for xx in (-5.4, -2.85):
        g.rect(xx, 19.88, xx + 0.25, 20.0, 0, INK)
    g.rect(-5.25, 7.65, -2.75, 19.85, 0.25, "none", INK, "1.4 0.8")
    g.rect(-5.25, 1.40, -2.75, 7.40, 0.25, "none", INK, "1.4 0.8")
    g.rect(*CANOPY, 0.2, "none", GREY, "2 1")


# ---------------- L-03 Muelle de carga ----------------
def sheet_L03():
    d = Doc()
    frame(d)
    # Planta 1:125 girada (horizontal = y, vertical = x)
    v = View(d, 8.0, 65, 50)
    g = Swap(v)
    g.rect(-8, -5, 2.5, 28, 0, "#eef3e6")
    g.rect(-8, -5, 2.5, -3.0, 0, "#e3e3e3")
    g.rect(0, 0, 2.5, 28, 0, "#f6f3ec")
    g.rect(0, 0, 0.15, DOCK_DOOR[0], 0, "#333")
    g.rect(0, DOCK_DOOR[1], 0.15, 28, 0, "#333")
    for y in COL_Y[:-1]:
        g.rect(0.0, y - 0.3, 0.4, y + 0.3, 0.15, "#9a9a9a")
    dock_geom(g)
    v.text(-4.0, -2.6, "VÍA INTERNA", 1.8, rot=-90, c="#555")
    v.text(2.0, -7.2, "rampa 7.5 % (sube hacia la vía)", 1.6, c="#555")
    v.text(13.5, -7.2, "zona del camión 2 % (sube hacia la vía)", 1.6, c="#555")
    v.text(4.4, -4.1, "tracto", 1.8, c="#444")
    v.text(13.75, -4.1, "contenedor 40' HC (12.19 m) — puertas hacia el andén", 1.7, c="#444")
    v.text(23.6, -6.0, "ANDÉN ±0.00", 2.0, weight="bold", anchor="start")
    v.text(21.25, -2.4, "niveladora 2.00×2.50", 1.3)
    v.text(23.5, 1.2, "puerta 3.00×3.20", 1.5)
    v.text(12.0, 1.4, "NAVE — muro lateral izquierdo (eje A)", 1.8, weight="bold")
    v.text(9.0, -0.85, "franja 1.50 de protección de cimentación (vereda)", 1.4, c="#555")
    v.text(17.4, -1.5, "esc.", 1.3)
    v.text(19.25, -6.85, "canal + sumidero", 1.3, anchor="end")
    v.text(17.6, -5.85, "guías de rueda", 1.3)
    v.text(21.0, -7.55, "marquesina 7.00 × 10.00 a +4.20", 1.4, c="#555")
    v.arrow([(21.4, -4.0), (23.4, -4.0), (23.4, -0.4)], GREEN, 0.5, None, 1.6)
    v.hdim(-3, 7, -8.6, "10.00 · rampa 7.5 %", 1.6)
    v.hdim(7, 20, -8.6, "13.00 · zona del camión 2 %", 1.6)
    v.hdim(20, 26, -8.6, "6.00 · andén", 1.6)
    v.hdim(22.0, 25.0, 2.0, "3.00", 1.4)
    v.vdim(LANE[0], LANE[1], -2.4, "4.50", 1.5)
    v.vdim(-1.5, 0.0, -2.4, "1.50", 1.3)
    v.vdim(-6.5, 0.0, 27.0, "6.50", 1.5)
    d.text(25, 126, "PLANTA DEL MUELLE LATERAL — calle deprimida paralela al muro", 3.0, "start", "bold")
    d.text(300, 126, "ESC. 1:125", 2.4, "end")

    # Corte longitudinal por el eje de la calle (x = -4.00), mirando hacia la nave
    s = View(d, 8.0, 65, 178)
    pts = [(-5, GRADE)] + [(y, ground_z(y)) for y in (-3.0, 7.0, 20.0)]
    s.poly(pts + [(20.0, -1.55), (7.0, -1.25), (-3.0, -0.50), (-5, -0.50)], 0.2, "#d8d2c4")
    s.poly(pts, 0.45, closed=False)
    s.rect(19.85, DOCK_LVL, 20.0, 0, 0.1, "#555")
    s.rect(20.0, -0.35, 26.0, 0.0, 0.2, "#d8d2c4")
    s.line(20.0, 0.0, 26.0, 0.0, 0.45)
    s.line(26.0, GRADE, 29.0, GRADE, 0.3)
    s.rect(0, 0, 28.5, EAVE, 0.15, "none", GREY)
    s.rect(22.0, 0, 25.0, 3.2, 0.15, "#fff", GREY)
    s.text(14.0, 5.3, "muro lateral de la nave (al fondo)", 1.6, c="#777")
    s.text(23.5, 3.45, "puerta 3.00×3.20", 1.4, c="#777")
    s.line(-3, -0.05, 20, -0.05, 0.25, GREY, "1.5 0.8")
    s.line(-3, 1.05, 20, 1.05, 0.25, GREY, "1.5 0.8")
    s.text(-2.8, 1.25, "muro de contención + baranda h 1.10", 1.4, c="#555", anchor="start")
    s.poly([(16.0, 4.20), (26.0, 4.45)], 0.45, closed=False)
    s.text(16.2, 4.6, "marquesina +4.20", 1.4, anchor="start")
    bed = DOCK_LVL + 1.35
    s.rect(7.65, bed, 19.85, bed + 2.90, 0.3, "#f3efe6", INK)
    s.rect(7.65, bed - 0.25, 19.85, bed, 0.15, "#ccc")
    s.text(13.75, bed + 1.5, "CONTENEDOR 40' HC — piso ≈ +0.10 respecto al andén", 1.6)
    for yy in (8.8, 10.0, 17.0, 18.2):
        s.circle(yy, ground_z(yy) + 0.5, 4.0, 0.2, "#555")
    b = ground_z(4.4) + 0.5
    s.poly([(7.4, b), (7.4, b + 1.1), (3.9, b + 1.1), (3.3, b + 2.9), (1.4, b + 2.9), (1.4, b)], 0.3, "#eee")
    for yy in (2.4, 5.6, 6.6):
        s.circle(yy, ground_z(yy) + 0.5, 4.0, 0.2, "#555")
    s.level(-4.5, GRADE, "-0.20 vía")
    s.level(7.0, MID_LVL, "-0.95")
    s.level(19.3, DOCK_LVL, "-1.25", left=True)
    s.level(27.0, 0.0, "±0.00 andén = bodega")
    s.text(2.0, -1.2, "7.5 %", 1.8, weight="bold")
    s.text(13.5, -1.55, "2 %", 1.8, weight="bold")
    s.vdim(DOCK_LVL, 0, 20.6, "1.25", 1.5)
    d.text(25, 197, "CORTE LONGITUDINAL POR EL EJE DE LA CALLE", 3.0, "start", "bold")
    d.text(300, 197, "ESC. 1:125", 2.4, "end")

    # Detalle 1:50 frente de muelle (cara del andén)
    t = View(d, 20.0, 95, 254)
    t.rect(-3.5, DOCK_LVL - 0.25, 0.0, DOCK_LVL, 0.15, "#d8d2c4")
    t.line(-3.5, DOCK_LVL, 0.0, DOCK_LVL, 0.4)
    t.rect(-0.95, DOCK_LVL - 0.30, -0.65, DOCK_LVL, 0.15, "#fff")
    t.line(-0.95, DOCK_LVL, -0.65, DOCK_LVL, 0.3, "#555", "0.5 0.3")
    t.text(-1.1, DOCK_LVL + 0.15, "canal 0.30 con rejilla", 1.4, anchor="end")
    t.rect(0.0, DOCK_LVL - 0.25, 0.30, 0.0, 0.15, "#bfb8a8")
    t.rect(0.30, -0.65, 2.80, -0.35, 0.15, "#d8d2c4")
    t.rect(2.80, -0.65, 3.10, 0.0, 0.15, "#d8d2c4")
    t.rect(0.30, -0.35, 2.80, 0.0, 0.1, "#fff")
    t.poly([(0.30, 0.0), (2.80, 0.0)], 0.5, closed=False)
    t.poly([(0.30, 0.0), (-0.10, -0.05)], 0.5, closed=False)
    t.text(1.55, -0.25, "fosa niveladora H.A. prof. 0.60", 1.5)
    t.text(1.55, 0.25, "plataforma 2.50 + labio 0.40", 1.5)
    t.rect(3.10, -0.20, 3.4, 0.0, 0.15, "#d8d2c4")
    t.rect(-0.10, -0.50, 0.0, -0.05, 0.1, INK, INK)
    t.text(-0.25, -0.30, "tope de caucho 450×250×100", 1.4, anchor="end")
    t.rect(-3.5, 0.10, -0.15, 0.15, 0.15, "#aaa")
    t.text(-1.8, 0.35, "piso del contenedor (variable +0.05 / +0.35)", 1.4)
    t.line(-0.6, 0.0, -0.6, 1.9, 0.15, GREY)
    t.circle(-0.6, 1.9, 1.0, 0.15, "#ff0")
    t.text(-0.8, 1.75, "luz de muelle LED en poste", 1.4, anchor="end")
    t.text(1.6, 1.6, "marquesina a +4.20 (fuera de la vista)", 1.4, c="#555")
    t.level(2.0, 0.0, "±0.00 andén", 1.6)
    t.level(-2.8, DOCK_LVL, "-1.25", 1.6)
    t.vdim(DOCK_LVL, 0.0, -3.3, "1.25", 1.6)
    t.vdim(-0.30, 0.30, 3.3, "±0.30", 1.4)
    d.text(25, 207, "DETALLE FRENTE DE MUELLE (cara del andén)", 3.0, "start", "bold")
    d.text(152, 207, "ESC. 1:50", 2.4, "end")

    tx, ty = 162, 210
    d.text(tx, ty, "ESPECIFICACIONES TÉCNICAS DEL MUELLE", 2.8, "start", "bold")
    specs = [
        ("Configuración", "Calle deprimida paralela al muro izquierdo. El camión entra de retro hacia el fondo y "
                          "descarga por la cola sobre un andén a ±0.00; el montacargas gira en el andén y entra a la "
                          "recepción, junto al showroom, por una puerta lateral"),
        ("Desnivel", "Calle a -1.25 en la cara del muelle → piso del contenedor ≈ nivel del andén"),
        ("Niveladora", "Hidráulica 2.00 × 2.50 m, labio 400 mm, 8 t dinámicas, rango ±300 mm, empotrada en el andén"),
        ("Calle", "10 m de rampa al 7.5 % + 13 m al 2 %; ancho libre 4.50; separada 1.50 del muro de la nave"),
        ("Andén", "6.50 × 6.00 m a ±0.00, losa H.A. de 20 cm; sirve como staging cubierto (≈ 16 pallets)"),
        ("Muros", "Contención H.A. e = 25 cm, h 0.15–1.20; baranda tubo galv. h 1.10 + bordillo"),
        ("Drenaje", "Canal 0.30 × 0.30 con rejilla para tráfico pesado + sumidero con bomba de 1 HP y alarma de nivel"),
        ("Puerta", "Enrollable motorizada 3.00 × 3.20 en el muro de la nave (ejes 4–5)"),
        ("Accesorios", "2 topes 450×250×100, guías de rueda, cuñas, luz LED, semáforo, espejo convexo"),
        ("Cubierta", "Marquesina metálica 7.00 × 10.00 a +4.20 sobre el andén y la cola del camión"),
    ]
    y = ty + 5.0
    for k, val in specs:
        d.text(tx, y, k, 1.75, "start", "bold")
        lines = wrap(val, 1.75, 116)
        for j, ln in enumerate(lines):
            d.text(tx + 24, y + j * 2.45, ln, 1.75, "start")
        y += 2.45 * len(lines) + 0.9
    title_block(d, "L-04", "Muelle de carga lateral — calle deprimida paralela al muro + andén", [
        ("Ubicación", "Costado izquierdo, calle de los ejes 1 a 4; andén y puerta entre los ejes 4 y 5"),
        ("Posiciones", "1 contenedor 20'/40'/40'HC"),
        ("Descarga", "Por la cola del contenedor sobre el andén; montacargas o transpaleta eléctrica a nivel"),
        ("Rendimiento", "Un 40' HC lleno equivale a ≈ 90 posiciones de pallet: ubicar en racks a medida que se descarga"),
    ], [
        "El contenedor abre solo por atrás: con la calle paralela al muro, la descarga es por la cola sobre el andén, no por el costado.",
        "La calle está separada 1.50 m del muro: una excavación de 1.25 m pegada a la nave descalzaría su cimentación.",
        "El camión retrocede 90° desde la vía interna a la calle. Verificar el ancho de la vía y el radio de giro "
        "(tracto + 40' ≈ 13–14 m de radio exterior).",
        "Pendiente ≤ 8 % en la rampa y ≤ 2 % donde se estaciona el remolque.",
        "Verificar el nivel freático y la cota de la red pluvial: si no hay salida por gravedad, la bomba es obligatoria.",
        "Montacargas que entre al contenedor: mástil recogido ≤ 2.10 m y elevación libre total.",
        "Este anteproyecto debe pasar a planos estructurales firmados por un ingeniero civil local.",
    ], "1:125 / 1:50", 4, 5)
    return d


# ---------------- L-04 Cortes: racks y mezanine ----------------
def rack_section(v, x0, x1):
    for xa in (x0, x1 - 0.07):
        v.rect(xa, 0, xa + 0.07, RACK_H, 0, BLUE)
    v.line(x0, 0.4, x1, 1.3, 0.08, BLUE)
    v.line(x1, 1.3, x0, 2.4, 0.08, BLUE)
    v.line(x0, 2.4, x1, 3.5, 0.08, BLUE)
    v.line(x1, 3.5, x0, 4.6, 0.08, BLUE)
    tops = [0.0] + [b + BEAM_H for b in BEAMS]
    for b in BEAMS:
        for xa in (x0 + 0.07, x1 - 0.12):
            v.rect(xa, b, xa + 0.05, b + BEAM_H, 0, ORANGE)
    for tz in tops:
        v.rect(x0 - 0.05, tz, x1 + 0.05, tz + 0.15, 0.08, "#c9a46a")
        v.rect(x0 - 0.03, tz + 0.15, x1 + 0.03, tz + LOAD_H, 0.08, "#f3e3c3", "#a07c40")


def roof_section(v, xa, xb):
    def zr(x):
        return EAVE + (RIDGE - EAVE) * min(x, AX_C) / AX_C
    v.poly([(xa, zr(xa) + 0.1), (min(xb, AX_C), zr(min(xb, AX_C)) + 0.1)], 0.45, closed=False)
    v.line(xa, EAVE, xb, EAVE, 0.25)
    n = 6
    for k in range(1, n + 1):
        x = AX_C * k / n
        if x > xb:
            break
        v.line(x, EAVE, x, zr(x), 0.12)
        v.line(AX_C * (k - 1) / n, EAVE if k % 2 else zr(AX_C * (k - 1) / n), x, zr(x) if k % 2 else EAVE, 0.1)


def sheet_L04():
    d = Doc()
    frame(d)
    # Corte B-B 1:100 (transversal por racks, mirando al fondo)
    v = View(d, 10.0, 40, 125)
    v.rect(-1, -0.25, 19.5, 0, 0.15, "#d8d2c4")
    v.rect(0, 0, 0.15, EAVE, 0, "#444")
    v.rect(PART[0], 0, PART[1], RIDGE, 0.1, "#7a7a7a")
    roof_section(v, -0.3, AX_C)
    v.text(PART[1] + 0.2, 4.5, "muro divisorio hasta cubierta", 1.5, rot=-90, anchor="middle")
    for nm, a, b in ROWS:
        rack_section(v, a, b)
        v.text((a + b) / 2, -0.75, nm, 1.7, weight="bold", c=BLUE)
    for nm, a, b in AISLES:
        v.hdim(a, b, 0.55, "3.50", 1.6)
        v.rect((a + b) / 2 - 0.4, 5.78, (a + b) / 2 + 0.4, 5.86, 0, "#333")
        v.text((a + b) / 2, 5.45, "LED", 1.3)
    top = BEAMS[-1] + BEAM_H + LOAD_H
    v.line(0.3, top, 18.0, top, 0.15, RED, "1 0.6")
    v.vdim(top, EAVE, 2.9, f"{EAVE - top:.2f}", 1.5)
    v.text(9.2, top - 0.30, f"tope de carga +{top:.2f}", 1.5, c=RED)
    v.level(18.6, EAVE, "+6.00 cercha")
    v.level(18.6, RIDGE, "+9.00 cumbrera")
    v.level(18.6, RACK_H, "+5.00 rack")
    v.level(18.6, 0, "±0.00")
    for b in BEAMS:
        v.level(-0.2, b, f"+{b:.2f}", 1.4, left=True)
    d.text(30, 140, "CORTE B-B — Racks (vanos normales) vs. altura libre de la nave", 3.0, "start", "bold")
    d.text(232, 140, "ESC. 1:100", 2.4, "end")

    # Cuadro racks
    tx, ty = 244, 26
    d.text(tx, ty, "CUADRO DE RACKS", 2.8, "start", "bold")
    rows = [("Sistema", "Selectivo, acceso directo a cada pallet"),
            ("Bastidor", "D 1100 × H 5000 mm, parante 100×70×2.2"),
            ("Viga", "Box beam L 3300, 160×45×1.5 (catálogo: 2,712 kgf)"),
            ("Niveles", "Piso + 3 de vigas = 4 posiciones"),
            ("Vigas a", "+1.35 / +2.79 / +4.23 (paso de 75 mm)"),
            ("Capacidad", "≤ 2,400 kg/nivel: 3 pallets ≤ 800 kg c/u"),
            ("Filas", "R1 y R6 simples; R2-R3 y R4-R5 dobles"),
            ("Vanos", "35 vanos de 3.30: 25 normales + 10 altos"),
            ("Vano alto", "Vigas a +2.05 / +4.25: 2 niveles de 1.85 m + 1 normal"),
            ("Posiciones", "25 × 12 + 10 × 9 = 390 pallets (60 altas)"),
            ("Pasillos", "3.50 m (contrabalanceado de 3 ruedas)"),
            ("Holgura", f"{EAVE - top:.2f} m entre la carga y la cercha")]
    y = ty + 5
    for k, val in rows:
        d.text(tx, y, k, 1.9, "start", "bold")
        for j, ln in enumerate(wrap(val, 1.9, 46)):
            d.text(tx + 20, y + j * 2.7, ln, 1.9, "start")
        y += 2.7 * len(wrap(val, 1.9, 46)) + 1.0

    # Corte C-C 1:100 (longitudinal por x ≈ 12, mirando a la izquierda)
    c = View(d, 10.0, -150, 255)
    c.rect(17.5, -0.25, 32.6, 0, 0.15, "#d8d2c4")
    c.rect(31.85, 0, 32.0, EAVE, 0, "#444")
    zr = EAVE + (RIDGE - EAVE) * 12.0 / AX_C
    c.line(17.5, zr, 32.0, zr, 0.45)
    c.line(17.5, EAVE, 31.85, EAVE, 0.25)
    for yy in (19.14, 25.42, 31.70):
        c.line(yy, EAVE, yy, zr, 0.12)
    c.text(19.0, zr + 0.3, f"cubierta en x = 12 m: +{zr:.2f}", 1.4, anchor="start")
    # rack R4 de costado
    for k in (NB,):
        y = RY0 + k * (BAY + UPR)
        c.rect(y, 0, y + UPR, RACK_H, 0, BLUE)
    for b in BEAMS:
        c.rect(17.6, b, RY1 - 0.1, b + BEAM_H, 0, ORANGE)
    for tz in [0.0] + [b + BEAM_H for b in BEAMS]:
        for p in range(PPL):
            py0 = RY0 + (NB - 1) * (BAY + UPR) + UPR + 0.075 + p * 1.075
            if py0 < 17.6:
                continue
            c.rect(py0, tz, py0 + 1.0, tz + LOAD_H, 0.08, "#f3e3c3", "#a07c40")
    c.text(18.6, -0.75, "rack R4 (costado)", 1.5, c=BLUE)
    # mezanine
    c.rect(MZ[1], MZ_BOT, MZ[3], MZ_FFL, 0.15, "#bbb")
    for yy in MZ_COLY:
        c.rect(yy - 0.075, 0, yy + 0.075, MZ_BOT, 0.1, "#555")
    c.rect(MZ[1], 0, MZ[1] + 0.1, 2.40, 0.1, "#fff", INK, "0.5 0.3")
    c.rect(MZ[1], 3.20, MZ[1] + 0.1, 5.90, 0.1, "#cfe3ee")
    c.rect(MZ[1], 3.20, MZ[1] + 0.1, 4.10, 0.1, "#ddd")
    c.line(MZ[1], 5.90, 31.85, 5.90, 0.2, GREY, "1 0.6")
    c.text(28.6, 6.15, "cielo raso +5.90", 1.4, c="#555")
    c.text(28.4, 1.7, "LABORATORIO / TALLER", 1.9, weight="bold", c="#2d4d6b")
    c.text(28.4, 1.0, "h libre 2.85", 1.6, c="#2d4d6b")
    c.text(28.4, 4.8, "COWORKING / CAFETERÍA", 1.9, weight="bold", c="#6b4a1a")
    c.text(28.4, 4.1, "h libre 2.70", 1.6, c="#6b4a1a")
    c.text(MZ[1] - 0.25, 1.3, "puerta 2.40", 1.4, rot=-90)
    c.text(MZ[1] - 0.25, 4.6, "vidrio templado", 1.4, rot=-90)
    c.level(32.3, MZ_FFL, "+3.20 NPT oficinas")
    c.level(32.3, MZ_BOT, "+2.85 bajo viga")
    c.level(32.3, EAVE, "+6.00")
    c.level(32.3, 0, "±0.00")
    c.hdim(RY1, MZ[1], 0.6, f"{MZ[1] - RY1:.2f} pasillo trasero", 1.5)
    c.hdim(MZ[1], MZ[3], 7.0, "6.00 mezanine", 1.5)
    d.text(25, 266, "CORTE C-C — Pasillo transversal y mezanine (x ≈ 12 m)", 3.0, "start", "bold")
    d.text(178, 266, "ESC. 1:100", 2.4, "end")

    # Alzado de fila 1:125
    r = View(d, 5.0, 190, 240)
    L = NB * BAY + (NB + 1) * UPR
    for k in range(NB + 1):
        y = k * (BAY + UPR)
        r.rect(y, 0, y + UPR, RACK_H, 0, BLUE)
    for k in range(NB):
        yb = k * (BAY + UPR) + UPR
        tall = k == NB - 1
        beams = TALL_BEAMS if tall else BEAMS
        for b in beams:
            r.rect(yb, b, yb + BAY, b + BEAM_H, 0, ORANGE)
        levels = [(0.0, 1.78), (TALL_BEAMS[0] + BEAM_H, 1.78), (TALL_BEAMS[1] + BEAM_H, LOAD_H)] if tall else \
            [(tz, LOAD_H) for tz in [0.0] + [b + BEAM_H for b in BEAMS]]
        for tz, lh in levels:
            for p in range(PPL):
                py0 = yb + 0.075 + p * 1.075
                r.rect(py0, tz, py0 + 1.0, tz + 0.15, 0.06, "#c9a46a")
                r.rect(py0 + 0.03, tz + 0.15, py0 + 0.97, tz + lh, 0.06, "#f6dcb8" if tall else "#f3e3c3", "#a07c40")
        r.hdim(yb, yb + BAY, -0.9, "3.30", 1.2)
    r.text(L - 1.4, 2.05 - 0.45, "+2.05", 1.2, c=ORANGE)
    r.text(L - 1.4, 4.25 - 0.45, "+4.25", 1.2, c=ORANGE)
    r.line(-0.5, 0, L + 0.5, 0, 0.3)
    r.vdim(0, RACK_H, L + 0.8, "5.00", 1.5)
    r.hdim(0, L, 6.2, f"{L:.2f}", 1.5)
    d.text(190, 266, "ALZADO FILA TIPO (6 vanos de 3.30; el último, alto)", 2.4, "start", "bold")
    d.text(310, 266, "ESC. 1:200", 2.4, "end")
    title_block(d, "L-05", "Cortes — racks, alturas libres y mezanine", [
        ("Altura libre", "+6.00 bajo el cordón inferior de la cercha (en toda la planta)"),
        ("Rack máx.", "H 5.00 m; tope de carga +5.57"),
        ("Mezanine", "NPT +3.20; PB libre 2.85; PA libre 2.70"),
    ], [
        "Las luminarias van sobre los pasillos, nunca sobre los racks. Mantener ≥ 0.40 m libres bajo la cercha.",
        "Placa de capacidad visible en cada fila; inspección anual de los racks y reposición de protectores golpeados.",
        "Antes de comprar, confirmar la altura real de las cargas: define 4 o 5 posiciones por vano.",
        "El mezanine es una estructura independiente: no se apoya ni se ancla en las columnas o cerchas de la nave.",
    ], "1:100 / 1:200", 5, 5)
    return d


def main():
    out = fitz.open()
    for i, fn in enumerate([sheet_complete, sheet_vicomer, sheet_mezz, sheet_L03, sheet_L04], 1):
        svg = fn().svg()
        p = os.path.join(HERE, f"_tmp_L0{i}.svg")
        with open(p, "w") as f:
            f.write(svg)
        src = fitz.open(p)
        out.insert_pdf(fitz.open("pdf", src.convert_to_pdf()))
        src[0].get_pixmap(dpi=120).save(os.path.join(HERE, f"_prev_L0{i}.png"))
        os.remove(p)
    out.save(OUT + ".pdf")
    print("ok", OUT + ".pdf")


if __name__ == "__main__":
    main()
