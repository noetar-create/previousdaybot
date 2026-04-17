from __future__ import annotations
from enum import Enum
from pydantic import BaseModel, Field


class Strategy(str, Enum):
    OVERNIGHT = "OVERNIGHT"
    RTH_PDHL = "RTH_PDHL"


class Action(str, Enum):
    LONG_ENTRY = "long_entry"
    SHORT_ENTRY = "short_entry"
    LONG_EXIT = "long_exit"
    SHORT_EXIT = "short_exit"


class Signal(BaseModel):
    secret: str = ""
    strategy: Strategy
    action: Action
    price: float
    ticker: str = "MNQ1!"
    contracts: int = 2
    stop_pts: float = 15.0

    @property
    def is_entry(self) -> bool:
        return self.action in (Action.LONG_ENTRY, Action.SHORT_ENTRY)

    @property
    def is_exit(self) -> bool:
        return self.action in (Action.LONG_EXIT, Action.SHORT_EXIT)

    @property
    def direction(self) -> str:
        return "long" if self.action in (Action.LONG_ENTRY, Action.LONG_EXIT) else "short"
