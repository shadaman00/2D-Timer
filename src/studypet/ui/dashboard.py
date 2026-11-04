"""통합 대시보드 프레임 창(640x480 * DPI/96, SysTabControl32) (DEVELOPMENT_PLAN.md 4-16)."""
from __future__ import annotations

from collections.abc import Callable
import ctypes
from ctypes import wintypes as wt
from datetime import date
from pathlib import Path

from studypet.crashlog import write_crash_log
from studypet.infra.config import AppConfig, SettingsPatch
from studypet.infra.db import StatsRepository, SubjectRepository
from studypet.strings import TAB_SETTINGS, TAB_STATS, TAB_SUBJECTS
from studypet.ui.tab_settings import SettingsTab
from studypet.ui.tab_stats import StatsTab
from studypet.ui.tab_subjects import SubjectsTab
from studypet.win32.actctx import comctl_v6_context
from studypet.win32.api import (
    ICC_BAR_CLASSES,
    ICC_HOTKEY_CLASS,
    ICC_LISTVIEW_CLASSES,
    ICC_STANDARD_CLASSES,
    ICC_TAB_CLASSES,
    IDC_ARROW,
    INITCOMMONCONTROLSEX,
    LPARAM,
    LRESULT,
    SW_HIDE,
    SW_SHOW,
    UINT_PTR,
    WM_CLOSE,
    WM_DESTROY,
    WM_NOTIFY,
    WM_SETFONT,
    WNDCLASSEXW,
    WNDPROC,
    WPARAM,
    WS_CAPTION,
    WS_CHILD,
    WS_MINIMIZEBOX,
    WS_SYSMENU,
    WS_VISIBLE,
    comctl32,
    gdi32,
    kernel32,
    user32,
)
from studypet.win32.monitors import monitor_at, primary


DASHBOARD_CLASS = "StudyPetDashboard"
_dashboard_registered = False

ID_TABCTRL = 1001
TCIF_TEXT = 0x0001
TCM_FIRST = 0x1300
TCM_GETCURSEL = TCM_FIRST + 11
TCM_SETCURSEL = TCM_FIRST + 12
TCM_INSERTITEMW = TCM_FIRST + 62
TCN_SELCHANGE = (-551) & 0xFFFFFFFF

COLOR_BTNFACE = 15


class NMHDR(ctypes.Structure):
    _fields_ = [
        ("hwndFrom", wt.HWND),
        ("idFrom", UINT_PTR),
        ("code", wt.UINT),
    ]


class TCITEMW(ctypes.Structure):
    _fields_ = [
        ("mask", wt.UINT),
        ("dwState", wt.DWORD),
        ("dwStateMask", wt.DWORD),
        ("pszText", wt.LPWSTR),
        ("cchTextMax", ctypes.c_int),
        ("iImage", ctypes.c_int),
        ("lParam", LPARAM),
    ]


