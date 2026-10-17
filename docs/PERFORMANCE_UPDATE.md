# 首页加载优化与部署教程

适用服务器：`SERVER_IP`，Debian 13，现有站点 `https://www.hushang985.online`。这是现有站点的更新教程，不重新初始化赛事，也不上传本地数据库。

## 1. 本次改动

2026-10-09 实测：首页 HTML 约 0.23 秒；`/api/state` 返回 7,637,574 字节，两次完整下载分别耗时 12.52 秒、21.82 秒。响应中 99.18% 是 Base64 头像和队徽。页面要等待整个响应才能显示。

| 文件 | 改动 |
| --- | --- |
| `server.py` | 新上传图片写入数据库旁的 `media/`；数据库保存 `/media/<SHA256>.<扩展名>`；图片长缓存；赛事接口 ETag 校验，数据未变返回 304 |
| `scripts/migrate_images.py` | 为已有数据库自动备份，把 Base64 图片转换成独立文件；保留原图片字节；支持重复运行；失败回滚数据库事务 |
| `public/app.js` | GET 请求重新验证缓存；保留赛事与比赛详情页每 4 秒检查更新的行为 |
| `public/team-components.js` | 图片懒加载、异步解码，屏幕外头像不用立即下载 |
| `public/index.html` | 更新修改过的 JS 版本号 |
| `deploy/nginx-performance.conf` | JSON、JS、CSS、SVG 压缩；`/media/` 转发到 Python；HTML 重新验证缓存 |

数据未变时，浏览器收到 304 并复用本地响应；登录状态仍使用 `no-store`。图片以内容哈希命名，更换图片即更换 URL，因此可以缓存一年。已有 HTTPS 外链图片保持原样。

本地数据库**副本**演练：75 张嵌入图片迁移后，接口从 7,429,546 字节降至 67,700 字节（减少 99.09%）；gzip 后 8,755 字节。逐张图片字节与其他业务数据均一致。这不是上线后的速度承诺，线上数据量与本地略有不同。

## 2. Mac：打包并上传代码

在 Mac 终端执行：

```bash
cd "/Users/tian33/Project CS2Web"
COPYFILE_DISABLE=1 tar -czf /tmp/cs2web-performance.tar.gz \
  server.py tournament.py public scripts deploy docs/PERFORMANCE_UPDATE.md
scp /tmp/cs2web-performance.tar.gz root@SERVER_IP:/root/
ssh root@SERVER_IP
```

包内没有 `data/`。以下步骤在服务器 root 终端执行。

## 3. 服务器：备份、更新、迁移

维护期间暂停后台录入。整个代码块执行：

```bash
(
set -e
CS2_UPDATE_DIR="/root/cs2web-backups/performance-$(date +%Y%m%d-%H%M%S)"
install -d -m 700 "$CS2_UPDATE_DIR"
printf '%s\n' "$CS2_UPDATE_DIR" > /root/cs2web-performance-last-backup
tar -czf "$CS2_UPDATE_DIR/nginx.tar.gz" -C /etc nginx
systemctl stop cs2web
sqlite3 /var/lib/cs2web/tournament.sqlite3 ".backup '$CS2_UPDATE_DIR/tournament.sqlite3'"
tar -czf "$CS2_UPDATE_DIR/code.tar.gz" -C /opt/cs2web server.py tournament.py public
if [ -d /var/lib/cs2web/media ]; then
  tar -czf "$CS2_UPDATE_DIR/media.tar.gz" -C /var/lib/cs2web media
fi
tar -xzf /root/cs2web-performance.tar.gz -C /opt/cs2web
chown -R root:root /opt/cs2web
chmod -R u=rwX,go=rX /opt/cs2web
cd /opt/cs2web
runuser -u cs2web -- env PYTHONDONTWRITEBYTECODE=1 python3 \
  scripts/migrate_images.py --database /var/lib/cs2web/tournament.sqlite3
sqlite3 /var/lib/cs2web/tournament.sqlite3 'PRAGMA integrity_check; PRAGMA foreign_key_check;'
systemctl start cs2web
curl --fail --silent --show-error http://127.0.0.1:5173/api/state -o /tmp/cs2-state-after.json
python3 - <<'PY'
import json
from pathlib import Path
p = Path('/tmp/cs2-state-after.json')
s = json.loads(p.read_text())
assert not any(t['logo'].startswith('data:') for t in s['teams'])
assert not any(p['avatar'].startswith('data:') for p in s['players'])
print('接口字节数:', p.stat().st_size)
print('队伍、选手、比赛:', len(s['teams']), len(s['players']), len(s['matches']))
PY
printf '\n更新前备份：%s\n' "$CS2_UPDATE_DIR"
)
```

