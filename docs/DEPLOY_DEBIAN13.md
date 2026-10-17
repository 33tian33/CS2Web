# Debian 13.2 新服务器部署：程序与本地数据库一起迁移

适用目标：`SERVER_IP`，网站地址 `https://www.hushang985.online`。

本文按新服务器首次部署编写。命令标注了执行位置，逐个代码块执行；遇到错误先解决，再继续。服务器命令均在 root 会话中执行。本文编写时没有登录或修改目标服务器，DNS、端口和证书需按下文实测。

已有线上站点升级图片存储、启用缓存与压缩，以及补齐裸域名证书，请使用 [首页加载优化与部署教程](PERFORMANCE_UPDATE.md)，不要覆盖线上数据库。

2026-10-09 首次编写时检查本地库：48 支队伍、64 名选手、104 场比赛，完整性检查为 `ok`，无外键错误。实际迁移以你打包时输出的数量为准。使用当前 `data/tournament.sqlite3`，不导入 `data/backups/` 或历史备份。图片目录 `data/media/` 与数据库一起迁移；旧 Base64 图片安装后由迁移脚本转为独立文件；外部 HTTPS 图片仍依赖原图片地址。

架构：公网浏览器 → Nginx 80/443 → Python `127.0.0.1:5173`；程序放在 `/opt/cs2web`，数据库放在 `/var/lib/cs2web/tournament.sqlite3`。当前程序没有第三方 Python 运行依赖，也没有前端构建步骤。Debian 13 自带 Python 3.13，直接用系统 Python，无需沿用旧 Debian 10 教程编译 Python。[Debian Python 软件包](https://packages.debian.org/trixie/python3)

## 1. 配置域名与云防火墙

在域名 DNS 管理控制台，为 `hushang985.online` 设置：

| 主机记录 | 类型 | 记录值 | TTL |
| --- | --- | --- | --- |
| www | A | SERVER_IP | 默认或 600 秒 |

如 `www` 已有其他 A/CNAME，修改对应记录，避免解析到多个不同网站。本教程不使用 CDN 代理。不配置 IPv6 时，移除或修正 `www` 上失效的 AAAA 记录。本文仅配置 `www.hushang985.online`；裸域名 `hushang985.online` 是另一个域名，不会自动获得证书或跳转。

在服务器控制台的安全组或防火墙中允许：

| 入站端口 | 协议 | 来源 | 用途 |
| --- | --- | --- | --- |
| 22 | TCP | 你的管理公网 IP | SSH |
| 80 | TCP | 0.0.0.0/0 | HTTP、证书验证和续期 |
| 443 | TCP | 0.0.0.0/0 | HTTPS |

保留控制台远程终端需要的现有规则。不要向公网开放 5173。

**Mac 终端：**

```bash
dig +short A www.hushang985.online
dig +short AAAA www.hushang985.online
```

A 应返回 `SERVER_IP`；本方案下 AAAA 应无输出。DNS 尚未生效时可以继续安装程序，但申请证书前必须生效。

## 2. 登录新服务器

**Mac 终端：**

```bash
ssh root@SERVER_IP
```

第一次连接时核对服务器控制台中的 SSH 主机指纹，再输入 `yes`。输入服务器密码时终端不会显示字符，这是正常的。若云平台提供的是普通账号，使用该账号 SSH 登录后执行 `sudo -i`；上传时也用该账号并先传至其家目录，再用 sudo 移到本文的 `/root/` 路径。

**服务器终端：**

```bash
cat /etc/os-release
uname -m
```

确认是 Debian 13（trixie），64 位架构通常显示 `x86_64` 或 `aarch64`。

## 3. 安装系统软件

**服务器终端：**

```bash
apt-get update
apt-get install -y python3 nginx sqlite3 certbot python3-certbot-nginx ca-certificates curl openssl
python3 --version
python3 -c "import ssl, sqlite3; print(ssl.OPENSSL_VERSION); print(sqlite3.sqlite_version)"
```

Python 应为 3.13 系列，最后一条应正常打印 OpenSSL 和 SQLite 版本。保留 Debian 13 的软件源；不要套用旧教程里的 buster 归档源。Debian 13 提供 Certbot Nginx 插件，可直接使用 APT 安装。[软件包说明](https://packages.debian.org/trixie/python3-certbot-nginx)

如系统已启用防火墙，还需在该防火墙中放行 80 和 443。使用 UFW 的服务器先执行 `ufw status`；只有已安装且状态为 active 时，执行：

```bash
ufw allow 80/tcp
ufw allow 443/tcp
```

新系统未启用 UFW 时不必专门启用它；云防火墙仍需配置。若使用 nftables，自行维护现有规则中的放行项，可用 `nft list ruleset` 查看；不要清空规则或改变 SSH 放行项。

## 4. 在 Mac 创建数据库快照并打包

打开另一个 **Mac 终端窗口**，不要在 SSH 会话中执行本节。

打包开始后，暂停在本地后台修改赛事，直到新站核验完毕。SQLite backup API 会生成一致快照，但快照生成之后的新修改不会自动同步。[SQLite 在线备份说明](https://www.sqlite.org/backup.html)

下面整个代码块一次复制执行：

```bash
(
set -e
cd "/Users/tian33/Project CS2Web"
export CS2_STAGE="$(mktemp -d /tmp/cs2web-deploy.XXXXXX)"

cp server.py tournament.py "$CS2_STAGE/"
cp -R public scripts deploy "$CS2_STAGE/"
mkdir "$CS2_STAGE/media"
if [ -d data/media ]; then cp -R data/media/. "$CS2_STAGE/media/"; fi

python3 - <<'PY'
import os
import sqlite3
from pathlib import Path

source = Path('data/tournament.sqlite3').resolve()
target = Path(os.environ['CS2_STAGE']) / 'tournament.sqlite3'
src = sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)
dst = sqlite3.connect(target)
try:
    src.backup(dst)
    result = dst.execute('PRAGMA integrity_check').fetchall()
    if result != [('ok',)]:
        raise RuntimeError(result)
    errors = dst.execute('PRAGMA foreign_key_check').fetchall()
    if errors:
        raise RuntimeError(errors)
    print('数据库快照:', target)
    for table in ['teams', 'players', 'matches']:
        print(table, dst.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0])
finally:
    dst.close()
    src.close()
PY

cd "$CS2_STAGE"
shasum -a 256 tournament.sqlite3 > SHA256SUMS
COPYFILE_DISABLE=1 tar -czf /tmp/cs2web-new-server.tar.gz \
  server.py tournament.py worldcup.py qualification.py rules public scripts deploy media tournament.sqlite3 SHA256SUMS
ls -lh /tmp/cs2web-new-server.tar.gz
)
```

记录输出的 `teams`、`players`、`matches` 数量。只有成功生成压缩包后才上传：

```bash
scp /tmp/cs2web-new-server.tar.gz root@SERVER_IP:/root/
```

压缩包包含程序、静态素材以及数据库快照，不包含历史备份和导入资料。

## 5. 在服务器解压、校验并安装

回到 **服务器终端**，整个代码块一次执行。这是首次安装；若提示已有数据库，应先核实已有部署，不要直接覆盖。

```bash
(
set -e
if [ -e /var/lib/cs2web/tournament.sqlite3 ]; then
  echo '目标数据库已存在，请先核实已有部署，停止首次安装。'
  exit 1
fi

CS2_UNPACK="$(mktemp -d /root/cs2web-unpack.XXXXXX)"
tar -xzf /root/cs2web-new-server.tar.gz -C "$CS2_UNPACK"
cd "$CS2_UNPACK"
sha256sum -c SHA256SUMS

if ! id cs2web >/dev/null 2>&1; then
  adduser --system --group --no-create-home cs2web
fi
install -d -m 755 /opt/cs2web
install -d -o cs2web -g cs2web -m 750 /var/lib/cs2web
cp server.py tournament.py /opt/cs2web/
cp -R public scripts deploy /opt/cs2web/
chown -R root:root /opt/cs2web
chmod -R u=rwX,go=rX /opt/cs2web
install -o cs2web -g cs2web -m 640 \
  tournament.sqlite3 /var/lib/cs2web/tournament.sqlite3
cp -R media /var/lib/cs2web/
chown -R cs2web:cs2web /var/lib/cs2web/media
)
```

应看到 `tournament.sqlite3: OK`。继续核对：

```bash
sqlite3 /var/lib/cs2web/tournament.sqlite3 <<'SQL'
PRAGMA integrity_check;
PRAGMA foreign_key_check;
SELECT 'teams', COUNT(*) FROM teams;
SELECT 'players', COUNT(*) FROM players;
SELECT 'matches', COUNT(*) FROM matches;
SQL

cd /opt/cs2web
```

数据库检查应输出 `ok`，没有外键错误，数量与第 4 步一致。本地验证通过不代替这里的 Debian 13 环境验证。

迁移旧 Base64 图片（自动备份；没有旧图片时输出 `converted: 0`）：

```bash
cd /opt/cs2web
runuser -u cs2web -- env PYTHONDONTWRITEBYTECODE=1 python3 \
  scripts/migrate_images.py --database /var/lib/cs2web/tournament.sqlite3
```

## 6. 设置线上管理员密码

**服务器终端，首次部署执行：**

```bash
(
set -e
if [ -e /etc/cs2web.env ]; then
  echo '/etc/cs2web.env 已存在，请编辑已有配置，不要重新生成。'
  exit 1
fi
umask 077
CS2_PASSWORD="$(openssl rand -hex 24)"
cat > /etc/cs2web.env <<EOF
PORT=5173
CS2_DB=/var/lib/cs2web/tournament.sqlite3
CS2_PUBLIC_ORIGIN=https://www.hushang985.online
CS2_ADMIN_PASSWORD=$CS2_PASSWORD
PYTHONUNBUFFERED=1
PYTHONDONTWRITEBYTECODE=1
EOF
chmod 600 /etc/cs2web.env
printf '管理员用户名：admin\n管理员密码：%s\n' "$CS2_PASSWORD"
)
```

把输出的密码保存在密码管理器中。线上用户名为 `admin`。数据库迁移不会迁移管理员密码；密码由这个环境文件决定。

`CS2_PUBLIC_ORIGIN` 必须与最终浏览器地址一致：使用 `https://`，带 `www`，不带末尾斜线。证书配置前不要在 HTTP 页面登录后台。

## 7. 配置后台常驻和开机启动

**服务器终端：**

```bash
cat > /etc/systemd/system/cs2web.service <<'EOF'
[Unit]
Description=CS2 Tournament Website
After=network.target

[Service]
Type=simple
User=cs2web
Group=cs2web
WorkingDirectory=/opt/cs2web
EnvironmentFile=/etc/cs2web.env
ExecStart=/usr/bin/python3 /opt/cs2web/server.py
Restart=on-failure
RestartSec=3
UMask=0027

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now cs2web
systemctl status cs2web --no-pager
curl --fail http://127.0.0.1:5173/api/session
```

服务应为 `active (running)`，接口应返回 `{"authenticated": false}`。如失败：

```bash
journalctl -u cs2web -n 100 --no-pager
```

## 8. 配置 Nginx HTTP 入口

**服务器终端：**

```bash
install -m 644 /opt/cs2web/deploy/nginx-performance.conf /etc/nginx/snippets/cs2web-performance.conf
cat > /etc/nginx/sites-available/cs2web <<'NGINX'
server {
    listen 80;
    server_name www.hushang985.online;

    root /opt/cs2web/public;
    index index.html;
    client_max_body_size 8m;
    include /etc/nginx/snippets/cs2web-performance.conf;

    location /api/ {
        proxy_pass http://127.0.0.1:5173;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        try_files $uri $uri/ =404;
    }
}
NGINX

ln -s /etc/nginx/sites-available/cs2web /etc/nginx/sites-enabled/cs2web
nginx -t
```

若链接已存在，确认它指向上述文件即可，不必重复创建。只有 `nginx -t` 成功才继续：

```bash
systemctl enable --now nginx
systemctl reload nginx
curl --fail -H 'Host: www.hushang985.online' http://127.0.0.1/api/session
```

不需要删除默认站点或其他站点配置。项目用 `/#/...` 路由，无需额外配置 SPA 回退。

**Mac 终端：**

```bash
curl --fail http://www.hushang985.online/api/session
```

应返回 `{"authenticated": false}`。这一步验证公网 DNS、80 端口和反向代理；仅服务器内部 curl 成功不能证明公网已经可用。

## 9. 申请 HTTPS 证书并启用跳转

确认第 8 步 Mac 上的 HTTP 请求成功。**服务器终端：**

```bash
certbot --nginx -d www.hushang985.online --redirect
```

按提示输入你常用的邮箱，阅读并接受证书服务条款；如询问是否分享邮箱，按个人意愿选择。该命令自动申请证书、写入 Nginx HTTPS 配置并开启 HTTP → HTTPS 跳转，无需手工上传证书。[Certbot Nginx 使用说明](https://eff-certbot.readthedocs.io/en/stable/using.html#nginx)

成功后执行：

```bash
nginx -t && systemctl reload nginx
certbot certificates
systemctl enable --now certbot.timer
systemctl list-timers --all certbot.timer
certbot renew --dry-run
```

确认计时器已安排下一次运行，续期模拟成功。80 端口与 DNS 解析应持续可用，以便后续验证和续期。[Certbot 自动续期说明](https://eff-certbot.readthedocs.io/en/stable/using.html#renewing-certificates)

证书成功后，不要再次用第 8 步的纯 HTTP 配置覆盖当前文件。申请失败时先排查 DNS、AAAA、80 端口以及已有 CAA 记录是否允许 Let's Encrypt，再重试；详细错误在 `/var/log/letsencrypt/letsencrypt.log`。

## 10. 验证 HTTPS 与迁移的数据

**Mac 终端：**

```bash
curl -I http://www.hushang985.online/
curl -I https://www.hushang985.online/
curl --fail https://www.hushang985.online/api/session
curl --fail --silent --show-error https://www.hushang985.online/api/state \
  -o /tmp/cs2web-online-state.json
python3 - <<'PY'
import json
from pathlib import Path
state = json.loads(Path('/tmp/cs2web-online-state.json').read_text())
print('赛事:', state['config']['name'])
for key in ['teams', 'players', 'matches']:
    print(key, len(state[key]))
PY
```

HTTP 应跳到 HTTPS，HTTPS 首页返回 `200`，接口数量与第 4 步一致。命令不使用 `-k`：成功才能说明证书校验也通过。

用浏览器打开：

- 首页：<https://www.hushang985.online/>
- 赛事：<https://www.hushang985.online/#/event>
- 后台：<https://www.hushang985.online/#/admin>

检查队名、选手、段位、队标、头像、分组和赛程。使用 `admin` 与第 6 步密码登录。保存一项你本来就要修改的内容，或在表单允许时保存原值，刷新前台核对保存结果。

**服务器终端：**

```bash
systemctl restart cs2web
systemctl is-active cs2web nginx
systemctl is-enabled cs2web nginx certbot.timer
ss -lntp
```

重启后再刷新网页确认数据仍在。当前管理员会话保存在内存，服务重启后需要重新登录；赛事数据在 SQLite 中保留。5173 应只监听 `127.0.0.1`。

上线后在新站后台维护赛事。本地数据库和服务器数据库从此是两份独立数据，不会双向自动同步。

## 11. 备份服务器数据库并下载到 Mac

每次更新程序前、重要数据录入后备份。图片迁移后必须同时保存 SQLite 与 `media/`。暂停后台录入，**服务器终端整个代码块执行：**

```bash
(
set -e
CS2_BACKUP_DIR="/root/cs2web-backups/full-$(date +%Y%m%d-%H%M%S)"
install -d -m 700 "$CS2_BACKUP_DIR"
systemctl stop cs2web
sqlite3 /var/lib/cs2web/tournament.sqlite3 ".backup '$CS2_BACKUP_DIR/tournament.sqlite3'"
if [ -d /var/lib/cs2web/media ]; then cp -a /var/lib/cs2web/media "$CS2_BACKUP_DIR/"; fi
tar -czf "$CS2_BACKUP_DIR.tar.gz" -C "$CS2_BACKUP_DIR" .
systemctl start cs2web
ls -lh "$CS2_BACKUP_DIR.tar.gz"
)
```

`.backup` 可在服务运行时使用；这里停服以让数据库和图片保持同一时点。中途失败时处理错误后再启动服务。**Mac 终端：**

```bash
mkdir -p "$HOME/Downloads/cs2web-backups"
scp 'root@SERVER_IP:/root/cs2web-backups/full-*.tar.gz' \
  "$HOME/Downloads/cs2web-backups/"
```

## 12. 后续只更新网页和程序

后续部署默认保留线上数据库。不要重新上传第 4 步的首次部署包，否则旧快照可能覆盖新录入的数据。

**Mac 终端：**

```bash
cd "/Users/tian33/Project CS2Web"
COPYFILE_DISABLE=1 tar -czf /tmp/cs2web-update.tar.gz \
  server.py tournament.py worldcup.py qualification.py rules public scripts deploy
scp /tmp/cs2web-update.tar.gz root@SERVER_IP:/root/
```

**服务器终端，整个代码块执行：**

```bash
(
set -e
install -d -m 700 /root/cs2web-backups
CS2_UPDATE_ID="$(date +%Y%m%d-%H%M%S)"
systemctl stop cs2web
sqlite3 /var/lib/cs2web/tournament.sqlite3 \
  ".backup '/root/cs2web-backups/tournament-before-update-$CS2_UPDATE_ID.sqlite3'"
tar -czf "/root/cs2web-backups/code-$CS2_UPDATE_ID.tar.gz" \
  -C /opt cs2web
tar -xzf /root/cs2web-update.tar.gz -C /opt/cs2web
chown -R root:root /opt/cs2web
chmod -R u=rwX,go=rX /opt/cs2web
systemctl start cs2web
systemctl status cs2web --no-pager
curl --fail http://127.0.0.1:5173/api/session
curl --fail --silent --show-error http://127.0.0.1:5173/api/state -o /tmp/cs2web-state-check.json
)
```

如果中途失败，服务可能保持停止状态，处理报错后再启动。重新验证首页、后台登录和保存。若新版本删除了旧静态文件，还需按实际变更清理对应旧文件。

## 13. 常用排障命令

**服务器终端：**

```bash
systemctl status cs2web nginx --no-pager
journalctl -u cs2web -n 100 --no-pager
nginx -t
tail -n 100 /var/log/nginx/error.log
ss -lntp
```

| 现象 | 检查和处理 |
| --- | --- |
| SSH 超时 | 云防火墙 22、服务器状态、管理 IP 规则 |
| SSH Permission denied | 登录账号、密码或 SSH 密钥是否与云控制台配置一致 |
| 公网网站超时 | A/AAAA、云防火墙 80/443、系统防火墙 |
| 显示 Nginx 默认页 | 用完整域名访问；检查 `server_name`、站点链接与 reload |
| 502 Bad Gateway | Python 服务是否运行，日志是否报错，5173 是否被占用 |
| 后台显示“无效的访问地址” | Nginx `Host` 与 `CS2_PUBLIC_ORIGIN` 中的域名 |
| 后台显示“不允许跨站修改” | 是否使用 `https://www.hushang985.online` |
| 登录后没有保持登录 | 是否仍在 HTTP 页面，Secure Cookie 要求 HTTPS |
| 数据库只读 | 数据库及 `/var/lib/cs2web` 目录的 cs2web 所有权与写入权限 |
| 页面为空或数量不符 | 服务的 `CS2_DB` 路径与上传快照数量；不要重新初始化赛事 |
| 上传图片 413 | 单图大小、Nginx 请求上限与后端 8,000,000 字节限制 |
| 修改配置没有生效 | 环境文件修改后执行 `systemctl restart cs2web` |
| 证书申请或续期失败 | DNS、失效 AAAA、80 端口、CAA、Certbot 错误日志 |

权限修复（仅当上面的数据库权限问题实际发生时）：

```bash
chown -R cs2web:cs2web /var/lib/cs2web
chmod 750 /var/lib/cs2web
chmod 640 /var/lib/cs2web/tournament.sqlite3
systemctl restart cs2web
```

本教程完成当前程序的单机部署，不改变现有 Python HTTP 后端或内存会话实现。
