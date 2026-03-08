import os
import json
import asyncio
import logging
import aiohttp
import websockets
from telegram import Bot

logger = logging.getLogger(__name__)

HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")
HELIUS_WS_URL = "wss://mainnet.helius-rpc.com/?api-key=" + str(HELIUS_API_KEY)

DEX_PROGRAMS = {
"JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": "Jupiter",
"675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "Raydium",
"whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc": "Orca",
"6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P": "Pump.fun",
}

class SolanaMonitor:
def __init__(self, contract_address: str, chat_id: int, bot: Bot, min_buy_usd: float = 1.0):
self.contract_address = contract_address
self.chat_id = chat_id
self.bot = bot
self.min_buy_usd = min_buy_usd
self.running = False
self.buy_count = 0
self.filtered_count = 0
self._ws = None

```
async def start(self):
    self.running = True
    logger.info("Starting monitor for " + self.contract_address + " (min $" + str(self.min_buy_usd) + ")")

    while self.running:
        try:
            await self._connect_and_listen()
        except Exception as e:
            logger.error("WebSocket error: " + str(e))
            if self.running:
                logger.info("Reconnecting in 5s...")
                await asyncio.sleep(5)

async def stop(self):
    self.running = False
    if self._ws:
        await self._ws.close()
    logger.info("Monitor stopped for " + self.contract_address)

async def _connect_and_listen(self):
    ws_url = "wss://mainnet.helius-rpc.com/?api-key=" + str(HELIUS_API_KEY)
    async with websockets.connect(ws_url, ping_interval=30) as ws:
        self._ws = ws

        subscribe_msg = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "logsSubscribe",
            "params": [
                {"mentions": [self.contract_address]},
                {"commitment": "confirmed"}
            ]
        }

        await ws.send(json.dumps(subscribe_msg))
        response = await ws.recv()
        logger.info("Subscribed to " + self.contract_address[:8] + "...")

        async for message in ws:
            if not self.running:
                break
            try:
                await self._process_message(json.loads(message))
            except Exception as e:
                logger.error("Error processing message: " + str(e))

async def _process_message(self, data: dict):
    if data.get("method") != "logsNotification":
        return

    result = data.get("params", {}).get("result", {})
    value = result.get("value", {})
    logs = value.get("logs", [])
    signature = value.get("signature", "")
    err = value.get("err")

    if err:
        return

    if not self._is_buy_transaction(logs):
        return

    tx_details = await self._fetch_transaction(signature)
    if not tx_details:
        return

    buy_info = await self._parse_buy(tx_details, signature)
    if not buy_info:
        return

    if buy_info["usd_value"] < self.min_buy_usd:
        self.filtered_count += 1
        logger.info("Filtered buy: $" + str(buy_info["usd_value"]) + " < min $" + str(self.min_buy_usd))
        return

    self.buy_count += 1
    await self._send_notification(buy_info)

def _is_buy_transaction(self, logs: list) -> bool:
    log_str = " ".join(logs).lower()
    buy_indicators = ["swap", "trade", "buy", "exchange", "invoke"]
    has_indicator = any(ind in log_str for ind in buy_indicators)
    has_dex = any(prog in " ".join(logs) for prog in DEX_PROGRAMS)
    return has_indicator or has_dex

async def _fetch_transaction(self, signature: str) -> dict | None:
    url = "https://api.helius.xyz/v0/transactions?api-key=" + str(HELIUS_API_KEY)
    payload = {"transactions": [signature]}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data[0] if data else None
    except Exception as e:
        logger.error("Failed to fetch tx " + signature + ": " + str(e))
    return None

async def _parse_buy(self, tx: dict, signature: str) -> dict | None:
    try:
        fee_payer = tx.get("feePayer", "Unknown")
        token_transfers = tx.get("tokenTransfers", [])
        native_transfers = tx.get("nativeTransfers", [])
        source = tx.get("source", "")

        tokens_received = 0
        buyer_wallet = fee_payer

        for transfer in token_transfers:
            if transfer.get("mint") == self.contract_address:
                tokens_received = transfer.get("tokenAmount", 0)
                to_account = transfer.get("toUserAccount", "")
                if to_account:
                    buyer_wallet = to_account
                break

        if tokens_received == 0:
            return None

        sol_spent = 0
        for transfer in native_transfers:
            if transfer.get("fromUserAccount") == buyer_wallet:
                sol_spent += transfer.get("amount", 0)

        sol_amount = sol_spent / 1e9
        usd_value = await self._get_usd_value(sol_amount)

        return {
            "signature": signature,
            "buyer": buyer_wallet,
            "tokens_received": tokens_received,
            "sol_spent": sol_amount,
            "usd_value": usd_value,
            "dex": source,
        }

    except Exception as e:
        logger.error("Error parsing buy: " + str(e))
        return None

async def _get_usd_value(self, sol_amount: float) -> float:
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    sol_price = data.get("solana", {}).get("usd", 0)
                    return round(sol_amount * sol_price, 2)
    except Exception:
        pass
    return 0.0

async def _send_notification(self, buy: dict):
    contract_short = self.contract_address[:6] + "..." + self.contract_address[-4:]
    buyer_short = buy["buyer"][:6] + "..." + buy["buyer"][-4:]

    tokens = buy["tokens_received"]
    if tokens >= 1_000_000:
        tokens_str = str(round(tokens / 1_000_000, 2)) + "M"
    elif tokens >= 1_000:
        tokens_str = str(round(tokens / 1_000, 2)) + "K"
    else:
        tokens_str = str(round(tokens, 4))

    sol_str = str(round(buy["sol_spent"], 4)) if buy["sol_spent"] > 0 else "?"
    usd_str = "$" + "{:,.2f}".format(buy["usd_value"]) if buy["usd_value"] > 0 else "N/A"
    dex_name = DEX_PROGRAMS.get(buy["dex"], buy["dex"]) if buy["dex"] else "DEX"

    dex_screener = "https://dexscreener.com/solana/" + self.contract_address
    birdeye = "https://birdeye.so/token/" + self.contract_address + "?chain=solana"
    solscan_tx = "https://solscan.io/tx/" + buy["signature"]
    wallet_link = "https://solscan.io/account/" + buy["buyer"]

    message = (
        "🟢 *NEW BUY DETECTED!*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🪙 Token: `" + contract_short + "`\n"
        "🏦 DEX: *" + dex_name + "*\n\n"
        "👛 Buyer: [" + buyer_short + "](" + wallet_link + ")\n"
        "💰 Spent: *" + sol_str + " SOL* (" + usd_str + ")\n"
        "🎁 Received: *" + tokens_str + " tokens*\n\n"
        "🔗 [DexScreener](" + dex_screener + ") • "
        "[Birdeye](" + birdeye + ") • "
        "[TX](" + solscan_tx + ")\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "#" + str(self.buy_count) + " buy • min $" + "{:,.2f}".format(self.min_buy_usd)
    )

    try:
        await self.bot.send_message(
            chat_id=self.chat_id,
            text=message,
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error("Failed to send notification: " + str(e))
```
