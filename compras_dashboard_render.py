#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compras_dashboard_render.py  ·  Grupo VICOMER
=============================================
JSON -> dashboards HTML AUTOCONTENIDOS de compras locales y cuentas por pagar.

Genera CINCO archivos con el mismo motor:

    Dashboard_Compras_VICOMER.html            <- UNO SOLO con selector de pais (el que se usa)
    Dashboard_Compras_Ecuador.html
    Dashboard_Compras_Colombia.html
    Dashboard_Compras_CostaRica.html
    Dashboard_Compras_Consolidado_Grupo.html

El archivo unico es el mismo motor arrancando en el consolidado, con la barra de
paises siempre visible: se navega sin abrir otro archivo. Los cuatro individuales
existen para enlazarlos o publicarlos por separado.

Cada archivo lleva su CSS, su JS y sus datos embebidos: abre sin internet, sin CDN
y sin localStorage (eso rompe los artefactos publicados).

Uso:
    python3 compras_dashboard_render.py
    python3 compras_dashboard_render.py --json ruta.json --out carpeta

Solo biblioteca estandar.
"""
import os, sys, json, argparse
from pathlib import Path

HOME = Path.home()
PROJ = Path(os.environ.get("VICOMER_PROJ", HOME / "Claude" / "Projects" / "CFO VICOMER"))
OUT_DIR = Path(os.environ.get("ODOO_OUT_DIR", PROJ / "OdooVentas"))

SALIDAS = [
    ("__CONSOLIDADO__", "Dashboard_Compras_VICOMER.html",            "Compras y CxP - Grupo VICOMER"),
    ("__CONSOLIDADO__", "Dashboard_Compras_Consolidado_Grupo.html",  "Compras y CxP - Consolidado Grupo VICOMER"),
    ("Ecuador",         "Dashboard_Compras_Ecuador.html",            "Compras y CxP - Ecuador | Grupo VICOMER"),
    ("Colombia",        "Dashboard_Compras_Colombia.html",           "Compras y CxP - Colombia | Grupo VICOMER"),
    ("Costa Rica",      "Dashboard_Compras_CostaRica.html",          "Compras y CxP - Costa Rica | Grupo VICOMER"),
]

HEAD = r"""<!DOCTYPE html>
<html lang="es" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>__TITULO__</title>
<style>
:root{
  --surface-0:#0b0d10; --surface-1:#101216; --surface-2:#171a1f; --surface-3:#1e222a;
  --line:#272c35; --line-soft:#1c2027;
  --text-primary:#f2f4f7; --text-secondary:#a5adbb; --text-muted:#6b7482;
  --series-1:#3987e5; --series-2:#d95926; --series-3:#199e70;
  --good:#0ca30c; --warning:#fab219; --serious:#ec835a; --critical:#d03b3b;
  --age-0:#184f95; --age-1:#256abf; --age-2:#3987e5; --age-3:#6da7ec; --age-4:#9ec5f4;
  --mono:ui-monospace,"SF Mono",Menlo,Consolas,"Roboto Mono",monospace;
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,Helvetica,Arial,sans-serif;
  --cond:"SF Compact Display","Roboto Condensed","Helvetica Neue",var(--sans);
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{background:var(--surface-0);color:var(--text-primary);font-family:var(--sans);
  font-size:14px;line-height:1.45;-webkit-font-smoothing:antialiased;padding-bottom:64px}
.wrap{max-width:1360px;margin:0 auto;padding:0 20px}
a{color:var(--series-1)}
h1,h2,h3{margin:0;font-weight:600;letter-spacing:-.01em}

/* ---------- A. barra de estado ---------- */
.statusbar{position:sticky;top:0;z-index:40;background:rgba(11,13,16,.93);
  backdrop-filter:saturate(140%) blur(10px);border-bottom:1px solid var(--line)}
.statusbar .inner{max-width:1360px;margin:0 auto;padding:10px 20px;display:flex;
  gap:14px;align-items:center;flex-wrap:wrap;font-size:12px;color:var(--text-secondary)}
.brand{font-family:var(--cond);font-size:15px;font-weight:700;letter-spacing:.06em;
  text-transform:uppercase;color:var(--text-primary);margin-right:4px}
.chip{display:inline-flex;align-items:center;gap:6px;padding:3px 9px;border:1px solid var(--line);
  border-radius:999px;background:var(--surface-2);white-space:nowrap}
.chip b{color:var(--text-primary);font-weight:600}
.chip.tc{border-color:#3a3f2a;color:var(--warning)}
.chip.avisos{cursor:pointer;border-color:#4a2a2a;color:var(--serious)}
.chip.avisos:hover{background:var(--surface-3)}
.chip.ok{border-color:#1f3a24;color:var(--good)}
.dot{width:7px;height:7px;border-radius:50%;display:inline-block}

/* ---------- tabs ---------- */
.tabs{display:flex;gap:2px;overflow-x:auto;border-bottom:1px solid var(--line);
  margin:0 0 18px;scrollbar-width:none}
.tabs::-webkit-scrollbar{display:none}
.tab{appearance:none;background:none;border:0;border-bottom:2px solid transparent;
  color:var(--text-secondary);font:inherit;font-size:13px;padding:11px 14px;cursor:pointer;white-space:nowrap}
.tab:hover{color:var(--text-primary)}
.tab[aria-selected="true"]{color:var(--text-primary);border-bottom-color:var(--series-1);font-weight:600}
.panel[hidden]{display:none}

/* ---------- header ---------- */
header.page{padding:22px 0 14px}
header.page h1{font-family:var(--cond);font-size:26px;letter-spacing:-.02em}
header.page .sub{color:var(--text-secondary);font-size:13px;margin-top:4px}

/* ---------- controles ---------- */
.controls{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:0 0 16px}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:8px;overflow:hidden;background:var(--surface-2)}
.seg button{appearance:none;background:none;border:0;color:var(--text-secondary);font:inherit;
  font-size:12px;padding:6px 11px;cursor:pointer}
.seg button+button{border-left:1px solid var(--line)}
.seg button[aria-pressed="true"]{background:var(--surface-3);color:var(--text-primary);font-weight:600}
.seg button:hover{color:var(--text-primary)}
.ctl-label{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--text-muted);margin-right:2px}
.btn{appearance:none;background:var(--surface-2);border:1px solid var(--line);color:var(--text-secondary);
  font:inherit;font-size:12px;padding:6px 11px;border-radius:8px;cursor:pointer}
.btn:hover{color:var(--text-primary);border-color:var(--text-muted)}

/* ---------- KPI ---------- */
.kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin:0 0 20px}
.kpi{background:var(--surface-1);border:1px solid var(--line);border-radius:12px;padding:13px 14px;
  display:flex;flex-direction:column;gap:6px;min-height:118px;position:relative;overflow:hidden}
.kpi .lab{font-size:10.5px;text-transform:uppercase;letter-spacing:.09em;color:var(--text-muted);
  font-weight:600;line-height:1.25}
.kpi .val{font-family:var(--cond);font-size:27px;font-weight:700;letter-spacing:-.03em;
  line-height:1;font-variant-numeric:tabular-nums;color:var(--text-primary)}
.kpi .val.sm{font-size:21px}
.kpi .cmp{font-size:11.5px;color:var(--text-secondary);font-variant-numeric:tabular-nums;
  display:flex;align-items:center;gap:5px;flex-wrap:wrap}
.kpi .spark{margin-top:auto;height:26px}
.kpi.nd .val{color:var(--text-muted)}
.kpi .flag{position:absolute;top:0;left:0;width:3px;height:100%}
.up{color:var(--good)} .down{color:var(--critical)} .warn{color:var(--warning)} .mut{color:var(--text-muted)}
.badge{font-size:9.5px;text-transform:uppercase;letter-spacing:.07em;border:1px solid var(--line);
  border-radius:4px;padding:1px 5px;color:var(--text-muted);white-space:nowrap}
.badge.tc{border-color:#4a412a;color:var(--warning)}
.badge.nd{border-color:#4a3030;color:var(--serious)}

/* ---------- cards ---------- */
.card{background:var(--surface-1);border:1px solid var(--line);border-radius:12px;
  padding:16px 16px 12px;margin:0 0 16px}
.card>h2{font-family:var(--cond);font-size:16px;letter-spacing:-.01em}
.card>.hint{color:var(--text-secondary);font-size:12px;margin:3px 0 12px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.readout{margin:10px 0 2px;padding:9px 11px;background:var(--surface-2);border-left:2px solid var(--series-1);
  border-radius:0 6px 6px 0;font-size:12.5px;color:var(--text-secondary);line-height:1.5}
.readout b{color:var(--text-primary);font-weight:600}
.nodata{border:1px dashed #4a3030;background:#1a1214;border-radius:10px;padding:16px;color:var(--serious);font-size:13px}
.nodata h3{font-size:13px;color:var(--serious);margin-bottom:6px;display:flex;gap:7px;align-items:center}
.nodata p{margin:0 0 6px;color:var(--text-secondary)}
.nodata .need{color:var(--text-muted);font-size:12px}

/* ---------- svg ---------- */
svg{display:block;width:100%;overflow:visible}
.ax{font-size:10px;fill:var(--text-muted);font-variant-numeric:tabular-nums}
.gl{stroke:var(--line-soft);stroke-width:1}
.axline{stroke:var(--line);stroke-width:1}
.dlabel{font-size:10px;fill:var(--text-secondary);font-variant-numeric:tabular-nums}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:11.5px;color:var(--text-secondary);margin:8px 0 2px}
.legend i{width:9px;height:9px;border-radius:2px;display:inline-block;margin-right:5px;vertical-align:-1px}
.legend .ln{width:14px;height:0;border-top:2px dashed var(--text-secondary);display:inline-block;margin-right:5px;vertical-align:3px}

/* ---------- tablas ---------- */
.tblwrap{overflow-x:auto;margin-top:10px;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-size:12.5px;font-variant-numeric:tabular-nums}
th,td{padding:7px 9px;text-align:right;border-bottom:1px solid var(--line-soft);white-space:nowrap}
th:first-child,td:first-child{text-align:left;white-space:normal;min-width:150px}
thead th{position:sticky;top:0;background:var(--surface-2);color:var(--text-muted);font-size:10.5px;
  text-transform:uppercase;letter-spacing:.06em;cursor:pointer;user-select:none;z-index:2}
thead th:hover{color:var(--text-primary)}
thead th .ar{opacity:.4;font-size:9px}
tbody tr:hover{background:var(--surface-2)}
td.neg{color:var(--critical)} td.pos{color:var(--good)}
td .mini{display:inline-block;height:6px;border-radius:2px;background:var(--series-1);vertical-align:1px}

/* ---------- integridad ---------- */
details.integrity{background:var(--surface-1);border:1px solid var(--line);border-radius:12px;padding:0;margin:22px 0 0}
details.integrity>summary{cursor:pointer;padding:14px 16px;font-family:var(--cond);font-size:15px;
  font-weight:600;list-style:none;display:flex;justify-content:space-between;align-items:center}
details.integrity>summary::-webkit-details-marker{display:none}
details.integrity>summary::after{content:"▾";color:var(--text-muted);font-size:12px}
details.integrity[open]>summary::after{content:"▴"}
.integrity .body{padding:0 16px 16px}
.aviso{display:flex;gap:10px;padding:9px 0;border-top:1px solid var(--line-soft);font-size:12.5px}
.aviso .lv{flex:0 0 74px;font-size:10px;text-transform:uppercase;letter-spacing:.07em;font-weight:700;padding-top:2px}
.aviso .lv.critico{color:var(--critical)} .aviso .lv.alerta{color:var(--warning)} .aviso .lv.nota{color:var(--text-muted)}
.aviso .tx{color:var(--text-secondary)}
.aviso .tx b{color:var(--text-primary);font-weight:600}
.srcgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:10px;margin-top:12px}
.src{background:var(--surface-2);border:1px solid var(--line);border-radius:8px;padding:10px 12px;font-size:12px}
.src .k{color:var(--text-muted);font-size:10px;text-transform:uppercase;letter-spacing:.07em}
.src .v{color:var(--text-secondary);margin-top:3px;word-break:break-word}


/* ---------- compras: extras ---------- */
.scopebar{display:flex;gap:2px;background:var(--surface-2);border:1px solid var(--line);border-radius:8px;padding:2px}
.scopebar button{appearance:none;background:none;border:0;color:var(--text-secondary);font:inherit;font-size:12px;
  padding:5px 12px;border-radius:6px;cursor:pointer;white-space:nowrap}
.scopebar button[aria-pressed="true"]{background:var(--series-1);color:#fff;font-weight:600}
.scopebar button:hover{color:var(--text-primary)}
.scopebar button[aria-pressed="true"]:hover{color:#fff}
.tres{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:0 0 16px}
.tres .m{background:var(--surface-1);border:1px solid var(--line);border-radius:12px;padding:14px 15px;position:relative}
.tres .m .lab{font-size:10.5px;text-transform:uppercase;letter-spacing:.09em;color:var(--text-muted);font-weight:600}
.tres .m .val{font-family:var(--cond);font-size:26px;font-weight:700;letter-spacing:-.03em;margin:5px 0 3px;
  font-variant-numeric:tabular-nums}
.tres .m .exp{font-size:11.5px;color:var(--text-secondary);line-height:1.4}
.tres .m::after{content:"";position:absolute;top:14px;right:14px;width:8px;height:8px;border-radius:2px}
.tres .m.flujo::after{background:var(--series-1)} .tres .m.stock::after{background:var(--series-2)}
.tres .m.caja::after{background:var(--series-3)}
.warnbox{border:1px solid #4a412a;background:#1a1710;border-radius:10px;padding:12px 14px;margin:0 0 14px;font-size:12.5px;color:var(--text-secondary)}
.warnbox b{color:var(--warning)}
.exgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px;margin:8px 0 4px}
.ex{background:var(--surface-2);border:1px solid var(--line);border-radius:10px;padding:11px 13px}
.ex .k{font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:var(--text-muted);font-weight:600}
.ex .v{font-family:var(--cond);font-size:20px;font-weight:700;margin:4px 0 2px;font-variant-numeric:tabular-nums}
.ex .n{font-size:11px;color:var(--text-muted)}
.ex.alerta{border-color:#4a3030}.ex.alerta .v{color:var(--serious)}
.esc{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;margin:10px 0 4px}
.esc .e{background:var(--surface-2);border:1px solid var(--line);border-left:3px solid var(--series-2);border-radius:8px;padding:11px 13px}
.esc .e .t{font-size:12px;font-weight:600;color:var(--text-primary);margin-bottom:5px}
.esc .e .v{font-family:var(--cond);font-size:22px;font-weight:700;font-variant-numeric:tabular-nums}
.esc .e .d{font-size:11.5px;color:var(--text-secondary);margin-top:3px;line-height:1.4}
.quad{font-size:10.5px;fill:var(--text-muted)}
@media (max-width:900px){.tres{grid-template-columns:1fr}}

/* ---------- tooltip ---------- */
#tip{position:fixed;pointer-events:none;z-index:99;background:var(--surface-3);border:1px solid var(--line);
  border-radius:8px;padding:8px 10px;font-size:12px;box-shadow:0 8px 26px rgba(0,0,0,.55);
  opacity:0;transition:opacity .09s;max-width:280px;font-variant-numeric:tabular-nums}
#tip.on{opacity:1}
#tip .t{color:var(--text-primary);font-weight:600;margin-bottom:3px}
#tip .r{color:var(--text-secondary);display:flex;justify-content:space-between;gap:14px}
#tip .r b{color:var(--text-primary);font-weight:600}
.foot{color:var(--text-muted);font-size:11.5px;margin:26px 0 0;line-height:1.6}

@media (max-width:1100px){.kpis{grid-template-columns:repeat(3,1fr)}.grid2{grid-template-columns:1fr}}
@media (max-width:640px){
  .wrap{padding:0 12px}.kpis{grid-template-columns:repeat(2,1fr);gap:8px}
  .kpi .val{font-size:22px}header.page h1{font-size:20px}
  .statusbar .inner{padding:8px 12px;gap:8px;font-size:11px}
  th:first-child,td:first-child{min-width:118px}
  .card{padding:13px 12px 10px}
}
@media print{
  body{background:#fff;color:#000;padding:0}
  .statusbar{position:static;background:#fff;border-color:#bbb}
  .tabs,.controls,.btn,.seg{display:none!important}
  .panel[hidden]{display:block!important}
  .card,.kpi,details.integrity{background:#fff;border-color:#bbb;break-inside:avoid;page-break-inside:avoid}
  .kpi .val,.brand,h1,h2,#tip .t{color:#000}
  .kpi .lab,.card>.hint,.readout,.aviso .tx,.src .v{color:#333}
  .readout{background:#f4f4f4}
  details.integrity{page-break-before:always}
  details.integrity[open]>summary::after{content:""}
  .nodata{background:#fff;border-color:#900;color:#900}
  #tip{display:none}
  .ax,.dlabel{fill:#444}
}
</style>
</head>
<body>
<div id="tip"></div>
"""

JS = r"""/* ===================================================================
   Motor de dashboards de ventas — Grupo VICOMER
   Sin dependencias externas. Todo el estado en variables JS
   (nada de localStorage: rompe el artefacto).
   =================================================================== */
(function(){
"use strict";
var D = window.__DATA__;
var SCOPE = window.__SCOPE__;
function esCons(){return SCOPE === "__CONSOLIDADO__";}
var MESES = D.meses;
var ORDEN = ["Ecuador","Colombia","Costa Rica"];
var TIP = document.getElementById("tip");

/* ---------- estado ---------- */
var ST = { periodo:"ytd", moneda:"local", sort:{}, incluirSinClasificar:false, depto:null };

/* ---------- utilidades ---------- */
function el(t,a,c){var e=document.createElement(t);if(a)for(var k in a){
  if(k==="html")e.innerHTML=a[k];else if(k==="text")e.textContent=a[k];
  else if(k.slice(0,2)==="on")e.addEventListener(k.slice(2),a[k]);else e.setAttribute(k,a[k]);}
  if(c)(Array.isArray(c)?c:[c]).forEach(function(x){if(x==null)return;
    e.appendChild(typeof x==="string"?document.createTextNode(x):x);});return e;}
function S(t,a){var e=document.createElementNS("http://www.w3.org/2000/svg",t);
  if(a)for(var k in a)e.setAttribute(k,a[k]);return e;}
function nn(v){return v!==null&&v!==undefined&&!(typeof v==="number"&&isNaN(v));}

var TC = D.tc.tasas||{};
function toUSD(v,cur){if(!nn(v))return null;var t=TC[cur];return t==null?null:v*t;}
function curOf(p){return ST.moneda==="usd"?"USD":(p&&p.moneda)||"USD";}
function conv(v,p){if(!nn(v))return null;return ST.moneda==="usd"?toUSD(v,p.moneda):v;}

function money(v,cur,compact){
  if(!nn(v))return "—";
  var neg=v<0, a=Math.abs(v), s;
  if(compact){
    if(a>=1e9)s=(a/1e9).toFixed(a/1e9<10?2:1)+" MM";
    else if(a>=1e6)s=(a/1e6).toFixed(a/1e6<10?2:1)+" M";
    else if(a>=1e3)s=(a/1e3).toFixed(a/1e3<100?1:0)+" k";
    else s=a.toFixed(0);
  } else s=a.toLocaleString("es-EC",{maximumFractionDigits:0});
  if(cur==="USD")return (neg?"−":"")+"$"+s;
  if(cur==="CRC")return (neg?"−":"")+"₡"+s;
  return (neg?"−":"")+s+(cur?" "+cur:"");
}
function pctf(v,dec){if(!nn(v))return "—";return (v*100).toFixed(dec===undefined?1:dec).replace(".",",")+"%";}
function ppf(v){if(!nn(v))return "—";return (v>=0?"+":"−")+Math.abs(v*100).toFixed(1).replace(".",",")+" pp";}
function num(v,d){if(!nn(v))return "—";return v.toLocaleString("es-EC",{maximumFractionDigits:d===undefined?0:d});}
function fecha(s){if(!s)return "—";var p=String(s).slice(0,10).split("-");return p[2]+"/"+p[1]+"/"+p[0];}

/* semáforo de cumplimiento */
function sem(v){if(!nn(v))return "mut";return v>=1?"up":(v>=0.85?"warn":"down");}
function semColor(v){if(!nn(v))return "var(--text-muted)";
  return v>=1?"var(--good)":(v>=0.85?"var(--warning)":"var(--critical)");}

/* ---------- tooltip ---------- */
function tipOn(ev,title,rows){
  TIP.innerHTML="";
  TIP.appendChild(el("div",{"class":"t",text:title}));
  (rows||[]).forEach(function(r){
    TIP.appendChild(el("div",{"class":"r"},[el("span",{text:r[0]}),el("b",{text:r[1]})]));});
  TIP.classList.add("on"); tipMove(ev);
}
function tipMove(ev){
  var x=ev.clientX+14,y=ev.clientY+14,w=TIP.offsetWidth,h=TIP.offsetHeight;
  if(x+w>innerWidth-8)x=ev.clientX-w-14;
  if(y+h>innerHeight-8)y=ev.clientY-h-14;
  TIP.style.left=x+"px";TIP.style.top=y+"px";
}
function tipOff(){TIP.classList.remove("on");}
function hover(node,title,rows){
  node.addEventListener("mouseenter",function(e){tipOn(e,title,rows);});
  node.addEventListener("mousemove",tipMove);
  node.addEventListener("mouseleave",tipOff);
  node.style.cursor="crosshair";
}

/* ---------- escalas ---------- */
function nice(max){
  if(!(max>0))return 1;
  var e=Math.pow(10,Math.floor(Math.log(max)/Math.LN10)),f=max/e;
  var m=f<=1?1:f<=2?2:f<=2.5?2.5:f<=5?5:10;return m*e;
}
function ticks(max,n){var out=[];for(var i=0;i<=n;i++)out.push(max*i/n);return out;}

/* ---------- chart host (responsive real: re-render on resize) ---------- */
var CHARTS=[];
function chartHost(h,draw){
  var box=el("div",{"class":"chartbox"});
  var render=function(){
    var w=box.clientWidth||box.parentNode&&box.parentNode.clientWidth||700;
    if(w<220)w=220;
    box.innerHTML=""; box.appendChild(draw(w,h(w)));
  };
  CHARTS.push(render);
  setTimeout(render,0);
  return box;
}
var rt; addEventListener("resize",function(){clearTimeout(rt);rt=setTimeout(function(){
  CHARTS.forEach(function(f){try{f();}catch(e){}});},160);});

/* ===================================================================
   GRÁFICO C — real (barras) vs presupuesto (línea)
   =================================================================== */
/* ===================================================================
   GRÁFICO D1 — venta neta (barras) / D2 — margen % (línea). Ejes separados.
   =================================================================== */
/* ===================================================================
   GRÁFICO D3 — mix por producto (barras horizontales)
   =================================================================== */
/* ===================================================================
   GRÁFICO E — aging apilado por cliente
   =================================================================== */
var BK=["Corriente","1-30","31-60","61-90",">90"];
var BKC=["var(--age-0)","var(--age-1)","var(--age-2)","var(--age-3)","var(--age-4)"];
function spark(vals,color,hasta){
  var v=vals.slice(0,hasta==null?vals.length:hasta).filter(nn);
  var box=el("div",{"class":"spark"});
  if(v.length<2)return box;
  var w=140,h=26,lo=Math.min.apply(null,v.concat([0])),hi=Math.max.apply(null,v);
  if(hi===lo)hi=lo+1;
  var g=S("svg",{viewBox:"0 0 "+w+" "+h,preserveAspectRatio:"none",height:h});
  var d="",ar="";
  v.forEach(function(q,i){var X=i/(v.length-1)*w,Y=h-2-((q-lo)/(hi-lo))*(h-4);
    d+=(i?"L":"M")+X+" "+Y;ar+=(i?"L":"M")+X+" "+Y;});
  ar+="L"+w+" "+h+"L0 "+h+"Z";
  g.appendChild(S("path",{d:ar,fill:color||"var(--series-1)",opacity:.14}));
  g.appendChild(S("path",{d:d,fill:"none",stroke:color||"var(--series-1)","stroke-width":1.6,
    "vector-effect":"non-scaling-stroke","stroke-linejoin":"round"}));
  box.appendChild(g);return box;
}

/* ---------- tablas ordenables + CSV ---------- */
function tabla(id,cols,rows,cellFns){
  var t=el("table",{id:id}),th=el("thead"),tr=el("tr");
  cols.forEach(function(c,i){
    var h=el("th",{},[c.t,el("span",{"class":"ar",text:" ⇅"})]);
    h.addEventListener("click",function(){
      var cur=ST.sort[id]||{}; var asc=(cur.i===i)?!cur.asc:false;
      ST.sort[id]={i:i,asc:asc};
      rows.sort(function(a,b){var A=a[c.k],B=b[c.k];
        if(A==null)A=asc?Infinity:-Infinity; if(B==null)B=asc?Infinity:-Infinity;
        if(typeof A==="string")return asc?String(A).localeCompare(B):String(B).localeCompare(A);
        return asc?A-B:B-A;});
      draw();
    });
    tr.appendChild(h);
  });
  th.appendChild(tr);t.appendChild(th);
  var tb=el("tbody");t.appendChild(tb);
  function draw(){
    tb.innerHTML="";
    rows.forEach(function(r){
      var x=el("tr");
      cols.forEach(function(c,i){
        var td=el("td");
        var out=cellFns[i](r);
        if(typeof out==="string")td.textContent=out; else if(out)td.appendChild(out);
        if(c.cls){var k=c.cls(r);if(k)td.className=k;}
        x.appendChild(td);
      });
      tb.appendChild(x);
    });
  }
  draw();
  t.__csv=function(){
    var out=[cols.map(function(c){return '"'+c.t+'"';}).join(";")];
    rows.forEach(function(r){out.push(cols.map(function(c){
      var v=r[c.k];return typeof v==="number"?String(v).replace(".",","):'"'+String(v==null?"":v)+'"';}).join(";"));});
    return out.join("\n");
  };
  return el("div",{"class":"tblwrap"},t);
}
function csvBtn(wrapEl,nombre){
  return el("button",{"class":"btn",onclick:function(){
    var t=wrapEl.querySelector("table"); if(!t||!t.__csv)return;
    var blob=new Blob(["﻿"+t.__csv()],{type:"text/csv;charset=utf-8"});
    var a=el("a",{href:URL.createObjectURL(blob),download:nombre+".csv"});
    document.body.appendChild(a);a.click();a.remove();
  },text:"Exportar CSV"});
}


/* ---------- helpers de scope ---------- */
function P(){ return D.paises[SCOPE] || null; }
function card(t,h,k){var c=el("div",{"class":"card"},[el("h2",{text:t})]);
  if(h)c.appendChild(el("div",{"class":"hint",text:h}));
  (Array.isArray(k)?k:[k]).forEach(function(x){if(x)c.appendChild(x);});return c;}
function lectura(html,color){var d=el("div",{"class":"readout",html:html});
  if(color)d.style.borderLeftColor=color;return d;}
function sinDato(t,m,n){return el("div",{"class":"nodata"},[el("h3",{},["⚠ ",t]),
  el("p",{text:m||""}),n?el("div",{"class":"need",text:"Qué hace falta: "+n}):null]);}

/* ===================================================================
   A. BARRA DE ESTADO — con selector de país (un solo archivo)
   =================================================================== */
function statusBar(){
  var av=D.avisos||[], crit=av.filter(function(a){return a.nivel==="critico";}).length;
  var cob=D.cobertura_clasificacion||{};
  var exc=0, nexc=0;
  ORDEN.forEach(function(k){var p=D.paises[k];if(!p)return;
    var e=p.excluido||{};
    ["importacion","servicios_exterior"].forEach(function(t){
      var u=toUSD((e[t]||{}).monto,p.moneda); if(u)exc+=u; nexc+=(e[t]||{}).n||0;});});
  var sel=el("div",{"class":"scopebar"});
  [["__CONSOLIDADO__","Grupo"]].concat(ORDEN.map(function(k){return [k,k];})).forEach(function(o){
    if(o[0]!=="__CONSOLIDADO__" && !D.paises[o[0]])return;
    sel.appendChild(el("button",{text:o[1],"aria-pressed":SCOPE===o[0]?"true":"false",
      onclick:function(){SCOPE=o[0];ST.moneda="local";boot();}}));});
  var frescura=null;
  var av3=av.filter(function(a){return a.bloque==="cxp";})[0];
  var inner=el("div",{"class":"inner"},[
    el("span",{"class":"brand",text:"VICOMER"}),
    sel,
    el("span",{"class":"chip"},[el("span",{"class":"dot",style:"background:var(--good)"}),
      el("span",{},["Datos al "]),el("b",{text:fecha(D.generado_fecha)})]),
    el("span",{"class":"chip"+(cob.cobertura>=0.95?"":" avisos")},
      ["Proveedores clasificados: ",el("b",{text:pctf(cob.cobertura,1)})]),
    exc?el("span",{"class":"chip",title:"Compras de proveedores del exterior, fuera del dashboard de compras locales"},
      ["Excluido por exterior: ",el("b",{text:money(exc,"USD",true)}),el("span",{"class":"mut",text:" · "+nexc+" docs"})]):null,
    el("span",{"class":"chip tc"},["TC referencial: COP "+num(D.tc.cop_por_usd)+" · CRC "+num(D.tc.crc_por_usd)]),
    el("span",{"class":av.length?"chip avisos":"chip ok",onclick:function(){
      var d=document.getElementById("integridad");if(d){d.open=true;d.scrollIntoView({behavior:"smooth"});}}},
      [av.length?(av.length+" aviso"+(av.length>1?"s":"")+(crit?" · "+crit+" crítico"+(crit>1?"s":""):"")):"sin avisos"])
  ].filter(Boolean));
  return el("div",{"class":"statusbar"},inner);
}

/* ===================================================================
   Las tres métricas que nunca se suman
   =================================================================== */
function tresMetricas(){
  var box=el("div",{"class":"tres"});
  var cur, compra, cxp, pagos, sub1, sub2, sub3;
  if(esCons()){
    var c=D.consolidado; cur="USD";
    compra=c.compra_ytd; cxp=c.cxp_total; pagos=c.pagos_ytd;
    sub1="Suma de los 3 países en USD referencial";
    sub2=pctf(c.pct_vencido,0)+" vencido";
    sub3="Salida de caja del año";
  } else {
    var p=P(); cur=curOf(p);
    compra=conv(p.compra.total_ytd,p); cxp=conv(p.cxp.total,p); pagos=conv(p.pagos.ytd,p);
    sub1=num(p.compra.n_docs_total)+" facturas de proveedor · de las cuales "+
      money(conv(p.compra.ytd,p),cur,true)+" es compra LOCAL operativa";
    sub2=pctf(p.cxp.pct_vencido,0)+" vencido · "+num(p.cxp.n_documentos)+" documentos";
    sub3=p.pagos.n?(num(p.pagos.n)+" pagos registrados en Odoo"+
        (p.pagos.estado_conocido&&p.pagos.no_aplicados?
          " · "+money(conv(p.pagos.no_aplicados,p),cur,true)+" SIN imputar a factura (anticipos)":"")):
      "NINGÚN pago registrado en Odoo";
  }
  [["flujo","Compra total facturada YTD",compra,"FLUJO: todo lo que facturaron los proveedores, locales y del exterior. "+sub1],
   ["stock","Saldo de CxP hoy",cxp,"STOCK de deuda al corte: lo que se debe ahora mismo. "+sub2],
   ["caja","Pagos ejecutados YTD",pagos,"CAJA: lo que efectivamente salió del banco. "+sub3]
  ].forEach(function(x){
    box.appendChild(el("div",{"class":"m "+x[0]},[
      el("div",{"class":"lab",text:x[1]}),
      el("div",{"class":"val",text:money(x[2],cur,true)}),
      el("div",{"class":"exp",text:x[3]})]));
  });
  var pie=[el("div",{"class":"foot",style:"margin:-8px 0 4px",
      text:"Los tres miden el MISMO universo de proveedores —locales y del exterior— pero cosas distintas, y jamás "+
           "se suman entre sí. Se puede pagar más de lo que se compró en el período (deuda vieja) o comprar más de "+
           "lo que se pagó (deuda nueva)."})];
  if(!esCons()){
    var p2=P(), ct=p2.control||{};
    if(nn(ct.sin_explicar)&&Math.abs(ct.sin_explicar)>1)
      pie.push(el("div",{"class":"warnbox",style:"margin:6px 0 16px",html:
        "<b>Prueba de coherencia:</b> de los "+money(conv(ct.compra_total_ytd,p2),curOf(p2))+
        " facturados este año quedan pendientes "+money(conv(ct.saldo_cxp_anio,p2),curOf(p2))+
        ", así que se pagaron <b>"+money(conv(ct.pagado_implicito_del_anio,p2),curOf(p2))+
        "</b>. Odoo registra "+money(conv(ct.pagos_ytd,p2),curOf(p2))+" en pagos"+
        (nn(ct.pagos_aplicados)?" ("+money(conv(ct.pagos_aplicados,p2),curOf(p2))+" imputados a facturas y "+
          money(conv(ct.pagos_no_aplicados,p2),curOf(p2))+" sin imputar)":"")+
        ": quedan <b>"+money(conv(ct.sin_explicar,p2),curOf(p2))+"</b> sin explicar. "+ct.nota}));
    else pie.push(el("div",{style:"margin-bottom:16px"}));
  } else pie.push(el("div",{style:"margin-bottom:16px"}));
  return el("div",{},[box].concat(pie));
}

/* ===================================================================
   B. KPIs
   =================================================================== */
function kpi(lab,val,cmp,spk,flag,badge){
  var k=el("div",{"class":"kpi"+(val==null?" nd":"")});
  k.appendChild(el("span",{"class":"flag",style:"background:"+(flag||"transparent")}));
  k.appendChild(el("div",{"class":"lab",text:lab}));
  k.appendChild(el("div",{"class":"val"+(String(val||"").length>11?" sm":""),text:val==null?"sin dato":val}));
  var c=el("div",{"class":"cmp"});
  (Array.isArray(cmp)?cmp:[cmp]).forEach(function(x){if(!x)return;
    c.appendChild(typeof x==="string"?document.createTextNode(x):x);});
  if(badge)c.appendChild(el("span",{"class":"badge "+(badge[1]||""),text:badge[0]}));
  k.appendChild(c);
  k.appendChild(spk||el("div",{"class":"spark"}));
  return k;
}
function kpisPais(p){
  var cur=curOf(p), box=el("div",{"class":"kpis"});
  var mtd=p.compra.mtd, ant=p.compra.mes_anterior;
  // El mes en curso esta a medias: compararlo crudo contra un mes cerrado siempre
  // muestra una "caida" que es solo calendario. Se compara contra el mismo tramo.
  var dia=(new Date()).getDate(), dmes=new Date(D.anio,p.mes_actual,0).getDate();
  var fr=Math.min(1,dia/dmes);
  var dlt=(nn(ant)&&ant)?(mtd-ant*fr)/Math.abs(ant*fr):null;
  var vd=(p.compra.ventana_datos||{});
  var unMes=vd.primera&&vd.ultima&&vd.primera.slice(0,7)===vd.ultima.slice(0,7);
  box.appendChild(kpi(unMes?("Compra local · "+MESES[p.mes_actual-1]+" (único mes en Odoo)")
                            :("Compra local "+MESES[p.mes_actual-1]),money(conv(mtd,p),cur,true),
    [nn(dlt)?el("span",{"class":Math.abs(dlt)<0.1?"mut":(dlt>0?"warn":"up"),
      text:(dlt>=0?"▲ ":"▼ ")+pctf(Math.abs(dlt),0)+" vs "+MESES[p.mes_actual-2]+" al mismo día"}):
      el("span",{"class":"mut",text:"sin mes anterior comparable"}),
     el("span",{"class":"mut",text:"· mes en curso, "+pctf(fr,0)+" transcurrido"})],
    spark(p.compra.mensual,"var(--series-1)",p.mes_actual)));
  var pr=p.presupuesto;
  if(pr&&pr.disponible){
    box.appendChild(kpi("Gasto H2 vs presupuesto",pctf(pr.run_rate_vs_vigente),
      [el("span",{"class":"mut",text:"run-rate "+money(pr.run_rate_h2,"USD",true)+" vs "+money(pr.vigente_total_h2,"USD",true)}),
       pr.ejecucion_comparable?null:el("span",{"class":"badge nd",text:"aún no concluyente"})],
      null,pr.ejecucion_comparable?semColor(pr.run_rate_vs_vigente?1/Math.max(pr.run_rate_vs_vigente,0.01):null):"var(--warning)"));
  } else {
    box.appendChild(kpi("Gasto vs presupuesto",null,[el("span",{"class":"warn",text:"sin presupuesto"})],
      null,"var(--serious)",["no cargado","nd"]));
  }
  var cx=p.cxp;
  box.appendChild(kpi("Saldo de CxP",money(conv(cx.total,p),cur,true),
    [el("span",{"class":cx.pct_vencido>0.5?"down":"mut",text:pctf(cx.pct_vencido,0)+" vencido"}),
     cx.total_anios_anteriores?el("span",{"class":"down",
       text:"· "+money(conv(cx.total_anios_anteriores,p),cur,true)+" de años anteriores"}):
       el("span",{"class":"mut",text:"· "+num(cx.n_proveedores)+" proveedores"})],null,
    cx.pct_vencido>0.5?"var(--critical)":(cx.pct_vencido>0.2?"var(--warning)":"var(--good)")));
  box.appendChild(kpi("Vencido > 30 días",money(conv(cx.vencido_mas_30,p),cur,true),
    [el("span",{"class":cx.pct_vencido_mas_30>0.4?"down":"warn",text:pctf(cx.pct_vencido_mas_30,0)+" de la CxP"}),
     el("span",{"class":"mut",text:"· "+money(conv(cx.buckets[">90"],p),cur,true)+" a +90d"})],null,
    cx.pct_vencido_mas_30>0.4?"var(--critical)":"var(--warning)"));
  var d=p.dpo;
  box.appendChild(kpi("DPO (días de pago)",nn(d.puntual)?num(d.puntual,0)+" d":null,
    [nn(d.dias_pago_real)?el("span",{"class":d.dias_pago_real>30?"down":(d.dias_pago_real>0?"warn":"up"),
      text:"pagas "+num(Math.abs(d.dias_pago_real),0)+" d "+(d.dias_pago_real>=0?"tarde":"antes")}):
      el("span",{"class":"mut",text:"sin base conciliada"}),
     el("span",{"class":"mut",text:"· sobre compra total "+money(conv(d.compra_periodo,p),cur,true)}) ],null,
    nn(d.puntual)?(d.puntual>120?"var(--critical)":(d.puntual>60?"var(--warning)":"var(--good)")):null,
    ["puntual","nd"]));
  var cal=p.calendario;
  box.appendChild(kpi("A pagar en 7 días",money(conv(cal.a_pagar_7_dias,p),cur,true),
    [el("span",{"class":cal.vencido_previo>0?"down":"mut",
      text:"+ "+money(conv(cal.vencido_previo,p),cur,true)+" ya vencido"}),
     el("span",{"class":"mut",text:"· "+num(cal.n_vencido_previo)+" docs atrasados"})],null,
    cal.vencido_previo>0?"var(--critical)":"var(--good)"));
  return box;
}
function kpisConsolidado(){
  var c=D.consolidado, box=el("div",{"class":"kpis"}), tcb=["TC referencial","tc"];
  box.appendChild(kpi("Compra local del grupo",money(c.compra_ytd,"USD",true),
    [el("span",{"class":"mut",text:"YTD, sólo proveedores locales"})],null,null,tcb));
  box.appendChild(kpi("CxP total del grupo",money(c.cxp_total,"USD",true),
    [el("span",{"class":c.pct_vencido>0.5?"down":"mut",text:pctf(c.pct_vencido,0)+" vencido"})],null,
    c.pct_vencido>0.5?"var(--critical)":"var(--warning)",tcb));
  box.appendChild(kpi("Vencido del grupo",money(c.cxp_vencido,"USD",true),
    [el("span",{"class":"mut",text:"suma de los 3 países"})],null,"var(--critical)",tcb));
  box.appendChild(kpi("Pagos ejecutados",money(c.pagos_ytd,"USD",true),
    [el("span",{"class":"mut",text:"salida real de caja YTD"})],null,null,tcb));
  box.appendChild(kpi("A pagar en 7 días",money(c.a_pagar_7_dias,"USD",true),
    [el("span",{"class":"mut",text:"vencimientos de la próxima semana"})],null,null,tcb));
  var peor=(c.por_pais||[]).slice().sort(function(a,b){return (b.pct_vencido_grupo||0)-(a.pct_vencido_grupo||0);})[0];
  box.appendChild(kpi("Concentración de la mora",peor?pctf(peor.pct_vencido_grupo,0):null,
    [el("span",{"class":"down",text:peor?"en "+peor.pais:""}),
     el("span",{"class":"mut",text:"· del vencido del grupo"})],null,
    (peor&&peor.pct_vencido_grupo>0.6)?"var(--critical)":"var(--warning)"));
  return box;
}

/* ===================================================================
   C. AGING DE CxP
   =================================================================== */
function chartAgingProv(p){
  var provs=(p.cxp.proveedores||[]).slice(0,10);
  return chartHost(function(w){return Math.max(70,provs.length*30+14)},function(w,h){
    var mL=w<560?104:210,mR=w<560?56:96,iw=w-mL-mR;
    var max=Math.max.apply(null,provs.map(function(c){return Math.abs(c.saldo);}).concat([1]));
    var g=S("svg",{width:w,height:h}),bh=20;
    provs.forEach(function(c,i){
      var Y=8+i*30,x=mL;
      BK.forEach(function(b,bi){
        var v=c.buckets[b]||0; if(!v)return;
        var wpx=Math.max(1.5,Math.abs(v)/max*iw);
        var r=S("rect",{x:x,y:Y,width:Math.max(0.5,wpx-2),height:bh,rx:3,fill:BKC[bi]});
        hover(r,c.proveedor,[["Tramo",b],["Saldo",money(conv(v,p),curOf(p))],
          ["% del proveedor",pctf(v/c.saldo)],["Saldo total",money(conv(c.saldo,p),curOf(p))],
          ["Departamento",c.depto||"—"],c.plazo?["Plazo pactado",c.plazo]:null].filter(Boolean));
        g.appendChild(r); x+=wpx;
      });
      var t=S("text",{x:mL-8,y:Y+14,"text-anchor":"end","class":"dlabel"});
      t.textContent=c.proveedor.length>(w<560?14:28)?c.proveedor.slice(0,w<560?13:27)+"…":c.proveedor;
      g.appendChild(t);
      var t2=S("text",{x:x+7,y:Y+14,"class":"dlabel"});
      t2.textContent=money(conv(c.saldo,p),curOf(p),true);
      if(c.pct_vencido>0.5)t2.setAttribute("fill","var(--critical)");
      g.appendChild(t2);
    });
    return g;
  });
}
function secAging(p){
  var cur=curOf(p), cx=p.cxp, k=[];
  if(!cx.n_documentos)return card("Antigüedad de la deuda","",sinDato("Sin cuentas por pagar abiertas en "+SCOPE,
    "Odoo no devuelve facturas de proveedor con saldo.","Verificar que la contabilidad del país esté cargada."));
  var bars=el("div",{style:"display:flex;gap:2px;height:28px;border-radius:6px;overflow:hidden;margin:2px 0 8px"});
  BK.forEach(function(b,i){var v=cx.buckets[b]||0;if(!v)return;
    var d=el("div",{style:"flex:"+Math.abs(v)+" 0 0;background:"+BKC[i]});
    hover(d,b,[["Saldo",money(conv(v,p),cur)],["% de la CxP",pctf(v/cx.total)]]);bars.appendChild(d);});
  k.push(bars);
  k.push(el("div",{"class":"legend"},BK.map(function(b,i){
    return el("span",{},[el("i",{style:"background:"+BKC[i]}),b+" · "+money(conv(cx.buckets[b],p),cur,true)+
      " ("+pctf((cx.buckets[b]||0)/cx.total,0)+")"]);})));
  var anios=Object.keys(cx.por_anio||{}).sort();
  if(anios.length>1){
    var ga=el("div",{"class":"exgrid",style:"margin-top:12px"});
    anios.forEach(function(a){
      ga.appendChild(el("div",{"class":"ex"+(a!==String(D.anio)?" alerta":"")},[
        el("div",{"class":"k",text:"Facturas de "+a}),
        el("div",{"class":"v",text:money(conv(cx.por_anio[a],p),cur,true)}),
        el("div",{"class":"n",text:pctf(cx.por_anio[a]/cx.total,0)+" del saldo"+
          (a!==String(D.anio)?" · deuda arrastrada":"")})]));});
    k.push(ga);
  }
  k.push(el("h3",{style:"font-size:12px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.08em;margin:18px 0 4px",
    text:"Antigüedad por proveedor (top "+(cx.proveedores||[]).length+" de "+num(cx.n_proveedores)+")"}));
  k.push(chartAgingProv(p));
  var peor=(cx.proveedores||[]).slice().sort(function(a,b){return b.dias-a.dias;})[0];
  var txt="Se deben <b>"+money(conv(cx.total,p),cur)+"</b> en "+num(cx.n_documentos)+" documentos a "+
    num(cx.n_proveedores)+" proveedores. Vencido <b>"+pctf(cx.pct_vencido)+"</b>; a más de 30 días, <b>"+
    pctf(cx.pct_vencido_mas_30)+"</b>.";
  if(peor&&peor.dias>0)txt+=" El documento más viejo es de <b>"+peor.proveedor+"</b>, con <b>"+num(peor.dias)+
    " días</b> de mora ("+(peor.mas_antiguo||"?")+") y un saldo de "+money(conv(peor.saldo,p),cur)+".";
  if(cx.pct_vencido>0.9)txt+=" <b>Prácticamente toda la cartera está vencida</b>: esto ya no es un plazo de pago, "+
    "es deuda que dejó de rotar. Antes de negociar plazos hay que entender por qué.";
  if(cx.total_anios_anteriores){
    var anios=Object.keys(cx.por_anio||{}).filter(function(a){return a!==String(D.anio);}).sort();
    txt+=" <b>"+money(conv(cx.total_anios_anteriores,p),cur)+" ("+pctf(cx.total_anios_anteriores/cx.total,0)+
      " del total) son facturas de "+anios.join(", ")+"</b>, no de este año. Esa deuda no aparece en "+
      "cxp_semana_actual.json, que sólo mira el año en curso.";
  }
  k.push(lectura(txt));
  var rows=(cx.proveedores||[]).map(function(c){return {proveedor:c.proveedor,saldo:conv(c.saldo,p),
    vencido:conv(c.vencido,p),pct:c.pct_vencido,dias:c.dias,doc:c.mas_antiguo,depto:c.depto,n:c.n,plazo:c.plazo||null};});
  var t=tabla("t-cxp",[{t:"Proveedor",k:"proveedor"},{t:"Saldo",k:"saldo"},{t:"Vencido",k:"vencido"},
    {t:"% vencido",k:"pct",cls:function(r){return r.pct>0.5?"neg":"";}},
    {t:"Días del más viejo",k:"dias",cls:function(r){return r.dias>60?"neg":"";}},
    {t:"Documento",k:"doc"},{t:"Depto",k:"depto"},{t:"Plazo pactado",k:"plazo"},{t:"Docs",k:"n"}],rows,
    [function(r){return r.proveedor;},function(r){return money(r.saldo,cur);},function(r){return money(r.vencido,cur);},
     function(r){return pctf(r.pct,0);},function(r){return r.dias?num(r.dias)+" d":"—";},
     function(r){return r.doc||"—";},function(r){return r.depto||"—";},
     function(r){return r.plazo||el("span",{"class":"badge nd",text:"sin plazo"});},function(r){return num(r.n);}]);
  k.push(t);k.push(csvBtn(t,"cxp_"+SCOPE));
  k.push(el("div",{"class":"foot",text:"Corte "+fecha(cx.corte)+". "+cx.fuente+
    (cx.monedas_documento&&cx.monedas_documento.length>1?
     "  ·  Los documentos vienen en "+cx.monedas_documento.join(" y ")+"; el total se agrega en "+p.moneda+
     " (moneda de la compañía), no sumando importes de monedas distintas.":"")}));
  return card("Antigüedad de la deuda y aging por proveedor",
    "Buckets sobre fecha de vencimiento. Incluye proveedores locales y del exterior: la deuda hay que pagarla venga de donde venga.",k);
}

/* ===================================================================
   D. CALENDARIO DE PAGOS Y CAJA
   =================================================================== */
var DEPCOL={"Operaciones":"var(--series-1)","Comercial":"var(--series-2)","Gerencia":"var(--series-3)"};
function colDep(d){return DEPCOL[d]||"var(--text-muted)";}
function chartCalendario(p){
  var sem=p.calendario.semanas||[];
  return chartHost(function(w){return w<560?210:250},function(w,h){
    var mL=w<560?44:66,mR=10,mT=14,mB=40,iw=w-mL-mR,ih=h-mT-mB,bw=iw/Math.max(1,sem.length);
    var max=nice(Math.max.apply(null,sem.map(function(s){return Math.abs(s.total);}).concat([1])));
    var y=function(v){return mT+ih-(v/max)*ih;};
    var g=S("svg",{width:w,height:h});
    ticks(max,4).forEach(function(t){
      g.appendChild(S("line",{x1:mL,x2:w-mR,y1:y(t),y2:y(t),"class":"gl"}));
      var tx=S("text",{x:mL-6,y:y(t)+3.5,"text-anchor":"end","class":"ax"});
      tx.textContent=money(t,curOf(p),true).replace(/^\$/,"");g.appendChild(tx);});
    sem.forEach(function(s,i){
      var x0=mL+bw*i+bw*0.16, wd=bw*0.68, acc=0;
      var deps=Object.keys(s.por_depto||{}).sort();
      if(!s.total){
        g.appendChild(S("line",{x1:x0,x2:x0+wd,y1:y(0),y2:y(0),stroke:"var(--text-muted)","stroke-width":2}));
      }
      deps.forEach(function(d){
        var v=s.por_depto[d]; if(!v)return;
        var hgt=Math.max(1.5,Math.abs(v)/max*ih);
        var r=S("rect",{x:x0,width:wd,y:y(acc+Math.abs(v)),height:hgt,rx:3,fill:colDep(d)});
        hover(r,"Semana "+s.iso+" · "+d,[["Vence",money(conv(v,p),curOf(p))],
          ["Total de la semana",money(conv(s.total,p),curOf(p))],["Documentos",num(s.n)],
          ["Del "+fecha(s.desde),"al "+fecha(s.fin)]]);
        g.appendChild(r); acc+=Math.abs(v);
      });
      var tx=S("text",{x:mL+bw*i+bw/2,y:h-22,"text-anchor":"middle","class":"ax"});
      tx.textContent=fecha(s.desde).slice(0,5); g.appendChild(tx);
      if(s.es_actual){var t2=S("text",{x:mL+bw*i+bw/2,y:h-8,"text-anchor":"middle","class":"ax",fill:"var(--series-1)"});
        t2.textContent="esta semana";g.appendChild(t2);}
    });
    return g;
  });
}
function secCalendario(p){
  var cur=curOf(p), cal=p.calendario, esc=p.escenarios, k=[];
  if(cal.vencido_previo>0)k.push(el("div",{"class":"warnbox",html:
    "<b>"+money(conv(cal.vencido_previo,p),cur)+"</b> ya venció y sigue sin pagarse ("+num(cal.n_vencido_previo)+
    " documentos). Eso no aparece en ninguna de las 8 semanas de abajo porque su fecha ya pasó: es deuda que "+
    "arrastras, no un compromiso futuro."}));
  var deps=Object.keys((p.cxp.por_departamento||{}));
  k.push(el("div",{"class":"legend"},deps.sort().map(function(d){
    return el("span",{},[el("i",{style:"background:"+colDep(d)}),d]);})
    .concat([el("span",{},[el("i",{style:"background:var(--text-muted);height:3px;border-radius:1px"}),"Semana sin vencimientos (cero real)"])])));
  k.push(chartCalendario(p));
  var s8=(cal.semanas||[]).reduce(function(a,s){return a+s.total;},0);
  k.push(lectura("En las próximas 8 semanas vencen <b>"+money(conv(s8,p),cur)+"</b>. La semana en curso concentra <b>"+
    money(conv((cal.semanas[0]||{}).total,p),cur)+"</b> en "+num((cal.semanas[0]||{}).n||0)+" documentos"+
    (cal.vencido_previo>0?", además de los "+money(conv(cal.vencido_previo,p),cur)+" ya vencidos":"")+"."));
  k.push(el("h3",{style:"font-size:12px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.08em;margin:20px 0 2px",
    text:"Escenarios de caja"}));
  var g=el("div",{"class":"esc"});
  [["pagar_todo_vencido","Pagar todo lo vencido"],["solo_corriente","Pagar sólo lo corriente"],
   ["diferir_mas_60","Pagar hasta 60 días y diferir el resto"]].forEach(function(o){
    var e=esc[o[0]]||{};
    g.appendChild(el("div",{"class":"e"},[el("div",{"class":"t",text:o[1]}),
      el("div",{"class":"v",text:money(conv(e.monto,p),cur)}),
      el("div",{"class":"d",text:e.descripcion+" ("+num(e.n)+" documentos"+
        (nn(e.difiere)?"; difiere "+money(conv(e.difiere,p),cur):"")+")"})]));});
  k.push(g);
  var docs=cal.semana_actual||[];
  if(docs.length){
    k.push(el("h3",{style:"font-size:12px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.08em;margin:20px 0 2px",
      text:"Detalle de la semana en curso — insumo del Comité de Pagos"}));
    var rows=docs.map(function(d){return {vence:d.vence,proveedor:d.proveedor,doc:d.doc,
      saldo:conv(d.saldo,p),depto:d.depto,dias:d.dias,origen:d.estado};});
    var t=tabla("t-sem",[{t:"Vence",k:"vence"},{t:"Proveedor",k:"proveedor"},{t:"Documento",k:"doc"},
      {t:"Monto",k:"saldo"},{t:"Depto",k:"depto"},{t:"Días",k:"dias"},{t:"Origen",k:"origen"}],rows,
      [function(r){return fecha(r.vence);},function(r){return r.proveedor;},function(r){return r.doc;},
       function(r){return money(r.saldo,cur);},function(r){return r.depto;},
       function(r){return r.dias>0?num(r.dias)+" d":"—";},function(r){return r.origen==="local"?"local":"exterior";}]);
    k.push(t);k.push(csvBtn(t,"comite_pagos_"+SCOPE));
  }
  k.push(el("div",{"class":"warnbox",style:"margin-top:14px",html:
    "Para exportar al formato de carga masiva del Banco Guayaquil hace falta completar <b>cuenta_empresa</b>, que "+
    "sigue en <b>null</b> en <code>Pagos/banco/bg_config.json</code>. Sin ese dato el archivo se genera pero "+
    "Banca Empresas lo rechaza. El CSV de arriba sirve para el comité; el archivo del banco, no todavía."}));
  return card("Calendario de pagos y caja","Qué vence, cuándo, y qué pasa con la caja según a quién le pagues.",k);
}

/* ===================================================================
   E. DPO Y PODER DE NEGOCIACIÓN
   =================================================================== */
function chartMatriz(p){
  var filas=(p.brecha_plazo.filas||[]).filter(function(f){return f.volumen>0;});
  if(!filas.length)return null;
  return chartHost(function(w){return w<560?260:320},function(w,h){
    var mL=w<560?46:70,mR=16,mT=16,mB=38,iw=w-mL-mR,ih=h-mT-mB;
    var maxD=Math.max.apply(null,filas.map(function(f){return f.dias_mora_actual||0;}).concat([30]));
    var maxV=Math.max.apply(null,filas.map(function(f){return Math.abs(f.volumen);}).concat([1]));
    var x=function(d){return mL+(d/maxD)*iw;}, y=function(v){return mT+ih-(Math.abs(v)/maxV)*ih;};
    var g=S("svg",{width:w,height:h});
    var cx=x(maxD*0.5), cy=y(maxV*0.5);
    g.appendChild(S("line",{x1:cx,x2:cx,y1:mT,y2:mT+ih,stroke:"var(--line)","stroke-dasharray":"3 4"}));
    g.appendChild(S("line",{x1:mL,x2:w-mR,y1:cy,y2:cy,stroke:"var(--line)","stroke-dasharray":"3 4"}));
    [[mL+6,mT+14,"Alto volumen · pagas rápido","start"],[w-mR-6,mT+14,"Alto volumen · pagas lento","end"],
     [mL+6,mT+ih-6,"Poco volumen · rápido","start"],[w-mR-6,mT+ih-6,"Poco volumen · lento","end"]
    ].forEach(function(q){var t=S("text",{x:q[0],y:q[1],"text-anchor":q[3],"class":"quad"});t.textContent=q[2];g.appendChild(t);});
    filas.forEach(function(f){
      var X=x(f.dias_mora_actual||0), Y=y(f.volumen);
      var alto=Math.abs(f.volumen)>maxV*0.5, lento=(f.dias_mora_actual||0)>maxD*0.5;
      var col=alto&&!lento?"var(--warning)":(alto&&lento?"var(--critical)":"var(--series-1)");
      var c=S("circle",{cx:X,cy:Y,r:Math.max(5,Math.min(15,Math.sqrt(Math.abs(f.volumen)/maxV)*15)),
        fill:col,"fill-opacity":.72,stroke:"var(--surface-1)","stroke-width":2});
      hover(c,f.proveedor,[["Volumen de compra",money(conv(f.volumen,p),curOf(p))],
        ["Mora del documento más viejo",num(f.dias_mora_actual)+" días"],
        f.plazo?["Plazo pactado",f.plazo+" ("+(f.fuente_plazo||"?")+")"]:["Plazo pactado","no cargado en Odoo"],
        nn(f.brecha)?["Brecha vs plazo",num(f.brecha)+" días"]:null,
        alto&&!lento?["Lectura","Alto volumen y pagas rápido: aquí se negocia plazo"]:null,
        alto&&lento?["Lectura","Alto volumen y pagas lento: riesgo de que te corten"]:null].filter(Boolean));
      g.appendChild(c);
    });
    var xa=S("text",{x:mL+iw/2,y:h-8,"text-anchor":"middle","class":"ax"});
    xa.textContent="Días de mora del documento más antiguo →";g.appendChild(xa);
    var ya=S("text",{x:12,y:mT+ih/2,"class":"ax",transform:"rotate(-90 12 "+(mT+ih/2)+")","text-anchor":"middle"});
    ya.textContent="Volumen de compra ↑";g.appendChild(ya);
    return g;
  });
}
function secDPO(p){
  var cur=curOf(p), d=p.dpo, b=p.brecha_plazo, k=[];
  var g=el("div",{"class":"exgrid"});
  [["DPO puntual",nn(d.puntual)?num(d.puntual,0)+" días":"sin dato",d.ventana||"",false],
   ["Días de pago real",nn(d.dias_pago_real)?num(d.dias_pago_real,0)+" días":"sin dato",
    nn(d.dias_pago_real)?"ponderado por monto sobre "+money(conv(d.base_conciliada,p),cur,true)+" conciliados":"sin conciliaciones",
    nn(d.dias_pago_real)&&d.dias_pago_real>30],
   ["Cobertura de plazo pactado",pctf(b.cobertura_plazo,0),
    num(b.n_con_plazo)+" de "+num(b.n_docs)+" facturas traen plazo en Odoo", b.cobertura_plazo<0.8]
  ].forEach(function(x){
    g.appendChild(el("div",{"class":"ex"+(x[3]?" alerta":"")},[el("div",{"class":"k",text:x[0]}),
      el("div",{"class":"v",text:x[1]}),el("div",{"class":"n",text:x[2]})]));});
  k.push(g);
  k.push(el("div",{"class":"foot",text:d.metodo}));
  var m=chartMatriz(p);
  if(m){
    k.push(el("h3",{style:"font-size:12px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.08em;margin:18px 0 2px",
      text:"Matriz de poder de negociación"}));
    k.push(m);
  }
  var txt="";
  if(nn(d.puntual)&&nn(d.dias_pago_real)){
    txt="El DPO puntual es de <b>"+num(d.puntual,0)+" días</b> y en los últimos 12 meses pagaste en promedio ponderado <b>"+
      num(Math.abs(d.dias_pago_real),0)+" días "+(d.dias_pago_real>=0?"después":"antes")+"</b> del vencimiento. ";
    if(d.puntual>120)txt+="Un DPO de tres dígitos con la cartera casi toda vencida no es poder de negociación: es "+
      "financiamiento forzado. El proveedor que aguanta eso ya te cobró el costo en el precio, o está por cortarte.";
    else if(d.dias_pago_real<0)txt+="Estás pagando <b>antes</b> del vencimiento: le estás dando financiamiento gratis al proveedor. "+
      "Cada día que adelantas es caja que sale sin necesidad.";
    if(d.dias_pago_real<0 && p.cxp.pct_vencido>0.7)
      txt+=" <b>Hay una contradicción que vale la pena mirar de frente:</b> a los proveedores que efectivamente pagas "+
        "les pagas <b>"+num(Math.abs(d.dias_pago_real),0)+" días antes</b> del vencimiento, mientras el <b>"+
        pctf(p.cxp.pct_vencido,0)+"</b> de la cartera está vencido. Eso no es falta de caja: es pago selectivo. "+
        "La pregunta de gerencia no es si alcanza la plata, sino quién decide a quién se le paga y con qué criterio.";
  }
  if(b.cobertura_plazo<0.8)txt+=" <b>Ojo con la matriz:</b> sólo el "+pctf(b.cobertura_plazo,0)+" de las facturas "+
    "trae plazo pactado en Odoo, así que el eje de la brecha vive sobre ese subconjunto. Lo demás no se supone.";
  if(txt)k.push(lectura(txt));
  var rows=(b.filas||[]).map(function(f){return {proveedor:f.proveedor,plazo:f.plazo,volumen:conv(f.volumen,p),
    dias:f.dias_mora_actual,brecha:f.brecha,fuente:f.fuente_plazo};});
  var t=tabla("t-dpo",[{t:"Proveedor",k:"proveedor"},{t:"Plazo pactado",k:"plazo"},{t:"Volumen",k:"volumen"},
    {t:"Mora del más viejo",k:"dias",cls:function(r){return r.dias>60?"neg":"";}},
    {t:"Brecha (días)",k:"brecha",cls:function(r){return nn(r.brecha)&&r.brecha>0?"neg":"";}},
    {t:"Fuente del plazo",k:"fuente"}],rows,
    [function(r){return r.proveedor;},
     function(r){return r.plazo||el("span",{"class":"badge nd",text:"no cargado"});},
     function(r){return money(r.volumen,cur);},function(r){return r.dias?num(r.dias)+" d":"—";},
     function(r){return nn(r.brecha)?num(r.brecha)+" d":"—";},
     function(r){return r.fuente||"—";}]);
  k.push(t);k.push(csvBtn(t,"dpo_"+SCOPE));
  k.push(el("div",{"class":"foot",text:b.nota}));
  return card("DPO y poder de negociación","Cuánto tardas en pagar, contra lo que pactaste. Sin plazo pactado no hay brecha: no se inventa.",k);
}

/* ===================================================================
   F. CONCENTRACIÓN Y DEPENDENCIA
   =================================================================== */
function secConcentracion(p){
  var cur=curOf(p), c=p.concentracion, k=[];
  var crit=(c.unicos_criticos||[]).filter(function(x){return x.alerta_roja;});
  if(crit.length)crit.forEach(function(x){
    k.push(el("div",{"class":"nodata",style:"margin:0 0 12px"},[
      el("h3",{},["⚠ Proveedor único con la factura vencida — "+x.categoria]),
      el("p",{text:x.proveedor+" es el único proveedor de "+x.categoria.toLowerCase()+" del país y su documento más "+
        "antiguo lleva "+num(x.dias_vencido)+" días vencido, con un saldo de "+money(conv(x.saldo,p),cur)+"."}),
      el("div",{"class":"need",text:"Este cruce —único proveedor + mora larga— es el que te deja sin el servicio un lunes. "+
        "Vale más resolverlo que negociar tres centavos de precio."})]));});
  var top=(p.compra.top_proveedores||[]).slice(0,15);
  var maxv=Math.max.apply(null,top.map(function(x){return Math.abs(x.monto);}).concat([1]));
  var lista=el("div",{style:"margin:4px 0 6px"});
  top.forEach(function(x){
    var row=el("div",{style:"display:flex;align-items:center;gap:10px;padding:5px 0;border-bottom:1px solid var(--line-soft)"});
    var nm=el("div",{style:"flex:0 0 "+(innerWidth<640?"108px":"216px"),title:x.proveedor});
    nm.appendChild(document.createTextNode(x.proveedor.length>30?x.proveedor.slice(0,29)+"…":x.proveedor));
    (x.etiquetas||[]).forEach(function(e){
      if(e.indexOf("cat:")===0)return;
      nm.appendChild(el("span",{"class":"badge",style:"margin-left:6px;border-color:#4a412a;color:var(--warning)",text:"com. ext."}));});
    row.appendChild(nm);
    var bar=el("div",{style:"flex:1;height:14px;background:var(--surface-2);border-radius:3px;overflow:hidden"});
    var f=el("div",{style:"width:"+(Math.abs(x.monto)/maxv*100)+"%;height:100%;border-radius:3px;background:"+
      (x.pct>0.4?"var(--critical)":(x.pct>0.2?"var(--warning)":"var(--series-1)"))});
    hover(f,x.proveedor,[["Compra YTD",money(conv(x.monto,p),cur)],["% del total",pctf(x.pct)],
      ["Documentos",num(x.n)],["Departamento",x.depto||"—"]]);
    bar.appendChild(f);row.appendChild(bar);
    row.appendChild(el("div",{style:"flex:0 0 92px;text-align:right;color:var(--text-secondary);font-variant-numeric:tabular-nums",
      text:money(conv(x.monto,p),cur,true)}));
    row.appendChild(el("div",{style:"flex:0 0 48px;text-align:right;font-weight:600;font-variant-numeric:tabular-nums",
      text:pctf(x.pct,0)}));
    lista.appendChild(row);
  });
  k.push(lista);
  var hhiBox=el("div",{style:"display:flex;gap:16px;align-items:center;flex-wrap:wrap;margin:12px 0 2px;padding:12px;"+
    "background:var(--surface-2);border-radius:10px;border-left:3px solid "+(c.critico?"var(--critical)":"var(--good)")});
  hhiBox.appendChild(el("div",{},[el("div",{style:"font-size:10.5px;text-transform:uppercase;letter-spacing:.09em;color:var(--text-muted)",text:"HHI de proveedores"}),
    el("div",{style:"font-family:var(--cond);font-size:28px;font-weight:700;color:"+(c.critico?"var(--critical)":"var(--good)"),
      text:num(c.hhi)})]));
  hhiBox.appendChild(el("div",{style:"flex:1;min-width:220px;color:var(--text-secondary);font-size:12.5px",
    text:(c.critico?"Por encima de 2.500 la dependencia es crítica. ":"Dentro de rango. ")+
      "Los 5 primeros concentran "+pctf(c.top5_pct)+" de la compra local."}));
  k.push(hhiBox);
  var uc=(c.unicos_criticos||[]);
  if(uc.length){
    k.push(el("h3",{style:"font-size:12px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.08em;margin:18px 0 2px",
      text:"Categorías con un solo proveedor"}));
    var rows=uc.map(function(x){return {categoria:x.categoria,proveedor:x.proveedor,monto:conv(x.monto,p),
      saldo:nn(x.saldo)?conv(x.saldo,p):null,dias:x.dias_vencido,riesgo:x.alerta_roja?"CRÍTICO":"vigilar"};});
    var t=tabla("t-unicos",[{t:"Categoría",k:"categoria"},{t:"Proveedor",k:"proveedor"},{t:"Compra YTD",k:"monto"},
      {t:"Saldo por pagar",k:"saldo"},{t:"Días vencido",k:"dias",cls:function(r){return r.dias>60?"neg":"";}},
      {t:"Riesgo",k:"riesgo"}],rows,
      [function(r){return r.categoria;},function(r){return r.proveedor;},function(r){return money(r.monto,cur);},
       function(r){return money(r.saldo,cur);},function(r){return r.dias?num(r.dias)+" d":"—";},
       function(r){return r.riesgo==="CRÍTICO"?el("span",{"class":"down",text:r.riesgo}):el("span",{"class":"mut",text:r.riesgo});}]);
    k.push(t);
  }
  return card("Concentración y dependencia de proveedores",
    "El riesgo operativo de la compra local. Un proveedor único con mora larga vale más que un punto de precio.",k);
}

/* ===================================================================
   G. GASTO POR DEPARTAMENTO Y CUENTA
   =================================================================== */
function chartCompraPagos(p){
  return chartHost(function(w){return w<560?200:250},function(w,h){
    var mL=w<560?44:66,mR=10,mT=14,mB=28,iw=w-mL-mR,ih=h-mT-mB,bw=iw/12;
    var cm=p.compra.mensual.map(function(v){return conv(v,p);});
    var pg=p.pagos.mensual.map(function(v){return conv(v,p);});
    var max=nice(Math.max.apply(null,cm.concat(pg).map(Math.abs).concat([1])));
    var y=function(v){return mT+ih-(Math.abs(v)/max)*ih;};
    var g=S("svg",{width:w,height:h});
    ticks(max,4).forEach(function(t){
      g.appendChild(S("line",{x1:mL,x2:w-mR,y1:y(t),y2:y(t),"class":"gl"}));
      var tx=S("text",{x:mL-6,y:y(t)+3.5,"text-anchor":"end","class":"ax"});
      tx.textContent=money(t,curOf(p),true).replace(/^\$/,"");g.appendChild(tx);});
    for(var m=0;m<12;m++){
      var futuro=(m+1)>p.mes_actual, x0=mL+bw*m;
      var tx=S("text",{x:x0+bw/2,y:h-8,"text-anchor":"middle","class":"ax"});
      tx.textContent=MESES[m]; if(futuro)tx.setAttribute("opacity",".45"); g.appendChild(tx);
      if(futuro){g.appendChild(S("rect",{x:x0+bw*0.12,y:mT,width:bw*0.76,height:ih,fill:"none",
        stroke:"var(--line)","stroke-dasharray":"2 4",rx:4}));continue;}
      [[cm[m],"var(--series-1)","Compra devengada",0.12],[pg[m],"var(--series-3)","Pagos ejecutados",0.52]].forEach(function(o){
        var v=o[0];
        if(!nn(v)||v===0){
          var z=S("line",{x1:x0+bw*o[3],x2:x0+bw*(o[3]+0.36),y1:y(0),y2:y(0),stroke:"var(--text-muted)","stroke-width":2});
          hover(z,MESES[m],[[o[2],"0 (cero real)"]]);g.appendChild(z);return;
        }
        var r=S("rect",{x:x0+bw*o[3],width:bw*0.36,y:y(v),height:Math.max(1.5,Math.abs(v)/max*ih),rx:3,fill:o[1]});
        hover(r,MESES[m]+" "+D.anio,[["Compra devengada",money(cm[m],curOf(p))],
          ["Pagos ejecutados",money(pg[m],curOf(p))],
          ["Diferencia",money((cm[m]||0)-(pg[m]||0),curOf(p))]]);
        g.appendChild(r);
      });
    }
    return g;
  });
}
function secDepartamento(p){
  var cur=curOf(p), k=[];
  k.push(el("div",{"class":"legend"},[
    el("span",{},[el("i",{style:"background:var(--series-1)"}),"Compra devengada (flujo)"]),
    el("span",{},[el("i",{style:"background:var(--series-3)"}),"Pagos ejecutados (caja)"]),
    el("span",{},[el("i",{style:"background:transparent;border:1px dashed var(--line)"}),"Mes futuro"]),
    el("span",{},[el("i",{style:"background:var(--text-muted);height:3px;border-radius:1px"}),"Cero real"])]));
  k.push(chartCompraPagos(p));
  k.push(lectura("Las barras azules son lo que <b>causaste</b> y las verdes lo que <b>pagaste</b>. Cuando la verde "+
    "supera a la azul estás pagando deuda vieja; cuando pasa lo contrario, estás acumulando deuda nueva. "+
    "En el año llevas "+money(conv(p.compra.ytd,p),cur)+" de compra local contra "+
    money(conv(p.pagos.ytd,p),cur)+" de pagos (que incluyen también a proveedores del exterior)."));
  var pgg=p.pagos||{};
  if(pgg.estado_conocido&&pgg.no_aplicados){
    k.push(el("div",{"class":"warnbox",style:"margin-top:14px",html:
      "<b>"+money(conv(pgg.no_aplicados,p),cur)+"</b> de los pagos ("+num(pgg.n_no_aplicados)+
      " movimientos) <b>no están imputados a ninguna factura</b>. Son anticipos o salidas de caja sin factura "+
      "contra la cual aplicarse — habitual en importación, donde se paga antes del embarque. Consecuencia práctica: "+
      "<b>la deuda neta real es menor que la que muestra el aging</b>, porque ese anticipo ya salió del banco pero "+
      "todavía no descontó ninguna factura."+
      ((pgg.top_anticipos||[]).length?" Los mayores: "+pgg.top_anticipos.map(function(x){
        return x.proveedor+" ("+money(conv(x.monto,p),cur,true)+")";}).join(", ")+".":"")}));
  }
  var pd=p.compra.por_departamento||{}, tot=0;
  for(var kk in pd)tot+=pd[kk];
  if(tot){
    k.push(el("h3",{style:"font-size:12px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.08em;margin:18px 0 6px",
      text:"Compra por departamento"}));
    var bar=el("div",{style:"display:flex;gap:2px;height:26px;border-radius:6px;overflow:hidden;margin:0 0 8px"});
    Object.keys(pd).sort(function(a,b){return pd[b]-pd[a];}).forEach(function(d){
      if(!pd[d])return;
      var seg=el("div",{style:"flex:"+Math.abs(pd[d])+" 0 0;background:"+colDep(d)});
      hover(seg,d,[["Compra",money(conv(pd[d],p),cur)],["% del total",pctf(pd[d]/tot)]]);
      bar.appendChild(seg);});
    k.push(bar);
    k.push(el("div",{"class":"legend"},Object.keys(pd).sort(function(a,b){return pd[b]-pd[a];}).map(function(d){
      return el("span",{},[el("i",{style:"background:"+colDep(d)}),d+" · "+money(conv(pd[d],p),cur,true)+" ("+pctf(pd[d]/tot,0)+")"]);})));
  }
  if(nn(p.compra.pct_sin_regla_depto)&&p.compra.pct_sin_regla_depto>0.25)
    k.push(el("div",{"class":"warnbox",html:"<b>"+pctf(p.compra.pct_sin_regla_depto,0)+"</b> de esta compra cae en el "+
      "departamento por defecto porque el proveedor no tiene regla en <code>pagos_reglas_depto.json</code>. "+
      "Mientras eso siga así, la torta de arriba dice más sobre el archivo de reglas que sobre tu operación. "+
      "Se arregla agregando palabras clave a ese archivo, sin tocar código."}));
  var cu=(p.compra.por_cuenta||[]).slice(0,20);
  if(cu.length){
    k.push(el("h3",{style:"font-size:12px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.08em;margin:18px 0 2px",
      text:"Apertura por cuenta contable"}));
    var rows=cu.map(function(c){return {code:c.code,name:c.name,monto:conv(c.monto,p),n:c.n,pct:c.pct};});
    var t=tabla("t-cta",[{t:"Código",k:"code"},{t:"Cuenta",k:"name"},{t:"Compra",k:"monto"},
      {t:"% del total",k:"pct"},{t:"Docs",k:"n"}],rows,
      [function(r){return r.code||"—";},function(r){return r.name||"—";},function(r){return money(r.monto,cur);},
       function(r){return pctf(r.pct,1);},function(r){return num(r.n);}]);
    k.push(t);k.push(csvBtn(t,"cuentas_"+SCOPE));
  }
  return card("Gasto por departamento y cuenta","Compra devengada contra pagos ejecutados, y en qué se fue.",k);
}

/* ===================================================================
   H. REAL VS PRESUPUESTO (Ecuador)
   =================================================================== */
function secPresupuesto(p){
  var pr=p.presupuesto;
  if(!pr||!pr.disponible)return card("Real vs presupuesto","",
    sinDato("Sin presupuesto de gastos 2026 para "+SCOPE,pr?pr.motivo:"", pr?pr.que_falta:""));
  var k=[];
  var pasos=[["Presupuesto original H2",pr.original_total_h2,"var(--text-muted)"],
             ["Resinceramiento de julio",pr.resinceramiento_total,pr.resinceramiento_total>0?"var(--warning)":"var(--good)"],
             ["Presupuesto vigente H2",pr.vigente_total_h2,"var(--series-1)"],
             ["Ejecutado del H2",pr.real_h2_total,"var(--series-3)"]];
  var maxp=Math.max.apply(null,pasos.map(function(x){return Math.abs(x[1]||0);}).concat([1]));
  var wf=el("div",{style:"margin:4px 0 10px"});
  pasos.forEach(function(x){
    var row=el("div",{style:"display:flex;align-items:center;gap:10px;padding:6px 0;border-bottom:1px solid var(--line-soft)"});
    row.appendChild(el("div",{style:"flex:0 0 "+(innerWidth<640?"120px":"200px"),text:x[0]}));
    var track=el("div",{style:"flex:1;height:18px;background:var(--surface-2);border-radius:3px;overflow:hidden"});
    var f=el("div",{style:"width:"+(Math.abs(x[1]||0)/maxp*100)+"%;height:100%;background:"+x[2]+";border-radius:3px"});
    hover(f,x[0],[["Monto",money(x[1],"USD")]]);
    track.appendChild(f);row.appendChild(track);
    row.appendChild(el("div",{style:"flex:0 0 100px;text-align:right;font-family:var(--cond);font-size:17px;"+
      "font-weight:700;font-variant-numeric:tabular-nums",text:money(x[1],"USD",true)}));
    wf.appendChild(row);
  });
  k.push(wf);
  var g=el("div",{"class":"exgrid"});
  [["Original ANUAL 2026",money(pr.original_total_anual,"USD"),"todo el año, como se aprobó en marzo",false],
   ["Real Ene–Jun",money(pr.real_ene_jun,"USD"),"seis meses de gasto efectivo",false],
   ["Avance del H2",pctf(pr.avance_h2_pct,0),num(pr.avance_h2_dias)+" de "+num(pr.dias_h2)+" días",false],
   ["Run-rate H2",money(pr.run_rate_h2,"USD"),pr.ejecucion_comparable?"proyección a fin de semestre":"aún no concluyente",!pr.ejecucion_comparable]
  ].forEach(function(x){g.appendChild(el("div",{"class":"ex"+(x[3]?" alerta":"")},
    [el("div",{"class":"k",text:x[0]}),el("div",{"class":"v",text:x[1]}),el("div",{"class":"n",text:x[2]})]));});
  k.push(g);
  if(!pr.ejecucion_comparable)k.push(el("div",{"class":"warnbox",text:pr.motivo_no_comparable}));
  var txt="El presupuesto original preveía <b>"+money(pr.original_total_anual,"USD")+"</b> para <b>todo 2026</b>, "+
    "pero el gasto real de Enero a Junio ya fue <b>"+money(pr.real_ene_jun,"USD")+"</b>. El resinceramiento de julio "+
    "llevó el presupuesto del semestre de "+money(pr.original_total_h2,"USD")+" a <b>"+money(pr.vigente_total_h2,"USD")+
    "</b>"+(nn(pr.resinceramiento_pct)?", un <b>"+pctf(pr.resinceramiento_pct,0)+"</b> más":"")+". No fue un ajuste fino: corrigió un presupuesto "+
    "construido a alrededor de la mitad de la base de costos real de la compañía.";
  k.push(lectura(txt,"var(--warning)"));
  var rows=(pr.filas||[]).map(function(f){return {codigo:f.codigo,cuenta:f.cuenta,vig:f.ppto_vigente_h2,
    ori:f.ppto_original_h2,resin:f.resinceramiento,eneJun:f.real_ene_jun,h2:f.real_h2_odoo,
    desv:f.desviacion,cumpl:f.cumpl,fuente:f.fuente_real};});
  var t=tabla("t-ppto",[{t:"Código",k:"codigo"},{t:"Cuenta",k:"cuenta"},{t:"Ppto vigente H2",k:"vig"},
    {t:"Ppto original H2",k:"ori"},{t:"Resinceramiento",k:"resin",cls:function(r){return nn(r.resin)?(r.resin>0?"neg":"pos"):"";}},
    {t:"Real Ene–Jun",k:"eneJun"},{t:"Real H2 (Odoo)",k:"h2"},{t:"Fuente",k:"fuente"}],rows,
    [function(r){return r.codigo;},function(r){return r.cuenta;},function(r){return money(r.vig,"USD");},
     function(r){return money(r.ori,"USD");},function(r){return money(r.resin,"USD");},
     function(r){return money(r.eneJun,"USD");},function(r){return money(r.h2,"USD");},
     function(r){return r.fuente||"—";}]);
  k.push(t);k.push(csvBtn(t,"presupuesto_ecuador"));
  var extras=[];
  if((pr.sin_desglosar||[]).length)extras.push("<b>Sin desglosar:</b> "+pr.sin_desglosar.map(function(x){
    return x.cuenta+" ("+money(x.monto,"USD")+")";}).join(", ")+" — presupuestado pero sin abrir por cuenta en el libro.");
  if(pr.n_huerfanas)extras.push("<b>"+pr.n_huerfanas+" cuenta(s) huérfanas:</b> presupuestadas pero sin ningún ancestro en el plan contable.");
  if(pr.n_sin_presupuesto)extras.push("<b>"+pr.n_sin_presupuesto+" cuenta(s) con gasto sin presupuesto:</b> gasto real que nadie presupuestó.");
  if(extras.length)k.push(el("div",{"class":"foot",html:extras.join("<br>")}));
  k.push(el("div",{"class":"foot",text:(pr.nota_fuentes||"")+" "+(pr.nivel_cruce||"")}));
  return card("Real vs presupuesto — Ecuador","Original, resinceramiento, vigente y ejecutado. Cada uno en su escala.",k);
}

/* ===================================================================
   Excluidos: qué NO está en el dashboard y por qué
   =================================================================== */
function secExcluidos(p){
  var cur=curOf(p), e=p.excluido, k=[];
  var g=el("div",{"class":"exgrid"});
  var items=[["Importación de mercadería",(e.importacion||{}).monto,(e.importacion||{}).n,
              "Compra al exterior y su cadena. No es gasto operativo local: entra a inventario.",false],
             ["Servicios del exterior",(e.servicios_exterior||{}).monto,(e.servicios_exterior||{}).n,
              "Software, suscripciones, viajes y certificaciones de proveedores no domiciliados. SÍ es gasto operativo, pero de fuera.",false],
             ["Sin clasificar",(e.sin_clasificar||{}).monto,(e.sin_clasificar||{}).n,
              "Proveedores sin país cargado en Odoo. No se reparten ni se esconden.",(e.sin_clasificar||{}).monto>0],
             ["No operativo",e.no_operativo_total,null,
              "Bancos, impuestos, nómina, intercompañía y préstamos a socios.",false]];
  items.forEach(function(x){
    if(!x[1])return;
    g.appendChild(el("div",{"class":"ex"+(x[4]?" alerta":"")},[
      el("div",{"class":"k",text:x[0]}),
      el("div",{"class":"v",text:money(conv(x[1],p),cur,true)}),
      el("div",{"class":"n",text:(x[2]!=null?num(x[2])+" documentos · ":"")+x[3]})]));
  });
  k.push(g);
  var no=e.no_operativo||{};
  if(Object.keys(no).length){
    var rows=Object.keys(no).map(function(kk){return {motivo:kk,monto:conv(no[kk].monto,p),n:no[kk].n};});
    rows.sort(function(a,b){return Math.abs(b.monto)-Math.abs(a.monto);});
    var t=tabla("t-exc",[{t:"Motivo de exclusión",k:"motivo"},{t:"Monto",k:"monto"},{t:"Líneas",k:"n"}],rows,
      [function(r){return r.motivo;},function(r){return money(r.monto,cur);},function(r){return num(r.n);}]);
    k.push(t);k.push(csvBtn(t,"excluidos_"+SCOPE));
  }
  var tops=[];
  ["importacion","servicios_exterior","sin_clasificar"].forEach(function(kk){
    ((e[kk]||{}).proveedores||[]).slice(0,4).forEach(function(x){
      tops.push({tipo:kk,proveedor:x.proveedor,monto:x.monto});});});
  if(tops.length){
    k.push(el("div",{"class":"foot",html:"Principales excluidos: "+tops.map(function(x){
      return "<b>"+x.proveedor+"</b> "+money(conv(x.monto,p),cur,true);}).join(" · ")}));
  }
  var ce=p.comercio_exterior_local||{};
  if(ce.monto)k.push(el("div",{"class":"warnbox",html:
    "<b>"+money(conv(ce.monto,p),cur)+"</b> de la compra local son <b>servicios de comercio exterior</b> facturados "+
    "por agentes constituidos en el país (agencias de aduana, forwarders, navieras representadas). Entran como "+
    "locales porque el proveedor lo es, pero el gasto es de importación. Están marcados para poder aislarlos: "+
    ((ce.proveedores||[]).slice(0,4).map(function(x){return x.proveedor;}).join(", ")||"")}));
  var pu=p.compra.puente||{};
  k.push(el("div",{"class":"foot",html:"<b>Puente de la compra local:</b> se facturaron "+
    money(conv(pu.neto_facturas_local,p),cur)+" a proveedores locales, de los cuales "+
    money(conv(pu.gasto_operativo,p),cur)+" son gasto operativo, "+money(conv(pu.menos_no_operativo,p),cur)+
    " se excluyeron por no operativos y "+money(conv(pu.resto_a_cuentas_de_balance,p),cur)+
    " fueron a cuentas de balance (inventario, IVA, activos de importación). Ninguna de esas dos últimas es gasto del período."}));
  return card("Qué NO está en este dashboard","Todo lo excluido, con su monto y su motivo. Un excluido invisible es un número mentiroso.",k);
}

/* ===================================================================
   Consolidado
   =================================================================== */
function secGrupo(){
  var c=D.consolidado, k=[];
  var comp=c.por_pais||[];
  var COL=["var(--series-1)","var(--series-2)","var(--series-3)"];
  var bar=el("div",{style:"display:flex;gap:2px;height:30px;border-radius:8px;overflow:hidden;margin:6px 0 10px"});
  comp.forEach(function(x,i){
    if(!(x.cxp_usd>0))return;
    var d=el("div",{style:"flex:"+x.cxp_usd+" 0 0;background:"+COL[i%3]+";display:flex;align-items:center;"+
      "justify-content:center;font-size:11px;font-weight:600;color:#fff"});
    if(x.pct_cxp>0.12)d.textContent=x.pais+" "+pctf(x.pct_cxp,0);
    hover(d,x.pais,[["CxP (USD ref.)",money(x.cxp_usd,"USD")],["En moneda local",money(x.cxp_local,x.moneda)],
      ["% de la CxP del grupo",pctf(x.pct_cxp)],["Vencido",pctf(x.pct_vencido)]]);
    bar.appendChild(d);});
  k.push(el("div",{style:"font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--text-muted);margin-bottom:4px",
    text:"Dónde está la deuda"}));
  k.push(bar);
  k.push(el("div",{"class":"legend"},comp.map(function(x,i){
    return el("span",{},[el("i",{style:"background:"+COL[i%3]}),x.pais+" · "+money(x.cxp_usd,"USD",true)+" ("+pctf(x.pct_cxp,0)+")"]);})));
  k.push(el("div",{style:"margin-top:6px"},el("span",{"class":"badge tc",
    text:"USD referencial · COP "+num(D.tc.cop_por_usd)+" · CRC "+num(D.tc.crc_por_usd)})));
  var peor=comp.slice().sort(function(a,b){return (b.pct_vencido_grupo||0)-(a.pct_vencido_grupo||0);})[0];
  var lento=comp.slice().filter(function(x){return nn(x.dpo);}).sort(function(a,b){return (b.dpo||0)-(a.dpo||0);})[0];
  var rapido=comp.slice().filter(function(x){return nn(x.dias_pago_real);}).sort(function(a,b){return (a.dias_pago_real||0)-(b.dias_pago_real||0);})[0];
  var txt="El grupo debe <b>"+money(c.cxp_total,"USD")+"</b> (USD referencial), de los cuales <b>"+
    pctf(c.pct_vencido)+"</b> está vencido.";
  if(peor)txt+=" <b>"+peor.pais+"</b> concentra el <b>"+pctf(peor.pct_vencido_grupo)+"</b> de esa mora: "+
    "el problema de pagos del grupo es, en la práctica, el de ese país.";
  if(lento&&lento.dpo>120)txt+=" Con un DPO de <b>"+num(lento.dpo,0)+" días</b> en "+lento.pais+
    ", ahí no hay plazo negociado sino deuda que dejó de rotar.";
  if(rapido&&rapido.dias_pago_real<5)txt+=" En cambio "+rapido.pais+" paga a "+num(rapido.dias_pago_real,0)+
    " días del vencimiento: es el país donde hay margen para pedir plazo sin romper nada.";
  k.push(lectura(txt));
  var rows=comp.map(function(x){return {pais:x.pais,moneda:x.moneda,compra:x.compra_local,compra_usd:x.compra_usd,
    cxp:x.cxp_local,cxp_usd:x.cxp_usd,venc:x.pct_vencido,dpo:x.dpo,pago:x.dias_pago_real,hhi:x.hhi,sem:x.a_pagar_7_usd};});
  var t=tabla("t-grupo",[{t:"País",k:"pais"},{t:"Compra local",k:"compra"},{t:"Compra USD ref.",k:"compra_usd"},
    {t:"CxP local",k:"cxp"},{t:"CxP USD ref.",k:"cxp_usd"},
    {t:"% vencido",k:"venc",cls:function(r){return r.venc>0.5?"neg":"";}},
    {t:"DPO",k:"dpo",cls:function(r){return r.dpo>120?"neg":"";}},
    {t:"Días de pago real",k:"pago"},{t:"HHI",k:"hhi",cls:function(r){return r.hhi>2500?"neg":"";}},
    {t:"Vence en 7 días (USD)",k:"sem"}],rows,
    [function(r){return r.pais;},function(r){return money(r.compra,r.moneda);},function(r){return money(r.compra_usd,"USD");},
     function(r){return money(r.cxp,r.moneda);},function(r){return money(r.cxp_usd,"USD");},
     function(r){return pctf(r.venc,0);},function(r){return nn(r.dpo)?num(r.dpo,0)+" d":"—";},
     function(r){return nn(r.pago)?num(r.pago,0)+" d":"—";},function(r){return num(r.hhi);},
     function(r){return money(r.sem,"USD");}]);
  k.push(t);k.push(csvBtn(t,"comparativo_compras_paises"));
  k.push(el("div",{"class":"foot",text:c.nota}));
  return card("Compras y cuentas por pagar — Grupo VICOMER",
    "Todo el consolidado en USD es REFERENCIAL: Odoo no mantiene tipos de cambio. La cifra que manda es la de cada país en su moneda.",k);
}
function secPaises(){
  return ORDEN.map(function(kk){
    var p=D.paises[kk]; if(!p)return null;
    var cx=p.cxp;
    return card(kk+" — resumen","Moneda autoritativa: "+p.moneda+".",[
      lectura("<b>"+kk+"</b>: compra local "+money(p.compra.ytd,p.moneda)+" YTD · CxP "+money(cx.total,p.moneda)+
        " ("+pctf(cx.pct_vencido,0)+" vencida, "+pctf(cx.pct_vencido_mas_30,0)+" a más de 30 días) · pagos "+
        money(p.pagos.ytd,p.moneda)+" · DPO "+(nn(p.dpo.puntual)?num(p.dpo.puntual,0)+" días":"sin dato")+
        " · HHI "+num(p.concentracion.hhi)+
        (p.presupuesto.disponible?" · presupuesto vigente H2 "+money(p.presupuesto.vigente_total_h2,"USD"):
         " · <b>sin presupuesto de gastos cargado</b>")+"."),
      el("div",{"class":"btn",style:"display:inline-block;cursor:pointer",onclick:(function(kk2){
        return function(){SCOPE=kk2;ST.moneda="local";boot();};})(kk)},"Ver el detalle de "+kk)]);
  }).filter(Boolean);
}

/* ===================================================================
   I. PANEL DE INTEGRIDAD (obligatorio)
   =================================================================== */
function secIntegridad(){
  var av=D.avisos||[], crit=av.filter(function(a){return a.nivel==="critico";}).length;
  var body=el("div",{"class":"body"});
  body.appendChild(el("div",{"class":"hint",text:
    "No se puede omitir por estética. Lista todo lo que este tablero NO sabe y de dónde sale cada bloque."}));
  var cob=D.cobertura_clasificacion||{};
  var g=el("div",{"class":"exgrid"});
  g.appendChild(el("div",{"class":"ex"+(cob.cobertura>=0.95?"":" alerta")},[
    el("div",{"class":"k",text:"Clasificación de proveedores"}),
    el("div",{"class":"v",text:pctf(cob.cobertura,1)}),
    el("div",{"class":"n",text:num(cob.con_pais)+" de "+num(cob.n_proveedores)+" con país cargado en Odoo"})]));
  if((cob.pendientes||[]).length)g.appendChild(el("div",{"class":"ex alerta"},[
    el("div",{"class":"k",text:"Sin país"}),
    el("div",{"class":"v",text:num(cob.pendientes.length)}),
    el("div",{"class":"n",text:cob.pendientes.map(function(x){return x.nombre;}).join(", ")})]));
  body.appendChild(g);
  body.appendChild(el("div",{"class":"foot",text:"Regla usada: "+(cob.regla||"")}));
  body.appendChild(el("h3",{style:"font-size:12px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.08em;margin:18px 0 2px",
    text:"Avisos ("+av.length+(crit?" · "+crit+" crítico"+(crit>1?"s":""):"")+")"}));
  if(!av.length)body.appendChild(el("div",{"class":"aviso"},[el("div",{"class":"tx",text:"Sin avisos."})]));
  av.forEach(function(a){body.appendChild(el("div",{"class":"aviso"},[
    el("div",{"class":"lv "+a.nivel,text:a.nivel}),
    el("div",{"class":"tx",html:"<b>"+(a.pais||"Grupo")+" · "+a.bloque+"</b> — "+a.texto})]));});
  var conc=D.conciliacion||{};
  body.appendChild(el("h3",{style:"font-size:12px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.08em;margin:20px 0 2px",
    text:"Conciliación contra las fuentes ya validadas"}));
  var tw=el("div",{"class":"tblwrap"}),t=el("table"),th=el("thead"),tr=el("tr");
  ["","País","Concepto","Dashboard","Referencia","Diferencia"].forEach(function(h){tr.appendChild(el("th",{text:h}));});
  th.appendChild(tr);t.appendChild(th);var tb=el("tbody");
  (conc.filas||[]).forEach(function(f){
    var ok=f.cuadra, tol=f.tolerable&&!ok;
    tb.appendChild(el("tr",{},[
      el("td",{style:"font-weight:700;color:"+(ok?"var(--good)":(tol?"var(--warning)":"var(--critical)")),
        text:ok?"✓":(tol?"~":"✗")}),
      el("td",{text:f.pais}),el("td",{text:f.concepto}),
      el("td",{text:num(f.dashboard,2)}),el("td",{text:f.referencia==null?"—":num(f.referencia,2)}),
      el("td",{"class":f.diferencia?"neg":"",text:f.diferencia==null?"—":num(f.diferencia,2)})]));
    if(f.nota)tb.appendChild(el("tr",{},[el("td",{}),el("td",{colspan:"5",style:"color:var(--text-muted);font-size:11.5px;white-space:normal",text:f.nota})]));
  });
  t.appendChild(tb);tw.appendChild(t);body.appendChild(tw);
  body.appendChild(el("div",{"class":"foot",text:(conc.todo_cuadra?
    "Todas las líneas duras cuadran. ":"Hay diferencias duras: se muestran arriba tal como salen. ")+(conc.nota||"")}));
  body.appendChild(el("h3",{style:"font-size:12px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.08em;margin:20px 0 2px",
    text:"Fuente y fecha de cada bloque"}));
  var sg=el("div",{"class":"srcgrid"});
  var F=D.fuentes||{};
  var items=[["Compra devengada",F.compra],["Saldo de CxP",F.cxp],["Pagos ejecutados",F.pagos],
    ["Reglas de clasificación",F.reglas],
    ["CxP de referencia",F.cxp_referencia?("cxp_semana_actual.json generada "+F.cxp_referencia):"(no disponible)"],
    ["Extracción Odoo",D.generado+" · "+D.odoo.url+" · db "+D.odoo.db+" · "+D.odoo.llamadas+" llamadas XML-RPC"],
    ["Tipo de cambio",D.tc.fuente+" — COP "+num(D.tc.cop_por_usd)+"/USD, CRC "+num(D.tc.crc_por_usd)+"/USD. REFERENCIAL."],
    ["Excluido a propósito","Compañías: "+((D.excluidas_del_grupo||[]).join(", ")||"ninguna")+
      ". Proveedores del exterior (en su propia tarjeta). Bancos, impuestos, nómina, intercompañía y préstamos a socios. "+
      "Los tres números —compra, CxP y pagos— nunca se suman entre sí."]];
  var pp=(F.presupuesto||{});
  Object.keys(pp).forEach(function(kk){items.push(["Presupuesto · "+kk,pp[kk]]);});
  items.forEach(function(x){sg.appendChild(el("div",{"class":"src"},[el("div",{"class":"k",text:x[0]}),
    el("div",{"class":"v",text:String(x[1]||"—")})]));});
  body.appendChild(sg);
  return el("details",{"class":"integrity",id:"integridad"},[
    el("summary",{},["Panel de integridad de datos"+(av.length?" — "+av.length+" aviso"+(av.length>1?"s":""):"")]),body]);
}

/* ===================================================================
   Controles, tabs y arranque
   =================================================================== */
function controles(){
  var box=el("div",{"class":"controls"});
  if(!esCons()){
    var p=P();
    if(p&&p.moneda!=="USD"){
      box.appendChild(el("span",{"class":"ctl-label",text:"Moneda"}));
      var s2=el("div",{"class":"seg"});
      [["local",p.moneda],["usd","USD ref."]].forEach(function(o){
        s2.appendChild(el("button",{text:o[1],"aria-pressed":ST.moneda===o[0]?"true":"false",
          onclick:function(){ST.moneda=o[0];render();}}));});
      box.appendChild(s2);
    }
  }
  box.appendChild(el("button",{"class":"btn",style:"margin-left:auto",text:"Imprimir / PDF",
    onclick:function(){window.print();}}));
  return box;
}

var ROOT;
function render(){
  CHARTS.length=0;
  ROOT.innerHTML="";
  ROOT.appendChild(controles());
  ROOT.appendChild(tresMetricas());
  var paneles=[];
  if(esCons()){
    ROOT.appendChild(kpisConsolidado());
    paneles.push(["Grupo",[secGrupo()]]);
    paneles.push(["Por país",secPaises()]);
  } else {
    var p=P();
    if(!p){ROOT.appendChild(sinDato("Sin datos para "+SCOPE,"El pipeline no devolvió este país.",
      "Revisar company_map en odoo_config.json."));return;}
    ROOT.appendChild(kpisPais(p));
    paneles.push(["Deuda y aging",[secAging(p)]]);
    paneles.push(["Calendario y caja",[secCalendario(p)]]);
    paneles.push(["DPO y negociación",[secDPO(p)]]);
    paneles.push(["Proveedores",[secConcentracion(p)]]);
    paneles.push(["Gasto",[secDepartamento(p)]]);
    paneles.push(["Presupuesto",[secPresupuesto(p)]]);
    paneles.push(["Excluidos",[secExcluidos(p)]]);
  }
  var tabs=el("div",{"class":"tabs",role:"tablist"}), host=el("div");
  paneles.forEach(function(pn,i){
    var b=el("button",{"class":"tab",role:"tab","aria-selected":i===0?"true":"false",text:pn[0]});
    var panel=el("div",{"class":"panel"});
    if(i!==0)panel.setAttribute("hidden","");
    pn[1].forEach(function(x){if(x)panel.appendChild(x);});
    b.addEventListener("click",function(){
      Array.prototype.forEach.call(tabs.children,function(t){t.setAttribute("aria-selected","false");});
      Array.prototype.forEach.call(host.children,function(t){t.setAttribute("hidden","");});
      b.setAttribute("aria-selected","true");panel.removeAttribute("hidden");
      CHARTS.forEach(function(f){try{f();}catch(e){}});
    });
    tabs.appendChild(b);host.appendChild(panel);
  });
  ROOT.appendChild(tabs);ROOT.appendChild(host);
  ROOT.appendChild(secIntegridad());
  ROOT.appendChild(el("div",{"class":"foot",html:
    "Generado por <b>compras_dashboard.py</b> + <b>compras_dashboard_render.py</b> el "+D.generado+
    ". Archivo autocontenido: abre sin internet. Compra devengada, saldo de CxP y pagos ejecutados son tres "+
    "métricas distintas y jamás se suman. Lo que no está, se declara."}));
}

function boot(){
  document.body.innerHTML="";
  document.body.appendChild(el("div",{id:"tip"}));
  TIP=document.getElementById("tip");
  document.body.appendChild(statusBar());
  var p=esCons()?null:P();
  var wrap=el("div",{"class":"wrap"});
  wrap.appendChild(el("header",{"class":"page"},[
    el("h1",{text:esCons()?"Compras y cuentas por pagar · Grupo VICOMER":"Compras y CxP · "+SCOPE}),
    el("div",{"class":"sub",text:(esCons()?"Ecuador · Colombia · Costa Rica — VIX excluida":
      "Moneda autoritativa "+(p?p.moneda:"")+
      ((p&&p.compra.ventana_datos&&p.compra.ventana_datos.primera)?
        " · facturas en Odoo desde "+fecha(p.compra.ventana_datos.primera)+" hasta "+fecha(p.compra.ventana_datos.ultima):""))+
      "  |  Año "+D.anio+"  |  Datos al "+fecha(D.generado_fecha)})]));
  ROOT=el("div");wrap.appendChild(ROOT);
  document.body.appendChild(wrap);
  render();
  window.scrollTo(0,0);
}
document.addEventListener("DOMContentLoaded",boot);
})();
"""


def build(doc, scope, titulo):
    datos = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = HEAD.replace("__TITULO__", titulo)
    html += "<script>window.__DATA__=" + datos + ";window.__SCOPE__=" + json.dumps(scope) + ";</script>\n"
    html += "<script>\n" + JS + "\n</script>\n</body>\n</html>\n"
    return html


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    src = Path(a.json) if a.json else (OUT_DIR / "dashboard_compras.json")
    out = Path(a.out) if a.out else OUT_DIR
    if not src.exists():
        sys.exit("ERROR: no existe %s. Corre primero: python3 compras_dashboard.py" % src)
    doc = json.loads(src.read_text(encoding="utf-8"))
    out.mkdir(parents=True, exist_ok=True)
    for scope, fname, titulo in SALIDAS:
        if scope != "__CONSOLIDADO__" and scope not in (doc.get("paises") or {}):
            print("  [!] %s no viene en el JSON: el HTML lo declara como bloque sin datos." % scope)
        dest = out / fname
        tmp = dest.with_suffix(".html.tmp")
        tmp.write_text(build(doc, scope, titulo), encoding="utf-8")
        os.replace(str(tmp), str(dest))
        print("  [OK] %-46s %7.0f KB" % (fname, dest.stat().st_size / 1024.0))
    av = doc.get("avisos") or []
    print("\n%d dashboards en %s" % (len(SALIDAS), out))
    print("Avisos embebidos: %d (%d criticos). Datos: %s" %
          (len(av), len([x for x in av if x.get("nivel") == "critico"]), doc.get("generado")))
    print("Conciliacion: %s" % ("CUADRA" if (doc.get("conciliacion") or {}).get("todo_cuadra") else "CON DIFERENCIAS"))


if __name__ == "__main__":
    main()
