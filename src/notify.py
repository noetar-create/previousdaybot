from __future__ import annotations
import logging

import httpx

from .schemas import Signal
from .settings import settings

log = logging.getLogger(__name__)


class TelegramNotifier:
    def _cfg(self):
        return settings()

    async def _send(self, text: str) -> None:
        cfg = self._cfg()
        if not cfg.telegram_token or not cfg.telegram_chat_id:
            log.warning("telegram_not_configured")
            return
        if cfg.dry_run_notify_only:
            log.info("DRY_RUN telegram: %s", text[:120])
            return
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    f"https://api.telegram.org/bot{cfg.telegram_token}/sendMessage",
                    json={"chat_id": cfg.telegram_chat_id, "text": text, "parse_mode": "HTML"},
                )
        except Exception as exc:
            log.warning("telegram_send_failed: %s", exc)

    async def send_entry_card(self, sig: Signal) -> None:
        direction_emoji = "🟢" if sig.direction == "long" else "🔴"
        strategy_label = "📊 OVERNIGHT" if sig.strategy.value == "OVERNIGHT" else "📈 RTH PREV DAY H/L"
        stop_price = round(
            sig.price - sig.stop_pts if sig.direction == "long" else sig.price + sig.stop_pts, 2
        )
        msg = (
            f"{direction_emoji} <b>{sig.direction.upper()} ENTRY</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Strategy: {strategy_label}\n"
            f"Ticker:   {sig.ticker}\n\n"
            f"📍 Entry:     <b>{sig.price:.2f}</b>\n"
            f"🛑 Stop:      <b>{stop_price:.2f}</b> ({sig.stop_pts} pts)\n"
            f"📦 Contracts: {sig.contracts}\n"
        )
        await self._send(msg)

    async def send_exit_card(self, sig: Signal, pnl_usd: float, pnl_pts: float) -> None:
        result_emoji = "✅" if pnl_usd > 0 else "🛑"
        msg = (
            f"{result_emoji} <b>TRADE CLOSED</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Exit price: <b>{sig.price:.2f}</b>\n"
            f"P&L:        <b>{pnl_pts:+.1f} pts  ${pnl_usd:+.2f}</b>\n"
        )
        await self._send(msg)

    async def send_alert(self, text: str) -> None:
        await self._send(f"⚠️ {text}")

    async def send_daily_summary(self, date_str: str, pnl_usd: float,
                                  entries: int, wins: int, losses: int) -> None:
        result_emoji = "✅" if pnl_usd >= 0 else "🔴"
        win_rate = round(wins / entries * 100) if entries else 0
        msg = (
            f"{result_emoji} <b>DAILY SUMMARY — {date_str}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"P&L:      <b>${pnl_usd:+.2f}</b>\n"
            f"Trades:   {entries}  (W:{wins} L:{losses}  {win_rate}% win rate)\n"
        )
        await self._send(msg)


telegram = TelegramNotifier()
