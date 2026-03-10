import time, threading, logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from typing import Optional
import discord_worker, tg_worker, db, config

logger = logging.getLogger("api")
PASSWORD = "1314@YSYms"
CST      = timezone(timedelta(hours=8))

def _auth(pw):
    if pw != PASSWORD: raise HTTPException(401, "unauthorized")

def _to_text(rows) -> str:
    """Convert DB rows to compact text for LLM."""
    from collections import defaultdict
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

def _parse_range(hours, start, end):
    """Parse time range from hours or start/end strings."""
    now = time.time()
    if start and end:
        fmt = "%Y-%m-%d %H:%M"
        s = datetime.strptime(start, fmt).replace(tzinfo=CST).timestamp()
        e = datetime.strptime(end, fmt).replace(tzinfo=CST).timestamp()
        return s, e
    h = hours or 24
    return now - h * 3600, now

@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    threading.Thread(target=discord_worker.run_poller, daemon=True).start()
    tg_worker.start_listener()
    yield

app = FastAPI(lifespan=lifespan)

class QueryReq(BaseModel):
    hours: Optional[float] = None
    start: Optional[str] = None   # "2026-03-09 10:00"
    end: Optional[str] = None     # "2026-03-10 10:00"

# ── Discord ───────────────────────────────────────────────────

@app.post("/discord/messages")
def discord_messages(req: QueryReq, x_password: str = Header(None)):
    _auth(x_password)
    if discord_worker.state["expired"]:
        return PlainTextResponse("ERROR: Discord token expired")
    s, e = _parse_range(req.hours, req.start, req.end)
    return PlainTextResponse(_to_text(db.query(s, e, platform="dc")))

# ── Telegram ──────────────────────────────────────────────────

@app.get("/telegram/dialogs")
async def tg_dialogs(x_password: str = Header(None)):
    _auth(x_password)
    return await tg_worker.get_dialogs()

@app.post("/telegram/recent")
def tg_recent(req: QueryReq, x_password: str = Header(None)):
    _auth(x_password)
    s, e = _parse_range(req.hours, req.start, req.end)
    return PlainTextResponse(_to_text(db.query(s, e, platform="tg")))

# ── All ───────────────────────────────────────────────────────

@app.post("/all")
def all_recent(req: QueryReq, x_password: str = Header(None)):
    _auth(x_password)
    s, e = _parse_range(req.hours, req.start, req.end)
    return PlainTextResponse(_to_text(db.query(s, e)))

# ── Export (historical fetch, not from DB) ────────────────────

class ExportReq(BaseModel):
    start: str             # "2026-03-01 00:00"
    end: str               # "2026-03-10 00:00"
    platform: Optional[str] = None  # "tg" | "dc" | None (both)

@app.post("/export")
async def export(req: ExportReq, x_password: str = Header(None)):
    _auth(x_password)
    import exporter
    from datetime import datetime
    fmt = "%Y-%m-%d %H:%M"
    s = datetime.strptime(req.start, fmt).replace(tzinfo=CST).timestamp()
    e = datetime.strptime(req.end,   fmt).replace(tzinfo=CST).timestamp()
    rows = []
    if req.platform in (None, "tg"):
        rows += await exporter.tg_export(s, e)
    if req.platform in (None, "dc"):
        cfg = config.load()
        rows += exporter.dc_export(cfg["discord_token"], s, e)
    return PlainTextResponse(exporter.to_text(rows))

# ── Health ────────────────────────────────────────────────────

@app.get("/health")
async def health():
    tg_ok = False
    try:
        tg_ok = await tg_worker._client.is_user_authorized()
    except Exception:
        pass
    return {
        "discord": "ok" if not discord_worker.state["expired"] else "token_expired",
        "telegram": "ok" if tg_ok else "not_authorized",
    }
