"""시스템 트레이 아이콘(Shell_NotifyIconW), 팝업 메뉴, 바탕화면 바로가기 생성 (DEVELOPMENT_PLAN.md 4-13, v0.7 4-6)."""
from __future__ import annotations

import base64
from collections.abc import Callable
import ctypes
from ctypes import wintypes as wt
import logging
from pathlib import Path
import subprocess

from studypet.domain.events import TimerState
from studypet.strings import (
    TRAY_CREATE_SHORTCUT,
    TRAY_GHOST_MODE,
    TRAY_OPEN_DASHBOARD,
    TRAY_PAUSE_STUDY,
    TRAY_QUIT,
    TRAY_RESUME_STUDY,
    TRAY_START_STUDY,
    TRAY_SUMMON,
    TRAY_TOOLTIP,
)
from studypet.ui.popup import show_popup
from studypet.win32.api import (
    IMAGE_ICON,
    LR_LOADFROMFILE,
    MF_CHECKED,
    MF_GRAYED,
    MF_SEPARATOR,
    MF_STRING,
    NIF_ICON,
    NIF_MESSAGE,
    NIF_TIP,
    NIM_ADD,
    NIM_DELETE,
    NOTIFYICONDATAW,
    WM_APP_TRAY,
    shell32,
    user32,
)
from studypet.win32.monitors import primary


logger = logging.getLogger(__name__)

CMD_PRIMARY = 100
CMD_SUMMON = 101
CMD_DASHBOARD = 102
CMD_GHOST = 103
CMD_SHORTCUT = 104
CMD_QUIT = 105


def create_desktop_shortcut(exe_path: Path, working_dir: Path, ico_path: Path) -> bool:
    """PowerShell -EncodedCommand를 통해 바탕화면에 StudyPet.lnk 바로가기를 생성한다 (4-13)."""
    def _esc(p: Path) -> str:
        return str(p.resolve()).replace("'", "''")

    ps_script = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut("
        "[Environment]::GetFolderPath('Desktop')+'\\StudyPet.lnk'); "
        f"$s.TargetPath='{_esc(exe_path)}'; "
        f"$s.WorkingDirectory='{_esc(working_dir)}'; "
        f"$s.IconLocation='{_esc(ico_path)},0'; "
        "$s.Save()"
    )
    encoded = base64.b64encode(ps_script.encode("utf-16le")).decode("ascii")
    try:
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-WindowStyle",
                "Hidden",
                "-EncodedCommand",
                encoded,
            ],
            capture_output=True,
            timeout=15,
            check=False,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
        return completed.returncode == 0
    except Exception:
        logger.exception("Failed to create desktop shortcut")
        return False


class TrayIcon:
    """작업 표시줄 알림 영역 아이콘 및 우클릭 컨텍스트 메뉴 관리."""

    def __init__(self, hwnd: wt.HWND, ico_path: Path) -> None:
        self.hwnd = hwnd
        self.ico_path = ico_path
        self.hicon: wt.HICON = wt.HICON(0)
        self._added: bool = False
        self._load_icon()

    def _load_icon(self) -> None:
        dpi = primary().dpi
        sz = max(16, int(16 * dpi / 96 + 0.5))
        if self.ico_path.exists():
            h = user32.LoadImageW(
                None,
                str(self.ico_path),
                IMAGE_ICON,
                sz,
                sz,
                LR_LOADFROMFILE,
            )
            if h:
                self.hicon = wt.HICON(h)

    def _make_nid(self) -> NOTIFYICONDATAW:
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_APP_TRAY
        nid.hIcon = self.hicon
        nid.szTip = TRAY_TOOLTIP
        return nid

    def add(self) -> bool:
        if not self.hwnd:
            return False
        nid = self._make_nid()
        ok = bool(shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)))
        self._added = ok
        return ok

    def re_add(self) -> bool:
        """탐색기 재시작(TaskbarCreated) 시 트레이 아이콘을 다시 등록한다."""
        return self.add()

    def remove(self) -> None:
        if self._added and self.hwnd:
            nid = self._make_nid()
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
            self._added = False
        if self.hicon:
            user32.DestroyIcon(self.hicon)
            self.hicon = wt.HICON(0)

    def show_popup_menu(
        self,
        engine_state: TimerState,
        ghost_active: bool,
        on_primary: Callable[[], None],
        on_summon: Callable[[], None],
        on_dashboard: Callable[[], None],
        on_toggle_ghost: Callable[[], None],
        on_shortcut: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        if not self.hwnd:
            return

        if engine_state is TimerState.RUNNING:
            primary_lbl = TRAY_PAUSE_STUDY
            primary_flags = MF_STRING
        elif engine_state is TimerState.PAUSED:
            primary_lbl = TRAY_RESUME_STUDY
            primary_flags = MF_STRING
        elif engine_state is TimerState.STOPPED:
            primary_lbl = TRAY_START_STUDY
            primary_flags = MF_STRING
        else:
            primary_lbl = TRAY_PAUSE_STUDY
            primary_flags = MF_STRING | MF_GRAYED

        ghost_flags = MF_STRING | (MF_CHECKED if ghost_active else 0)
        ghost_label = TRAY_GHOST_MODE

        items: list[tuple[int, str, int]] = [
            (CMD_PRIMARY, primary_lbl, primary_flags),
            (0, "", MF_SEPARATOR),
            (CMD_SUMMON, TRAY_SUMMON, MF_STRING),
            (CMD_DASHBOARD, TRAY_OPEN_DASHBOARD, MF_STRING),
            (CMD_GHOST, ghost_label, ghost_flags),
            (CMD_SHORTCUT, TRAY_CREATE_SHORTCUT, MF_STRING),
            (0, "", MF_SEPARATOR),
            (CMD_QUIT, TRAY_QUIT, MF_STRING),
        ]

        cmd = show_popup(self.hwnd, items)
        if cmd == CMD_PRIMARY and not (primary_flags & MF_GRAYED):
            on_primary()
        elif cmd == CMD_SUMMON:
            on_summon()
        elif cmd == CMD_DASHBOARD:
            on_dashboard()
        elif cmd == CMD_GHOST:
            on_toggle_ghost()
        elif cmd == CMD_SHORTCUT:
            on_shortcut()
        elif cmd == CMD_QUIT:
            on_quit()
