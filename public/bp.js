const bpMapKeys={'Mirage':'mirage','Inferno':'inferno','Dust II':'dust2','Ancient':'ancient','Nuke':'nuke','Anubis':'anubis','Vertigo':'vertigo','Train':'train','Overpass':'overpass','Cache':'cache'};
const bpDefaultPool=['Mirage','Inferno','Dust II','Ancient','Nuke','Anubis','Cache'];
let bpDraft=null,bpBase=null,bpDirty=false,bpCleared=false;
function bpTemplate(m,first='A'){
  const order={2:['A:Ban','B:Ban','B:Ban','A:Ban','A:Pick','B:Pick',':Unused'],3:['A:Ban','B:Ban','A:Pick','B:Pick','A:Ban','B:Ban',':Decider'],5:['A:Ban','B:Ban','A:Pick','B:Pick','A:Pick','B:Pick',':Decider']}[m.bo];
  const ids=first==='A'?{A:m.team_a,B:m.team_b}:{A:m.team_b,B:m.team_a};
  return order.map(x=>{const [side,action]=x.split(':');return {teamId:ids[side]??null,action,map:'',sidePicker:null,startSide:''}});
}
function bpDisplaySteps(m){
  if(m.bp_config?.first)return m.bp;
  if(!m.bp.length)return bpTemplate(m);
  return [...m.bp,...Array.from({length:Math.max(0,7-m.bp.length)},()=>({action:'Pending',map:'',teamId:null}))];
}
function bpCards(m,steps=bpDisplaySteps(m)){
  let mapIndex=0;
  return `<div class="veto-scroll" tabindex="0" role="region" aria-label="地图禁选顺序"><div class="veto-grid">${steps.map((s,i)=>{
    const playable=['Pick','Decider'].includes(s.action),number=playable?++mapIndex:null,t=team(s.teamId),result=playable?m.maps.find(map=>map.name===s.map):null;
    return `<article class="veto-card ${s.action.toLowerCase()} ${s.map?'':'pending'}"><div class="veto-step"><span>${String(i+1).padStart(2,'0')}</span><b>${s.action==='Pending'?'—':s.action.toUpperCase()}</b></div><div class="veto-owner">${t?.logo?`<img src="${esc(t.logo)}" alt="">`:''}<span title="${esc(t?.name)}">${esc(t?.tag||'')}</span></div><div class="veto-art">${s.map&&bpMapKeys[s.map]?`<img src="/assets/maps/${bpMapKeys[s.map]}.webp" alt="${esc(s.map)}" loading="lazy">`:''}<strong>${esc(s.map||'待选地图')}</strong></div>${playable?`<div class="veto-result"><span class="veto-mapno">MAP ${String(number).padStart(2,'0')}</span>${[m.team_a,m.team_b].map((id,index)=>{const side=s.sidePicker&&s.startSide?(id===s.sidePicker?s.startSide:s.startSide==='CT'?'T':'CT'):'';return `<div class="veto-side"><span title="${esc(team(id)?.name)}">${esc(team(id)?.tag||'待定')}</span><b class="${side.toLowerCase()}">${side||'—'}</b>${result?`<strong class="veto-score">${index===0?result.scoreA:result.scoreB}</strong>`:''}</div>`}).join('')}</div>`:''}</article>`;
  }).join('')}</div></div>`;
}
function initBP(m){
  bpCleared=false;
  bpBase={bp:structuredClone(m.bp),config:structuredClone(m.bp_config),bo:m.bo,teams:[m.team_a,m.team_b]};
  if(m.bp_config.first){bpDraft={config:structuredClone(m.bp_config),steps:structuredClone(m.bp)};return}
  const first=m.bp[0]?.teamId===m.team_b?'B':'A',steps=bpTemplate(m,first);
  for(const saved of m.bp){const slot=steps.find(s=>!s.map&&s.action===saved.action&&(s.teamId===saved.teamId||s.action==='Decider'));if(slot)Object.assign(slot,saved,{sidePicker:null,startSide:''})}
  const pool=[...new Set([...m.bp.map(s=>s.map),...bpDefaultPool])].slice(0,7);
  bpDraft={config:{first,pool},steps};
}
function bpEditor(m){
  return `<h3>地图 BP</h3><div class="bp-controls"><div class="bp-order"><span class="pill">BO${m.bo}</span><label class="field">BP 先手方<select onchange="changeBPFirst(this.value)">${[['A',m.team_a],['B',m.team_b]].map(([side,id])=>`<option value="${side}" ${bpDraft.config.first===side?'selected':''}>${esc(team(id)?.name||'待定队伍')}</option>`).join('')}</select></label></div><details class="bp-pool"><summary>地图池 <span id="pool-count">${bpDraft.config.pool.length} / 7</span></summary><div class="pool-options">${Object.keys(bpMapKeys).map(name=>`<label><input type="checkbox" value="${esc(name)}" ${bpDraft.config.pool.includes(name)?'checked':''} onchange="changeBPPool(this)">${esc(name)}</label>`).join('')}</div></details></div><div id="bp-edit-steps">${bpStepInputs(m)}</div><div class="bp-save"><button type="button" class="subtle" onclick="clearBP()">清空 BP</button></div><section class="section"><div class="section-heading"><h2>展示预览</h2></div><div id="bp-preview">${bpCards(m,bpDraft.steps)}</div></section>`;
}
function bpStepInputs(m){return `<div class="bp-edit-grid">${bpDraft.steps.map((s,i)=>`<div class="bp-edit-card"><div class="veto-step"><span>${String(i+1).padStart(2,'0')}</span><b>${s.action.toUpperCase()}</b></div><div class="bp-edit-owner">${esc(team(s.teamId)?.tag||'双方')}</div><label class="field">地图<select aria-label="第 ${i+1} 步地图" onchange="setBPMap(${i},this.value)"><option value="">待选地图</option>${bpDraft.config.pool.map(name=>`<option value="${esc(name)}" ${name===s.map?'selected':''} ${bpDraft.steps.some((x,j)=>j!==i&&x.map===name)?'disabled':''}>${esc(name)}</option>`).join('')}</select></label>${['Pick','Decider'].includes(s.action)?`<label class="field">选边队伍<select aria-label="第 ${i+1} 步选边队伍" onchange="setBPSide(${i},'sidePicker',this.value)" ${!s.map?'disabled':''}><option value="">待定</option>${[m.team_a,m.team_b].filter(Boolean).map(id=>`<option value="${id}" ${id===s.sidePicker?'selected':''}>${esc(team(id)?.tag)}</option>`).join('')}</select></label><label class="field">开局阵营<select aria-label="第 ${i+1} 步开局阵营" onchange="setBPSide(${i},'startSide',this.value)" ${!s.map||!s.sidePicker?'disabled':''}><option value="">待定</option>${['CT','T'].map(side=>`<option ${s.startSide===side?'selected':''}>${side}</option>`).join('')}</select></label>`:''}</div>`).join('')}</div>`}
function refreshBPDraft(){bpDirty=true;bpCleared=false;const m=draftMatch;$('#bp-edit-steps').innerHTML=bpStepInputs(m);$('#bp-preview').innerHTML=bpCards(m,bpDraft.steps)}
function setBPMap(i,map){Object.assign(bpDraft.steps[i],{map,sidePicker:null,startSide:''});refreshBPDraft()}
function setBPSide(i,key,value){bpDraft.steps[i][key]=key==='sidePicker'?(Number(value)||null):value;if(key==='sidePicker'&&!value)bpDraft.steps[i].startSide='';refreshBPDraft()}
function changeBPFirst(first){const m=draftMatch,next=bpTemplate(m,first);bpDraft.config.first=first;bpDraft.steps=next.map((s,i)=>({...s,map:bpDraft.steps[i].map,sidePicker:bpDraft.steps[i].sidePicker,startSide:bpDraft.steps[i].startSide}));refreshBPDraft()}
function changeBPPool(input){if(!input.checked&&bpDraft.steps.some(s=>s.map===input.value)){input.checked=true;toast('请先清除该地图的 BP 选择');return}bpDraft.config.pool=[...document.querySelectorAll('.pool-options input:checked')].map(x=>x.value);$('#pool-count').textContent=bpDraft.config.pool.length+' / 7';refreshBPDraft()}
function clearBP(){bpDraft.steps=bpTemplate(draftMatch,bpDraft.config.first);refreshBPDraft();bpCleared=true}
