let draftSponsor;

function sponsorImage(sponsor, fit = sponsor.fit) {
  return `<div class="sponsor-image"><img src="${esc(sponsor.image)}" alt="${esc(sponsor.name)}" style="object-fit:${fit}" loading="lazy" width="600" height="400"></div>`;
}

function sponsorHero() {
  if (!state.sponsors.length) return '';
  return `<div class="hero-sponsors" role="group" aria-label="赛事赞助商">${state.sponsors.map(s=>sponsorImage(s,'contain')).join('')}</div>`;
}

function sponsorFooter() {
  if (!state.config.name || !state.sponsors.length) return '';
  return `<footer class="sponsor-footer" aria-labelledby="sponsor-heading"><div class="section-heading"><h2 id="sponsor-heading">赛事赞助商 <small>SPONSORS</small></h2></div><div class="sponsor-grid">${state.sponsors.map(s=>`<figure class="sponsor-card">${sponsorImage(s,'contain')}<figcaption>${esc(s.name)}</figcaption></figure>`).join('')}</div></footer>`;
}

function adminSponsors() {
  if (!state.config.name) return '<div class="empty">请先保存赛事信息，再添加赞助商。</div>';
  return `<div class="section-heading"><h2>赛事赞助商</h2><button class="primary" onclick="editSponsor()">＋ 添加赞助商</button></div><div class="admin-list">${state.sponsors.map(s=>`<div class="admin-row sponsor-admin-row"><div class="sponsor-admin-identity">${sponsorImage(s)}<div><h3>${esc(s.name)}</h3><p>${s.fit==='cover'?'居中裁切':'拉伸填满'}</p></div></div><div class="sponsor-actions"><button class="outline" onclick="editSponsor(${s.id})">编辑</button><button class="subtle" onclick="deleteSponsor(${s.id})">删除</button></div></div>`).join('')||'<div class="empty">暂无赞助商</div>'}</div>`;
}

function editSponsor(id) {
  draftSponsor = structuredClone(state.sponsors.find(s=>s.id===id)||{name:'',image:'',fit:'cover'});
  openModal(id?'编辑赞助商':'添加赞助商', `<form id="sponsor-form" onsubmit="saveSponsor(event)" oninput="updateSponsorPreview()"><div class="form-grid">${field('赞助商名称','name',draftSponsor.name,'text','maxlength="120"')}${select('图片适配方式','fit',draftSponsor.fit,[['cover','居中裁切'],['fill','拉伸填满']])}<label class="field full">赞助商图片<input class="upload" type="file" accept="image/png,image/jpeg,image/webp" aria-label="上传赞助商图片" onchange="readSponsorImage(this)"><small>PNG / JPG / WebP，最大 5MB；展示比例 3:2。</small></label></div><div class="sponsor-preview" id="sponsor-preview"></div><p class="error" id="sponsor-error" role="alert"></p><div class="form-actions"><button type="button" class="outline" onclick="$('#modal').close()">取消</button><button class="primary" type="submit">保存赞助商</button></div></form>`);
  updateSponsorPreview();
}

function updateSponsorPreview() {
  const form = $('#sponsor-form');
  draftSponsor.name = form.elements.name.value;
  draftSponsor.fit = form.elements.fit.value;
  $('#sponsor-preview').innerHTML = draftSponsor.image?sponsorImage(draftSponsor):'<div class="sponsor-image sponsor-placeholder">图片预览</div>';
}

async function readSponsorImage(input) {
  const file = input.files[0];
  if (!file) return;
  const form = input.form, error = form.querySelector('.error'), draft = draftSponsor;
  error.textContent = '';
  if (file.size>5000000 || !['image/png','image/jpeg','image/webp'].includes(file.type)) {
    error.textContent = '请选择 5MB 以内的 PNG / JPG / WebP 图片';
    input.value = '';
    return;
  }
  const button = form.querySelector('[type=submit]');
  button.disabled = true;
  input.disabled = true;
  try {
    const data = await new Promise((resolve,reject)=>{
      const reader = new FileReader();
      reader.onload = ()=>resolve(reader.result);
      reader.onerror = ()=>reject(Error('图片读取失败，请重新选择'));
      reader.readAsDataURL(file);
    });
    await new Promise((resolve,reject)=>{
      const image = new Image();
      image.onload = resolve;
      image.onerror = ()=>reject(Error('图片无法打开，请重新选择'));
      image.src = data;
    });
    if (draft!==draftSponsor) return;
    draft.image = data;
    updateSponsorPreview();
  } catch (err) {
    error.textContent = err.message;
    input.value = '';
  } finally {
    button.disabled = false;
    input.disabled = false;
  }
}

async function saveSponsor(event) {
  event.preventDefault();
  const form = event.target, button = form.querySelector('[type=submit]');
  updateSponsorPreview();
  if (!draftSponsor.image) { $('#sponsor-error').textContent='请上传赞助商图片'; return; }
  button.disabled = true;
  try {
    await api('sponsor',draftSponsor);
    $('#modal').close();
    await reload();
    toast('赞助商已保存');
  } catch (err) {
    form.querySelector('.error').textContent = err.message;
  } finally {
    button.disabled = false;
  }
}

async function deleteSponsor(id) {
  const sponsor = state.sponsors.find(s=>s.id===id);
  if (!confirm(`删除赞助商“${sponsor.name}”？`)) return;
  try {
    await api('sponsor/delete',{id});
    await reload();
    toast('赞助商已删除');
  } catch (err) { toast(err.message); }
}
