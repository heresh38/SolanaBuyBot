# Solana Buy Bot

A Telegram bot that monitors Solana token contracts and sends real-time buy notifications to your group. Supports multiple tokens per chat, configurable minimum buy threshold, and works with SOL, WSOL, USDC, and USDT pairs.

---

## Notification Format

Every buy alert looks like this:

```
🟢 NEW BUY DETECTED!
━━━━━━━━━━━━━━━━━━
🪙 Pepe Solana (PEPE)
`EPjFWd...t1v`
🏦 DEX: Jupiter

👛 Buyer: 7xKXtg...3Qp
💰 Spent: 0.5000 SOL ($83.50)
🎁 Received: 125.43K tokens

🔗 DexScreener • Birdeye • TX
━━━━━━━━━━━━━━━━━━
#1 buy • min $1.00
```

---

## Setup (~30 mins)

### Step 1 - Create Telegram Bot
1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow the prompts
3. Copy the bot token it gives you

### Step 2 - Get Helius API Key (Free)
1. Sign up at [https://helius.dev](https://helius.dev)
2. Create a project and copy your API Key
3. Free tier gives ~1M credits/month which is plenty

### Step 3 - Deploy to Railway (Free)
1. Push this repo to GitHub
2. Go to [https://railway.app](https://railway.app) and sign in with GitHub
3. New Project -> Deploy from GitHub repo -> select this repo
4. Click your service -> Variables tab -> add these two:
```
TELEGRAM_TOKEN    your_bot_token_here
HELIUS_API_KEY    your_helius_key_here
```
5. Railway detects the Procfile and starts the bot automatically

> Render.com alternative: New -> Background Worker -> connect repo
> Build command: pip install -r requirements.txt
> Start command: python bot.py
> Add the same two environment variables.

### Step 4 - Add bot to your Telegram group
1. Open your Telegram group
2. Go to Group Info -> Add Members -> search your bot username
3. Add it as an Admin so it can send messages

---

## Commands

| Command | Description |
|---|---|
| `/start` | Show help and all commands |
| `/watch <contract>` | Start watching a token |
| `/unwatch <contract>` | Stop watching a specific token |
| `/stopall` | Stop all monitors |
| `/list` | Show all watched tokens with buy counts |
| `/status` | Summary stats across all tokens |
| `/setmin <amount>` | Set minimum buy in USD (e.g. `/setmin 50`) |
| `/getmin` | Show current minimum buy threshold |

Default minimum buy is $1.00 — buys below this are silently ignored.

Example usage:
```
/watch 7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU
/watch EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v
/setmin 50
/list
```

---

## Features

- Watches multiple tokens at once per chat
- Works with SOL, WSOL, USDC, and USDT pairs
- Shows token name and symbol in every notification (e.g. Pepe Solana (PEPE))
- Configurable minimum buy threshold per chat — different groups can have different settings
- Updating /setmin applies instantly to all active monitors, no need to restart
- /list shows buys posted and buys filtered so you know what is being caught vs skipped
- Polls Helius every 10 seconds for new swaps
- SOL price fetched from Helius with automatic fallback
- Auto-reconnects on any errors
- Duplicate transaction protection so you never get the same buy twice

---

## File Structure

```
solana-buy-bot/
├── bot.py           # Telegram commands and multi-token management
├── monitor.py       # Helius polling monitor, buy parser, notifications
├── requirements.txt
├── Procfile         # For Railway/Render deployment
└── .env.example     # Environment variable template
```

---

## How It Works

1. You run /watch <contract> in your Telegram group
2. The bot fetches the token name and symbol from Helius
3. Every 10 seconds it polls Helius for new SWAP transactions on that contract
4. New transactions are parsed to find the buyer wallet and amount spent
5. It checks for SOL, WSOL, USDC, and USDT payments automatically
6. If the buy value meets your minimum threshold it sends a notification
7. Each chat tracks its own token list and minimum independently

---

## Filtering

Use /setmin to control how many alerts you get:
- /setmin 1 -- default, catch nearly everything
- /setmin 50 -- medium filter, ignore small buys
- /setmin 500 -- whale alerts only

Use /list to see buys posted vs filtered for each token.

---

## Notes

- Each token you watch uses one polling loop. Watching 10 tokens means 10 loops running every 10 seconds, which is fine for normal use.
- The bot token should be kept private. Never paste it into your code files, only add it in Railway/Render environment variables.
- If Railway shows multiple deployments running at the same time, go to the Deployments tab and remove old ones -- only one instance should run at a time.
- Turn off Smart Punctuation on iPhone (Settings -> General -> Keyboard -> Smart Punctuation -> Off) before editing any code files to avoid quote corruption.
