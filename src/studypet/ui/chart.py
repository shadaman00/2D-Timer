"""공부 기록장 탭용 더블 버퍼링 GDI 가로 막대 차트 컨트롤 (DEVELOPMENT_PLAN.md 4-16)."""
from __future__ import annotations

import ctypes
from ctypes import wintypes as wt

from typing import Sequence

from studypet.crashlog import write_crash_log
from studypet.domain.stats import StatRowLike, achievement_pct, format_korean_hm
from studypet.graphics.text import rgb_to_colorref
from studypet.win32.api import (
    IDC_ARROW,
    LPARAM,
    LRESULT,
    PAINTSTRUCT,
    RECT,
    TRANSPARENT,
    WM_DESTROY,
    WM_MOUSEWHEEL,
    WM_PAINT,
    WNDCLASSEXW,
    WNDPROC,
    WPARAM,
    WS_BORDER,
    WS_CHILD,
    WS_VISIBLE,
    gdi32,
    kernel32,
    user32,
)


CHART_CLASS_NAME = "StudyPetChart"
_chart_class_registered = False

SRCCOPY = 0x00CC0020
PS_DOT = 2


def parse_hex_colorref(hex_str: str) -> int:
    s = hex_str.strip().lstrip("#")
    if len(s) == 6:
        try:
            r = int(s[0:2], 16)
            g = int(s[2:4], 16)
            b = int(s[4:6], 16)
            return rgb_to_colorref(r, g, b)
        except ValueError:
            pass
    return rgb_to_colorref(91, 141, 239)


