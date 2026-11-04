"""9-slice 도트 패널 합성 및 캐시 (DEVELOPMENT_PLAN.md 4-11)."""
from __future__ import annotations

from pathlib import Path

from studypet.graphics.png_codec import decode_png_rgba, rgba_to_premultiplied_bgra
from studypet.graphics.sprites import scale_frame


class NineSlicePanel:
    """12x12 원본(모서리 4sp) 이미지를 임의의 (w_sp, h_sp) 크기로 합성 후 정수 배율로 스케일·캐시한다."""

    def __init__(self, panel_png_path: Path, corner_sp: int = 4) -> None:
        w, h, rgba = decode_png_rgba(panel_png_path.read_bytes())
        if w < corner_sp * 2 + 1 or h < corner_sp * 2 + 1:
            raise ValueError(f"Panel image too small for corner={corner_sp}: {w}x{h}")
        self.src_w = w
        self.src_h = h
        self.corner = corner_sp
        self.src_bgra = rgba_to_premultiplied_bgra(rgba)
        self._cache: dict[tuple[int, int, int], bytes] = {}

    def _slice_row_sp(self, src_y: int, target_w_sp: int) -> bytes:
        c = self.corner
        mid_w = max(0, target_w_sp - 2 * c)
        row_start = src_y * self.src_w * 4
        left_part = self.src_bgra[row_start : row_start + c * 4]
        mid_px = self.src_bgra[row_start + c * 4 : row_start + (c + 1) * 4]
        right_part = self.src_bgra[row_start + (self.src_w - c) * 4 : row_start + self.src_w * 4]
        return left_part + (mid_px * mid_w) + right_part

    def get_panel(self, w_sp: int, h_sp: int, scale: int) -> bytes:
        """(w_sp * scale) x (h_sp * scale) 크기의 Premultiplied BGRA 바이트를 반환한다."""
        c = self.corner
        w_sp = max(c * 2 + 1, int(w_sp))
        h_sp = max(c * 2 + 1, int(h_sp))
        s = max(1, int(scale))

        key = (w_sp, h_sp, s)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        unscaled_rows: list[bytes] = []
        # 상단 모서리 행
        for y in range(c):
            unscaled_rows.append(self._slice_row_sp(y, w_sp))
        # 중앙 반복 행
        mid_row = self._slice_row_sp(c, w_sp)
        for _ in range(h_sp - 2 * c):
            unscaled_rows.append(mid_row)
        # 하단 모서리 행
        for y in range(self.src_h - c, self.src_h):
            unscaled_rows.append(self._slice_row_sp(y, w_sp))

        unscaled_bgra = b"".join(unscaled_rows)
        scaled_bgra = scale_frame(unscaled_bgra, w_sp, h_sp, s, flip=False)
        self._cache[key] = scaled_bgra
        return scaled_bgra

    def clear_cache(self) -> None:
        self._cache.clear()


def fill_rect(
    buf: bytearray,
    buf_w_px: int,
    x: int,
    y: int,
    w: int,
    h: int,
    bgra: bytes,
) -> None:
    """Premultiplied BGRA 4바이트 색상을 행 슬라이스 대입으로 (x, y, w, h) 영역에 채운다 (v0.7 3-7)."""
    if w <= 0 or h <= 0 or buf_w_px <= 0 or len(bgra) != 4:
        return
    buf_h_px = len(buf) // (buf_w_px * 4)
    x0 = max(0, int(x))
    y0 = max(0, int(y))
    x1 = min(buf_w_px, int(x) + int(w))
    y1 = min(buf_h_px, int(y) + int(h))
    if x1 <= x0 or y1 <= y0:
        return
    span_w = x1 - x0
    row_slice = bytes(bgra) * span_w
    stride = buf_w_px * 4
    span_bytes = span_w * 4
    for py in range(y0, y1):
        start = py * stride + x0 * 4
        buf[start : start + span_bytes] = row_slice


