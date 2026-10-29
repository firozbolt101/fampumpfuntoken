"""
Pump.fun Telegram bot: token alerts + Telegram commands.
Safe default: alert-only. No private key required unless you later implement/review live trading.
Commands: /start /help /status /pause /resume
"""
import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pump-telegram-bot")

PUMPPORTAL_WS = "wss://pumpportal.fun/api/data"
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
STATE_PATH = Path(os.getenv("STATE_FILE", "bot_state.json"))
POLL_SECONDS = 2
MAX_SEEN = 3000

def load_state():
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except Exception:
            pass
    return {"paused": False, "started_at": int(time.time()), "seen": []}

def save_state(state):
    # Atomic replace to reduce risk of corrupting state on abrupt stop.
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(STATE_PATH)

async def tg_call(session, method, payload):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/{method}"
    async with session.post(url, json=payload, timeout=20) as resp:
        data = await resp.json(content_type=None)
        if resp.status >= 400 or not data.get("ok"):
            raise RuntimeError(f"Telegram {method} failed: {str(data)[:300]}")
        return data["result"]

async def send_message(session, chat_id, text):
    return await tg_call(session, "sendMessage", {
        "chat_id": chat_id, "text": text, "disable_web_page_preview": True
    })

def uptime_text(started_at):
    seconds = max(0, int(time.time()) - int(started_at))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}h {minutes}m {secs}s"

async def command_loop(session, state):
    offset = 0
    while True:
        try:
            result = await tg_call(session, "getUpdates", {
                "offset": offset, "timeout": 20,
                "allowed_updates": ["message"]
            })
            for update in result:
                offset = max(offset, int(update["update_id"]) + 1)
                msg = update.get("message") or {}
                chat = msg.get("chat") or {}
                chat_id = str(chat.get("id", ""))
                text = (msg.get("text") or "").strip()
                # Security: only the configured chat can control this bot.
                if not TG_CHAT_ID or chat_id != TG_CHAT_ID:
                    if text.startswith("/"):
                        log.warning("Ignored command from non-authorized chat %s", chat_id)
                    continue
                command = text.split()[0].split("@")[0].lower() if text else ""
                if command in ("/start", "/help"):
                    await send_message(session, chat_id,
                        "🤖 Pump.fun Token Alert Bot\n\n"
                        "Commands:\n"
                        "/status — bot status\n"
                        "/pause — pause token alerts\n"
                        "/resume — resume token alerts\n"
                        "/help — show commands\n\n"
                        "Mode: alert-only. This bot does not buy or sell tokens.")
                elif command == "/status":
                    await send_message(session, chat_id,
                        "📊 Bot status\n"
                        f"Alerts: {'PAUSED' if state.get('paused') else 'ACTIVE'}\n"
                        f"Unique mints seen: {len(state.get('seen', []))}\n"
                        f"Process uptime: {uptime_text(state.get('started_at', time.time()))}\n"
                        "Trading: DISABLED")
                elif command == "/pause":
                    state["paused"] = True
                    save_state(state)
                    await send_message(session, chat_id, "⏸️ Token alerts paused. Use /resume to restart alerts.")
                elif command == "/resume":
                    state["paused"] = False
                    save_state(state)
                    await send_message(session, chat_id, "▶️ Token alerts resumed.")
                elif command:
                    await send_message(session, chat_id, "Unknown command. Use /help.")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("Telegram polling error: %s", exc)
            await asyncio.sleep(3)

async def token_stream(session, state):
    while True:
        try:
            async with session.ws_connect(PUMPPORTAL_WS, heartbeat=25, receive_timeout=90) as ws:
                await ws.send_json({"method": "subscribeNewToken"})
                log.info("Connected to PumpPortal stream.")
                await send_message(session, TG_CHAT_ID,
                                  "✅ Pump.fun token stream connected. Use /status, /pause, /resume.")
                async for message in ws:
                    if message.type == aiohttp.WSMsgType.TEXT:
                        try:
                            token = json.loads(message.data)
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(token, dict):
                            continue
                        mint = str(token.get("mint", "")).strip()
                        if not mint or len(mint) < 32:
                            continue
                        seen = state.setdefault("seen", [])
                        if mint in seen:
                            continue
                        seen.append(mint)
                        if len(seen) > MAX_SEEN:
                            state["seen"] = seen[-MAX_SEEN:]
                        save_state(state)
                        if state.get("paused"):
                            continue
                        name = str(token.get("name", "Unknown"))[:70]
                        symbol = str(token.get("symbol", "???"))[:24]
                        market_cap = token.get("marketCapSol", "unknown")
                        text = (
                            "🆕 New Pump.fun token\n\n"
                            f"Name: {name}\nSymbol: {symbol}\n"
                            f"Market cap (reported SOL): {market_cap}\n"
                            f"Mint: {mint}\n"
                            f"Pump.fun: https://pump.fun/coin/{mint}\n"
                            f"Solscan: https://solscan.io/token/{mint}\n\n"
                            "⚠️ Alert only—not a buy recommendation. Check liquidity, authorities, holder concentration and sellability."
                        )
                        try:
                            await send_message(session, TG_CHAT_ID, text)
                        except Exception as exc:
                            log.warning("Could not send token alert: %s", exc)
                    elif message.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        break
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("PumpPortal disconnected: %s; reconnecting shortly", exc)
            await asyncio.sleep(5)

async def main():
    if not TG_TOKEN or not TG_CHAT_ID:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env first.")
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        # Verify Telegram token and send startup notice.
        me = await tg_call(session, "getMe", {})
        log.info("Logged in as @%s", me.get("username", "unknown"))
        state = load_state()
        if "paused" not in state:
            state["paused"] = False
        if "started_at" not in state:
            state["started_at"] = int(time.time())
        save_state(state)
        await send_message(session, TG_CHAT_ID,
                           f"🤖 Telegram bot online: @{me.get('username', 'unknown')}\n"
                           "Mode: token alerts only; trading disabled.\nUse /help for commands.")
        await asyncio.gather(command_loop(session, state), token_stream(session, state))

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped.")
