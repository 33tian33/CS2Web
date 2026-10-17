const knockoutPositions=new Map();
function knockoutBronze(st,plan){
  const defs=flowMatches({stages:[st]}),final=defs.at(-1);
  if(st.type!=='playoff'||st.teamCount<4)return null;
  const semis=new Set([final.a.matchKey,final.b.matchKey]);
  return plan.stages.find(s=>s.type==='custom'&&s.slots.length===2&&s.slots.every(src=>src.kind==='loser'&&semis.has(src.matchKey))&&s.slots[0].matchKey!==s.slots[1].matchKey)||null;
}
function publicFlowStages(plan){
  const merged=new Set(plan.stages.filter(s=>s.type==='playoff').map(s=>knockoutBronze(s,plan)?.id));
  return plan.stages.filter(s=>!merged.has(s.id));
}
function knockoutLayout(st,plan){
  const defs=flowMatches({stages:[st]}),byKey=new Map(defs.map(d=>[d.key,d])),ordered=[];
  function visit(d){for(const src of [d.a,d.b])if(byKey.has(src.matchKey))visit(byKey.get(src.matchKey));ordered.push(d)}
  visit(defs.at(-1));
  const rounds=[...new Set(defs.map(d=>d.round))];
  const width=204,step=232,height=106,nodes=[],positions=new Map();
  rounds.forEach((round,col)=>ordered.filter(d=>d.round===round).forEach((d,row)=>{
    const parents=[d.a,d.b].map(src=>positions.get(src.matchKey)).filter(Boolean);
    const y=parents.length?parents.reduce((sum,p)=>sum+p.y,0)/parents.length:18+row*122;
    const node={d,x:16+col*step,y,width,height,kind:d===defs.at(-1)?'final':'match'};
    nodes.push(node);positions.set(d.key,node);
  }));
  const bronze=knockoutBronze(st,plan);
  if(bronze){
    const d=flowMatches({stages:[bronze]})[0],final=nodes.at(-1);
    const node={d:{...d,round:'季军战'},x:final.x,y:final.y+194,width,height,kind:'bronze'};
    nodes.push(node);positions.set(d.key,node);
  }
  return {nodes,positions,rounds,width:step*(rounds.length-1)+width+32,height:Math.max(...nodes.map(n=>n.y+height))+24,step};
}
function knockoutSource(src,plan,matches){
  if(src.kind==='rank')return `${String.fromCharCode(65+src.group)}组第${src.rank===1?'一':src.rank===2?'二':src.rank}名`;
  if(src.kind==='winner'||src.kind==='loser'){
    const m=matches.get(src.matchKey);
    if(m)return `#${m.id} ${src.kind==='winner'?'胜者':'败者'}`;
  }
  return sourceName(src,plan);
}
function knockoutCard(n,plan,matches,publicView,projections){
  const m=matches.get(n.d.key),scores=m?score(m):null;
  const projected=projections.get(n.d.key),provisional=!!projected&&(!m?.team_a||!m?.team_b)&&(!m||m.status==='scheduled');
  const title=n.kind==='final'?'决赛':n.kind==='bronze'?'季军战':n.d.round;
  const tag=m&&!provisional?(publicView?'a':'button'):'article';
  const action=m&&!provisional?(publicView?`href="#/match/${m.id}"`:`type="button" onclick="editMatch(${m.id})"`):'';
  const status=provisional?'暂定对阵':m?statusLabel(m.status):'待启用';
  return `<${tag} ${action} class="knockout-card knockout-${n.kind} ${m?.status==='live'?'is-live':''}" style="left:${n.x}px;top:${n.y}px;width:${n.width}px" aria-label="${esc(`${title}${m?' #'+m.id:''} · BO${m?.bo||n.d.bo} · ${status}`)}"><div class="knockout-card-head"><span>${n.kind==='match'?(m?'#'+m.id:title):title+(m?' · #'+m.id:'')}</span><span>BO${m?.bo||n.d.bo}</span></div>${['a','b'].map((side,i)=>{
    const src=n.d[side],t=team(m?.['team_'+side]??(provisional?projected['team_'+side]:src.kind==='team'?src.teamId:null));
    const label=t?t.name:knockoutSource(src,plan,matches),won=m?.status==='finished'&&scores[i]>scores[1-i];
    const seed=provisional?projected['seed_'+side]:'';
    return `<div class="knockout-team ${won?'is-winner':''}" title="${esc(label)}"><span class="knockout-identity">${t?teamIdentity(t):`<span class="knockout-pending">${esc(label)}</span>`}</span>${seed?`<small class="knockout-seed">${esc(seed)}</small>`:''}<b>${m&&m.status!=='scheduled'?scores[i]:'—'}</b></div>`;
  }).join('')}<div class="knockout-card-foot"><span>${esc(status)}</span><span>${m?.time?esc(date(m.time)):'时间待定'}</span></div></${tag}>`;
}
function knockoutProgress(layout,matches){
  const rounds=layout.rounds.map(round=>layout.nodes.filter(n=>n.kind!=='bronze'&&n.d.round===round));
  let index=rounds.findIndex(nodes=>nodes.some(n=>matches.get(n.d.key)?.status!=='finished'));
  if(index===-1)index=rounds.length-1;
  const nodes=rounds[index],finished=nodes.filter(n=>matches.get(n.d.key)?.status==='finished').length;
  const live=nodes.find(n=>matches.get(n.d.key)?.status==='live');
  const current=live||nodes.find(n=>matches.get(n.d.key)?.status!=='finished')||nodes[0];
  const progress=Math.min(rounds.length-1,index+finished/nodes.length);
  const bronze=layout.nodes.find(n=>n.kind==='bronze');
  return {x:rounds[0][0].x+nodes[0].width/2+progress*layout.step,
    y:index===rounds.length-1&&bronze?(current.y+bronze.y+current.height)/2:current.y+current.height/2,
    fraction:progress/Math.max(1,rounds.length-1),endX:rounds.at(-1)[0].x+nodes[0].width/2,
    round:layout.rounds[index],signature:`${index}:${finished}:${live?.d.key||''}`};
}
function knockoutGraph(st,plan,publicView){
  const layout=knockoutLayout(st,plan),matches=new Map(state.matches.filter(m=>m.flow_key).map(m=>[m.flow_key,m]));
  const projections=new Map((publicView?state.flow.projections?.find(p=>p.stageId===st.id)?.matches||[]:[]).map(m=>[m.key,m]));
  const provisional=[...projections.keys()].some(key=>{const m=matches.get(key);return (!m?.team_a||!m?.team_b)&&(!m||m.status==='scheduled')});
  const focus=knockoutProgress(layout,matches),bronze=knockoutBronze(st,plan),count=st.teamCount-1+(bronze?1:0);
  const paths=layout.nodes.flatMap(n=>[n.d.a,n.d.b].map(src=>{
    const p=layout.positions.get(src.matchKey);if(!p)return '';
    const loss=src.kind==='loser',start=p.y+(loss?80:49),end=n.y+49,bend=n.x-(loss?10:20);
    return `<path class="${loss?'knockout-loss-path':'knockout-win-path'}" d="M${p.x+p.width} ${start} H${bend} V${end} H${n.x}"/>`;
  })).join('');
  return `<div class="knockout" data-knockout="${st.id}" data-progress="${focus.signature}" data-focus-fraction="${focus.fraction}" data-focus-end="${focus.endX}" data-focus-y="${focus.y}"><div class="knockout-toolbar"><div class="knockout-summary"><strong>${st.teamCount} 强</strong><span>${count} 场${bronze?' · 含季军战':''}</span></div><div class="knockout-navigation"><span>${esc(focus.round)}</span><button type="button" onclick="centerKnockout(this.closest('[data-knockout]'),true)">回到当前赛程</button></div></div>${provisional?'<p class="knockout-projection-note">按当前积分暂定 · 同分沿用积分表顺序 · 小组赛结束后确定</p>':''}<div class="knockout-viewport" tabindex="0" role="region" aria-label="${esc(st.name)}对阵图，可拖动查看" onscroll="rememberKnockoutPosition(this)"><div class="knockout-surface" style="width:${layout.width}px"><div class="knockout-board"><div class="knockout-rounds" style="grid-template-columns:repeat(${layout.rounds.length},${layout.step}px)">${layout.rounds.map((round,i)=>`<div class="${round===focus.round?'is-current':''}"><span>${String(i+1).padStart(2,'0')}</span>${round==='决赛'&&bronze?'决赛 / 季军战':esc(round)}</div>`).join('')}</div><div class="knockout-canvas" style="height:${layout.height}px"><svg preserveAspectRatio="none" viewBox="0 0 ${layout.width} ${layout.height}" aria-hidden="true">${paths}</svg>${layout.nodes.map(n=>knockoutCard(n,plan,matches,publicView,projections)).join('')}</div></div></div></div></div>`;
}
function centerKnockout(root,smooth=false){
  const el=root.querySelector('.knockout-viewport');
  el.scrollTo({left:Math.max(0,Number(root.dataset.focusEnd)-el.clientWidth/2)*Number(root.dataset.focusFraction),top:Number(root.dataset.focusY)+44-el.clientHeight/2,
    behavior:smooth&&!matchMedia('(prefers-reduced-motion: reduce)').matches?'smooth':'instant'});
  rememberKnockoutPosition(el);
}
function rememberKnockoutPosition(el){
  const root=el.closest('[data-knockout]');
  knockoutPositions.set(root.dataset.knockout,{progress:root.dataset.progress,left:el.scrollLeft,top:el.scrollTop});
}
function enableKnockoutDrag(el){
  let drag=null,suppressClick=false;
  el.addEventListener('pointerdown',e=>{
    if(e.pointerType==='touch'||e.button!==0)return;
    suppressClick=false;
    drag={id:e.pointerId,x:e.clientX,y:e.clientY,left:el.scrollLeft,top:el.scrollTop,moved:false};
  });
  el.addEventListener('pointermove',e=>{
    if(!drag||e.pointerId!==drag.id)return;
    const dx=e.clientX-drag.x,dy=e.clientY-drag.y;
    if(!drag.moved&&Math.hypot(dx,dy)<5)return;
    if(!drag.moved){el.setPointerCapture(e.pointerId);el.classList.add('is-dragging');drag.moved=true}
    e.preventDefault();
    el.scrollLeft=drag.left-dx;el.scrollTop=drag.top-dy;
  });
  const finish=()=>{if(drag?.moved)suppressClick=true;drag=null;el.classList.remove('is-dragging')};
  el.addEventListener('pointerup',finish);
  el.addEventListener('pointercancel',finish);
  el.addEventListener('lostpointercapture',finish);
  el.addEventListener('pointerleave',()=>{if(!drag?.moved)drag=null});
  el.addEventListener('dragstart',e=>e.preventDefault());
  el.addEventListener('click',e=>{if(suppressClick){e.preventDefault();e.stopPropagation();suppressClick=false}},true);
}
function restoreKnockoutPositions(){
  document.querySelectorAll('[data-knockout]').forEach(root=>{
    const el=root.querySelector('.knockout-viewport'),position=knockoutPositions.get(root.dataset.knockout);
    enableKnockoutDrag(el);
    if(position?.progress===root.dataset.progress){el.scrollLeft=position.left;el.scrollTop=position.top}
    else centerKnockout(root);
  });
}
