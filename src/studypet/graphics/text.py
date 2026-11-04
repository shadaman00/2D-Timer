"""GDI 픽셀 폰트 텍스트 렌더링 및 알파 복원 (DEVELOPMENT_PLAN.md 4-11)."""
from __future__ import annotations

import ctypes
from ctypes import wintypes as wt
from pathlib import Path

from studypet.graphics.dib import DibSurface
from studypet.win32.api import (
    FR_PRIVATE,
    NONANTIALIASED_QUALITY,
    SIZE,
    TRANSPARENT,
    gdi32,
)


def rgb_to_colorref(r: int, g: int, b: int) -> int:
    return (int(r) & 0xFF) | ((int(g) & 0xFF) << 8) | ((int(b) & 0xFF) << 16)


class PixelFontRenderer:
    """픽셀 폰트를 프로세스 로컬로 등록하고 GDI TextOutW 후 스텝 슬라이스로 알파(0xFF)를 복원한다."""

    def __init__(self, font_ttf_path: Path | None = None) -> None:
        self.font_path: Path | None = None
        self.face_name: str = "맑은 고딕"
        self._fonts_by_px: dict[int, wt.HFONT] = {}

        if font_ttf_path is not None and font_ttf_path.exists():
            added = gdi32.AddFontResourceExW(str(font_ttf_path), FR_PRIVATE, None)
            if added > 0:
                self.font_path = font_ttf_path
                self.face_name = "Galmuri11"

    def get_hfont(self, height_px: int, bold: bool = False) -> wt.HFONT:
        key = (height_px if not bold else -height_px)
        hfont = self._fonts_by_px.get(key)
        if hfont:
            return hfont
        weight = 700 if bold else 400
        hfont = gdi32.CreateFontW(
            -abs(int(height_px)),
            0,
            0,
            0,
            weight,
            0,
            0,
            0,
            1,  # DEFAULT_CHARSET
            0,
            0,
            NONANTIALIASED_QUALITY,
            0,
            self.face_name,
        )
        self._fonts_by_px[key] = hfont
        return hfont

    def measure_text(self, hdc: wt.HDC, text: str, scale: int) -> tuple[int, int]:
        hfont = self.get_hfont(10 * max(1, scale))
        old_font = gdi32.SelectObject(hdc, hfont)
        try:
            sz = SIZE()
            gdi32.GetTextExtentPoint32W(hdc, text, len(text), ctypes.byref(sz))
            return (int(sz.cx), int(sz.cy))
        finally:
            gdi32.SelectObject(hdc, old_font)

    def render_on_panel(
        self,
        panel_bgra: bytes,
        w_px: int,
        h_px: int,
        scale: int,
        lines: list[tuple[int, int, str, tuple[int, int, int]]],
        border_px: int = 2,
    ) -> bytes:
        """불투명 9-slice 패널 위에 텍스트 줄들을 그리고, GDI가 0으로 만든 내부 알파를 스텝 슬라이스로 복원한다."""
        surf = DibSurface(w_px, h_px)
        try:
            surf.blit_rows(panel_bgra, w_px, h_px, 0, 0)
            hfont = self.get_hfont(9 * max(1, scale))
            old_font = gdi32.SelectObject(surf.hdc, hfont)
            gdi32.SetBkMode(surf.hdc, TRANSPARENT)
            try:
                for x_px, y_px, text, (r, g, b) in lines:
                    if not text:
                        continue
                    gdi32.SetTextColor(surf.hdc, rgb_to_colorref(r, g, b))
                    gdi32.TextOutW(surf.hdc, int(x_px), int(y_px), text, len(text))
            finally:
                gdi32.SelectObject(surf.hdc, old_font)

            gdi32.GdiFlush()

            # DIB 버퍼를 bytearray로 복사한 뒤 패널 내부 영역 행의 알파(3::4)를 0xFF로 일괄 복원 (픽셀 루프 금지!)
            raw_ba = bytearray(surf.bits)
            pad = max(1, border_px * scale)
            inner_w = max(0, w_px - 2 * pad)
            if inner_w > 0:
                alpha_fill = b"\xff" * inner_w
                stride = w_px * 4
                x_start_alpha = pad * 4 + 3
                x_end_alpha = (pad + inner_w) * 4
                for y in range(pad, h_px - pad):
                    row_off = y * stride
                    raw_ba[row_off + x_start_alpha : row_off + x_end_alpha : 4] = alpha_fill

            return bytes(raw_ba)
        finally:
            surf.destroy()

    def destroy(self) -> None:
        for hfont in self._fonts_by_px.values():
            if hfont:
                gdi32.DeleteObject(hfont)
        self._fonts_by_px.clear()
        if self.font_path is not None:
            gdi32.RemoveFontResourceExW(str(self.font_path), FR_PRIVATE, None)
            self.font_path = None

