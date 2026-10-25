let flowDraft=null,flowSelected=null,flowTab='format',flowDirty=false,publicStage=null;
const worldCupThirdGroups={A:'C/E/F/H/I',B:'E/F/G/I/J',D:'B/E/F/I/J',E:'A/B/C/D/F',G:'A/E/H/I/J',I:'C/D/F/G/H',K:'D/E/I/J/L',L:'E/H/I/J/K'};
const stageTypeName=st=>st.bracket==='worldcup2026'?'2026 世界杯单败淘汰':flowTypes[st.type];
const flowTypes={group:'小组循环赛',playoff:'单败淘汰',custom:'单场对决'};
function flowMatches(plan){
  const matches=[];
  for(const st of plan.stages){
    if(st.type==='group'){
      const size=st.teamCount/st.groupCount;
      for(let g=0;g<st.groupCount;g++)for(let i=g*size;i<(g+1)*size;i++)for(let j=i+1;j<(g+1)*size;j++)matches.push({key:`${st.id}:g${g}:${i}-${j}`,stageId:st.id,round:`${String.fromCharCode(65+g)} 组`,group:g,a:st.slots[i],b:st.slots[j],bo:st.bo});
    }else{
      let entries=[...st.slots],round=1;
      while(entries.length>1){if(st.bracket==='worldcup2026'&&round>1)entries=st.roundPairs[round-2].flatMap(pair=>pair.map(i=>entries[i]));const next=[];for(let i=0;i<entries.length;i+=2){const key=`${st.id}:r${round}:${i/2}`,name=st.type==='custom'?'单场对决':entries.length===2?'决赛':entries.length===4?'半决赛':`${entries.length} 强赛`;matches.push({key,stageId:st.id,round:name,group:null,a:entries[i],b:entries[i+1],bo:st.bo});next.push({kind:'winner',matchKey:key})}entries=next;round++}
    }
  }
  return matches;
}
function sourceName(src,plan=flowDraft){
  if(!src||src.kind==='empty')return '待安排';
  if(src.kind==='team')return team(src.teamId)?.tag||'待定队伍';
  if(src.kind==='rank'){const st=plan.stages.find(s=>s.id===src.stageId);return `${st?.name||'已移除赛段'} · ${String.fromCharCode(65+src.group)}${src.rank}`}
  if(src.kind==='worldcupThird')return `${worldCupThirdGroups[src.winnerGroup]} 组第三名`;
  if(src.kind==='comparison'){const st=plan.stages.find(s=>s.id===src.stageId),c=st?.comparators?.find(c=>c.id===src.comparatorId);return `${c?.name||'已移除比较器'} · 第 ${src.rank} 名`}
  const m=flowMatches(plan).find(m=>m.key===src.matchKey),st=plan.stages.find(s=>s.id===m?.stageId);
  return `${st?.name||'已移除赛段'} · ${m?.round||''} ${Number(src.matchKey.split(':').at(-1))+1} ${src.kind==='winner'?'胜者':'败者'}`;
}
function matchSourceLabel(m,side){const def=flowMatches(state.flow.active).find(x=>x.key===m.flow_key);return def?sourceName(def[side],state.flow.active):'待定队伍'}
function planner(){
  if(!flowDraft)flowDraft=structuredClone(state.flow.draft);
  const stages=flowDraft.stages,st=stages.find(s=>s.id===flowSelected)||stages[0];flowSelected=st?.id;
  const active=JSON.stringify(flowDraft)===JSON.stringify(state.flow.active)&&stages.length;
  return `<div class="section-heading"><div><h2>赛段规划器</h2></div><span class="pill">${flowDirty?'未保存':active?'已启用':'草稿'}</span></div><div class="planner-toolbar"><div class="planner-add">${Object.entries(flowTypes).map(([type,name])=>`<button class="outline" onclick="addStage('${type}')">＋ ${name}</button>`).join('')}</div><div class="planner-buttons"><button class="outline" onclick="saveFlow('save')">保存草稿</button><button class="outline" onclick="saveFlow('check')">检查路径</button><button class="primary" onclick="saveFlow('activate')">应用赛制</button></div></div><p id="flow-message" role="status"></p>${st?`<div class="planner-workspace"><aside class="stage-rail">${stages.map((s,i)=>`<button class="stage-rail-item ${st.id===s.id?'selected':''}" onclick="flowSelected='${s.id}';render()"><span>${String(i+1).padStart(2,'0')}</span><div><strong>${esc(s.name)}</strong><small>${s.teamCount} 支队伍 · ${flowMatches({stages:[s]}).length} 场</small></div></button>`).join('')}</aside><div class="panel stage-details"><div class="stage-top"><label class="field">赛段名称<input value="${esc(st.name)}" maxlength="60" onchange="updateStage('name',this.value)"></label><div class="stage-tools"><button class="subtle" onclick="moveStage(-1)" ${stages[0]===st?'disabled':''}>上移</button><button class="subtle" onclick="moveStage(1)" ${stages.at(-1)===st?'disabled':''}>下移</button><button class="subtle" onclick="removeStage()">移除</button></div></div><div class="tabs planner-tabs">${[['format','赛制配置'],['slots','参赛与晋级来源'],...(st.type==='group'?[['comparators','跨组比较器']]:[]),['matches','对阵模块']].map(([id,name])=>`<button class="tab ${flowTab===id?'active':''}" onclick="flowTab='${id}';render()">${name}</button>`).join('')}</div>${flowTab==='format'?stageFormat(st):flowTab==='slots'?stageSlots(st):flowTab==='comparators'&&st.type==='group'?stageComparators(st):stageMatchList(st)}</div></div><section class="section"><div class="section-heading"><h2>赛程图</h2><span class="muted">${esc(st.name)}</span></div>${stageGraph(st,flowDraft)}${comparatorGraph(st,flowDraft)}</section>`:'<div class="empty">添加一个赛段，开始安排对阵与晋级。</div>'}`;
}
function addStage(type){const id='s'+crypto.randomUUID().replaceAll('-',''),n=type==='custom'?2:4;flowDraft.stages.push({id,name:flowTypes[type],type,bo:type==='group'?state.config.groupBO:state.config.playoffBO,teamCount:n,groupCount:1,advance:2,slots:Array.from({length:n},()=>({kind:'empty'}))});flowSelected=id;flowDirty=true;flowTab='format';render()}
function selectedStage(){return flowDraft.stages.find(s=>s.id===flowSelected)}
function updateStage(key,value){const st=selectedStage();st[key]=value;flowDirty=true;render()}
function resizeStage(n){const st=selectedStage();st.teamCount=n;st.slots=Array.from({length:n},(_,i)=>st.slots[i]||{kind:'empty'});flowDirty=true;render()}
function moveStage(delta){const stages=flowDraft.stages,i=stages.findIndex(s=>s.id===flowSelected);[stages[i],stages[i+delta]]=[stages[i+delta],stages[i]];flowDirty=true;render()}
function removeStage(){
  if(!confirm('从草稿移除此赛段？引用它的晋级位置将改为待安排，应用后删除其中未开始且无 BP、赛果的比赛。'))return;
  const removed=flowSelected;
  flowDraft.stages=flowDraft.stages.filter(s=>s.id!==removed);
  for(const st of flowDraft.stages)st.slots=st.slots.map(src=>
    ((src.kind==='rank'||src.kind==='comparison'||src.kind==='worldcupThird')&&src.stageId===removed)||
    ((src.kind==='winner'||src.kind==='loser')&&src.matchKey.split(':')[0]===removed)
      ?{kind:'empty'}:src);
  flowSelected=flowDraft.stages[0]?.id;
  flowDirty=true;render();
}
function stageFormat(st){return `<div class="form-grid"><label class="field">赛制<input value="${stageTypeName(st)}" readonly></label><label class="field">默认 BO<select onchange="updateStage('bo',Number(this.value))">${(st.type==='group'?[2,3,5]:[3,5]).map(n=>`<option value="${n}" ${st.bo===n?'selected':''}>BO${n}</option>`).join('')}</select></label>${st.type==='playoff'?`<label class="field">参赛位置<select ${st.bracket?'disabled':''} onchange="resizeStage(Number(this.value))">${[2,4,8,16,32,64].map(n=>`<option ${st.teamCount===n?'selected':''}>${n}</option>`).join('')}</select></label>`:`<label class="field">参赛位置<input type="number" min="2" max="64" value="${st.teamCount}" ${st.type==='custom'?'readonly':''} onchange="resizeStage(Math.max(2,Math.min(64,Number(this.value))))"></label>`}${st.type==='group'?`<label class="field">小组数量<input type="number" min="1" max="16" value="${st.groupCount}" onchange="updateStage('groupCount',Math.max(1,Math.min(16,Number(this.value))))"></label><label class="field">每组晋级<input type="number" min="1" max="16" value="${st.advance}" onchange="updateStage('advance',Number(this.value))"></label>`:''}</div><div class="stage-summary"><strong>${flowMatches({stages:[st]}).length}</strong><span>场比赛</span><span>${st.type==='group'?`每组 ${st.teamCount/st.groupCount} 队`:'胜者进入下一轮'}</span></div>`}
function sourceOptions(st){
  const opts=[[{kind:'empty'},'待安排'],...state.teams.map(t=>[{kind:'team',teamId:t.id},`${t.tag} · ${t.name}`])];
  for(const s of flowDraft.stages.slice(0,flowDraft.stages.indexOf(st))){
    if(s.type==='group'){for(let g=0;g<s.groupCount;g++)for(let rank=1;rank<=s.advance;rank++)if(!(s.comparators||[]).some(c=>c.inputs.some(src=>src?.group===g&&src?.rank===rank)))opts.push([{kind:'rank',stageId:s.id,group:g,rank},`${s.name} · ${String.fromCharCode(65+g)} 组第 ${rank} 名`])}
    for(const c of (s.comparators||[]).filter(c=>!worldCupComparator(flowDraft,s,c)))for(let rank=1;rank<=c.inputs.length;rank++){const src=comparisonSource(s,c,rank);opts.push([src,sourceName(src)])}
    if(s.type!=='group')for(const m of flowMatches({stages:[s]}))for(const kind of ['winner','loser']){const src={kind,matchKey:m.key};opts.push([src,sourceName(src)])}
  }
  return opts;
}
function stageSlots(st){if(st.bracket==='worldcup2026')return `<div class="stage-slots">${st.slots.map((src,i)=>`<label class="field">位置 ${i+1}<input readonly value="${esc(sourceName(src))}"></label>`).join('')}</div>`;const options=sourceOptions(st);return `<div class="stage-slots">${st.slots.map((src,i)=>{const value=JSON.stringify(src),opts=options.some(([s])=>JSON.stringify(s)===value)?options:[[src,sourceName(src)],...options];return `<label class="field"><span class="slot-label">${st.type==='group'?`${String.fromCharCode(65+Math.floor(i/(st.teamCount/st.groupCount)))} 组 · `:''}位置 ${String(i+1).padStart(2,'0')}</span><select aria-label="位置 ${i+1} 来源" onchange="setStageSource(${i},this.value)">${opts.map(([s,name])=>`<option value="${esc(JSON.stringify(s))}" ${JSON.stringify(s)===value?'selected':''}>${esc(name)}</option>`).join('')}</select></label>`}).join('')}</div>`}
function setStageSource(i,value){selectedStage().slots[i]=JSON.parse(value);flowDirty=true;render()}
function flowTeamIdentity(src,plan,teamId){
  const t=team(teamId??(src.kind==='team'?src.teamId:null));
  return `<span class="flow-team-label" title="${esc(sourceName(src,plan))}">${t?teamIdentity(t,{short:true}):esc(sourceName(src,plan))}</span>`;
}
function stageMatchList(st){return `<div class="stage-matches">${flowMatches({stages:[st]}).map(d=>{const m=state.matches.find(m=>m.flow_key===d.key);return `<div class="stage-match-row"><div><small>${esc(d.round)} · BO${m?.bo||d.bo}</small><div class="schedule-teams">${flowTeamIdentity(d.a,flowDraft,m?.team_a)}<span class="muted">vs</span>${flowTeamIdentity(d.b,flowDraft,m?.team_b)}</div></div>${m?`<button class="outline" onclick="editMatch(${m.id})">比赛数据</button>`:'<span class="muted">待启用</span>'}</div>`}).join('')}</div>`}
async function saveFlow(action){try{await api('flow/'+action,flowDraft);if(action==='check'){$('#flow-message').className='lime';$('#flow-message').textContent='路径检查通过';return}flowDirty=false;await reload();toast(action==='activate'?'赛制已应用，赛程已更新':'草稿已保存')}catch(e){$('#flow-message').className='error';$('#flow-message').textContent=e.message}}
function stageGraph(st,plan,publicView=false){
  if(st.type==='playoff')return knockoutGraph(st,plan,publicView);
  const defs=flowMatches({stages:[st]});
  const rounds=[...new Set(defs.map(d=>d.round))],nodes=[],positions=new Map();
  rounds.forEach((round,col)=>{const ms=defs.filter(d=>d.round===round);ms.forEach((d,row)=>{const parents=[d.a,d.b].map(s=>positions.get(s?.matchKey)).filter(Boolean);const y=st.type==='playoff'&&parents.length?parents.reduce((sum,p)=>sum+p.y,0)/parents.length:row*110+46;const node={d,x:col*260+16,y};nodes.push(node);positions.set(d.key,node)})});
  const width=rounds.length*260+10,height=Math.max(165,...nodes.map(n=>n.y+110));
  return `<div class="flow-graph-scroll"><div class="flow-graph" style="width:${width}px;height:${height}px"><svg viewBox="0 0 ${width} ${height}" aria-hidden="true">${nodes.flatMap(n=>[n.d.a,n.d.b].map(src=>{const p=positions.get(src?.matchKey);if(!p)return '';return `<path d="M ${p.x+224} ${p.y+40} H ${p.x+242} V ${n.y+40} H ${n.x}"/>`})).join('')}</svg>${rounds.map((r,i)=>`<div class="flow-column-title" style="left:${i*260+16}px">${esc(r)}</div>`).join('')}${nodes.map(n=>{const m=state.matches.find(m=>m.flow_key===n.d.key),sc=m?displayScore(m):null;return `<${publicView&&m?'a':'div'} ${publicView&&m?`href="#/match/${m.id}"`:''} class="flow-node" style="left:${n.x}px;top:${n.y}px">${['a','b'].map((side,i)=>`<div>${flowTeamIdentity(n.d[side],plan,m?.['team_'+side])}<b>${m&&m.status!=='scheduled'?sc[i]:'—'}</b></div>`).join('')}</${publicView&&m?'a':'div'}>`}).join('')}</div></div>`;
}
let publicGroupsFinished=false;
function allGroupMatchesFinished(){
  const matches=state.matches.filter(m=>m.stage==='group');
  return matches.length>0&&matches.every(m=>m.status==='finished');
}
function flowPublic(){
  const plan=state.flow.active,visible=publicFlowStages(plan),finished=allGroupMatchesFinished();
  if(finished&&!publicGroupsFinished){
    const knockout=visible.find(s=>s.type==='playoff'&&s.teamCount===32);
    if(knockout)publicStage=knockout.id;
    showKnockoutPrediction=false;
  }
  publicGroupsFinished=finished;
  const st=visible.find(s=>s.id===publicStage)||visible[0];if(!st)return '';
  return `<section class="section"><div class="section-heading"><h2>赛段与晋级 <small>TOURNAMENT FLOW</small></h2>${st.type==='group'?state.flow.projections.filter(p=>plan.stages.find(s=>s.id===p.stageId).groupStageId===st.id).map(p=>`<div class="admin-actions">${finished?'':`<button class="outline" onclick="openKnockoutPrediction('${p.stageId}')">淘汰赛预测</button>`}<a class="outline" href="#/event/simulation">模拟赛果</a></div>`).join(''):''}</div><div class="stage-public-tabs">${visible.map((s,i)=>`<button class="tab ${s.id===st.id?'active':''}" onclick="publicStage='${s.id}';render()">${String(i+1).padStart(2,'0')} ${esc(s.name)}</button>`).join('')}</div><div class="section-heading"><h3>${esc(st.name)}</h3><span class="pill">${stageTypeName(st)} · 默认 BO${st.bo}</span></div>${st.type==='group'?`<div class="two-col">${state.flow.tables.filter(t=>t.stageId===st.id).map(g=>`<div><div class="group-title"><strong>${String.fromCharCode(65+g.group)} 组</strong><span class="muted">前 ${st.advance} 名晋级</span></div><div class="table-wrap group-standings"><table><thead><tr><th>#</th><th>队伍</th><th>胜 / 平 / 负</th><th>净回合</th><th>积分</th></tr></thead><tbody>${g.rows.map((r,i)=>`<tr class="rank-${i<st.advance?'green':i===st.advance?'yellow':'red'} confirmed-${r.qualification||'pending'}"><td>${i+1}</td><td><a class="inline-team" href="#/team/${r.teamId}">${teamIdentity(team(r.teamId))}</a></td><td>${r.w} / ${r.d} / ${r.l}</td><td>${r.rd}</td><td>${r.pts}</td></tr>`).join('')||'<tr><td colspan="5">等待晋级队伍</td></tr>'}</tbody></table></div>${g.complete&&g.rows.some(r=>r.tied)?'<p class="error">存在完全同分，请裁定后再推进晋级。</p>':''}</div>`).join('')}</div>`:''}${publicComparators(st)}${st.type!=='group'?stageGraph(st,plan,true):''}</section>`;
}
