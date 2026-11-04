"""비중첩(단일 메시지 루프) Win32 모달 대화상자 및 우선순위 대기열(ModalQueue) (DEVELOPMENT_PLAN.md 4-15, v0.7 4-2)."""
from __future__ import annotations

from collections.abc import Callable
import ctypes
from ctypes import wintypes as wt
from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Literal

from studypet.crashlog import write_crash_log
from studypet.strings import (
    APP_TITLE,
    MODAL_BTN_AFK_EXCLUDE,
    MODAL_BTN_AFK_INCLUDE,
    MODAL_BTN_CANCEL,
    MODAL_BTN_QUIT_KEEP,
    MODAL_BTN_QUIT_SAVE,
    MODAL_BTN_RECOVER_DISCARD,
    MODAL_BTN_RECOVER_LATER,
    MODAL_BTN_RECOVER_RESUME,
    MODAL_BTN_RECOVER_SAVE,
    MODAL_BTN_SAVE_MEMO,
    MODAL_BTN_SAVE_NO_MEMO,
    MODAL_TITLE_AFK,
    MODAL_TITLE_MEMO,
    MODAL_TITLE_QUIT,
    MODAL_TITLE_RECOVERY,
    MSG_RECOVER_DISCARD_CONFIRM,
)
from studypet.win32.actctx import comctl_v6_context
from studypet.win32.api import (
    IDC_ARROW,
    IDCANCEL,
    IDOK,
    IDYES,
    LPARAM,
    LRESULT,
    MB_ICONINFORMATION,
    MB_ICONWARNING,
    MB_OK,
    MB_TOPMOST,
    MB_YESNO,
    SW_SHOW,
    SW_SHOWNOACTIVATE,
    WM_CLOSE,
    WM_COMMAND,
    WM_DESTROY,
    WM_SETFONT,
    WNDCLASSEXW,
    WNDPROC,
    WPARAM,
    WS_BORDER,
    WS_CAPTION,
    WS_CHILD,
    WS_EX_DLGMODALFRAME,
    WS_EX_TOPMOST,
    WS_POPUP,
    WS_SYSMENU,
    WS_TABSTOP,
    WS_VISIBLE,
    gdi32,
    kernel32,
    user32,
)
from studypet.win32.monitors import MonitorInfo, monitor_at, primary


logger = logging.getLogger(__name__)

MODAL_CLASS_NAME = "StudyPetModal"
_modal_class_registered = False

ModalKind = Literal["recovery", "memo", "afk", "quit"]

ID_SAVE = 3
ID_KEEP = 3
ID_DISCARD = 4
ID_EDIT_MEMO = 201

ES_AUTOHSCROLL = 0x0080
EM_LIMITTEXT = 0x00C5
BS_DEFPUSHBUTTON = 0x0001
BS_PUSHBUTTON = 0x0000
COLOR_BTNFACE = 15


def show_info_message(message: str, title: str = APP_TITLE, warning: bool = False) -> None:
    flags = MB_OK | MB_TOPMOST | (MB_ICONWARNING if warning else MB_ICONINFORMATION)
    user32.MessageBoxW(None, message, title, flags)


@dataclass
class ModalRequest:
    kind: ModalKind
    show: Callable[[], wt.HWND]
    default: Callable[[], None]


