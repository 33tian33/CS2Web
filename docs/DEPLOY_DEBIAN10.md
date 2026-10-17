# 腾讯云轻量服务器部署教程（保留 Debian 10）

服务器公网 IP：`SERVER_IP`。保留 Debian 10，不重装，不跨大版本升级。

教程中的软件包下载均使用国内源：APT 使用阿里云 Debian 归档镜像，Python 源码使用华为云镜像，证书由腾讯云下载。官方文档链接仅用于查阅和核对校验值，不参与安装下载。

本文使用 `cs2.example.com` 作为域名占位符：请将全文中的该域名替换为你已经解析的真实域名。IP 地址不能代替 HTTPS 证书中的域名。没有连接服务器执行本文命令；本次已完成的是本地数据清理。

## 1. 本地数据已清空

2026-10-08 已备份并清空当前数据库：

- 清空前：48 支队伍、240 名选手、10 场比赛。
- 清空后：0 支队伍、0 名选手、0 场比赛。
- 赛事名称、赛季、日期和地点为空；BP、赛果、选手统计、赛段草稿、已启用赛段及旧操作日志已清空。
- 表单保留创建新赛事所需的初始数值，不代表已有赛事；首页显示“暂无赛事”。
- 正常启动不再自动生成演示数据。
- 学校选项、校徽、地图素材和后台功能保留。

本次备份：`data/backups/tournament.before-clear-20261008-150737.sqlite3`。

备份与旧的 `data/tournament.before-four-schools.sqlite3` 均不由网页读取，也不应随部署上传。首次部署不上传任何本地数据库，让服务器自动创建空库；不要恢复旧备份，否则旧赛事会回来。

## 2. 服务器准备

先在腾讯云控制台创建实例快照，保留已有数据。

轻量应用服务器 → 实例 → 防火墙，允许以下入站流量：

| 端口 | 协议 | 来源 | 用途 |
| --- | --- | --- | --- |
| 22 | TCP | 你的管理 IP | SSH；保留网页终端所需的现有规则 |
| 80 | TCP | 0.0.0.0/0 | HTTP 跳转 |
| 443 | TCP | 0.0.0.0/0 | HTTPS |

不要向公网开放 5173。若系统内已有防火墙，也需要允许 80、443；不要清空现有规则。

域名 A 记录应指向 `SERVER_IP`（使用 CDN 时按其接入配置）。本教程使用 IPv4；若有不可用的 AAAA 记录，请修正。中国大陆服务器需完成相应 ICP 备案后开放网站，解析成功不等于备案完成。

Debian 10 的官方 LTS 已于 2024-06-30 结束，归档源不会恢复安全维护。当前 Python `http.server` 后端仍为原型；Nginx 和 HTTPS 可以完成上线试运行，但不是完整生产服务改造。

## 3. 登录服务器

在 **Mac 终端**执行：

```bash
ssh root@SERVER_IP
```

若使用普通账号登录，执行 `sudo -i`。下文“服务器执行”均指 root 会话。

```bash
cat /etc/os-release
uname -m
```

确认是 Debian 10、x86_64。

## 4. 配置国内 Debian 10 归档源并安装依赖

**服务器执行：**

```bash
cp -a /etc/apt "/root/apt-backup-$(date +%Y%m%d-%H%M%S)"
cat /etc/apt/sources.list
ls -l /etc/apt/sources.list.d/

cat > /etc/apt/sources.list <<'SOURCES'
deb https://mirrors.aliyun.com/debian-archive/debian buster main contrib non-free
deb https://mirrors.aliyun.com/debian-archive/debian-security buster/updates main contrib non-free
SOURCES

apt-get update
```

若其他源报 404，只停用 `/etc/apt/sources.list.d/` 中对应的失效源。若归档源提示 Release 文件过期，在对应行的 `deb` 后加入 `[check-valid-until=no]`，保留其余地址不变。不要使用 `trusted=yes` 或关闭签名验证；签名错误需要单独解决。

