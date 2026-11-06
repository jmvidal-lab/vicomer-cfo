#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ventas_dashboard_render.py  ·  Grupo VICOMER
============================================
JSON -> 4 dashboards HTML AUTOCONTENIDOS (Ecuador, Colombia, Costa Rica, Consolidado).

No toca Odoo. Lee OdooVentas/dashboard_ventas.json (el contrato que deja
ventas_dashboard.py) y escribe:

    OdooVentas/Dashboard_Ventas_Ecuador.html
    OdooVentas/Dashboard_Ventas_Colombia.html
    OdooVentas/Dashboard_Ventas_CostaRica.html
    OdooVentas/Dashboard_Ventas_Consolidado_Grupo.html

Cada archivo lleva su CSS, su JS y sus datos embebidos: abre sin internet,
sin CDN y sin localStorage (eso rompe los artefactos publicados).

Uso:
    python3 ventas_dashboard_render.py
    python3 ventas_dashboard_render.py --json ruta.json --out carpeta

Solo biblioteca estandar.
"""
import os, sys, json, datetime, argparse
from pathlib import Path

HOME = Path.home()
PROJ = Path(os.environ.get("VICOMER_PROJ", HOME / "Claude" / "Projects" / "CFO VICOMER"))
OUT_DIR = Path(os.environ.get("ODOO_OUT_DIR", PROJ / "OdooVentas"))

SALIDAS = [
    ("Ecuador",        "Dashboard_Ventas_Ecuador.html",            "Dashboard de Ventas - Ecuador | Grupo VICOMER"),
    ("Colombia",       "Dashboard_Ventas_Colombia.html",           "Dashboard de Ventas - Colombia | Grupo VICOMER"),
    ("Costa Rica",     "Dashboard_Ventas_CostaRica.html",          "Dashboard de Ventas - Costa Rica | Grupo VICOMER"),
    ("__CONSOLIDADO__","Dashboard_Ventas_Consolidado_Grupo.html",  "Consolidado Grupo VICOMER | Ventas"),
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
var D = window.__DATA__, SCOPE = window.__SCOPE__;
var CONS = SCOPE === "__CONSOLIDADO__";
var MESES = D.meses;
var TIP = document.getElementById("tip");

/* ---------- estado ---------- */
var ST = { periodo:"ytd", moneda:"local", sort:{} };

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
function chartRealPpto(p){
  var mesCierre=p.mes_cierre, mesAct=p.mes_actual;
  return chartHost(function(w){return w<560?250:310},function(w,h){
    var real=p.mensual.map(function(v){return conv(v,p);});
    var ppto=p.ppto_mensual?p.ppto_mensual.map(function(v){return conv(v,p);}):null;
    var vals=real.concat(ppto||[]).filter(nn);
    var max=nice(Math.max.apply(null,vals.concat([1])));
    var mL=w<560?42:62, mR=10, mT=14, mB=26;
    var iw=w-mL-mR, ih=h-mT-mB;
    var bw=iw/12, y=function(v){return mT+ih-(v/max)*ih;};
    var g=S("svg",{width:w,height:h,role:"img"});
    ticks(max,4).forEach(function(t){
      g.appendChild(S("line",{x1:mL,x2:w-mR,y1:y(t),y2:y(t),"class":"gl"}));
      var tx=S("text",{x:mL-6,y:y(t)+3.5,"text-anchor":"end","class":"ax"});
      tx.textContent=money(t,curOf(p),true).replace(/^\$/,""); g.appendChild(tx);
    });
    for(var m=0;m<12;m++){
      var cx=mL+bw*m, futuro=(m+1)>mesAct;
      var tx=S("text",{x:cx+bw/2,y:h-8,"text-anchor":"middle","class":"ax"});
      tx.textContent=MESES[m]; if(futuro)tx.setAttribute("opacity",".45"); g.appendChild(tx);
      var v=real[m];
      if(futuro){
        var ph=S("rect",{x:cx+bw*0.16,y:mT,width:bw*0.68,height:ih,fill:"none",
          stroke:"var(--line)","stroke-dasharray":"2 4",rx:4});
        g.appendChild(ph); continue;
      }
      if(nn(v)&&v!==0){
        var neg=v<0, hgt=Math.max(2,Math.abs(v)/max*ih);
        var r=S("rect",{x:cx+bw*0.16,width:bw*0.68,y:neg?y(0):y(Math.abs(v)),height:hgt,rx:4,
          fill:neg?"var(--critical)":"var(--series-1)"});
        var srcMes = p.mensual_hist&&p.mensual_hist[m]?"histórico pre-migración":"Odoo";
        hover(r,MESES[m]+" "+D.anio,[["Real",money(v,curOf(p))],
          ppto&&nn(ppto[m])?["Presupuesto",money(ppto[m],curOf(p))]:null,
          ppto&&nn(ppto[m])&&ppto[m]?["Cumplimiento",pctf(v/ppto[m])]:null,
          ["Fuente",srcMes]].filter(Boolean));
        g.appendChild(r);
      } else {
        var z=S("line",{x1:cx+bw*0.16,x2:cx+bw*0.84,y1:y(0),y2:y(0),
          stroke:"var(--text-muted)","stroke-width":2});
        hover(z,MESES[m]+" "+D.anio,[["Real","0 (cero real, no dato faltante)"]]);
        g.appendChild(z);
      }
    }
    if(ppto){
      var d="",pts=[];
      for(var m2=0;m2<12;m2++){ if(!nn(ppto[m2]))continue;
        var X=mL+bw*m2+bw/2, Y=y(ppto[m2]); d+=(d?"L":"M")+X+" "+Y; pts.push([X,Y,m2]); }
      g.appendChild(S("path",{d:d,fill:"none",stroke:"var(--series-2)","stroke-width":2,
        "stroke-dasharray":"6 4","stroke-linejoin":"round"}));
      pts.forEach(function(q){
        var c=S("circle",{cx:q[0],cy:q[1],r:3.4,fill:"var(--series-2)",
          stroke:"var(--surface-1)","stroke-width":2});
        hover(c,MESES[q[2]]+" — presupuesto",[["Presupuesto",money(ppto[q[2]],curOf(p))],
          nn(real[q[2]])?["Real",money(real[q[2]],curOf(p))]:null].filter(Boolean));
        g.appendChild(c);
      });
    }
    return g;
  });
}

/* gráfico de cumplimiento acumulado (eje propio, %) */
function chartAcum(p){
  if(!p.ppto_mensual)return null;
  return chartHost(function(w){return 130},function(w,h){
    var mL=w<560?42:62,mR=10,mT=12,mB=22,iw=w-mL-mR,ih=h-mT-mB,bw=iw/12;
    var ar=0,ap=0,pts=[];
    for(var m=0;m<12;m++){
      if(m+1>p.mes_cierre)break;
      ar+=p.mensual[m]||0; ap+=p.ppto_mensual[m]||0;
      if(ap)pts.push([m,ar/ap]);
    }
    if(!pts.length)return S("svg",{width:w,height:1});
    var lo=Math.min(0.5,Math.min.apply(null,pts.map(function(q){return q[1];}))-0.05);
    var hi=Math.max(1.15,Math.max.apply(null,pts.map(function(q){return q[1];}))+0.05);
    var y=function(v){return mT+ih-((v-lo)/(hi-lo))*ih;};
    var g=S("svg",{width:w,height:h});
    [1].concat(lo<0.85?[0.85]:[]).forEach(function(t){
      g.appendChild(S("line",{x1:mL,x2:w-mR,y1:y(t),y2:y(t),stroke:t===1?"var(--good)":"var(--warning)",
        "stroke-width":1,"stroke-dasharray":"3 4",opacity:.6}));
      var tx=S("text",{x:w-mR,y:y(t)-4,"text-anchor":"end","class":"ax"});
      tx.textContent=(t*100).toFixed(0)+"%";g.appendChild(tx);
    });
    var d="",area="";
    pts.forEach(function(q,i){var X=mL+bw*q[0]+bw/2,Y=y(q[1]);
      d+=(i?"L":"M")+X+" "+Y; area+=(i?"L":"M")+X+" "+Y;});
    var x0=mL+bw*pts[0][0]+bw/2, x1=mL+bw*pts[pts.length-1][0]+bw/2;
    area+="L"+x1+" "+y(lo)+"L"+x0+" "+y(lo)+"Z";
    g.appendChild(S("path",{d:area,fill:"var(--series-1)",opacity:.13}));
    g.appendChild(S("path",{d:d,fill:"none",stroke:"var(--series-1)","stroke-width":2,"stroke-linejoin":"round"}));
    pts.forEach(function(q){var c=S("circle",{cx:mL+bw*q[0]+bw/2,cy:y(q[1]),r:3.6,
      fill:semColor(q[1]),stroke:"var(--surface-1)","stroke-width":2});
      hover(c,"Acumulado a "+MESES[q[0]],[["Cumplimiento YTD",pctf(q[1])]]);g.appendChild(c);});
    var lab=S("text",{x:mL,y:mT-2,"class":"ax"});lab.textContent="Cumplimiento acumulado";g.appendChild(lab);
    return g;
  });
}

/* ===================================================================
   GRÁFICO D1 — venta neta (barras) / D2 — margen % (línea). Ejes separados.
   =================================================================== */
function chartMargen(p){
  var mg=p.margen;
  return chartHost(function(w){return 210},function(w,h){
    var mL=w<560?42:62,mR=10,mT=14,mB=40,iw=w-mL-mR;
    var top=Math.round((h-mB)*0.56), bot=(h-mB)-top-10;
    var bw=iw/12;
    var ventas=mg.mensual.map(function(x){return nn(x.venta)?conv(x.venta,p):null;});
    var max=nice(Math.max.apply(null,ventas.filter(nn).concat([1])));
    var g=S("svg",{width:w,height:h});
    var y1=function(v){return mT+top-(v/max)*top;};
    ticks(max,3).forEach(function(t){
      g.appendChild(S("line",{x1:mL,x2:w-mR,y1:y1(t),y2:y1(t),"class":"gl"}));
      var tx=S("text",{x:mL-6,y:y1(t)+3.5,"text-anchor":"end","class":"ax"});
      tx.textContent=money(t,curOf(p),true).replace(/^\$/,"");g.appendChild(tx);});
    mg.mensual.forEach(function(x,m){
      if(!nn(x.venta))return;
      var r=S("rect",{x:mL+bw*m+bw*0.18,width:bw*0.64,y:y1(Math.max(x.venta<0?0:conv(x.venta,p),0)),
        height:Math.max(1,Math.abs(conv(x.venta,p))/max*top),rx:4,fill:"var(--series-1)",opacity:.85});
      hover(r,MESES[m]+" — venta contable",[["Venta neta",money(conv(x.venta,p),curOf(p))],
        ["COGS",money(conv(x.cogs,p),curOf(p))],["Margen",money(conv(x.margen,p),curOf(p))],
        ["Margen %",pctf(x.margen_pct)]]);
      g.appendChild(r);});
    var bt=mT+top+22;
    var pcts=(mg.mensual_confiable===false)?[]:mg.mensual.map(function(x){return x.margen_pct;});
    if(mg.mensual_confiable===false){
      var av=S("text",{x:mL,y:bt+18,"class":"dlabel",fill:"var(--serious)"});
      av.textContent="Margen mensual no confiable — ver nota. Sólo el acumulado del año es utilizable.";
      g.appendChild(av);
    }
    var vv=pcts.filter(nn); var lo=Math.min.apply(null,vv.concat([0])), hi=Math.max.apply(null,vv.concat([0.1]));
    if(hi-lo<0.05)hi=lo+0.05;
    var y2=function(v){return bt+bot-((v-lo)/(hi-lo))*bot;};
    g.appendChild(S("line",{x1:mL,x2:w-mR,y1:y2(lo),y2:y2(lo),"class":"axline"}));
    var lab2=S("text",{x:mL,y:bt-6,"class":"ax"});lab2.textContent="Margen bruto %";g.appendChild(lab2);
    [lo,hi].forEach(function(t){var tx=S("text",{x:mL-6,y:y2(t)+3.5,"text-anchor":"end","class":"ax"});
      tx.textContent=(t*100).toFixed(0)+"%";g.appendChild(tx);});
    var d="",prev=null;
    pcts.forEach(function(v,m){if(!nn(v))return;var X=mL+bw*m+bw/2,Y=y2(v);
      d+=(prev===null?"M":"L")+X+" "+Y;prev=m;});
    if(d)g.appendChild(S("path",{d:d,fill:"none",stroke:"var(--series-3)","stroke-width":2,"stroke-linejoin":"round"}));
    pcts.forEach(function(v,m){if(!nn(v))return;
      var c=S("circle",{cx:mL+bw*m+bw/2,cy:y2(v),r:3.8,fill:"var(--series-3)",
        stroke:"var(--surface-1)","stroke-width":2});
      hover(c,MESES[m]+" — margen",[["Margen %",pctf(v)],
        ["Venta",money(conv(mg.mensual[m].venta,p),curOf(p))],["COGS",money(conv(mg.mensual[m].cogs,p),curOf(p))]]);
      g.appendChild(c);});
    for(var m3=0;m3<12;m3++){var tx=S("text",{x:mL+bw*m3+bw/2,y:h-6,"text-anchor":"middle","class":"ax"});
      tx.textContent=MESES[m3];if(!nn(pcts[m3]))tx.setAttribute("opacity",".45");g.appendChild(tx);}
    return g;
  });
}

/* ===================================================================
   GRÁFICO D3 — mix por producto (barras horizontales)
   =================================================================== */
function chartMix(p){
  var mix=p.mix, porMargen=mix.cogs_por_producto;
  var rows=(mix.productos||[]).slice(0,12).map(function(x){return x;});
  rows.sort(function(a,b){
    var A=porMargen?(a.margen||0):(a.venta||0),B=porMargen?(b.margen||0):(b.venta||0);return B-A;});
  return chartHost(function(w){return Math.max(150,rows.length*26+30)},function(w,h){
    var mL=w<560?110:200,mR=w<560?58:96,iw=w-mL-mR;
    var key=function(x){return porMargen?(x.margen||0):(x.venta||0);};
    var max=Math.max.apply(null,rows.map(function(x){return Math.abs(key(x));}).concat([1]));
    var g=S("svg",{width:w,height:h}), bh=22;
    rows.forEach(function(x,i){
      var Y=14+i*26, v=key(x), wpx=Math.max(2,Math.abs(v)/max*iw);
      var destruye = porMargen && nn(x.margen_pct) && x.margen_pct<0.12 && (x.pct_total||0)>0.03;
      var col = v<0?"var(--critical)":(destruye?"var(--warning)":"var(--series-1)");
      var r=S("rect",{x:mL,y:Y,width:wpx,height:bh,rx:4,fill:col});
      hover(r,x.nombre,[["Venta",money(conv(x.venta,p),curOf(p))],
        nn(x.cogs)?["COGS",money(conv(x.cogs,p),curOf(p))]:null,
        nn(x.margen)?["Margen $",money(conv(x.margen,p),curOf(p))]:null,
        nn(x.margen_pct)?["Margen %",pctf(x.margen_pct)]:null,
        ["% del total",pctf(x.pct_total)],
        destruye?["⚠","Alta venta, bajo margen"]:null].filter(Boolean));
      g.appendChild(r);
      var t=S("text",{x:mL-8,y:Y+15,"text-anchor":"end","class":"dlabel"});
      t.textContent=x.nombre.length>(w<560?16:30)?x.nombre.slice(0,w<560?15:29)+"…":x.nombre;g.appendChild(t);
      var t2=S("text",{x:mL+wpx+7,y:Y+15,"class":"dlabel"});
      t2.textContent=money(conv(v,p),curOf(p),true)+(porMargen&&nn(x.margen_pct)?"  "+pctf(x.margen_pct,0):"");
      g.appendChild(t2);
    });
    return g;
  });
}

/* ===================================================================
   GRÁFICO E — aging apilado por cliente
   =================================================================== */
var BK=["Corriente","1-30","31-60","61-90",">90"];
var BKC=["var(--age-0)","var(--age-1)","var(--age-2)","var(--age-3)","var(--age-4)"];
function chartAging(p){
  var car=p.cartera, cls=(car.clientes||[]).slice(0,10);
  return chartHost(function(w){return Math.max(70,cls.length*30+14)},function(w,h){
    var mL=w<560?104:190,mR=w<560?52:92,iw=w-mL-mR;
    var max=Math.max.apply(null,cls.map(function(c){return Math.abs(c.saldo);}).concat([1]));
    var g=S("svg",{width:w,height:h}),bh=20;
    cls.forEach(function(c,i){
      var Y=12+i*30,x=mL;
      BK.forEach(function(b,bi){
        var v=c.buckets[b]||0; if(!v)return;
        var wpx=Math.max(1.5,Math.abs(v)/max*iw);
        var r=S("rect",{x:x,y:Y,width:Math.max(0.5,wpx-2),height:bh,rx:3,fill:BKC[bi]});
        hover(r,c.cliente,[["Tramo",b],["Saldo",money(conv(v,p),curOf(p))],
          ["% del cliente",pctf(v/c.saldo)],["Saldo total",money(conv(c.saldo,p),curOf(p))],
          ["Vencido",pctf(c.pct_vencido)]]);
        g.appendChild(r); x+=wpx;
      });
      var t=S("text",{x:mL-8,y:Y+14,"text-anchor":"end","class":"dlabel"});
      t.textContent=c.cliente.length>(w<560?14:26)?c.cliente.slice(0,w<560?13:25)+"…":c.cliente;g.appendChild(t);
      var t2=S("text",{x:x+7,y:Y+14,"class":"dlabel"});
      t2.textContent=money(conv(c.saldo,p),curOf(p),true);
      if(nn(c.pct_vencido)&&c.pct_vencido>0.3)t2.setAttribute("fill","var(--critical)");
      g.appendChild(t2);
    });
    return g;
  });
}

/* tendencia de cartera / DSO desde el histórico diario */
function chartSerie(p,campo,titulo,fmt){
  var s=(p.serie_historica||[]).filter(function(x){return nn(x[campo]);});
  if(s.length<2)return null;
  return chartHost(function(w){return 150},function(w,h){
    var mL=w<560?46:64,mR=12,mT=16,mB=22,iw=w-mL-mR,ih=h-mT-mB;
    var vs=s.map(function(x){return x[campo];});
    var lo=Math.min.apply(null,vs),hi=Math.max.apply(null,vs);
    if(hi===lo){hi=lo+Math.abs(lo||1)*0.1;}
    var x=function(i){return mL+(s.length<2?0:i/(s.length-1)*iw);};
    var y=function(v){return mT+ih-((v-lo)/(hi-lo))*ih;};
    var g=S("svg",{width:w,height:h}),d="";
    s.forEach(function(q,i){d+=(i?"L":"M")+x(i)+" "+y(q[campo]);});
    g.appendChild(S("path",{d:d,fill:"none",stroke:"var(--series-3)","stroke-width":2}));
    s.forEach(function(q,i){var c=S("circle",{cx:x(i),cy:y(q[campo]),r:3.4,fill:"var(--series-3)",
      stroke:"var(--surface-1)","stroke-width":2});
      hover(c,fecha(q.fecha),[[titulo,fmt(q[campo])]]);g.appendChild(c);});
    [[lo,"end"],[hi,"end"]].forEach(function(t){var tx=S("text",{x:mL-6,y:y(t[0])+3.5,"text-anchor":"end","class":"ax"});
      tx.textContent=fmt(t[0]);g.appendChild(tx);});
    var a=S("text",{x:mL,y:h-6,"class":"ax"});a.textContent=fecha(s[0].fecha);g.appendChild(a);
    var b=S("text",{x:w-mR,y:h-6,"text-anchor":"end","class":"ax"});b.textContent=fecha(s[s.length-1].fecha);g.appendChild(b);
    return g;
  });
}

/* sparkline de KPI */
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

/* ===================================================================
   A. BARRA DE ESTADO
   =================================================================== */
function statusBar(){
  var av=D.avisos||[];
  var crit=av.filter(function(a){return a.nivel==="critico";}).length;
  var fuente = CONS ? "mixta (3 países)" : (D.paises[SCOPE]||{}).fuente_ventas||"—";
  var inner=el("div",{"class":"inner"},[
    el("span",{"class":"brand",text:"VICOMER"}),
    el("span",{"class":"chip"},[el("span",{"class":"dot",style:"background:var(--good)"}),
      el("span",{},["Datos al "]),el("b",{text:fecha(D.generado_fecha)})]),
    el("span",{"class":"chip"},[el("span",{},["Fuente: "]),el("b",{text:fuente})]),
    el("span",{"class":"chip"},[el("span",{},["Cierre: "]),el("b",{text:MESES[D.mes_cierre-1]+" "+D.anio})]),
    el("span",{"class":"chip tc",title:"Odoo no mantiene tipos de cambio: el USD consolidado es referencial."},
      ["TC referencial: COP "+num(D.tc.cop_por_usd)+" / USD · CRC "+num(D.tc.crc_por_usd)+" · "+(D.tc.fuente||"")]),
    el("span",{"class":av.length?"chip avisos":"chip ok",onclick:function(){
        var d=document.getElementById("integridad"); if(d){d.open=true;d.scrollIntoView({behavior:"smooth"});}
      }},[av.length? (av.length+" aviso"+(av.length>1?"s":"")+(crit?" · "+crit+" crítico"+(crit>1?"s":""):"")) : "sin avisos"])
  ]);
  return el("div",{"class":"statusbar"},inner);
}

/* ===================================================================
   B. KPIs
   =================================================================== */
function kpi(lab,val,cmp,sparkEl,estado,badge){
  var k=el("div",{"class":"kpi"+(val==null?" nd":"")});
  k.appendChild(el("span",{"class":"flag",style:"background:"+(estado||"transparent")}));
  k.appendChild(el("div",{"class":"lab",text:lab}));
  var v=el("div",{"class":"val"+(String(val||"").length>11?" sm":"")});
  v.textContent = val==null?"sin dato":val; k.appendChild(v);
  var c=el("div",{"class":"cmp"});
  (Array.isArray(cmp)?cmp:[cmp]).forEach(function(x){if(!x)return;
    if(typeof x==="string")c.appendChild(document.createTextNode(x)); else c.appendChild(x);});
  if(badge)c.appendChild(el("span",{"class":"badge "+(badge[1]||""),text:badge[0]}));
  k.appendChild(c);
  if(sparkEl)k.appendChild(sparkEl); else k.appendChild(el("div",{"class":"spark"}));
  return k;
}
function delta(v,inv){
  if(!nn(v))return el("span",{"class":"mut",text:"—"});
  var good=inv?v<0:v>0;
  return el("span",{"class":good?"up":"down",text:(v>=0?"▲ ":"▼ ")+Math.abs(v*100).toFixed(1).replace(".",",")+"%"});
}

function kpisPais(p){
  var box=el("div",{"class":"kpis"});
  var cur=curOf(p);
  /* 1 venta YTD */
  box.appendChild(kpi("Venta YTD ("+cur+")",money(conv(p.ytd_real,p),cur,true),
    [nn(p.cumpl_ytd)?el("span",{"class":sem(p.cumpl_ytd),text:pctf(p.cumpl_ytd,0)+" del ppto"}):el("span",{"class":"mut",text:"sin presupuesto"}),
     nn(p.var_ytd)?el("span",{"class":"mut",text:"· "+(p.var_ytd>=0?"+":"")+money(conv(p.var_ytd,p),cur,true)}):null],
    spark(p.mensual,"var(--series-1)",p.mes_cierre),semColor(p.cumpl_ytd),
    ST.moneda==="usd"?["TC referencial","tc"]:null));
  /* 2 MTD */
  var m=p.mtd;
  box.appendChild(kpi("MTD "+MESES[m.mes-1],money(conv(m.real,p),cur,true),
    [nn(m.cumpl)?el("span",{"class":sem(m.cumpl),text:pctf(m.cumpl,0)+" del mes"}):el("span",{"class":"mut",text:"mes sin ppto"}),
     el("span",{"class":"mut",text:"· día "+m.dia+"/"+m.dias_mes+" ("+pctf(m.avance_calendario,0)+" del calendario)"})],
    null,semColor(m.cumpl!=null?m.cumpl/Math.max(m.avance_calendario,0.01):null)));
  /* 3 cumplimiento */
  box.appendChild(kpi("Cumplimiento ppto YTD",nn(p.cumpl_ytd)?pctf(p.cumpl_ytd):null,
    [el("span",{"class":"mut",text:"Ppto YTD "+money(conv(p.ppto_ytd,p),cur,true)}),
     nn(p.run_rate_vs_ppto)?el("span",{"class":sem(p.run_rate_vs_ppto),text:"· run-rate "+pctf(p.run_rate_vs_ppto,0)+" del año"}):null],
    null,semColor(p.cumpl_ytd)));
  /* 4 margen */
  var mg=p.margen||{};
  if(mg.disponible&&mg.ytd){
    var serieMg=mg.mensual.map(function(x){return x.margen_pct;});
    box.appendChild(kpi("Margen bruto % YTD",pctf(mg.ytd.margen_pct),
      [el("span",{"class":"mut",text:"Ut. bruta "+money(conv(mg.ytd.margen,p),cur,true)}),
       mg.cogs_rescatado_por_nombre?el("span",{"class":"badge nd",text:"COGS por nombre"}):null],
      spark(serieMg,"var(--series-3)"),
      mg.ytd.margen_pct>=0.30?"var(--good)":(mg.ytd.margen_pct>=0.20?"var(--warning)":"var(--critical)")));
  } else {
    box.appendChild(kpi("Margen bruto % YTD",null,
      [el("span",{"class":"warn",text:"no calculable"})],null,"var(--serious)",["sin COGS en Odoo","nd"]));
  }
  /* 5 cartera */
  var car=p.cartera||{};
  if(car.disponible){
    box.appendChild(kpi("Cartera total",money(conv(car.total,p),cur,true),
      [el("span",{"class":nn(car.pct_vencido_mas_30)&&car.pct_vencido_mas_30>0.2?"down":"mut",
        text:pctf(car.pct_vencido_mas_30,0)+" vencido +30d"}),
       el("span",{"class":"mut",text:"· "+pctf(car.pct_vencido,0)+" vencido total"})],
      chartSerieMini(p,"cartera"),
      nn(car.pct_vencido_mas_30)?(car.pct_vencido_mas_30>0.25?"var(--critical)":(car.pct_vencido_mas_30>0.1?"var(--warning)":"var(--good)")):null));
  } else {
    box.appendChild(kpi("Cartera total",null,[el("span",{"class":"warn",text:"sin dato"})],null,"var(--serious)",["ver integridad","nd"]));
  }
  /* 6 DSO */
  var ds=p.dso||{};
  box.appendChild(kpi("DSO (días de cobro)",nn(ds.dso_puntual)?num(ds.dso_puntual,0)+" d":null,
    [nn(ds.dias_pago_real)?el("span",{"class":ds.dias_pago_real>15?"down":(ds.dias_pago_real>0?"warn":"up"),
      text:(ds.dias_pago_real>=0?"paga "+num(ds.dias_pago_real,0)+" d tarde":"paga "+num(-ds.dias_pago_real,0)+" d antes")}):
      el("span",{"class":"mut",text:"sin base conciliada"}),
     el("span",{"class":"mut",text:ds.ventana?"· "+ds.ventana:""})],
    chartSerieMini(p,"dso"),
    nn(ds.dso_puntual)?(ds.dso_puntual>90?"var(--critical)":(ds.dso_puntual>60?"var(--warning)":"var(--good)")):null,
    ["puntual","nd"]));
  return box;
}
function chartSerieMini(p,campo){
  var s=(p.serie_historica||[]).filter(function(x){return nn(x[campo]);});
  if(s.length<2)return null;
  return spark(s.map(function(x){return x[campo];}),"var(--series-2)");
}

function kpisConsolidado(){
  var c=D.consolidado, box=el("div",{"class":"kpis"});
  var tcb=["TC referencial","tc"];
  box.appendChild(kpi("Venta YTD grupo (USD)",money(c.ytd_real,"USD",true),
    [nn(c.cumpl_ytd)?el("span",{"class":sem(c.cumpl_ytd),text:pctf(c.cumpl_ytd,0)+" del ppto"}):null,
     el("span",{"class":"mut",text:"· "+(c.var_ytd>=0?"+":"")+money(c.var_ytd,"USD",true)})],
    spark(c.mensual,"var(--series-1)",D.mes_cierre),semColor(c.cumpl_ytd),tcb));
  box.appendChild(kpi("MTD "+MESES[c.mtd.mes-1]+" (USD)",money(c.mtd.real,"USD",true),
    [el("span",{"class":"mut",text:"suma de los 3 países"})],null,null,tcb));
  box.appendChild(kpi("Cumplimiento ppto YTD",nn(c.cumpl_ytd)?pctf(c.cumpl_ytd):null,
    [el("span",{"class":"mut",text:"Ppto YTD "+money(c.ppto_ytd,"USD",true)}),
     el("span",{"class":"mut",text:"· avance año "+pctf(c.avance_anual,0)})],null,semColor(c.cumpl_ytd),tcb));
  var conMg=c.composicion.filter(function(x){return nn(x.margen_pct);});
  if(conMg.length){
    var w=0,s=0;conMg.forEach(function(x){w+=x.usd||0;s+=(x.usd||0)*x.margen_pct;});
    box.appendChild(kpi("Margen bruto % (parcial)",pctf(w?s/w:null),
      [el("span",{"class":"mut",text:"sólo "+conMg.map(function(x){return x.pais;}).join(" + ")}),
       el("span",{"class":"badge nd",text:(3-conMg.length)+" país(es) sin COGS"})],null,"var(--warning)"));
  } else {
    box.appendChild(kpi("Margen bruto %",null,[el("span",{"class":"warn",text:"no calculable"})],null,"var(--serious)",["sin COGS","nd"]));
  }
  var cart=0,hay=false;
  ORDEN.forEach(function(k){var p=D.paises[k];if(p&&p.cartera&&p.cartera.disponible&&nn(p.usd.cartera)){cart+=p.usd.cartera;hay=true;}});
  box.appendChild(kpi("Cartera grupo (USD)",hay?money(cart,"USD",true):null,
    [el("span",{"class":"mut",text:hay?"suma de países con dato":"sin dato"})],null,null,tcb));
  box.appendChild(kpi("Concentración (HHI grupo)",nn(c.hhi_grupo)?num(c.hhi_grupo):null,
    [el("span",{"class":c.hhi_grupo>2500?"down":"mut",text:c.hhi_grupo>2500?"concentración crítica":"dentro de rango"}),
     el("span",{"class":"mut",text:"· umbral 2.500"})],null,
    c.hhi_grupo>2500?"var(--critical)":"var(--good)"));
  return box;
}

/* ===================================================================
   Bloques de "sin dato" (cero real ≠ dato faltante)
   =================================================================== */
function sinDato(titulo,motivo,necesita){
  return el("div",{"class":"nodata"},[
    el("h3",{},["⚠ ",titulo]),
    el("p",{text:motivo||"Sin dato disponible."}),
    necesita?el("div",{"class":"need",text:"Qué hace falta: "+necesita}):null]);
}
function card(titulo,hint,contenido){
  var c=el("div",{"class":"card"},[el("h2",{text:titulo})]);
  if(hint)c.appendChild(el("div",{"class":"hint",text:hint}));
  (Array.isArray(contenido)?contenido:[contenido]).forEach(function(x){if(x)c.appendChild(x);});
  return c;
}
function lectura(txt){return el("div",{"class":"readout",html:txt});}

var ORDEN=["Ecuador","Colombia","Costa Rica"];

/* ===================================================================
   C. REAL VS PRESUPUESTO
   =================================================================== */
function secRealPpto(p){
  var cur=curOf(p);
  var kids=[];
  kids.push(el("div",{"class":"legend"},[
    el("span",{},[el("i",{style:"background:var(--series-1)"}),"Real facturado (neto sin IVA)"]),
    p.ppto_mensual?el("span",{},[el("span",{"class":"ln",style:"border-color:var(--series-2)"}),"Presupuesto"]):null,
    el("span",{},[el("i",{style:"background:transparent;border:1px dashed var(--line)"}),"Mes futuro (sin dato aún)"]),
    el("span",{},[el("i",{style:"background:var(--text-muted);height:3px;border-radius:1px"}),"Cero real"])
  ].filter(Boolean)));
  kids.push(chartRealPpto(p));
  var ac=chartAcum(p); if(ac)kids.push(ac);
  /* lectura */
  var mejor=-1,peor=-1;
  if(p.ppto_mensual){
    var best=-9,worst=9;
    for(var m=0;m<p.mes_cierre;m++){var pp=p.ppto_mensual[m];if(!pp)continue;
      var r=p.mensual[m]/pp; if(r>best){best=r;mejor=m;} if(r<worst){worst=r;peor=m;}}
  }
  var txt="<b>"+SCOPE+"</b> lleva <b>"+money(conv(p.ytd_real,p),cur)+"</b> a "+MESES[p.mes_cierre-1]+
    (nn(p.cumpl_ytd)?", un <b>"+pctf(p.cumpl_ytd)+"</b> del presupuesto YTD ("+
      (p.var_ytd>=0?"+":"")+money(conv(p.var_ytd,p),cur)+")":", sin presupuesto de referencia cargado")+
    ". Al ritmo actual el año cierra en <b>"+money(conv(p.run_rate_anual,p),cur)+"</b>"+
    (nn(p.run_rate_vs_ppto)?" = <b>"+pctf(p.run_rate_vs_ppto)+"</b> del presupuesto anual":"")+".";
  if(mejor>=0)txt+=" Mejor mes contra presupuesto: <b>"+MESES[mejor]+"</b>; el peor, <b>"+MESES[peor]+"</b>.";
  if(p.hist_amount)txt+=" Ojo: <b>"+money(conv(p.hist_amount,p),cur)+"</b> ("+pctf(p.hist_amount/p.ytd_real,0)+
    " del YTD) viene del histórico pre-migración, no de Odoo, y no trae detalle por cliente ni por producto.";
  kids.push(lectura(txt));
  /* tabla mensual */
  var rows=[];
  for(var i=0;i<12;i++){
    var real=p.mensual[i], pp=p.ppto_mensual?p.ppto_mensual[i]:null;
    rows.push({mes:MESES[i],idx:i,real:conv(real,p),ppto:nn(pp)?conv(pp,p):null,
      cumpl:((i+1)>p.mes_actual)?null:((nn(pp)&&pp)?real/pp:null), var_:nn(pp)?conv(real-pp,p):null,
      fuente:(i+1)>p.mes_actual?"futuro":(p.mensual_hist[i]?"histórico":(p.mensual_odoo[i]?"Odoo":"—"))});
  }
  var t=tabla("t-mes-"+SCOPE,
    [{t:"Mes",k:"mes"},{t:"Real",k:"real"},{t:"Presupuesto",k:"ppto"},{t:"Cumpl.",k:"cumpl"},
     {t:"Variación",k:"var_",cls:function(r){return nn(r.var_)?(r.var_<0?"neg":"pos"):"";}},{t:"Fuente",k:"fuente"}],
    rows,
    [function(r){return r.mes;},
     function(r){return (r.idx+1)>p.mes_actual?"—":money(r.real,cur);},
     function(r){return money(r.ppto,cur);},
     function(r){return ((r.idx+1)>p.mes_actual||!nn(r.cumpl))?"—":el("span",{"class":sem(r.cumpl),text:pctf(r.cumpl,0)});},
     function(r){return (r.idx+1)>p.mes_actual?"—":money(r.var_,cur);},
     function(r){return r.fuente;}]);
  kids.push(t); kids.push(csvBtn(t,"real_vs_presupuesto_"+SCOPE));
  if(p.ppto_mensual_meta)kids.push(el("div",{"class":"foot",
    text:"Curva de presupuesto: "+p.ppto_mensual_meta.fuente+" — fila localizada validando su total anual contra estado_grupo.json."}));
  return card("Real vs presupuesto — "+D.anio,
    "Barras = facturación neta sin IVA. Línea punteada = presupuesto. Los meses futuros van en gris punteado, nunca en cero.",kids);
}

/* ===================================================================
   D. MARGEN Y MIX
   =================================================================== */
function secMargen(p){
  var cur=curOf(p), mg=p.margen||{};
  if(!mg.disponible){
    return card("Margen bruto y mix de producto","",
      [sinDato("Margen no calculable en "+SCOPE, mg.motivo||"Sin costo de ventas en Odoo.",
        "Registrar el COGS en Odoo (valoración de inventario en modo anglosajón o asiento de costo por venta) "+
        "y tipificar la cuenta como 'Costo directo'. Mientras tanto, este bloque queda en blanco a propósito: "+
        "un margen de 100% sería una cifra falsa que se ve perfectamente creíble."),
       (p.mix&&p.mix.disponible)?secMix(p,true):null].filter(Boolean));
  }
  var kids=[el("div",{"class":"legend"},[
    el("span",{},[el("i",{style:"background:var(--series-1)"}),"Venta contable del mes (eje superior)"]),
    mg.mensual_confiable===false?null:el("span",{},[el("i",{style:"background:var(--series-3)"}),"Margen bruto % (eje inferior)"])
    ].filter(Boolean))];
  if(mg.mensual_confiable===false)kids.push(el("div",{"class":"nodata",style:"margin:0 0 10px"},[
    el("h3",{},["⚠ El margen MENSUAL no es interpretable en "+SCOPE]),
    el("p",{text:mg.motivo_mensual||""}),
    el("div",{"class":"need",text:"Qué hace falta: que Odoo registre el costo de ventas contra cada factura (valoración de inventario en tiempo real), no en asientos puntuales de ajuste."})]));
  kids.push(chartMargen(p));
  var serie=(mg.mensual_confiable===false)?[]:mg.mensual.filter(function(x){return nn(x.margen_pct);});
  var txt="Margen bruto YTD <b>"+pctf(mg.ytd.margen_pct)+"</b> ("+money(conv(mg.ytd.margen,p),cur)+
    " sobre "+money(conv(mg.ytd.venta,p),cur)+" de venta contable).";
  if(nn(mg.cobertura_meses))txt+=" Ojo: el mayor sólo tiene resultado en <b>"+mg.cobertura_meses+
    " mes(es)</b> por la migración a Odoo, así que esto compara la venta y el costo contabilizados, no el año calendario.";
  if(serie.length>=2){
    var a=serie[0],z=serie[serie.length-1];
    var d=z.margen_pct-a.margen_pct;
    txt+=" Entre "+MESES[a.mes-1]+" y "+MESES[z.mes-1]+" el margen "+(d>=0?"subió":"cayó")+" <b>"+ppf(d)+"</b>";
    var vd=(z.venta-a.venta);
    txt+= (d<0&&vd>0) ? ", <b>mientras la venta crecía</b>: estás comprando volumen con margen — revisar precio y descuentos antes de empujar más."
        : (d<0? " junto con la venta." : ".");
  }
  if(mg.cogs_rescatado_por_nombre)txt+=" El COGS se identificó por <b>nombre de cuenta</b>, no por tipo: la cifra es utilizable pero el plan de cuentas debería corregirse en Odoo.";
  kids.push(lectura(txt));
  var rows=mg.mensual.filter(function(x){return nn(x.venta);}).map(function(x){
    return {mes:MESES[x.mes-1],venta:conv(x.venta,p),cogs:conv(x.cogs,p),margen:conv(x.margen,p),pct:x.margen_pct};});
  var t=tabla("t-mg-"+SCOPE,
    [{t:"Mes",k:"mes"},{t:"Venta contable",k:"venta"},{t:"COGS",k:"cogs"},{t:"Margen $",k:"margen"},
     {t:"Margen %",k:"pct",cls:function(r){return r.pct<0?"neg":"";}}],rows,
    [function(r){return r.mes;},function(r){return money(r.venta,cur);},function(r){return money(r.cogs,cur);},
     function(r){return money(r.margen,cur);},function(r){return pctf(r.pct);}]);
  kids.push(t);kids.push(csvBtn(t,"margen_mensual_"+SCOPE));
  var c=card("Margen bruto — "+D.anio,
    "Fuente: mayor contable de Odoo (cuentas de ingreso menos costo directo). No es la factura: es lo que dice la contabilidad.",kids);
  var mixCard=secMix(p,false);
  return el("div",{},[c,mixCard]);
}

function secMix(p,soloVenta){
  var cur=curOf(p), mix=p.mix||{};
  if(!mix.disponible){
    return card("Mix de producto","",sinDato("Mix de producto no disponible en "+SCOPE,
      mix.motivo||"El mayor no devuelve ventas con producto asignado.",
      "Que los asientos de venta lleven producto (facturar desde líneas de producto, no como concepto libre)."));
  }
  var kids=[];
  kids.push(el("div",{"class":"legend"},[
    el("span",{},[el("i",{style:"background:var(--series-1)"}),mix.cogs_por_producto?"Margen aportado":"Venta"]),
    mix.cogs_por_producto?el("span",{},[el("i",{style:"background:var(--warning)"}),"Alta venta, margen bajo (<12%)"]):null,
    (mix.productos||[]).some(function(x){return (mix.cogs_por_producto?(x.margen||0):(x.venta||0))<0;})
      ?el("span",{},[el("i",{style:"background:var(--critical)"}),"Aporte negativo"]):null].filter(Boolean)));
  kids.push(chartMix(p));
  if(!mix.cogs_por_producto)kids.push(el("div",{"class":"nodata",style:"margin-top:10px"},[
    el("h3",{},["⚠ Ordenado por venta, no por margen"]),
    el("p",{text:mix.motivo_cogs||"No hay COGS a nivel de producto en Odoo, así que no se puede rankear por margen aportado."}),
    el("div",{"class":"need",text:"Qué hace falta: que el asiento de costo lleve el producto (valoración automática de inventario)."})]));
  var top=mix.productos||[];
  var txt="";
  if(top.length){
    var c1=top[0];
    txt="El producto que más factura es <b>"+c1.nombre+"</b> con "+money(conv(c1.venta,p),cur)+" ("+pctf(c1.pct_total,0)+" de la venta con producto).";
    if(mix.cogs_por_producto){
      var malos=top.filter(function(x){return nn(x.margen_pct)&&x.margen_pct<0.12&&(x.pct_total||0)>0.03;});
      if(malos.length)txt+=" <b>"+malos.length+" línea(s) de alta venta destruyen margen</b>: "+
        malos.slice(0,3).map(function(x){return x.nombre+" ("+pctf(x.margen_pct,0)+")";}).join(", ")+
        ". Es venta que consume caja e inventario sin dejar utilidad.";
      else txt+=" Ninguna línea grande está por debajo de 12% de margen.";
    }
    txt+=" El top "+top.length+" cubre "+pctf(top.reduce(function(s,x){return s+(x.pct_total||0);},0),0)+" de la venta con producto identificado.";
  }
  if(txt)kids.push(lectura(txt));
  var rows=top.map(function(x){return {nombre:x.nombre,venta:conv(x.venta,p),cogs:nn(x.cogs)?conv(x.cogs,p):null,
    margen:nn(x.margen)?conv(x.margen,p):null,pct:x.margen_pct,share:x.pct_total,delta:nn(x.delta_mes)?conv(x.delta_mes,p):null};});
  var t=tabla("t-mix-"+SCOPE,
    [{t:"Producto",k:"nombre"},{t:"Venta",k:"venta"},{t:"COGS",k:"cogs"},{t:"Margen $",k:"margen"},
     {t:"Margen %",k:"pct",cls:function(r){return nn(r.pct)&&r.pct<0.12?"neg":"";}},
     {t:"% del total",k:"share"},
     {t:mix.delta_meses?("Δ "+MESES[mix.delta_meses[1]-1]+" vs "+MESES[mix.delta_meses[0]-1]):"Δ vs mes ant.",
      k:"delta",cls:function(r){return nn(r.delta)?(r.delta<0?"neg":"pos"):"";}}],
    rows,
    [function(r){return r.nombre;},function(r){return money(r.venta,cur);},function(r){return money(r.cogs,cur);},
     function(r){return money(r.margen,cur);},function(r){return pctf(r.pct);},
     function(r){return pctf(r.share,1);},function(r){return nn(r.delta)?money(r.delta,cur,true):"—";}]);
  kids.push(t);kids.push(csvBtn(t,"mix_producto_"+SCOPE));
  return card("Mix de producto — top "+top.length+" de "+num(mix.n_productos),
    mix.cogs_por_producto?"Ordenado por margen absoluto aportado, no por facturación.":"Ordenado por venta: sin COGS por producto no hay margen que ordenar.",kids);
}

/* ===================================================================
   E. CARTERA / AGING / DSO
   =================================================================== */
function secCartera(p){
  var cur=curOf(p), car=p.cartera||{}, ds=p.dso||{};
  if(!car.disponible){
    return card("Cartera y cobranza","",
      sinDato("Cartera no disponible en "+SCOPE,car.motivo||"Odoo no devolvió cuentas por cobrar abiertas.",
        "Verificar que la contabilidad del país esté cargada en Odoo y que las facturas se registren contra una cuenta por cobrar."));
  }
  var kids=[];
  /* barras de buckets totales */
  var tot=car.total||0;
  var bars=el("div",{style:"display:flex;gap:2px;height:26px;border-radius:6px;overflow:hidden;margin:2px 0 8px"});
  BK.forEach(function(b,i){
    var v=car.buckets[b]||0; if(!v)return;
    var d=el("div",{style:"flex:"+Math.abs(v)+" 0 0;background:"+BKC[i]});
    hover(d,b,[["Saldo",money(conv(v,p),cur)],["% de la cartera",pctf(v/tot)]]);
    bars.appendChild(d);
  });
  kids.push(bars);
  kids.push(el("div",{"class":"legend"},BK.map(function(b,i){
    return el("span",{},[el("i",{style:"background:"+BKC[i]}),b+" · "+money(conv(car.buckets[b],p),cur,true)+
      " ("+pctf((car.buckets[b]||0)/tot,0)+")"]);})));
  kids.push(el("h3",{style:"font-size:12px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.08em;margin:16px 0 4px",
    text:"Antigüedad por cliente (top "+(car.clientes||[]).length+")"}));
  kids.push(chartAging(p));
  /* tendencia */
  var sc=chartSerie(p,"cartera","Cartera",function(v){return money(v,p.moneda,true);});
  var sd=chartSerie(p,"dso","DSO",function(v){return num(v,0)+" d";});
  if(sc||sd){
    var g=el("div",{"class":"grid2",style:"margin-top:14px"});
    if(sc)g.appendChild(el("div",{},[el("div",{"class":"hint",text:"Cartera total — histórico diario"}),sc]));
    if(sd)g.appendChild(el("div",{},[el("div",{"class":"hint",text:"DSO puntual — histórico diario"}),sd]));
    kids.push(g);
  } else {
    kids.push(el("div",{"class":"foot",text:
      "Todavía no hay serie histórica de cartera/DSO: se construye sola a partir de hoy, un punto por cada corrida diaria (OdooVentas/historico/). "+
      "Odoo no guarda fotos de cartera pasada, así que no se puede reconstruir hacia atrás sin inventarla."}));
  }
  /* lectura */
  var txt="Cartera de <b>"+money(conv(car.total,p),cur)+"</b> repartida en "+num(car.n_documentos)+" documentos y "+
    num(car.n_clientes)+" clientes. Vencido total <b>"+pctf(car.pct_vencido)+"</b>; a más de 30 días, <b>"+pctf(car.pct_vencido_mas_30)+"</b>.";
  if(nn(ds.dso_puntual))txt+=" DSO puntual <b>"+num(ds.dso_puntual,0)+" días</b> ("+(ds.ventana||"")+").";
  if(nn(ds.dias_pago_real))txt+=" En los últimos 12 meses los clientes pagaron en promedio ponderado <b>"+
    num(Math.abs(ds.dias_pago_real),0)+" días "+(ds.dias_pago_real>=0?"DESPUÉS":"antes")+"</b> del vencimiento (base conciliada "+
    money(conv(ds.base_conciliada,p),cur,true)+").";
  var peor=(car.clientes||[]).filter(function(c){return nn(c.pct_vencido);}).sort(function(a,b){return b.vencido-a.vencido;})[0];
  if(peor&&peor.vencido>0)txt+=" El saldo vencido más grande es de <b>"+peor.cliente+"</b>: "+money(conv(peor.vencido,p),cur)+
    " ("+pctf(peor.pct_vencido,0)+" de su saldo, factura más antigua "+(peor.mas_antigua||"?")+" con "+num(peor.mas_antigua_dias)+" días).";
  kids.push(lectura(txt));
  /* cruce venta-cobro */
  var cx=p.cruce_venta_cobro||[];
  if(cx.length){
    kids.push(el("div",{"class":"nodata",style:"margin-top:14px"},[
      el("h3",{},["⚠ Crecen en venta y se deterioran en cobro"]),
      el("p",{text:"Señal temprana de problema de caja: les estás vendiendo más y te están pagando peor. Revisar límite de crédito antes del próximo despacho."}),
      el("div",{"class":"tblwrap"},(function(){
        var t=el("table"),th=el("thead"),tr=el("tr");
        ["Cliente","Venta 3m","vs 3m previos","Saldo","% vencido","Días prom."].forEach(function(h){tr.appendChild(el("th",{text:h}));});
        th.appendChild(tr);t.appendChild(th);
        var tb=el("tbody");
        cx.forEach(function(r){
          tb.appendChild(el("tr",{},[el("td",{text:r.cliente}),el("td",{text:money(conv(r.venta_3m,p),cur,true)}),
            el("td",{"class":"pos",text:"+"+pctf(r.crecimiento,0)}),el("td",{text:money(conv(r.saldo,p),cur,true)}),
            el("td",{"class":"neg",text:pctf(r.pct_vencido,0)}),el("td",{text:num(r.dias_promedio,0)+" d"})]));});
        t.appendChild(tb);return t;})())]));
  }
  /* tabla cartera */
  var rows=(car.clientes||[]).map(function(c){return {cliente:c.cliente,saldo:conv(c.saldo,p),
    vencido:conv(c.vencido,p),pct:c.pct_vencido,dias:c.dias_promedio,ant:c.mas_antigua,antd:c.mas_antigua_dias};});
  var t=tabla("t-car-"+SCOPE,
    [{t:"Cliente",k:"cliente"},{t:"Saldo",k:"saldo"},{t:"Vencido",k:"vencido"},
     {t:"% vencido",k:"pct",cls:function(r){return nn(r.pct)&&r.pct>0.3?"neg":"";}},
     {t:"Días prom.",k:"dias"},{t:"Documento vencido más antiguo",k:"ant"},{t:"Días",k:"antd"}],rows,
    [function(r){return r.cliente;},function(r){return money(r.saldo,cur);},function(r){return money(r.vencido,cur);},
     function(r){return pctf(r.pct,0);},function(r){return nn(r.dias)?num(r.dias,0)+" d":"—";},
     function(r){return r.ant||"—";},function(r){return r.antd?num(r.antd)+" d":"—";}]);
  kids.push(t);kids.push(csvBtn(t,"cartera_"+SCOPE));
  kids.push(el("div",{"class":"foot",text:
    "Corte "+fecha(car.corte)+". "+car.fuente+" Se excluyeron "+num(car.residuos_excluidos)+" residuos de conciliación por debajo del umbral de ruido. "+
    (ds.metodo||"")}));
  return card("Cartera, antigüedad y DSO","Buckets sobre fecha de vencimiento (invoice_date_due). El DSO es puntual, no promedio: ver nota al pie.",kids);
}

/* ===================================================================
   F. CLIENTES Y CONCENTRACIÓN
   =================================================================== */
function secClientes(p){
  var cur=curOf(p), cl=p.clientes||{};
  if(!cl.disponible)return card("Clientes y concentración","",
    sinDato("Sin detalle de clientes en "+SCOPE,cl.motivo||"No hay facturas en Odoo para el período.",
      "Que la facturación del país esté en Odoo. El histórico pre-migración no trae detalle por cliente."));
  var kids=[];
  if(nn(cl.cobertura_pct)&&cl.cobertura_pct<0.95)kids.push(el("div",{"class":"nodata",style:"margin:0 0 12px"},[
    el("h3",{},["⚠ Este bloque describe el "+pctf(cl.cobertura_pct,0)+" del año, no el año"]),
    el("p",{text:"Sólo "+money(conv(cl.base_odoo,p),cur)+" de los "+money(conv(cl.ytd_pais,p),cur)+
      " facturados YTD están en Odoo con detalle de cliente. El resto viene del histórico pre-migración, que no trae cliente. "+
      "El HHI y el ranking de abajo son de esa porción."}),
    el("div",{"class":"need",text:"Qué hace falta: cargar el detalle por cliente de los meses pre-migración, o esperar a que el año corriente se acumule en Odoo."})]));
  if(cl.pct_intercompania)kids.push(el("div",{"class":"readout",style:"border-left-color:var(--warning)",
    html:"<b>"+pctf(cl.pct_intercompania,0)+"</b> de esta venta es <b>intercompañía</b> ("+money(conv(cl.venta_intercompania,p),cur)+
      "): no es mercado, es el grupo vendiéndose a sí mismo. Descontándola, el HHI de terceros es <b>"+num(cl.hhi_terceros)+
      "</b>. Ojo con leer esa línea como crecimiento comercial — y con la cuenta por cobrar que genera."}));
  var top=cl.clientes||[];
  var maxv=Math.max.apply(null,top.map(function(c){return Math.abs(c.venta);}).concat([1]));
  var lista=el("div",{style:"margin:4px 0 6px"});
  top.forEach(function(c){
    var row=el("div",{style:"display:flex;align-items:center;gap:10px;padding:5px 0;border-bottom:1px solid var(--line-soft)"});
    var nm=el("div",{style:"flex:0 0 "+(innerWidth<640?"110px":"210px"),title:c.cliente});
    nm.appendChild(document.createTextNode(c.cliente.length>30?c.cliente.slice(0,29)+"…":c.cliente));
    if(c.intercompania)nm.appendChild(el("span",{"class":"badge",style:"margin-left:6px;border-color:#4a412a;color:var(--warning)",text:"intercía"}));
    row.appendChild(nm);
    var barw=Math.max(2,Math.abs(c.venta)/maxv*100);
    var bar=el("div",{style:"flex:1;height:14px;background:var(--surface-2);border-radius:3px;overflow:hidden"});
    var fill=el("div",{style:"width:"+barw+"%;height:100%;background:"+(c.pct>0.5?"var(--critical)":(c.pct>0.25?"var(--warning)":"var(--series-1)"))+";border-radius:3px"});
    hover(fill,c.cliente,[["Venta YTD",money(conv(c.venta,p),cur)],["% del país",pctf(c.pct)],
      nn(c.venta_aa)?["Año anterior",money(conv(c.venta_aa,p),cur)]:null,
      nn(c.delta_aa)?["Δ vs año anterior",pctf(c.delta_aa,0)]:null].filter(Boolean));
    bar.appendChild(fill);row.appendChild(bar);
    row.appendChild(el("div",{style:"flex:0 0 92px;text-align:right;font-variant-numeric:tabular-nums;color:var(--text-secondary)",
      text:money(conv(c.venta,p),cur,true)}));
    row.appendChild(el("div",{style:"flex:0 0 52px;text-align:right;font-variant-numeric:tabular-nums;font-weight:600;color:"+
      (c.pct>0.5?"var(--critical)":"var(--text-primary)"),text:pctf(c.pct,0)}));
    lista.appendChild(row);
  });
  kids.push(lista);
  var hhiBox=el("div",{style:"display:flex;gap:16px;align-items:center;flex-wrap:wrap;margin:12px 0 2px;padding:12px;background:var(--surface-2);border-radius:10px;border-left:3px solid "+(cl.critico?"var(--critical)":"var(--good)")});
  hhiBox.appendChild(el("div",{},[el("div",{"class":"lab",style:"font-size:10.5px;text-transform:uppercase;letter-spacing:.09em;color:var(--text-muted)",text:"Índice HHI"}),
    el("div",{style:"font-family:var(--cond);font-size:28px;font-weight:700;color:"+(cl.critico?"var(--critical)":"var(--good)"),text:num(cl.hhi)})]));
  if(cl.pct_intercompania)hhiBox.appendChild(el("div",{},[el("div",{style:"font-size:10.5px;text-transform:uppercase;letter-spacing:.09em;color:var(--text-muted)",text:"HHI sólo terceros"}),
    el("div",{style:"font-family:var(--cond);font-size:28px;font-weight:700;color:"+(cl.hhi_terceros>2500?"var(--critical)":"var(--good)"),text:num(cl.hhi_terceros)})]));
  hhiBox.appendChild(el("div",{style:"flex:1;min-width:220px;color:var(--text-secondary);font-size:12.5px",text:cl.lectura||""}));
  kids.push(hhiBox);
  var txt="Los 5 primeros clientes concentran <b>"+pctf(cl.top5_pct)+"</b> de la venta registrada en Odoo. ";
  var crecen=top.filter(function(c){return nn(c.delta_aa)&&c.delta_aa<-0.15;});
  if(crecen.length)txt+="<b>"+crecen.length+" cliente(s) del top cayeron más de 15% contra el año anterior</b>: "+
    crecen.slice(0,3).map(function(c){return c.cliente+" ("+pctf(c.delta_aa,0)+")";}).join(", ")+". ";
  if(nn(cl.cobertura_pct)&&cl.cobertura_pct<0.95)txt+="Este desglose cubre sólo el <b>"+pctf(cl.cobertura_pct,0)+
    "</b> del YTD del país; el resto viene del histórico pre-migración, que no trae cliente.";
  kids.push(lectura(txt));
  var rows=top.map(function(c){return {cliente:c.cliente+(c.intercompania?"  [intercompañía]":""),venta:conv(c.venta,p),pct:c.pct,
    aa:nn(c.venta_aa)?conv(c.venta_aa,p):null,delta:c.delta_aa};});
  var t=tabla("t-cli-"+SCOPE,
    [{t:"Cliente",k:"cliente"},{t:"Venta YTD",k:"venta"},{t:"% del país",k:"pct"},
     {t:"Año anterior",k:"aa"},{t:"Δ vs AA",k:"delta",cls:function(r){return nn(r.delta)?(r.delta<0?"neg":"pos"):"";}}],rows,
    [function(r){return r.cliente;},function(r){return money(r.venta,cur);},function(r){return pctf(r.pct,1);},
     function(r){return money(r.aa,cur);},function(r){return nn(r.delta)?pctf(r.delta,0):"—";}]);
  kids.push(t);kids.push(csvBtn(t,"clientes_"+SCOPE));
  return card("Clientes y concentración",
    "El riesgo estructural del grupo. HHI = Σ (participación %)²; por encima de 2.500 la dependencia es crítica.",kids);
}

/* ===================================================================
   4.2 EXTRAS DEL CONSOLIDADO
   =================================================================== */
function secGrupo(){
  var c=D.consolidado, kids=[];
  var comp=c.composicion||[];
  var bar=el("div",{style:"display:flex;gap:2px;height:30px;border-radius:8px;overflow:hidden;margin:6px 0 10px"});
  var COL=["var(--series-1)","var(--series-2)","var(--series-3)"];
  comp.forEach(function(x,i){
    if(!(x.usd>0))return;
    var d=el("div",{style:"flex:"+x.usd+" 0 0;background:"+COL[i%3]+";display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:600;color:#fff"});
    if(x.pct>0.12)d.textContent=x.pais+" "+pctf(x.pct,0);
    hover(d,x.pais,[["Venta YTD (USD ref.)",money(x.usd,"USD")],["En moneda local",money(x.local,x.moneda)],
      ["% del grupo",pctf(x.pct)],nn(x.cumpl)?["Cumplimiento",pctf(x.cumpl)]:null].filter(Boolean));
    bar.appendChild(d);
  });
  kids.push(bar);
  kids.push(el("div",{"class":"legend"},comp.map(function(x,i){
    return el("span",{},[el("i",{style:"background:"+COL[i%3]}),x.pais+" · "+money(x.usd,"USD",true)+" ("+pctf(x.pct,0)+")"]);})));
  kids.push(el("div",{style:"margin-top:6px"},el("span",{"class":"badge tc",text:"USD referencial · COP "+num(D.tc.cop_por_usd)+" · CRC "+num(D.tc.crc_por_usd)})));
  /* ranking */
  kids.push(el("h3",{style:"font-size:12px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.08em;margin:20px 0 6px",
    text:"Ranking de cumplimiento presupuestal"}));
  (c.ranking_cumplimiento||[]).forEach(function(x,i){
    var row=el("div",{style:"display:flex;align-items:center;gap:10px;padding:6px 0;border-bottom:1px solid var(--line-soft)"});
    row.appendChild(el("div",{style:"flex:0 0 20px;color:var(--text-muted);font-weight:700",text:String(i+1)}));
    row.appendChild(el("div",{style:"flex:0 0 90px;font-weight:600",text:x.pais}));
    var track=el("div",{style:"flex:1;height:16px;background:var(--surface-2);border-radius:3px;position:relative;overflow:hidden"});
    var w=Math.min(100,Math.max(1,(x.cumpl||0)*100*0.8));
    var f=el("div",{style:"width:"+w+"%;height:100%;background:"+semColor(x.cumpl)+";border-radius:3px"});
    track.appendChild(f);
    track.appendChild(el("div",{style:"position:absolute;left:80%;top:0;bottom:0;width:1px;background:var(--text-muted);opacity:.7"}));
    hover(f,x.pais,[["Cumplimiento YTD",pctf(x.cumpl)],["Real",money(x.local,x.moneda)],["USD ref.",money(x.usd,"USD")]]);
    row.appendChild(track);
    row.appendChild(el("div",{style:"flex:0 0 58px;text-align:right;font-weight:700;font-variant-numeric:tabular-nums;color:"+semColor(x.cumpl),
      text:pctf(x.cumpl,0)}));
    kids.push(row);
  });
  kids.push(el("div",{"class":"foot",text:"La marca vertical es el 100% del presupuesto."}));
  /* lectura */
  var lider=comp[0];
  var txt="El grupo lleva <b>"+money(c.ytd_real,"USD")+"</b> (USD referencial) contra un presupuesto YTD de "+
    money(c.ppto_ytd,"USD")+" = <b>"+pctf(c.cumpl_ytd)+"</b>. ";
  if(lider)txt+="<b>"+lider.pais+"</b> pesa <b>"+pctf(lider.pct)+"</b> de la venta"+
    (lider.pct>0.6?" — el grupo es, en la práctica, ese país":"")+". ";
  var culpa=(comp.slice().sort(function(a,b){return a.desviacion_usd-b.desviacion_usd;}))[0];
  if(culpa&&culpa.desviacion_usd<0)txt+="La brecha contra presupuesto la explica sobre todo <b>"+culpa.pais+
    "</b> ("+money(culpa.desviacion_usd,"USD")+", "+pctf(culpa.pct_desviacion,0)+" de la desviación total).";
  kids.push(lectura(txt));
  /* tabla comparativa */
  var rows=comp.map(function(x){var p=D.paises[x.pais]||{};
    return {pais:x.pais,local:x.local,moneda:x.moneda,usd:x.usd,cumpl:x.cumpl,margen:x.margen_pct,
      dso:x.dso,hhi:x.hhi,cartera:(p.cartera&&p.cartera.disponible)?p.usd.cartera:null};});
  var t=tabla("t-grupo",
    [{t:"País",k:"pais"},{t:"Venta local",k:"local"},{t:"Venta USD ref.",k:"usd"},
     {t:"% ppto",k:"cumpl"},{t:"Margen %",k:"margen"},{t:"Cartera USD ref.",k:"cartera"},
     {t:"DSO",k:"dso"},{t:"HHI",k:"hhi",cls:function(r){return r.hhi>2500?"neg":"";}}],rows,
    [function(r){return r.pais;},function(r){return money(r.local,r.moneda);},function(r){return money(r.usd,"USD");},
     function(r){return nn(r.cumpl)?el("span",{"class":sem(r.cumpl),text:pctf(r.cumpl,0)}):"—";},
     function(r){return nn(r.margen)?pctf(r.margen):el("span",{"class":"badge nd",text:"no calculable"});},
     function(r){return money(r.cartera,"USD");},
     function(r){return nn(r.dso)?num(r.dso,0)+" d":"—";},function(r){return num(r.hhi);}]);
  kids.push(t);kids.push(csvBtn(t,"comparativo_paises"));
  return card("Composición del grupo — "+D.anio,
    "Todo el consolidado en USD es REFERENCIAL: Odoo no mantiene tipos de cambio y se usan overrides manuales.",kids);
}

function secConcentracionGrupo(){
  var c=D.consolidado;
  if(!c.top_clientes_grupo)return null;
  var kids=[];
  var top=c.top_clientes_grupo, maxv=Math.max.apply(null,top.map(function(x){return x.usd;}).concat([1]));
  top.forEach(function(x){
    var row=el("div",{style:"display:flex;align-items:center;gap:10px;padding:5px 0;border-bottom:1px solid var(--line-soft)"});
    row.appendChild(el("div",{style:"flex:0 0 "+(innerWidth<640?"110px":"230px"),text:x.cliente.length>36?x.cliente.slice(0,35)+"…":x.cliente,title:x.cliente}));
    var bar=el("div",{style:"flex:1;height:14px;background:var(--surface-2);border-radius:3px;overflow:hidden"});
    var f=el("div",{style:"width:"+(x.usd/maxv*100)+"%;height:100%;background:"+(x.pct>0.3?"var(--critical)":"var(--series-1)")+";border-radius:3px"});
    hover(f,x.cliente,[["Venta YTD (USD ref.)",money(x.usd,"USD")],["% del grupo",pctf(x.pct)]]);
    bar.appendChild(f);row.appendChild(bar);
    row.appendChild(el("div",{style:"flex:0 0 92px;text-align:right;color:var(--text-secondary);font-variant-numeric:tabular-nums",text:money(x.usd,"USD",true)}));
    row.appendChild(el("div",{style:"flex:0 0 52px;text-align:right;font-weight:600;font-variant-numeric:tabular-nums",text:pctf(x.pct,0)}));
    kids.push(row);
  });
  var t5=top.slice(0,5).reduce(function(s,x){return s+x.pct;},0);
  kids.push(lectura("HHI del grupo <b>"+num(c.hhi_grupo)+"</b>. Los 5 clientes más grandes concentran <b>"+pctf(t5)+
    "</b> de la venta consolidada. "+(c.hhi_grupo>2500?
    "Esto no es un dato de marketing: es el riesgo número uno del balance. La pérdida de un solo cliente mueve la caja del grupo entero.":
    "La dependencia está dentro de un rango manejable.")+
    " <span style='color:var(--text-muted)'>"+(c.nota_hhi||"")+"</span>"));
  return card("Concentración de clientes — grupo","Módulo no solicitado, incluido porque un dashboard de ventas que lo oculta desinforma.",kids);
}

/* ===================================================================
   G. PANEL DE INTEGRIDAD DE DATOS (obligatorio)
   =================================================================== */
function secIntegridad(){
  var av=D.avisos||[];
  var crit=av.filter(function(a){return a.nivel==="critico";}).length;
  var body=el("div",{"class":"body"});
  body.appendChild(el("div",{"class":"hint",text:
    "Este panel no se puede omitir por estética. Lista todo lo que el dashboard NO sabe y de dónde sale cada bloque."}));
  /* avisos */
  body.appendChild(el("h3",{style:"font-size:12px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.08em;margin:14px 0 2px",
    text:"Avisos ("+av.length+(crit?" · "+crit+" crítico"+(crit>1?"s":""):"")+")"}));
  if(!av.length)body.appendChild(el("div",{"class":"aviso"},[el("div",{"class":"tx",text:"Sin avisos: todas las fuentes respondieron."})]));
  av.forEach(function(a){
    body.appendChild(el("div",{"class":"aviso"},[
      el("div",{"class":"lv "+a.nivel,text:a.nivel}),
      el("div",{"class":"tx",html:"<b>"+(a.pais||"Grupo")+" · "+a.bloque+"</b> — "+a.texto})]));
  });
  /* conciliación */
  var conc=D.conciliacion||{};
  body.appendChild(el("h3",{style:"font-size:12px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.08em;margin:20px 0 2px",
    text:"Conciliación contra las fuentes ya validadas"}));
  var tw=el("div",{"class":"tblwrap"});
  var t=el("table"),th=el("thead"),tr=el("tr");
  ["","País","Concepto","Dashboard","Referencia","Diferencia"].forEach(function(h){tr.appendChild(el("th",{text:h}));});
  th.appendChild(tr);t.appendChild(th);var tb=el("tbody");
  (conc.filas||[]).forEach(function(f){
    tb.appendChild(el("tr",{},[
      el("td",{style:"color:"+(f.cuadra?"var(--good)":"var(--critical)")+";font-weight:700",text:f.cuadra?"✓":"✗"}),
      el("td",{text:f.pais}),el("td",{text:f.concepto}),
      el("td",{text:num(f.dashboard,2)}),el("td",{text:f.referencia==null?"—":num(f.referencia,2)}),
      el("td",{"class":f.diferencia?"neg":"",text:f.diferencia==null?"—":num(f.diferencia,2)})]));
  });
  t.appendChild(tb);tw.appendChild(t);body.appendChild(tw);
  body.appendChild(el("div",{"class":"foot",text:conc.todo_cuadra?
    "Todas las líneas cuadran al centavo contra estado_grupo.json y los históricos de odoo_config.json.":
    "Hay diferencias: no están maquilladas, se muestran arriba tal como salen."}));
  /* fuentes */
  body.appendChild(el("h3",{style:"font-size:12px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.08em;margin:20px 0 2px",
    text:"Fuente y fecha de cada bloque"}));
  var sg=el("div",{"class":"srcgrid"});
  var items=[["Ventas",D.fuentes.ventas],["Presupuesto",D.fuentes.presupuesto],
    ["Margen",D.fuentes.margen],["Cartera",D.fuentes.cartera],
    ["Extracción Odoo",D.generado+"  ·  "+D.odoo.url+"  ·  db "+D.odoo.db+"  ·  "+D.odoo.llamadas+" llamadas XML-RPC"],
    ["estado_grupo.json",D.fuentes.estado_grupo_generado||"(no disponible)"],
    ["Tipo de cambio",D.tc.fuente+" — COP "+num(D.tc.cop_por_usd)+"/USD, CRC "+num(D.tc.crc_por_usd)+"/USD. REFERENCIAL: Odoo no mantiene tasas."]];
  if(!CONS){
    var p=D.paises[SCOPE]||{};
    items.push(["Fuente de ventas de "+SCOPE,p.fuente_ventas+(p.corte_migracion?" · corte de migración "+fecha(p.corte_migracion):"")]);
    items.push(["Compañías incluidas",(p.empresas||[]).join(", ")||"—"]);
  }
  items.push(["Excluido a propósito","Compañías: "+((D.excluidas||[]).join(", ")||"ninguna")+
    ". VICOMER LOGISTICA no existe en Odoo. Los meses futuros no se proyectan. "+
    "Los saldos de cartera no tienen historia previa a la primera corrida de este pipeline."]);
  items.forEach(function(x){sg.appendChild(el("div",{"class":"src"},[el("div",{"class":"k",text:x[0]}),el("div",{"class":"v",text:String(x[1]||"—")})]));});
  body.appendChild(sg);
  var d=el("details",{"class":"integrity",id:"integridad"},[
    el("summary",{},["Panel de integridad de datos"+(av.length?" — "+av.length+" aviso"+(av.length>1?"s":""):"")]),body]);
  return d;
}

/* ===================================================================
   Controles y navegación
   =================================================================== */
function controles(){
  var box=el("div",{"class":"controls"});
  box.appendChild(el("span",{"class":"ctl-label",text:"Período"}));
  var seg=el("div",{"class":"seg"});
  [["ytd","YTD"],["mes","Mes"],["trim","Trimestre"],["r12","Rolling 12"]].forEach(function(o){
    var b=el("button",{text:o[1],"aria-pressed":ST.periodo===o[0]?"true":"false",onclick:function(){
      ST.periodo=o[0];render();}});
    seg.appendChild(b);});
  box.appendChild(seg);
  if(!CONS){
    var p=D.paises[SCOPE];
    if(p&&p.moneda!=="USD"){
      box.appendChild(el("span",{"class":"ctl-label",style:"margin-left:8px",text:"Moneda"}));
      var s2=el("div",{"class":"seg"});
      [["local",p.moneda],["usd","USD ref."]].forEach(function(o){
        s2.appendChild(el("button",{text:o[1],"aria-pressed":ST.moneda===o[0]?"true":"false",
          onclick:function(){ST.moneda=o[0];render();}}));});
      box.appendChild(s2);
    }
  }
  box.appendChild(el("button",{"class":"btn",style:"margin-left:auto",text:"Imprimir / PDF",onclick:function(){window.print();}}));
  return box;
}

/* resumen del período elegido (el filtro cambia el número, no sólo la vista) */
function resumenPeriodo(p){
  var cur=curOf(p), mc=p.mes_cierre, ma=p.mes_actual, r=p.mensual, pp=p.ppto_mensual;
  var ini,fin,lab;
  if(ST.periodo==="mes"){ini=ma;fin=ma;lab=MESES[ma-1]+" "+D.anio+" (mes en curso)";}
  else if(ST.periodo==="trim"){fin=ma;ini=Math.max(1,ma-2);lab="Últimos 3 meses ("+MESES[ini-1]+"–"+MESES[fin-1]+")";}
  else if(ST.periodo==="r12"){ini=1;fin=12;lab="Rolling 12 (año calendario "+D.anio+" disponible)";}
  else {ini=1;fin=mc;lab="YTD a "+MESES[mc-1]+" "+D.anio;}
  var sr=0,sp=0,hay=false;
  for(var m=ini;m<=fin;m++){sr+=r[m-1]||0;if(pp&&nn(pp[m-1])){sp+=pp[m-1];hay=true;}}
  var box=el("div",{style:"display:flex;gap:22px;flex-wrap:wrap;align-items:baseline;margin:0 0 14px;padding:11px 14px;background:var(--surface-1);border:1px solid var(--line);border-radius:10px"});
  box.appendChild(el("div",{},[el("div",{style:"font-size:10.5px;text-transform:uppercase;letter-spacing:.09em;color:var(--text-muted)",text:lab}),
    el("div",{style:"font-family:var(--cond);font-size:22px;font-weight:700",text:money(conv(sr,p),cur)})]));
  if(hay)box.appendChild(el("div",{},[el("div",{style:"font-size:10.5px;text-transform:uppercase;letter-spacing:.09em;color:var(--text-muted)",text:"Presupuesto del período"}),
    el("div",{style:"font-family:var(--cond);font-size:22px;font-weight:700;color:var(--text-secondary)",text:money(conv(sp,p),cur)})]));
  if(hay&&sp)box.appendChild(el("div",{},[el("div",{style:"font-size:10.5px;text-transform:uppercase;letter-spacing:.09em;color:var(--text-muted)",text:"Cumplimiento"}),
    el("div",{style:"font-family:var(--cond);font-size:22px;font-weight:700;color:"+semColor(sr/sp),text:pctf(sr/sp)})]));
  return box;
}

/* ===================================================================
   Render principal
   =================================================================== */
var ROOT;
function render(){
  CHARTS.length=0;
  ROOT.innerHTML="";
  ROOT.appendChild(controles());
  var paneles=[];
  if(CONS){
    ROOT.appendChild(kpisConsolidado());
    paneles.push(["Grupo",[secGrupo()]]);
    paneles.push(["Por país",ORDEN.map(function(k){
      var p=D.paises[k]; if(!p)return null;
      var c=card(k+" — real vs presupuesto","Moneda autoritativa: "+p.moneda+".",[chartRealPpto(p),
        lectura("<b>"+k+"</b>: "+money(p.ytd_real,p.moneda)+" YTD"+(nn(p.cumpl_ytd)?" = <b>"+pctf(p.cumpl_ytd)+"</b> del presupuesto":"")+
          ". Margen "+((p.margen&&p.margen.disponible)?pctf(p.margen.ytd.margen_pct):"<b>no calculable</b>")+
          ". Cartera "+((p.cartera&&p.cartera.disponible)?money(p.cartera.total,p.moneda)+" ("+pctf(p.cartera.pct_vencido,0)+" vencida)":"sin dato")+".")]);
      return c;}).filter(Boolean)]);
    paneles.push(["Concentración",[secConcentracionGrupo()].filter(Boolean)]);
  } else {
    var p=D.paises[SCOPE];
    if(!p){ROOT.appendChild(sinDato("Sin datos para "+SCOPE,"El pipeline no devolvió este país.","Revisar company_map en odoo_config.json."));return;}
    ROOT.appendChild(kpisPais(p));
    ROOT.appendChild(resumenPeriodo(p));
    paneles.push(["Real vs presupuesto",[secRealPpto(p)]]);
    paneles.push(["Margen y mix",[secMargen(p)]]);
    paneles.push(["Cartera y cobranza",[secCartera(p)]]);
    paneles.push(["Clientes",[secClientes(p)]]);
  }
  var tabs=el("div",{"class":"tabs",role:"tablist"});
  var host=el("div");
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
    "Generado por <b>ventas_dashboard.py</b> + <b>ventas_dashboard_render.py</b> el "+D.generado+
    ". Archivo autocontenido: abre sin internet. Cifras netas sin IVA, sólo documentos <i>posted</i>. "+
    "Notas de crédito restando. Ningún número de este tablero se estima: lo que no está, se declara."}));
}

/* boot */
document.addEventListener("DOMContentLoaded",function(){
  document.body.insertBefore(statusBar(),document.body.firstChild.nextSibling);
  var head=el("header",{"class":"page"},[
    el("h1",{text:(CONS?"Consolidado Grupo VICOMER":"Dashboard de ventas · "+SCOPE)}),
    el("div",{"class":"sub",text:(CONS?"Ecuador · Colombia · Costa Rica — VIX excluida por decisión de gerencia":
      "Compañías: "+(((D.paises[SCOPE]||{}).empresas)||[]).join(", "))+
      "  |  Año "+D.anio+"  |  Cierre "+MESES[D.mes_cierre-1]})]);
  var wrap=el("div",{"class":"wrap"});
  wrap.appendChild(head);
  ROOT=el("div");wrap.appendChild(ROOT);
  document.body.appendChild(wrap);
  render();
});
})();
"""


