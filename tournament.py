"""Stage templates, advancement and BP rules for the local tournament."""
import json
import hashlib
import worldcup
import qualification
from itertools import combinations

MAPS = ['Mirage', 'Inferno', 'Dust II', 'Ancient', 'Nuke', 'Anubis', 'Vertigo', 'Train', 'Overpass', 'Cache']
BP_ACTIONS = {
    2: [('A','Ban'),('B','Ban'),('B','Ban'),('A','Ban'),('A','Pick'),('B','Pick'),(None,'Unused')],
    3: [('A','Ban'),('B','Ban'),('A','Pick'),('B','Pick'),('A','Ban'),('B','Ban'),(None,'Decider')],
    5: [('A','Ban'),('B','Ban'),('A','Pick'),('B','Pick'),('A','Pick'),('B','Pick'),(None,'Decider')],
}

def migrate(con):
    con.execute('CREATE TABLE IF NOT EXISTS flow (id INTEGER PRIMARY KEY CHECK(id=1), draft TEXT NOT NULL, active TEXT NOT NULL)')
    con.execute("INSERT OR IGNORE INTO flow VALUES (1, '{\"stages\":[]}', '{\"stages\":[]}')")
    columns = {r[1] for r in con.execute('PRAGMA table_info(matches)')}
    if 'flow_key' not in columns:
        con.execute('ALTER TABLE matches ADD COLUMN flow_key TEXT')
        con.execute('CREATE UNIQUE INDEX matches_flow_key ON matches(flow_key)')
        con.execute("ALTER TABLE matches ADD COLUMN bp_config TEXT NOT NULL DEFAULT '{}'")
    if 'mvp_player_id' not in columns:
        con.execute('ALTER TABLE matches ADD COLUMN mvp_player_id INTEGER REFERENCES players(id) ON DELETE SET NULL')
    if 'finished_at' not in columns:
        con.execute("ALTER TABLE matches ADD COLUMN finished_at TEXT NOT NULL DEFAULT ''")
    if 'replay_url' not in columns:
        con.execute("ALTER TABLE matches ADD COLUMN replay_url TEXT NOT NULL DEFAULT ''")
    if 'forfeit_winner' not in columns:
        con.execute("ALTER TABLE matches ADD COLUMN forfeit_winner TEXT NOT NULL DEFAULT '' CHECK(forfeit_winner IN ('','A','B'))")

def template(m, first='A'):
    ids = {'A': m['team_a'], 'B': m['team_b']}
    if first == 'B': ids = {'A': m['team_b'], 'B': m['team_a']}
    return [dict(teamId=ids.get(side), action=action, map='', sidePicker=None, startSide='') for side, action in BP_ACTIONS[m['bo']]]

def validate_bp(m, steps, config):
    if config.get('first') not in ['A', 'B']: raise ValueError('请选择 BP 先手方')
    pool = config.get('pool', [])
    if len(pool) != 7 or len(set(pool)) != 7 or any(x not in MAPS for x in pool): raise ValueError('地图池需要选择 7 张不同地图')
    if not m['team_a'] or not m['team_b']: raise ValueError('请先确定对阵双方')
    expected = template(m, config['first'])
    if len(steps) != 7: raise ValueError('BP 需要保留 7 个步骤')
    used = set()
    for step, exp in zip(steps, expected):
        if (step.get('teamId'), step.get('action')) != (exp['teamId'], exp['action']): raise ValueError('BP 顺序与比赛制式不符')
        name = step.get('map')
        if name and (name not in pool or name in used): raise ValueError('BP 地图不在地图池中或重复选择')
        if not isinstance(name, str): raise ValueError('BP 地图无效')
        if name: used.add(name)
        picker, side = step.get('sidePicker'), step.get('startSide', '')
        if picker is not None or side:
            if not name or step['action'] not in ['Pick','Decider'] or picker not in [m['team_a'],m['team_b']] or side not in ['CT','T']: raise ValueError('请完整填写选边队伍和 CT/T')
    played = [s['map'] for s in steps if s['action'] in ['Pick','Decider']]
    for i, result in enumerate(m['maps']):
        if result['name'] != played[i]: raise ValueError('BP 与已有地图赛果不一致，请先处理对应赛果和选手数据')
    return steps

