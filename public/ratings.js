let ratingStage='all';

function ratingClass(rating){
  return rating<0.9?'rating-low':rating>1.1?'rating-high':'rating-neutral';
}

function matchPlayerRatings(match,teamId,mapIndex){
  const stats=new Map(match.stats.filter(s=>s.map===mapIndex).map(s=>[s.playerId,s]));
  return players(teamId).map(player=>({player,stat:stats.get(player.id)}))
    .sort((a,b)=>(b.stat?.rating??-1)-(a.stat?.rating??-1)||a.player.id-b.player.id);
}

function ratingLeaderboards(data,stage='all'){
  const roster=new Map(data.players.map(p=>[p.id,p])),totals=new Map(),performances=[];
  for(const match of data.matches){
    for(const stat of match.stats){
      const player=roster.get(stat.playerId);
      performances.push({player,match,mapIndex:stat.map,rating:stat.rating,
        opponentId:player.team_id===match.team_a?match.team_b:match.team_a});
      if(stage!=='all'&&match.stage!==stage)continue;
      if(!totals.has(player.id))totals.set(player.id,{player,total:0,played:0});
      const row=totals.get(player.id);
      row.total+=stat.rating;
      row.played++;
    }
  }
  const averages=[...totals.values()].map(row=>({...row,rating:row.total/row.played}));
  averages.sort((a,b)=>b.rating-a.rating||b.played-a.played||a.player.id-b.player.id);
  performances.sort((a,b)=>b.rating-a.rating||a.match.id-b.match.id||a.mapIndex-b.mapIndex||a.player.id-b.player.id);
  return {averages:averages.slice(0,30),peaks:performances.slice(0,5)};
}

function ratingPlayerCell(player){
  return `<span class="rating-player">${playerAvatar(player)}<strong>${esc(player.nickname)}</strong></span>`;
}

function ratingMatchCell(row){
  const map=row.match.maps[row.mapIndex].name,mapKey=bpMapKeys[map];
  return `<a class="rating-match" href="#/match/${row.match.id}">${mapKey?`<img class="rating-map-background" src="/assets/maps/${mapKey}.webp" alt="" loading="lazy">`:''}<strong>${esc(row.match.round_name)} · vs ${esc(team(row.opponentId).name)}</strong><span>图${['一','二','三','四','五'][row.mapIndex]} · ${esc(map)}</span></a>`;
}

function ratingBoards(view='preview'){
  const rankings=ratingLeaderboards(state,ratingStage),preview=view==='preview';
  const averages=rankings.averages.slice(0,preview?3:30),peaks=rankings.peaks.slice(0,preview?3:5);
  return `${view!=='peak'?`<section class="section rating-section" id="rating-leaderboard">
    <div class="section-heading"><h2>平均 Rating 榜 <small>TOP ${preview?3:30}</small></h2>
      <div class="rating-actions"><div class="tabs" role="group" aria-label="平均 Rating 赛事阶段">${[['all','全部'],['group','小组赛'],['playoff','淘汰赛']].map(([value,label])=>`<button class="tab ${ratingStage===value?'active':''}" aria-pressed="${ratingStage===value}" onclick="switchRatingStage('${value}')">${label}</button>`).join('')}</div>${preview?'<a class="subtle" href="#/event/ratings/average">查看完整榜单 ↗</a>':''}</div>
    </div>
    <div class="table-wrap rating-average" tabindex="0" role="region" aria-label="平均 Rating 前${preview?3:30}名"><table>
      <thead><tr><th scope="col">排名</th><th scope="col">选手 ID</th><th scope="col">所属队伍</th><th scope="col">场数（图）</th><th scope="col">平均 Rating</th></tr></thead>
      <tbody>${averages.map((row,i)=>`<tr><td class="rank">${i+1}</td><td>${ratingPlayerCell(row.player)}</td><td><a href="#/team/${row.player.team_id}">${teamIdentity(team(row.player.team_id))}</a></td><td>${row.played}</td><td class="points ${ratingClass(row.rating)}">${row.rating.toFixed(2)}</td></tr>`).join('')||'<tr><td colspan="5" class="empty">暂无选手 Rating 数据</td></tr>'}</tbody>
    </table></div>
  </section>`:''}${view!=='average'?`<section class="section rating-section" id="peak-rating-leaderboard">
    <div class="section-heading"><h2>最高单图 Rating 榜 <small>TOP ${preview?3:5}</small></h2>${preview?'<a class="subtle" href="#/event/ratings/peak">查看完整榜单 ↗</a>':''}</div>
    <div class="table-wrap" tabindex="0" role="region" aria-label="最高单图 Rating 前${preview?3:5}名"><table>
      <thead><tr><th scope="col">排名</th><th scope="col">选手 ID</th><th scope="col">所属队伍</th><th scope="col">Rating</th><th scope="col">比赛 / 地图</th></tr></thead>
      <tbody>${peaks.map((row,i)=>`<tr><td class="rank">${i+1}</td><td>${ratingPlayerCell(row.player)}</td><td><a href="#/team/${row.player.team_id}">${teamIdentity(team(row.player.team_id))}</a></td><td class="points ${ratingClass(row.rating)}">${row.rating.toFixed(2)}</td><td class="rating-map-cell">${ratingMatchCell(row)}</td></tr>`).join('')||'<tr><td colspan="5" class="empty">暂无选手 Rating 数据</td></tr>'}</tbody>
    </table></div>
  </section>`:''}`;
}

function switchRatingStage(stage){
  ratingStage=stage;
  const section=$('#rating-leaderboard');
  const container=document.createElement('div');
  container.innerHTML=ratingBoards(location.hash==='#/event/ratings/average'?'average':'preview');
  section.replaceWith(container.firstElementChild);
  $('#rating-leaderboard button[aria-pressed="true"]').focus({preventScroll:true});
}

function ratingPage(view){
  if(!state.config.name){shell('<div class="empty">暂无赛事</div>');return}
  shell(`<div class="breadcrumb"><a href="#/event">赛事详情</a><span>/</span><span>${view==='peak'?'最高单图 Rating 榜':'平均 Rating 榜'}</span></div><div class="rating-detail">${ratingBoards(view)}</div>`);
}
