"""comctl32 v6 활성화 컨텍스트 (DEVELOPMENT_PLAN.md 4-16)."""
from __future__ import annotations

import ctypes
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from studypet.win32.api import (
    ACTCTXW,
    ICC_BAR_CLASSES,
    ICC_HOTKEY_CLASS,
    ICC_LISTVIEW_CLASSES,
    ICC_STANDARD_CLASSES,
    ICC_TAB_CLASSES,
    INITCOMMONCONTROLSEX,
    INVALID_HANDLE_VALUE,
    ULONG_PTR,
    comctl32,
    kernel32,
)


def init_common_controls() -> bool:
    icc = INITCOMMONCONTROLSEX()
    icc.dwSize = ctypes.sizeof(INITCOMMONCONTROLSEX)
    icc.dwICC = (
        ICC_TAB_CLASSES
        | ICC_LISTVIEW_CLASSES
        | ICC_BAR_CLASSES
        | ICC_HOTKEY_CLASS
        | ICC_STANDARD_CLASSES
    )
    return bool(comctl32.InitCommonControlsEx(ctypes.byref(icc)))


@contextmanager
def comctl_v6_context(manifest_path: Path | None) -> Iterator[bool]:
    """manifest 파일로 comctl32 v6 활성화 컨텍스트를 적용한다. 실패 시 클래식 스타일로 폴백."""
    if manifest_path is None or not manifest_path.exists():
        init_common_controls()
        yield False
        return

    act = ACTCTXW()
    act.cbSize = ctypes.sizeof(ACTCTXW)
    act.dwFlags = 0
    act.lpSource = str(manifest_path)

    hctx = kernel32.CreateActCtxW(ctypes.byref(act))
    if not hctx or hctx == INVALID_HANDLE_VALUE:
        init_common_controls()
        yield False
        return

    cookie = ULONG_PTR(0)
    activated = bool(kernel32.ActivateActCtx(hctx, ctypes.byref(cookie)))
    try:
        init_common_controls()
        yield activated
    finally:
        if activated:
            kernel32.DeactivateActCtx(0, cookie)
        kernel32.ReleaseActCtx(hctx)

