#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/.."
if lsof -nP -iTCP:5173 -sTCP:LISTEN >/dev/null 2>&1; then
  echo '请先停止本地 5173 端口的服务（在运行服务的终端按 Ctrl+C），然后重新执行。'
  exit 1
fi

CS2_REMOTE='root@43.132.178.154'
mkdir -p data/backups
CS2_STAGE="$(mktemp -d "$PWD/data/backups/server-sync-XXXXXX")"
CS2_REMOTE_DIR="/root/cs2web-backups/$(basename "$CS2_STAGE")"

ssh "$CS2_REMOTE" bash -s -- "$CS2_REMOTE_DIR" <<'REMOTE'
set -euo pipefail
CS2_EXPORT="$1"
install -d -m 700 "$CS2_EXPORT"
systemctl stop cs2web
trap 'systemctl start cs2web' EXIT
sqlite3 /var/lib/cs2web/tournament.sqlite3 ".backup '$CS2_EXPORT/tournament.sqlite3'"
mkdir -p "$CS2_EXPORT/media"
if [ -d /var/lib/cs2web/media ]; then
  cp -a /var/lib/cs2web/media/. "$CS2_EXPORT/media/"
fi
systemctl start cs2web
trap - EXIT
systemctl is-active cs2web
tar -czf "$CS2_EXPORT.tar.gz" -C "$CS2_EXPORT" tournament.sqlite3 media
REMOTE

scp "$CS2_REMOTE:$CS2_REMOTE_DIR.tar.gz" "$CS2_STAGE/snapshot.tar.gz"
tar -xzf "$CS2_STAGE/snapshot.tar.gz" -C "$CS2_STAGE"

python3 - "$CS2_STAGE/tournament.sqlite3" <<'PY'
import sqlite3
import sys
from pathlib import Path

db = Path(sys.argv[1]).resolve()
with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as con:
    result = con.execute('PRAGMA integrity_check').fetchall()
    if result != [('ok',)]:
        raise SystemExit(f'数据库完整性检查失败：{result}')
    errors = con.execute('PRAGMA foreign_key_check').fetchall()
    if errors:
        raise SystemExit(f'外键检查失败：{errors}')
    print('服务器快照检查：ok')
    for table in ('teams', 'players', 'matches'):
        count = con.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
        print(f'{table}: {count}')
PY

if lsof -nP -iTCP:5173 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "本地服务正在运行，未替换数据。已下载快照：$CS2_STAGE"
  exit 1
fi

CS2_OLD="$(mktemp -d "$PWD/data/backups/before-server-sync-XXXXXX")"
shopt -s nullglob
for CS2_FILE in data/*.sqlite3 data/*.sqlite3-wal data/*.sqlite3-shm data/*.sqlite3-journal data/media; do
  if [ -e "$CS2_FILE" ]; then
    mv "$CS2_FILE" "$CS2_OLD/"
  fi
done
mv "$CS2_STAGE/tournament.sqlite3" data/tournament.sqlite3
mv "$CS2_STAGE/media" data/media

echo "同步完成，原本地数据库（含测试库）与图片已移至：$CS2_OLD"
echo '启动本地站点：http://127.0.0.1:5173'
CS2_DB="$PWD/data/tournament.sqlite3" python3 server.py
