# Genera la solicitud de cotización (RFQ) para Guangzhou Jinshichang: racks revisados + mezanine.
# Uso: python3 gen_rfq.py
import os
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "RFQ_Vicomer_Racks_Mezzanine_v5.docx")
NAVY = RGBColor(0x1F, 0x3A, 0x5F)


def shade(cell, hex_fill):
    tcPr = cell._tc.get_or_add_tcPr()
    s = OxmlElement("w:shd")
    s.set(qn("w:val"), "clear")
    s.set(qn("w:color"), "auto")
    s.set(qn("w:fill"), hex_fill)
    tcPr.append(s)


def table(doc, header, rows, widths, opt_rows=()):
    t = doc.add_table(rows=1, cols=len(header))
    t.style = "Table Grid"
    for i, h in enumerate(header):
        c = t.rows[0].cells[i]
        c.text = ""
        r = c.paragraphs[0].add_run(h)
        r.bold, r.font.size, r.font.color.rgb = True, Pt(8.5), RGBColor(0xFF, 0xFF, 0xFF)
        shade(c, "1F3A5F")
    for k, row in enumerate(rows):
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = ""
            r = cells[i].paragraphs[0].add_run(str(v))
            r.font.size = Pt(8.5)
            if k in opt_rows:
                shade(cells[i], "F3F6FA")
    for row in t.rows:
        for i, w in enumerate(widths):
            row.cells[i].width = Cm(w)
    doc.add_paragraph()
    return t


def h(doc, text, lvl=1):
    p = doc.add_heading(text, lvl)
    for r in p.runs:
        r.font.color.rgb = NAVY
    return p


def para(doc, text, bold=False, size=10, italic=False):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.bold, r.italic, r.font.size = bold, italic, Pt(size)
    return p


def bullets(doc, items, size=9.5):
    for it in items:
        p = doc.add_paragraph(style="List Bullet")
        r = p.add_run(it)
        r.font.size = Pt(size)


doc = Document()
for s in doc.sections:
    s.left_margin = s.right_margin = Cm(2.0)
    s.top_margin = s.bottom_margin = Cm(1.8)
doc.styles["Normal"].font.name = "Arial"
doc.styles["Normal"].font.size = Pt(10)

# ---------- Resumen interno (ES) ----------
t = doc.add_paragraph()
r = t.add_run("RESUMEN INTERNO — no enviar al proveedor")
r.bold, r.font.size, r.font.color.rgb = True, Pt(9), RGBColor(0xC0, 0x39, 0x2B)
h(doc, "Solicitud de cotización revisada — racks y mezanine (Nave E02-1)", 1)
bullets(doc, [
    "La proforma TL2026070203 (US$ 19,443 FOB) era para 80 vanos con bastidores de 7.05 m de alto. "
    "La nave tiene 6.00 m libres bajo la cercha, así que esos racks no entran.",
    "En la mitad A de la nave caben 35 vanos de 3.30 m (3 pallets por nivel) = 390 pallets, con pasillos de 3.50 m y los racks "
    "hasta la fachada. Son 25 vanos normales de 4 niveles y 10 vanos altos para refrigeradoras. Se piden 41 bastidores de 5.00 m "
    "(antes 96) y 190 vigas de 3.30 m (antes 800 de 2.70 m).",
    "Se eliminan las 24 vigas de pasillo de 3.60 m (amarres superiores): no hacen falta a 5 m de altura "
    "y el mástil del montacargas chocaría con ellas.",
    "Se mantiene el parante 100×70×2.2. La viga sube a cajón 160×45×1.5 porque es más larga: según el catálogo soporta 2,712 kgf "
    "con 3.30 m. Carga de diseño: 2,400 kg por nivel (3 pallets de máx. 800 kg). Los productos de Vicomer pesan mucho menos.",
    "Con las proporciones de la proforma original, el costo de los racks debería quedar en ≈ US$ 6,000–6,800 FOB "
    "(≈ 70 % menos). Esto es una estimación para negociar, no un precio del proveedor.",
    "Se agrega la cotización del mezanine para oficinas: 17.60 × 6.00 m, piso terminado a +3.20 m, "
    "carga viva de 500 kg/m², con escalera recta de un tramo, barandas y pases para la zona húmeda.",
    "Se piden opcionales: un 4.º nivel de vigas, parrillas de malla, placas de capacidad y 2 estanterías medianas para el laboratorio.",
    "Pedir también precio CIF Guayaquil. Pedir que racks y mezanine vengan en un solo contenedor para ahorrar flete.",
], 9.5)
para(doc, "Adjuntar al correo: Nave_E02_Fase1_planos_v12.pdf (láminas L-01, L-02, L-03 y L-05; la L-04 del muelle no es necesaria).", italic=True, size=9)
doc.add_page_break()