def matches_of(plan):
    result = []
    for st in plan['stages']:
        n, sid = st['teamCount'], st['id']
        if st['type'] == 'group':
            size = n // st['groupCount']
            for g in range(st['groupCount']):
                slots = list(range(g*size, (g+1)*size))
                for i, j in combinations(slots, 2):
                    result.append(dict(key=f'{sid}:g{g}:{i}-{j}', stageId=sid, group=g, round=f'{chr(65+g)} 组', bo=st['bo'], a=st['slots'][i], b=st['slots'][j]))
        else:
            entries = st['slots'][:]
            rnd = 1
            while len(entries)>1:
                if st.get('bracket') == 'worldcup2026' and rnd > 1:
                    entries = [entries[i] for pair in st['roundPairs'][rnd-2] for i in pair]
                following = []
                for i in range(0,len(entries),2):
                    key = f'{sid}:r{rnd}:{i//2}'
                    name = '单场对决' if st['type']=='custom' else ('决赛' if len(entries)==2 else '半决赛' if len(entries)==4 else f'{len(entries)} 强赛')
                    result.append(dict(key=key,stageId=sid,group=None,round=name,bo=st['bo'],a=entries[i],b=entries[i+1]))
                    following.append(dict(kind='winner',matchKey=key))
                entries=following; rnd+=1
    return result

def validate_plan(plan, team_ids, activate=False):
    stages = plan.get('stages')
    if not isinstance(stages,list) or len(stages)>16: raise ValueError('最多配置 16 个赛段')
    previous, keys, sources = {}, set(), set()
    for st in stages:
        sid = st.get('id')
        if not isinstance(sid,str) or not sid.isalnum() or sid in previous: raise ValueError('赛段编号无效或重复')
        if not isinstance(st.get('name'),str) or not st['name'].strip() or len(st['name'])>60: raise ValueError('请填写赛段名称')
        kind,n,bo=st.get('type'),st.get('teamCount'),st.get('bo')
        if kind not in ['group','playoff','custom'] or type(n)!=int or not 2<=n<=64: raise ValueError('赛段类型或队伍数量无效')
        if bo not in ([2,3,5] if kind=='group' else [3,5]): raise ValueError('赛段 BO 无效')
        if kind=='custom' and n!=2: raise ValueError('单场对决需要两个参赛位置')
        if kind=='playoff' and n not in [2,4,8,16,32,64]: raise ValueError('单败队伍数请选择 2、4、8、16、32 或 64')
        if kind=='group':
            g=st.get('groupCount')
            if type(g)!=int or not 1<=g<=16 or n%g or not 2<=n//g<=16: raise ValueError('小组需等额分组，每组 2–16 队')
            if type(st.get('advance'))!=int or not 1<=st['advance']<=n//g: raise ValueError('晋级人数超出小组容量')
        if len(st.get('slots',[]))!=n: raise ValueError('参赛位置数量与配置不符')
        if st.get('bracket') == 'worldcup2026': worldcup.validate_stage(st, previous)
        local=set()
        for src in st['slots']:
            typ=src.get('kind')
            token=json.dumps({k:src[k] for k in ('kind','stageId','group','rank')},sort_keys=True) if typ=='rank' else json.dumps(src,sort_keys=True)
            if typ=='empty':
                if activate: raise ValueError(f'{st["name"]}还有未安排的参赛位置')
                continue
            if token in local: raise ValueError('同一赛段不可重复安排队伍或晋级来源')
            local.add(token)
            if typ=='team':
                if src.get('teamId') not in team_ids: raise ValueError('参赛队伍不存在')
            elif typ=='rank':
                source=previous.get(src.get('stageId'))
                if not source or source['type']!='group' or type(src.get('group'))!=int or not 0<=src['group']<source['groupCount'] or type(src.get('rank'))!=int or not 1<=src['rank']<=source['advance']: raise ValueError('小组晋级来源无效，请先调整赛段顺序或晋级名额')
            elif typ=='comparison':
                source=previous.get(src.get('stageId'))
                comparator=next((c for c in source.get('comparators',[]) if c['id']==src.get('comparatorId')),None) if source else None
                if not comparator or type(src.get('rank'))!=int or not 1<=src['rank']<=len(comparator['inputs']): raise ValueError('跨组比较器排名来源无效')
                if any(s.get('bracket')=='worldcup2026' and s.get('groupStageId')==src['stageId'] and s.get('comparatorId')==src['comparatorId'] for s in stages):
                    raise ValueError('世界杯第三名由官方组合表分配，不能再按比较名次连接')
            elif typ=='worldcupThird':
                if st.get('bracket')!='worldcup2026': raise ValueError('世界杯第三名来源只能用于世界杯淘汰赛')
            elif typ in ['winner','loser']:
                if src.get('matchKey') not in keys: raise ValueError('胜败来源必须指向前面的赛段')
                source_id=src['matchKey'].split(':')[0]
                if previous[source_id]['type']=='group': raise ValueError('循环赛请使用小组名次晋级')
            else: raise ValueError('参赛来源无效')
            if typ!='team':
                if token in sources: raise ValueError('同一个晋级来源只能分配一次')
                sources.add(token)
        comparators=st.get('comparators',[])
        if not isinstance(comparators,list) or (comparators and kind!='group'): raise ValueError('跨组比较器只能配置在小组赛中')
        comparator_ids=set()
        for c in comparators:
            cid=c.get('id')
            if not isinstance(cid,str) or not cid.isalnum() or cid in comparator_ids: raise ValueError('比较器编号无效或重复')
            comparator_ids.add(cid)
            if not isinstance(c.get('name'),str) or not c['name'].strip() or len(c['name'])>60: raise ValueError('请填写比较器名称')
            inputs=c.get('inputs')
            if not isinstance(inputs,list) or not 2<=len(inputs)<=n: raise ValueError('比较器需设置 2 至参赛队伍数个来源')
            if len(c.get('outcomes',[]))!=len(inputs) or any(x not in ['qualified','eliminated'] for x in c['outcomes']): raise ValueError('比较器排名去向无效')
            for src in inputs:
                if src is None:
                    if activate: raise ValueError(f'{c["name"]}还有未选择的小组名次')
                    continue
                if not isinstance(src,dict) or type(src.get('group'))!=int or not 0<=src['group']<st['groupCount'] or type(src.get('rank'))!=int or not 1<=src['rank']<=n//st['groupCount']: raise ValueError('比较器的小组名次超出范围')
                token=json.dumps(dict(kind='rank',stageId=sid,group=src['group'],rank=src['rank']),sort_keys=True)
                if token in sources: raise ValueError('同一个小组名次只能进入一个比较器或晋级位置')
                sources.add(token)
        previous[sid]=st
        keys.update(x['key'] for x in matches_of({'stages':[st]}))
    return plan

