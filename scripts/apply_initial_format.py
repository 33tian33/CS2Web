"""Apply the requested four-school format, backing up the target database first."""
import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
import tournament
import worldcup


def apply(database):
    server.DB = Path(database).resolve()
    server.initialize()
    with server.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        if any(tournament.protected(m) for m in tournament.load_matches(con)):
            raise ValueError('存在 BP 或赛果，不能覆盖赛事数据')
        backup = server.DB.parent / 'backups' / ('tournament.before-initial-format-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.sqlite3')
        backup.parent.mkdir(exist_ok=True)
        with sqlite3.connect(server.DB) as source, sqlite3.connect(backup) as target:
            source.backup(target)
        con.execute('DELETE FROM matches')
        con.execute('DELETE FROM players')
        con.execute('DELETE FROM teams')
        con.execute('UPDATE flow SET draft=?,active=? WHERE id=1', ('{"stages":[]}', '{"stages":[]}'))
        cfg = server.default_config()
        cfg.update(name='四校 CS2 联赛', groupCount=12, teamsPerGroup=4, advance=2, thirdPlace=True)
        con.execute('UPDATE settings SET value=? WHERE id=1', (json.dumps(cfg, ensure_ascii=False),))
        slots = []
        for number in range(1, 13):
            for school in server.SCHOOLS:
                tid = con.execute('INSERT INTO teams(name,school,tag,color,logo,group_name,introduction) VALUES (?,?,?,?,?,?,?)',
                    (f"{school['short']}{number}队", school['name'], f"{school['short']}{number}", school['color'], '', chr(64+number), '')).lastrowid
                slots.append(dict(kind='team', teamId=tid))
        plan = dict(stages=[
            dict(id='groups', name='小组赛', type='group', bo=2, teamCount=48, groupCount=12, advance=2, slots=slots,
                 comparators=[dict(id='thirds', name='小组第三名比较（前8名晋级）', inputs=[dict(group=g, rank=3) for g in range(12)], outcomes=['qualified']*8+['eliminated']*4)]),
            dict(id='knockout', name='32强单淘汰', type='playoff', bo=3, teamCount=32, slots=[]),
            dict(id='bronze', name='季军赛', type='custom', bo=3, teamCount=2,
                 slots=[dict(kind='loser', matchKey=f'knockout:r4:{i}') for i in range(2)])
        ])
        worldcup.configure(plan)
        tournament.validate_plan(plan, {s['teamId'] for s in slots}, activate=True)
        tournament.activate(con, plan)
        con.execute("UPDATE matches SET time=''")
        con.execute("UPDATE matches SET bo=5 WHERE flow_key='knockout:r5:0'")
        con.execute("UPDATE matches SET round_name='季军赛' WHERE flow_key='bronze:r1:0'")
        con.execute('INSERT INTO audit_log(action) VALUES (?)', ('应用四校48队赛制：12组、24+8晋级、32强单淘及季军赛；清空队员',))
        assert con.execute('SELECT count(*) FROM teams').fetchone()[0] == 48
        assert con.execute('SELECT count(*) FROM players').fetchone()[0] == 0
        assert con.execute('SELECT count(*) FROM matches').fetchone()[0] == 104
        assert not con.execute('PRAGMA foreign_key_check').fetchall()
    print(json.dumps(dict(database=str(server.DB), backup=str(backup), teams=48, players=0, groupMatches=72, playoffMatches=32), ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--database', default=str(server.DB))
    apply(parser.parse_args().database)
