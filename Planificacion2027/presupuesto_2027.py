#!/usr/bin/env python3
"""presupuesto_2027.py — genera el libro 'Presupuesto_Comercial_2027.xlsx' (3 países + grupo).

Uso:  python3 Planificacion2027/presupuesto_2027.py [carpeta_scratch_con_out_y_odoo]
Las cifras base 2025/2026E salen de Perseo (Ecuador) y Odoo (3 países), extraídas el 2026-11-06
con los scripts de Planificacion2027/analisis/. Todo supuesto editable vive en la hoja 'Supuestos'
(texto azul, fondo amarillo). Las hojas por país son fórmulas: cambiar un supuesto recalcula todo.
Salida: Planificacion2027/salida/Presupuesto_Comercial_2027.xlsx (carpeta ignorada por git).
"""
import sys, os, json, collections, datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.comments import Comment
from openpyxl.utils import get_column_letter as CL

ROOT=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(ROOT,"salida"); os.makedirs(OUT,exist_ok=True)
SCR=sys.argv[1] if len(sys.argv)>1 else None
F=lambda **k: Font(**{"name":"Arial","size":10,**k})
BLUE=F(color="0000FF"); BLACK=F(); BOLD=F(bold=True); HDR=F(bold=True,color="FFFFFF"); TITLE=F(bold=True,size=14); GREEN=F(color="008000")
YEL=PatternFill("solid",fgColor="FFFF00"); NAVY=PatternFill("solid",fgColor="1F3864"); GREY=PatternFill("solid",fgColor="F2F2F2"); LIGHT=PatternFill("solid",fgColor="D9E1F2")
thin=Side(style="thin",color="BFBFBF"); BOX=Border(left=thin,right=thin,top=thin,bottom=thin)
NUM='#,##0;(#,##0);-'; PCT='0.0%'; NUM1='#,##0.0;(#,##0.0);-'
MESES=["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]
wb=Workbook()

# ───────────────────────── SUPUESTOS ─────────────────────────
ws=wb.active; ws.title="Supuestos"
ws["A1"]="PRESUPUESTO COMERCIAL 2027 — GRUPO VICOMER · Supuestos"; ws["A1"].font=TITLE
ws["A2"]="Celdas azules sobre amarillo = editables. Todo lo demás es fórmula. Versión 2 (09-nov-2026): Perseo (EC 2021–jul 2026), Odoo con costo por compañía, maestro de importaciones armonizado y modelo HiHeat 2027–2029."; ws["A2"].font=F(italic=True,color="595959")
ws["A4"]="Escenario activo (1=Conservador, 2=Base, 3=Ambicioso)"; ws["B4"]=2; ws["B4"].font=BLUE; ws["B4"].fill=YEL
ws["A5"]="TRM COP/USD 2027 (presentación)"; ws["B5"]=3200; ws["B5"].font=BLUE; ws["B5"].fill=YEL; ws["B5"].comment=Comment("Odoo registra 3.185 al 14-oct-2026; corrida EEFF 26-oct usó 3.158,43. Supuesto conservador 3.200. Fuente: usuario/Banco de la República.","CFO")
ws["A6"]="Nombre escenario"; ws["B6"]='=INDEX({"Conservador","Base","Ambicioso"},1,$B$4)'
SEL="Supuestos!$B$4"
# tabla canales
r=8
ws.cell(r,1,"CANALES POR PAÍS — venta neta sin IVA, excluye intercompañía").font=BOLD; r+=1
hdr=["País","Canal / cuenta","Moneda","Real 2025","Est. 2026","Base 2027","Factor Conservador","Factor Base","Factor Ambicioso","Margen bruto objetivo","Costo comercial variable %","Crecimiento base vs 2026E","Nota"]
for j,h in enumerate(hdr,1):
    c=ws.cell(r,j,h); c.font=HDR; c.fill=NAVY; c.alignment=Alignment(wrap_text=True,vertical="center"); c.border=BOX
r+=1; CH_START=r
canales=[
 # pais, canal, moneda, real2025, est2026, base2027, fc, fb, fa, mb, var, nota
 ("Ecuador","Retail Sukasa (Comohogar)","USD",1123494,1195000,1255000,0.92,1.0,1.06,0.36,0.04,"68% de la venta 2025, ~65% 2026. Techo deliberado +5%: el crecimiento 2027 no puede depender de esta cuenta. Perseo+Odoo."),
 ("Ecuador","Proyectos (Prodesigns)","USD",148624,156000,185000,0.90,1.0,1.15,0.40,0.03,"Cuenta estable 9–14%. Crece con pipeline de edificios (CRM: Otero 3B 50k, Neo Muebles)."),
 ("Ecuador","Consumidor final + digital","USD",145215,200000,280000,0.85,1.0,1.20,0.48,0.06,"Ticket medio USD 815–990; 110–170 clientes nuevos/año con retención <15%. Palanca: e-commerce, marketplaces (lista D5), servicio técnico como puerta."),
 ("Ecuador","B2B / HORECA / constructoras","USD",116859,153000,215000,0.85,1.0,1.20,0.42,0.04,"Agroindustrias San Esteban, Semaica, hoteles, clubes. Canal de margen y menos concentración."),
 ("Ecuador","Otros retail y dealers","USD",99699,125000,215000,0.80,1.0,1.25,0.38,0.04,"Colineal, Favorita, Marcimex, Ecmercard, Crecoscorp. Objetivo: 2 cuentas nuevas con exhibición (lista D6)."),
 ("Ecuador","HiHeat empotrables (lanzamiento)","USD",None,0,300000,0.50,1.0,1.60,0.46,0.06,"Segundo motor. Modelo HiHeat 2027–2029 (Drive): 890 uds y USD 492 k en 2027. Base = 61 % del modelo porque ETD es 15-feb-2027 y falta INEN: venta desde mayo. MB 45,8 % del modelo. Curva propia de lanzamiento."),
 ("Colombia","Casa Magna","COP",None,881000000,980000000,0.90,1.0,1.10,0.48,0.04,"2026E = Q1 vintral1 186,6M + Odoo abr–oct 604,3M + nov–dic est. 90M. Condición: acuerdo marco firmado y cartera <60 d."),
 ("Colombia","USA Electrodomésticos","COP",None,579000000,640000000,0.90,1.0,1.10,0.48,0.03,"2026E = Q1 69,8M + abr–oct 449,2M + nov–dic est. 60M."),
 ("Colombia","Inverdescuentos","COP",None,40000000,60000000,0.85,1.0,1.20,0.48,0.03,"Tercera cuenta; hoy 2,4%."),
 ("Colombia","Kitchen Studios, especificadores y distribuidores nuevos","COP",None,12000000,250000000,0.40,1.0,1.60,0.45,0.06,"Batalla B1. 8 KS con exhibición y 20 especificadores activos a dic-2027 (doc 06). Condicionado a lista 2027 y acuerdo marco Casa Magna."),
 ("Colombia","Proyectos / constructoras / dealers","COP",None,0,90000000,0.50,1.0,1.50,0.50,0.04,"Canal nuevo con KAM. Sin histórico: cifra de arranque."),
 ("Costa Rica","Cemaco","USD",None,86680,170000,0.80,1.0,1.20,0.40,0.03,"2026: 1 pedido grande jun (84k) + oct. 2027 supone reposición trimestral con exhibición completa."),
 ("Costa Rica","Panafoto","USD",None,19068,70000,0.70,1.0,1.30,0.40,0.03,"Arrancó oct-2026 (2 entidades, 9,5k c/u)."),
 ("Costa Rica","Proyectos y dealers nuevos","USD",None,0,40000,0.40,1.0,1.50,0.40,0.05,"Sin histórico. Depende de contratar/asignar vendedor local o apoyo desde Ecuador."),
]
for p,cn,mo,r25,e26,b27,fc,fb,fa,mb,var,nota in canales:
    vals=[p,cn,mo,r25,e26,b27,fc,fb,fa,mb,var,None,nota]
    for j,v in enumerate(vals,1):
        c=ws.cell(r,j,v); c.border=BOX; c.font=BLACK
        if j in (4,5,6,7,8,9,10,11) and v is not None: c.font=BLUE; c.fill=YEL
        if j in (4,5,6): c.number_format=NUM
        if j in (7,8,9): c.number_format='0.00'
        if j in (10,11): c.number_format=PCT
    ws.cell(r,12,f"=IF(E{r}>0,F{r}/E{r}-1,\"n/a\")").number_format=PCT
    ws.cell(r,13).alignment=Alignment(wrap_text=True)
    r+=1
CH_END=r-1
ws.cell(CH_START,4).comment=Comment("Perseo: facturas − notas de crédito, sin IVA, por cliente. 2025 total Ecuador 1.649.918 incl. 16.026 intercompañía (excluida aquí).","CFO")
ws.cell(CH_START+5,5).comment=Comment("Colombia no tiene 2025 comparable: la instancia vintral1 (jun-2025–mar-2026) no es accesible desde la nube (falta ODOO_APIKEY_VINTRAL1). Q1-2026 por cliente reconstruido según Estructura_Felipe_Moreno (sep-2026).","CFO")
r+=1
ws.cell(r,1,"ESTACIONALIDAD (índice mensual, suma 12)").font=BOLD; r+=1
for j,h in enumerate(["País"]+MESES+["Suma","Fuente"],1):
    c=ws.cell(r,j,h); c.font=HDR; c.fill=NAVY; c.border=BOX
r+=1; SEAS={}
seas=[("Ecuador",[0.78,0.75,1.10,0.58,0.87,1.04,0.70,1.33,1.50,0.86,1.22,1.30],"Perseo 2023–2025, ventas netas mensuales / promedio"),
      ("Colombia",[0.70,0.75,0.95,0.95,1.15,1.15,0.85,0.95,1.05,1.00,1.25,1.25],"Supuesto retail CO (día de la madre, primas jun/dic, navidad). 2026 Odoo distorsionado por migración (abr)"),
      ("Costa Rica",[0.60,0.60,0.80,0.80,0.90,1.00,0.90,1.00,1.10,1.20,1.50,1.60],"Supuesto: pedidos por contenedor, peso Q4"),
      ("HiHeat",[0,0,0,0,0.60,1.10,1.20,1.40,1.70,1.70,2.00,2.30],"Curva de lanzamiento: ETD 15-feb, tránsito e INEN; venta desde mayo, rampa hasta diciembre")]
for p,idx,src in seas:
    ws.cell(r,1,p).border=BOX
    for j,v in enumerate(idx,2):
        c=ws.cell(r,j,v); c.font=BLUE; c.fill=YEL; c.number_format='0.00'; c.border=BOX
    ws.cell(r,14,f"=SUM(B{r}:M{r})").number_format='0.00'; ws.cell(r,15,src).font=F(italic=True,color="595959")
    SEAS[p]=r; r+=1
r+=1
ws.cell(r,1,"OTROS SUPUESTOS").font=BOLD; r+=1
otros=[("IVA Ecuador",0.15,PCT,"Para pasar a venta con IVA (cartera)"),("IVA Colombia",0.19,PCT,""),("IVA Costa Rica",0.13,PCT,""),
       ("DSO objetivo Ecuador (días)",35,'0',"Nov-2026: ~24 d sobre 90 d, 45% vencido"),("DSO objetivo Colombia (días)",60,'0',"Nov-2026: ~104 d, 61% vencido; Casa Magna 320M vencidos"),("DSO objetivo Costa Rica (días)",45,'0',"Nov-2026: 100% vencido"),
       ("Cobertura inventario objetivo Ecuador (meses)",5,'0.0',"Hoy: 56% del valor sin venta o >12 m de cobertura"),("Cobertura inventario objetivo Colombia (meses)",6,'0.0',"Hoy: ~12 m (701M COP vs COGS ~690M en 8 meses)"),
       ("Tasa máx. notas de crédito s/ventas",0.04,PCT,"Ecuador: 2,6% (2024) → 6,5% (2025) → 9,3% (ene–jul 2026)"),("Marketing (% venta)",0.03,PCT,"Tope grupo"),("Tope costo comercial variable por cuenta",0.06,PCT,"Regla Estructura_Felipe_Moreno §4.3"),
       ("Compra mínima Hyxion (USD/año, EC+CO+CR)",600000,NUM,"Contrato 16-oct-2024; terminación si <75% dos años seguidos")]
OT={}
for k,v,fmt,n in otros:
    ws.cell(r,1,k).border=BOX; c=ws.cell(r,2,v); c.font=BLUE; c.fill=YEL; c.number_format=fmt; c.border=BOX; ws.cell(r,3,n).font=F(italic=True,color="595959"); OT[k]=r; r+=1
ws.column_dimensions["A"].width=46; ws.column_dimensions["B"].width=34; ws.column_dimensions["C"].width=10
for col in "DEF": ws.column_dimensions[col].width=15
for col in "GHIJKL": ws.column_dimensions[col].width=12
ws.column_dimensions["M"].width=70
ws.freeze_panes="A10"

# ───────────────────────── HOJAS POR PAÍS ─────────────────────────
def hoja_pais(p, mon):
    w=wb.create_sheet(p)
    w["A1"]=f"PRESUPUESTO COMERCIAL 2027 — {p.upper()} ({mon}, venta neta sin IVA, sin intercompañía)"; w["A1"].font=TITLE
    w["A2"]='="Escenario: "&Supuestos!$B$6'; w["A2"].font=GREEN
    rows=[i for i in range(CH_START,CH_END+1) if canales[i-CH_START][0]==p]
    hdr=["Canal / cuenta","Real 2025","Est. 2026","Anual 2027 (escenario)","Δ vs 2026E"]+MESES+["Total 12m","Check","MB obj.","Margen bruto 2027","Costo com. variable"]
    for j,h in enumerate(hdr,1):
        c=w.cell(4,j,h); c.font=HDR; c.fill=NAVY; c.border=BOX; c.alignment=Alignment(wrap_text=True,horizontal="center")
    r=5; first=r
    for i in rows:
        sr=SEAS["HiHeat"] if "HiHeat" in canales[i-CH_START][1] else SEAS[p]
        w.cell(r,1,f"=Supuestos!B{i}").font=GREEN
        w.cell(r,2,f"=Supuestos!D{i}").font=GREEN; w.cell(r,3,f"=Supuestos!E{i}").font=GREEN
        w.cell(r,4,f"=Supuestos!F{i}*INDEX(Supuestos!G{i}:I{i},1,{SEL})")
        w.cell(r,5,f'=IF(C{r}>0,D{r}/C{r}-1,"n/a")').number_format=PCT
        for m in range(12):
            col=6+m; w.cell(r,col,f"=$D{r}*Supuestos!{CL(2+m)}${sr}/Supuestos!$N${sr}")
        w.cell(r,18,f"=SUM(F{r}:Q{r})"); w.cell(r,19,f'=IF(ABS(R{r}-D{r})<1,"ok","ERROR")')
        w.cell(r,20,f"=Supuestos!J{i}").font=GREEN; w.cell(r,20).number_format=PCT
        w.cell(r,21,f"=D{r}*T{r}"); w.cell(r,22,f"=D{r}*Supuestos!K{i}")
        for j in (2,3,4)+tuple(range(6,19))+(21,22): w.cell(r,j).number_format=NUM
        for j in range(1,23): w.cell(r,j).border=BOX
        r+=1
    last=r-1; w.cell(r,1,"TOTAL").font=BOLD
    for j in list(range(2,5))+list(range(6,19))+[21,22]:
        c=w.cell(r,j,f"=SUM({CL(j)}{first}:{CL(j)}{last})"); c.font=BOLD; c.number_format=NUM; c.fill=LIGHT; c.border=BOX
    w.cell(r,5,f'=IF(C{r}>0,D{r}/C{r}-1,"n/a")').number_format=PCT; w.cell(r,19,f'=IF(ABS(R{r}-D{r})<1,"ok","ERROR")')
    w.cell(r,20,f"=IF(D{r}>0,U{r}/D{r},0)").number_format=PCT
    TOT=r; r+=2
    w.cell(r,1,"Participación del cliente principal (%)").font=BOLD; w.cell(r,2,f"=IF(D{TOT}>0,MAX(D{first}:D{last})/D{TOT},0)").number_format=PCT
    w.cell(r,3,"Objetivo 2027: Ecuador ≤52% (con HiHeat) · Colombia ≤50% · Costa Rica ≤65%").font=F(italic=True,color="595959"); r+=1
    w.cell(r,1,"Venta acumulada mensual 2027").font=BOLD
    for m in range(12):
        c=w.cell(r,6+m,f"=SUM($F${TOT}:{CL(6+m)}${TOT})"); c.number_format=NUM
    r+=1
    w.cell(r,1,"Venta con IVA (base cartera)").font=BOLD
    iva={"Ecuador":"IVA Ecuador","Colombia":"IVA Colombia","Costa Rica":"IVA Costa Rica"}[p]
    for m in range(12):
        c=w.cell(r,6+m,f"={CL(6+m)}{TOT}*(1+Supuestos!$B${OT[iva]})"); c.number_format=NUM
    r+=1
    dso={"Ecuador":"DSO objetivo Ecuador (días)","Colombia":"DSO objetivo Colombia (días)","Costa Rica":"DSO objetivo Costa Rica (días)"}[p]
    w.cell(r,1,"Cartera objetivo al cierre de mes (venta c/IVA × DSO/30)").font=BOLD
    for m in range(12):
        c=w.cell(r,6+m,f"={CL(6+m)}{r-1}*Supuestos!$B${OT[dso]}/30"); c.number_format=NUM
    r+=2
    w.cell(r,1,"Lectura: el presupuesto 2026 de este país fue "+{"Ecuador":"USD 2.290.147 (cumplimiento ~82%)","Colombia":"COP 3.672 M (cumplimiento ~44% sin intercompañía)","Costa Rica":"USD 300.002 (cumplimiento ~35%)"}[p]+". El 2027 se construye desde el run-rate real, no desde el presupuesto anterior.").font=F(italic=True,color="595959")
    w.column_dimensions["A"].width=38
    for j in range(2,23): w.column_dimensions[CL(j)].width=13
    w.freeze_panes="B5"
    return TOT
TOT={p:hoja_pais(p,m) for p,m in [("Ecuador","USD"),("Colombia","COP"),("Costa Rica","USD")]}

# ───────────────────────── GRUPO USD ─────────────────────────
g=wb.create_sheet("Grupo USD")
g["A1"]="CONSOLIDADO GRUPO 2027 — USD de presentación (Colombia a TRM de Supuestos; no es consolidación contable, no elimina intercompañía porque ya está excluida)"; g["A1"].font=TITLE
g["A2"]='="Escenario: "&Supuestos!$B$6'; g["A2"].font=GREEN
hdr=["País","Est. 2026 USD","2027 USD","Δ%","Margen bruto 2027 USD","MB %"]+MESES+["Peso 2027"]
for j,h in enumerate(hdr,1):
    c=g.cell(4,j,h); c.font=HDR; c.fill=NAVY; c.border=BOX; c.alignment=Alignment(wrap_text=True,horizontal="center")
r=5
for p in ("Ecuador","Colombia","Costa Rica"):
    t=TOT[p]; div="/Supuestos!$B$5" if p=="Colombia" else ""
    g.cell(r,1,p).border=BOX
    g.cell(r,2,f"='{p}'!C{t}{div}"); g.cell(r,3,f"='{p}'!D{t}{div}"); g.cell(r,4,f'=IF(B{r}>0,C{r}/B{r}-1,"n/a")').number_format=PCT
    g.cell(r,5,f"='{p}'!U{t}{div}"); g.cell(r,6,f"=IF(C{r}>0,E{r}/C{r},0)").number_format=PCT
    for m in range(12): g.cell(r,7+m,f"='{p}'!{CL(6+m)}{t}{div}").number_format=NUM
    g.cell(r,19,f"=IF($C$8>0,C{r}/$C$8,0)").number_format=PCT
    for j in (2,3,5): g.cell(r,j).number_format=NUM
    for j in range(1,20): g.cell(r,j).border=BOX
    r+=1
g.cell(8,1,"GRUPO").font=BOLD
for j in [2,3,5]+list(range(7,19)):
    c=g.cell(8,j,f"=SUM({CL(j)}5:{CL(j)}7)"); c.font=BOLD; c.number_format=NUM; c.fill=LIGHT
g.cell(8,4,'=IF(B8>0,C8/B8-1,"n/a")').number_format=PCT; g.cell(8,6,"=IF(C8>0,E8/C8,0)").number_format=PCT
g["A10"]="Referencias"; g["A10"].font=BOLD
refs=[("Venta 2025 Ecuador (Perseo, sin IC)",1633892),("Venta grupo 2026E (USD ref.)","=B8"),("Compras a Hyxion implícitas 2027 (COGS ≈ venta − MB, −20% por reducción de inventario)","=(C8-E8)*0.8"),("Mínimo contractual Hyxion","=Supuestos!B"+str(OT["Compra mínima Hyxion (USD/año, EC+CO+CR)"])),("Cumple mínimo Hyxion","=IF(B13>=B14,\"Sí\",\"NO — revisar\")")]
for i,(k,v) in enumerate(refs):
    g.cell(11+i,1,k); c=g.cell(11+i,2,v); c.number_format=NUM
g.column_dimensions["A"].width=60
for j in range(2,20): g.column_dimensions[CL(j)].width=12

# ───────────────────────── ESCENARIOS ─────────────────────────
e=wb.create_sheet("Escenarios")
e["A1"]="RESUMEN DE ESCENARIOS 2027 (anual, moneda local; USD para grupo a TRM de Supuestos)"; e["A1"].font=TITLE
hdr=["País","Est. 2026","Conservador","Base","Ambicioso","Base vs 2026E","Moneda"]
for j,h in enumerate(hdr,1):
    c=e.cell(3,j,h); c.font=HDR; c.fill=NAVY; c.border=BOX
r=4
for p,mon in [("Ecuador","USD"),("Colombia","COP"),("Costa Rica","USD")]:
    rows=[i for i in range(CH_START,CH_END+1) if canales[i-CH_START][0]==p]
    e.cell(r,1,p).border=BOX; e.cell(r,2,"=SUM("+",".join(f"Supuestos!E{i}" for i in rows)+")").number_format=NUM
    for k,col in ((3,"G"),(4,"H"),(5,"I")):
        e.cell(r,k,"=SUMPRODUCT(Supuestos!F"+str(rows[0])+":F"+str(rows[-1])+",Supuestos!"+col+str(rows[0])+":"+col+str(rows[-1])+")").number_format=NUM
    e.cell(r,6,f'=IF(B{r}>0,D{r}/B{r}-1,"n/a")').number_format=PCT; e.cell(r,7,mon)
    for j in range(1,8): e.cell(r,j).border=BOX
    r+=1
e.cell(r,1,"Grupo USD").font=BOLD
for k in (2,3,4,5):
    c=e.cell(r,k,f"={CL(k)}4+{CL(k)}5/Supuestos!$B$5+{CL(k)}6"); c.number_format=NUM; c.font=BOLD; c.fill=LIGHT
e.cell(r,6,f'=IF(B{r}>0,D{r}/B{r}-1,"n/a")').number_format=PCT; e.cell(r,7,"USD")
e.cell(r+2,1,"Qué tiene que ser verdad para cada escenario").font=BOLD
txt=[("Conservador","Sukasa −8%, sin distribuidor nuevo en Colombia, Costa Rica solo Cemaco. Es el piso para dimensionar gastos fijos: la estructura debe ser rentable aquí."),
     ("Base","Sukasa +5%, 1 distribuidor nuevo en Colombia desde abril (tras reprecio y acuerdo marco Casa Magna), Panafoto activo, canal directo/digital +40% en Ecuador."),
     ("Ambicioso","Además: Corona o segundo distribuidor grande en CO, 2 dealers nuevos en EC con exhibición, tercer cliente en CR. Exige capital de trabajo adicional ≈ USD 150k (cartera + inventario)."),]
for i,(k,v) in enumerate(txt): e.cell(r+3+i,1,k).font=BOLD; e.cell(r+3+i,2,v)
e.column_dimensions["A"].width=16
for j in range(2,8): e.column_dimensions[CL(j)].width=18

# ───────────────────────── KPIs ─────────────────────────
k=wb.create_sheet("KPIs 2027")
k["A1"]="KPIs COMERCIALES Y DE CAPITAL DE TRABAJO 2027 — línea base nov-2026 vs objetivo"; k["A1"].font=TITLE
hdr=["KPI","Ecuador hoy","Ecuador 2027","Colombia hoy","Colombia 2027","Costa Rica hoy","Costa Rica 2027","Fuente / cómo se mide"]
for j,h in enumerate(hdr,1):
    c=k.cell(3,j,h); c.font=HDR; c.fill=NAVY; c.border=BOX; c.alignment=Alignment(wrap_text=True)
kp=[("Venta neta anual (moneda local)","1.83 M (2026E)","='Ecuador'!D"+str(TOT["Ecuador"]),"1.512 MM COP (2026E)","='Colombia'!D"+str(TOT["Colombia"]),"106 k (2026E)","='Costa Rica'!D"+str(TOT["Costa Rica"]),"Facturas − NC sin IVA, sin intercompañía (account.move)"),
    ("Peso del cliente principal",0.65,0.58,0.51,0.50,0.82,0.65,"Odoo por partner; Colombia: Casa Magna+USA = 89% → objetivo ≤80% combinados"),
    ("HHI de terceros",5379,3500,4787,3500,6881,5000,"Suma de cuotas² (≥2.500 = crítico)"),
    ("Margen bruto (costo real)",0.407,0.40,0.555,0.48,0.438,0.40,"Odoo ago–nov con standard_price leído por compañía; CO y CR completados con landed del maestro de importaciones. CO baja a propósito por el reprecio"),
    ("DSO (días)",24,35,104,60,172,45,"Cartera / venta c/IVA 90 d × 90"),
    ("% cartera vencida",0.45,0.15,0.61,0.20,1.0,0.20,"account.move residual vs fecha de vencimiento"),
    ("Tasa de notas de crédito",0.093,0.04,0.028,0.03,0.0,0.03,"EC ene–jul 2026 Perseo (5,7% ago–nov Odoo)"),
    ("Cobertura de inventario (meses)","~10 (56% muerto/lento)",5,"~12",6,0,2,"Stock / demanda 12 m por SKU"),
    ("Clientes activos (facturados en 12 m)",163,220,10,16,3,5,"Partners con factura en el año"),
    ("Retención de clientes >USD 500",0.14,0.30,"n/d",0.9,"n/d",1.0,"Clientes del año anterior que repiten"),
    ("Entregas a tiempo",0.27,0.85,0.40,0.85,"n/d",0.85,"stock.picking date_done ≤ scheduled_date"),
    ("Tickets de servicio abiertos >7 días",37,5,1,2,1,1,"helpdesk.ticket por etapa"),
    ("Venta sin costo estándar en Odoo (%)",0.06,0.0,0.0,0.0,0.18,0.0,"EC: XRD48E, TPG3601; CR: SRG3601. Leído por compañía (corrige la lectura del 06-nov)"),
    ("Puntos de venta con HiHeat empotrables",0,"—",0,"—",0,"—","Batalla B2: Sukasa + 3 retailers en EC a dic-2027"),
    ("Kitchen Studios con exhibición Thor","—","—",0,8,"—","—","Batalla B1"),
    ("Especificadores activos (1 proyecto facturado en 12 m)","—","—",0,20,"—","—","Batalla B1")]
for i,row in enumerate(kp):
    for j,v in enumerate(row,1):
        c=k.cell(4+i,j,v); c.border=BOX
        if isinstance(v,float) and v<=1.5: c.number_format=PCT
        elif isinstance(v,(int,float)): c.number_format=NUM
        if j in (3,5,7) and not (isinstance(v,str) and v.startswith("=")): c.font=BLUE; c.fill=YEL
k.column_dimensions["A"].width=42; k.column_dimensions["H"].width=70
for j in range(2,8): k.column_dimensions[CL(j)].width=18

# ───────────────────────── PLAN DE COMPRAS POR SKU ─────────────────────────
pc=wb.create_sheet("Plan compras SKU")
pc["A1"]="PLAN DE COMPRAS 2027 POR SKU (top 25 por venta) — demanda 12 m real × crecimiento − stock disponible"; pc["A1"].font=TITLE
pc["A2"]="Demanda EC = Perseo (nov-2025–jul-2026, prorrateado) + Odoo (ago–nov 2026). Demanda CO = Odoo abr–nov 2026 anualizado ×12/8. Stock = stock.quant ubicaciones internas al 06-nov-2026. Factor de crecimiento editable."; pc["A2"].font=F(italic=True,color="595959")
hdr=["País","SKU","Descripción","Demanda 12 m (uds)","Stock hoy (uds)","Cobertura (meses)","Factor crecimiento 2027","Demanda 2027","Stock seguridad (meses)","Compra sugerida 2027 (uds)","Costo std unit. (moneda local)","Compra sugerida (valor)"]
for j,h in enumerate(hdr,1):
    c=pc.cell(4,j,h); c.font=HDR; c.fill=NAVY; c.border=BOX; c.alignment=Alignment(wrap_text=True)
r=5
if SCR:
    L=lambda n: json.load(open(f"{SCR}/odoo/{n}.json"))
    inv={i["id"]:i for i in L("invoices")}; lines=L("invoice_lines"); prods={p["id"]:p for p in L("products")}; quants=L("quants"); locs={l["id"]:l for l in L("locations")}
    pr=json.load(open(f"{SCR}/out/perseo_ventas_an.json"))
    dem={2:collections.defaultdict(float),1:collections.defaultdict(float)}; rev={2:collections.defaultdict(float),1:collections.defaultdict(float)}; nm={}; cost={}
    for l in lines:
        i=inv.get(l["move_id"][0])
        if not i or i["move_type"] not in ("out_invoice","out_refund") or not l["product_id"] or i["company_id"][0] not in (1,2): continue
        p=prods.get(l["product_id"][0],{}); code=(p.get("default_code") or (p.get("name") or "")[:25]).upper(); sg=-1 if i["move_type"]=="out_refund" else 1
        c=i["company_id"][0]; f=1 if c==2 else 12/8
        dem[c][code]+=sg*l["quantity"]*f; rev[c][code]+=sg*l["price_subtotal"]*f; nm[code]=p.get("name") or ""; 
        if p.get("standard_price") and c==1: cost[(c,code)]=p["standard_price"]
    ALIAS={"TMO30":"TMO30H","TMO24":"TMO24H","IG-35":"IG35","IG-35P":"IG35","HRT3618U":"HRT3618U-M1","HRT4806U":"HRT4806U-M1","IG-25":"IG25","IG-55":"IG55","IG-10 1498900017010":"IG10","IGWI-A":"IGWIA","IG-BEER":"IGBEER","TIM15":"TIM1501"}
    def N(k2):
        k2=k2.upper().strip(); return ALIAS.get(k2, k2.replace("-","") if k2.startswith("IG-") else k2)
    for k2,v in pr["skus_anual"].get("2026",{}).items():
        kk=N(k2); dem[2][kk]+=v["q"]; rev[2][kk]+=v["rev"]; nm.setdefault(kk,v["nom"])
    for k2,v in pr["skus_anual"].get("2025",{}).items():
        kk=N(k2); dem[2][kk]+=v["q"]*2/12; rev[2][kk]+=v["rev"]*2/12; nm.setdefault(kk,v["nom"])
    # costo EC desde Perseo (costo unitario medio 2026)
    for k2,v in pr["skus_anual"].get("2026",{}).items():
        kk=N(k2)
        if v["q"]: cost[(2,kk)]=round(v["cost"]/v["q"],2)
    stock={2:collections.defaultdict(float),1:collections.defaultdict(float)}
    for q in quants:
        if locs.get(q["location_id"][0],{}).get("usage")!="internal" or not q["company_id"] or q["company_id"][0] not in (1,2): continue
        p=prods.get(q["product_id"][0],{}); code=(p.get("default_code") or (p.get("name") or "")[:25]).upper(); stock[q["company_id"][0]][code]+=q["quantity"]
    for c,p in ((2,"Ecuador"),(1,"Colombia")):
        top=sorted(rev[c].items(),key=lambda kv:-kv[1])[:25]
        for code,_ in top:
            d=max(dem[c][code],0); s=stock[c].get(code,0)
            vals=[p,code,nm.get(code,"")[:50],round(d),round(s),None,1.15,None,2,None,cost.get((c,code)),None]
            for j,v in enumerate(vals,1):
                cc=pc.cell(r,j,v); cc.border=BOX
                if j in (7,9): cc.font=BLUE; cc.fill=YEL
            pc.cell(r,6,f'=IF(D{r}>0,E{r}/(D{r}/12),"∞")').number_format='0.0'
            pc.cell(r,8,f"=D{r}*G{r}").number_format=NUM
            pc.cell(r,10,f"=MAX(0,ROUND(H{r}+H{r}/12*I{r}-E{r},0))").number_format=NUM
            pc.cell(r,11).number_format=NUM; pc.cell(r,12,f'=IF(ISNUMBER(K{r}),J{r}*K{r},"")').number_format=NUM
            r+=1
pc.column_dimensions["C"].width=52
for j in (1,2)+tuple(range(4,13)): pc.column_dimensions[CL(j)].width=14

# ───────────────────────── HISTÓRICO ─────────────────────────
h=wb.create_sheet("Histórico")
h["A1"]="HISTÓRICO VERIFICADO — base del presupuesto"; h["A1"].font=TITLE
h["A3"]="Ecuador (Perseo, USD sin IVA, facturas − NC). 2026 = ene–jul Perseo + ago–nov Odoo."; h["A3"].font=BOLD
hist=[("Año","Venta neta","Facturas","NC monto","NC %","Clientes","HHI","Cliente principal %","Margen bruto (mayor)","GV+GA","Resultado (mayor)","Resultado %"),
 ("2021",66520,69,0,None,56,478,0.17,0.470,3782,28939,None),("2022",236934,163,0,None,107,1003,0.246,0.515,27795,83166,None),
 ("2023",621442,378,-10841,None,234,2293,0.457,0.495,122563,170641,None),("2024",1205752,344,-31254,None,188,4569,0.662,0.413,393270,68659,None),
 ("2025",1649918,478,-108085,None,223,4738,0.681,0.397,535538,48916,None),("2026 ene–jul",1113374,324,-103089,None,163,4112,0.628,0.418,329144,98862,None),
 ("2026 ago–nov (Odoo)",503959,212,-30651,None,108,5379,0.711,None,None,None,None)]
for i,row in enumerate(hist):
    for j,v in enumerate(row,1):
        c=h.cell(4+i,j,v); c.border=BOX
        if i==0: c.font=HDR; c.fill=NAVY
        elif isinstance(v,float) and abs(v)<=1: c.number_format=PCT
        elif isinstance(v,(int,float)): c.number_format=NUM
    if i>0:
        h.cell(4+i,5,f"=IF(B{4+i}>0,-D{4+i}/B{4+i},0)").number_format=PCT
        h.cell(4+i,12,f'=IF(AND(ISNUMBER(K{4+i}),B{4+i}>0),K{4+i}/B{4+i},"")').number_format=PCT
r=4+len(hist)+2
h.cell(r,1,"Ecuador mensual (USD): 2024–2025 Perseo; 2026 ene–jul Perseo, ago–nov Odoo").font=BOLD; r+=1
for j,m in enumerate(["Año"]+MESES+["Total"],1):
    c=h.cell(r,j,m); c.font=HDR; c.fill=NAVY; c.border=BOX
r+=1
mens={"2024":[52888,43341,152284,52988,111328,57503,53125,190851,136040,105525,98796,151081],"2025":[158947,136774,125027,69604,124112,207674,122008,165139,185720,94714,129692,130507],"2026":[197352,84145,216967,56641,125162,332928,100178,158799,210190,123606,None,None]}
for y,vals in mens.items():
    h.cell(r,1,y).border=BOX
    for j,v in enumerate(vals,2):
        c=h.cell(r,j,v); c.number_format=NUM; c.border=BOX
    h.cell(r,14,f"=SUM(B{r}:M{r})").number_format=NUM; r+=1
h.cell(r,1,"Nota: 2024–2025 mensual sale del mayor (cuenta 41, asientos deduplicados), por eso el anual difiere ±0,1% de la suma de facturas.").font=F(italic=True,color="595959"); r+=2
h.cell(r,1,"Colombia mensual 2026 (COP, Odoo; Q1 desde vintral1 vía odoo_config.json)").font=BOLD; r+=1
for j,m in enumerate(["Concepto"]+MESES[:11],1):
    c=h.cell(r,j,m); c.font=HDR; c.fill=NAVY; c.border=BOX
r+=1
co=[("Total facturado",[121934422,82011091,58375628,329046932,121847882,159549377,60513538,192284140,203433276,123241883,2941176]),
    ("Casa Magna",[None,None,None,201700000,85200000,95400000,43800000,62900000,84800000,30500000,2900000]),
    ("USA Electrodomésticos",[None,None,None,112300000,36600000,59100000,15500000,17600000,115700000,92400000,0]),
    ("Intercompañía Vicomer",[0,0,0,0,0,0,0,100301041,0,0,0])]
for k2,vals in co:
    h.cell(r,1,k2).border=BOX
    for j,v in enumerate(vals,2):
        c=h.cell(r,j,v); c.number_format=NUM; c.border=BOX
    r+=1
h.cell(r,1,"Q1 por cliente: Casa Magna 186,6M · USA 69,8M · Inverdescuentos 5,9M (reconstrucción proporcional, Estructura_Felipe_Moreno sep-2026).").font=F(italic=True,color="595959"); r+=2
h.cell(r,1,"Costa Rica 2026 (USD, Odoo): jun 83.947 (Cemaco) · ago 2.250 · oct 19.551 (Panafoto 2×9.534 + Cemaco). Cartera 47.017, 100% vencida.").font=BOLD
h.column_dimensions["A"].width=26
for j in range(2,15): h.column_dimensions[CL(j)].width=13

# ───────────────────────── LEYENDA ─────────────────────────
ly=wb.create_sheet("Leyenda",0)
ly["A1"]="PRESUPUESTO COMERCIAL 2027 — GRUPO VICOMER"; ly["A1"].font=TITLE
lines=["Cómo usar este libro:",
"1. 'Supuestos': cambia el escenario (B4), la TRM (B5), las metas por canal (columna F), los factores por escenario (G–I), márgenes y estacionalidad. Celdas azules sobre amarillo.",
"2. 'Ecuador', 'Colombia', 'Costa Rica': se recalculan solas. La columna 'Check' debe decir ok en todas las filas.",
"3. 'Grupo USD': consolidado de presentación (Colombia a TRM). 'Escenarios': los tres casos lado a lado.",
"4. 'KPIs 2027': línea base medida en Odoo/Perseo al 06-nov-2026 y objetivo. 'Plan compras SKU': demanda real × crecimiento − stock.",
"5. 'Histórico': cifras verificadas que sostienen el presupuesto (Ecuador 2021–2026, Colombia 2026, Costa Rica 2026).",
"",
"Convenciones: venta neta sin IVA, sin intercompañía. Ecuador y Costa Rica en USD; Colombia en COP (USD solo referencial).",
"Fuente: Perseo API (facturas_consulta, asientoscontables_consulta) y Odoo XML-RPC (account.move, stock.quant, product). Extracción 2026-11-06.",
"Lo que NO está: ventas de Colombia jun-2025–dic-2025 (instancia vintral1 sin credencial en la nube); sell-out de Casa Magna (adjuntos NetSuite no accesibles por API).",
"Regenerar: python3 Planificacion2027/presupuesto_2027.py <carpeta con odoo/ y out/>"]
for i,t in enumerate(lines): ly.cell(3+i,1,t).font=BOLD if i==0 else BLACK
ly.column_dimensions["A"].width=140
for w in wb.worksheets:
    for row in w.iter_rows():
        for c in row:
            if c.font and c.font.name!="Arial": c.font=Font(name="Arial",size=c.font.size or 10,bold=c.font.bold,italic=c.font.italic,color=c.font.color)
out=os.path.join(OUT,"Presupuesto_Comercial_2027.xlsx"); wb.save(out); print("OK",out)