def load_matches(con):
    result=[]
    for r in con.execute('SELECT * FROM matches ORDER BY id'):
        m=dict(r)
        for k in ['maps','stats','bp','bp_config']: m[k]=json.loads(m[k])
        result.append(m)
    return result

def score(m):
    return (sum(x['scoreA']>x['scoreB'] for x in m['maps']),sum(x['scoreB']>x['scoreA'] for x in m['maps']))

def table(team_ids, matches, cfg, results=None):
    results = results or {}
    match_score = lambda m: (results[m['id']]['scoreA'], results[m['id']]['scoreB']) if m['id'] in results else score(m)
    rows={i:dict(teamId=i,played=0,w=0,d=0,l=0,mw=0,ml=0,rd=0,pts=0,h2h=0) for i in team_ids if i is not None}
    for m in matches:
        if m['status']!='finished' and m['id'] not in results: continue
        a,b=rows[m['team_a']],rows[m['team_b']];x,y=match_score(m)
        rd=results[m['id']]['roundDiff'] if m['id'] in results else sum(v['scoreA']-v['scoreB'] for v in m['maps'])
        for row,mine,other,diff in [(a,x,y,rd),(b,y,x,-rd)]:
            row['played']+=1;row['mw']+=mine;row['ml']+=other;row['rd']+=diff
            outcome='w' if mine>other else 'l' if mine<other else 'd'
            row[outcome]+=1;row['pts']+=cfg[{'w':'winPoints','l':'lossPoints','d':'drawPoints'}[outcome]]
    for m in matches:
        if m['status']!='finished' and m['id'] not in results: continue
        a,b=rows[m['team_a']],rows[m['team_b']]
        if a['pts']!=b['pts']: continue
        x,y=match_score(m)
        for row,mine,other in [(a,x,y),(b,y,x)]: row['h2h']+=cfg['winPoints' if mine>other else 'lossPoints' if mine<other else 'drawPoints']
    def key(r): return (r['pts'], *[r['mw']-r['ml'] if k=='map' else r['rd'] if k=='round' else r['h2h'] for k in cfg['tieBreak'].split(',')])
    ordered=sorted(rows.values(),key=lambda r:tuple(-v for v in key(r))+(r['teamId'],))
    for row in ordered: row['tied']=sum(key(row)==key(other) for other in ordered)>1
    return ordered

