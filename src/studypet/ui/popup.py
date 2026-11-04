"""Windows 기본 팝업 메뉴(TrackPopupMenu) 공통 헬퍼 및 명령 ID 상수 (REVISION_PLAN_v0.7 4-6, 8장 D1)."""
from __future__ import annotations

import ctypes
from ctypes import wintypes as wt

from studypet.win32.api import (
    MF_SEPARATOR,
    POINT,
    TPM_NONOTIFY,
    TPM_RETURNCMD,
    TPM_RIGHTBUTTON,
    WM_NULL,
    user32,
)


# 8장 D1 명령 ID 범위
CMD_SUBJECT_BASE = 1000
CMD_MODE_POMODORO = 2001
CMD_MODE_STOPWATCH = 2002

CMD_MORE_SUBJECTS = 3001
CMD_MORE_BUBBLE = 3002
CMD_MORE_GHOST = 3003
CMD_MORE_SUMMON = 3004
CMD_MORE_QUIT = 3005
CMD_MANAGE_SUBJECTS = 3010

# 호환 별칭
CMD_MORE_BUBBLE_TOGGLE = CMD_MORE_BUBBLE
CMD_MORE_GHOST_MODE = CMD_MORE_GHOST
CMD_MORE_SUMMON_CENTER = CMD_MORE_SUMMON


def cursor_pos() -> tuple[int, int]:
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return (int(pt.x), int(pt.y))


def show_popup(
    hwnd: wt.HWND,
    items: list[tuple[int, str, int]],
    anchor_px: tuple[int, int] | None = None,
) -> int:
    """items: (명령 ID, 라벨, MF_* 플래그). 0 = 취소. 반환 후 호출자가 명령 실행."""
    if not hwnd or not items:
        return 0
    hmenu = user32.CreatePopupMenu()
    if not hmenu:
        return 0
    try:
        for cid, label, flags in items:
            user32.AppendMenuW(hmenu, flags, cid, label if not (flags & MF_SEPARATOR) else None)
        x, y = anchor_px if anchor_px is not None else cursor_pos()
        user32.SetForegroundWindow(hwnd)  # 없으면 바깥 클릭 시 메뉴가 닫히지 않음
        cmd = int(
            user32.TrackPopupMenu(
                hmenu,
                TPM_RETURNCMD | TPM_RIGHTBUTTON | TPM_NONOTIFY,
                int(x),
                int(y),
                0,
                hwnd,
                None,
            )
        )
        user32.PostMessageW(hwnd, WM_NULL, 0, 0)  # 알려진 메뉴 잔류 문제 회피
        return cmd
    finally:
        user32.DestroyMenu(hmenu)
