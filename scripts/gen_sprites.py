"""도트 캐릭터(default_pixel_cat 34프레임), UI 9-slice 패널, 방사형 메뉴 아이콘, 멀티 해상도 .ico 생성기 (DEVELOPMENT_PLAN.md 4-11)."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from studypet.graphics.png_codec import encode_ico, encode_png_rgba


PALETTE_TXT = """# StudyPet default_pixel_cat 16색 이하 팔레트 (. = 투명)
. = transparent
K = #282328
B = #F5E6D3
S = #DEC6B0
W = #FFFDF9
P = #F29CB1
E = #362F3B
C = #F7838D
D = #A86B43
L = #754729
N = #6C7A89
M = #8CE0F5
Y = #FFD859
G = #7CD992
R = #F26D6D
Z = #99B4FF
"""


def parse_palette(text: str) -> dict[str, tuple[int, int, int, int]]:
    pal: dict[str, tuple[int, int, int, int]] = {".": (0, 0, 0, 0), " ": (0, 0, 0, 0)}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = [x.strip() for x in line.split("=", 1)]
        if v.lower() == "transparent":
            pal[k] = (0, 0, 0, 0)
        elif v.startswith("#") and len(v) == 7:
            r = int(v[1:3], 16)
            g = int(v[3:5], 16)
            b = int(v[5:7], 16)
            pal[k] = (r, g, b, 255)
    return pal


def make_empty_grid(w: int = 64, h: int = 64) -> list[list[str]]:
    return [["." for _ in range(w)] for _ in range(h)]


def grid_to_text(grid: list[list[str]]) -> str:
    return "\n".join("".join(row) for row in grid) + "\n"


def draw_ellipse(
    grid: list[list[str]],
    cx: int,
    cy: int,
    rx: int,
    ry: int,
    fill_ch: str,
    border_ch: str = "K",
) -> None:
    h = len(grid)
    w = len(grid[0])
    for y in range(max(0, cy - ry - 1), min(h, cy + ry + 2)):
        for x in range(max(0, cx - rx - 1), min(w, cx + rx + 2)):
            d = ((x - cx) / max(1, rx)) ** 2 + ((y - cy) / max(1, ry)) ** 2
            if d <= 1.0:
                d_in = ((x - cx) / max(0.5, rx - 1.2)) ** 2 + ((y - cy) / max(0.5, ry - 1.2)) ** 2
                grid[y][x] = border_ch if d_in > 1.0 else fill_ch


def draw_rect(
    grid: list[list[str]],
    x0: int,
    y0: int,
    w: int,
    h: int,
    fill_ch: str,
    border_ch: str | None = "K",
) -> None:
    for y in range(y0, y0 + h):
        for x in range(x0, x0 + w):
            if 0 <= y < len(grid) and 0 <= x < len(grid[0]):
                is_edge = x in (x0, x0 + w - 1) or y in (y0, y0 + h - 1)
                grid[y][x] = border_ch if (border_ch and is_edge) else fill_ch


def build_parts() -> dict[str, list[list[str]]]:
    """64x64 문자 격자 부품들을 생성한다."""
    parts: dict[str, list[list[str]]] = {}

    # 1. 기본 머리+귀+몸통 (body_base)
    g_body = make_empty_grid()
    # 양쪽 귀
    for dy in range(11):
        hw = dy // 2 + 1
        y = 14 + dy
        for lx in range(21 - hw, 21 + hw + 1):
            is_edge = lx in (21 - hw, 21 + hw) or dy == 0
            g_body[y][lx] = "K" if is_edge else ("P" if dy >= 3 and abs(lx - 21) <= hw - 2 else "B")
        for rx in range(42 - hw, 42 + hw + 1):
            is_edge = rx in (42 - hw, 42 + hw) or dy == 0
            g_body[y][rx] = "K" if is_edge else ("P" if dy >= 3 and abs(rx - 42) <= hw - 2 else "B")
    # 둥근 몸통+머리
    draw_ellipse(g_body, 32, 40, 17, 18, "B", "K")
    # 하얀 배 패치
    draw_ellipse(g_body, 32, 47, 9, 8, "W", "S")
    parts["body_base"] = g_body

    # 2. 납작 찌그러진 몸통 (body_squish — land 상태용)
    g_squish = make_empty_grid()
    for dy in range(10):
        hw = dy // 2 + 1
        y = 19 + dy
        for lx in range(20 - hw, 20 + hw + 1):
            g_squish[y][lx] = "K" if (lx in (20 - hw, 20 + hw) or dy == 0) else "B"
        for rx in range(43 - hw, 43 + hw + 1):
            g_squish[y][rx] = "K" if (rx in (43 - hw, 43 + hw) or dy == 0) else "B"
    draw_ellipse(g_squish, 32, 44, 20, 15, "B", "K")
    draw_ellipse(g_squish, 32, 49, 11, 6, "W", "S")
    parts["body_squish"] = g_squish

    # 3. 얼굴 표정 부품 (face_normal, face_blink, face_sleep, face_happy, face_focus)
    g_fn = make_empty_grid()
    for dy in range(3):
        for dx in range(2):
            g_fn[35 + dy][24 + dx] = "E"
            g_fn[35 + dy][38 + dx] = "E"
    for dx in range(3):
        g_fn[39][20 + dx] = "C"
        g_fn[39][41 + dx] = "C"
    g_fn[38][31] = "K"
    g_fn[39][32] = "K"
    g_fn[38][33] = "K"
    parts["face_normal"] = g_fn

    g_fb = make_empty_grid()
    for dx in range(3):
        g_fb[36][24 + dx] = "E"
        g_fb[36][37 + dx] = "E"
        g_fb[39][20 + dx] = "C"
        g_fb[39][41 + dx] = "C"
    g_fb[39][32] = "K"
    parts["face_blink"] = g_fb

    g_fh = make_empty_grid()
    # ^ ^ 웃는 눈
    g_fh[36][24] = "E"; g_fh[35][25] = "E"; g_fh[36][26] = "E"
    g_fh[36][37] = "E"; g_fh[35][38] = "E"; g_fh[36][39] = "E"
    for dx in range(3):
        g_fh[39][20 + dx] = "C"
        g_fh[39][41 + dx] = "C"
    g_fh[38][31] = "K"; g_fh[39][32] = "P"; g_fh[38][33] = "K"
    parts["face_happy"] = g_fh

    # 4. 다리 부품 (legs_stand, legs_walk_0..2, legs_sit, legs_dangle_0..1)
    def make_legs(l_off_x: int, l_off_y: int, r_off_x: int, r_off_y: int) -> list[list[str]]:
        g = make_empty_grid()
        draw_rect(g, 21 + l_off_x, 56 + l_off_y, 7, 7 - l_off_y, "B", "K")
        draw_rect(g, 36 + r_off_x, 56 + r_off_y, 7, 7 - r_off_y, "B", "K")
        return g

    parts["legs_stand"] = make_legs(0, 0, 0, 0)
    parts["legs_walk_a"] = make_legs(-2, -1, 2, 0)
    parts["legs_walk_b"] = make_legs(2, 0, -2, -1)
    parts["legs_dangle_a"] = make_legs(-1, 1, 1, 0)
    parts["legs_dangle_b"] = make_legs(1, 0, -1, 1)

    # 5. 꼬리 부품 (tail_left, tail_mid, tail_right)
    for t_name, bend in [("tail_a", -2), ("tail_b", 0), ("tail_c", 2)]:
        gt = make_empty_grid()
        for i in range(10):
            tx = 48 + (i // 2)
            ty = 48 - i + (bend if i > 5 else 0)
            draw_rect(gt, tx, ty, 4, 4, "S", "K")
        parts[t_name] = gt

    # 6. Zzz 수면 이펙트 (zzz_0, zzz_1)
    for z_idx, z_shift in enumerate((0, -2)):
        gz = make_empty_grid()
        zx, zy = 46, 18 + z_shift
        for dx in range(5):
            gz[zy][zx + dx] = "Z"
            gz[zy + 4][zx + dx] = "Z"
            gz[zy + 4 - (dx * 4) // 4][zx + dx] = "Z"
        parts[f"zzz_{z_idx}"] = gz

    # 7. 열공 책상 + 노트북/책 + 타이핑 앞발 (desk_study_a, desk_study_b)
    for s_idx, paw_shift in enumerate((0, 1)):
        gd = make_empty_grid()
        # 원목 책상 상판 (y=49..62, x=8..56)
        draw_rect(gd, 8, 50, 48, 6, "D", "K")
        draw_rect(gd, 11, 55, 5, 8, "L", "K")
        draw_rect(gd, 48, 55, 5, 8, "L", "K")
        # 노트북 화면 & 빛나는 모니터
        draw_rect(gd, 16, 40, 16, 11, "N", "K")
        draw_rect(gd, 18, 42, 12, 7, "M", None)
        # 펼쳐진 노트/책
        draw_rect(gd, 35, 46, 14, 5, "W", "K")
        # 타이핑하는 고양이 앞발
        draw_rect(gd, 34, 45 - paw_shift, 5, 4, "B", "K")
        draw_rect(gd, 42, 44 + paw_shift, 5, 4, "B", "K")
        parts[f"desk_study_{s_idx}"] = gd

    # 8. 축하 반짝이/별 이펙트 (stars_a, stars_b)
    for st_idx, offset in enumerate((0, 2)):
        gs = make_empty_grid()
        star_coords = [(10, 18 + offset), (52, 16 - offset), (12, 34 - offset), (54, 32 + offset)]
        for sx, sy in star_coords:
            gs[sy][sx] = "Y"
            gs[sy - 1][sx] = "Y"; gs[sy + 1][sx] = "Y"
            gs[sy][sx - 1] = "Y"; gs[sy][sx + 1] = "Y"
        parts[f"stars_{st_idx}"] = gs

    return parts


def build_frames_spec() -> dict[str, list[list[object]]]:
    """34개 프레임(meta.json의 0..33번 인덱스 순서)의 부품 조합 명세."""
    spec: dict[str, list[list[object]]] = {
        # idle (0..3)
        "frame_00_idle_0": [["tail_a", 0, 0], ["legs_stand", 0, 0], ["body_base", 0, 0], ["face_normal", 0, 0]],
        "frame_01_idle_1": [["tail_b", 0, 0], ["legs_stand", 0, 0], ["body_base", 0, 1], ["face_normal", 0, 1]],
        "frame_02_idle_2": [["tail_c", 0, 0], ["legs_stand", 0, 0], ["body_base", 0, 0], ["face_blink", 0, 0]],
        "frame_03_idle_3": [["tail_b", 0, 0], ["legs_stand", 0, 0], ["body_base", 0, 1], ["face_normal", 0, 1]],
        # walk (4..9)
        "frame_04_walk_0": [["tail_a", 0, 0], ["legs_walk_a", 0, 0], ["body_base", 0, 0], ["face_normal", 0, 0]],
        "frame_05_walk_1": [["tail_b", 0, 0], ["legs_stand", 0, 0], ["body_base", 0, -1], ["face_normal", 0, -1]],
        "frame_06_walk_2": [["tail_c", 0, 0], ["legs_walk_b", 0, 0], ["body_base", 0, 0], ["face_normal", 0, 0]],
        "frame_07_walk_3": [["tail_b", 0, 0], ["legs_stand", 0, 0], ["body_base", 0, -1], ["face_normal", 0, -1]],
        "frame_08_walk_4": [["tail_a", 0, 0], ["legs_walk_a", 0, 0], ["body_base", 0, 0], ["face_normal", 0, 0]],
        "frame_09_walk_5": [["tail_c", 0, 0], ["legs_walk_b", 0, 0], ["body_base", 0, 0], ["face_normal", 0, 0]],
        # sit (10..11)
        "frame_10_sit_0": [["tail_a", 0, 1], ["legs_stand", 0, 0], ["body_base", 0, 2], ["face_normal", 0, 2]],
        "frame_11_sit_1": [["tail_c", 0, 1], ["legs_stand", 0, 0], ["body_base", 0, 2], ["face_happy", 0, 2]],
        # sleep (12..15)
        "frame_12_sleep_0": [["tail_a", 0, 2], ["legs_stand", 0, 0], ["body_base", 0, 3], ["face_blink", 0, 3], ["zzz_0", 0, 0]],
        "frame_13_sleep_1": [["tail_a", 0, 2], ["legs_stand", 0, 0], ["body_base", 0, 4], ["face_blink", 0, 4], ["zzz_1", 0, 0]],
        "frame_14_sleep_2": [["tail_b", 0, 2], ["legs_stand", 0, 0], ["body_base", 0, 3], ["face_blink", 0, 3], ["zzz_0", 0, 0]],
        "frame_15_sleep_3": [["tail_b", 0, 2], ["legs_stand", 0, 0], ["body_base", 0, 4], ["face_blink", 0, 4], ["zzz_1", 0, 0]],
        # drag (16..17)
        "frame_16_drag_0": [["tail_a", 0, -2], ["legs_dangle_a", 0, 0], ["body_base", 0, -3], ["face_happy", 0, -3]],
        "frame_17_drag_1": [["tail_c", 0, -2], ["legs_dangle_b", 0, 0], ["body_base", 0, -2], ["face_normal", 0, -2]],
        # fall (18..19)
        "frame_18_fall_0": [["tail_a", 0, -3], ["legs_dangle_a", 0, -1], ["body_base", 0, -2], ["face_normal", 0, -2]],
        "frame_19_fall_1": [["tail_c", 0, -3], ["legs_dangle_b", 0, -1], ["body_base", 0, -1], ["face_normal", 0, -1]],
        # land (20..21)
        "frame_20_land_0": [["tail_b", 0, 3], ["legs_stand", 0, 0], ["body_squish", 0, 0], ["face_blink", 0, 4]],
        "frame_21_land_1": [["tail_b", 0, 1], ["legs_stand", 0, 0], ["body_base", 0, 1], ["face_normal", 0, 1]],
        # study (22..27)
        "frame_22_study_0": [["body_base", 0, 1], ["face_normal", 0, 1], ["desk_study_0", 0, 0]],
        "frame_23_study_1": [["body_base", 0, 1], ["face_normal", 0, 1], ["desk_study_1", 0, 0]],
        "frame_24_study_2": [["body_base", 0, 2], ["face_normal", 0, 2], ["desk_study_0", 0, 0]],
        "frame_25_study_3": [["body_base", 0, 2], ["face_blink", 0, 2], ["desk_study_1", 0, 0]],
        "frame_26_study_4": [["body_base", 0, 1], ["face_normal", 0, 1], ["desk_study_0", 0, 0]],
        "frame_27_study_5": [["body_base", 0, 1], ["face_happy", 0, 1], ["desk_study_1", 0, 0]],
        # celebrate (28..33)
        "frame_28_celeb_0": [["tail_a", 0, -2], ["legs_walk_a", 0, -2], ["body_base", 0, -3], ["face_happy", 0, -3], ["stars_0", 0, 0]],
        "frame_29_celeb_1": [["tail_c", 0, -4], ["legs_walk_b", 0, -4], ["body_base", 0, -5], ["face_happy", 0, -5], ["stars_1", 0, 0]],
        "frame_30_celeb_2": [["tail_a", 0, -2], ["legs_stand", 0, 0], ["body_base", 0, -1], ["face_happy", 0, -1], ["stars_0", 0, 0]],
        "frame_31_celeb_3": [["tail_c", 0, -4], ["legs_walk_a", 0, -3], ["body_base", 0, -4], ["face_happy", 0, -4], ["stars_1", 0, 0]],
        "frame_32_celeb_4": [["tail_b", 0, -1], ["legs_stand", 0, 0], ["body_base", 0, -2], ["face_happy", 0, -2], ["stars_0", 0, 0]],
        "frame_33_celeb_5": [["tail_b", 0, 0], ["legs_stand", 0, 0], ["body_base", 0, 0], ["face_happy", 0, 0], ["stars_1", 0, 0]],
    }
    return spec


META_JSON = {
    "frame_w": 64,
    "frame_h": 64,
    "anchor": [32, 63],
    "states": {
        "idle": {"frames": [0, 1, 2, 3], "fps": 4, "loop": True},
        "walk": {"frames": [4, 5, 6, 7, 8, 9], "fps": 8, "loop": True},
        "sit": {"frames": [10, 11], "fps": 2, "loop": True},
        "sleep": {"frames": [12, 13, 14, 15], "fps": 2, "loop": True},
        "drag": {"frames": [16, 17], "fps": 6, "loop": True},
        "fall": {"frames": [18, 19], "fps": 8, "loop": True},
        "land": {"frames": [20, 21], "fps": 8, "loop": False},
        "study": {"frames": [22, 23, 24, 25, 26, 27], "fps": 6, "loop": True},
        "celebrate": {"frames": [28, 29, 30, 31, 32, 33], "fps": 6, "loop": False},
    },
}


def compose_frame_rgba(
    layer_list: list[list[object]],
    parts: dict[str, list[list[str]]],
    palette: dict[str, tuple[int, int, int, int]],
) -> bytes:
    buf = bytearray(64 * 64 * 4)
    for item in layer_list:
        part_name = str(item[0])
        dx = int(item[1])  # type: ignore[arg-type]
        dy = int(item[2])  # type: ignore[arg-type]
        grid = parts[part_name]
        for y in range(64):
            ty = y + dy
            if not (0 <= ty < 64):
                continue
            row = grid[y]
            for x in range(64):
                ch = row[x]
                if ch in (".", " "):
                    continue
                tx = x + dx
                if not (0 <= tx < 64):
                    continue
                rgba = palette[ch]
                if rgba[3] == 255:
                    idx = (ty * 64 + tx) * 4
                    buf[idx : idx + 4] = bytes(rgba)
    return bytes(buf)


def generate_ui_panel_png() -> bytes:
    """12x12 9-slice 도트 패널 (모서리 4sp, 알파 0/255)."""
    w, h = 12, 12
    buf = bytearray(w * h * 4)
    c_border = bytes([38, 35, 52, 255])
    c_highlight = bytes([75, 70, 102, 255])
    c_fill = bytes([28, 27, 41, 255])

    for y in range(h):
        for x in range(w):
            # 네 꼭짓점 1픽셀씩 투명 처리하여 도트 라운드 코너 구현
            if (x in (0, w - 1)) and (y in (0, h - 1)):
                continue
            is_outer = (
                x in (0, w - 1)
                or y in (0, h - 1)
                or (x in (1, w - 2) and y in (1, h - 2))
            )
            is_inner_rim = x in (1, w - 2) or y in (1, h - 2)
            idx = (y * w + x) * 4
            if is_outer:
                buf[idx : idx + 4] = c_border
            elif is_inner_rim:
                buf[idx : idx + 4] = c_highlight
            else:
                buf[idx : idx + 4] = c_fill

    return encode_png_rgba(w, h, bytes(buf), strict_alpha=True)


def generate_menu_icon_png(kind: str, hover: bool = False) -> bytes:
    """16x16 방사형 메뉴 도트 아이콘 (start, pause, subjects, settings, stats)."""
    w, h = 16, 16
    buf = bytearray(w * h * 4)
    bg_map = {
        "start": (76, 195, 125) if not hover else (110, 225, 155),
        "pause": (240, 175, 75) if not hover else (255, 205, 110),
        "subjects": (95, 145, 245) if not hover else (130, 175, 255),
        "settings": (175, 125, 235) if not hover else (205, 160, 255),
        "stats": (240, 115, 145) if not hover else (255, 150, 175),
    }
    r, g, b = bg_map[kind]
    c_bg = bytes([r, g, b, 255])
    c_border = bytes([30, 28, 42, 255])
    c_fg = bytes([255, 253, 249, 255])

    for y in range(h):
        for x in range(w):
            d2 = (x - 7.5) ** 2 + (y - 7.5) ** 2
            if d2 <= 54:
                idx = (y * w + x) * 4
                buf[idx : idx + 4] = c_border if d2 >= 38 else c_bg

    def put_fg(px: int, py: int) -> None:
        if 0 <= px < 16 and 0 <= py < 16:
            idx = (py * 16 + px) * 4
            buf[idx : idx + 4] = c_fg

    if kind == "start":  # ▶ 삼각형
        for dy in range(-3, 4):
            span = 4 - abs(dy)
            for dx in range(span):
                put_fg(6 + dx, 8 + dy)
    elif kind == "pause":  # ❚❚ 막대 2개
        for py in range(5, 11):
            for px in (5, 6, 9, 10):
                put_fg(px, py)
    elif kind == "subjects":  # ☰ 목록
        for py in (5, 8, 11):
            for px in range(5, 12):
                put_fg(px, py)
    elif kind == "settings":  # ⚙ 십자+중앙 기어
        for py in range(5, 11):
            for px in range(5, 11):
                if (px in (7, 8) or py in (7, 8)) and not (px in (7, 8) and py in (7, 8)):
                    put_fg(px, py)
    elif kind == "stats":  # 📊 막대 차트
        for py in range(9, 12):
            put_fg(5, py); put_fg(6, py)
        for py in range(5, 12):
            put_fg(8, py); put_fg(9, py)
        for py in range(7, 12):
            put_fg(11, py)

    return encode_png_rgba(w, h, bytes(buf), strict_alpha=True)


def scale_rgba_nearest(rgba: bytes, src_w: int, src_h: int, dst_w: int, dst_h: int) -> bytes:
    out = bytearray(dst_w * dst_h * 4)
    for y in range(dst_h):
        sy = (y * src_h) // dst_h
        for x in range(dst_w):
            sx = (x * src_w) // dst_w
            si = (sy * src_w + sx) * 4
            di = (y * dst_w + x) * 4
            out[di : di + 4] = rgba[si : si + 4]
    return bytes(out)


def main() -> int:
    art_dir = ROOT / "art" / "default_pixel_cat"
    parts_dir = art_dir / "parts"
    parts_dir.mkdir(parents=True, exist_ok=True)

    # 1. art/ 원본 파일 기록
    (art_dir / "palette.txt").write_text(PALETTE_TXT, encoding="utf-8")
    parts = build_parts()
    for p_name, grid in parts.items():
        (parts_dir / f"{p_name}.txt").write_text(grid_to_text(grid), encoding="utf-8")

    frames_spec = build_frames_spec()
    (art_dir / "frames.json").write_text(json.dumps(frames_spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # 2. sheet.png (34 프레임 가로 연결: 2176 x 64) 및 meta.json 생성
    palette = parse_palette(PALETTE_TXT)
    ordered_keys = sorted(frames_spec.keys())
    frame_rgbas = [compose_frame_rgba(frames_spec[k], parts, palette) for k in ordered_keys]

    num_frames = len(frame_rgbas)
    sheet_w = 64 * num_frames
    sheet_h = 64
    sheet_buf = bytearray(sheet_w * sheet_h * 4)
    for f_idx, f_rgba in enumerate(frame_rgbas):
        for y in range(64):
            src_off = y * 64 * 4
            dst_off = (y * sheet_w + f_idx * 64) * 4
            sheet_buf[dst_off : dst_off + 64 * 4] = f_rgba[src_off : src_off + 64 * 4]

    skin_dir = ROOT / "assets" / "skins" / "default_pixel_cat"
    skin_dir.mkdir(parents=True, exist_ok=True)
    (skin_dir / "sheet.png").write_bytes(encode_png_rgba(sheet_w, sheet_h, bytes(sheet_buf), strict_alpha=True))
    (skin_dir / "meta.json").write_text(json.dumps(META_JSON, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # 3. UI 에셋 생성 (assets/ui/)
    ui_dir = ROOT / "assets" / "ui"
    ui_dir.mkdir(parents=True, exist_ok=True)
    (ui_dir / "panel.png").write_bytes(generate_ui_panel_png())
    for kind in ("start", "pause", "subjects", "settings", "stats"):
        (ui_dir / f"menu_{kind}.png").write_bytes(generate_menu_icon_png(kind, hover=False))
        (ui_dir / f"menu_{kind}_hover.png").write_bytes(generate_menu_icon_png(kind, hover=True))

    # 4. 아이콘 생성 (assets/icons/studypet.ico — 16, 32, 48 BMP + 256 PNG)
    icons_dir = ROOT / "assets" / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)
    base_icon_rgba = frame_rgbas[0]  # idle_0 프레임 기반
    ico_entries = [
        (sz, sz, scale_rgba_nearest(base_icon_rgba, 64, 64, sz, sz))
        for sz in (16, 32, 48, 256)
    ]
    (icons_dir / "studypet.ico").write_bytes(encode_ico(ico_entries))

    print(f"[gen_sprites] 생성 완료: {num_frames} 프레임 ({sheet_w}x{sheet_h}), UI 아이콘 및 studypet.ico")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
