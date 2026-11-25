#!/usr/bin/env python3
"""work/output/analysis.json -> work/output/index.html (dashboard autocontenido; Chart.js desde cdnjs)."""
import json, os
from common import jload, wpath

A = jload('output/analysis.json')
D = {k: A[k] for k in ('rows', 'cmp', 'desc', 'kpi', 'alertas', 'frenos', 'pedidos', 'por_despachar', 'transito', 'consig_otros',
                       'fecha', 'hoy', 'asof_sellin', 'n_correos', 'modelo', 'odoo_sellin')}
TPL = r'''<title>Casa Magna Sell Out</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Sans+Condensed:wght@600;700&family=IBM+Plex+Mono:wght@400;500&display=swap">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
/* Layout: tablero operativo de una columna; resumen arriba, posición por SKU al centro, contexto comercial abajo */
:root{
  --bg:#f3f5f4;--panel:#ffffff;--ink:#16201d;--mute:#5d6b66;--line:#dfe5e2;
  --acc:#0f6b5c;--acc2:#b4721b;--bad:#b3261e;--warn:#a86400;--ok:#1d7a46;--info:#3b5bab;
  --bad-bg:#fbe9e7;--warn-bg:#fdf1dc;--ok-bg:#e3f3ea;--info-bg:#e7ecf8;--neu-bg:#eceff0;
  --f-head:"IBM Plex Sans Condensed","Arial Narrow",Arial,sans-serif;--f-body:"IBM Plex Sans",system-ui,Segoe UI,Arial,sans-serif;--f-num:"IBM Plex Mono",ui-monospace,Menlo,monospace;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#0f1514;--panel:#161e1c;--ink:#e4ece9;--mute:#93a39d;--line:#26322f;
  --acc:#4fc1a9;--acc2:#e3a54f;--bad:#f2867c;--warn:#efb35a;--ok:#6fcf97;--info:#8fa8ec;
  --bad-bg:#3a1d1b;--warn-bg:#3a2b12;--ok-bg:#16301f;--info-bg:#1c2540;--neu-bg:#222b29;color-scheme:dark}}
:root[data-theme="dark"]{
  --bg:#0f1514;--panel:#161e1c;--ink:#e4ece9;--mute:#93a39d;--line:#26322f;
  --acc:#4fc1a9;--acc2:#e3a54f;--bad:#f2867c;--warn:#efb35a;--ok:#6fcf97;--info:#8fa8ec;
  --bad-bg:#3a1d1b;--warn-bg:#3a2b12;--ok-bg:#16301f;--info-bg:#1c2540;--neu-bg:#222b29;color-scheme:dark}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--ink);font:14px/1.45 var(--f-body);margin:0}
.wrap{max-width:1320px;margin:0 auto;padding-block:20px 48px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));display:grid;gap:16px}
header{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:flex-end;gap:8px 24px}
h1{font:700 26px/1.1 var(--f-head);margin:0;letter-spacing:.2px;text-wrap:balance}
h2{font:600 16px/1.2 var(--f-head);margin:0 0 10px;letter-spacing:.3px;text-transform:uppercase;color:var(--mute)}
.sub{color:var(--mute);font-size:12.5px}
.num,td.n,.k b{font-family:var(--f-num);font-variant-numeric:tabular-nums}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:14px;min-width:0}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:1px;background:var(--line);border:1px solid var(--line);border-radius:8px;overflow:hidden}
.k{background:var(--panel);padding:12px 14px}.k span{display:block;font-size:11.5px;color:var(--mute);text-transform:uppercase;letter-spacing:.4px}.k b{display:block;font-size:21px;font-weight:500;margin-top:3px}.k i{font-style:normal;font-size:12px;color:var(--mute)}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.chip{border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:999px;padding:6px 12px;font:500 13px var(--f-body);cursor:pointer;display:flex;gap:8px;align-items:center}
.chip[aria-pressed="true"]{border-color:var(--acc);box-shadow:inset 0 0 0 1px var(--acc)}
.chip:focus-visible,select:focus-visible,th:focus-visible{outline:2px solid var(--acc);outline-offset:2px}
.chip .c{font-family:var(--f-num);font-size:12px;padding:1px 7px;border-radius:9px}
.tag{display:inline-block;padding:2px 8px;border-radius:9px;font-size:11.5px;font-weight:600;white-space:nowrap}
.t-fc{background:var(--bad-bg);color:var(--bad)}.t-rv{background:var(--warn-bg);color:var(--warn)}.t-rp{background:var(--info-bg);color:var(--info)}
.t-ss{background:var(--warn-bg);color:var(--acc2)}.t-sr{background:var(--neu-bg);color:var(--mute)}.t-ok{background:var(--ok-bg);color:var(--ok)}
.scroll{overflow:auto;max-height:520px}
table{border-collapse:collapse;width:100%;font-size:12.8px}
th,td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
td.n,th.n{text-align:right}td.d{white-space:normal;min-width:180px;color:var(--mute)}
th{position:sticky;top:0;background:var(--panel);color:var(--mute);font-weight:600;font-size:11.5px;text-transform:uppercase;letter-spacing:.3px;cursor:pointer;user-select:none}
td.z{color:var(--mute)}td.hot{color:var(--bad);font-weight:600}
.alerts{margin:0;padding:0;list-style:none;display:grid;gap:6px}
.alerts li{padding:8px 10px;border-radius:6px;background:var(--warn-bg);color:var(--ink);border-left:3px solid var(--warn)}
.alerts li.fr{background:var(--bad-bg);border-left-color:var(--bad)}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:16px}
.filters{display:flex;flex-wrap:wrap;gap:10px 14px}
.filters label{display:flex;flex-direction:column;gap:3px;font-size:11.5px;color:var(--mute);text-transform:uppercase;letter-spacing:.3px}
select{background:var(--bg);color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:5px 8px;font:13px var(--f-body);max-width:220px}
canvas{max-height:280px}
.note{font-size:12px;color:var(--mute);margin-top:8px;max-width:110ch}
details summary{cursor:pointer;font:600 14px var(--f-head);text-transform:uppercase;letter-spacing:.3px;color:var(--mute)}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style>
<div class="wrap">
<header><div><h1>Casa Magna · Sell Out vs Sell In</h1><div class="sub" id="sub"></div></div><div class="sub" id="src"></div></header>
<ul class="alerts" id="alerts"></ul>
<section class="kpis" id="kpis" aria-label="Indicadores"></section>
<section class="panel">
  <h2>Posición por SKU</h2>
  <div class="chips" id="chips" role="group" aria-label="Filtrar por estado"></div>
  <div class="scroll" style="margin-top:12px"><table id="tpos"></table></div>
  <p class="note" id="metodo"></p>
</section>
<div class="grid2">
  <section class="panel"><h2>Pedidos abiertos de Casa Magna</h2><div class="scroll"><table id="tped"></table></div></section>
  <section class="panel"><h2>Por despachar a Casa Magna</h2><div class="scroll"><table id="tdes"></table></div></section>
  <section class="panel"><h2>Tránsito (compras sin recibir)</h2><div class="scroll"><table id="ttra"></table></div></section>
  <section class="panel"><h2>Sell in vs sell out (unidades)</h2><canvas id="cio" aria-label="Sell in vs sell out por SKU"></canvas></section>
</div>
<section class="panel">
  <h2>Contexto comercial (sell out NetSuite)</h2>
  <div class="filters">
    <label for="fm">Marca<select id="fm"></select></label><label for="fp">Plaza<select id="fp"></select></label>
    <label for="fr">Representante<select id="fr"></select></label><label for="fw1">Semana desde<select id="fw1"></select></label><label for="fw2">Semana hasta<select id="fw2"></select></label>
  </div>
  <div class="kpis" id="kpis2" style="margin-top:12px"></div>
  <div class="grid2" style="margin-top:16px">
    <div><h2>Venta neta semanal</h2><canvas id="ctr"></canvas></div>
    <div><h2>Pareto por SKU</h2><canvas id="cpa"></canvas></div>
    <div><h2>Venta por plaza</h2><canvas id="cpl"></canvas></div>
    <div><h2>Mix por marca</h2><canvas id="cma"></canvas></div>
  </div>
</section>
<details class="panel"><summary>Detalle de ventas por SKU (filtro actual)</summary><div class="scroll" style="margin-top:10px"><table id="tsk"></table></div></details>
<details class="panel"><summary>Consignación en otros clientes (informativo)</summary><div class="scroll" style="margin-top:10px"><table id="tcon"></table></div></details>
</div>
<script>
const D=__DATA__;const $=i=>document.getElementById(i);
const css=v=>getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const nf=new Intl.NumberFormat('es-CO');const fmt=n=>n==null?'—':nf.format(Math.round(n));
const fm=n=>n==null?'—':'$'+(Math.abs(n)>=1e6?(n/1e6).toLocaleString('es-CO',{maximumFractionDigits:1})+' M':fmt(n));
const pc=x=>x==null?'—':(x*100).toLocaleString('es-CO',{maximumFractionDigits:1})+'%';
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const K=D.kpi;
$('sub').textContent=`Corte NetSuite ${D.fecha} · Odoo al ${D.asof_sellin.nueva||'—'} · ${D.n_correos} reportes semanales`;
$('src').textContent=`Ventas ${K.periodo[0]} → ${K.periodo[1]} · COP sin IVA`;
$('alerts').innerHTML=D.frenos.map(a=>`<li class="fr"><b>Freno:</b> ${esc(a)}</li>`).join('')+D.alertas.map(a=>`<li>${esc(a)}</li>`).join('');
const tile=(l,v,i)=>`<div class="k"><span>${l}</span><b>${v}</b>${i?`<i>${i}</i>`:''}</div>`;
$('kpis').innerHTML=[
 tile('Últimas 4 semanas',fm(K.l4_vn),K.var_4s==null?'':`${K.var_4s>=0?'+':''}${pc(K.var_4s)} vs 4 previas`),
 tile('Cobertura In/Out',K.cobertura.toLocaleString('es-CO',{maximumFractionDigits:2})+'x',`${fmt(K.in_u)} u facturadas / ${fmt(K.out_u)} vendidas`),
 tile('Consignación en CM',fmt(K.consig_cm_u)+' u',`≈ ${fm(K.consig_cm_valor_est)} a precio de factura`),
 tile('Facturar consignación',fmt(K.facturar_cons_u)+' u','vendidas sin factura'),
 tile('Reponer',fmt(K.reponer_u)+' u',`${fmt(K.por_comprar_u)} u por comprar`),
 tile('Por despachar',fmt(K.por_despachar_u)+' u','entregas abiertas en Odoo'),
 tile('Venta neta acumulada',fm(K.venta_neta),`margen CM ${pc(K.margen)}`)].join('');
const EST={'Facturar consignación':'t-fc','Revisar':'t-rv','Reponer':'t-rp','Sobre-stock CM':'t-ss','Sin rotación':'t-sr','OK':'t-ok'};
const ORD=Object.keys(EST);let fEst=null;
function chips(){$('chips').innerHTML=`<button class="chip" id="ch-all" aria-pressed="${!fEst}">Todos <span class="c t-sr">${D.cmp.length}</span></button>`+
 ORD.map((e,i)=>{const n=D.cmp.filter(c=>c.est==e).length;return n?`<button class="chip" id="ch-${i}" data-e="${e}" aria-pressed="${fEst==e}">${e} <span class="c ${EST[e]}">${n}</span></button>`:''}).join('');
 $('chips').querySelectorAll('button').forEach(b=>b.onclick=()=>{fEst=b.dataset.e||null;chips();pos()})}
function sortable(id,cols,rows,def,dir){const t=$(id);let st={c:def||0,d:dir||-1};
 function draw(){rows.sort((a,b)=>{const x=a[cols[st.c].k],y=b[cols[st.c].k];if(x==null)return 1;if(y==null)return -1;return (typeof x=='string'?x.localeCompare(y):x-y)*st.d});
 t.innerHTML='<thead><tr>'+cols.map((c,i)=>`<th class="${c.n?'n':''}" data-i="${i}" tabindex="0" title="${esc(c.t||'')}">${c.h}</th>`).join('')+'</tr></thead><tbody>'+
 (rows.length?rows.map(r=>'<tr>'+cols.map(c=>{const v=r[c.k];const cl=(c.n?'n ':'')+(c.d?'d ':'')+(c.n&&!v?'z ':'')+(c.hot&&v>0?'hot':'');return `<td class="${cl}">${c.f?c.f(v,r):esc(v)}</td>`}).join('')+'</tr>').join(''):`<tr><td colspan="${cols.length}" class="z">Sin registros.</td></tr>`)+'</tbody>';
 t.querySelectorAll('th').forEach(h=>{const go=()=>{const i=+h.dataset.i;st=st.c==i?{c:i,d:-st.d}:{c:i,d:-1};draw()};h.onclick=go;h.onkeydown=e=>{if(e.key=='Enter')go()}})}draw()}
const U=v=>v==null?'—':fmt(v);
function pos(){const R=D.cmp.filter(c=>!fEst||c.est==fEst).map(c=>({...c,ord:ORD.indexOf(c.est)}));
 sortable('tpos',[{h:'SKU',k:'sku'},{h:'Descripción',k:'desc',d:1},{h:'Estado',k:'ord',f:(v,r)=>`<span class="tag ${EST[r.est]}">${r.est}</span>`},
 {h:'Facturado',k:'inu',n:1,f:U,t:'Sell in Odoo (vintral1 + principal)'},{h:'Vendido',k:'outu',n:1,f:U,t:'Sell out NetSuite'},
 {h:'Consig.',k:'consig',n:1,f:U,t:'Unidades VINTRAL en consignación a nombre de Casa Magna'},{h:'Inv. CM',k:'inv_cm',n:1,f:U,t:'Facturado + consignación − vendido'},
 {h:'Rot./sem',k:'rot_sem',n:1,f:v=>v?v.toLocaleString('es-CO',{maximumFractionDigits:2}):'—'},{h:'Cob. sem',k:'cob_sem',n:1,f:v=>v==null?'—':Math.round(v)},
 {h:'Facturar',k:'facturar_cons',n:1,hot:1,f:U},{h:'Ped. abierto',k:'pedido_abierto',n:1,f:U},{h:'Por desp.',k:'por_despachar',n:1,f:U},
 {h:'Stock VINTRAL',k:'stock_propio',n:1,f:U},{h:'Tránsito',k:'transito',n:1,f:U},{h:'Reponer',k:'reponer',n:1,hot:1,f:U},{h:'Por comprar',k:'por_comprar',n:1,hot:1,f:U},
 {h:'Últ. venta',k:'ult_venta',f:v=>v||'—'}],R,2,1)}
chips();pos();
const M=D.modelo;$('metodo').textContent=`Inv. CM = facturado + consignación − vendido (estimado: el sell in arranca jun-2025 y el sell out ago-2025, así que el inventario queda algo sobrestimado). Rotación = unidades vendidas en las últimas ${M.semanas_rotacion} semanas ÷ ${M.semanas_rotacion}. Reponer = rotación × ${M.semanas_objetivo_cm} semanas − inventario CM − pedidos abiertos; se cubre con stock VINTRAL disponible, luego tránsito, y el resto es por comprar. Sobre-stock = más de ${M.semanas_sobrestock} semanas de cobertura. Facturar consignación = vendido por encima de lo facturado, hasta las unidades en consignación. Excluye accesorios (DSTOCLI, PROTMK04SS304, FT05).`;
sortable('tped',[{h:'Pedido',k:'pedido'},{h:'Estado',k:'estado'},{h:'Fecha',k:'fecha'},{h:'Valor',k:'valor',n:1,f:fm},{h:'Líneas',k:'lin',d:1}],D.pedidos.map(p=>({...p,lin:p.lineas.map(l=>`${l.sku} ×${fmt(l.u)}`).join(', ')||'—'})),2);
sortable('tdes',[{h:'SKU',k:'sku'},{h:'Unid.',k:'u',n:1,f:U},{h:'Entrega',k:'picking'},{h:'Origen',k:'origen'},{h:'Programada',k:'fecha'}],D.por_despachar.slice(),4,1);
sortable('ttra',[{h:'SKU',k:'sku'},{h:'Unid.',k:'units',n:1,f:U},{h:'OC',k:'ref'},{h:'Proveedor',k:'proveedor',d:1},{h:'ETA',k:'eta',f:(v,r)=>r.eta_vencida?`<span class="tag t-rv">${v} vencida</span>`:v}],D.transito.slice(),4,1);
sortable('tcon',[{h:'Cliente',k:'s'},{h:'SKU',k:'sku'},{h:'Unid.',k:'u',n:1,f:U}],Object.entries(D.consig_otros).flatMap(([s,o])=>Object.entries(o).map(([sku,u])=>({s,sku,u}))),0,1);
const CH={};function mk(id,cfg){try{if(CH[id])CH[id].destroy();if(window.Chart)CH[id]=new Chart($(id),cfg)}catch(e){console.error(id,e)}}
if(window.Chart){Chart.defaults.color=css('--mute');Chart.defaults.borderColor=css('--line');Chart.defaults.font.family=css('--f-body')}
const CS=D.cmp.filter(c=>c.inu||c.outu).sort((a,b)=>b.inu+b.outu-a.inu-a.outu).slice(0,18);
mk('cio',{type:'bar',data:{labels:CS.map(c=>c.sku),datasets:[{label:'Facturado',data:CS.map(c=>c.inu),backgroundColor:css('--acc')},{label:'Vendido',data:CS.map(c=>c.outu),backgroundColor:css('--acc2')},{label:'Consignación',data:CS.map(c=>c.consig),backgroundColor:css('--info')}]},options:{maintainAspectRatio:false,plugins:{legend:{position:'bottom'}}}});
const uniq=a=>[...new Set(a)].sort();const weeks=uniq(D.rows.map(r=>r.w));
function fill(id,vals,all){$(id).innerHTML=(all?'<option value="">Todos</option>':'')+vals.map(v=>`<option>${esc(v)}</option>`).join('')}
fill('fm',uniq(D.rows.map(r=>r.marca)),1);fill('fp',uniq(D.rows.map(r=>r.plaza)),1);fill('fr',uniq(D.rows.map(r=>r.rep)),1);fill('fw1',weeks);fill('fw2',weeks);$('fw2').value=weeks[weeks.length-1];
['fm','fp','fr','fw1','fw2'].forEach(i=>$(i).onchange=render);
const pal=['--acc','--acc2','--info','--ok','--bad','--warn'].map(css);
function render(){const m=$('fm').value,p=$('fp').value,r=$('fr').value,w1=$('fw1').value,w2=$('fw2').value;
 const R=D.rows.filter(x=>(!m||x.marca==m)&&(!p||x.plaza==p)&&(!r||x.rep==r)&&x.w>=w1&&x.w<=w2);
 const vn=R.reduce((a,x)=>a+x.vn,0),ct=R.reduce((a,x)=>a+x.ct,0),u=R.reduce((a,x)=>a+x.q,0);
 $('kpis2').innerHTML=[tile('Venta neta',fm(vn)),tile('Unidades',fmt(u)),tile('Margen CM',vn?pc(1-ct/vn):'—'),tile('Líneas',fmt(R.length)),tile('Semanas con venta',uniq(R.map(x=>x.w)).length+'')].join('');
 const by=(k,f)=>{const o={};R.forEach(x=>o[x[k]]=(o[x[k]]||0)+f(x));return o};
 const W=weeks.filter(w=>w>=w1&&w<=w2),tw=by('w',x=>x.vn);
 mk('ctr',{type:'bar',data:{labels:W,datasets:[{label:'Venta neta',data:W.map(w=>tw[w]||0),backgroundColor:css('--acc')}]},options:{plugins:{legend:{display:false}},scales:{y:{ticks:{callback:v=>fm(v)}}}}});
 const bm=by('marca',x=>x.vn);mk('cma',{type:'doughnut',data:{labels:Object.keys(bm),datasets:[{data:Object.values(bm),backgroundColor:pal,borderColor:css('--panel')}]},options:{plugins:{legend:{position:'bottom'}}}});
 const bp=Object.entries(by('plaza',x=>x.vn)).sort((a,b)=>b[1]-a[1]);mk('cpl',{type:'bar',data:{labels:bp.map(x=>x[0]),datasets:[{data:bp.map(x=>x[1]),backgroundColor:css('--info')}]},options:{indexAxis:'y',plugins:{legend:{display:false}},scales:{x:{ticks:{callback:v=>fm(v)}}}}});
 const S={};R.forEach(x=>{const s=S[x.sku]=S[x.sku]||{sku:x.sku,desc:D.desc[x.sku]||'',u:0,v:0,last:''};s.u+=x.q;s.v+=x.vn;if(x.f>s.last)s.last=x.f});
 const SL=Object.values(S).sort((a,b)=>b.v-a.v);let acc=0;SL.forEach(s=>{acc+=s.v;s.cum=vn?acc/vn*100:0;s.abc=s.cum<=80?'A':s.cum<=95?'B':'C'});
 mk('cpa',{type:'bar',data:{labels:SL.map(s=>s.sku),datasets:[{label:'Venta neta',data:SL.map(s=>s.v),backgroundColor:css('--acc2'),yAxisID:'y'},{type:'line',label:'% acumulado',data:SL.map(s=>s.cum),borderColor:css('--bad'),backgroundColor:css('--bad'),yAxisID:'y1',pointRadius:2}]},options:{plugins:{legend:{position:'bottom'}},scales:{y:{ticks:{callback:v=>fm(v)}},y1:{position:'right',min:0,max:100,grid:{drawOnChartArea:false}}}}});
 sortable('tsk',[{h:'SKU',k:'sku'},{h:'Descripción',k:'desc',d:1},{h:'Unid.',k:'u',n:1,f:U},{h:'Venta neta',k:'v',n:1,f:fm},{h:'% acum.',k:'cum',n:1,f:v=>v.toFixed(1)+'%'},{h:'ABC',k:'abc'},{h:'Últ. venta',k:'last'}],SL.slice(),3)}
render();
</script>'''
html = TPL.replace('__DATA__', json.dumps(D, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/'))
open(wpath('output/index.html'), 'w', encoding='utf-8').write(html)
# copia standalone para el correo (con doctype propio, porque fuera del artefacto no hay esqueleto)
open(wpath('output/Sell_Out_CasaMagna.html'), 'w', encoding='utf-8').write(
    '<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body>' + html + '</body></html>')
print(f'OK dashboard ({len(html)//1024} KB)')