采用 [阿里云 Debian 归档镜像](https://developer.aliyun.com/mirror/debian/) 的公网地址，适用于腾讯云服务器；不要使用阿里云 ECS 专用内网地址。APT 输出中应看到 `mirrors.aliyun.com`。若 `/etc/apt/sources.list.d/` 还有旧 Debian 官方源，备份后停用对应条目，避免继续从旧源下载；不要删除不相关的第三方源。若旧系统缺少 CA 导致 HTTPS 证书验证失败，可暂将这两条 APT 地址改为 `http://mirrors.aliyun.com/...`，保留签名验证，安装 `ca-certificates` 后恢复 HTTPS。

索引更新成功后安装：

```bash
apt-get install -y \
  ca-certificates curl xz-utils nano nginx sqlite3 openssl \
  build-essential pkg-config libssl-dev zlib1g-dev libbz2-dev \
  libreadline-dev libsqlite3-dev libffi-dev liblzma-dev
```

## 5. 从国内镜像独立安装 Python

不修改 `/usr/bin/python3`。项目要求 Python 3.9+，这里延续此前教程的 Python 3.11.15，避免中途混用版本和文件名；该版本并非最新安全补丁，后续应更新同系列补丁。

已核对华为云的两个国内镜像入口都列有源码包：

- [华为云软件仓库（首选）](https://repo.huaweicloud.com/python/3.11.15/)
- [华为云工具镜像（备用入口，同一服务商）](https://mirrors.huaweicloud.com/repository/toolkit/python/3.11.15/)

下载速度取决于服务器实际网络，未在 `SERVER_IP` 上测速。如果旧的官方源下载还在运行，先按 `Ctrl+C` 停止，再执行下面命令。重新下载会覆盖同名未完成文件；若已经完成安装验证，可直接继续第 6 步。

### 5.1 下载源码

**服务器执行：**

```bash
mkdir -p /usr/local/src
cd /usr/local/src
curl --fail --location --connect-timeout 15 --retry 2 \
  --output Python-3.11.15.tar.xz \
  https://repo.huaweicloud.com/python/3.11.15/Python-3.11.15.tar.xz
```

如果首选入口仍然慢，停止下载后改用备用入口：

```bash
cd /usr/local/src
curl --fail --location --connect-timeout 15 --retry 2 \
  --output Python-3.11.15.tar.xz \
  https://mirrors.huaweicloud.com/repository/toolkit/python/3.11.15/Python-3.11.15.tar.xz
```

两条下载命令选一条成功执行即可，不必重复下载。

### 5.2 核对源码包

使用 [Python 官方发布页](https://www.python.org/downloads/release/python-31115/) 的 SHA-256 校验值，确认镜像文件与官方源码一致：

```bash
cd /usr/local/src
sha256sum -c <<'SHA256'
272179ddd9a2e41a0fc8e42e33dfbdca0b3711aa5abf372d3f2d51543d09b625  Python-3.11.15.tar.xz
SHA256
```

只有显示 `Python-3.11.15.tar.xz: OK`（或本地语言的成功提示）才继续。若校验失败，重新下载，不要解压安装。

### 5.3 编译安装

```bash
cd /usr/local/src
tar -xf Python-3.11.15.tar.xz
cd Python-3.11.15
./configure --prefix=/opt/python311 --with-ensurepip=install
make -j1
make altinstall
```

逐条执行，出现错误时先解决再继续。编译使用本机 CPU，不受下载镜像影响；可能需要几分钟到几十分钟。`-j1` 减少小内存服务器的编译压力。`ensurepip` 使用源码自带的安装包，不需要访问 PyPI。

### 5.4 验证安装

```bash
/opt/python311/bin/python3.11 --version
/opt/python311/bin/python3.11 -c \
  "import ssl, sqlite3; print(ssl.OPENSSL_VERSION); print(sqlite3.sqlite_version)"
```

两条命令成功后直接继续第 6 步，不需要重新编译。

### 5.5 只有报错缺少 `_ssl` 或 `_sqlite3` 时才执行

这句话的意思是：Python 主程序可能安装成功了，但编译时没有找到某些系统开发库，导致相应功能没有编译进去。常见错误是 `ModuleNotFoundError: No module named '_ssl'` 或 `No module named '_sqlite3'`。

| 缺少的模块 | 用途 | 对应编译依赖 |
| --- | --- | --- |
| `_ssl` | Python 的 TLS/HTTPS 功能 | `libssl-dev` |
| `_sqlite3` | Python 读取和写入 SQLite 数据库，本网站需要 | `libsqlite3-dev` |

这两个模块随 Python 源码一起构建，不能靠 `pip install ssl` 或 `pip install sqlite3` 修复。安装系统开发库后，需要重新编译 Python 才能加入相应模块；Nginx 的 HTTPS 证书是另外一项配置。

**在服务器 root 会话执行，先确保第 4 步已经换为国内源：**

```bash
apt-get update
apt-get install -y build-essential pkg-config libssl-dev libsqlite3-dev
```

安装成功后，在前面解压的源码目录重新配置、编译、安装。`make distclean` 清理的是该源码目录的上次构建结果，不会清空网站数据库：

```bash
cd /usr/local/src/Python-3.11.15
make distclean
./configure --prefix=/opt/python311 --with-ensurepip=install
make -j1
make altinstall
```

逐条执行，某一步失败就先处理该步错误。重新验证：

```bash
/opt/python311/bin/python3.11 -c "import ssl; print(ssl.OPENSSL_VERSION)"
/opt/python311/bin/python3.11 -c "import sqlite3; print(sqlite3.sqlite_version)"
```

两条命令均输出版本号且无报错，才继续第 6 步。如果仍失败，保留完整报错及编译最后的模块检查输出，以判断是库版本、探测路径还是链接问题，不要反复盲目重编译。若网站服务此前已运行，修复验证成功后还需执行 `systemctl restart cs2web`。

第 6 步之后：程序由 Mac 通过 SCP 上传到 `SERVER_IP`，证书从腾讯云下载，其余为服务器本地配置。当前项目无第三方 Python 运行依赖，不需要另外配置 pip 镜像或安装 npm 包。

## 6. 部署前修改域名访问配置

**当前本地 `server.py` 已完成本节修改，并修复粘贴造成的缩进和残留代码错误。使用当前项目请跳过下面的手动替换，直接进行第 7 步上传。** 以下替换说明仅供仍使用旧版文件时参考，不要重复粘贴。

在 **Mac** 编辑项目 `server.py`。

在 `PORT = ...` 下方加入（已有 `os`、`urlparse` 导入）：

```python
PUBLIC_ORIGIN = os.environ.get(
    'CS2_PUBLIC_ORIGIN', f'http://127.0.0.1:{PORT}'
).rstrip('/')
PUBLIC_HOST = urlparse(PUBLIC_ORIGIN).netloc
COOKIE_SECURE = '; Secure' if PUBLIC_ORIGIN.startswith('https://') else ''
```

把 `do_POST` 开头原有的 Host 和 Origin 两项检查替换为以下内容，保留方法内缩进：

```python
        if self.headers.get('Host') not in [PUBLIC_HOST, f'127.0.0.1:{PORT}', f'localhost:{PORT}']:
            return self.json({'error': '无效的访问地址'}, 403)
        if self.headers.get('Origin') not in [None, PUBLIC_ORIGIN, f'http://127.0.0.1:{PORT}', f'http://localhost:{PORT}']:
            return self.json({'error': '不允许跨站修改'}, 403)
```

登录接口中，将原来的 `ip=self.client_address[0]; attempts=...` 一行替换为：

```python
                ip = self.headers.get('X-Real-IP', self.client_address[0])
                attempts = [x for x in ATTEMPTS.get(ip, []) if x > time.time() - 300]
```

登录成功和退出登录设置 Cookie 的两行分别改为：

```python
                return self.json({'ok':True},cookie=f'cs2_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800{COOKIE_SECURE}')
```

```python
                return self.json({'ok':True},cookie=f'cs2_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0{COOKIE_SECURE}')
```

继续使用 `127.0.0.1` 监听地址。第 11 节 Nginx 会覆盖 `X-Real-IP`，Python 不直接接受公网连接。

## 7. 上传程序（不上传任何数据库）

**Mac 终端：**

```bash
cd "/Users/tian33/Project CS2Web"
COPYFILE_DISABLE=1 tar -czf /tmp/cs2web.tar.gz \
  server.py tournament.py public
scp /tmp/cs2web.tar.gz root@SERVER_IP:/root/
```

不要打包整个 `data` 目录。本次空白部署让服务器首次启动自行建库。

**服务器执行（首次部署）：**

```bash
adduser --system --group --no-create-home cs2web
install -d -m 755 /opt/cs2web
install -d -o cs2web -g cs2web -m 750 /var/lib/cs2web
tar -xzf /root/cs2web.tar.gz -C /opt/cs2web
chown -R root:root /opt/cs2web
chmod -R u=rwX,go=rX /opt/cs2web
ls -la /var/lib/cs2web
```

如果用户或目录已经存在，无需重复创建。如果 `/var/lib/cs2web/tournament.sqlite3` 已存在，程序会保留其数据，不会自动清空。此次清理仅针对本地；不要把本文当成删除服务器既有数据库的指令。

## 8. 设置管理员密码和环境变量

**服务器执行：**

```bash
openssl rand -hex 24
install -m 600 /dev/null /etc/cs2web.env
nano /etc/cs2web.env
```

仅首次部署使用上面的 `install` 命令；已有环境文件时直接编辑，避免清空旧配置。保存生成的密码，填写：

```ini
PORT=5173
CS2_DB=/var/lib/cs2web/tournament.sqlite3
CS2_PUBLIC_ORIGIN=https://fdcs2.online
CS2_ADMIN_PASSWORD=替换为生成的随机密码
PYTHONUNBUFFERED=1
PYTHONDONTWRITEBYTECODE=1
```

替换真实域名。管理员用户名为 `admin`，不要使用本地演示密码。Nano 保存：`Ctrl+O`、回车、`Ctrl+X`。

## 9. 配置开机启动

**服务器执行：**

```bash
nano /etc/systemd/system/cs2web.service
```

写入：

```ini
[Unit]
Description=CS2 Website
After=network.target

[Service]
Type=simple
User=cs2web
Group=cs2web
WorkingDirectory=/opt/cs2web
EnvironmentFile=/etc/cs2web.env
ExecStart=/opt/python311/bin/python3.11 /opt/cs2web/server.py
Restart=on-failure
RestartSec=3
UMask=0027

[Install]
WantedBy=multi-user.target
```

启动并检查：

```bash
systemctl daemon-reload
systemctl enable --now cs2web
systemctl status cs2web --no-pager
curl --fail http://127.0.0.1:5173/api/session
```

应显示 `active (running)`，接口返回 `{"authenticated": false}`。失败时查看：

```bash
journalctl -u cs2web -n 80 --no-pager
```

## 10. 申请 HTTPS 证书

腾讯云控制台 → SSL 证书 → 为实际域名申请证书 → 完成域名验证 → 签发后下载 **Nginx 格式**。证书有效期、费用以控制台为准。下载包里找到完整证书链（通常为 `bundle.crt`）和私钥（`.key`）。

**服务器：**

```bash
install -d -m 700 /etc/nginx/ssl/cs2web
```

**Mac：将路径改成实际下载文件路径。**

```bash
scp "/你的证书目录/域名_bundle.crt" \
  root@SERVER_IP:/etc/nginx/ssl/cs2web/fullchain.crt
scp "/你的证书目录/域名.key" \
  root@SERVER_IP:/etc/nginx/ssl/cs2web/private.key
```

**服务器：**

```bash
chmod 644 /etc/nginx/ssl/cs2web/fullchain.crt
chmod 600 /etc/nginx/ssl/cs2web/private.key
```

不要把私钥放入 `public` 目录或项目仓库。

## 11. 配置 Nginx

**服务器：**

```bash
nano /etc/nginx/sites-available/cs2web
```

写入以下配置，替换所有 `cs2.example.com`：

```nginx
server {
    listen 80;
    server_name fdcs2.online;
    return 301 https://fdcs2.online$request_uri;
}

server {
    listen 443 ssl;
    server_name fdcs2.online;

    ssl_certificate /etc/nginx/ssl/cs2web/fullchain.crt;
    ssl_certificate_key /etc/nginx/ssl/cs2web/private.key;
    ssl_protocols TLSv1.2 TLSv1.3;

    root /opt/cs2web/public;
    index index.html;
    client_max_body_size 8m;

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
```

启用：

```bash
ln -s /etc/nginx/sites-available/cs2web /etc/nginx/sites-enabled/cs2web
nginx -t
```

符号链接已存在时不用重复创建。只有检查通过后再执行：

```bash
systemctl enable nginx
systemctl restart nginx
```

不要删除其他网站配置。端口冲突可用 `ss -lntp` 查看。网站使用 hash 路由，不需要额外配置前端路由回退。

## 12. 验证空白网站并创建第一场赛事

**Mac：**

```bash
dig +short A cs2.example.com
dig +short AAAA cs2.example.com
```

未使用 CDN 时 A 记录应是 `SERVER_IP`。浏览器访问（替换真实域名）：

- 首页：`https://cs2.example.com/`，应显示“0 项赛事”“暂无赛事”。
- 当前赛事：`https://cs2.example.com/#/event`，应显示“暂无赛事”。
- 后台：`https://cs2.example.com/#/admin`。

用 `admin` 和第 8 节的密码登录。依次完成：

1. 在“赛事与赛制”填写真实名称、赛季、日期、地点及赛制并保存。
2. 在“队伍与选手”创建队伍和阵容；先按实际队伍数设置足够的分组容量。
3. 在“赛段规划器”配置并启用赛段，或在“赛程与数据”手动添加对阵。
4. 刷新前台确认数据。
5. 执行 `systemctl restart cs2web`，确认数据仍在。当前登录会话在内存中，重启需重新登录。

清空后不应看到旧赛事、48 支演示队伍或旧赛果。若看到了，检查是否用了旧程序、旧数据库或浏览器缓存；不要直接覆盖线上数据。

## 13. 备份

**服务器：**

```bash
install -d -m 700 /root/cs2web-backups
sqlite3 /var/lib/cs2web/tournament.sqlite3 \
  ".backup '/root/cs2web-backups/tournament-$(date +%Y%m%d-%H%M%S).sqlite3'"
ls -lh /root/cs2web-backups
```

SQLite `.backup` 可在服务运行时创建一致备份。**Mac 下载：**

```bash
mkdir -p "$HOME/Downloads/cs2web-backups"
scp 'root@SERVER_IP:/root/cs2web-backups/*.sqlite3' \
  "$HOME/Downloads/cs2web-backups/"
```

赛事开始前、重要数据录入后、更新程序前进行备份。

## 14. 更新网站和证书

更新程序仍然只打包 `server.py tournament.py public`，不上传本地数据库。

**Mac：**

```bash
cd "/Users/tian33/Project CS2Web"
COPYFILE_DISABLE=1 tar -czf /tmp/cs2web-update.tar.gz \
  server.py tournament.py public
scp /tmp/cs2web-update.tar.gz root@SERVER_IP:/root/
```

先按第 13 节备份线上数据库，再在服务器执行：

```bash
tar -czf "/root/cs2web-code-$(date +%Y%m%d-%H%M%S).tar.gz" \
  -C /opt/cs2web server.py tournament.py public
systemctl stop cs2web
tar -xzf /root/cs2web-update.tar.gz -C /opt/cs2web
chown -R root:root /opt/cs2web
chmod -R u=rwX,go=rX /opt/cs2web
systemctl start cs2web
systemctl status cs2web --no-pager
```

更新后检查登录、保存和前台显示。后续若有删除或重命名文件，部署时还要处理遗留文件。

本教程使用手动证书，不自动续期。到期前重新签发并替换证书、私钥，检查后重载：

```bash
nginx -t && systemctl reload nginx
```

## 15. 排障

| 问题 | 检查 |
| --- | --- |
| 连接超时 | DNS、腾讯云防火墙、系统防火墙 |
| 证书警告 | 证书域名、有效期、完整证书链 |
| API 返回 502 | `systemctl status cs2web` 和服务日志 |
| 无效的访问地址 | 第 6 节 Host 检查、Nginx Host 和真实域名 |
| 不允许跨站修改 | `CS2_PUBLIC_ORIGIN` 与浏览器地址，含 `https://` |
| 数据库只读 | `/var/lib/cs2web` 目录和数据库属于 `cs2web` |
| 上传返回 413 | Nginx 8m 限制及 Python 8,000,000 字节限制 |
| 修改环境变量没生效 | `systemctl restart cs2web` |

```bash
journalctl -u cs2web -n 100 --no-pager
tail -n 100 /var/log/nginx/error.log
```

## 官方参考

- [Debian 10 LTS 结束公告](https://www.debian.org/News/2024/20240615.en.html)
- [阿里云 Debian 归档镜像配置](https://developer.aliyun.com/mirror/debian/)
- [Python 编译配置文档](https://docs.python.org/3.11/using/configure.html)
- [Python 3.11.15](https://www.python.org/downloads/release/python-31115/)
- [Python http.server 使用限制](https://docs.python.org/3/library/http.server.html)
- [腾讯云防火墙](https://cloud.tencent.com.cn/document/product/1207/136745)
- [腾讯云备案说明](https://cloud.tencent.com/document/api/243/37402)
- [腾讯云 SSL 证书部署](https://cloud.tencent.com/document/product/400/4143)