迁移脚本输出 `converted` 和备份路径；数据库检查输出 `ok` 且无外键错误。脚本会再保存一份迁移前数据库到 `/var/lib/cs2web/backups/`。重复运行时 `converted: 0` 是正常结果。

新图片目录由 `cs2web` 用户创建并读取，位于 `/var/lib/cs2web/media/`，不在会被更新覆盖的 `/opt/cs2web/public/` 内。Nginx 通过本机 Python 读取图片，不需要开放数据库目录权限。

如果某一步报错，先处理该错误；`set -e` 会停止后续操作，服务可能仍停止。迁移失败时数据库修改自动回滚，已写出的无引用图片不会被页面使用。不要跳过迁移直接认为优化已经完成。

## 4. 服务器：让 Nginx 提供图片和压缩

```bash
install -m 644 /opt/cs2web/deploy/nginx-performance.conf /etc/nginx/snippets/cs2web-performance.conf
nano /etc/nginx/sites-available/cs2web
```

在已有 `server_name www.hushang985.online;` 且监听 **443** 的 `server { ... }` 内，加入下面一行，位置与 `root`、`location` 同级，不要放进已有 `location` 内：

```nginx
include /etc/nginx/snippets/cs2web-performance.conf;
```

保留原来的证书路径、`location /api/` 和 `location /`。若该 server 已有 `gzip` 等同名指令或 `/media/`、`/index.html` 专用 location，合并为一份，避免重复配置。然后执行：

```bash
nginx -t && systemctl reload nginx
```

