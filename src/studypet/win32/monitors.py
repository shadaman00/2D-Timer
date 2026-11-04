"""멀티 모니터, 작업 영역, Per-Monitor DPI v2 조회 (DEVELOPMENT_PLAN.md 4-3)."""
from __future__ import annotations

import ctypes
from ctypes import wintypes as wt
from dataclasses import dataclass

from studypet.win32.api import (
    DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2,
    LPARAM,
    MDT_EFFECTIVE_DPI,
    MONITOR_DEFAULTTONEAREST,
    MONITOR_DEFAULTTOPRIMARY,
    MONITORENUMPROC,
    MONITORINFO,
    POINT,
    RECT,
    shcore,
    user32,
)


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    def contains(self, x: int, y: int) -> bool:
        return self.left <= x < self.right and self.top <= y < self.bottom


@dataclass(frozen=True)
class MonitorInfo:
    handle: int
    monitor: Rect
    work: Rect
    dpi: int
    is_primary: bool


_cached_monitors: list[MonitorInfo] | None = None


def enable_per_monitor_dpi() -> None:
    if not user32.SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2):
        try:
            shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
        except OSError:
            pass


def invalidate_monitor_cache() -> None:
    global _cached_monitors
    _cached_monitors = None


def _query_monitor_info(hmon: int) -> MonitorInfo:
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    if not user32.GetMonitorInfoW(wt.HMONITOR(hmon), ctypes.byref(mi)):
        return MonitorInfo(
            handle=hmon,
            monitor=Rect(0, 0, 1920, 1080),
            work=Rect(0, 0, 1920, 1040),
            dpi=96,
            is_primary=True,
        )
    dpi_x = wt.UINT(96)
    dpi_y = wt.UINT(96)
    try:
        hr = shcore.GetDpiForMonitor(
            wt.HMONITOR(hmon),
            MDT_EFFECTIVE_DPI,
            ctypes.byref(dpi_x),
            ctypes.byref(dpi_y),
        )
        dpi = int(dpi_x.value) if hr == 0 and dpi_x.value > 0 else 96
    except OSError:
        dpi = 96

    mon_rect = Rect(mi.rcMonitor.left, mi.rcMonitor.top, mi.rcMonitor.right, mi.rcMonitor.bottom)
    work_rect = Rect(mi.rcWork.left, mi.rcWork.top, mi.rcWork.right, mi.rcWork.bottom)
    is_primary = bool(mi.dwFlags & 1)  # MONITORINFOF_PRIMARY == 1
    return MonitorInfo(handle=hmon, monitor=mon_rect, work=work_rect, dpi=dpi, is_primary=is_primary)


def list_monitors() -> list[MonitorInfo]:
    global _cached_monitors
    if _cached_monitors is not None:
        return _cached_monitors

    handles: list[int] = []

    def _cb(hmon: wt.HMONITOR, hdc: wt.HDC, lprect: ctypes.POINTER(RECT), lparam: LPARAM) -> int:
        if hmon:
            handles.append(int(hmon))
        return 1

    enum_proc = MONITORENUMPROC(_cb)
    user32.EnumDisplayMonitors(None, None, enum_proc, 0)
    result = [_query_monitor_info(h) for h in handles]
    if not result:
        hprim = user32.MonitorFromPoint(POINT(0, 0), MONITOR_DEFAULTTOPRIMARY)
        result = [_query_monitor_info(int(hprim or 0))]
    _cached_monitors = result
    return result


def monitor_at(x: int, y: int) -> MonitorInfo:
    hmon = user32.MonitorFromPoint(POINT(int(x), int(y)), MONITOR_DEFAULTTONEAREST)
    if hmon:
        for m in list_monitors():
            if m.handle == int(hmon):
                return m
        return _query_monitor_info(int(hmon))
    return primary()


def primary() -> MonitorInfo:
    for m in list_monitors():
        if m.is_primary:
            return m
    mons = list_monitors()
    return mons[0]


def phys_scale(config_scale: int, dpi: int) -> int:
    """일반 반올림(round half up)으로 물리 픽셀 배율을 계산한다 (은행가 반올림 금지)."""
    return max(1, int(config_scale * dpi / 96 + 0.5))