def comparison_table(st, comparator, tables, team_names):
    rows=[]; complete=True; unresolved=False
    for src in comparator['inputs']:
        if src is None:
            complete=False
            continue
        group=tables[(st['id'],src['group'])]
        if not group['complete']: complete=False
        if len(group['rows'])<src['rank']:
            complete=False
            continue
        row=group['rows'][src['rank']-1]
        if row['tied']:
            complete=False
            unresolved=unresolved or group['complete']
        rows.append(dict(row,group=src['group'],groupRank=src['rank'],mapDiff=row['mw']-row['ml']))
    rows.sort(key=lambda r:(-r['pts'],-r['mapDiff'],-r['rd'],team_names[r['teamId']],r['teamId']))
    return dict(rows=rows,complete=complete and len(rows)==len(comparator['inputs']),unresolved=unresolved)

def resolve(plan, matches, cfg, team_names, preview=False, results=None):
    bykey={m['flow_key']:m for m in matches if m['flow_key']}
    resolved, tables, comparisons={},{},{}
    def source(src):
        if src['kind']=='team': return src['teamId']
        if src['kind']=='empty': return None
        if src['kind']=='rank':
            group=tables.get((src['stageId'],src['group']))
            if not group or not group['complete']: return None
            row=group['rows'][src['rank']-1]
            return None if row['tied'] else row['teamId']
        if src['kind']=='comparison':
            comparison=comparisons.get((src['stageId'],src['comparatorId']))
            if not comparison or not comparison['complete']: return None
            return comparison['rows'][src['rank']-1]['teamId']
        if src['kind']=='worldcupThird':
            comparison=comparisons[(src['stageId'],src['comparatorId'])]
            if not comparison['complete']: return None
            return worldcup.allocation(comparison['rows'])[src['winnerGroup']]
        m=bykey.get(src['matchKey'])
        if not m or m['status']!='finished': return None
        a,b=score(m)
        if a==b: return None
        return m['team_a'] if (a>b)==(src['kind']=='winner') else m['team_b']
    defs=matches_of(plan)
    for st in plan['stages']:
        roster=[source(src) for src in st['slots']]; known=[tid for tid in roster if tid is not None]
        if not preview and len(known)!=len(set(known)): raise ValueError('同一队伍重复进入赛段，请调整参赛来源')
        for d in [d for d in defs if d['stageId']==st['id']]:
            resolved[d['key']]=(source(d['a']),source(d['b']))
        if st['type']=='group':
            size=st['teamCount']//st['groupCount']
            for g in range(st['groupCount']):
                groupdefs=[d for d in defs if d['stageId']==st['id'] and d['group']==g]
                ms=[bykey[d['key']] for d in groupdefs if d['key'] in bykey]
                if preview: ms=[m for m in ms if (m['team_a'],m['team_b'])==resolved[m['flow_key']]]
                ids=[source(s) for s in st['slots'][g*size:(g+1)*size]]
                tables[(st['id'],g)]=dict(rows=table(ids,ms,cfg,results),complete=bool(ms) and len(ms)==len(groupdefs) and all(m['status']=='finished' or m['id'] in (results or {}) for m in ms))
            for c in st.get('comparators',[]):
                comparisons[(st['id'],c['id'])]=comparison_table(st,c,tables,team_names)
                comparison=comparisons[(st['id'],c['id'])]
                if comparison['complete'] and any(s.get('bracket')=='worldcup2026' and s['groupStageId']==st['id'] and s['comparatorId']==c['id'] for s in plan['stages']):
                    opponents={team_id:winner for winner,team_id in worldcup.allocation(comparison['rows']).items()}
                    for row in comparison['rows']: row['worldcupOpponent']=opponents.get(row['teamId'])
    return resolved,tables,comparisons

