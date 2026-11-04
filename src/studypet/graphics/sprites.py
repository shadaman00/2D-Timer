"""스프라이트 시트 로드 및 상태별 사전 스케일 프레임 캐시 (DEVELOPMENT_PLAN.md 4-11)."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from studypet.graphics.png_codec import decode_png_rgba, rgba_to_premultiplied_bgra


def scale_frame(src_bgra: bytes, w: int, h: int, s: int, flip: bool = False) -> bytes:
    """로드 시 1회 실행하는 최근접 이웃(Nearest-Neighbor) 정수 배율 스케일 함수 (4-11)."""
    if s <= 0:
        raise ValueError(f"Scale must be >= 1, got {s}")
    rows = []
    for y in range(h):
        row = src_bgra[y * w * 4 : (y + 1) * w * 4]
        px = [row[i : i + 4] for i in range(0, w * 4, 4)]
        if flip:
            px.reverse()
        srow = b"".join(p * s for p in px)
        rows.append(srow * s)
    return b"".join(rows)


@dataclass(frozen=True)
class StateAnimMeta:
    name: str
    frames: tuple[int, ...]
    fps: int
    loop: bool


class SpriteSheet:
    """sheet.png + meta.json을 로드하고 (state, frame_idx, phys_scale, flip)별로 지연 스케일 캐싱한다."""

    def __init__(self, sheet_png_path: Path, meta_json_path: Path, initial_scale: int = 2) -> None:
        meta_raw = json.loads(meta_json_path.read_text(encoding="utf-8"))
        self.frame_w: int = int(meta_raw.get("frame_w", 64))
        self.frame_h: int = int(meta_raw.get("frame_h", 64))
        anc = meta_raw.get("anchor", [32, 63])
        self.anchor: tuple[int, int] = (int(anc[0]), int(anc[1]))

        self.states: dict[str, StateAnimMeta] = {}
        for s_name, s_info in meta_raw.get("states", {}).items():
            self.states[s_name] = StateAnimMeta(
                name=s_name,
                frames=tuple(int(i) for i in s_info["frames"]),
                fps=max(1, int(s_info.get("fps", 4))),
                loop=bool(s_info.get("loop", True)),
            )

        sheet_w, sheet_h, rgba = decode_png_rgba(sheet_png_path.read_bytes())
        if sheet_h != self.frame_h or sheet_w % self.frame_w != 0:
            raise ValueError(
                f"Invalid sprite sheet size {sheet_w}x{sheet_h} for frame {self.frame_w}x{self.frame_h}"
            )
        bgra_sheet = rgba_to_premultiplied_bgra(rgba)
        num_frames = sheet_w // self.frame_w
        self._raw_frames: list[bytes] = []
        sheet_stride = sheet_w * 4
        frame_stride = self.frame_w * 4
        for f_idx in range(num_frames):
            f_rows = []
            x_off = f_idx * frame_stride
            for y in range(self.frame_h):
                row_start = y * sheet_stride + x_off
                f_rows.append(bgra_sheet[row_start : row_start + frame_stride])
            self._raw_frames.append(b"".join(f_rows))

        self._scale: int = max(1, int(initial_scale))
        self._cache: dict[tuple[int, int, bool], bytes] = {}
        # 기동 시에는 idle 프레임만 사전 스케일하여 Cold Start를 단축한다 (3-3 #7)
        self.warm_state("idle", self._scale)

    def warm_state(self, state_name: str, scale: int) -> None:
        meta = self.states.get(state_name)
        if meta is None:
            return
        for raw_idx in meta.frames:
            for flip in (False, True):
                self._get_scaled_raw(raw_idx, scale, flip)

    def set_scale(self, new_scale: int) -> None:
        s = max(1, int(new_scale))
        if s != self._scale:
            self._scale = s
            self._cache.clear()
            self.warm_state("idle", s)

    def _get_scaled_raw(self, raw_frame_idx: int, scale: int, flip: bool) -> bytes:
        key = (raw_frame_idx, scale, flip)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        raw = self._raw_frames[raw_frame_idx % len(self._raw_frames)]
        scaled = scale_frame(raw, self.frame_w, self.frame_h, scale, flip)
        self._cache[key] = scaled
        return scaled

    def get_frame(self, state_name: str, step_idx: int, scale: int, flip: bool = False) -> bytes:
        meta = self.states.get(state_name) or self.states["idle"]
        if meta.loop:
            idx_in_state = step_idx % len(meta.frames)
        else:
            idx_in_state = min(max(0, step_idx), len(meta.frames) - 1)
        raw_idx = meta.frames[idx_in_state]
        return self._get_scaled_raw(raw_idx, scale, flip)

    def state_meta(self, state_name: str) -> StateAnimMeta:
        return self.states.get(state_name) or self.states["idle"]

