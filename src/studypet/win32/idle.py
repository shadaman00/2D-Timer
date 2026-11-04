"""전역 키보드·마우스 유휴 시간 조회 (DEVELOPMENT_PLAN.md 4-7)."""
from __future__ import annotations

import ctypes

from studypet.win32.api import LASTINPUTINFO, kernel32, user32


def compute_idle_ms(tick_count: int, dw_time: int) -> int:
    """GetTickCount 32-bit(49.7일) 오버플로우 되감기에 안전한 경과 밀리초 계산."""
    return (int(tick_count) - int(dw_time)) & 0xFFFFFFFF


def get_idle_ms() -> int:
    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if not user32.GetLastInputInfo(ctypes.byref(lii)):
        return 0
    now_tick = int(kernel32.GetTickCount())
    return compute_idle_ms(now_tick, int(lii.dwTime))

