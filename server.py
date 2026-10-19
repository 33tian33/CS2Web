"""Local CS2 tournament prototype. Run: python3 server.py."""
import os, json, sqlite3, secrets, hashlib, hmac, time, base64, binascii, re, tempfile
import tournament
from datetime import datetime, timedelta, timezone
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from http.cookies import SimpleCookie
from urllib.parse import urlparse

ROOT = Path(__file__).parent
DB = Path(os.environ.get('CS2_DB', str(ROOT / 'data/tournament.sqlite3')))
PORT = int(os.environ.get('PORT', '5173'))
PUBLIC_ORIGIN = os.environ.get(
    'CS2_PUBLIC_ORIGIN', f'http://127.0.0.1:{PORT}'
).rstrip('/')
PUBLIC_HOST = urlparse(PUBLIC_ORIGIN).netloc
COOKIE_SECURE = '; Secure' if PUBLIC_ORIGIN.startswith('https://') else ''
SCHOOLS = [
    dict(id='fudan', name='复旦大学', short='复旦', color='#75b3ed', emblem='/assets/schools/fudan.png'),
    dict(id='ecnu', name='华东师范大学', short='华师', color='#ef787d', emblem='/assets/schools/ecnu.png'),
    dict(id='sjtu', name='上海交通大学', short='交大', color='#f1a063', emblem='/assets/schools/sjtu.png'),
    dict(id='tongji', name='同济大学', short='同济', color='#74d7c9', emblem='/assets/schools/tongji.png'),
]
SCHOOL_NAMES = [s['name'] for s in SCHOOLS]
POSITIONS = ['指挥', '狙击手', '突破手', '补枪手', '自由人']
PERFECT_RANKS = ['', 'D', 'C', 'C+', 'C++', 'B', 'B+', 'B++', 'A', 'A+', 'A++', '普通S', '黄金S', '钻石S', '魔王S']
SESSIONS = {}
ATTEMPTS = {}
PASSWORD = os.environ.get('CS2_ADMIN_PASSWORD', 'cs2local')
PASSWORD_HASH = hashlib.pbkdf2_hmac('sha256', PASSWORD.encode(), b'cs2-local-admin', 260000)
BEIJING_TZ = timezone(timedelta(hours=8))


def connect():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys = ON')
    return con


def initialize():
    DB.parent.mkdir(parents=True, exist_ok=True)
    with connect() as con:
        con.executescript('''
        CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS teams (id INTEGER PRIMARY KEY, name TEXT NOT NULL, school TEXT NOT NULL, tag TEXT NOT NULL, color TEXT NOT NULL, logo TEXT NOT NULL DEFAULT '', group_name TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS players (id INTEGER PRIMARY KEY, team_id INTEGER NOT NULL REFERENCES teams(id), nickname TEXT NOT NULL, avatar TEXT NOT NULL DEFAULT '', role TEXT NOT NULL DEFAULT '选手');
        CREATE TABLE IF NOT EXISTS matches (id INTEGER PRIMARY KEY, team_a INTEGER REFERENCES teams(id), team_b INTEGER REFERENCES teams(id), stage TEXT NOT NULL, round_name TEXT NOT NULL, bo INTEGER NOT NULL CHECK(bo IN (2,3,5)), status TEXT NOT NULL, time TEXT NOT NULL, maps TEXT NOT NULL DEFAULT '[]', bp TEXT NOT NULL DEFAULT '[]', stats TEXT NOT NULL DEFAULT '[]');
        CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, action TEXT NOT NULL);
        ''')
        con.execute('INSERT OR IGNORE INTO settings VALUES (1,?)', (json.dumps(default_config()),))
        migrate_sponsors(con)
        migrate_rosters(con)
        if 'perfect_rank' not in {r['name'] for r in con.execute('PRAGMA table_info(players)')}:
            con.execute("ALTER TABLE players ADD COLUMN perfect_rank TEXT NOT NULL DEFAULT ''")
        con.execute("""UPDATE players SET perfect_rank = CASE perfect_rank
            WHEN 'S青铜' THEN '普通S' WHEN 'S白银' THEN '黄金S'
            WHEN 'S黄金' THEN '钻石S' WHEN 'S钻石' THEN '魔王S' END
            WHERE perfect_rank IN ('S青铜','S白银','S黄金','S钻石')""")
        tournament.migrate(con)
        start_due_matches(con)