# ---------- RFQ (EN) ----------
h(doc, "REQUEST FOR QUOTATION — Revised pallet racking + steel mezzanine", 1)
info = [
    ("To", "Guangzhou Jinshichang Shelf Co., Ltd. — Attn. Mr. Frank (Frank@liangangrack.com)"),
    ("From", "VICOMER S.A.S. (iGlace) — Juan Marcelo Vidal, jmvidal@v-comer.com"),
    ("Reference", "VIC-RFQ-2026-01 · replaces the configuration of PI No. TL2026070203 (2026-07-02)"),
    ("Date", "30 October 2026"),
    ("Site", "Warehouse E02-1, Ecuador (seismic zone — see section C)"),
]
tt = doc.add_table(rows=0, cols=2)
for k, v in info:
    c = tt.add_row().cells
    c[0].text, c[1].text = k, v
    c[0].paragraphs[0].runs[0].bold = True
    c[0].width, c[1].width = Cm(3), Cm(14)
doc.add_paragraph()
para(doc, "Dear Frank, thank you for PI TL2026070203. After surveying our building we must change the configuration: "
          "the clear height under the roof trusses is only 6.00 m, so the 7,050 mm uprights cannot be installed. "
          "Please quote the revised racking below plus a steel mezzanine for offices. Layout drawings are attached.", size=10)

h(doc, "A. Selective pallet racking (revised)", 2)
bullets(doc, [
    "Layout: 6 runs (2 single + 2 double back-to-back) = 35 bays (5 runs × 6 bays + 1 run × 5 bays); aisles 3,500 mm.",
    "Bay: clear beam length 3,300 mm (3 pallets per level); frame depth 1,100 mm; frame height 5,000 mm.",
    "Levels: 25 standard bays with floor + 3 beam levels (beams at approx. +1,350 / +2,790 / +4,230 mm) and 10 tall bays "
    "with floor + 2 beam levels (beams at approx. +2,050 / +4,250 mm) for refrigerators up to 1,800 mm high; 75 mm adjustment pitch.",
    "Pallet: 1,000 × 1,200 mm (1,200 deep), max. 800 kg per pallet, 3 pallets per level.",
    "Design load: 2,400 kg per level (UDL per beam pair).",
    "Sections: upright 100×70×2.2 mm (as in your PI, do not reduce); box beam 160×45×1.5 mm. "
    "Please confirm the beam rating (your catalog table: 2,712 kgf at L 3,300 mm).",
    "Colours: uprights RAL 5005, beams RAL 2004 (as quoted). Epoxy powder coat ≥ 60 µm.",
], 9.5)
table(doc, ["No.", "Item", "Specification", "Qty", "Unit", "Unit price (USD)", "Amount (USD)"], [
    ("1", "Upright frame", "D 1,100 × H 5,000 mm; upright section 100×70×2.2 mm; bracing, base plates, bolts", "41", "set", "", ""),
    ("2", "Box beam", "L 3,300 mm; section 160×45×1.5 mm; with safety locks (25 × 3 + 10 × 2 levels)", "190", "pc", "", ""),
    ("3", "Row spacer", "L 200 mm; 50×30×1.5 mm (3 per frame pair, double runs)", "42", "pc", "", ""),
    ("4", "Upright protector", "U-type, H 500 × 3.0 mm, aisle-side uprights", "41", "pc", "", ""),
    ("5", "End-of-row barrier", "L 1,100 × H 500 mm, Φ76 × 2.5 mm (single runs)", "4", "set", "", ""),
    ("6", "End-of-row barrier", "L 2,400 × H 500 mm, Φ76 × 2.5 mm (double runs, 1,100 + 200 + 1,100)", "4", "set", "", ""),
    ("7", "Anchor bolts", "M12 expansion, incl. 10 % spare", "180", "pc", "", ""),
    ("8", "Safety pins", "Beam locks, incl. spare", "420", "pc", "", ""),
    ("O1", "OPTION — Box beam", "Extra 4th beam level for the 25 standard bays, L 3,300, 160×45×1.5", "50", "pc", "", ""),
    ("O2", "OPTION — Wire mesh deck", "For 3,300 × 1,100 bay (3 panels per level), galvanised, ≥ 800 kg per panel (first level, 35 bays)", "105", "pc", "", ""),
    ("O3", "OPTION — Load signs", "Capacity plate per run", "6", "pc", "", ""),
    ("O4", "OPTION — Medium-duty shelving", "1,500 × 500 × 2,500 mm, 4 levels, 300 kg/level, steel panels", "2", "unit", "", ""),
], [1.0, 3.0, 6.6, 1.1, 1.0, 2.0, 2.0], opt_rows=range(8, 12))
para(doc, "Removed from the PI: aisle beams L 3,600 (top ties). They are not required at H 5,000 mm. "
          "If your engineering requires them for stability, please quote them separately with justification.", size=9, italic=True)

