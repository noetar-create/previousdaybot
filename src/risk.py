from __future__ import annotations
from datetime import date

from .schemas import Signal
from .state import store

POINT_VALUE = 2.0  # USD per point per MNQ contract


class RiskTracker:
    async def record_entry(self, sig: Signal) -> None:
        await store.set_open_position(
            strategy=sig.strategy.value,
            direction=sig.direction,
            ticker=sig.ticker,
            entry_price=sig.price,
            contracts=sig.contracts,
            stop_pts=sig.stop_pts,
        )

    async def record_exit(self, sig: Signal) -> tuple[float, float]:
        pos = await store.clear_open_position()
        if not pos:
            return 0.0, 0.0

        entry = pos["entry_price"]
        contracts = pos["contracts"]

        if pos["direction"] == "long":
            pts = round(sig.price - entry, 2)
        else:
            pts = round(entry - sig.price, 2)

        usd = round(pts * POINT_VALUE * contracts, 2)
        return pts, usd

    async def daily_pnl(self, d: date | None = None):
        return await store.daily_pnl(d)


tracker = RiskTracker()
