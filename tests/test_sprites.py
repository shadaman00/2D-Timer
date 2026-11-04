"""사전 스케일, 좌우 반전, Premultiplied BGRA 변환 및 SpriteSheet/NineSlicePanel 캐시 테스트 (7-1)."""
from __future__ import annotations

from pathlib import Path
import unittest

from studypet.graphics.panel import NineSlicePanel
from studypet.graphics.png_codec import rgba_to_premultiplied_bgra
from studypet.graphics.sprites import SpriteSheet, scale_frame


ROOT = Path(__file__).resolve().parents[1]


class TestSprites(unittest.TestCase):
    def test_rgba_to_premultiplied_bgra(self) -> None:
        # 픽셀 0: 투명(RGB가 있어도 0,0,0,0이 되어야 함), 픽셀 1: 불투명(R=10, G=20, B=30, A=255 -> B=30, G=20, R=10, A=255)
        rgba = bytes([100, 150, 200, 0, 10, 20, 30, 255])
        bgra = rgba_to_premultiplied_bgra(rgba)
        self.assertEqual(bgra[:4], b"\x00\x00\x00\x00")
        self.assertEqual(bgra[4:8], bytes([30, 20, 10, 255]))

    def test_scale_frame_dimensions_and_flip(self) -> None:
        # 2x1 원본: 왼쪽 빨강(B=0,G=0,R=255,A=255), 오른쪽 파랑(B=255,G=0,R=0,A=255)
        red = bytes([0, 0, 255, 255])
        blue = bytes([255, 0, 0, 255])
        src = red + blue

        s2 = scale_frame(src, 2, 1, 2, flip=False)
        self.assertEqual(len(s2), (2 * 2) * (1 * 2) * 4)
        # 첫 행: red, red, blue, blue
        self.assertEqual(s2[:16], red * 2 + blue * 2)

        s2_flip = scale_frame(src, 2, 1, 2, flip=True)
        # 반전 첫 행: blue, blue, red, red
        self.assertEqual(s2_flip[:16], blue * 2 + red * 2)

    def test_sprite_sheet_load_and_cache(self) -> None:
        skin_dir = ROOT / "assets" / "skins" / "default_pixel_cat"
        sheet = SpriteSheet(skin_dir / "sheet.png", skin_dir / "meta.json", initial_scale=2)
        f0 = sheet.get_frame("idle", 0, 2, flip=False)
        self.assertEqual(len(f0), (64 * 2) * (64 * 2) * 4)
        # 캐시 동일 객체 반환 확인
        self.assertIs(f0, sheet.get_frame("idle", 0, 2, flip=False))

        # 비루프 상태(celebrate)는 마지막 프레임에 고정되는지 확인
        celeb_last = sheet.get_frame("celebrate", 99, 2, flip=False)
        celeb_5 = sheet.get_frame("celebrate", 5, 2, flip=False)
        self.assertIs(celeb_last, celeb_5)

    def test_nine_slice_panel(self) -> None:
        panel = NineSlicePanel(ROOT / "assets" / "ui" / "panel.png")
        p_bytes = panel.get_panel(48, 24, 2)
        self.assertEqual(len(p_bytes), (48 * 2) * (24 * 2) * 4)
        self.assertIs(p_bytes, panel.get_panel(48, 24, 2))


if __name__ == "__main__":
    unittest.main()

