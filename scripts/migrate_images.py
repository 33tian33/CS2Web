"""Move embedded roster images to content-addressed files; back up SQLite first."""
import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server


def migrate(database):
    server.DB = Path(database).resolve(strict=True)
    with server.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        if con.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('数据库完整性检查失败')
        if con.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('数据库存在外键错误')
        rows = [(table, column, row['id'], row[column])
                for table, column in [('teams', 'logo'), ('players', 'avatar')]
                for row in con.execute(f"SELECT id,{column} FROM {table} WHERE {column} LIKE 'data:image/%'")]
        if not rows:
            return dict(converted=0, database=str(server.DB), backup=None)
        backup = server.DB.parent/'backups'/('tournament.before-images-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.sqlite3')
        backup.parent.mkdir(exist_ok=True)
        with sqlite3.connect(server.DB) as source, sqlite3.connect(backup) as target:
            source.backup(target)
        for table, column, ident, value in rows:
            url = server.image_url(value)
            con.execute(f'UPDATE {table} SET {column}=? WHERE id=?', (url, ident))
        con.execute('INSERT INTO audit_log(action) VALUES (?)', ('迁移头像与队徽为独立图片文件',))
    return dict(converted=len(rows), database=str(server.DB), backup=str(backup))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', default=str(server.DB))
    print(json.dumps(migrate(parser.parse_args().database), ensure_ascii=False))
