import asyncio, threading, logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
import discord_worker, tg_worker

logger = logging.getLogger("api")
PASSWORD = "1314@YSYms"
PORT     = 7790

def _auth(pw):
    if pw != PASSWORD: raise HTTPException(401, "unauthorized")

@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=discord_worker.run_poller, daemon=True).start()
    yield

app = FastAPI(lifespan=lifespan)

class HoursReq(BaseModel):
    hours: float

# ── Discord ───────────────────────────────────────────────────

@app.post("/discord/messages")
def discord_messages(req: HoursReq, x_password: str = Header(None)):
    _auth(x_password)
    if discord_worker.state["expired"]:
        return {"status": "token_expired"}
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(discord_worker.query(req.hours))

# ── Telegram ──────────────────────────────────────────────────

@app.get("/telegram/dialogs")
async def tg_dialogs(x_password: str = Header(None)):
    _auth(x_password)
    return await tg_worker.get_dialogs()

@app.post("/telegram/recent")
async def tg_recent(req: HoursReq, x_password: str = Header(None)):
    _auth(x_password)
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(await tg_worker.get_recent(req.hours))

@app.post("/all")
async def all_recent(req: HoursReq, x_password: str = Header(None)):
    _auth(x_password)
    from fastapi.responses import PlainTextResponse
    parts = []
    dc = discord_worker.query(req.hours)
    tg = await tg_worker.get_recent(req.hours)
    if dc: parts.append(dc)
    if tg: parts.append(tg)
    return PlainTextResponse("\n".join(parts))

# ── Health ────────────────────────────────────────────────────

@app.get("/health")
async def health():
    tg_ok = False
    try:
        tg_ok = bool(await tg_worker._client.is_user_authorized())
    except Exception:
        pass
    return {
        "discord": "ok" if not discord_worker.state["expired"] else "token_expired",
        "telegram": "ok" if tg_ok else "not_authorized",
    }
