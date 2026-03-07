import os
import asyncio
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from monitor import SolanaMonitor

logging.basicConfig(
format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",

level=logging.INFO
)
logger = logging.getLogger(**name**)

TELEGRAM_TOKEN = os.getenv(“TELEGRAM_TOKEN”)

# chat_id -> { contract_address -> SolanaMonitor }

monitors: dict[int, dict[str, SolanaMonitor]] = {}

# chat_id -> minimum USD buy amount (default $1)

min_buy_usd: dict[int, float] = {}

DEFAULT_MIN_BUY = 1.0

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
await update.message.reply_text(
“👋 *Solana Buy Bot*\n\n”
“Notifies you on every buy above your minimum threshold.\n”
“Watch *multiple tokens at once!*\n\n”
“📋 *Commands:*\n”
“`/watch <contract>` - Start watching a token\n”
“`/unwatch <contract>` - Stop watching a specific token\n”
“`/stopall` - Stop watching all tokens\n”
“`/list` - Show all watched tokens\n”
“`/status` - Summary stats\n”
“`/setmin <amount>` - Set minimum buy in USD (default: $1)\n”
“`/getmin` - Show current minimum buy\n\n”
“Example:\n”
“`/watch EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v`\n”
“`/setmin 50` - Only show buys of $50+”,
parse_mode=“Markdown”
)

async def setmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
chat_id = update.effective_chat.id

```
if not context.args:
    await update.message.reply_text(
        "❌ Please provide an amount.\n"
        "Usage: `/setmin <amount>`\n"
        "Example: `/setmin 50`",
        parse_mode="Markdown"
    )
    return

try:
    amount = float(context.args[0].replace("$", "").strip())
    if amount < 0:
        raise ValueError
except ValueError:
    await update.message.reply_text(
        "❌ Invalid amount. Please enter a positive number.\n"
        "Example: `/setmin 25`",
        parse_mode="Markdown"
    )
    return

min_buy_usd[chat_id] = amount
await update.message.reply_text(
    f"✅ Minimum buy set to *${amount:,.2f}*\n\n"
    f"Only buys of ${amount:,.2f} or more will be posted.",
    parse_mode="Markdown"
)

if chat_id in monitors:
    for monitor in monitors[chat_id].values():
        monitor.min_buy_usd = amount
```

async def getmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
chat_id = update.effective_chat.id
amount = min_buy_usd.get(chat_id, DEFAULT_MIN_BUY)
await update.message.reply_text(
f”📏 Current minimum buy: *${amount:,.2f}*\n”
f”Use `/setmin <amount>` to change it.”,
parse_mode=“Markdown”
)

async def watch(update: Update, context: ContextTypes.DEFAULT_TYPE):
chat_id = update.effective_chat.id

```
if not context.args:
    await update.message.reply_text(
        "❌ Please provide a contract address.\n"
        "Usage: `/watch <contract_address>`",
        parse_mode="Markdown"
    )
    return

contract = context.args[0].strip()

if len(contract) < 32 or len(contract) > 44:
    await update.message.reply_text(
        "❌ That does not look like a valid Solana contract address.\n"
        "Solana addresses are 32-44 characters long.",
        parse_mode="Markdown"
    )
    return

if chat_id not in monitors:
    monitors[chat_id] = {}

if contract in monitors[chat_id]:
    await update.message.reply_text(
        f"⚠️ Already watching `{contract[:6]}...{contract[-4:]}`",
        parse_mode="Markdown"
    )
    return

await update.message.reply_text(
    f"🔍 Starting monitor for:\n`{contract}`\n\nConnecting to Helius...",
    parse_mode="Markdown"
)

current_min = min_buy_usd.get(chat_id, DEFAULT_MIN_BUY)

monitor = SolanaMonitor(
    contract_address=contract,
    chat_id=chat_id,
    bot=context.application.bot,
    min_buy_usd=current_min
)

monitors[chat_id][contract] = monitor
asyncio.create_task(monitor.start())

count = len(monitors[chat_id])
await update.message.reply_text(
    f"✅ *Now watching:* `{contract[:6]}...{contract[-4:]}`\n\n"
    f"📏 Min buy threshold: *${current_min:,.2f}*\n"
    f"📡 Total tokens watched: *{count}*\n\n"
    f"`/list` to see all - `/setmin <amount>` to change threshold",
    parse_mode="Markdown"
)
```

async def unwatch(update: Update, context: ContextTypes.DEFAULT_TYPE):
chat_id = update.effective_chat.id

