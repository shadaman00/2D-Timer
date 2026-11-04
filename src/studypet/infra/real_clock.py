"""QueryUnbiasedInterruptTime 기반 실측 시계 (DEVELOPMENT_PLAN.md 4-4)."""
from __future__ import annotations

import ctypes
from datetime import datetime

from studypet.win32.api import kernel32


class RealClock:
    """절전·최대 절전 시간을 제외하는 Windows 커널 Unbiased Interrupt Time 시계."""

    def mono_ns(self) -> int:
        t_100ns = ctypes.c_ulonglong(0)
        kernel32.QueryUnbiasedInterruptTime(ctypes.byref(t_100ns))
        return int(t_100ns.value) * 100

    def now_local(self) -> datetime:
        return datetime.now().astimezone()

