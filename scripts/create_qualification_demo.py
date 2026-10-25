import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
import tournament
import worldcup


def create(database):
    database = Path(database).resolve()
    if database.exists():
        raise FileExistsError(f'数据库已存在：{database}')
    server.DB = database
    server.initialize()
    cfg = server.default_config()
    cfg.update(name='晋级确认测试赛', season='2026 测试赛季', location='线上赛事',
               groupCount=12, teamsPerGroup=4, advance=2, thirdPlace=True)
    slots = [dict(kind='team', teamId=i) for i in range(1, 49)]
    plan = worldcup.configure(dict(stages=[
        dict(id='groups', name='小组赛', type='group', bo=2, teamCount=48, groupCount=12, advance=2,
             slots=slots, comparators=[dict(id='thirds', name='小组第三名排行榜',
             inputs=[dict(group=g, rank=3) for g in range(12)], outcomes=['qualified']*8+['eliminated']*4)]),
        dict(id='knockout', name='32强', type='playoff', bo=3, teamCount=32, slots=[]),
        dict(id='bronze', name='季军赛', type='custom', bo=3, teamCount=2, slots=[]),
    ]))
    with server.connect() as con:
        con.execute('UPDATE settings SET value=? WHERE id=1', (json.dumps(cfg, ensure_ascii=False),))
        for g in range(12):
            for i, school in enumerate(server.SCHOOLS):
                tid = g*4+i+1
                tag = f'{chr(65+g)}{i+1}'
                name = f'{tag} ' + ['曙光', '疾风', '星火', '潮汐'][i]
                con.execute('INSERT INTO teams(id,name,school,tag,color,logo,group_name) VALUES (?,?,?,?,?,?,?)',
                            (tid, name, school['name'], tag, school['color'], '', chr(65+g)))
                for n, position in enumerate(server.POSITIONS, 1):
                    con.execute('INSERT INTO players(team_id,nickname,avatar,role,position,school) VALUES (?,?,?,?,?,?)',
                                (tid, f'{tag}_{n:02}', '', '队长' if n == 1 else '选手', position, school['name']))
        tournament.validate_plan(plan, set(range(1, 49)), activate=True)
        tournament.activate(con, plan)
        for m in tournament.load_matches(con):
            if m['stage'] != 'group':
                continue
            g = (m['team_a']-1)//4
            a, b = (m['team_a']-1)%4+1, (m['team_b']-1)%4+1
            scores = None
            if g == 0:
                scores = {(1, 2): [(13, 10), (13, 12)], (1, 3): [(5, 13), (8, 13)],
                          (2, 3): [(13, 10), (12, 13)], (2, 4): [(13, 9), (13, 7)],
                          (3, 4): [(8, 13), (6, 13)]}.get((a, b))
            elif g == 1 and (a, b) in [(1, 2), (1, 3)]:
                scores = [(13, 5), (13, 7)]
            elif g == 2:
                scores = [(13, 8), (8, 13)]
            elif 3 <= g <= 10:
                loser = g-3 if a == 3 else 5
                scores = [(13, loser), (13, loser)]
            if scores is not None:
                maps = [dict(name=name, scoreA=x, scoreB=y) for name, (x, y) in zip(['Mirage', 'Nuke'], scores)]
                con.execute("UPDATE matches SET status='finished',maps=?,finished_at=? WHERE id=?",
                            (json.dumps(maps), f'2026-10-16T{10+g:02}:00:00+08:00', m['id']))
        con.execute("UPDATE matches SET bo=5 WHERE flow_key='knockout:r5:0'")
        con.execute("UPDATE matches SET round_name='季军赛' WHERE flow_key='bronze:r1:0'")
        tournament.reconcile(con)
        assert con.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert not con.execute('PRAGMA foreign_key_check').fetchall()
    state = server.get_state()
    status = lambda rows: dict(Counter(r['qualification'] for r in rows))
    report = dict(database=str(database), teams=len(state['teams']), players=len(state['players']),
                  matches=dict(Counter(m['status'] for m in state['matches'])),
                  groups={chr(65+g['group']): [(next(t['tag'] for t in state['teams'] if t['id']==r['teamId']), r['pts'], r['qualification'])
                          for r in g['rows']] for g in state['flow']['tables']},
                  thirdPlace=status(state['flow']['comparisons'][0]['rows']))
    database.with_suffix('.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--database', default=str(server.ROOT/'data/qualification-demo.sqlite3'))
    create(parser.parse_args().database)
