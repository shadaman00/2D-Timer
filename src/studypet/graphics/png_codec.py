"""순수 Python PNG(RGBA8, 필터 0~4) 인코더/디코더 및 ICO 인코더 (DEVELOPMENT_PLAN.md 4-11)."""
from __future__ import annotations

import struct
import zlib


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _paeth_predictor(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def _make_chunk(chunk_type: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(chunk_type)
    crc = zlib.crc32(data, crc) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)


def validate_strict_binary_alpha(rgba_bytes: bytes) -> None:
    """알파 채널이 0 또는 255만 포함하는지 검증한다 (반투명 픽셀 거부)."""
    alphas = rgba_bytes[3::4]
    for a in alphas:
        if a not in (0, 255):
            raise ValueError(f"Alpha value must be 0 or 255, got {a}")


def encode_png_rgba(
    width: int,
    height: int,
    rgba_bytes: bytes,
    filter_type: int = 0,
    strict_alpha: bool = True,
) -> bytes:
    """RGBA8 바이트 버퍼를 비인터레이스 PNG로 인코딩한다 (필터 0~4 지원)."""
    if width <= 0 or height <= 0:
        raise ValueError(f"Invalid PNG dimensions: {width}x{height}")
    stride = width * 4
    if len(rgba_bytes) != stride * height:
        raise ValueError(f"Expected {stride * height} bytes, got {len(rgba_bytes)}")
    if filter_type not in (0, 1, 2, 3, 4):
        raise ValueError(f"Unsupported PNG filter type: {filter_type}")
    if strict_alpha:
        validate_strict_binary_alpha(rgba_bytes)

    raw_rows = bytearray()
    prev_row = bytes(stride)
    for y in range(height):
        row = rgba_bytes[y * stride : (y + 1) * stride]
        raw_rows.append(filter_type)
        if filter_type == 0:
            raw_rows.extend(row)
        elif filter_type == 1:  # Sub
            for i in range(stride):
                left = row[i - 4] if i >= 4 else 0
                raw_rows.append((row[i] - left) & 0xFF)
        elif filter_type == 2:  # Up
            for i in range(stride):
                up = prev_row[i]
                raw_rows.append((row[i] - up) & 0xFF)
        elif filter_type == 3:  # Average
            for i in range(stride):
                left = row[i - 4] if i >= 4 else 0
                up = prev_row[i]
                raw_rows.append((row[i] - ((left + up) >> 1)) & 0xFF)
        elif filter_type == 4:  # Paeth
            for i in range(stride):
                left = row[i - 4] if i >= 4 else 0
                up = prev_row[i]
                up_left = prev_row[i - 4] if i >= 4 else 0
                pred = _paeth_predictor(left, up, up_left)
                raw_rows.append((row[i] - pred) & 0xFF)
        prev_row = row

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    compressed = zlib.compress(bytes(raw_rows), level=9)
    return (
        PNG_SIGNATURE
        + _make_chunk(b"IHDR", ihdr)
        + _make_chunk(b"IDAT", compressed)
        + _make_chunk(b"IEND", b"")
    )


def decode_png_rgba(png_bytes: bytes) -> tuple[int, int, bytes]:
    """8-bit RGBA(색 형식 6, 비인터레이스, 필터 0~4) PNG를 디코딩하여 (width, height, rgba_bytes)를 반환한다."""
    if not png_bytes.startswith(PNG_SIGNATURE):
        raise ValueError("Invalid PNG signature")

    pos = len(PNG_SIGNATURE)
    width = 0
    height = 0
    ihdr_seen = False
    idat_chunks: list[bytes] = []
    iend_seen = False

    while pos + 8 <= len(png_bytes):
        length, chunk_type = struct.unpack(">I4s", png_bytes[pos : pos + 8])
        pos += 8
        if pos + length + 4 > len(png_bytes):
            raise ValueError("Truncated PNG chunk")
        chunk_data = png_bytes[pos : pos + length]
        pos += length
        expected_crc = struct.unpack(">I", png_bytes[pos : pos + 4])[0]
        pos += 4

        calc_crc = zlib.crc32(chunk_type)
        calc_crc = zlib.crc32(chunk_data, calc_crc) & 0xFFFFFFFF
        if calc_crc != expected_crc:
            raise ValueError(f"CRC mismatch in chunk {chunk_type!r}")

        if chunk_type == b"IHDR":
            if length != 13:
                raise ValueError("Invalid IHDR length")
            w, h, bit_depth, color_type, comp, filt, interlace = struct.unpack(">IIBBBBB", chunk_data)
            if bit_depth != 8 or color_type != 6 or comp != 0 or filt != 0 or interlace != 0:
                raise ValueError(
                    f"Unsupported PNG format: depth={bit_depth}, color={color_type}, interlace={interlace}"
                )
            if w <= 0 or h <= 0:
                raise ValueError("Invalid PNG dimensions in IHDR")
            width, height = w, h
            ihdr_seen = True
        elif chunk_type == b"IDAT":
            idat_chunks.append(chunk_data)
        elif chunk_type == b"IEND":
            iend_seen = True
            break

    if not ihdr_seen or not idat_chunks or not iend_seen:
        raise ValueError("Incomplete PNG stream")

    raw = zlib.decompress(b"".join(idat_chunks))
    stride = width * 4
    expected_raw_len = height * (1 + stride)
    if len(raw) != expected_raw_len:
        raise ValueError(f"Decompressed size mismatch: {len(raw)} != {expected_raw_len}")

    out = bytearray(height * stride)
    prev_row = bytearray(stride)
    in_pos = 0
    for y in range(height):
        f_type = raw[in_pos]
        in_pos += 1
        row_in = raw[in_pos : in_pos + stride]
        in_pos += stride
        row_out = bytearray(stride)

        if f_type == 0:
            row_out[:] = row_in
        elif f_type == 1:  # Sub
            for i in range(stride):
                left = row_out[i - 4] if i >= 4 else 0
                row_out[i] = (row_in[i] + left) & 0xFF
        elif f_type == 2:  # Up
            for i in range(stride):
                row_out[i] = (row_in[i] + prev_row[i]) & 0xFF
        elif f_type == 3:  # Average
            for i in range(stride):
                left = row_out[i - 4] if i >= 4 else 0
                up = prev_row[i]
                row_out[i] = (row_in[i] + ((left + up) >> 1)) & 0xFF
        elif f_type == 4:  # Paeth
            for i in range(stride):
                left = row_out[i - 4] if i >= 4 else 0
                up = prev_row[i]
                up_left = prev_row[i - 4] if i >= 4 else 0
                pred = _paeth_predictor(left, up, up_left)
                row_out[i] = (row_in[i] + pred) & 0xFF
        else:
            raise ValueError(f"Invalid PNG scanline filter: {f_type}")

        out[y * stride : (y + 1) * stride] = row_out
        prev_row = row_out

    return width, height, bytes(out)


def rgba_to_premultiplied_bgra(rgba_bytes: bytes) -> bytes:
    """RGBA8 바이트를 Win32 UpdateLayeredWindow용 Premultiplied BGRA 바이트로 변환한다 (로드 시 1회)."""
    n = len(rgba_bytes)
    out = bytearray(n)
    for i in range(0, n, 4):
        r = rgba_bytes[i]
        g = rgba_bytes[i + 1]
        b = rgba_bytes[i + 2]
        a = rgba_bytes[i + 3]
        if a == 0:
            out[i : i + 4] = b"\x00\x00\x00\x00"
        elif a == 255:
            out[i] = b
            out[i + 1] = g
            out[i + 2] = r
            out[i + 3] = 255
        else:
            out[i] = (b * a) // 255
            out[i + 1] = (g * a) // 255
            out[i + 2] = (r * a) // 255
            out[i + 3] = a
    return bytes(out)


def _encode_ico_bmp_entry(w: int, h: int, rgba_bytes: bytes) -> bytes:
    """16/32/48px 아이콘을 Bottom-Up 32bpp DIB + 1bpp AND 마스크 형식으로 인코딩한다."""
    xor_mask = bytearray(w * h * 4)
    and_row_bytes = ((w + 31) // 32) * 4
    and_mask = bytearray(and_row_bytes * h)

    for y in range(h):
        src_y = h - 1 - y  # Bottom-Up
        for x in range(w):
            si = (src_y * w + x) * 4
            di = (y * w + x) * 4
            r, g, b, a = rgba_bytes[si : si + 4]
            xor_mask[di] = b
            xor_mask[di + 1] = g
            xor_mask[di + 2] = r
            xor_mask[di + 3] = a
            if a == 0:
                byte_idx = y * and_row_bytes + (x // 8)
                bit_idx = 7 - (x % 8)
                and_mask[byte_idx] |= 1 << bit_idx

    bmi_header = struct.pack(
        "<IIIHHIIIIII",
        40,
        w,
        h * 2,  # XOR + AND 높이 합산
        1,
        32,
        0,
        len(xor_mask) + len(and_mask),
        0,
        0,
        0,
        0,
    )
    return bmi_header + bytes(xor_mask) + bytes(and_mask)


def encode_ico(entries: list[tuple[int, int, bytes]]) -> bytes:
    """[(w, h, rgba_bytes), ...] 목록을 받아 멀티 해상도 Windows .ico 바이너리를 생성한다.
    16·32·48은 BMP DIB 항목으로, 256은 PNG 항목으로 저장한다.
    """
    if not entries:
        raise ValueError("ICO must contain at least one image")

    payloads: list[tuple[int, int, bytes]] = []
    for w, h, rgba in entries:
        if w >= 256 or h >= 256:
            data = encode_png_rgba(w, h, rgba, strict_alpha=False)
        else:
            data = _encode_ico_bmp_entry(w, h, rgba)
        payloads.append((w, h, data))

    header = struct.pack("<HHH", 0, 1, len(payloads))
    dir_entries = bytearray()
    offset = 6 + 16 * len(payloads)

    for w, h, data in payloads:
        bw = 0 if w >= 256 else w
        bh = 0 if h >= 256 else h
        dir_entries.extend(
            struct.pack(
                "<BBBBHHII",
                bw,
                bh,
                0,
                0,
                1,
                32,
                len(data),
                offset,
            )
        )
        offset += len(data)

    return header + bytes(dir_entries) + b"".join(d for _, _, d in payloads)