class ModalQueue:
    """창 생성과 분리된 순수 모달 우선순위 대기열 (v0.7 4-2, tests/test_modal_queue.py)."""

    PRIORITY: dict[ModalKind, int] = {
        "recovery": 0,
        "memo": 1,
        "afk": 2,
        "quit": 3,
    }

    def __init__(self) -> None:
        self.active: ModalRequest | None = None
        self._pending: list[tuple[int, int, ModalRequest]] = []
        self._seq: int = 0
        self._releasing: bool = False   # 활성 모달의 결과 콜백 실행 중 (새 요청은 대기열로)
        self.closing: bool = False      # 종료 중: 새 요청은 창을 만들지 않고 기본값으로 즉시 처리

    def push(self, req: ModalRequest) -> None:
        if self.closing:
            req.default()
            return

        if self.active is None and not self._releasing:
            self._show(req)
            return

        # 이미 같은 kind가 대기열에 있으면 새 요청으로 대체
        self._pending = [(prio, seq, r) for (prio, seq, r) in self._pending if r.kind != req.kind]
        self._seq += 1
        prio = self.PRIORITY.get(req.kind, 99)
        self._pending.append((prio, self._seq, req))
        self._pending.sort(key=lambda item: (item[0], item[1]))

    def _show(self, req: ModalRequest) -> None:
        """창 생성이 실패해도 대기열이 막히지 않도록 기본값으로 처리하고 다음 요청으로 넘어간다."""
        self.active = req
        try:
            req.show()
        except Exception:
            logger.exception("Failed to show modal %s; applying default", req.kind)
            self.active = None
            req.default()
            self._show_next()

    def _show_next(self) -> None:
        if self.active is None and not self._releasing and not self.closing and self._pending:
            _, _, nxt = self._pending.pop(0)
            self._show(nxt)

    def begin_release(self) -> None:
        """활성 모달의 결과 콜백을 실행하기 직전에 호출한다. 이후 flush_defaults가 이 모달을 다시 처리하지 않는다."""
        self.active = None
        self._releasing = True

    def end_release(self) -> None:
        """결과 콜백 실행 후 호출한다. 콜백 중 들어온 요청까지 포함해 우선순위가 가장 높은 모달을 띄운다."""
        self._releasing = False
        self._show_next()

    def on_closed(self) -> None:
        self.begin_release()
        self.end_release()

    def flush_defaults(self) -> None:
        """강제 닫기(종료 등) 시 활성 모달과 대기 중인 모든 모달의 안전한 기본값 콜백을 호출하고 비운다.

        기본값 콜백이 새 모달을 요청하면(예: 복구 '나중에 결정' → 다음 복구 행) 창을 만들지 않고 그 기본값도 즉시 처리한다.
        """
        self.closing = True
        if self.active is not None:
            cur = self.active
            self.active = None
            cur.default()

        while self._pending:
            _, _, req = self._pending.pop(0)
            req.default()

    @property
    def pending_kinds(self) -> list[ModalKind]:
        return [r.kind for _, _, r in self._pending]

    @property
    def pending_count(self) -> int:
        return len(self._pending)