def migrate_sponsors(con):
    con.execute('''CREATE TABLE IF NOT EXISTS sponsors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL REFERENCES settings(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        image TEXT NOT NULL,
        fit TEXT NOT NULL CHECK(fit IN ('cover','fill'))
    )''')


def default_config():
    return dict(name='', season='', start='', end='', location='',
                groupCount=1, teamsPerGroup=4, advance=2, winPoints=3,
                drawPoints=1, lossPoints=0, tieBreak='map,round,h2h',
                groupBO=2, playoffBO=3, finalBO=5, thirdPlace=False)


def migrate_rosters(con):
    if con.execute('PRAGMA user_version').fetchone()[0] >= 1:
        return
    con.execute("ALTER TABLE teams ADD COLUMN introduction TEXT NOT NULL DEFAULT ''")
    con.execute("ALTER TABLE teams ADD COLUMN show_school_badge INTEGER NOT NULL DEFAULT 1 CHECK(show_school_badge IN (0,1))")
    con.execute("ALTER TABLE players ADD COLUMN position TEXT NOT NULL DEFAULT '自由人'")
    con.execute("ALTER TABLE players ADD COLUMN school TEXT NOT NULL DEFAULT ''")
    con.execute('UPDATE players SET school=(SELECT school FROM teams WHERE teams.id=players.team_id)')
    con.execute('PRAGMA user_version = 1')


def start_due_matches(con):
    now = datetime.now(BEIJING_TZ).strftime('%Y-%m-%dT%H:%M')
    con.execute("""UPDATE matches SET status='live'
        WHERE status='scheduled' AND time!='' AND time<=?
        AND team_a IS NOT NULL AND team_b IS NOT NULL""", (now,))


def get_state():
    with connect() as con:
        start_due_matches(con)
        cfg=json.loads(con.execute('SELECT value FROM settings WHERE id=1').fetchone()[0])
        teams=[dict(r) for r in con.execute('SELECT teams.*, (SELECT count(*) FROM players WHERE team_id=teams.id) AS player_count FROM teams ORDER BY id')]
        for t in teams: t['show_school_badge']=bool(t['show_school_badge'])
        players=[dict(r) for r in con.execute('SELECT * FROM players')]
        matches=[dict(r) for r in con.execute('SELECT * FROM matches ORDER BY time,id')]
        for m in matches:
            for key in ['maps','bp','stats','bp_config']: m[key]=json.loads(m[key])
        sponsors=[dict(r) for r in con.execute('SELECT * FROM sponsors WHERE event_id=1 ORDER BY id')]
        return dict(config=cfg,schools=SCHOOLS,perfect_ranks=PERFECT_RANKS,teams=teams,players=players,matches=matches,sponsors=sponsors,flow=tournament.state(con,matches,cfg))


def integer(value, low, high):
    if isinstance(value,bool) or not isinstance(value,int) or not low<=value<=high: raise ValueError('数字超出允许范围')
    return value


def short(value, limit=120):
    if not isinstance(value,str) or not value.strip() or len(value)>limit: raise ValueError('请填写有效的文本内容')
    return value.strip()


def image_url(value, max_length=1000000):
    if not isinstance(value,str) or len(value)>max_length: raise ValueError('图片过大')
    if not value or value.startswith('https://'): return value
    if re.fullmatch(r'/media/[0-9a-f]{64}\.(png|jpg|webp)',value):
        if not (DB.parent/value.lstrip('/')).is_file(): raise ValueError('图片文件不存在')
        return value
    match=re.fullmatch(r'data:image/(png|jpeg|webp);base64,(.+)',value)
    if not match: raise ValueError('请使用 HTTPS 图片地址或 PNG/JPG/WebP 图片')
    kind,encoded=match.groups()
    try:
        data=base64.b64decode(encoded,validate=True)
    except binascii.Error:
        raise ValueError('图片 Base64 数据无效') from None
    valid=(kind=='png' and data.startswith(b'\x89PNG\r\n\x1a\n') or
           kind=='jpeg' and data.startswith(b'\xff\xd8\xff') or
           kind=='webp' and data.startswith(b'RIFF') and data[8:12]==b'WEBP')
    if not valid: raise ValueError('图片内容与格式不匹配')
    extension='jpg' if kind=='jpeg' else kind
    name=hashlib.sha256(data).hexdigest()+'.'+extension
    directory=DB.parent/'media'
    directory.mkdir(exist_ok=True)
    target=directory/name
    if not target.exists():
        with tempfile.NamedTemporaryFile(dir=directory,delete=False) as file:
            file.write(data)
        os.replace(file.name,target)
    return '/media/'+name


