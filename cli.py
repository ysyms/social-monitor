#!/usr/bin/env python3
"""
social-monitor CLI
交互式配置 Discord + Telegram，或导入配置文件，启动统一监控服务。

用法:
  python cli.py                  # 交互式配置
  python cli.py --config cfg.json  # 导入配置文件
  python cli.py --tg-session /path/to/tg.session  # 导入已有 TG session
"""
import asyncio, os, sys, json, argparse, logging
import uvicorn
import config, discord_worker, tg_worker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")

BANNER = """
╔═══════════════════════════════════╗
║       Social Monitor CLI          ║
║   Discord + Telegram 消息监控     ║
╚═══════════════════════════════════╝
"""

CONFIG_TEMPLATE = {
    "discord_token": "YOUR_DISCORD_TOKEN",
    "tg_session": "/path/to/tg_session.session"  # 可选，有则跳过手机登录
}

async def setup_telegram(client, tg_session_src=None):
    """Telegram 登录：已有 session 直接用，否则交互登录"""
    if tg_session_src and os.path.exists(tg_session_src):
        # 导入外部 session 文件
        import shutil
        shutil.copy(tg_session_src, tg_worker.SESSION + ".session")
        print(f"  ✓ 已导入 Telegram session：{tg_session_src}")

    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"  ✓ Telegram 已登录：{me.first_name} (@{me.username})")
        return

    # 交互登录
    phone = input("  Telegram 手机号（含国家码，如 +8613800000000）：").strip()
    await client.send_code_request(phone)
    code = input("  验证码：").strip()
    try:
        await client.sign_in(phone, code)
    except Exception:
        pw = input("  两步验证密码：").strip()
        await client.sign_in(password=pw)
    me = await client.get_me()
    print(f"  ✓ Telegram 登录成功：{me.first_name}")

async def main():
    parser = argparse.ArgumentParser(description="Social Monitor CLI")
    parser.add_argument("--config", metavar="FILE", help="导入 JSON 配置文件")
    parser.add_argument("--tg-session", metavar="FILE", help="导入已有 Telegram session 文件")
    parser.add_argument("--print-template", action="store_true", help="打印配置文件模板")
    parser.add_argument("--no-interactive", action="store_true", help="非交互模式（配合 --config 使用）")
    args = parser.parse_args()

    # 打印模板
    if args.print_template:
        print(json.dumps(CONFIG_TEMPLATE, indent=2, ensure_ascii=False))
        sys.exit(0)

    print(BANNER)
    cfg = config.load()

    # ── 导入配置文件 ──────────────────────────────────────────
    if args.config:
        if not os.path.exists(args.config):
            print(f"错误：找不到配置文件 {args.config}")
            sys.exit(1)
        with open(args.config) as f:
            imported = json.load(f)
        cfg.update({k: v for k, v in imported.items() if v and v != CONFIG_TEMPLATE.get(k)})
        print(f"✓ 已导入配置：{args.config}")

    # ── Discord token ─────────────────────────────────────────
    print("【Discord】")
    if cfg.get("discord_token"):
        print(f"  已有 token（末尾：...{cfg['discord_token'][-8:]}）")
        if not args.no_interactive and input("  重新输入？(y/N) ").strip().lower() == "y":
            cfg["discord_token"] = input("  Discord token：").strip()
    elif not args.no_interactive:
        print("  获取：浏览器打开 Discord → F12 → Network → Authorization header")
        cfg["discord_token"] = input("  Discord token：").strip()

    # ── Telegram ──────────────────────────────────────────────
    print("\n【Telegram】")
    tg_session_src = args.tg_session or cfg.get("tg_session")
    client = await tg_worker.init_client()
    await setup_telegram(client, tg_session_src)

    config.save(cfg)
    discord_worker.init(cfg["discord_token"])

    print("\n✓ 配置完成，正在启动服务...\n")
    print("  API：http://0.0.0.0:7790")
    print("  Header：x-password: 1314@YSYms\n")

    import api
    uvicorn_cfg = uvicorn.Config(api.app, host="0.0.0.0", port=7790, log_level="warning")
    server = uvicorn.Server(uvicorn_cfg)

    await asyncio.gather(server.serve(), _keep_alive())

async def _keep_alive():
    while True:
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main())
