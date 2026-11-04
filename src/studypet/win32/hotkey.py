"""전역 단축키(RegisterHotKey) 파싱 및 등록·해제 관리 (DEVELOPMENT_PLAN.md 4-13)."""
from __future__ import annotations

from ctypes import wintypes as wt
import logging

from studypet.win32.api import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_NOREPEAT,
    MOD_SHIFT,
    user32,
)


logger = logging.getLogger(__name__)

HOTKEY_ID_GHOST = 1

# msctls_hotkey32 제어용 수정자 상수 (commctrl.h)
HOTKEYF_SHIFT = 0x01
HOTKEYF_CONTROL = 0x02
HOTKEYF_ALT = 0x04


def parse_hotkey_string(shortcut: str) -> tuple[int, int] | None:
    """'Ctrl+Alt+G' 형식 문자열을 파싱하여 (win32_mods, vk_code) 튜플을 반환한다."""
    if not isinstance(shortcut, str) or not shortcut.strip():
        return None
    parts = [p.strip().upper() for p in shortcut.split("+") if p.strip()]
    if len(parts) < 2:
        return None

    mods = 0
    for mod_part in parts[:-1]:
        if mod_part in ("CTRL", "CONTROL"):
            mods |= MOD_CONTROL
        elif mod_part == "ALT":
            mods |= MOD_ALT
        elif mod_part == "SHIFT":
            mods |= MOD_SHIFT
        else:
            return None

    if mods == 0:
        return None

    key = parts[-1]
    if len(key) == 1 and ("A" <= key <= "Z" or "0" <= key <= "9"):
        vk = ord(key)
        return (mods, vk)
    if key.startswith("F") and key[1:].isdigit():
        fn = int(key[1:])
        if 1 <= fn <= 12:
            vk = 0x70 + (fn - 1)  # VK_F1 == 0x70
            return (mods, vk)
    return None


def hotkey_string_to_hk_word(shortcut: str) -> int:
    """'Ctrl+Alt+G' 문자열을 msctls_hotkey32의 HKM_SETHOTKEY wParam 값(LOBYTE=vk, HIBYTE=hotkeyf)으로 변환한다."""
    parsed = parse_hotkey_string(shortcut)
    if parsed is None:
        return 0
    mods, vk = parsed
    hk_flags = 0
    if mods & MOD_CONTROL:
        hk_flags |= HOTKEYF_CONTROL
    if mods & MOD_ALT:
        hk_flags |= HOTKEYF_ALT
    if mods & MOD_SHIFT:
        hk_flags |= HOTKEYF_SHIFT
    return (vk & 0xFF) | ((hk_flags & 0xFF) << 8)


def hk_word_to_hotkey_string(hk_word: int) -> str | None:
    """msctls_hotkey32의 HKM_GETHOTKEY 반환값을 'Ctrl+Alt+G' 문자열로 변환한다."""
    vk = hk_word & 0xFF
    hk_flags = (hk_word >> 8) & 0xFF
    if vk == 0 or hk_flags == 0:
        return None

    tokens: list[str] = []
    if hk_flags & HOTKEYF_CONTROL:
        tokens.append("Ctrl")
    if hk_flags & HOTKEYF_ALT:
        tokens.append("Alt")
    if hk_flags & HOTKEYF_SHIFT:
        tokens.append("Shift")
    if not tokens:
        return None

    if ord("A") <= vk <= ord("Z") or ord("0") <= vk <= ord("9"):
        tokens.append(chr(vk))
    elif 0x70 <= vk <= 0x7B:
        tokens.append(f"F{vk - 0x70 + 1}")
    else:
        return None

    return "+".join(tokens)


class HotkeyManager:
    """유령 모드 토글 전역 단축키 등록/해제."""

    def __init__(self, hwnd: wt.HWND) -> None:
        self.hwnd = hwnd
        self._registered: bool = False
        self.current_shortcut: str = ""

    def register(self, shortcut: str) -> bool:
        self.unregister()
        if not self.hwnd:
            return False
        parsed = parse_hotkey_string(shortcut)
        if parsed is None:
            return False
        mods, vk = parsed
        ok = bool(user32.RegisterHotKey(self.hwnd, HOTKEY_ID_GHOST, mods | MOD_NOREPEAT, vk))
        self._registered = ok
        if ok:
            self.current_shortcut = shortcut
        else:
            logger.warning("RegisterHotKey failed for %s (already in use)", shortcut)
        return ok

    def unregister(self) -> None:
        if self._registered and self.hwnd:
            user32.UnregisterHotKey(self.hwnd, HOTKEY_ID_GHOST)
            self._registered = False

