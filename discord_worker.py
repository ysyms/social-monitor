import sqlite3, time, random, logging, httpx
from collections import defaultdict
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("discord")

BASE_URL    = "https://discord.com/api/v9"
TEXT_TYPES  = {0, 5}
MAX_HOURS   = 72
POLL_MIN    = 10
POLL_MAX    = 15
DB_PATH     = "/opt/social-monitor/discord.db"
CST         = timezone(timedelta(hours=8))

state = {"expired": False}
_token = ""

def init(token: str):
    global _token
    _token = token
    _init_db()

def _headers():
    return {
        "Authorization": _token,
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    }

def _snowflake_to_time(s): return ((int(s) >> 22) + 1420070400000) / 1000
def _time_to_snowflake(ts): return str((int(ts * 1000) - 1420070400000) << 22)

class CookieExpired(Exception): pass

def _get(url, params=None):
    r = httpx.get(url, headers=_headers(), params=params, timeout=15)
    if r.status_code == 401: raise CookieExpired()
    if r.status_code == 403: return None
    r.raise_for_status()
    return r.json()

def _init_db():
    import os; os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with sqlite3.connect(DB_PATH) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY, channel_id TEXT, guild_id TEXT,
            guild_name TEXT, channel_name TEXT, author TEXT, content TEXT, ts REAL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS channel_state (
            channel_id TEXT PRIMARY KEY, last_id TEXT)""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_ts ON messages(ts)")

def _insert(rows):
    if not rows: return
    with sqlite3.connect(DB_PATH) as c:
        c.executemany("INSERT OR IGNORE INTO messages VALUES (?,?,?,?,?,?,?,?)", rows)

def query(hours: float) -> str:
    since = time.time() - hours * 3600
    with sqlite3.connect(DB_PATH) as c:
        rows = c.execute(
            "SELECT guild_name,channel_name,author,content,ts FROM messages WHERE ts>? ORDER BY ts ASC",
            (since,)).fetchall()
    tree = defaultdict(lambda: defaultdict(list))
    for g,ch,a,txt,ts in rows:
        t = datetime.fromtimestamp(ts, tz=CST).strftime("%H:%M")
        tree[g][ch].append(f"  {t} {a}: {txt}")
    lines = []
    for g, chs in tree.items():
        for ch, msgs in chs.items():
            lines.append(f"[DC] {g} / {ch}")
            lines.extend(msgs)
    return "\n".join(lines)

def _get_last(cid):
    with sqlite3.connect(DB_PATH) as c:
        r = c.execute("SELECT last_id FROM channel_state WHERE channel_id=?", (cid,)).fetchone()
    return r[0] if r else None

def _set_last(cid, lid):
    with sqlite3.connect(DB_PATH) as c:
        c.execute("INSERT OR REPLACE INTO channel_state VALUES (?,?)", (cid, lid))

def _fetch_after(cid, gid, gname, cname, after, max_fetch=None):
    rows, cursor, total = [], after, 0
    while True:
        data = _get(f"{BASE_URL}/channels/{cid}/messages", {"after": cursor, "limit": 100})
        if not data: break
        for m in data:
            if m.get("content","").strip():
                rows.append((m["id"],cid,gid,gname,cname,m["author"]["username"],
                             m["content"].strip(), _snowflake_to_time(m["id"])))
        cursor = data[-1]["id"]
        total += len(data)
        if len(data) < 100 or (max_fetch and total >= max_fetch): break
        time.sleep(0.5)
    return rows, cursor

def _poll_once():
    for guild in (_get(f"{BASE_URL}/users/@me/guilds") or []):
        gid, gname = guild["id"], guild["name"]
        channels = _get(f"{BASE_URL}/guilds/{gid}/channels")
        if not channels: continue
        for ch in [c for c in channels if c.get("type") in TEXT_TYPES]:
            cid, cname = ch["id"], ch.get("name","")
            last = _get_last(cid)
            after = last or _time_to_snowflake(time.time() - MAX_HOURS * 3600)
            try:
                rows, newest = _fetch_after(cid, gid, gname, cname, after, None if last else 500)
                if rows: _insert(rows)
                _set_last(cid, newest if rows else (after if not last else last))
            except CookieExpired: raise
            except Exception as e: logger.warning(f"频道 {cname} 出错: {e}")
            time.sleep(0.3)

def run_poller():
    _init_db()
    logger.info("Discord poller 启动")
    while True:
        try:
            _poll_once()
            cutoff = time.time() - MAX_HOURS * 3600
            with sqlite3.connect(DB_PATH) as c:
                c.execute("DELETE FROM messages WHERE ts<?", (cutoff,))
        except CookieExpired:
            logger.error("Discord token 已过期")
            state["expired"] = True
            return
        except Exception as e:
            logger.error(f"轮询异常: {e}")
        interval = random.randint(POLL_MIN * 60, POLL_MAX * 60)
        logger.info(f"下次轮询 {interval//60}m 后")
        time.sleep(interval)
