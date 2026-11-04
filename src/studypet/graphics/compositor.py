"""펫 캔버스(192x144 sp) 레이어 합성기 (DEVELOPMENT_PLAN.md 4-11)."""
from __future__ import annotations

import ctypes
from ctypes import wintypes as wt

from studypet.graphics.dib import DibSurface
from studypet.win32.api import (
    AC_SRC_ALPHA,
    AC_SRC_OVER,
    BLENDFUNCTION,
    POINT,
    SIZE,
    SWP_NOACTIVATE,
    SWP_NOMOVE,
    SWP_NOSIZE,
    SWP_NOZORDER,
    ULW_ALPHA,
    user32,
)


CANVAS_W_SP = 192
CANVAS_H_SP = 144
CHAR_X_SP = 64
CHAR_Y_SP = 80
CHAR_W_SP = 64
CHAR_H_SP = 64


class Compositor:
    """레이어끼리 겹치지 않는 192x144 sp 캔버스를 행 복사(memmove)만으로 합성하고 UpdateLayeredWindow로 출력한다."""

    def __init__(self, scale: int) -> None:
        self.scale: int = max(1, int(scale))
        self.surface = DibSurface(CANVAS_W_SP * self.scale, CANVAS_H_SP * self.scale)
        self._char_bytes: bytes | None = None
        self._bubble: tuple[bytes, int, int, int, int] | None = None  # (bytes, x_sp, y_sp, w_sp, h_sp)
        self._menu_icons: list[tuple[bytes, int, int, int, int]] | None = None  # [(bytes, x_sp, y_sp, w_sp, h_sp)]
        self._panel: tuple[bytes, int, int, int, int] | None = None
        self._dirty: bool = True
        self._last_pos: tuple[int, int] | None = None
        self._last_alpha: int = -1

    def set_scale(self, scale: int) -> None:
        s = max(1, int(scale))
        if s != self.scale:
            self.scale = s
            self.surface.destroy()
            self.surface = DibSurface(CANVAS_W_SP * s, CANVAS_H_SP * s)
            self._dirty = True

    def set_character(self, frame_bytes: bytes) -> None:
        if self._char_bytes is not frame_bytes:
            self._char_bytes = frame_bytes
            self._dirty = True

    def set_bubble(self, layer: tuple[bytes, int, int, int, int] | None) -> None:
        if self._bubble != layer:
            self._bubble = layer
            self._dirty = True

    def set_menu(self, icons: list[tuple[bytes, int, int, int, int]] | None) -> None:
        if self._menu_icons != icons:
            self._menu_icons = icons
            self._dirty = True

    def set_panel(self, panel: tuple[bytes, int, int, int, int] | None) -> None:
        if self._panel != panel:
            self._panel = panel
            self._dirty = True

    def mark_dirty(self) -> None:
        self._dirty = True

    def present(self, hwnd: wt.HWND, screen_x: int, screen_y: int, opacity: float = 1.0) -> bool:
        """버퍼 변경 시 UpdateLayeredWindow를 호출하고, 위치만 바뀐 경우 SetWindowPos만 호출한다."""
        if not hwnd:
            return False
        s = self.scale
        alpha_byte = max(1, min(255, int(round(255.0 * opacity))))
        if alpha_byte != self._last_alpha:
            self._dirty = True

        if self._dirty:
            self.surface.clear_all()
            if self._char_bytes is not None:
                self.surface.blit_rows(
                    self._char_bytes,
                    CHAR_W_SP * s,
                    CHAR_H_SP * s,
                    CHAR_X_SP * s,
                    CHAR_Y_SP * s,
                )
            if self._menu_icons is not None:
                for ibytes, ix, iy, iw, ih in self._menu_icons:
                    self.surface.blit_rows(ibytes, iw * s, ih * s, ix * s, iy * s)
            elif self._panel is not None:
                pbytes, px, py, pw, ph = self._panel
                self.surface.blit_rows(pbytes, pw * s, ph * s, px * s, py * s)
            elif self._bubble is not None:
                bbytes, bx, by, bw, bh = self._bubble
                self.surface.blit_rows(bbytes, bw * s, bh * s, bx * s, by * s)

            pos = POINT(int(screen_x), int(screen_y))
            size = SIZE(CANVAS_W_SP * s, CANVAS_H_SP * s)
            src_pt = POINT(0, 0)
            blend = BLENDFUNCTION(AC_SRC_OVER, 0, alpha_byte, AC_SRC_ALPHA)
            user32.UpdateLayeredWindow(
                hwnd,
                None,
                ctypes.byref(pos),
                ctypes.byref(size),
                self.surface.hdc,
                ctypes.byref(src_pt),
                0,
                ctypes.byref(blend),
                ULW_ALPHA,
            )
            self._dirty = False
            self._last_pos = (int(screen_x), int(screen_y))
            self._last_alpha = alpha_byte
            return True

        new_pos = (int(screen_x), int(screen_y))
        if new_pos != self._last_pos:
            user32.SetWindowPos(
                hwnd,
                None,
                new_pos[0],
                new_pos[1],
                0,
                0,
                SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE,
            )
            self._last_pos = new_pos
            return True

        return False

    def destroy(self) -> None:
        self.surface.destroy()

