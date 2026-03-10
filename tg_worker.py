import logging, time
from datetime import datetime, timezone, timedelta
from telethon import TelegramClient, events
from telethon.tl.types import User, Chat, Channel
import db

logger = logging.getLogger("telegram")

API_ID   = 2040
API_HASH = "b18441a1ff607e10a989891a5462e627"
SESSION  = "/opt/social-cli/tg_session"
CST      = timezone(timedelta(hours=8))

_client: TelegramClient = None

async def init_client():
    global _client
    _client = TelegramClient(SESSION, API_ID, API_HASH)
    await _client.connect()
    return _client

def _group_name(entity) -> str:
    if hasattr(entity, "first_name"):
        return entity.first_name or "Unknown"
    return getattr(entity, "title", "Unknown")

def start_listener():
    """注册新消息事件监听，实时入库"""
    @_client.on(events.NewMessage)
    async def handler(event):
        try:
            msg = event.message
            if not msg.text: return
            chat = await event.get_chat()
            group = _group_name(chat)
            sender_entity = await event.get_sender()
            sender = _group_name(sender_entity) if sender_entity else group
            db.insert([(
                f"tg-{msg.id}-{chat.id}", "tg",
                group, sender, msg.text,
                msg.date.timestamp()
            )])
        except Exception as e:
            logger.warning(f"消息入库失败: {e}")

async def get_dialogs():
    dialogs = await _client.get_dialogs()
    result = {"private": [], "groups": []}
    for d in dialogs:
        item = {"id": d.id, "name": d.name, "unread": d.unread_count}
        if isinstance(d.entity, User):
            result["private"].append(item)
        else:
            result["groups"].append(item)
    return result