def optional_date(value, precise=False):
    if value == '': return ''
    fmt = '%Y-%m-%dT%H:%M' if precise else '%Y-%m-%d'
    if not isinstance(value, str): raise ValueError('日期时间无效')
    try:
        parsed = datetime.strptime(value, fmt)
    except ValueError:
        raise ValueError('日期时间无效')
    return parsed.strftime(fmt)


def validate_config(c):
    c['name']=short(c.get('name'))
    for k in ['season','location']: c[k]=short(c.get(k)) if c.get(k) != '' else ''
    for k in ['start','end']: c[k]=optional_date(c.get(k))
    integer(c.get('groupCount'),1,16); integer(c.get('teamsPerGroup'),2,16); integer(c.get('advance'),1,c['teamsPerGroup'])
    for k in ['winPoints','drawPoints','lossPoints']: integer(c.get(k),0,20)
    if c.get('groupBO') not in [2,3,5] or c.get('playoffBO') not in [3,5] or c.get('finalBO') not in [3,5]: raise ValueError('BO 设置无效')
    if c.get('tieBreak') not in ['map,round,h2h','h2h,map,round','round,map,h2h']: raise ValueError('同分规则无效')
    if not isinstance(c.get('thirdPlace'),bool): raise ValueError('季军赛设置无效')
    if c['start'] and c['end'] and c['end']<c['start']: raise ValueError('结束日期不能早于开始日期')
    return c