def protected(m): return m['status']!='scheduled' or bool(m['maps'] or m['stats'] or any(b['map'] for b in m['bp']))

def reconcile(con):
    plan=json.loads(con.execute('SELECT active FROM flow WHERE id=1').fetchone()[0])
    cfg=json.loads(con.execute('SELECT value FROM settings WHERE id=1').fetchone()[0])
    matches=load_matches(con)
    pairs,_,_=resolve(plan,matches,cfg,{r['id']:r['name'] for r in con.execute('SELECT id,name FROM teams')})
    for m in matches:
        if m['flow_key'] not in pairs: continue
        a,b=pairs[m['flow_key']]
        if a is not None and a==b: raise ValueError('晋级后同一队伍出现在对阵双方，请调整参赛来源')
        if (a,b)!=(m['team_a'],m['team_b']):
            if protected(m): raise ValueError('下游比赛已有 BP 或赛果，不能改变晋级队伍')
            con.execute("UPDATE matches SET team_a=?,team_b=?,bp='[]',bp_config='{}',mvp_player_id=NULL WHERE id=?",(a,b,m['id']))

def activate(con, plan):
    old=json.loads(con.execute('SELECT active FROM flow WHERE id=1').fetchone()[0])
    before={d['key']:d for d in matches_of(old)};after={d['key']:d for d in matches_of(plan)}
    existing={m['flow_key']:m for m in load_matches(con) if m['flow_key']}
    for key,m in existing.items():
        if before.get(key)!=after.get(key) and protected(m): raise ValueError('受影响比赛已有 BP 或赛果，不能重建该赛段')
    for key,m in existing.items():
        if key not in after: con.execute('DELETE FROM matches WHERE id=?',(m['id'],))
    cfg=json.loads(con.execute('SELECT value FROM settings WHERE id=1').fetchone()[0])
    for st in plan['stages']:
        for d in [x for x in after.values() if x['stageId']==st['id']]:
            stage='group' if st['type']=='group' else 'playoff'
            if d['key'] not in existing:
                con.execute('INSERT INTO matches(stage,round_name,bo,status,time,flow_key) VALUES (?,?,?,?,?,?)',(stage,d['round'],d['bo'],'scheduled',cfg['start']+'T14:00' if cfg['start'] else '',d['key']))
            elif before.get(d['key'])!=d:
                con.execute('UPDATE matches SET stage=?,round_name=?,bo=? WHERE flow_key=?',(stage,d['round'],d['bo'],d['key']))
    con.execute('UPDATE flow SET active=?,draft=? WHERE id=1',(json.dumps(plan),json.dumps(plan)))
    reconcile(con)

def state(con, matches, cfg):
    row=con.execute('SELECT * FROM flow WHERE id=1').fetchone()
    draft,active=json.loads(row['draft']),json.loads(row['active'])
    names={r['id']:r['name'] for r in con.execute('SELECT id,name FROM teams')}
    pairs,tables,comparisons=resolve(active,matches,cfg,names)
    qualify(active,matches,cfg,names,pairs,tables,comparisons)
    active_defs={m['key']:m for m in matches_of(active)}
    draft_defs={m['key']:m for m in matches_of(draft)}
    preview_matches=[m for m in matches if m['flow_key'] in draft_defs and draft_defs[m['flow_key']]==active_defs.get(m['flow_key'])]
    draft_pairs,draft_tables,draft_comparisons=resolve(draft,preview_matches,cfg,names,preview=True)
    qualify(draft,preview_matches,cfg,names,draft_pairs,draft_tables,draft_comparisons)
    serialize=lambda values:[dict(stageId=s,comparatorId=c,**value) for (s,c),value in values.items()]
    projections=[p for st in active['stages'] if st.get('bracket')=='worldcup2026'
                 if (p:=worldcup.projection(st,tables,comparisons)) is not None]
    return dict(simulationRevision=simulation_revision(active,matches,cfg,names),draft=draft,active=active,tables=[dict(stageId=s,group=g,**value) for (s,g),value in tables.items()],comparisons=serialize(comparisons),draftComparisons=serialize(draft_comparisons),projections=projections)


