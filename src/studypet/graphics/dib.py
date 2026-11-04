"""32-bit Top-Down DIBSection 래퍼 및 고속 행 단위 메모리 복사 (DEVELOPMENT_PLAN.md 4-11)."""
from __future__ import annotations

import ctypes
from ctypes import wintypes as wt

from studypet.win32.api import BI_RGB, BITMAPINFO, DIB_RGB_COLORS, gdi32


class DibSurface:
    """CreateDIBSection으로 할당된 32-bit Top-Down Premultiplied BGRA 표면."""

    def __init__(self, w_px: int, h_px: int) -> None:
        if w_px <= 0 or h_px <= 0:
            raise ValueError(f"Invalid DIB dimensions: {w_px}x{h_px}")
        self.width: int = int(w_px)
        self.height: int = int(h_px)
        self.stride: int = self.width * 4
        self.byte_size: int = self.stride * self.height

        self.hdc: wt.HDC = gdi32.CreateCompatibleDC(None)
        if not self.hdc:
            raise RuntimeError("CreateCompatibleDC failed")

        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(bmi.bmiHeader)
        bmi.bmiHeader.biWidth = self.width
        bmi.bmiHeader.biHeight = -self.height  # Top-Down DIB (0행 = 상단)
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = BI_RGB
        bmi.bmiHeader.biSizeImage = self.byte_size

        ppv = ctypes.c_void_p()
        self.hbmp: wt.HBITMAP = gdi32.CreateDIBSection(
            self.hdc,
            ctypes.byref(bmi),
            DIB_RGB_COLORS,
            ctypes.byref(ppv),
            None,
            0,
        )
        if not self.hbmp or not ppv.value:
            gdi32.DeleteDC(self.hdc)
            raise RuntimeError("CreateDIBSection failed")

        self._old_bmp: wt.HGDIOBJ = gdi32.SelectObject(self.hdc, self.hbmp)
        self.base_addr: int = int(ppv.value)
        self.bits = (ctypes.c_ubyte * self.byte_size).from_address(self.base_addr)

    def clear_all(self) -> None:
        if self.base_addr:
            ctypes.memset(self.base_addr, 0, self.byte_size)

    def clear_rect(self, x: int, y: int, w: int, h: int) -> None:
        if not self.base_addr or w <= 0 or h <= 0:
            return
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(self.width, x + w)
        y1 = min(self.height, y + h)
        if x0 >= x1 or y0 >= y1:
            return
        if x0 == 0 and x1 == self.width:
            ctypes.memset(self.base_addr + y0 * self.stride, 0, (y1 - y0) * self.stride)
            return
        row_bytes = (x1 - x0) * 4
        offset_x = x0 * 4
        for row in range(y0, y1):
            ctypes.memset(self.base_addr + row * self.stride + offset_x, 0, row_bytes)

    def blit_rows(self, src: bytes, src_w: int, src_h: int, x: int, y: int) -> None:
        """사전 스케일된 BGRA 바이트 버퍼를 행 단위 ctypes.memmove로 고속 복사한다 (클리핑 포함)."""
        if not self.base_addr or src_w <= 0 or src_h <= 0:
            return
        expected = src_w * src_h * 4
        if len(src) < expected:
            raise ValueError(f"src buffer too small: {len(src)} < {expected}")

        # 클리핑 영역 계산
        dst_x0 = max(0, x)
        dst_y0 = max(0, y)
        dst_x1 = min(self.width, x + src_w)
        dst_y1 = min(self.height, y + src_h)
        if dst_x0 >= dst_x1 or dst_y0 >= dst_y1:
            return

        src_x0 = dst_x0 - x
        src_y0 = dst_y0 - y
        copy_w_bytes = (dst_x1 - dst_x0) * 4
        src_stride = src_w * 4
        rows = dst_y1 - dst_y0

        src_buf = ctypes.c_char_p(src)
        src_base = ctypes.cast(src_buf, ctypes.c_void_p).value
        if not src_base:
            return

        for r in range(rows):
            s_addr = src_base + (src_y0 + r) * src_stride + src_x0 * 4
            d_addr = self.base_addr + (dst_y0 + r) * self.stride + dst_x0 * 4
            ctypes.memmove(d_addr, s_addr, copy_w_bytes)

    def destroy(self) -> None:
        if getattr(self, "hdc", None):
            if getattr(self, "_old_bmp", None):
                gdi32.SelectObject(self.hdc, self._old_bmp)
                self._old_bmp = None
            if getattr(self, "hbmp", None):
                gdi32.DeleteObject(self.hbmp)
                self.hbmp = None
            gdi32.DeleteDC(self.hdc)
            self.hdc = None
        self.base_addr = 0

