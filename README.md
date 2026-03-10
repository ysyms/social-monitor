# Social CLI

A unified CLI tool for monitoring Discord and Telegram messages via a single HTTP API.

---

## Architecture

```
cli.py              # Entry point, interactive setup
├── discord_worker.py   # Discord polling + SQLite storage
├── tg_worker.py        # Telegram via Telethon (MTProto), real-time listener
├── exporter.py         # Historical export, fetches directly from APIs
├── db.py               # Shared SQLite storage (1 week retention)
├── api.py              # Unified FastAPI server
└── config.py           # Config persistence
```

### How monitoring works

**Telegram** — Uses [Telethon](https://github.com/LonamiWebs/Telethon), a pure Python MTProto client. After login the session file stores the authorization key. A real-time event listener captures every new message and writes it to SQLite immediately.

**Discord** — No real-time push API for user accounts, so a background worker polls all guilds and channels every 10–15 minutes and stores new messages in SQLite.

Both platforms retain messages for **1 week**. Monitoring starts from the moment the CLI is launched — no historical backfill on startup.

### Telegram API credentials

No registration required. Built-in client credentials are hardcoded in `tg_worker.py`:

```python
API_ID   = 2040
API_HASH = "b18441a1ff607e10a989891a5462e627"
```

To use your own, register at [my.telegram.org/apps](https://my.telegram.org/apps).

---

## Getting Discord Token

Requires a Discord **user token** (not a Bot token).

1. Open Discord in your browser
2. Press `F12` → **Network** tab
3. Switch to any channel to trigger a request
4. Find a request matching `discord.com/api/v9/channels/*/messages`
5. Click it → **Request Headers** → copy the `Authorization` value

> ⚠️ Your user token grants full account access. Never share it or commit it to version control.

---

## Installation

```bash
git clone https://github.com/ysyms/social-cli.git
cd social-cli
pip install -r requirements.txt
```

---

## Usage

### Interactive setup

```bash
python cli.py
```

Prompts for Discord token, then Telegram phone number + verification code.

### Import config file

```bash
python cli.py --print-template   # print config template
python cli.py --config myconfig.json
```

Config format:

```json
{
  "discord_token": "YOUR_DISCORD_TOKEN",
  "tg_session": "/path/to/tg_session.session"
}
```

### Import existing Telegram session

```bash
python cli.py --tg-session /path/to/tg.session
```

---

## API Reference

All endpoints require header: `x-password: 1314@YSYms`

### Monitoring endpoints (reads from local DB)

Query by `hours` or explicit `start`/`end` time range (UTC+8, format `YYYY-MM-DD HH:MM`).

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/all` | POST | All platforms combined |
| `/discord/messages` | POST | Discord only |
| `/telegram/recent` | POST | Telegram only |
| `/telegram/dialogs` | GET | Telegram dialog list |
| `/health` | GET | Service health |

```bash
# Last 24 hours
curl -X POST http://localhost:7790/all \
  -H "x-password: 1314@YSYms" \
  -H "Content-Type: application/json" \
  -d '{"hours": 24}'

# Specific time range
curl -X POST http://localhost:7790/all \
  -H "x-password: 1314@YSYms" \
  -H "Content-Type: application/json" \
  -d '{"start": "2026-03-01 00:00", "end": "2026-03-07 23:59"}'
```

### Export endpoint (fetches historical data from source)

Pulls historical messages directly from Telegram/Discord APIs for any time range. Does not write to local DB.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/export` | POST | Historical export |

```bash
curl -X POST http://localhost:7790/export \
  -H "x-password: 1314@YSYms" \
  -H "Content-Type: application/json" \
  -d '{
    "start": "2026-03-01 00:00",
    "end": "2026-03-07 23:59",
    "platform": "tg"
  }'
```

`platform` options: `"tg"` / `"dc"` / omit for both.

### Output format

All endpoints return plain text optimized for LLM consumption:

```
[TG] 张三
  03/10 14:30 张三: 消息内容

[DC] Google Labs / general
  03/10 14:31 username: 消息内容
```

---

## Security

- Credentials stored at `~/.social-monitor/config.json` — never committed to git
- Session files (`.session`) and databases (`.db`) are in `.gitignore`
- Change the default API password before production deployment

---

## 中文说明

<details>
<summary>点击展开</summary>

**监听**：启动后从当前时刻开始监听，不补拉历史消息。TG 实时入库，Discord 每 10–15 分钟轮询一次，数据保留 1 周。

**导出**：`/export` 接口直接从 TG/Discord API 拉取指定时间段的历史消息，不写入本地数据库。

**Discord Token**：浏览器打开 Discord → F12 → Network → 切换频道 → 找 `/channels/*/messages` 请求 → Request Headers → `Authorization` 字段。

**Telegram 登录**：无需申请 API，使用内置凭证，手机号 + 验证码登录，session 文件保存授权密钥。

</details>
