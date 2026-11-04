"""대시보드 탭 3: 공부 기록장 (일/주/월 통계, 실시간 합산, 막대 차트, CSV 내보내기) (DEVELOPMENT_PLAN.md 4-16)."""
from __future__ import annotations

from collections.abc import Callable
import ctypes
from ctypes import wintypes as wt
from datetime import date, timedelta
from typing import Literal

from studypet.crashlog import write_crash_log
from studypet.domain.stats import (
    PeriodKind,
    format_korean_hm,
    merge_live,
    overall_pct,
    period_days,
    period_range,
)
from studypet.infra.db import StatsRepository, SubjectRepository, SubjectTotal
from studypet.ui.chart import ChartControl
from studypet.win32.api import (
    IDC_ARROW,
    LPARAM,
    LRESULT,
    WM_COMMAND,
    WM_DESTROY,
    WM_SETFONT,
    WNDCLASSEXW,
    WNDPROC,
    WPARAM,
    WS_CHILD,
    WS_EX_CONTROLPARENT,
    WS_TABSTOP,
    WS_VISIBLE,
    kernel32,
    user32,
)


TAB_STATS_CLASS = "StudyPetTabStats"
_tab_stats_registered = False

ID_BTN_DAY = 501
ID_BTN_WEEK = 502
ID_BTN_MONTH = 503
ID_BTN_PREV = 504
ID_BTN_NEXT = 505
ID_BTN_TODAY = 506
ID_BTN_CSV = 507

COLOR_BTNFACE = 15


