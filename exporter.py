"""
On-demand historical message export.
Fetches directly from TG/Discord APIs for a given time range.
Does NOT write to the local DB.
"""
import time, logging, httpx
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import tg_worker

logger = logging.getLogger("exporter")
CST = timezone(timedelta(hours=8))

BASE_URL   = "https://discord.com/api/v9"
TEXT_TYPES = {0, 5}

# ── Telegram ──────────────────────────────────────────────────

async def tg_export(start_ts: float, end_ts: float) -> list[tuple]:
    """Fetch TG messages in [start_ts, end_ts] from Telegram servers."""
    rows = []
    dialogs = await tg_worker._client.get_dialogs()
    for d in dialogs:
        try:
            async for msg in tg_worker._client.iter_messages(
                d.entity, reverse=False, limit=None,
                offset_date=datetime.fromtimestamp(end_ts, tz=timezone.utc)
            ):
                ts = msg.date.timestamp()
                if ts < start_ts: break
                if ts > end_ts: continue
                if not msg.text: continue
                sender = tg_worker._group_name(msg.sender) if msg.sender else d.name
                rows.append(("tg", d.name, sender, msg.text, ts))
        except Exception as e:
            logger.warning(f"TG export {d.name}: {e}")
    return rows

# ── Discord ───────────────────────────────────────────────────

def _dc_get(token: str, url, params=None):
    r = httpx.get(url, headers={
        "Authorization": token,
        "User-Agent": "Mozilla/5.0 Chrome/120.0.0.0",
    }, params=params, timeout=15)
    if r.status_code in (401, 403): return None
    r.raise_for_status()
    return r.json()

def _snowflake_to_time(s): return ((int(s) >> 22) + 1420070400000) / 1000
def _time_to_snowflake(ts): return str((int(ts * 1000) - 1420070400000) << 22)

def dc_export(token: str, start_ts: float, end_ts: float) -> list[tuple]:
    """Fetch Discord messages in [start_ts, end_ts] from Discord API."""
    rows = []
    guilds = _dc_get(token, f"{BASE_URL}/users/@me/guilds") or []
    for guild in guilds:
        gid, gname = guild["id"], guild["name"]
        channels = _dc_get(token, f"{BASE_URL}/guilds/{gid}/channels") or []
        for ch in [c for c in channels if c.get("type") in TEXT_TYPES]:
            cid, cname = ch["id"], ch.get("name", "")
            after = _time_to_snowflake(start_ts)
            while True:
                data = _dc_get(token, f"{BASE_URL}/channels/{cid}/messages",
                               {"after": after, "limit": 100})
                if not data: break
                for m in data:
                    ts = _snowflake_to_time(m["id"])
                    if ts > end_ts: break
                    if m.get("content","").strip():
                        rows.append(("dc", f"{gname} / {cname}",
                                    m["author"]["username"],
                                    m["content"].strip(), ts))
                after = data[-1]["id"]
                if len(data) < 100 or _snowflake_to_time(after) > end_ts: break
                time.sleep(0.3)
            time.sleep(0.2)
    return rows

# ── Format ────────────────────────────────────────────────────

def to_text(rows: list[tuple]) -> str:
    rows = sorted(rows, key=lambda r: r[4])
    groups = defaultdict(list)
    for platform, group, sender, text, ts in rows:
        t = datetime.fromtimestamp(ts, tz=CST).strftime("%m/%d %H:%M")
        prefix = "[TG]" if platform == "tg" else "[DC]"
        groups[f"{prefix} {group}"].append(f"  {t} {sender}: {text}")
    lines = []
    for group, msgs in groups.items():
        lines.append(group)
        lines.extend(msgs)
    return "\n".join(lines)
