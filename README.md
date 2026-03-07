# 🤖 Solana Buy Bot

A Telegram bot that monitors Solana token contracts and sends real-time buy notifications. Supports multiple tokens per chat, and a configurable minimum buy threshold so you only see the buys that matter.

-----

## 📋 Notification Format

```
🟢 NEW BUY DETECTED!
━━━━━━━━━━━━━━━━━━
🪙 Token: EPjFWd...t1v
🏦 DEX: Jupiter

👛 Buyer: 7xKXtg...3Qp
💰 Spent: 0.5000 SOL ($82.50)
🎁 Received: 125.43K tokens

🔗 DexScreener • Birdeye • TX
━━━━━━━━━━━━━━━━━━
#1 buy • min $1.00
```

-----

## ⚙️ Setup (~30 mins)

### Step 1 — Create Telegram Bot

1. Message [@BotFather](https://t.me/BotFather) on Telegram
1. Send `/newbot` and follow the prompts
1. Copy the **bot token** it gives you

### Step 2 — Get Helius API Key (Free)

1. Sign up at <https://helius.dev>
1. Create a project and copy your **API Key**
1. Free tier: ~1M credits/month (plenty for monitoring)

### Step 3 — Deploy to Railway (Free)

1. Push this repo to GitHub
1. Go to <https://railway.app> → New Project → Deploy from GitHub
1. In **Variables**, add:
   
   ```
   TELEGRAM_TOKEN = your_bot_token_here
   HELIUS_API_KEY = your_helius_api_key_here
   ```
1. Railway detects the `Procfile` and starts the bot automatically ✅

> **Render.com alternative:**
> New → Background Worker → connect repo
> Build command: `pip install -r requirements.txt`
> Start command: `python bot.py`
> Add the same two environment variables.

-----

## 🚀 Commands

|Command              |Description                               |
|---------------------|------------------------------------------|
|`/start`             |Show help                                 |
|`/watch <contract>`  |Start watching a token                    |
|`/unwatch <contract>`|Stop watching a specific token            |
|`/stopall`           |Stop all monitors                         |
|`/list`              |Show all watched tokens + buy counts      |
|`/status`            |Summary stats for all tokens              |
|`/setmin <amount>`   |Set minimum buy in USD (e.g. `/setmin 50`)|
|`/getmin`            |Show current minimum buy threshold        |

**Default minimum buy: $1.00** — buys below this are silently ignored.

**Examples:**

```
/watch EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v
/watch 7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU
/setmin 100
/list
```

-----

## 📁 File Structure

```
solana-buy-bot/
├── bot.py           # Telegram commands & multi-token management
├── monitor.py       # Helius WebSocket monitor, buy parser & filter
├── requirements.txt
├── Procfile         # For Railway/Render
└── .env.example     # Environment variable template
```

-----

## 🔧 How It Works

1. `/watch <contract>` opens a Helius WebSocket subscribed to that token’s transactions
1. Each transaction is checked for DEX swap activity (Jupiter, Raydium, Orca, Pump.fun)
1. Confirmed buys are parsed for buyer wallet, SOL spent, and tokens received
1. SOL → USD conversion via CoinGecko live price
1. If the buy value meets your minimum threshold, a notification fires in Telegram
1. Each chat tracks its own token list and minimum independently

-----

## 📊 Filtering

Use `/setmin` to control noise:

- `/setmin 1` — default, catch everything ($1+)
- `/setmin 50` — medium filter
- `/setmin 500` — only whale alerts

`/list` and `/status` show both **buys posted** and **buys filtered** so you can see what’s being caught vs skipped.

-----

## ⚠️ Notes

- One token = one WebSocket connection. 10 tokens = 10 connections. Fine for normal use.
- Auto-reconnects on disconnect every 5 seconds
- `/setmin` updates all active monitors instantly — no need to re-watch
- Minimum threshold is per-chat, so different groups can have different settings