def qualify(plan, matches, cfg, names, pairs, tables, comparisons, results=None):
    bykey={m['flow_key']:m for m in matches if m['flow_key']}
    defs=matches_of(plan)
    for st in plan['stages']:
        if st['type']!='group' or st['teamCount']//st['groupCount']!=4: continue
        possibilities={}
        for g in range(st['groupCount']):
            ids=[r['teamId'] for r in tables[st['id'],g]['rows']]
            if len(ids)!=4: continue
            ms=[]
            for d in defs:
                if d['stageId']!=st['id'] or d['group']!=g: continue
                a,b=pairs[d['key']]
                m=bykey.get(d['key'])
                if m and (m['team_a'],m['team_b'])==(a,b):
                    ms.append(dict(m,bo=m.get('bo',d['bo'])))
                else:
                    ms.append(dict(team_a=a,team_b=b,bo=d['bo'],status='scheduled',maps=[]))
            possibilities[g]=qualification.group_scenarios(ids,ms,cfg,results)
        qualification.annotate(st,tables,comparisons,possibilities,names,plan)


def simulation_revision(plan, matches, cfg, names):
    ranking_matches = [dict(id=m['id'],flow_key=m['flow_key'],team_a=m['team_a'],team_b=m['team_b'],
                            bo=m['bo'],finished=m['status']=='finished',maps=m['maps'])
                       for m in sorted(matches,key=lambda m:m['id']) if m['stage']=='group']
    payload = json.dumps([plan,ranking_matches,cfg,names],sort_keys=True,ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def simulate(plan, matches, cfg, names, entries):
    if not isinstance(entries, list):
        raise ValueError('模拟赛果格式无效')
    definitions = {d['key'] for st in plan['stages'] if st['type']=='group'
                   for d in matches_of({'stages':[st]})}
    eligible = {m['id']:m for m in matches if m['flow_key'] in definitions
                and (m['status']=='finished' or not m['maps']) and m['team_a'] and m['team_b']}
    results = {}
    for entry in entries:
        if not isinstance(entry, dict) or any(type(entry.get(k)) is not int for k in ('id','scoreA','scoreB','roundDiff')):
            raise ValueError('比分和净胜回合须为整数')
        mid = entry['id']
        if mid not in eligible or mid in results:
            raise ValueError('该比赛不可模拟，请刷新页面')
        m = eligible[mid]
        if m['status']=='finished' and entry.get('unlocked') is not True:
            raise ValueError('已完成比赛需先手动解锁模拟')
        a,b,rd = entry['scoreA'],entry['scoreB'],entry['roundDiff']
        valid = a>=0 and b>=0 and (a+b==2 if m['bo']==2 else max(a,b)==m['bo']//2+1 and min(a,b)<max(a,b))
        if not valid:
            raise ValueError('大比分与比赛制式不符')
        if not a-13*b <= rd <= 13*a-b:
            raise ValueError('净胜回合与大比分不符')
        results[mid] = entry
    group_plan = {'stages':[s for s in plan['stages'] if s['type']=='group']}
    pairs,tables,comparisons = resolve(group_plan,matches,cfg,names,results=results)
    qualify(plan,matches,cfg,names,pairs,tables,comparisons,results)
    projections = [p for st in plan['stages'] if st.get('bracket')=='worldcup2026'
                   if (p:=worldcup.projection(st,tables,comparisons)) is not None]
    for st in plan['stages']:
        if st.get('bracket')!='worldcup2026' or not any(p['stageId']==st['id'] for p in projections): continue
        comparison=comparisons[(st['groupStageId'],st['comparatorId'])]
        opponents={tid:winner for winner,tid in worldcup.allocation(comparison['rows']).items()}
        for row in comparison['rows']: row['worldcupOpponent']=opponents.get(row['teamId'])
    return dict(tables=[dict(stageId=s,group=g,**v) for (s,g),v in tables.items()],
                comparisons=[dict(stageId=s,comparatorId=c,**v) for (s,c),v in comparisons.items()],
                projections=projections)
