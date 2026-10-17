"""Apply the FIFA 2026 bracket to an existing event, retaining groups and scores."""
import argparse
import copy
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tournament
import worldcup


def apply(database):
    database = Path(database).resolve()
    with sqlite3.connect(f'file:{database}?mode=rw', uri=True) as con:
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA foreign_keys=ON')
        con.execute('BEGIN IMMEDIATE')
        flow = con.execute('SELECT active,draft FROM flow WHERE id=1').fetchone()
        active, draft = (json.loads(flow[k]) for k in ('active', 'draft'))
        updated, updated_draft = (worldcup.configure(copy.deepcopy(p)) for p in (active, draft))
        teams = {r[0] for r in con.execute('SELECT id FROM teams')}
        tournament.validate_plan(updated, teams, activate=True)
        tournament.validate_plan(updated_draft, teams)
        if updated == active and updated_draft == draft:
            return dict(database=str(database), changed=False)
        matches = tournament.load_matches(con)
        if any(tournament.protected(m) for m in matches if m['stage']=='playoff'):
            raise ValueError('淘汰赛已有 BP、赛果或已开始，不能改变淘汰路径')
        preserved = {table: [tuple(r) for r in con.execute(f'SELECT * FROM {table} ORDER BY id')]
                     for table in ('settings', 'teams', 'players', 'sponsors')}
        group_matches = [m for m in matches if m['stage']=='group']
        backup = database.parent / 'backups' / ('tournament.before-worldcup-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.sqlite3')
        backup.parent.mkdir(exist_ok=True)
        with sqlite3.connect(f'file:{database}?mode=ro', uri=True) as source, sqlite3.connect(backup) as target:
            source.backup(target)
        tournament.activate(con, updated)
        con.execute('UPDATE flow SET draft=? WHERE id=1', (json.dumps(updated_draft, ensure_ascii=False),))
        con.executemany('UPDATE matches SET bo=? WHERE id=?', [(m['bo'], m['id']) for m in matches])
        after = tournament.load_matches(con)
        if {m['id'] for m in after} != {m['id'] for m in matches} or group_matches != [m for m in after if m['stage']=='group']:
            raise ValueError('迁移改变了现有比赛或小组赛数据，已回滚')
        for table, rows in preserved.items():
            if rows != [tuple(r) for r in con.execute(f'SELECT * FROM {table} ORDER BY id')]:
                raise ValueError('迁移改变了赛事、分组或人员数据，已回滚')
        if con.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or con.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('数据库完整性检查未通过，已回滚')
        con.execute('INSERT INTO audit_log(action) VALUES (?)', ('应用2026世界杯官方淘汰路径及附录C的495种第三名组合；保留分组、人员、小组赛与BO',))
    return dict(database=str(database), backup=str(backup), changed=True, matches=len(after), groupsPreserved=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', default=str(Path(__file__).resolve().parents[1] / 'data/tournament.sqlite3'))
    print(json.dumps(apply(parser.parse_args().database), ensure_ascii=False))
