function beijingDay(now=new Date()){
  return new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(now);
}
function spotlightMatches(matches,today=beijingDay()){
  const eligible=matches.filter(m=>m.team_a&&m.team_b);
  const upcoming=eligible.filter(m=>m.status!=='finished'&&m.time.slice(0,10)===today).sort((a,b)=>(b.status==='live')-(a.status==='live')||a.time.localeCompare(b.time));
  const results=eligible.filter(m=>m.status==='finished').sort((a,b)=>(b.finished_at||b.time).localeCompare(a.finished_at||a.time)||b.id-a.id);
  const shown=[];
  for(let i=0;i<3;i++){if(upcoming[i])shown.push(upcoming[i]);if(results[i])shown.push(results[i]);}
  return shown;
}
function resultMaps(m){return m.maps.map(x=>`<div class="result-map">${bpMapKeys[x.name]?`<img src="/assets/maps/${bpMapKeys[x.name]}.webp" alt="" loading="lazy">`:''}<span>${esc(x.name)}</span><strong><b class="${x.scoreA>x.scoreB?'map-winner':''}">${x.scoreA}</b><i>:</i><b class="${x.scoreB>x.scoreA?'map-winner':''}">${x.scoreB}</b></strong></div>`).join('');}
function mvpSummary(m,pid=m.mvp_player_id){
  const rows=m.stats.filter(s=>s.playerId===pid);
  if(!rows.length)return null;
  return {rating:rows.reduce((n,s)=>n+s.rating,0)/rows.length,kills:rows.reduce((n,s)=>n+s.kills,0),deaths:rows.reduce((n,s)=>n+s.deaths,0),maps:rows.length};
}
let spotlightIndex=0,spotlightKey='',spotlightTimer,spotlightPaused=false;
function spotlightSlides(matches){return matches.flatMap(m=>[{key:`match-${m.id}`,match:m,type:'match'},...(m.status==='finished'&&m.mvp_player_id?[{key:`mvp-${m.id}`,match:m,type:'mvp'}]:[])]);}
function spotlightCard(m){
  const finished=m.status==='finished',live=m.status==='live',a=team(m.team_a),b=team(m.team_b),sc=displayScore(m);
  const backdrop=finished?`<div class="spotlight-backdrop" aria-hidden="true">${m.maps.map(x=>`<div>${bpMapKeys[x.name]?`<img src="/assets/maps/${bpMapKeys[x.name]}.webp" alt="">`:''}</div>`).join('')}</div>`:'';
  return `<a class="spotlight-card ${finished?'is-result':'is-upcoming'}" href="#/match/${m.id}">${backdrop}<div class="spotlight-top"><span class="spotlight-status">${finished?'已完赛':live?'进行中':'今日预告'}</span><span>${esc(m.round_name)} · BO${m.bo}</span><time>${esc(date(m.time))}</time></div><div class="spotlight-versus"><div class="spotlight-team">${teamLogo(a,true)}<strong>${esc(a.name)}</strong><small>${esc(a.school)}</small></div><div class="spotlight-score"><strong>${finished||live?`${sc[0]}<i>:</i>${sc[1]}`:esc(m.time.slice(11,16))}</strong><span>${finished?'完赛':live?'LIVE':'北京时间'}</span></div><div class="spotlight-team">${teamLogo(b,true)}<strong>${esc(b.name)}</strong><small>${esc(b.school)}</small></div></div>${finished?`<div class="spotlight-map-scores">${m.maps.map(x=>`<div><span>${esc(x.name)}</span><strong><b class="${x.scoreA>x.scoreB?'map-winner':''}">${x.scoreA}</b><i>:</i><b class="${x.scoreB>x.scoreA?'map-winner':''}">${x.scoreB}</b></strong></div>`).join('')}</div>`:''}<div class="spotlight-bottom"><span>${finished?'查看赛果':'查看对阵'} ↗</span></div></a>`;
}
function homeSpotlight(){
  const slides=spotlightSlides(spotlightMatches(state.matches.filter(m=>state.config.thirdPlace||m.round_name!=='季军赛')));
  const found=slides.findIndex(s=>s.key===spotlightKey);spotlightIndex=found<0?0:found;spotlightKey=slides[spotlightIndex]?.key||'';
  return `<section class="section spotlight-section"><div class="section-heading"><h2>赛场速递 <small>MATCH CENTER</small></h2><a class="subtle" href="#/event">全部赛程 ↗</a></div>${slides.length?`<div class="spotlight-carousel" aria-label="赛场速递" aria-roledescription="轮播"><div class="spotlight-window"><div class="spotlight-track" style="transform:translateX(-${spotlightIndex*100}%)">${slides.map((s,i)=>`<div class="spotlight-slide" data-key="${s.key}" role="group" aria-label="${i+1} / ${slides.length}" ${i!==spotlightIndex?'inert aria-hidden="true"':''}>${s.type==='mvp'?`<a class="spotlight-mvp-slide" href="#/match/${s.match.id}">${mvpBanner(s.match)}<div class="mvp-match-caption">${esc(team(s.match.team_a).name)} <b>${displayScore(s.match).join(' : ')}</b> ${esc(team(s.match.team_b).name)}<span>查看赛果 ↗</span></div></a>`:spotlightCard(s.match)}</div>`).join('')}</div></div>${slides.length>1?`<div class="spotlight-controls"><button type="button" aria-label="上一张" onclick="moveSpotlight(-1)">←</button><div class="spotlight-dots">${slides.map((s,i)=>`<button type="button" aria-label="第 ${i+1} 张${s.type==='mvp'?' MVP':''}" aria-current="${i===spotlightIndex}" onclick="showSpotlight(${i})"></button>`).join('')}</div><span class="spotlight-count">${spotlightIndex+1} / ${slides.length}</span><button type="button" class="spotlight-pause" aria-label="${spotlightPaused?'播放轮播':'暂停轮播'}" onclick="toggleSpotlight()">${spotlightPaused?'▶':'Ⅱ'}</button><button type="button" aria-label="下一张" onclick="moveSpotlight(1)">→</button></div>`:''}</div>`:'<div class="empty">今日暂无赛程与近期赛果</div>'}</section>`;
}
function showSpotlight(index){
  const root=document.querySelector('.spotlight-carousel');if(!root)return;
  const slides=[...root.querySelectorAll('.spotlight-slide')];spotlightIndex=(index+slides.length)%slides.length;spotlightKey=slides[spotlightIndex].dataset.key;
  root.querySelector('.spotlight-track').style.transform=`translateX(-${spotlightIndex*100}%)`;
  slides.forEach((s,i)=>{s.inert=i!==spotlightIndex;s.setAttribute('aria-hidden',String(i!==spotlightIndex));});
  root.querySelectorAll('.spotlight-dots button').forEach((b,i)=>b.setAttribute('aria-current',String(i===spotlightIndex)));
  const count=root.querySelector('.spotlight-count');if(count)count.textContent=`${spotlightIndex+1} / ${slides.length}`;
  mountSpotlight();
}
function moveSpotlight(delta){showSpotlight(spotlightIndex+delta);}
function toggleSpotlight(){spotlightPaused=!spotlightPaused;const b=document.querySelector('.spotlight-pause');b.textContent=spotlightPaused?'▶':'Ⅱ';b.setAttribute('aria-label',spotlightPaused?'播放轮播':'暂停轮播');mountSpotlight();}
function mountSpotlight(){
  clearInterval(spotlightTimer);
  const root=document.querySelector('.spotlight-carousel');if(!root||root.querySelectorAll('.spotlight-slide').length<2)return;
  spotlightTimer=setInterval(()=>{if(!spotlightPaused&&!document.hidden&&!root.matches(':hover')&&!root.contains(document.activeElement))moveSpotlight(1);},6000);
}
function mvpBanner(m,preview=false){
  const p=state.players.find(p=>p.id===m.mvp_player_id);if(!p||(!preview&&m.status!=='finished'))return '';
  const t=team(p.team_id),opponent=team(p.team_id===m.team_a?m.team_b:m.team_a),s=mvpSummary(m);
  return `<section class="mvp-banner" aria-label="本场 MVP"><div class="mvp-poster-heading"><span>${esc(state.config.name)}</span><span class="mvp-opponent"><span>VS</span>${teamLogo(opponent)}<span class="mvp-opponent-name">${esc(opponent.name)}</span><span class="mvp-opponent-round">${esc(m.round_name)} · BO${m.bo}</span></span></div><div class="mvp-portrait"><span class="mvp-watermark" aria-hidden="true"><span>MVP</span><span>MVP</span><span>MVP</span><span>MVP</span><span>MVP</span></span>${playerAvatar(p,true)}</div><div class="mvp-content"><span class="mvp-kicker">MOST VALUABLE PLAYER</span><div class="mvp-award">MVP</div><h2>${esc(p.nickname)}</h2><div class="mvp-team">${teamLogo(t)}<span>${esc(t.name)} · ${esc(p.school)}</span></div>${s?`<div class="mvp-numbers"><div><strong>${s.rating.toFixed(2)}</strong><span>Rating</span></div><div><strong>${s.kills}<i> / </i>${s.deaths}</strong><span>K / D</span></div><div><strong>${s.kills-s.deaths>0?'+':''}${s.kills-s.deaths}</strong><span>净击杀</span></div></div><small class="mvp-scope">${s.maps} MAPS · ${esc(date(m.time))}</small>`:''}</div></section>`;
}
function mvpEditor(m){const candidates=state.players.filter(p=>[m.team_a,m.team_b].includes(p.team_id)).sort((a,b)=>(mvpSummary(m,b.id)?.rating??-1)-(mvpSummary(m,a.id)?.rating??-1));return `<div class="edit-section" id="mvp-editor"><h3>本场 MVP</h3><label class="field">最佳选手<select name="mvp_player_id" onchange="previewMvp()"><option value="">不展示 MVP</option>${candidates.map(p=>{const s=mvpSummary(m,p.id);return `<option value="${p.id}" ${p.id===m.mvp_player_id?'selected':''}>${esc(team(p.team_id).name)} · ${esc(p.nickname)}${s?` · ${s.rating.toFixed(2)} Rating · ${s.kills}/${s.deaths}`:''}</option>`}).join('')}</select></label><div id="mvp-preview">${mvpBanner(m,true)}</div></div>`;}
function previewMvp(){readDraft();$('#mvp-preview').innerHTML=mvpBanner(draftMatch,true);}
function refreshMvpEditor(){readDraft();if(!state.players.some(p=>p.id===draftMatch.mvp_player_id&&[draftMatch.team_a,draftMatch.team_b].includes(p.team_id)))draftMatch.mvp_player_id=null;$('#mvp-editor').outerHTML=mvpEditor(draftMatch);$('#mvp-editor').hidden=!!draftMatch.forfeit_winner;}