必须完成此步骤，否则默认 `try_files` 会让迁移后的图片返回 404。Nginx 的 `gzip_types` 默认只包含 HTML，因此此配置明确加入 JSON、JS 和 CSS。[Nginx gzip 文档](https://nginx.org/en/docs/http/ngx_http_gzip_module.html)

## 5. 补齐裸域名证书和跳转

这一部分独立于加载优化。保留带 `www` 的地址作为正式入口，`CS2_PUBLIC_ORIGIN` 仍为 `https://www.hushang985.online`。

先在 DNS 控制台确认：

| 主机记录 | 类型 | 地址 |
| --- | --- | --- |
| `@` | A | `SERVER_IP` |
| `www` | A | `SERVER_IP` |

没有提供 IPv6 服务时，不保留指向其他服务器的 AAAA 记录。确认公网 80、443 端口可访问。

先检查是否已有裸域名配置：

```bash
nginx -T 2>&1 | grep -n 'server_name\|ssl_certificate'
```

如果已有 `server_name hushang985.online;`，编辑现有配置，不再新建重复的 server。按当前只部署 `www` 的情况，创建裸域名的 HTTP 配置：

```bash
cat > /etc/nginx/sites-available/cs2web-apex <<'NGINX'
server {
    listen 80;
    server_name hushang985.online;
    return 301 https://www.hushang985.online$request_uri;
}
NGINX
ln -s /etc/nginx/sites-available/cs2web-apex /etc/nginx/sites-enabled/cs2web-apex
nginx -t && systemctl reload nginx
```

为裸域名单独申请证书，现有 `www` 证书继续使用：

```bash
certbot certonly --nginx --cert-name hushang985.online -d hushang985.online
certbot certificates
```

成功后应存在 `/etc/letsencrypt/live/hushang985.online/fullchain.pem` 和 `privkey.pem`。Certbot 如显示不同路径，使用其实际输出。[Certbot 证书管理文档](https://eff-certbot.readthedocs.io/en/stable/using.html#managing-certificates)

只有证书签发成功后，才把下面的 HTTPS 配置追加到同一文件：

```bash
cat >> /etc/nginx/sites-available/cs2web-apex <<'NGINX'

server {
    listen 443 ssl;
    server_name hushang985.online;
    ssl_certificate /etc/letsencrypt/live/hushang985.online/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/hushang985.online/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    return 301 https://www.hushang985.online$request_uri;
}
NGINX
nginx -t && systemctl reload nginx
certbot renew --dry-run
```

上述创建与追加命令只执行一次；后续调整用编辑器修改原文件。HTTPS 必须先通过证书验证才能跳转，单独设置 HTTP 301 不能解决之前的域名证书错误。

## 6. 验证结果

可从 Mac 或服务器终端执行。公网速度以访问者网络上的结果为准。

```bash
curl --fail --silent --show-error --compressed \
  -D /tmp/cs2-state.headers -o /tmp/cs2-state.json \
  -w '首字节=%{time_starttransfer}s 总耗时=%{time_total}s 传输=%{size_download}字节\n' \
  https://www.hushang985.online/api/state
cat /tmp/cs2-state.headers
```

应看到 `Content-Encoding: gzip`、`ETag` 和 `Cache-Control: no-cache`；JSON 不再包含 Base64 图片。下面验证未变化返回 304，以及图片可以正常读取：

```bash
CS2_ETAG="$(sed -n 's/^[Ee][Tt][Aa][Gg]: *//p' /tmp/cs2-state.headers | tr -d '\r')"
curl --silent --show-error --compressed -D - -o /dev/null \
  -H "If-None-Match: $CS2_ETAG" https://www.hushang985.online/api/state
CS2_IMAGE="$(python3 - <<'PY'
import json
with open('/tmp/cs2-state.json') as f:
    s = json.load(f)
print(next(t['logo'] for t in s['teams'] if t['logo'].startswith('/media/')))
PY
)"
curl --fail --silent --show-error -I "https://www.hushang985.online$CS2_IMAGE"
curl --fail --silent --show-error -I https://hushang985.online/
curl --fail --silent --show-error -L -o /dev/null \
  -w '最终地址=%{url_effective} 状态=%{http_code}\n' https://hushang985.online/
```

预期：未发生后台修改时数据接口为 `304`；图片为 `200`，带 `max-age=31536000, immutable`；裸域名为 `301`，最终地址为 `https://www.hushang985.online/` 且返回 `200`。不要用 `curl -k`，否则无法验证证书修复。

浏览器刷新首页并打开赛事页，检查头像与队徽；开发者工具 Network 中保持 **Disable cache 未勾选**，观察后续 `/api/state` 为 304。修改并保存一项赛事数据，下一次应返回 200 并显示更新。图片按需加载，重新访问应使用缓存。登录、保存队伍及上传图片仍应正常。

## 7. 备份与回滚

之后备份不能只备份 SQLite，还要备份 `/var/lib/cs2web/media/`。做完整快照时暂停写入或停止服务，SQLite 使用 `.backup`，再归档 `media/`，两者一起保存。迁移脚本不会压缩原图或删除旧文件。

以下用于**本次上线验证失败，尚未恢复后台录入**时回滚。若上线后已有新录入，先备份当前数据库和图片；不要直接恢复旧数据库，否则会丢失新录入。

```bash
(
set -e
CS2_RESTORE_DIR="$(cat /root/cs2web-performance-last-backup)"
systemctl stop cs2web
tar -xzf "$CS2_RESTORE_DIR/code.tar.gz" -C /opt/cs2web
sqlite3 "$CS2_RESTORE_DIR/tournament.sqlite3" ".backup '/var/lib/cs2web/tournament.sqlite3'"
chown cs2web:cs2web /var/lib/cs2web/tournament.sqlite3
chmod 640 /var/lib/cs2web/tournament.sqlite3
tar -xzf "$CS2_RESTORE_DIR/nginx.tar.gz" -C /etc
if [ -L /etc/nginx/sites-enabled/cs2web-apex ] && \
   ! tar -tzf "$CS2_RESTORE_DIR/nginx.tar.gz" | grep -q '^nginx/sites-enabled/cs2web-apex$'; then
  unlink /etc/nginx/sites-enabled/cs2web-apex
fi
nginx -t
systemctl start cs2web
systemctl reload nginx
curl --fail http://127.0.0.1:5173/api/session
)
```

保留本次生成的图片与证书文件即可，回滚后的旧数据库仍使用原 Base64 图片；不必删除文件或撤销证书。若只需撤销裸域名跳转而保留性能优化，移除其 `sites-enabled` 链接并测试、重载 Nginx，不要回滚数据库。
