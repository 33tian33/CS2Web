function statNumberParts(digits, count) {
  if (!count) return digits ? [] : [[]];
  const parts = [];
  for (let size = 1; size <= 3 && size <= digits.length - count + 1; size++) {
    const token = digits.slice(0, size), value = Number(token);
    if (value > 200 || (size > 1 && token[0] === '0')) continue;
    for (const rest of statNumberParts(digits.slice(size), count - 1)) parts.push([value, ...rest]);
  }
  return parts;
}

function parseCopiedStats(text) {
  const lines = text.trim().split(/\r?\n/).map(line => line.trim()).filter(Boolean);
  const records = [];
  for (let i = 0; i < lines.length; i++) {
    if (/^UID\s*[/／]/i.test(lines[i])) continue;
    let nickname, data;
    const inline = lines[i].match(/^(.*?)\s*(土匪|警察)(?=\s*\d)/);
    if (inline && inline[1].trim()) {
      nickname = inline[1].trim(); data = lines[i].slice(inline[1].length).trim();
    } else {
      nickname = lines[i]; data = lines[++i] || '';
    }
    const row = data.match(/^(土匪|警察)\s*(.*?)%\s*(\d+(?:\.\d+)?)%\s*(\d+\.\d{2})\s*(\d+\.\d{2})\s*\d[\d\s]*ms\s*[\d\s]+$/);
    if (!row) throw Error(`${nickname}：无法识别战绩，请复制完整数据行`);
    const columns = row[2].trim().split(/\s+/);
    let candidates;
    if (columns.length === 6 && /^\d+$/.test(columns[0])) {
      candidates = [columns.slice(1, 5).map(Number)];
    } else {
      // This scoreboard's plain-text copy joins a 13-digit team ID and integer columns.
      const compact = row[2].replace(/\s/g, '').match(/^\d{13}(\d{4,12})100$/);
      if (!compact) throw Error(`${nickname}：数字列无法拆分，请复制带空格或制表符的完整数据行`);
      const headshot = Number(row[3]);
      candidates = statNumberParts(compact[1], 4).filter(([kills, , , first]) => {
        if (first > kills) return false;
        if (!kills) return headshot === 0;
        return Math.abs(Math.round(kills * headshot / 100) / kills * 100 - headshot) <= 0.0051;
      });
    }
    candidates = candidates.filter(values => values.every(n => Number.isInteger(n) && n >= 0 && n <= 200));
    candidates.sort((a, b) => a[2] - b[2] || a[3] - b[3] || a[0] - b[0]);
    const unique = [...new Map(candidates.map(([kills, deaths, assists]) => {
      const value = {kills, deaths, assists};
      return [JSON.stringify(value), value];
    })).values()];
    if (!unique.length || Number(row[5]) > 10) throw Error(`${nickname}：K/D/A 或 Rating 格式不正确`);
    records.push({nickname, candidates: unique, rating: Number(row[5])});
  }
  if (!records.length) throw Error('请先粘贴战绩');
  return records;
}

function statsImportBox(map) {
  return `<details class="stats-import" data-map="${map}"><summary>粘贴战绩</summary><label class="field">战绩文本<textarea rows="4" aria-label="第 ${map + 1} 张地图战绩文本" placeholder="粘贴选手 ID 和完整战绩行" oninput="clearStatsImport(this)"></textarea></label><button type="button" class="outline" onclick="previewStatsImport(this)">识别战绩</button><p class="error" role="alert"></p><div class="stats-import-preview"></div></details>`;
}

function clearStatsImport(input) {
  const box = input.closest('.stats-import');
  box.querySelector('.stats-import-preview').innerHTML = '';
  box.querySelector('.error').textContent = '';
  delete box.records;
}

function previewStatsImport(button) {
  const box = button.closest('.stats-import');
  clearStatsImport(button);
  try {
    const records = parseCopiedStats(box.querySelector('textarea').value);
    const roster = [...document.querySelectorAll(`.stats-row[data-map="${box.dataset.map}"]`)].map(row => state.players.find(p => p.id === Number(row.dataset.player)));
    const normalize = name => name.normalize('NFKC').trim().replace(/\s+/g, ' ').toLowerCase();
    box.records = records;
    box.querySelector('.stats-import-preview').innerHTML = `<div class="table-wrap"><table><thead><tr><th>复制的 ID</th><th>本场选手</th><th>K / D / A</th><th>Rating</th></tr></thead><tbody>${records.map(record => {
      const matches = roster.filter(p => normalize(p.nickname) === normalize(record.nickname));
      const selected = matches.length === 1 ? matches[0].id : null;
      return `<tr class="stats-import-row"><td>${esc(record.nickname)}</td><td><select class="import-player" aria-label="${esc(record.nickname)} 匹配选手"><option value="">选择本场选手</option>${roster.map(p => `<option value="${p.id}" ${p.id === selected ? 'selected' : ''}>${esc(team(p.team_id).tag)} · ${esc(p.nickname)}</option>`).join('')}</select></td><td><select class="import-kda" aria-label="${esc(record.nickname)} K/D/A">${record.candidates.map((s, i) => `<option value="${i}">${s.kills} / ${s.deaths} / ${s.assists}</option>`).join('')}</select>${record.candidates.length > 1 ? '<span class="import-ambiguity">多种拆分，请核对</span>' : ''}</td><td>${record.rating.toFixed(2)}</td></tr>`;
    }).join('')}</tbody></table></div><button type="button" class="primary" onclick="applyStatsImport(this)">填入当前地图</button>`;
  } catch (error) {
    box.querySelector('.error').textContent = error.message;
  }
}

function applyStatsImport(button) {
  const box = button.closest('.stats-import'), selected = new Set(), updates = [];
  const error = box.querySelector('.error');
  error.textContent = '';
  for (const [i, row] of [...box.querySelectorAll('.stats-import-row')].entries()) {
    const record = box.records[i], playerId = Number(row.querySelector('.import-player').value);
    if (!playerId || selected.has(playerId)) {
      error.textContent = `${record.nickname}：${playerId ? '选手重复，请重新选择' : '请选择本场选手'}`;
      return;
    }
    selected.add(playerId);
    updates.push({playerId, ...record.candidates[Number(row.querySelector('.import-kda').value)], rating: record.rating});
  }
  for (const update of updates) {
    const row = document.querySelector(`.stats-row[data-map="${box.dataset.map}"][data-player="${update.playerId}"]`);
    for (const key of ['kills', 'deaths', 'assists', 'rating']) row.querySelector(`[data-key="${key}"]`).value = update[key];
  }
  box.open = false;
  toast(`已填入 ${updates.length} 名选手，请保存比赛`);
}