def validate_match(m,con):
    integer(m.get('bo'),2,5)
    if m['bo'] not in [2,3,5]: raise ValueError('仅支持 BO2、BO3、BO5')
    if m.get('stage') not in ['group','playoff']: raise ValueError('赛事阶段无效')
    if m['stage']=='playoff' and m['bo']==2: raise ValueError('淘汰赛请选择 BO3 或 BO5')
    if m.get('status') not in ['scheduled','live','finished']: raise ValueError('比赛状态无效')
    m['round_name']=short(m.get('round_name'))
    m['time']=optional_date(m.get('time'), precise=True)
    ids={r[0] for r in con.execute('SELECT id FROM teams')}
    for k in ['team_a','team_b']:
        if m.get(k) is not None and m[k] not in ids: raise ValueError('队伍不存在')
    if m.get('team_a') and m['team_a']==m.get('team_b'): raise ValueError('对阵双方不能是同一队伍')
    if m['status']!='scheduled' and (not m.get('team_a') or not m.get('team_b')): raise ValueError('请先选择对阵双方')
    maps=m.get('maps',[])
    if not isinstance(maps,list) or len(maps)>m['bo']: raise ValueError('地图数量超过 BO 设置，请先调整已有数据')
    wa=wb=0
    for x in maps:
        short(x.get('name')); integer(x.get('scoreA'),0,100); integer(x.get('scoreB'),0,100)
        if x['scoreA']==x['scoreB']: raise ValueError('请只录入已结束地图，回合比分不能相同')
        if m['bo']!=2 and max(wa,wb)>=m['bo']//2+1: raise ValueError('已决出胜负，不能继续添加地图')
        wa+=x['scoreA']>x['scoreB']; wb+=x['scoreB']>x['scoreA']
    if m['status']=='finished' and ((m['bo']==2 and len(maps)!=2) or (m['bo']!=2 and max(wa,wb)!=m['bo']//2+1)): raise ValueError('已结束比赛的地图赛果不完整')
    if maps and (not m.get('team_a') or not m.get('team_b')): raise ValueError('录入地图前需要选择双方队伍')
    if m['stage']=='group' and not m.get('flow_key') and m.get('team_a') and m.get('team_b'):
        groups=[con.execute('SELECT group_name FROM teams WHERE id=?',(m[k],)).fetchone()[0] for k in ['team_a','team_b']]
        if groups[0]!=groups[1]: raise ValueError('小组赛双方必须属于同一小组')
    players={r[0] for r in con.execute('SELECT id FROM players WHERE team_id IN (?,?)',(m.get('team_a'),m.get('team_b')))}
    if m.get('mvp_player_id') is not None:
        integer(m['mvp_player_id'],1,2147483647)
        if m['mvp_player_id'] not in players: raise ValueError('MVP 必须属于本场参赛队伍')
    seen=set()
    for s in m.get('stats',[]):
        integer(s.get('map'),0,len(maps)-1)
        if s.get('playerId') not in players: raise ValueError('选手不属于本场参赛队伍')
        key=(s['map'],s['playerId'])
        if key in seen: raise ValueError('同一地图的选手数据重复')
        seen.add(key)
        for k in ['kills','deaths','assists']: integer(s.get(k),0,200)
        if not isinstance(s.get('rating'),(int,float)) or not 0<=s['rating']<=10: raise ValueError('Rating 超出范围')
    if m.get('bp_config'):
        tournament.validate_bp(m,m['bp'],m['bp_config'])
    else:
        for b in m.get('bp',[]):
            if b.get('teamId') not in [m.get('team_a'),m.get('team_b')] or b.get('action') not in ['Ban','Pick','Decider']: raise ValueError('BP 数据无效')
            short(b.get('map'))
    if m.get('id'):
        old=con.execute('SELECT * FROM matches WHERE id=?',(m['id'],)).fetchone()
        if old:
            old_maps=json.loads(old['maps'])
            for i,result in enumerate(old_maps):
                if i<len(maps) and maps[i]['name']!=result['name'] and maps[i]['name'] not in [x['name'] for x in old_maps] and any(x['map']==i for x in m.get('stats',[])):
                    raise ValueError('更换地图前请先清除该图选手数据')
    return m


class TournamentHTTPServer(ThreadingHTTPServer):
    def service_actions(self):
        now = time.monotonic()
        if now < getattr(self, '_next_match_check', 0):
            return
        with connect() as con:
            start_due_matches(con)
        self._next_match_check = now + 1


class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(ROOT/'public'),**kwargs)
    def json(self,obj,status=200,cookie=None,conditional=False):
        data=json.dumps(obj,ensure_ascii=False).encode()
        etag='W/"'+hashlib.sha256(data).hexdigest()+'"' if conditional else None
        unchanged=conditional and self.headers.get('If-None-Match')==etag
        self.send_response(304 if unchanged else status)
        self.send_header('Cache-Control','no-cache' if conditional else 'no-store')
        if etag: self.send_header('ETag',etag)
        if unchanged:
            self.end_headers()
            return
        self.send_header('Content-Type','application/json; charset=utf-8')
        if cookie: self.send_header('Set-Cookie',cookie)
        self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
    def authorized(self):
        cookie=SimpleCookie(self.headers.get('Cookie',''))
        token=cookie.get('cs2_session')
        return bool(token and SESSIONS.get(token.value,0)>time.time())
    def do_GET(self):
        if self.path=='/api/state': return self.json(get_state(),conditional=True)
        if self.path=='/api/session': return self.json({'authenticated':self.authorized()})
        if self.path.startswith('/api/'): return self.json({'error':'接口不存在'},404)
        super().do_GET()
    def send_head(self):
        path=urlparse(self.path).path
        if not path.startswith('/media/'): return super().send_head()
        if not re.fullmatch(r'/media/[0-9a-f]{64}\.(png|jpg|webp)',path):
            self.send_error(404)
            return None
        try:
            file=(DB.parent/path.lstrip('/')).open('rb')
        except FileNotFoundError:
            self.send_error(404)
            return None
        etag='"'+Path(path).stem+'"'
        unchanged=self.headers.get('If-None-Match')==etag
        self.send_response(304 if unchanged else 200)
        self.send_header('ETag',etag)
        self.send_header('Cache-Control','public, max-age=31536000, immutable')
        self.send_header('X-Content-Type-Options','nosniff')
        if unchanged:
            self.end_headers(); file.close()
            return None
        self.send_header('Content-Type',self.guess_type(path))
        self.send_header('Content-Length',str(os.fstat(file.fileno()).st_size))
        self.end_headers()
        return file
    def do_POST(self):
        if self.headers.get('Host') not in [PUBLIC_HOST, f'127.0.0.1:{PORT}', f'localhost:{PORT}']:
            return self.json({'error': '无效的访问地址'}, 403)
        if self.headers.get('Origin') not in [None, PUBLIC_ORIGIN, f'http://127.0.0.1:{PORT}', f'http://localhost:{PORT}']:
            return self.json({'error': '不允许跨站修改'}, 403)
        if self.headers.get('Content-Type','').split(';')[0]!='application/json': return self.json({'error':'需要 JSON 请求'},415)
        try:
            length=int(self.headers.get('Content-Length',0))
            if length>8000000: return self.json({'error':'请求内容过大'},413)
            body=json.loads(self.rfile.read(length))
            if self.path=='/api/simulate':
                if not isinstance(body,dict): raise ValueError('模拟赛果格式无效')
                with connect() as con:
                    con.execute('BEGIN')
                    plan=json.loads(con.execute('SELECT active FROM flow WHERE id=1').fetchone()[0])
                    cfg=json.loads(con.execute('SELECT value FROM settings WHERE id=1').fetchone()[0])
                    names={r['id']:r['name'] for r in con.execute('SELECT id,name FROM teams')}
                    matches=tournament.load_matches(con)
                    if body.get('revision')!=tournament.simulation_revision(plan,matches,cfg,names):
                        raise ValueError('真实赛果或赛制已更新，请同步赛果后重新模拟')
                    result=tournament.simulate(plan,matches,cfg,names,body.get('results'))
                return self.json(result)
            if self.path=='/api/login':
                ip = self.headers.get('X-Real-IP', self.client_address[0])
                attempts = [x for x in ATTEMPTS.get(ip, []) if x > time.time() - 300]
                if len(attempts)>=10: return self.json({'error':'尝试次数过多，请 5 分钟后重试'},429)
                digest=hashlib.pbkdf2_hmac('sha256', str(body.get('password','')).encode(), b'cs2-local-admin', 260000)
                if body.get('username')!='admin' or not hmac.compare_digest(digest,PASSWORD_HASH):
                    ATTEMPTS[ip]=attempts+[time.time()]; return self.json({'error':'账号或密码不正确'},401)
                token=secrets.token_urlsafe(32); SESSIONS[token]=time.time()+28800
                return self.json({'ok':True},cookie=f'cs2_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800{COOKIE_SECURE}')
            if not self.authorized(): return self.json({'error':'请先登录管理员账号'},401)
            if self.path=='/api/logout':
                cookie=SimpleCookie(self.headers.get('Cookie','')); token=cookie.get('cs2_session')
                if token: SESSIONS.pop(token.value,None)
                return self.json({'ok':True},cookie=f'cs2_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0{COOKIE_SECURE}')
            with connect() as con:
                if self.path=='/api/config':
                    cfg=validate_config(body)
                    current=list(con.execute('SELECT group_name,count(*) AS n FROM teams GROUP BY group_name'))
                    if any(ord(r['group_name'])-65>=cfg['groupCount'] or r['n']>cfg['teamsPerGroup'] for r in current): raise ValueError('现有队伍超出新分组容量，请先调整队伍分组')
                    con.execute('UPDATE settings SET value=? WHERE id=1',(json.dumps(cfg),))
                elif self.path=='/api/sponsor':
                    cfg=json.loads(con.execute('SELECT value FROM settings WHERE id=1').fetchone()[0])
                    if not cfg['name']: raise ValueError('请先保存赛事信息')
                    name=short(body.get('name'))
                    fit=body.get('fit')
                    if fit not in ['cover','fill']: raise ValueError('请选择裁切或拉伸')
                    if not body.get('image'): raise ValueError('请上传赞助商图片')
                    image=image_url(body['image'],7000000)
                    if body.get('id') is not None:
                        sid=integer(body['id'],1,2147483647)
                        if not con.execute('UPDATE sponsors SET name=?,image=?,fit=? WHERE id=? AND event_id=1',(name,image,fit,sid)).rowcount:
                            raise ValueError('赞助商不存在')
                    else:
                        con.execute('INSERT INTO sponsors(event_id,name,image,fit) VALUES (1,?,?,?)',(name,image,fit))
                elif self.path=='/api/sponsor/delete':
                    sid=integer(body.get('id'),1,2147483647)
                    if not con.execute('DELETE FROM sponsors WHERE id=? AND event_id=1',(sid,)).rowcount:
                        raise ValueError('赞助商不存在')
                elif self.path in ['/api/flow/save','/api/flow/check','/api/flow/activate']:
                    plan=tournament.validate_plan(body,{r[0] for r in con.execute('SELECT id FROM teams')},self.path!='/api/flow/save')
                    if self.path=='/api/flow/activate': tournament.activate(con,plan)
                    elif self.path=='/api/flow/save': con.execute('UPDATE flow SET draft=? WHERE id=1',(json.dumps(plan),))
                elif self.path=='/api/bp':
                    m=next((x for x in tournament.load_matches(con) if x['id']==body.get('matchId')),None)
                    if not m: raise ValueError('比赛不存在')
                    if body.get('base')!={'bp':m['bp'],'config':m['bp_config'],'bo':m['bo'],'teams':[m['team_a'],m['team_b']]}: raise ValueError('比赛已更新，请重新打开 BP 面板')
                    if body.get('clear'):
                        steps=[]; config={}
                    else:
                        config=body['config'];steps=tournament.validate_bp(m,body['steps'],config)
                    con.execute('UPDATE matches SET bp=?,bp_config=? WHERE id=?',(json.dumps(steps),json.dumps(config),m['id']))
                elif self.path=='/api/match':
                    old=next((x for x in tournament.load_matches(con) if x['id']==body.get('id')),None)
                    body['flow_key']=old['flow_key'] if old else None
                    edit=body.get('bp_edit')
                    if edit and old and edit.get('base')!={'bp':old['bp'],'config':old['bp_config'],'bo':old['bo'],'teams':[old['team_a'],old['team_b']]}:
                        raise ValueError('比赛 BP 已更新，请重新打开对阵')
                    if old:
                        body['bp']=old['bp'];body['bp_config']=old['bp_config']
                        if any(body.get(k)!=old[k] for k in ['bo','team_a','team_b']):
                            if any(b['map'] for b in old['bp']) and not (edit and not edit['config']): raise ValueError('调整 BO 或队伍前，请清空本场 BP')
                            body['bp']=[];body['bp_config']={} 
                        if old['flow_key'] and any(body.get(k)!=old[k] for k in ['stage','team_a','team_b']): raise ValueError('请通过赛段规划器调整队伍来源或赛事阶段')
                    else:
                        body['bp']=[];body['bp_config']={}
                    if edit:
                        body['bp_config']=edit['config']
                        body['bp']=edit['steps'] if edit['config'] else []
                    m=validate_match(body,con)
                    finished_at = (old['finished_at'] if old and old['status']=='finished' else datetime.now(BEIJING_TZ).isoformat(timespec='seconds')) if m['status']=='finished' else ''
                    vals=tuple(m.get(k) for k in ['team_a','team_b','stage','round_name','bo','status','time'])+tuple(json.dumps(m.get(k,[])) for k in ['maps','bp','stats'])+(json.dumps(m['bp_config']),m.get('mvp_player_id'),finished_at)
                    if m.get('id'):
                        cur=con.execute('UPDATE matches SET team_a=?,team_b=?,stage=?,round_name=?,bo=?,status=?,time=?,maps=?,bp=?,stats=?,bp_config=?,mvp_player_id=?,finished_at=? WHERE id=?',vals+(m['id'],))
                        if cur.rowcount!=1: raise ValueError('比赛不存在')
                    else: con.execute('INSERT INTO matches(team_a,team_b,stage,round_name,bo,status,time,maps,bp,stats,bp_config,mvp_player_id,finished_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',vals)
                elif self.path=='/api/team':
                    t=body; cfg=json.loads(con.execute('SELECT value FROM settings WHERE id=1').fetchone()[0])
                    t['name']=short(t.get('name'))
                    t['tag']=short(t.get('tag'),4)
                    if t.get('school') not in SCHOOL_NAMES: raise ValueError('请选择参赛学校')
                    if not isinstance(t.get('show_school_badge'),bool): raise ValueError('校徽角标设置无效')
                    intro=t.get('introduction','')
                    if not isinstance(intro,str) or len(intro)>100 or len(intro.splitlines())>2: raise ValueError('队伍介绍限 100 字、最多两行')
                    if t.get('id') and not con.execute('SELECT id FROM teams WHERE id=?',(t['id'],)).fetchone(): raise ValueError('队伍不存在')
                    if con.execute('SELECT count(*) FROM teams WHERE school=? AND id!=?',(t['school'],t.get('id',0))).fetchone()[0]>=12: raise ValueError('该校已有 12 支队伍')
                    g=t.get('group_name','')
                    if len(g)!=1 or not 'A'<=g<chr(65+cfg['groupCount']): raise ValueError('分组不在赛事配置范围内')
                    if con.execute('SELECT count(*) FROM teams WHERE group_name=? AND id!=?',(g,t.get('id',0))).fetchone()[0]>=cfg['teamsPerGroup']: raise ValueError('该组队伍数量已满')
                    color=t.get('color','#c9fb65')
                    if len(color)!=7 or color[0]!='#' or any(ch not in '0123456789abcdefABCDEF' for ch in color[1:]): raise ValueError('队伍颜色无效')
                    vals=(t['name'],t['school'],t['tag'],color,image_url(t.get('logo','')),g,intro.strip(),t['show_school_badge'])
                    if t.get('id'):
                        con.execute('UPDATE teams SET name=?,school=?,tag=?,color=?,logo=?,group_name=?,introduction=?,show_school_badge=? WHERE id=?',vals+(t['id'],)); tid=t['id']
                    else: tid=con.execute('INSERT INTO teams(name,school,tag,color,logo,group_name,introduction,show_school_badge) VALUES (?,?,?,?,?,?,?,?)',vals).lastrowid
                    for p in t.get('players',[]):
                        if p.get('school') not in SCHOOL_NAMES+['外援']: raise ValueError('请选择队员所属学校或外援')
                        rank=p.get('perfect_rank','')
                        if rank not in PERFECT_RANKS: raise ValueError('请选择有效的完美段位')
                        vals=(short(p.get('nickname')),image_url(p.get('avatar','')),short(p.get('role','选手')),short(p.get('position'),20),p['school'],rank)
                        if p.get('id'):
                            cur=con.execute('UPDATE players SET nickname=?,avatar=?,role=?,position=?,school=?,perfect_rank=? WHERE id=? AND team_id=?',vals+(p['id'],tid))
                            if cur.rowcount!=1: raise ValueError('选手不属于该队伍')
                        else: con.execute('INSERT INTO players(nickname,avatar,role,position,school,perfect_rank,team_id) VALUES (?,?,?,?,?,?,?)',vals+(tid,))
                    for pid in t.get('removed_player_ids',[]):
                        for match in con.execute('SELECT stats FROM matches'):
                            if any(s['playerId']==pid for s in json.loads(match['stats'])): raise ValueError('该选手已有比赛数据，不能移除')
                        cur=con.execute('DELETE FROM players WHERE id=? AND team_id=?',(pid,tid))
                        if cur.rowcount!=1: raise ValueError('选手不属于该队伍')
                else: return self.json({'error':'接口不存在'},404)
                if self.path in ['/api/match','/api/config','/api/team']: tournament.reconcile(con)
                start_due_matches(con)
                con.execute('INSERT INTO audit_log(action) VALUES (?)',(self.path,))
            self.json({'ok':True})
        except (ValueError,TypeError,KeyError,sqlite3.IntegrityError) as error: self.json({'error':str(error) or '数据格式错误'},400)


if __name__=='__main__':
    initialize()
    print(f'CS2 local preview: http://127.0.0.1:{PORT}',flush=True)
    TournamentHTTPServer(('127.0.0.1',PORT),Handler).serve_forever()
