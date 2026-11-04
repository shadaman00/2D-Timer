"""대시보드 탭 1: 과목 관리 (DEVELOPMENT_PLAN.md 4-16)."""
from __future__ import annotations

from collections.abc import Callable
import ctypes
from ctypes import wintypes as wt

from studypet.crashlog import write_crash_log
from studypet.graphics.text import rgb_to_colorref
from studypet.infra.db import SubjectRepository, SubjectRow
from studypet.strings import (
    MSG_SUBJECT_ARCHIVE_ACTIVE,
    MSG_SUBJECT_ARCHIVE_LAST,
    MSG_SUBJECT_GOAL_INVALID,
    MSG_SUBJECT_NAME_INVALID,
)
from studypet.ui.chart import parse_hex_colorref
from studypet.ui.modals import show_info_message
from studypet.win32.api import (
    CHOOSECOLORW,
    IDC_ARROW,
    LPARAM,
    LRESULT,
    WM_COMMAND,
    WM_DESTROY,
    WM_SETFONT,
    WNDCLASSEXW,
    WNDPROC,
    WPARAM,
    WS_BORDER,
    WS_CHILD,
    WS_EX_CONTROLPARENT,
    WS_TABSTOP,
    WS_VISIBLE,
    comdlg32,
    kernel32,
    user32,
)


TAB_SUBJ_CLASS = "StudyPetTabSubjects"
_tab_subj_registered = False

ID_LISTBOX = 301
ID_EDIT_NAME = 302
ID_EDIT_GOAL = 303
ID_BTN_COLOR = 304
ID_BTN_ADD = 305
ID_BTN_UPDATE = 306
ID_BTN_ARCHIVE = 307
ID_CHK_ARCHIVED = 308

LBS_NOTIFY = 0x0001
WS_VSCROLL = 0x00200000
LBN_SELCHANGE = 1
LB_ADDSTRING = 0x0180
LB_RESETCONTENT = 0x0184
LB_GETCURSEL = 0x0188
LB_SETCURSEL = 0x0186

ES_AUTOHSCROLL = 0x0080
ES_NUMBER = 0x2000
EM_LIMITTEXT = 0x00C5
BS_AUTOCHECKBOX = 0x0003
BM_GETCHECK = 0x00F0
CC_RGBINIT = 0x00000001
CC_FULLOPEN = 0x00000002
COLOR_BTNFACE = 15

PRESET_COLORS_HEX = [
    "#5B8DEF",
    "#4CC37D",
    "#F0AF4B",
    "#F07391",
    "#AF7DEB",
    "#4AC2C9",
    "#E56B55",
    "#8E99B0",
]


def colorref_to_hex(cr: int) -> str:
    r = cr & 0xFF
    g = (cr >> 8) & 0xFF
    b = (cr >> 16) & 0xFF
    return f"#{r:02X}{g:02X}{b:02X}"