h(doc, "B. Steel mezzanine (office platform)", 2)
bullets(doc, [
    "Type: free-standing bolted steel structure, independent of the building (no connection to building columns or trusses).",
    "Platform size: 17,600 mm (L) × 6,000 mm (W) = 105.6 m². Finished floor level +3,200 mm. "
    "Underside of the structure ≥ +2,850 mm (clear height below).",
    "Columns: max. 10 columns — 5 along the front edge and 5 along the rear edge (rear edge 150 mm from the back wall). "
    "Indicative positions along the length from the left edge: 150 / 4,470 / 8,780 / 13,100 / 17,450 mm. "
    "No intermediate columns: there are rooms below (showroom and lab). Square tube ≥ 150×150 mm with base plates.",
    "Use: offices (desks, meeting room, kitchenette, archive). Design live load 500 kg/m² (4.9 kN/m²) "
    "+ lightweight partitions 100 kg/m² + floor finish. Deflection ≤ L/360.",
    "Seismic: Ecuador, high seismic hazard. Design to NEC-SE-DS or an equivalent standard, minimum Z = 0.25 g, with bracing.",
    "Floor — please quote both options: (1) galvanised steel floor deck for an 80–100 mm concrete topping poured locally; "
    "(2) galvanised steel floor planks (as in your catalog) ready for an 18–20 mm board finish.",
    "Staircase: 1 straight single-flight steel staircase placed along an internal wall, inside the platform footprint; "
    "clear width 1,100 mm; 18 risers (≈ 178 mm); tread 280 mm; total run ≈ 4,760 mm; anti-slip checkered treads; "
    "handrail on the open side H 900 mm + wall handrail. Deck opening 1,100 × 4,850 mm, located 7,600 mm from the left "
    "edge of the platform and running to the rear edge (see drawing L-03).",
    "Guardrails: H 1,100 mm with mid-rail and 100 mm toe board — front edge (17.6 m) + stair opening (≈ 10.8 m) ≈ 29 m.",
    "Wet areas: (1) 2 toilets + kitchenette at the rear-right corner (≈ 5 × 2.5 m); (2) private bathroom with shower at the "
    "rear-left corner (≈ 1.8 × 2.4 m). Please provide 5 deck penetrations Ø110 mm for drainage (3 right, 2 left) and "
    "consider the extra finish load (ceramic tiles + screed ≈ 150 kg/m²) in both zones.",
    "Finish: shot-blasted + epoxy powder coat (RAL 7035) or hot-dip galvanised — please quote both.",
    "Include: bolts, chemical anchors (M16), base plates, edge fascia, assembly drawings, installation manual and the "
    "structural calculation report with base-plate reactions (needed to check our floor slab).",
], 9.5)
table(doc, ["No.", "Item", "Specification", "Qty", "Unit", "Unit price (USD)", "Amount (USD)"], [
    ("M1", "Mezzanine structure", "17.6 × 6.0 m, FFL +3,200, LL 500 kg/m², 10 columns", "105.6", "m²", "", ""),
    ("M2", "Floor option 1", "Galvanised steel deck for concrete topping", "105.6", "m²", "", ""),
    ("M3", "Floor option 2", "Galvanised steel floor planks", "105.6", "m²", "", ""),
    ("M4", "Straight staircase", "W 1,100, 18 risers, single flight, handrails", "1", "set", "", ""),
    ("M5", "Guardrail + toe board", "H 1,100 mm", "29", "m", "", ""),
    ("M6", "OPTION — straight emergency stair", "W 1,000, 18 risers, handrails", "1", "set", "", ""),
], [1.0, 3.2, 6.4, 1.1, 1.0, 2.0, 2.0], opt_rows=[5])

h(doc, "C. Commercial and technical documents", 2)
bullets(doc, [
    "Prices FOB Nansha AND CIF Guayaquil, Ecuador. Please ship racking and mezzanine together in one container if possible; "
    "state the container type (20' / 40' HC).",
    "Packing list with weights (kg) and volume (CBM) per item; HS codes.",
    "Production lead time, payment terms, quotation validity, warranty (structure and coating).",
    "Steel grade (Q235 / Q355) and thickness tolerance; mill certificates on request.",
    "Rack structural check for H 5,000 mm with 3 levels × 2,400 kg in a seismic zone, plus anchor and base-plate loads.",
    "Option: remote installation support (video) or quote for on-site supervision.",
], 9.5)
para(doc, "Attachments: Nave_E02_Fase1_planos_v12.pdf — L-01 complete warehouse, L-02 racking layout, L-03 mezzanine plans, L-05 sections.", size=9, italic=True)
para(doc, "Best regards,\nJuan Marcelo Vidal\nVICOMER S.A.S.", size=10)

doc.save(OUT)
print("ok", OUT)
