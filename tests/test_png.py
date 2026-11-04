"""PNG 인코더·디코더 및 알파 0/255 규칙 테스트 (DEVELOPMENT_PLAN.md 7-1)."""
from __future__ import annotations

import unittest

from studypet.graphics.png_codec import (
    decode_png_rgba,
    encode_png_rgba,
    validate_strict_binary_alpha,
)


class TestPngCodec(unittest.TestCase):
    def _sample_rgba(self, w: int = 8, h: int = 6) -> bytes:
        buf = bytearray(w * h * 4)
        for y in range(h):
            for x in range(w):
                idx = (y * w + x) * 4
                if (x + y) % 3 == 0:
                    buf[idx : idx + 4] = b"\x00\x00\x00\x00"
                else:
                    buf[idx] = (x * 31 + y * 17) & 0xFF
                    buf[idx + 1] = (x * 13 + y * 53) & 0xFF
                    buf[idx + 2] = (x * 71 + y * 29) & 0xFF
                    buf[idx + 3] = 255
        return bytes(buf)

    def test_encode_decode_roundtrip_all_filters(self) -> None:
        src = self._sample_rgba(12, 10)
        for f_type in (0, 1, 2, 3, 4):
            with self.subTest(filter_type=f_type):
                png = encode_png_rgba(12, 10, src, filter_type=f_type, strict_alpha=True)
                w, h, decoded = decode_png_rgba(png)
                self.assertEqual(w, 12)
                self.assertEqual(h, 10)
                self.assertEqual(decoded, src)

    def test_reject_non_binary_alpha(self) -> None:
        bad = bytearray(self._sample_rgba(4, 4))
        bad[3] = 128  # 반투명 픽셀
        with self.assertRaises(ValueError):
            validate_strict_binary_alpha(bytes(bad))
        with self.assertRaises(ValueError):
            encode_png_rgba(4, 4, bytes(bad), strict_alpha=True)

    def test_reject_invalid_signature_or_corrupt_crc(self) -> None:
        src = self._sample_rgba(4, 4)
        png = encode_png_rgba(4, 4, src)
        with self.assertRaises(ValueError):
            decode_png_rgba(b"NOT_A_PNG" + png[8:])

        corrupted = bytearray(png)
        corrupted[-6] ^= 0xFF
        with self.assertRaises(ValueError):
            decode_png_rgba(bytes(corrupted))


if __name__ == "__main__":
    unittest.main()

