function worldCupComparator(plan,st,c){return plan.stages.find(s=>s.bracket==='worldcup2026'&&s.groupStageId===st.id&&s.comparatorId===c.id)}
function comparisonSource(st,c,rank){return {kind:'comparison',stageId:st.id,comparatorId:c.id,rank}}
function comparisonTarget(plan,st,c,rank){return plan.stages.flatMap(s=>s.slots.map((src,i)=>({stage:s,index:i,src}))).find(t=>t.src.kind==='comparison'&&t.src.stageId===st.id&&t.src.comparatorId===c.id&&t.src.rank===rank)}
function groupRankUsed(st,group,rank,exceptId,exceptIndex){
  return (st.comparators||[]).some(c=>c.inputs.some((src,i)=>src&&src.group===group&&src.rank===rank&&(c.id!==exceptId||i!==exceptIndex)))||flowDraft.stages.some(s=>s.slots.some(src=>src.kind==='rank'&&src.stageId===st.id&&src.group===group&&src.rank===rank));
}
function addComparator(){const st=selectedStage();(st.comparators||=[]).push({id:'c'+crypto.randomUUID().replaceAll('-',''),name:`跨组比较器 ${st.comparators.length+1}`,inputs:[null,null],outcomes:['qualified','eliminated']});flowDirty=true;render()}
function changeComparator(id,key,value){const c=selectedStage().comparators.find(c=>c.id===id);c[key]=value;flowDirty=true;render()}
function resizeComparator(id,value){
  const st=selectedStage(),c=st.comparators.find(c=>c.id===id),n=Number(value);
  if(!Number.isInteger(n)||n<2||n>st.teamCount){toast(`进入队伍数须为 2–${st.teamCount}`);render();return}
  if(c.inputs.some((_,i)=>i>=n&&comparisonTarget(flowDraft,st,c,i+1))){toast('请先解除被移除名次的晋级去向');render();return}
  c.inputs=Array.from({length:n},(_,i)=>c.inputs[i]??null);c.outcomes=Array.from({length:n},(_,i)=>c.outcomes[i]||'eliminated');flowDirty=true;render();
}
function removeComparator(id){
  const st=selectedStage(),c=st.comparators.find(c=>c.id===id);
  if(c.inputs.some((_,i)=>comparisonTarget(flowDraft,st,c,i+1))){toast('请先解除比较器的晋级去向');return}
  st.comparators=st.comparators.filter(c=>c.id!==id);flowDirty=true;render();
}
function setComparatorInput(id,index,value){const c=selectedStage().comparators.find(c=>c.id===id);c.inputs[index]=value?JSON.parse(value):null;flowDirty=true;render()}
function setComparatorTarget(id,rank,value){
  const st=selectedStage(),c=st.comparators.find(c=>c.id===id),old=comparisonTarget(flowDraft,st,c,rank);
  if(old)old.stage.slots[old.index]={kind:'empty'};
  if(['qualified','eliminated'].includes(value))c.outcomes[rank-1]=value;
  else {const [sid,index]=value.split(':');flowDraft.stages.find(s=>s.id===sid).slots[Number(index)]=comparisonSource(st,c,rank)}
  flowDirty=true;render();
}
function comparatorRoute(st,c,rank){
  const target=comparisonTarget(flowDraft,st,c,rank),value=target?`${target.stage.id}:${target.index}`:c.outcomes[rank-1];
  const options=[['qualified','终结 · 晋级',false],['eliminated','终结 · 淘汰',false]];
  for(const s of flowDraft.stages.slice(flowDraft.stages.indexOf(st)+1))s.slots.forEach((src,i)=>options.push([`${s.id}:${i}`,`${s.name} · 位置 ${i+1}`,src.kind!=='empty'&&`${s.id}:${i}`!==value]));
  return `<select aria-label="${esc(c.name)}第 ${rank} 名去向" onchange="setComparatorTarget('${c.id}',${rank},this.value)">${options.map(([v,label,disabled])=>`<option value="${esc(v)}" ${v===value?'selected':''} ${disabled?'disabled':''}>${esc(label)}</option>`).join('')}</select>`;
}
function comparatorTable(st,c,plan,result,editable=false){
  const wc=worldCupComparator(plan,st,c);
  const diff=n=>n>0?'+'+n:String(n);
  return `<div class="table-wrap comparator-table"><table><thead><tr><th>排名</th><th>来源</th><th>队伍</th><th>积分</th><th>净胜图</th><th>净胜回合</th><th>排名去向</th></tr></thead><tbody>${c.inputs.map((_,i)=>{const row=result?.rows[i],target=comparisonTarget(plan,st,c,i+1),outcome=wc&&i<8?(row?.worldcupOpponent?`32强 · 对 ${row.worldcupOpponent}1`:'晋级32强 · 对手待定'):target?`${target.stage.name} · 位置 ${target.index+1}`:c.outcomes[i]==='qualified'?'晋级':'淘汰';return `<tr class="rank-${wc?i<8?'green':'red':target||c.outcomes[i]==='qualified'?'green':'red'} confirmed-${row?.qualification||'pending'}"><td>${String(i+1).padStart(2,'0')}</td><td>${row?`${String.fromCharCode(65+row.group)} 组第 ${row.groupRank} 名`:'—'}</td><td>${row?`<a class="inline-team" href="#/team/${row.teamId}">${teamIdentity(team(row.teamId))}</a>`:'待定'}</td><td class="points">${row?.pts??'—'}</td><td>${row?diff(row.mapDiff):'—'}</td><td>${row?diff(row.rd):'—'}</td><td>${editable&&!wc?comparatorRoute(st,c,i+1):`<span class="${result?.complete&&c.outcomes[i]==='qualified'&&!target?'lime':''}">${result?.complete||['qualified','eliminated'].includes(row?.qualification)?'':'待定 · '}${esc(row?.qualification==='eliminated'?'淘汰':outcome)}</span>`}</td></tr>`}).join('')}</tbody></table></div>`;
}
function comparatorStatus(result,dirty=false){return dirty?'保存草稿后更新排名':result?.unresolved?'组内名次同分，等待裁定':result?.complete?'最终排名':'暂定排名 · 等待来源选齐及相关小组完赛'}
function stageComparators(st){
  const dirty=JSON.stringify(flowDraft)!==JSON.stringify(state.flow.draft);
  return `<div class="section-heading"><h3>跨组比较器</h3><button class="outline" onclick="addComparator()">＋ 添加比较器</button></div>${(st.comparators||[]).length?'':'<div class="empty">选择各小组名次，比较晋级队伍。</div>'}${(st.comparators||[]).map(c=>{
    const result=dirty?null:state.flow.draftComparisons.find(r=>r.stageId===st.id&&r.comparatorId===c.id),size=Math.floor(st.teamCount/st.groupCount),locked=Boolean(worldCupComparator(flowDraft,st,c));
    return `<section class="comparator-editor"><div class="comparator-heading"><label class="field">比较器名称<input value="${esc(c.name)}" maxlength="60" onchange="changeComparator('${c.id}','name',this.value)"></label><label class="field">进入队伍数<input type="number" ${locked?'disabled':''} min="2" max="${st.teamCount}" value="${c.inputs.length}" onchange="resizeComparator('${c.id}',this.value)"></label><button class="subtle" ${locked?'disabled':''} onclick="removeComparator('${c.id}')">删除比较器</button></div><div class="stage-slots comparator-inputs">${c.inputs.map((src,i)=>`<label class="field">来源 ${i+1}<select ${locked?'disabled':''} aria-label="${esc(c.name)}来源 ${i+1}" onchange="setComparatorInput('${c.id}',${i},this.value)"><option value="">选择小组名次</option>${Array.from({length:st.groupCount},(_,g)=>Array.from({length:size},(_,r)=>{const selected=src?.group===g&&src?.rank===r+1;return `<option value="${esc(JSON.stringify({group:g,rank:r+1}))}" ${selected?'selected':''} ${groupRankUsed(st,g,r+1,c.id,i)?'disabled':''}>${String.fromCharCode(65+g)} 组第 ${r+1} 名</option>`}).join('')).join('')}</select></label>`).join('')}</div><p class="comparator-rule">积分 → 净胜图 → 净胜回合；同分按队名、队伍编号。统计全部组内比赛。</p><p class="comparator-status ${result?.complete?'lime':'muted'}" role="status">${comparatorStatus(result,dirty)}</p>${comparatorTable(st,c,flowDraft,result,true)}</section>`;
  }).join('')}`;
}
function publicComparators(st){return (st.comparators||[]).map(c=>{const result=state.flow.comparisons.find(r=>r.stageId===st.id&&r.comparatorId===c.id);return `<section class="section"><div class="section-heading"><h3>${esc(c.name)}</h3><span class="pill">${comparatorStatus(result)}</span></div><p class="comparator-rule">积分 → 净胜图 → 净胜回合；同分按队名、队伍编号。</p>${comparatorTable(st,c,state.flow.active,result)}</section>`}).join('')}
function comparatorGraph(st,plan){return (st.comparators||[]).map(c=>`<div class="comparator-graph"><div class="comparator-origins">${c.inputs.map(src=>`<span>${src?`${String.fromCharCode(65+src.group)} 组第 ${src.rank} 名`:'待选来源'}</span>`).join('')}</div><span class="graph-arrow" aria-hidden="true">→</span><strong>${esc(c.name)}</strong><span class="graph-arrow" aria-hidden="true">→</span><div class="comparator-exits">${c.inputs.map((_,i)=>{const target=comparisonTarget(plan,st,c,i+1);return `<span>第 ${i+1} 名 → ${worldCupComparator(plan,st,c)&&i<8?'世界杯32强':target?`${esc(target.stage.name)} · 位置 ${target.index+1}`:c.outcomes[i]==='qualified'?'晋级':'淘汰'}</span>`}).join('')}</div></div>`).join('')}