```
if not context.args:
    await update.message.reply_text(
        "❌ Please provide a contract address.\n"
        "Usage: `/unwatch <contract_address>`\n"
        "Use `/list` to see all watched tokens.",
        parse_mode="Markdown"
    )
    return

contract = context.args[0].strip()

if chat_id not in monitors or contract not in monitors[chat_id]:
    await update.message.reply_text(
        f"⚠️ Not watching `{contract[:6]}...{contract[-4:]}`\n"
        "Use `/list` to see all watched tokens.",
        parse_mode="Markdown"
    )
    return

await monitors[chat_id][contract].stop()
del monitors[chat_id][contract]

remaining = len(monitors.get(chat_id, {}))
await update.message.reply_text(
    f"🛑 Stopped watching `{contract[:6]}...{contract[-4:]}`\n"
    f"📡 Tokens still being watched: *{remaining}*",
    parse_mode="Markdown"
)
```

async def stopall(update: Update, context: ContextTypes.DEFAULT_TYPE):
chat_id = update.effective_chat.id

```
if chat_id not in monitors or not monitors[chat_id]:
    await update.message.reply_text("⚠️ You are not watching any tokens right now.")
    return

count = len(monitors[chat_id])
for monitor in monitors[chat_id].values():
    await monitor.stop()
monitors[chat_id] = {}

await update.message.reply_text(
    f"🛑 Stopped watching all *{count}* token(s).\n"
    "Use `/watch <contract>` to start again.",
    parse_mode="Markdown"
)
```

async def list_tokens(update: Update, context: ContextTypes.DEFAULT_TYPE):
chat_id = update.effective_chat.id

```
if chat_id not in monitors or not monitors[chat_id]:
    await update.message.reply_text(
        "📭 Not watching any tokens right now.\n"
        "Use `/watch <contract>` to start.",
        parse_mode="Markdown"
    )
    return

current_min = min_buy_usd.get(chat_id, DEFAULT_MIN_BUY)
lines = [f"📡 *Currently Watching:*\n📏 Min buy: *${current_min:,.2f}*\n"]

for i, (contract, monitor) in enumerate(monitors[chat_id].items(), 1):
    status_icon = "🟢" if monitor.running else "🔴"
    lines.append(
        f"{i}. {status_icon} `{contract[:6]}...{contract[-4:]}`\n"
        f"   Buys posted: *{monitor.buy_count}* | Filtered: *{monitor.filtered_count}*\n"
        f"   `{contract}`"
    )

lines.append(f"\n*Total: {len(monitors[chat_id])} token(s)*")
await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
```

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
chat_id = update.effective_chat.id

```
if chat_id not in monitors or not monitors[chat_id]:
    await update.message.reply_text(
        "📭 Not watching any tokens.\nUse `/watch <contract>` to start.",
        parse_mode="Markdown"
    )
    return

if context.args:
    contract = context.args[0].strip()
    if contract not in monitors[chat_id]:
        await update.message.reply_text(
            f"⚠️ Not watching `{contract[:6]}...{contract[-4:]}`\n"
            "Use `/list` to see all watched tokens.",
            parse_mode="Markdown"
        )
        return
    monitor = monitors[chat_id][contract]
    await update.message.reply_text(
        f"📊 *Token Status*\n\n"
        f"Contract: `{contract}`\n"
        f"Buys posted: *{monitor.buy_count}*\n"
        f"Filtered (below min): *{monitor.filtered_count}*\n"
        f"Min threshold: *${monitor.min_buy_usd:,.2f}*\n"
        f"Status: {'🟢 Running' if monitor.running else '🔴 Stopped'}",
        parse_mode="Markdown"
    )
else:
    current_min = min_buy_usd.get(chat_id, DEFAULT_MIN_BUY)
    total_buys = sum(m.buy_count for m in monitors[chat_id].values())
    total_filtered = sum(m.filtered_count for m in monitors[chat_id].values())
    running = sum(1 for m in monitors[chat_id].values() if m.running)
    await update.message.reply_text(
        f"📊 *Summary*\n\n"
        f"Tokens watched: *{len(monitors[chat_id])}*\n"
        f"Active monitors: *{running}*\n"
        f"Min buy threshold: *${current_min:,.2f}*\n"
        f"Total buys posted: *{total_buys}*\n"
        f"Total filtered out: *{total_filtered}*\n\n"
        f"Use `/list` to see each token.",
        parse_mode="Markdown"
    )
```

def main():
if not TELEGRAM_TOKEN:
raise ValueError(“TELEGRAM_TOKEN environment variable not set!”)

```
app = Application.builder().token(TELEGRAM_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("watch", watch))
app.add_handler(CommandHandler("unwatch", unwatch))
app.add_handler(CommandHandler("stopall", stopall))
app.add_handler(CommandHandler("list", list_tokens))
app.add_handler(CommandHandler("status", status))
app.add_handler(CommandHandler("setmin", setmin))
app.add_handler(CommandHandler("getmin", getmin))

logger.info("Bot started!")
app.run_polling(allowed_updates=Update.ALL_TYPES)
```

if **name** == “**main**”:
main()
