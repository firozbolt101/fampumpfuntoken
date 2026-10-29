# Pump.fun Telegram Token Alert Bot

## Features
- Detects new Pump.fun tokens using PumpPortal WebSocket `subscribeNewToken`.
- Sends Telegram alerts with token mint, Pump.fun page and Solscan link.
- Telegram commands: `/start`, `/help`, `/status`, `/pause`, `/resume`.
- Only the configured `TELEGRAM_CHAT_ID` can control the bot.
- Alert-only: no swaps, no wallet signing, no private key required.

## Setup
Python 3.11+ recommended.

```bash
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows PowerShell:
# .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Copy `.env.example` to `.env`, set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`, then run:

```bash
python bot.py
```

## Telegram setup
1. Open Telegram and message `@BotFather`.
2. Run `/newbot` and follow its steps.
3. Put the bot token in `.env`; do not share it.
4. Send a message to your new bot.
5. Obtain your numeric chat ID using a trusted Telegram getUpdates method or a bot you trust, then set `TELEGRAM_CHAT_ID`.
6. Start the script on a computer/server that remains online.
7. Send `/start` to the bot.

## Commands
- `/status` — stream status and count of remembered token mints
- `/pause` — pause alerts
- `/resume` — resume alerts
- `/help` — command list

## Important
- This is not a trading bot. It will not buy/sell or sign transactions.
- A token event is not proof of liquidity or safety. Verify liquidity, mint/freeze authority, holder concentration, deployer history and whether selling works before any manual trade.
- PumpPortal is a third-party service; check current docs and terms.
- Keep your Telegram bot token private. The chat ID restriction is a basic control, not a substitute for server security.