class SubjectsTab:
    """과목 목록 조회, 추가, 수정, 보관/복원, 색상 선택(ChooseColorW) 탭 패널."""

    def __init__(
        self,
        parent_hwnd: wt.HWND,
        x: int,
        y: int,
        w: int,
        h: int,
        dpi: int,
        hfont: wt.HFONT,
        repo: SubjectRepository,
        get_running_subject_id: Callable[[], int | None],
        on_subjects_changed: Callable[[], None],
    ) -> None:
        self.repo = repo
        self.get_running_subject_id = get_running_subject_id
        self.on_subjects_changed = on_subjects_changed
        self.s = max(1.0, dpi / 96.0)
        self.hfont = hfont
        self._subjects: list[SubjectRow] = []
        self._selected_color: str = "#5B8DEF"
        self._cust_colors = (wt.DWORD * 16)()
        for i, hx in enumerate(PRESET_COLORS_HEX):
            self._cust_colors[i] = parse_hex_colorref(hx)
        for i in range(len(PRESET_COLORS_HEX), 16):
            self._cust_colors[i] = rgb_to_colorref(255, 255, 255)

        self._wndproc_ref = WNDPROC(self._wnd_proc)
        self._ensure_class()

        hinst = kernel32.GetModuleHandleW(None)
        self.hwnd: wt.HWND = user32.CreateWindowExW(
            WS_EX_CONTROLPARENT,
            TAB_SUBJ_CLASS,
            "",
            WS_CHILD | WS_VISIBLE,
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

        self._chk_archived = self._create_ctrl(
            "BUTTON",
            "보관된 과목 표시",
            WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_AUTOCHECKBOX,
            px(16),
            px(10),
            px(180),
            px(24),
            ID_CHK_ARCHIVED,
        )

        self._listbox = self._create_ctrl(
            "LISTBOX",
            "",
            WS_CHILD | WS_VISIBLE | WS_BORDER | WS_VSCROLL | WS_TABSTOP | LBS_NOTIFY,
            px(16),
            px(40),
            px(568),
            px(210),
            ID_LISTBOX,
        )

        self._create_ctrl("STATIC", "과목명 (1~40자):", WS_CHILD | WS_VISIBLE, px(16), px(264), px(120), px(22), 0)
        self._edit_name = self._create_ctrl(
            "EDIT",
            "",
            WS_CHILD | WS_VISIBLE | WS_BORDER | WS_TABSTOP | ES_AUTOHSCROLL,
            px(138),
            px(260),
            px(190),
            px(26),
            ID_EDIT_NAME,
        )
        user32.SendMessageW(self._edit_name, EM_LIMITTEXT, 40, 0)

        self._create_ctrl("STATIC", "일일 목표(분):", WS_CHILD | WS_VISIBLE, px(344), px(264), px(100), px(22), 0)
        self._edit_goal = self._create_ctrl(
            "EDIT",
            "60",
            WS_CHILD | WS_VISIBLE | WS_BORDER | WS_TABSTOP | ES_NUMBER,
            px(446),
            px(260),
            px(70),
            px(26),
            ID_EDIT_GOAL,
        )

        self._btn_color = self._create_ctrl(
            "BUTTON",
            f"색상: {self._selected_color}",
            WS_CHILD | WS_VISIBLE | WS_TABSTOP,
            px(16),
            px(300),
            px(140),
            px(30),
            ID_BTN_COLOR,
        )
        self._btn_add = self._create_ctrl(
            "BUTTON",
            "추가",
            WS_CHILD | WS_VISIBLE | WS_TABSTOP,
            px(172),
            px(300),
            px(96),
            px(30),
            ID_BTN_ADD,
        )
        self._btn_update = self._create_ctrl(
            "BUTTON",
            "선택 과목 수정",
            WS_CHILD | WS_VISIBLE | WS_TABSTOP,
            px(278),
            px(300),
            px(120),
            px(30),
            ID_BTN_UPDATE,
        )
        self._btn_archive = self._create_ctrl(
            "BUTTON",
            "보관 / 복원",
            WS_CHILD | WS_VISIBLE | WS_TABSTOP,
            px(408),
            px(300),
            px(110),
            px(30),
            ID_BTN_ARCHIVE,
        )

        self.refresh_list()

    def _ensure_class(self) -> None:
        global _tab_subj_registered
        if _tab_subj_registered:
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
        wc.lpszClassName = TAB_SUBJ_CLASS
        wc.hIconSm = None
        user32.RegisterClassExW(ctypes.byref(wc))
        _tab_subj_registered = True

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

    @staticmethod
    def _get_text(hwnd: wt.HWND) -> str:
        length = int(user32.GetWindowTextLengthW(hwnd))
        if length <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 2)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value

    def refresh_list(self) -> None:
        show_arch = bool(user32.SendMessageW(self._chk_archived, BM_GETCHECK, 0, 0))
        self._subjects = self.repo.list(include_archived=show_arch)
        user32.SendMessageW(self._listbox, LB_RESETCONTENT, 0, 0)
        for s in self._subjects:
            status = "[보관됨]" if s.is_archived else "[활성]"
            line = f"{status}  {s.name}   |   일일 목표: {s.daily_goal_minutes}분   |   색상: {s.color_code}"
            buf = ctypes.create_unicode_buffer(line)
            user32.SendMessageW(self._listbox, LB_ADDSTRING, 0, ctypes.addressof(buf))
        if self._subjects:
            user32.SendMessageW(self._listbox, LB_SETCURSEL, 0, 0)
            self._on_selection_changed()

    def _selected_subject(self) -> SubjectRow | None:
        idx = int(user32.SendMessageW(self._listbox, LB_GETCURSEL, 0, 0))
        if 0 <= idx < len(self._subjects):
            return self._subjects[idx]
        return None

    def _on_selection_changed(self) -> None:
        subj = self._selected_subject()
        if subj is None:
            return
        user32.SetWindowTextW(self._edit_name, subj.name)
        user32.SetWindowTextW(self._edit_goal, str(subj.daily_goal_minutes))
        self._selected_color = subj.color_code
        user32.SetWindowTextW(self._btn_color, f"색상: {self._selected_color}")
        user32.SetWindowTextW(self._btn_archive, "복원" if subj.is_archived else "보관")

    def _pick_color(self) -> None:
        cc = CHOOSECOLORW()
        cc.lStructSize = ctypes.sizeof(CHOOSECOLORW)
        cc.hwndOwner = self.hwnd
        cc.rgbResult = parse_hex_colorref(self._selected_color)
        cc.lpCustColors = ctypes.cast(self._cust_colors, ctypes.POINTER(wt.DWORD))
        cc.Flags = CC_RGBINIT | CC_FULLOPEN
        if comdlg32.ChooseColorW(ctypes.byref(cc)):
            self._selected_color = colorref_to_hex(int(cc.rgbResult))
            user32.SetWindowTextW(self._btn_color, f"색상: {self._selected_color}")

    def _validate_inputs(self) -> tuple[str, int] | None:
        name = self._get_text(self._edit_name).strip()
        if not (1 <= len(name) <= 40):
            show_info_message(MSG_SUBJECT_NAME_INVALID, warning=True)
            return None
        goal_str = self._get_text(self._edit_goal).strip()
        if not goal_str.isdigit():
            show_info_message(MSG_SUBJECT_GOAL_INVALID, warning=True)
            return None
        goal = int(goal_str)
        if not (1 <= goal <= 1440):
            show_info_message(MSG_SUBJECT_GOAL_INVALID, warning=True)
            return None
        return (name, goal)

    def _handle_add(self) -> None:
        validated = self._validate_inputs()
        if validated is None:
            return
        name, goal = validated
        try:
            self.repo.create(name, self._selected_color, goal)
            self.refresh_list()
            self.on_subjects_changed()
        except Exception:
            show_info_message(MSG_SUBJECT_NAME_INVALID, warning=True)

    def _handle_update(self) -> None:
        subj = self._selected_subject()
        if subj is None:
            return
        validated = self._validate_inputs()
        if validated is None:
            return
        name, goal = validated
        try:
            self.repo.update(subj.id, name, self._selected_color, goal)
            self.refresh_list()
            self.on_subjects_changed()
        except Exception:
            show_info_message(MSG_SUBJECT_NAME_INVALID, warning=True)

    def _handle_archive_toggle(self) -> None:
        subj = self._selected_subject()
        if subj is None:
            return
        if not subj.is_archived:
            running_id = self.get_running_subject_id()
            if running_id is not None and running_id == subj.id:
                show_info_message(MSG_SUBJECT_ARCHIVE_ACTIVE, warning=True)
                return
            active_list = self.repo.list(include_archived=False)
            if len(active_list) <= 1:
                show_info_message(MSG_SUBJECT_ARCHIVE_LAST, warning=True)
                return
            self.repo.set_archived(subj.id, True)
        else:
            self.repo.set_archived(subj.id, False)

        self.refresh_list()
        self.on_subjects_changed()

    def _wnd_proc(self, hwnd: wt.HWND, msg: int, wparam: int, lparam: int) -> int:
        try:
            if msg == WM_COMMAND:
                cid = int(wparam) & 0xFFFF
                code = (int(wparam) >> 16) & 0xFFFF
                if cid == ID_LISTBOX and code == LBN_SELCHANGE:
                    self._on_selection_changed()
                elif cid == ID_CHK_ARCHIVED:
                    self.refresh_list()
                elif cid == ID_BTN_COLOR:
                    self._pick_color()
                elif cid == ID_BTN_ADD:
                    self._handle_add()
                elif cid == ID_BTN_UPDATE:
                    self._handle_update()
                elif cid == ID_BTN_ARCHIVE:
                    self._handle_archive_toggle()
                return 0
            if msg == WM_DESTROY:
                return 0
        except Exception:
            write_crash_log()
            return 0
        return int(user32.DefWindowProcW(hwnd, msg, WPARAM(wparam), LPARAM(lparam)))
