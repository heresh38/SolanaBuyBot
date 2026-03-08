import os
import asyncio
import logging
import aiohttp
from telegram import Bot

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")

DEX_PROGRAMS = {
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": "Jupiter",
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "Raydium",
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc": "Orca",
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P": "Pump.fun",
    "pumpCFAmQEPpFgJxMKwN3fwmQ8p8jD5HBn5DkaWbSXR": "Pump.fun AMM",
}

POLL_INTERVAL = 10


class SolanaMonitor:
    def __init__(self, contract_address: str, chat_id: int, bot: Bot, min_buy_usd: float = 1.0):
        self.contract_address = contract_address
        self.chat_id = chat_id
        self.bot = bot
        self.min_buy_usd = min_buy_usd
        self.running = False
        self.buy_count = 0
        self.filtered_count = 0
        self._seen_signatures = set()
        self._sol_price_cache = 0.0
        self._sol_price_last_fetch = 0

    async def start(self):
        self.running = True
        logger.info("Polling monitor started for " + self.contract_address)

        # Fetch SOL price immediately on startup
        await self._refresh_sol_price()

        # Seed existing so we dont alert on old txs
        await self._seed_existing_signatures()

        while self.running:
            try:
                await self._poll()
            except Exception as e:
                logger.error("Poll error: " + str(e))
            await asyncio.sleep(POLL_INTERVAL)

    async def stop(self):
        self.running = False
        logger.info("Monitor stopped for " + self.contract_address)

    async def _refresh_sol_price(self):
        price = await self._fetch_sol_price()
        if price > 0:
            self._sol_price_cache = price
            self._sol_price_last_fetch = asyncio.get_event_loop().time()
            logger.info("SOL price: $" + str(price))
        else:
            logger.warning("Could not fetch SOL price")

    async def _fetch_sol_price(self) -> float:
        # Try Binance first (no rate limit issues)
        try:
            url = "https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        price = float(data.get("price", 0))
                        if price > 0:
                            return price
        except Exception as e:
            logger.warning("Binance price fetch failed: " + str(e))

        # Fallback to CoinGecko
        try:
            url = "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return float(data.get("solana", {}).get("usd", 0))
        except Exception as e:
            logger.warning("CoinGecko price fetch failed: " + str(e))

        return 0.0

    async def _get_usd_value(self, sol_amount: float) -> float:
        now = asyncio.get_event_loop().time()
        # Refresh price every 60 seconds
        if self._sol_price_cache == 0 or (now - self._sol_price_last_fetch) > 60:
            await self._refresh_sol_price()
        return round(sol_amount * self._sol_price_cache, 2)

    async def _seed_existing_signatures(self):
        logger.info("Seeding existing signatures for " + self.contract_address[:8] + "...")
        txs = await self._fetch_recent_transactions(limit=10)
        for tx in txs:
            sig = tx.get("signature", "")
            if sig:
                self._seen_signatures.add(sig)
        logger.info("Seeded " + str(len(self._seen_signatures)) + " existing signatures")

    async def _poll(self):
        txs = await self._fetch_recent_transactions(limit=10)
        if not txs:
            logger.info("No transactions returned for " + self.contract_address[:8] + "...")
            return

        new_txs = [tx for tx in reversed(txs) if tx.get("signature") not in self._seen_signatures]

        if new_txs:
            logger.info("Found " + str(len(new_txs)) + " new transactions for " + self.contract_address[:8] + "...")

        for tx in new_txs:
            sig = tx.get("signature", "")
            if sig:
                self._seen_signatures.add(sig)
            if len(self._seen_signatures) > 500:
                self._seen_signatures = set(list(self._seen_signatures)[-200:])
            await self._process_transaction(tx)

    async def _fetch_recent_transactions(self, limit: int = 10):
        url = (
            "https://api.helius.xyz/v0/addresses/"
            + self.contract_address
            + "/transactions?api-key="
            + str(HELIUS_API_KEY)
            + "&limit="
            + str(limit)
            + "&type=SWAP"
        )
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        text = await resp.text()
                        logger.error("Helius API error " + str(resp.status) + ": " + text)
        except Exception as e:
            logger.error("Failed to fetch transactions: " + str(e))
        return []

    async def _process_transaction(self, tx: dict):
        signature = tx.get("signature", "")
        if tx.get("transactionError"):
            return

        buy_info = await self._parse_buy(tx, signature)
        if not buy_info:
            return

        if buy_info["usd_value"] < self.min_buy_usd:
            self.filtered_count += 1
            logger.info(
                "Filtered: $" + "{:.2f}".format(buy_info["usd_value"])
                + " < min $" + str(self.min_buy_usd)
                + " | " + signature[:12] + "..."
            )
            return

        self.buy_count += 1
        logger.info(
            "Buy #" + str(self.buy_count) + " posting: $"
            + "{:.2f}".format(buy_info["usd_value"])
            + " | " + signature[:12] + "..."
        )
        await self._send_notification(buy_info)

    async def _parse_buy(self, tx: dict, signature: str):
        try:
            fee_payer = tx.get("feePayer", "Unknown")
            token_transfers = tx.get("tokenTransfers", [])
            native_transfers = tx.get("nativeTransfers", [])
            source = tx.get("source", "")

            tokens_received = 0
            buyer_wallet = fee_payer

            for transfer in token_transfers:
                if transfer.get("mint") == self.contract_address:
                    amount = transfer.get("tokenAmount", 0)
                    to_account = transfer.get("toUserAccount", "")
                    if amount > 0 and to_account:
                        tokens_received = amount
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
            logger.error("Error parsing tx: " + str(e))
            return None

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