class ModalManager:
    """중첩 메시지 루프 없이 ModalQueue를 통해 단일 활성 모달 창을 관리한다."""

    def __init__(self, manifest_path: Path | None = None) -> None:
        self.manifest_path = manifest_path
        self.queue = ModalQueue()
        self.active_hwnd: wt.HWND = wt.HWND(0)
        self._edit_hwnd: wt.HWND = wt.HWND(0)
        self._hfont: wt.HFONT = wt.HFONT(0)
        self._result_callback: Callable[[int, str], None] | None = None
        self._discard_confirm_msg: str | None = None
        self.on_modal_state_changed: Callable[[bool], None] | None = None
        self._wndproc_ref = WNDPROC(self._wnd_proc)

    def _ensure_class(self) -> None:
        global _modal_class_registered
        if _modal_class_registered:
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
        wc.lpszClassName = MODAL_CLASS_NAME
        wc.hIconSm = None
        user32.RegisterClassExW(ctypes.byref(wc))
        _modal_class_registered = True

    def _get_monitor(self, ref_pos: tuple[int, int] | None) -> MonitorInfo:
        if ref_pos is not None:
            return monitor_at(ref_pos[0], ref_pos[1])
        return primary()

    def _read_edit_text(self) -> str:
        if not self._edit_hwnd:
            return ""
        length = int(user32.GetWindowTextLengthW(self._edit_hwnd))
        if length <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 2)
        user32.GetWindowTextW(self._edit_hwnd, buf, length + 1)
        return buf.value.strip()[:200]

    def _destroy_window_only(self) -> None:
        if self.active_hwnd:
            hwnd = self.active_hwnd
            self.active_hwnd = wt.HWND(0)
            self._edit_hwnd = wt.HWND(0)
            user32.DestroyWindow(hwnd)
        if self._hfont:
            gdi32.DeleteObject(self._hfont)
            self._hfont = wt.HFONT(0)
        self._discard_confirm_msg = None

    def flush_defaults_and_close(self) -> None:
        """종료 시 호출: 창을 파괴하고 큐의 모든 모달에 대해 기본값 콜백을 실행한다."""
        self._result_callback = None
        self._destroy_window_only()
        self.queue.flush_defaults()
        if self.on_modal_state_changed is not None:
            self.on_modal_state_changed(False)

    def bring_active_to_front(self) -> None:
        if self.active_hwnd:
            user32.ShowWindow(self.active_hwnd, SW_SHOW)
            user32.SetForegroundWindow(self.active_hwnd)

    def _finish(self, btn_id: int) -> None:
        # H2: 복구 창에서 [폐기] 클릭 시 재확인 대화상자 표시
        if btn_id == ID_DISCARD and self._discard_confirm_msg:
            ans = int(
                user32.MessageBoxW(
                    self.active_hwnd,
                    self._discard_confirm_msg,
                    MODAL_TITLE_RECOVERY,
                    MB_YESNO | MB_ICONWARNING | MB_TOPMOST,
                )
            )
            if ans != IDYES:
                return

        text = self._read_edit_text()
        cb = self._result_callback
        self._result_callback = None
        self._destroy_window_only()
        # 콜백 전에 활성 표시를 해제: 콜백 안에서 종료(flush_defaults)가 일어나도 이 모달의 기본값이 다시 불리지 않는다
        self.queue.begin_release()
        try:
            if cb is not None:
                cb(btn_id, text)
        finally:
            self.queue.end_release()
        if self.on_modal_state_changed is not None:
            self.on_modal_state_changed(bool(self.active_hwnd))

    def _create_base_modal(
        self,
        title: str,
        prompt: str,
        buttons: list[tuple[int, str, bool]],  # [(id, label, enabled)]
        has_edit: bool,
        activate: bool,
        ref_pos: tuple[int, int] | None,
        callback: Callable[[int, str], None],
        discard_confirm_msg: str | None = None,
    ) -> wt.HWND:
        self._ensure_class()
        self._result_callback = callback
        self._discard_confirm_msg = discard_confirm_msg

        mon = self._get_monitor(ref_pos)
        s = max(1.0, mon.dpi / 96.0)

        def px(val: int) -> int:
            return int(round(val * s))

        num_btns = len(buttons)
        win_w = px(480 if num_btns >= 4 else 430)
        win_h = px(200 if has_edit else 170)
        win_x = mon.work.left + (mon.work.width - win_w) // 2
        win_y = mon.work.top + (mon.work.height - win_h) // 2

        hinst = kernel32.GetModuleHandleW(None)
        font_h = -px(13)
        self._hfont = gdi32.CreateFontW(font_h, 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 0, 0, "맑은 고딕")

        with comctl_v6_context(self.manifest_path):
            hwnd = user32.CreateWindowExW(
                WS_EX_TOPMOST | WS_EX_DLGMODALFRAME,
                MODAL_CLASS_NAME,
                title,
                WS_POPUP | WS_CAPTION | WS_SYSMENU,
                win_x,
                win_y,
                win_w,
                win_h,
                None,
                None,
                hinst,
                None,
            )
            self.active_hwnd = hwnd

            lbl_hwnd = user32.CreateWindowExW(
                0,
                "STATIC",
                prompt,
                WS_CHILD | WS_VISIBLE,
                px(18),
                px(16),
                win_w - px(36),
                px(50),
                hwnd,
                None,
                hinst,
                None,
            )
            user32.SendMessageW(lbl_hwnd, WM_SETFONT, WPARAM(int(self._hfont or 0)), 1)

            if has_edit:
                edit_hwnd = user32.CreateWindowExW(
                    0,
                    "EDIT",
                    "",
                    WS_CHILD | WS_VISIBLE | WS_BORDER | WS_TABSTOP | ES_AUTOHSCROLL,
                    px(18),
                    px(68),
                    win_w - px(36),
                    px(26),
                    hwnd,
                    wt.HMENU(ID_EDIT_MEMO),
                    hinst,
                    None,
                )
                user32.SendMessageW(edit_hwnd, WM_SETFONT, WPARAM(int(self._hfont or 0)), 1)
                user32.SendMessageW(edit_hwnd, EM_LIMITTEXT, 200, 0)
                self._edit_hwnd = edit_hwnd

            btn_y = px(112 if has_edit else 86)
            btn_w = px(102 if num_btns >= 4 else (122 if num_btns == 3 else 135))
            btn_h = px(30)
            gap = px(8)
            total_btns_w = num_btns * btn_w + max(0, num_btns - 1) * gap
            start_x = (win_w - total_btns_w) // 2

            for idx, (bid, blabel, benabled) in enumerate(buttons):
                bx = start_x + idx * (btn_w + gap)
                bstyle = WS_CHILD | WS_VISIBLE | WS_TABSTOP | (BS_DEFPUSHBUTTON if bid == IDOK else BS_PUSHBUTTON)
                b_hwnd = user32.CreateWindowExW(
                    0,
                    "BUTTON",
                    blabel,
                    bstyle,
                    bx,
                    btn_y,
                    btn_w,
                    btn_h,
                    hwnd,
                    wt.HMENU(bid),
                    hinst,
                    None,
                )
                user32.SendMessageW(b_hwnd, WM_SETFONT, WPARAM(int(self._hfont or 0)), 1)
                if not benabled:
                    user32.EnableWindow(b_hwnd, False)

        if self.on_modal_state_changed is not None:
            self.on_modal_state_changed(True)

        if activate:
            user32.ShowWindow(hwnd, SW_SHOW)
            user32.SetForegroundWindow(hwnd)
            if self._edit_hwnd:
                user32.SetFocus(self._edit_hwnd)
        else:
            user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)

        return hwnd

    def show_memo_modal(
        self,
        prompt: str,
        ref_pos: tuple[int, int] | None,
        on_done: Callable[[str], None],
    ) -> None:
        def _cb(btn_id: int, text: str) -> None:
            memo = text if btn_id == IDOK else ""
            on_done(memo)

        def _show() -> wt.HWND:
            return self._create_base_modal(
                title=MODAL_TITLE_MEMO,
                prompt=prompt,
                buttons=[
                    (IDOK, MODAL_BTN_SAVE_MEMO, True),
                    (IDCANCEL, MODAL_BTN_SAVE_NO_MEMO, True),
                ],
                has_edit=True,
                activate=True,
                ref_pos=ref_pos,
                callback=_cb,
            )

        self.queue.push(ModalRequest(kind="memo", show=_show, default=lambda: on_done("")))

    def show_afk_modal(
        self,
        prompt: str,
        can_include: bool,
        ref_pos: tuple[int, int] | None,
        on_decision: Callable[[bool], None],
    ) -> None:
        def _cb(btn_id: int, _text: str) -> None:
            include = (btn_id == IDOK) and can_include
            on_decision(include)

        def _show() -> wt.HWND:
            return self._create_base_modal(
                title=MODAL_TITLE_AFK,
                prompt=prompt,
                buttons=[
                    (IDCANCEL, MODAL_BTN_AFK_EXCLUDE, True),
                    (IDOK, MODAL_BTN_AFK_INCLUDE, can_include),
                ],
                has_edit=False,
                activate=False,  # 4-15: AFK 복귀 모달은 포커스를 뺏지 않고 SW_SHOWNOACTIVATE로 표시
                ref_pos=ref_pos,
                callback=_cb,
            )

        self.queue.push(ModalRequest(kind="afk", show=_show, default=lambda: on_decision(False)))

    def show_recovery_modal(
        self,
        prompt: str,
        subject_name: str,
        duration_s: int,
        allow_resume: bool,
        ref_pos: tuple[int, int] | None,
        on_choice: Callable[[str], None],
    ) -> None:
        confirm_msg = MSG_RECOVER_DISCARD_CONFIRM.format(
            subject=subject_name,
            minutes=max(0, duration_s // 60),
        )

        def _cb(btn_id: int, _text: str) -> None:
            if btn_id == IDOK and allow_resume:
                on_choice("resume")
            elif btn_id == ID_SAVE:
                on_choice("save")
            elif btn_id == ID_DISCARD:
                on_choice("discard")
            else:
                on_choice("later")

        def _show() -> wt.HWND:
            return self._create_base_modal(
                title=MODAL_TITLE_RECOVERY,
                prompt=prompt,
                buttons=[
                    (IDOK, MODAL_BTN_RECOVER_RESUME, allow_resume),
                    (ID_SAVE, MODAL_BTN_RECOVER_SAVE, True),
                    (ID_DISCARD, MODAL_BTN_RECOVER_DISCARD, True),
                    (IDCANCEL, MODAL_BTN_RECOVER_LATER, True),
                ],
                has_edit=False,
                activate=True,
                ref_pos=ref_pos,
                callback=_cb,
                discard_confirm_msg=confirm_msg,
            )

        self.queue.push(ModalRequest(kind="recovery", show=_show, default=lambda: on_choice("later")))

    def show_quit_confirm_modal(
        self,
        prompt: str,
        ref_pos: tuple[int, int] | None,
        on_choice: Callable[[str], None],
    ) -> None:
        def _cb(btn_id: int, _text: str) -> None:
            if btn_id == IDOK:
                on_choice("save_quit")
            elif btn_id == ID_KEEP:
                on_choice("keep_quit")
            else:
                on_choice("cancel")

        def _show() -> wt.HWND:
            return self._create_base_modal(
                title=MODAL_TITLE_QUIT,
                prompt=prompt,
                buttons=[
                    (IDOK, MODAL_BTN_QUIT_SAVE, True),
                    (ID_KEEP, MODAL_BTN_QUIT_KEEP, True),
                    (IDCANCEL, MODAL_BTN_CANCEL, True),
                ],
                has_edit=False,
                activate=True,
                ref_pos=ref_pos,
                callback=_cb,
            )

        self.queue.push(ModalRequest(kind="quit", show=_show, default=lambda: on_choice("cancel")))

    def _wnd_proc(self, hwnd: wt.HWND, msg: int, wparam: int, lparam: int) -> int:
        try:
            if msg == WM_COMMAND:
                cmd_id = int(wparam) & 0xFFFF
                notify_code = (int(wparam) >> 16) & 0xFFFF
                if notify_code == 0 and cmd_id in (IDOK, IDCANCEL, ID_SAVE, ID_DISCARD):
                    self._finish(cmd_id)
                    return 0

            if msg == WM_CLOSE:
                self._finish(IDCANCEL)
                return 0

            if msg == WM_DESTROY:
                return 0

        except Exception:
            write_crash_log()
            return 0

        return int(user32.DefWindowProcW(hwnd, msg, WPARAM(wparam), LPARAM(lparam)))