class DashboardWindow:
    """과목 관리, 설정, 공부 기록장 3개 탭을 호스팅하고 닫을 때 리소스를 완전히 해제하는 대시보드 창."""

    def __init__(
        self,
        manifest_path: Path | None,
        subject_repo: SubjectRepository,
        stats_repo: StatsRepository,
        get_config: Callable[[], AppConfig],
        on_apply_settings: Callable[[SettingsPatch], None],
        on_subjects_changed: Callable[[], None],
        get_running_subject_id: Callable[[], int | None],
        get_today: Callable[[], date],
        get_live_credit: Callable[[], tuple[int, date, int] | None],
        on_export_csv: Callable[[], None],
    ) -> None:
        self.manifest_path = manifest_path
        self.subject_repo = subject_repo
        self.stats_repo = stats_repo
        self.get_config = get_config
        self.on_apply_settings = on_apply_settings
        self.on_subjects_changed = on_subjects_changed
        self.get_running_subject_id = get_running_subject_id
        self.get_today = get_today
        self.get_live_credit = get_live_credit
        self.on_export_csv = on_export_csv

        self.hwnd: wt.HWND = wt.HWND(0)
        self._tab_hwnd: wt.HWND = wt.HWND(0)
        self._hfont: wt.HFONT = wt.HFONT(0)
        self.tab_subjects: SubjectsTab | None = None
        self.tab_settings: SettingsTab | None = None
        self.tab_stats: StatsTab | None = None
        self._active_tab_idx: int = 0

        self._wndproc_ref = WNDPROC(self._wnd_proc)

    def _ensure_class(self) -> None:
        global _dashboard_registered
        if _dashboard_registered:
            return
        icex = INITCOMMONCONTROLSEX()
        icex.dwSize = ctypes.sizeof(INITCOMMONCONTROLSEX)
        icex.dwICC = (
            ICC_TAB_CLASSES
            | ICC_LISTVIEW_CLASSES
            | ICC_BAR_CLASSES
            | ICC_HOTKEY_CLASS
            | ICC_STANDARD_CLASSES
        )
        comctl32.InitCommonControlsEx(ctypes.byref(icex))

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
        wc.lpszClassName = DASHBOARD_CLASS
        wc.hIconSm = None
        user32.RegisterClassExW(ctypes.byref(wc))
        _dashboard_registered = True

    def open_tab(self, tab_index: int = 0, ref_pos: tuple[int, int] | None = None) -> wt.HWND:
        if self.hwnd:
            self._switch_to_tab(tab_index)
            user32.ShowWindow(self.hwnd, SW_SHOW)
            user32.SetForegroundWindow(self.hwnd)
            return self.hwnd

        mon = monitor_at(ref_pos[0], ref_pos[1]) if ref_pos is not None else primary()
        dpi = mon.dpi
        s = max(1.0, dpi / 96.0)

        def px(v: int) -> int:
            return int(round(v * s))

        win_w = px(640)
        win_h = px(480)
        win_x = mon.work.left + (mon.work.width - win_w) // 2
        win_y = mon.work.top + (mon.work.height - win_h) // 2

        hinst = kernel32.GetModuleHandleW(None)
        self._hfont = gdi32.CreateFontW(-px(13), 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 0, 0, "맑은 고딕")

        with comctl_v6_context(self.manifest_path):
            self._ensure_class()
            self.hwnd = user32.CreateWindowExW(
                0,
                DASHBOARD_CLASS,
                "StudyPet 대시보드",
                WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX,
                win_x,
                win_y,
                win_w,
                win_h,
                None,
                None,
                hinst,
                None,
            )

            self._tab_hwnd = user32.CreateWindowExW(
                0,
                "SysTabControl32",
                "",
                WS_CHILD | WS_VISIBLE,
                px(10),
                px(10),
                px(604),
                px(420),
                self.hwnd,
                wt.HMENU(ID_TABCTRL),
                hinst,
                None,
            )
            user32.SendMessageW(self._tab_hwnd, WM_SETFONT, WPARAM(int(self._hfont or 0)), 1)

            for idx, title in enumerate((TAB_SUBJECTS, TAB_SETTINGS, TAB_STATS)):
                tci = TCITEMW()
                tci.mask = TCIF_TEXT
                buf = ctypes.create_unicode_buffer(title)
                tci.pszText = ctypes.cast(buf, wt.LPWSTR)
                user32.SendMessageW(self._tab_hwnd, TCM_INSERTITEMW, idx, ctypes.addressof(tci))

            panel_x = px(14)
            panel_y = px(42)
            panel_w = px(596)
            panel_h = px(382)

            self.tab_subjects = SubjectsTab(
                parent_hwnd=self.hwnd,
                x=panel_x,
                y=panel_y,
                w=panel_w,
                h=panel_h,
                dpi=dpi,
                hfont=self._hfont,
                repo=self.subject_repo,
                get_running_subject_id=self.get_running_subject_id,
                on_subjects_changed=self.on_subjects_changed,
            )
            self.tab_settings = SettingsTab(
                parent_hwnd=self.hwnd,
                x=panel_x,
                y=panel_y,
                w=panel_w,
                h=panel_h,
                dpi=dpi,
                hfont=self._hfont,
                current_config=self.get_config(),
                on_apply=self.on_apply_settings,
            )
            self.tab_stats = StatsTab(
                parent_hwnd=self.hwnd,
                x=panel_x,
                y=panel_y,
                w=panel_w,
                h=panel_h,
                dpi=dpi,
                hfont=self._hfont,
                stats_repo=self.stats_repo,
                subject_repo=self.subject_repo,
                get_today=self.get_today,
                get_live_credit=self.get_live_credit,
                on_export_csv=self.on_export_csv,
            )

        self._switch_to_tab(tab_index)
        user32.ShowWindow(self.hwnd, SW_SHOW)
        user32.SetForegroundWindow(self.hwnd)
        return self.hwnd

    def _switch_to_tab(self, idx: int) -> None:
        self._active_tab_idx = max(0, min(2, int(idx)))
        if self._tab_hwnd:
            user32.SendMessageW(self._tab_hwnd, TCM_SETCURSEL, self._active_tab_idx, 0)

        if self.tab_subjects is not None:
            user32.ShowWindow(self.tab_subjects.hwnd, SW_SHOW if self._active_tab_idx == 0 else SW_HIDE)
            if self._active_tab_idx == 0:
                self.tab_subjects.refresh_list()

        if self.tab_settings is not None:
            user32.ShowWindow(self.tab_settings.hwnd, SW_SHOW if self._active_tab_idx == 1 else SW_HIDE)
            if self._active_tab_idx == 1:
                self.tab_settings.load_from_config(self.get_config())

        if self.tab_stats is not None:
            user32.ShowWindow(self.tab_stats.hwnd, SW_SHOW if self._active_tab_idx == 2 else SW_HIDE)
            if self._active_tab_idx == 2:
                self.tab_stats.refresh_stats()

    def on_second_tick(self) -> None:
        """진행 중 세션이 있을 때 공부 기록장 탭이 열려 있으면 1초마다 실시간 합산만 갱신한다 (v0.7 M4)."""
        if self.hwnd and self._active_tab_idx == 2 and self.tab_stats is not None:
            self.tab_stats.refresh_live()

    def close_and_destroy(self) -> None:
        if self.tab_stats is not None:
            self.tab_stats.destroy()
            self.tab_stats = None
        self.tab_subjects = None
        self.tab_settings = None
        if self.hwnd:
            hwnd = self.hwnd
            self.hwnd = wt.HWND(0)
            self._tab_hwnd = wt.HWND(0)
            user32.DestroyWindow(hwnd)
        if self._hfont:
            gdi32.DeleteObject(self._hfont)
            self._hfont = wt.HFONT(0)

    def _wnd_proc(self, hwnd: wt.HWND, msg: int, wparam: int, lparam: int) -> int:
        try:
            if msg == WM_NOTIFY and lparam:
                nm = NMHDR.from_address(int(lparam))
                if int(nm.idFrom) == ID_TABCTRL and (nm.code & 0xFFFFFFFF) == TCN_SELCHANGE:
                    sel = int(user32.SendMessageW(self._tab_hwnd, TCM_GETCURSEL, 0, 0))
                    self._switch_to_tab(sel)
                    return 0

            if msg == WM_CLOSE:
                self.close_and_destroy()
                return 0

            if msg == WM_DESTROY:
                return 0

        except Exception:
            write_crash_log()
            return 0

        return int(user32.DefWindowProcW(hwnd, msg, WPARAM(wparam), LPARAM(lparam)))
