from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

import pytz

EST = pytz.timezone("America/New_York")


class Phase(str, Enum):
    OVERNIGHT = "overnight"
    RTH = "rth"
    CLOSED = "closed"


@dataclass
class PhaseInfo:
    phase: Phase
    active_strategy: str | None
    allows_new_entries: bool


class SessionClock:
    def now_ny(self) -> datetime:
        return datetime.now(EST)

    def phase_at(self, dt: datetime | None = None) -> PhaseInfo:
        now = dt or self.now_ny()
        tod = now.hour * 60 + now.minute  # minutes since midnight

        # RTH: 09:30 (570) to 16:05 (965) inclusive
        if 570 <= tod <= 965:
            return PhaseInfo(Phase.RTH, "RTH_PDHL", True)

        # Closed: 16:06 (966) to 19:59 (1199)
        if 966 <= tod < 1200:
            return PhaseInfo(Phase.CLOSED, None, False)

        # Overnight: 20:00 (1200) to 09:29 (569) — wraps midnight
        return PhaseInfo(Phase.OVERNIGHT, "OVERNIGHT", True)

    def is_in_rth_window(self) -> bool:
        return self.phase_at().phase == Phase.RTH


clock = SessionClock()