class ChartControl:
    """과목별 가로 막대, 라벨(과목명 N시간 M분 달성률%), 목표선(점선), 10개 초과 시 스크롤을 제공하는 커스텀 GDI 차트 창."""

    def __init__(self, parent_hwnd: wt.HWND, x: int, y: int, w: int, h: int, dpi: int) -> None:
        self.parent_hwnd = parent_hwnd
        self.w = max(100, int(w))
        self.h = max(80, int(h))
        self.dpi = max(96, int(dpi))
        self.s = self.dpi / 96.0
        self._rows: list[StatRowLike] = []
        self._days: int = 1
        self._scroll_y: int = 0
        self._max_scroll_y: int = 0

        font_h = -int(round(12 * self.s))
        self._hfont: wt.HFONT = gdi32.CreateFontW(font_h, 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 0, 0, "맑은 고딕")
        self._wndproc_ref = WNDPROC(self._wnd_proc)
        self._ensure_class()

        hinst = kernel32.GetModuleHandleW(None)
        self.hwnd: wt.HWND = user32.CreateWindowExW(
            0,
            CHART_CLASS_NAME,
            "",
            WS_CHILD | WS_VISIBLE | WS_BORDER,
            int(x),
            int(y),
            self.w,
            self.h,
            parent_hwnd,
            None,
            hinst,
            None,
        )

    def _ensure_class(self) -> None:
        global _chart_class_registered
        if _chart_class_registered:
            return
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.style = 0
        wc.lpfnWndProc = self._wndproc_ref
        wc.cbClsExtra = 0
        wc.cbWndExtra = 0
        wc.hInstance = hinst
        wc.hIcon = None
        wc.hCursor = user32.LoadCursorW(None, ctypes.c_void_p(IDC_ARROW))
        wc.hbrBackground = None
        wc.lpszMenuName = None
        wc.lpszClassName = CHART_CLASS_NAME
        wc.hIconSm = None
        user32.RegisterClassExW(ctypes.byref(wc))
        _chart_class_registered = True

    def set_data(self, rows: Sequence[StatRowLike], days: int) -> None:
        self._rows = list(rows)
        self._days = max(1, int(days))
        row_h = int(round(28 * self.s))
        content_h = len(self._rows) * row_h + int(round(16 * self.s))
        self._max_scroll_y = max(0, content_h - self.h)
        self._scroll_y = max(0, min(self._max_scroll_y, self._scroll_y))
        if self.hwnd:
            user32.InvalidateRect(self.hwnd, None, False)

    def _paint(self, hwnd: wt.HWND) -> None:
        ps = PAINTSTRUCT()
        hdc = user32.BeginPaint(hwnd, ctypes.byref(ps))
        if not hdc:
            return
        try:
            rc = RECT()
            user32.GetClientRect(hwnd, ctypes.byref(rc))
            cw = max(1, rc.right - rc.left)
            ch = max(1, rc.bottom - rc.top)

            mem_dc = gdi32.CreateCompatibleDC(hdc)
            mem_bmp = gdi32.CreateCompatibleBitmap(hdc, cw, ch)
            old_bmp = gdi32.SelectObject(mem_dc, mem_bmp)
            old_font = gdi32.SelectObject(mem_dc, self._hfont)
            try:
                bg_brush = gdi32.CreateSolidBrush(rgb_to_colorref(248, 249, 252))
                full_rc = RECT(0, 0, cw, ch)
                user32.FillRect(mem_dc, ctypes.byref(full_rc), bg_brush)
                gdi32.DeleteObject(bg_brush)

                gdi32.SetBkMode(mem_dc, TRANSPARENT)

                if not self._rows:
                    gdi32.SetTextColor(mem_dc, rgb_to_colorref(120, 125, 140))
                    msg = "표시할 과목 기록이 없습니다."
                    gdi32.TextOutW(mem_dc, int(16 * self.s), int(20 * self.s), msg, len(msg))
                else:
                    row_h = int(round(28 * self.s))
                    pad_x = int(round(12 * self.s))
                    label_w = int(round(220 * self.s))
                    bar_left = pad_x + label_w
                    bar_max_w = max(40, cw - bar_left - int(round(36 * self.s)))
                    goal_x = bar_left + int(bar_max_w * 0.75)

                    # 목표선(100% 기준선) 점선 그리기
                    dot_pen = gdi32.CreatePen(PS_DOT, 1, rgb_to_colorref(170, 175, 195))
                    old_pen = gdi32.SelectObject(mem_dc, dot_pen)
                    gdi32.MoveToEx(mem_dc, goal_x, 0, None)
                    gdi32.LineTo(mem_dc, goal_x, ch)
                    gdi32.SelectObject(mem_dc, old_pen)
                    gdi32.DeleteObject(dot_pen)

                    track_brush = gdi32.CreateSolidBrush(rgb_to_colorref(228, 231, 240))
                    try:
                        for idx, row in enumerate(self._rows):
                            y = int(round(8 * self.s)) + idx * row_h - self._scroll_y
                            if y + row_h < 0 or y > ch:
                                continue

                            pct = achievement_pct(row.total_seconds, row.daily_goal_minutes, self._days)
                            hm_str = format_korean_hm(row.total_seconds)
                            lbl = f"{row.name[:10]}  {hm_str} ({pct:.0f}%)"
                            gdi32.SetTextColor(mem_dc, rgb_to_colorref(35, 38, 52))
                            gdi32.TextOutW(mem_dc, pad_x, y + int(round(4 * self.s)), lbl, len(lbl))

                            bar_top = y + int(round(5 * self.s))
                            bar_bottom = y + row_h - int(round(6 * self.s))
                            track_rc = RECT(bar_left, bar_top, bar_left + bar_max_w, bar_bottom)
                            user32.FillRect(mem_dc, ctypes.byref(track_rc), track_brush)

                            # 100%가 goal_x(bar_max_w * 0.75)에 오도록 비율 계산 (최대 133%까지 표시)
                            ratio = min(1.333, max(0.0, pct / 100.0))
                            fill_w = int(round((bar_max_w * 0.75) * ratio))
                            if fill_w > 0:
                                c_brush = gdi32.CreateSolidBrush(parse_hex_colorref(row.color_code))
                                fill_rc = RECT(bar_left, bar_top, min(bar_left + bar_max_w, bar_left + fill_w), bar_bottom)
                                user32.FillRect(mem_dc, ctypes.byref(fill_rc), c_brush)
                                gdi32.DeleteObject(c_brush)
                    finally:
                        gdi32.DeleteObject(track_brush)

                gdi32.BitBlt(hdc, 0, 0, cw, ch, mem_dc, 0, 0, SRCCOPY)
            finally:
                gdi32.SelectObject(mem_dc, old_font)
                gdi32.SelectObject(mem_dc, old_bmp)
                gdi32.DeleteObject(mem_bmp)
                gdi32.DeleteDC(mem_dc)
        finally:
            user32.EndPaint(hwnd, ctypes.byref(ps))

    def _wnd_proc(self, hwnd: wt.HWND, msg: int, wparam: int, lparam: int) -> int:
        try:
            if msg == WM_PAINT:
                self._paint(hwnd)
                return 0
            if msg == WM_MOUSEWHEEL:
                delta_raw = (int(wparam) >> 16) & 0xFFFF
                delta = delta_raw - 0x10000 if delta_raw >= 0x8000 else delta_raw
                step = int(round(28 * self.s))
                if delta < 0:
                    self._scroll_y = min(self._max_scroll_y, self._scroll_y + step)
                elif delta > 0:
                    self._scroll_y = max(0, self._scroll_y - step)
                user32.InvalidateRect(hwnd, None, False)
                return 0
            if msg == WM_DESTROY:
                return 0
        except Exception:
            write_crash_log()
            return 0
        return int(user32.DefWindowProcW(hwnd, msg, WPARAM(wparam), LPARAM(lparam)))

    def destroy(self) -> None:
        if self.hwnd:
            user32.DestroyWindow(self.hwnd)
            self.hwnd = wt.HWND(0)
        if self._hfont:
            gdi32.DeleteObject(self._hfont)
            self._hfont = wt.HFONT(0)
