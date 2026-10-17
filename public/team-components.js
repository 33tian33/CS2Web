function schoolEmblem(school, corner=false){
  if(school==='外援')return '<span class="school-emblem corner external" title="外援" aria-label="外援">外</span>';
  const s=state.schools.find(s=>s.name===school);
  return s?`<span data-school="${s.id}" class="school-emblem ${corner?'corner':''}" title="${esc(s.name)}"><span class="emblem-art"><img loading="lazy" decoding="async" src="${esc(s.emblem)}" alt="${esc(s.name)}校徽"></span></span>`:'';
}
function teamLogo(t,big=false){
  return `<span class="badge ${big?'big':''}" style="--team-color:${esc(t?.color||'#82908e')}"><span class="badge-face">${t?.logo?`<img loading="lazy" decoding="async" src="${esc(t.logo)}" alt="${esc(t.name)}队标">`:esc(t?.tag||'TBD')}</span>${t?.show_school_badge?schoolEmblem(t.school,true):''}</span>`;
}
function teamIdentity(t,{big=false,short=false,stacked=false}={}){
  return `<span class="team-identity ${stacked?'stacked':''}">${teamLogo(t,big)}<span class="team-name">${esc(t?(short?t.tag:t.name):'待定队伍')}</span></span>`;
}
function playerAvatar(p,large=false){
  return `<span class="avatar ${large?'large':''}"><span class="avatar-face">${p.avatar?`<img loading="lazy" decoding="async" src="${esc(p.avatar)}" alt="${esc(p.nickname)}头像">`:esc(p.nickname.slice(0,2).toUpperCase())}</span>${schoolEmblem(p.school,true)}</span>`;
}
function playerSummary(p){
  return `<div class="roster-player">${playerAvatar(p)}<span class="player-info"><strong title="${esc(p.nickname)}">${esc(p.nickname)}</strong>${playerPosition(p)}</span></div>`;
}

function rankLabel(rank){return rank.endsWith('++')?rank[0]+' 精英':rank||'未设置'}
function perfectRankIcon(rank){
  if(!rank)return '';
  const label='完美段位：'+rankLabel(rank),base='/assets/ranks/';
  const sIcons={'普通S':'s-brass-s21','黄金S':'s-silver-1','钻石S':'s-gold-1','魔王S':'s-diamond-1'};
  if(sIcons[rank])return `<img loading="lazy" decoding="async" class="perfect-rank rank-s" src="${base+sIcons[rank]}.png" alt="${esc(label)}" title="${esc(label)}">`;
  const file=rank.replaceAll('+','1'),bg=rank.endsWith('++')?file+'_bg':'ABC_bg';
  return `<span class="perfect-rank rank-letter" role="img" aria-label="${esc(label)}" title="${esc(label)}"><img loading="lazy" decoding="async" class="rank-background" src="${base+bg}.svg" alt=""><img loading="lazy" decoding="async" class="rank-symbol" src="${base+file}.svg" alt=""></span>`;
}
function playerPosition(p){return `<span class="player-position"><span>${esc(p.position)}</span>${perfectRankIcon(p.perfect_rank)}</span>`}
