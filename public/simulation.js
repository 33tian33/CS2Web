const unlockedSimulationMatches=new Set();
let simulatedResults={},simulationResult=null,simulationRequest=0,simulationEntryRequest=0;
const simulationEligible=m=>m.stage==='group'&&m.flow_key&&(m.status==='finished'||!m.maps.length)&&m.team_a&&m.team_b;
function simulationScores(bo){return bo===2?[[2,0],[1,1],[0,2]]:Array.from({length:Math.floor(bo/2)+1},(_,i)=>[[Math.floor(bo/2)+1,i],[i,Math.floor(bo/2)+1]]).flat()}
function actualSimulationResult(m){const [scoreA,scoreB]=score(m);return {id:m.id,scoreA,scoreB,roundDiff:m.maps.reduce((sum,map)=>sum+map.scoreA-map.scoreB,0)}}
function simulationMatch(m){
  const finished=m.status==='finished',locked=finished&&!unlockedSimulationMatches.has(m.id);
  const value=simulatedResults[m.id]||(finished?actualSimulationResult(m):null);
  const options=simulationScores(m.bo);
  if(finished&&!options.some(([a,b])=>a===value.scoreA&&b===value.scoreB))options.unshift([value.scoreA,value.scoreB]);
  return `<div id="simulation-match-${m.id}" class="simulation-match ${locked?'is-locked':''}"><div class="simulation-teams">${teamIdentity(team(m.team_a))}<span>vs</span>${teamIdentity(team(m.team_b))}</div>${finished?`<div class="simulation-lock"><span>${locked?'已完成 · 已锁定':'已完成 · 已解锁模拟'}</span><button type="button" class="outline" aria-label="#${m.id} ${locked?'解锁模拟':'恢复并锁定'}" onclick="toggleSimulationLock(${m.id})">${locked?'解锁模拟':'恢复并锁定'}</button></div>`:''}<div class="simulation-inputs"><label>大比分<select aria-label="#${m.id} 大比分" ${locked?'disabled':''} onchange="setSimulationScore(${m.id},this.value)">${finished?'':'<option value="">未模拟</option>'}${options.map(([a,b])=>`<option value="${a}:${b}" ${value?.scoreA===a&&value?.scoreB===b?'selected':''}>${a} : ${b}</option>`).join('')}</select></label><label>左队净胜小局<input type="number" step="1" aria-label="#${m.id} 左队净胜小局" value="${value?.roundDiff??''}" ${value&&!locked?'':'disabled'} oninput="setSimulationDiff(${m.id},this)"></label></div></div>`;
}
function toggleSimulationLock(id){
  if(unlockedSimulationMatches.has(id)){unlockedSimulationMatches.delete(id);delete simulatedResults[id]}
  else unlockedSimulationMatches.add(id);
  $(`#simulation-match-${id}`).outerHTML=simulationMatch(state.matches.find(m=>m.id===id));
  queueSimulation();
}
function simulationTable(g,advance){return `<div class="table-wrap group-standings"><table><thead><tr><th>#</th><th>队伍</th><th>胜/平/负</th><th>净胜图</th><th>净胜小局</th><th>积分</th></tr></thead><tbody>${g.rows.map((r,i)=>`<tr class="rank-${i<advance?'green':i===advance?'yellow':'red'} confirmed-${r.qualification||'pending'}"><td>${i+1}</td><td>${teamIdentity(team(r.teamId))}</td><td>${r.w}/${r.d}/${r.l}</td><td>${r.mw-r.ml}</td><td>${r.rd}</td><td class="points">${r.pts}</td></tr>`).join('')}</tbody></table></div>`}
let simulationConfirmed=false;
async function enterSimulation(){
  simulationConfirmed=false;
  const request=++simulationEntryRequest;
  simulationRequest++;
  shell('<div class="loading" role="status">正在同步最新赛果…</div>');
  try{
    const latest=await api('state');
    if(request!==simulationEntryRequest||location.hash!=='#/event/simulation')return;
    state=latest;simulatedResults={};simulationResult=null;unlockedSimulationMatches.clear();
    render();
  }catch(error){
    if(request!==simulationEntryRequest||location.hash!=='#/event/simulation')return;
    shell(`<div class="empty">同步赛果失败：${esc(error.message)}<p><button class="outline" onclick="enterSimulation()">重新同步</button></p></div>`);
  }
}
function confirmFinishedSimulation(){simulationConfirmed=true;render()}
function simulationPage(){
  if(allGroupMatchesFinished()&&!simulationConfirmed){
    shell('<section class="panel simulation-confirmation"><p>小组赛的结局已经编织完毕，32强的对决已经产生，过时的预言无法改变已有的命运……</p><button type="button" class="primary" onclick="confirmFinishedSimulation()">是的，我还要预言我的Team If</button></section>');
    return;
  }
  const plan=state.flow.active,stages=plan.stages.filter(s=>s.type==='group');
  const data=simulationResult||state.flow;
  shell(`<div class="breadcrumb"><a href="#/event">赛事详情</a><span>/</span><span>模拟赛果</span></div><div class="page-heading"><div><h1>模拟赛果</h1><p>仅影响本页预测；净胜小局按左侧队伍计算，负数表示净负。完全同分沿用积分表顺序。</p></div><button class="outline" onclick="resetSimulation()">重置模拟</button></div><div class="simulation-nav"><div class="tabs"><button class="tab" onclick="document.querySelector('.simulation-groups').scrollIntoView()">小组赛果</button><button class="tab" onclick="document.querySelector('#simulation-outcomes').scrollIntoView()">第三名排名</button><button class="tab" onclick="document.querySelector('#simulation-bracket').scrollIntoView()">淘汰赛预测</button></div><span id="simulation-status" role="status" aria-live="polite">${Object.keys(simulatedResults).length} 场已模拟</span></div><div class="simulation-groups">${stages.map(st=>data.tables.filter(g=>g.stageId===st.id).map(g=>{
    const keys=new Set(flowMatches({stages:[st]}).filter(d=>d.group===g.group).map(d=>d.key));
    const matches=state.matches.filter(m=>keys.has(m.flow_key)&&simulationEligible(m));
    return `<section class="panel simulation-group"><h2>${String.fromCharCode(65+g.group)} 组</h2><div id="simulation-table-${st.id}-${g.group}">${simulationTable(g,st.advance)}</div><details open><summary>小组比赛 · ${matches.length} 场</summary>${matches.map(simulationMatch).join('')||'<p class="muted">本组没有可模拟的比赛</p>'}</details></section>`;
  }).join('')).join('')}</div><div id="simulation-outcomes">${simulationOutcomes(data)}</div>`);
}
function simulationOutcomes(data){
  const plan=state.flow.active;
  return plan.stages.filter(s=>s.type==='group').map(st=>(st.comparators||[]).map(c=>{const result=data.comparisons.find(r=>r.stageId===st.id&&r.comparatorId===c.id);return `<section class="section"><div class="section-heading"><h2>${esc(c.name)} · 模拟排名</h2></div>${comparatorTable(st,c,plan,result)}</section>`}).join('')).join('')+'<div id="simulation-bracket">'+plan.stages.filter(s=>data.projections.some(p=>p.stageId===s.id)).map(st=>`<section class="section"><div class="section-heading"><h2>淘汰赛对阵预测</h2></div>${knockoutGraph(st,plan,true,data)}</section>`).join('')+'</div>';
}
function setSimulationScore(id,value){
  if(!value)delete simulatedResults[id];
  else{const [scoreA,scoreB]=value.split(':').map(Number);simulatedResults[id]={id,scoreA,scoreB,roundDiff:13*(scoreA-scoreB),unlocked:unlockedSimulationMatches.has(id)}}
  const input=document.querySelector(`[aria-label="#${id} 左队净胜小局"]`);
  input.disabled=!value;input.value=simulatedResults[id]?.roundDiff??'';input.setCustomValidity('');
  queueSimulation();
}
function setSimulationDiff(id,input){
  if(input.value===''||!Number.isInteger(Number(input.value))){input.setCustomValidity('请输入整数');simulationRequest++;$('#simulation-status').textContent='请输入完整的净胜小局，预测尚未更新';return}
  input.setCustomValidity('');
  if(!simulatedResults[id])simulatedResults[id]={...actualSimulationResult(state.matches.find(m=>m.id===id)),unlocked:unlockedSimulationMatches.has(id)};
  simulatedResults[id].roundDiff=Number(input.value);queueSimulation();
}
async function queueSimulation(){
  const request=++simulationRequest;
  if([...document.querySelectorAll('.simulation-inputs input:not(:disabled)')].some(input=>input.value===''||!input.validity.valid)){$('#simulation-status').textContent='请输入完整的净胜小局，预测尚未更新';return}
  $('#simulation-status').textContent='正在更新预测…';
    try{
      const result=await api('simulate',{revision:state.flow.simulationRevision,results:Object.values(simulatedResults)});
      if(request!==simulationRequest||location.hash!=='#/event/simulation')return;
      simulationResult=result;
      for(const st of state.flow.active.stages.filter(s=>s.type==='group'))for(const g of result.tables.filter(g=>g.stageId===st.id))$(`#simulation-table-${st.id}-${g.group}`).innerHTML=simulationTable(g,st.advance);
      $('#simulation-outcomes').innerHTML=simulationOutcomes(result);restoreKnockoutPositions();
      $('#simulation-status').textContent=`${Object.keys(simulatedResults).length} 场已模拟`;
    }catch(e){if(request===simulationRequest&&location.hash.startsWith('#/event/simulation'))$('#simulation-status').innerHTML=`${esc(e.message)}；预测尚未更新 <button class="outline" onclick="enterSimulation()">同步赛果并重置模拟</button>`}
}
function resetSimulation(){simulationRequest++;unlockedSimulationMatches.clear();simulatedResults={};simulationResult=null;render();queueSimulation()}