def build(doc, scope, titulo):
    datos = json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
    # el JSON va dentro de un <script>: hay que neutralizar cualquier cierre de etiqueta
    datos = datos.replace("</", "<\\/")
    html = HEAD.replace("__TITULO__", titulo)
    html += "<script>window.__DATA__=" + datos + ";window.__SCOPE__=" + json.dumps(scope) + ";</script>\n"
    html += "<script>\n" + JS + "\n</script>\n</body>\n</html>\n"
    return html


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    src = Path(a.json) if a.json else (OUT_DIR / "dashboard_ventas.json")
    out = Path(a.out) if a.out else OUT_DIR
    if not src.exists():
        sys.exit("ERROR: no existe %s. Corre primero: python3 ventas_dashboard.py" % src)
    doc = json.loads(src.read_text(encoding="utf-8"))
    out.mkdir(parents=True, exist_ok=True)
    hechos = []
    for scope, fname, titulo in SALIDAS:
        if scope != "__CONSOLIDADO__" and scope not in (doc.get("paises") or {}):
            print("  [!] %s no viene en el JSON: se genera igual, el HTML lo declara como bloque sin datos." % scope)
        html = build(doc, scope, titulo)
        dest = out / fname
        tmp = dest.with_suffix(".html.tmp")
        tmp.write_text(html, encoding="utf-8")
        os.replace(str(tmp), str(dest))
        hechos.append(dest)
        print("  [OK] %-46s %7.0f KB" % (fname, dest.stat().st_size / 1024.0))
    print("\n%d dashboards en %s" % (len(hechos), out))
    av = doc.get("avisos") or []
    crit = [x for x in av if x.get("nivel") == "critico"]
    print("Avisos embebidos: %d (%d criticos). Datos generados: %s" % (len(av), len(crit), doc.get("generado")))
    return hechos


if __name__ == "__main__":
    main()
