from __future__ import annotations
from datetime import date
from typing import Any

import aiosqlite

DB_PATH = "bot.db"


class StateStore:
    async def init_db(self) -> None:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS trades (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    strategy    TEXT,
                    action      TEXT,
                    direction   TEXT,
                    ticker      TEXT,
                    price       REAL,
                    contracts   INTEGER,
                    stop_pts    REAL,
                    pnl_points  REAL,
                    pnl_usd     REAL,
                    note        TEXT
                );

                CREATE TABLE IF NOT EXISTS open_positions (
                    id          INTEGER PRIMARY KEY,
                    strategy    TEXT,
                    direction   TEXT,
                    ticker      TEXT,
                    entry_price REAL,
                    contracts   INTEGER,
                    stop_pts    REAL,
                    entry_ts    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS kill_switch (
                    id     INTEGER PRIMARY KEY CHECK (id = 1),
                    active INTEGER DEFAULT 0,
                    reason TEXT,
                    ts     TIMESTAMP
                );

                INSERT OR IGNORE INTO kill_switch (id, active) VALUES (1, 0);
            """)
            await db.commit()

    async def current_open_position(self) -> dict[str, Any] | None:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM open_positions LIMIT 1") as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def set_open_position(self, strategy: str, direction: str, ticker: str,
                                 entry_price: float, contracts: int, stop_pts: float) -> None:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM open_positions")
            await db.execute(
                "INSERT INTO open_positions (strategy, direction, ticker, entry_price, contracts, stop_pts) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (strategy, direction, ticker, entry_price, contracts, stop_pts),
            )
            await db.commit()

    async def clear_open_position(self) -> dict[str, Any] | None:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM open_positions LIMIT 1") as cur:
                row = await cur.fetchone()
                pos = dict(row) if row else None
            await db.execute("DELETE FROM open_positions")
            await db.commit()
        return pos

    async def insert_trade(self, **kwargs: Any) -> None:
        async with aiosqlite.connect(DB_PATH) as db:
            cols = ", ".join(kwargs.keys())
            placeholders = ", ".join("?" * len(kwargs))
            await db.execute(
                f"INSERT INTO trades ({cols}) VALUES ({placeholders})",
                list(kwargs.values()),
            )
            await db.commit()

    async def kill_switch_active(self) -> bool:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT active FROM kill_switch WHERE id=1") as cur:
                row = await cur.fetchone()
                return bool(row[0]) if row else False

    async def set_kill_switch(self, active: bool, reason: str | None) -> None:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE kill_switch SET active=?, reason=?, ts=CURRENT_TIMESTAMP WHERE id=1",
                (int(active), reason),
            )
            await db.commit()

    async def daily_pnl(self, d: date | None = None) -> dict[str, Any]:
        target = str(d or date.today())
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                """SELECT
                       COALESCE(SUM(pnl_usd), 0),
                       COUNT(*),
                       COALESCE(SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END), 0),
                       COALESCE(SUM(CASE WHEN pnl_usd <= 0 THEN 1 ELSE 0 END), 0)
                   FROM trades
                   WHERE date(ts) = ? AND pnl_usd IS NOT NULL""",
                (target,),
            ) as cur:
                row = await cur.fetchone()
                return {
                    "date": target,
                    "pnl_usd": round(row[0], 2),
                    "entries": row[1],
                    "wins": row[2],
                    "losses": row[3],
                }


store = StateStore()
