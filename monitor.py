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
SOL_MINT = "So11111111111111111111111111111111111111112"


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
        await self._refresh_sol_price()
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
            logger.info("SOL price: $" + "{:.2f}".format(price))
        else:
            logger.warning("Could not fetch SOL price, will retry on next poll")

    async def _fetch_sol_price(self) -> float:
        # Use Helius asset API to get SOL price - same domain we already use
        try:
            url = "https://mainnet.helius-rpc.com/?api-key=" + str(HELIUS_API_KEY)
            payload = {
                "jsonrpc": "2.0",
                "id": "sol-price",
                "method": "getAsset",
                "params": {"id": SOL_MINT}
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        token_info = data.get("result", {}).get("token_info", {})
                        price = token_info.get("price_info", {}).get("price_per_token", 0)
                        if price and price > 0:
                            return float(price)
        except Exception as e:
            logger.warning("Helius asset price failed: " + str(e))

        # Fallback: derive SOL price from a recent USDC swap via Helius transactions
        try:
            url = (
                "https://api.helius.xyz/v0/addresses/"
                + SOL_MINT
                + "/transactions?api-key="
                + str(HELIUS_API_KEY)
                + "&limit=1&type=SWAP"
            )
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        txs = await resp.json()
                        if txs:
                            tx = txs[0]
                            transfers = tx.get("tokenTransfers", [])
                            native = tx.get("nativeTransfers", [])
                            # Find SOL amount and USDC amount in same tx
                            usdc_amount = 0
                            sol_lamports = 0
                            for t in transfers:
                                if t.get("mint") == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v":
                                    usdc_amount = t.get("tokenAmount", 0)
                            for t in native:
                                sol_lamports += t.get("amount", 0)
                            if usdc_amount > 0 and sol_lamports > 0:
                                sol_amount = sol_lamports / 1e9
                                return round(usdc_amount / sol_amount, 2)
        except Exception as e:
            logger.warning("Swap-derived price failed: " + str(e))

        return 0.0

    async def _get_usd_value(self, sol_amount: float) -> float:
        now = asyncio.get_event_loop().time()
        if self._sol_price_cache == 0 or (now - self._sol_price_last_fetch) > 60:
            await self._refresh_sol_price()
        if self._sol_price_cache == 0:
            # Last resort: use a hardcoded fallback so buys still post
            logger.warning("Using fallback SOL price $130")
            return round(sol_amount * 130, 2)
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