class StatsTab:
    """일·주·월 통계 조회, 진행 중 세션 실시간 반영, 차트 렌더링, CSV 내보내기 탭 패널."""

    def __init__(
        self,
        parent_hwnd: wt.HWND,
        x: int,
        y: int,
        w: int,
        h: int,
        dpi: int,
        hfont: wt.HFONT,
        stats_repo: StatsRepository,
        subject_repo: SubjectRepository,
        get_today: Callable[[], date],
        get_live_credit: Callable[[], tuple[int, date, int] | None],
        on_export_csv: Callable[[], None],
    ) -> None:
        self.dpi = dpi
        self.s = max(1.0, dpi / 96.0)
        self.hfont = hfont
        self.stats_repo = stats_repo
        self.subject_repo = subject_repo
        self.get_today = get_today
        self.get_live_credit = get_live_credit
        self.on_export_csv = on_export_csv

        self.kind: PeriodKind = "day"
        self.anchor: date = self.get_today()
        self._cached_rows: list[SubjectTotal] = []
        self._cached_range: tuple[date, date] | None = None

        self._wndproc_ref = WNDPROC(self._wnd_proc)
        self._ensure_class()

        hinst = kernel32.GetModuleHandleW(None)
        self.hwnd: wt.HWND = user32.CreateWindowExW(
            WS_EX_CONTROLPARENT,
            TAB_STATS_CLASS,
            "",
            WS_CHILD,
            int(x),
            int(y),
            int(w),
            int(h),
            parent_hwnd,
            None,
            hinst,
            None,
        )

        def px(v: int) -> int:
            return int(round(v * self.s))

        # 상단 기간 종류 및 이동 버튼
        self._btn_day = self._create_ctrl("BUTTON", "일(Day)", WS_CHILD | WS_VISIBLE | WS_TABSTOP, px(16), px(12), px(74), px(28), ID_BTN_DAY)
        self._btn_week = self._create_ctrl("BUTTON", "주(Week)", WS_CHILD | WS_VISIBLE | WS_TABSTOP, px(96), px(12), px(80), px(28), ID_BTN_WEEK)
        self._btn_month = self._create_ctrl("BUTTON", "월(Month)", WS_CHILD | WS_VISIBLE | WS_TABSTOP, px(182), px(12), px(84), px(28), ID_BTN_MONTH)

        self._btn_prev = self._create_ctrl("BUTTON", "◀", WS_CHILD | WS_VISIBLE | WS_TABSTOP, px(284), px(12), px(38), px(28), ID_BTN_PREV)
        self._btn_today = self._create_ctrl("BUTTON", "오늘", WS_CHILD | WS_VISIBLE | WS_TABSTOP, px(328), px(12), px(58), px(28), ID_BTN_TODAY)
        self._btn_next = self._create_ctrl("BUTTON", "▶", WS_CHILD | WS_VISIBLE | WS_TABSTOP, px(392), px(12), px(38), px(28), ID_BTN_NEXT)

        self._btn_csv = self._create_ctrl("BUTTON", "CSV 내보내기", WS_CHILD | WS_VISIBLE | WS_TABSTOP, px(464), px(12), px(120), px(28), ID_BTN_CSV)

        # 기간 및 총 달성률 요약 라벨
        self._lbl_summary = self._create_ctrl("STATIC", "", WS_CHILD | WS_VISIBLE, px(16), px(48), px(568), px(24), 0)

        # 과목별 막대 차트 컨트롤
        self.chart = ChartControl(self.hwnd, px(16), px(76), px(568), px(276), self.dpi)

        self.refresh_stats()

    def _ensure_class(self) -> None:
        global _tab_stats_registered
        if _tab_stats_registered:
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
        wc.hbrBackground = wt.HBRUSH(COLOR_BTNFACE + 1)
        wc.lpszMenuName = None
        wc.lpszClassName = TAB_STATS_CLASS
        wc.hIconSm = None
        user32.RegisterClassExW(ctypes.byref(wc))
        _tab_stats_registered = True

    def _create_ctrl(self, cls: str, text: str, style: int, x: int, y: int, w: int, h: int, cid: int) -> wt.HWND:
        hinst = kernel32.GetModuleHandleW(None)
        hwnd = user32.CreateWindowExW(
            0,
            cls,
            text,
            style,
            x,
            y,
            w,
            h,
            self.hwnd,
            wt.HMENU(cid) if cid else None,
            hinst,
            None,
        )
        if self.hfont:
            user32.SendMessageW(hwnd, WM_SETFONT, WPARAM(int(self.hfont)), 1)
        return hwnd

    def _shift_anchor(self, delta: int) -> None:
        if self.kind == "day":
            self.anchor = self.anchor + timedelta(days=delta)
        elif self.kind == "week":
            self.anchor = self.anchor + timedelta(days=7 * delta)
        elif self.kind == "month":
            year = self.anchor.year
            month = self.anchor.month + delta
            while month < 1:
                month += 12
                year -= 1
            while month > 12:
                month -= 12
                year += 1
            self.anchor = date(year, month, 1)
        self.refresh_stats()

    def refresh_stats(self) -> None:
        """기간 변경·탭 진입 시 DB를 조회해 캐시하고 화면을 갱신한다 (v0.7 M4)."""
        start_d, end_d = period_range(self.kind, self.anchor)
        self._cached_range = (start_d, end_d)
        self._cached_rows = list(self.stats_repo.period_totals(start_d, end_d))
        self.refresh_live()

    def refresh_live(self) -> None:
        """DB 재조회 없이 캐시된 집계 행에 진행 중 세션 시간만 합산해 차트와 요약을 갱신한다 (v0.7 M4)."""
        if self._cached_range is None:
            self.refresh_stats()
            return
        start_d, end_d = self._cached_range
        days = period_days(self.kind, start_d, end_d)
        domain_rows: list[SubjectTotal] = list(self._cached_rows)

        live = self.get_live_credit()
        if live is not None:
            live_sid, live_date, live_sec = live
            # 진행 중 과목이 아직 DB 완료 기록이 없는 보관 과목일 경우 보충
            if start_d <= live_date <= end_d and live_sec > 0 and not any(r.subject_id == live_sid for r in domain_rows):
                subj = self.subject_repo.get(live_sid)
                if subj is not None:
                    domain_rows.append(
                        SubjectTotal(
                            subject_id=subj.id,
                            name=subj.name,
                            color_code=subj.color_code,
                            daily_goal_minutes=subj.daily_goal_minutes,
                            is_archived=subj.is_archived,
                            total_seconds=0,
                        )
                    )

        merged = merge_live(domain_rows, live, start_d, end_d)
        total_sec = sum(r.total_seconds for r in merged)
        tot_pct = overall_pct(merged, days)

        if start_d == end_d:
            period_str = f"{start_d.isoformat()} (일간)"
        else:
            kind_lbl = "주간" if self.kind == "week" else f"월간 {days}일"
            period_str = f"{start_d.isoformat()} ~ {end_d.isoformat()} ({kind_lbl})"

        summary = f"기간: {period_str}   |   총 학습 시간: {format_korean_hm(total_sec)}   |   전체 목표 달성률: {tot_pct:.1f}%"
        user32.SetWindowTextW(self._lbl_summary, summary)
        self.chart.set_data(merged, days)

    def _wnd_proc(self, hwnd: wt.HWND, msg: int, wparam: int, lparam: int) -> int:
        try:
            if msg == WM_COMMAND:
                cid = int(wparam) & 0xFFFF
                if cid == ID_BTN_DAY:
                    self.kind = "day"
                    self.refresh_stats()
                elif cid == ID_BTN_WEEK:
                    self.kind = "week"
                    self.refresh_stats()
                elif cid == ID_BTN_MONTH:
                    self.kind = "month"
                    self.refresh_stats()
                elif cid == ID_BTN_PREV:
                    self._shift_anchor(-1)
                elif cid == ID_BTN_NEXT:
                    self._shift_anchor(1)
                elif cid == ID_BTN_TODAY:
                    self.anchor = self.get_today()
                    self.refresh_stats()
                elif cid == ID_BTN_CSV:
                    self.on_export_csv()
                return 0
            if msg == WM_DESTROY:
                return 0
        except Exception:
            write_crash_log()
            return 0
        return int(user32.DefWindowProcW(hwnd, msg, WPARAM(wparam), LPARAM(lparam)))

    def destroy(self) -> None:
        self.chart.destroy()
