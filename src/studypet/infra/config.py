"""설정 파일(config.json) 로드, 깊은 병합, 검증, 백업 및 원자적 저장 (DEVELOPMENT_PLAN.md 4-6)."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
import json
import logging
import os
from pathlib import Path
import re
import shutil
from typing import Any


logger = logging.getLogger("studypet.config")

_HOTKEY_MODS = {"CTRL", "CONTROL", "ALT", "SHIFT"}
_HOTKEY_KEY_RE = re.compile(r"^([A-Z0-9]|F([1-9]|1[0-2]))$")


def is_valid_hotkey_str(s: str) -> bool:
    """'Ctrl+Alt+G' 등 유효한 단축키 문자열 형식인지 검사한다 (4-13)."""
    if not isinstance(s, str) or not s.strip():
        return False
    parts = [p.strip().upper() for p in s.split("+") if p.strip()]
    if len(parts) < 2:
        return False
    mods, key = parts[:-1], parts[-1]
    if not all(m in _HOTKEY_MODS for m in mods):
        return False
    return bool(_HOTKEY_KEY_RE.match(key))


@dataclass
class PointPos:
    x: int
    y: int

    def to_dict(self) -> dict[str, int]:
        return {"x": int(self.x), "y": int(self.y)}


@dataclass
class CharacterConfig:
    skin_id: str = "default_pixel_cat"
    scale: int = 2
    opacity: float = 1.0
    last_position: PointPos | None = None
    walk_enabled: bool = True


@dataclass
class TimerConfig:
    default_mode: str = "POMODORO"
    pomodoro_focus_min: int = 25
    pomodoro_break_min: int = 5
    afk_timeout_min: int = 10
    sound_alert: bool = True
    last_subject_id: int | None = None


@dataclass
class AudioConfig:
    volume: float = 0.7


@dataclass
class RenderConfig:
    fps: int = 30


@dataclass
class HudConfig:
    bubble_collapsed: bool = False
    hint_shown: bool = False


@dataclass(frozen=True)
class SettingsPatch:
    """설정 탭에서 편집하는 필드만 담는 패치 객체 (M1: last_position·last_subject_id·bubble_collapsed 보존)."""

    default_mode: str
    pomodoro_focus_min: int
    pomodoro_break_min: int
    afk_timeout_min: int
    sound_alert: bool
    scale: int
    walk_enabled: bool
    fps: int
    volume: float
    toggle_ghost: str

    def apply_to(self, cfg: AppConfig) -> AppConfig:
        return replace(
            cfg,
            character=replace(
                cfg.character,
                scale=int(self.scale),
                walk_enabled=bool(self.walk_enabled),
            ),
            timer=replace(
                cfg.timer,
                default_mode=str(self.default_mode),
                pomodoro_focus_min=int(self.pomodoro_focus_min),
                pomodoro_break_min=int(self.pomodoro_break_min),
                afk_timeout_min=int(self.afk_timeout_min),
                sound_alert=bool(self.sound_alert),
            ),
            audio=replace(
                cfg.audio,
                volume=round(float(self.volume), 4),
            ),
            render=replace(
                cfg.render,
                fps=int(self.fps),
            ),
            shortcuts=replace(
                cfg.shortcuts,
                toggle_ghost=str(self.toggle_ghost),
            ),
        )


@dataclass
class ShortcutsConfig:
    toggle_ghost: str = "Ctrl+Alt+G"


@dataclass
class AppConfig:
    version: int = 1
    character: CharacterConfig = field(default_factory=CharacterConfig)
    timer: TimerConfig = field(default_factory=TimerConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    render: RenderConfig = field(default_factory=RenderConfig)
    hud: HudConfig = field(default_factory=HudConfig)
    shortcuts: ShortcutsConfig = field(default_factory=ShortcutsConfig)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": int(self.version),
            "character": {
                "skin_id": self.character.skin_id,
                "scale": int(self.character.scale),
                "opacity": float(self.character.opacity),
                "last_position": (
                    self.character.last_position.to_dict()
                    if self.character.last_position is not None
                    else None
                ),
                "walk_enabled": bool(self.character.walk_enabled),
            },
            "timer": {
                "default_mode": self.timer.default_mode,
                "pomodoro_focus_min": int(self.timer.pomodoro_focus_min),
                "pomodoro_break_min": int(self.timer.pomodoro_break_min),
                "afk_timeout_min": int(self.timer.afk_timeout_min),
                "sound_alert": bool(self.timer.sound_alert),
                "last_subject_id": self.timer.last_subject_id,
            },
            "audio": {
                "volume": float(self.audio.volume),
            },
            "render": {
                "fps": int(self.render.fps),
            },
            "hud": {
                "bubble_collapsed": bool(self.hud.bubble_collapsed),
                "hint_shown": bool(self.hud.hint_shown),
            },
            "shortcuts": {
                "toggle_ghost": self.shortcuts.toggle_ghost,
            },
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | Any) -> "AppConfig":
        """기본값과 깊은 병합하고 필드별 타입·범위를 검증한다 (범위 밖이면 기본값 대체 후 로그)."""
        cfg = cls()
        if not isinstance(raw, dict):
            logger.warning("config root is not a dict; using defaults")
            return cfg

        # character
        c_raw = raw.get("character")
        if isinstance(c_raw, dict):
            skin = c_raw.get("skin_id")
            if isinstance(skin, str) and skin.strip():
                cfg.character.skin_id = skin.strip()
            elif "skin_id" in c_raw:
                logger.warning("Invalid character.skin_id: %r", skin)

            scale_val = c_raw.get("scale")
            if isinstance(scale_val, (int, float)) and not isinstance(scale_val, bool):
                norm_scale = int(scale_val + 0.5) if scale_val >= 0 else -1
                if 1 <= norm_scale <= 4:
                    cfg.character.scale = norm_scale
                else:
                    logger.warning("character.scale out of range (1..4): %r", scale_val)
            elif "scale" in c_raw:
                logger.warning("Invalid character.scale type: %r", scale_val)

            op_val = c_raw.get("opacity")
            if isinstance(op_val, (int, float)) and not isinstance(op_val, bool):
                op_f = float(op_val)
                if 0.3 <= op_f <= 1.0:
                    cfg.character.opacity = round(op_f, 4)
                else:
                    logger.warning("character.opacity out of range (0.3..1.0): %r", op_val)
            elif "opacity" in c_raw:
                logger.warning("Invalid character.opacity type: %r", op_val)

            pos_val = c_raw.get("last_position")
            if pos_val is None:
                cfg.character.last_position = None
            elif isinstance(pos_val, dict):
                px = pos_val.get("x")
                py = pos_val.get("y")
                if (
                    isinstance(px, (int, float))
                    and not isinstance(px, bool)
                    and isinstance(py, (int, float))
                    and not isinstance(py, bool)
                ):
                    cfg.character.last_position = PointPos(int(round(px)), int(round(py)))
                else:
                    logger.warning("Invalid character.last_position coordinates: %r", pos_val)
            else:
                logger.warning("Invalid character.last_position: %r", pos_val)

            walk_val = c_raw.get("walk_enabled")
            if isinstance(walk_val, bool):
                cfg.character.walk_enabled = walk_val
            elif "walk_enabled" in c_raw:
                logger.warning("Invalid character.walk_enabled: %r", walk_val)

        # timer
        t_raw = raw.get("timer")
        if isinstance(t_raw, dict):
            mode_val = t_raw.get("default_mode")
            if mode_val in ("STOPWATCH", "POMODORO"):
                cfg.timer.default_mode = mode_val
            elif "default_mode" in t_raw:
                logger.warning("Invalid timer.default_mode: %r", mode_val)

            focus_val = t_raw.get("pomodoro_focus_min")
            if isinstance(focus_val, int) and not isinstance(focus_val, bool) and 1 <= focus_val <= 180:
                cfg.timer.pomodoro_focus_min = focus_val
            elif "pomodoro_focus_min" in t_raw:
                logger.warning("Invalid timer.pomodoro_focus_min (1..180): %r", focus_val)

            break_val = t_raw.get("pomodoro_break_min")
            if isinstance(break_val, int) and not isinstance(break_val, bool) and 1 <= break_val <= 60:
                cfg.timer.pomodoro_break_min = break_val
            elif "pomodoro_break_min" in t_raw:
                logger.warning("Invalid timer.pomodoro_break_min (1..60): %r", break_val)

            afk_val = t_raw.get("afk_timeout_min")
            if isinstance(afk_val, int) and not isinstance(afk_val, bool) and 1 <= afk_val <= 120:
                cfg.timer.afk_timeout_min = afk_val
            elif "afk_timeout_min" in t_raw:
                logger.warning("Invalid timer.afk_timeout_min (1..120): %r", afk_val)

            snd_val = t_raw.get("sound_alert")
            if isinstance(snd_val, bool):
                cfg.timer.sound_alert = snd_val
            elif "sound_alert" in t_raw:
                logger.warning("Invalid timer.sound_alert: %r", snd_val)

            sub_val = t_raw.get("last_subject_id")
            if sub_val is None:
                cfg.timer.last_subject_id = None
            elif isinstance(sub_val, int) and not isinstance(sub_val, bool) and sub_val > 0:
                cfg.timer.last_subject_id = sub_val
            else:
                logger.warning("Invalid timer.last_subject_id: %r", sub_val)

        # audio
        a_raw = raw.get("audio")
        if isinstance(a_raw, dict):
            vol_val = a_raw.get("volume")
            if isinstance(vol_val, (int, float)) and not isinstance(vol_val, bool):
                vol_f = float(vol_val)
                if 0.0 <= vol_f <= 1.0:
                    cfg.audio.volume = round(vol_f, 4)
                else:
                    logger.warning("audio.volume out of range (0.0..1.0): %r", vol_val)
            elif "volume" in a_raw:
                logger.warning("Invalid audio.volume: %r", vol_val)

        # render
        r_raw = raw.get("render")
        if isinstance(r_raw, dict):
            fps_val = r_raw.get("fps")
            if isinstance(fps_val, int) and not isinstance(fps_val, bool) and fps_val in (30, 60):
                cfg.render.fps = fps_val
            elif "fps" in r_raw:
                logger.warning("Invalid render.fps (30 or 60): %r", fps_val)

        # hud
        h_raw = raw.get("hud")
        if isinstance(h_raw, dict):
            col_val = h_raw.get("bubble_collapsed")
            if isinstance(col_val, bool):
                cfg.hud.bubble_collapsed = col_val
            elif "bubble_collapsed" in h_raw:
                logger.warning("Invalid hud.bubble_collapsed: %r", col_val)

            hint_val = h_raw.get("hint_shown")
            if isinstance(hint_val, bool):
                cfg.hud.hint_shown = hint_val
            elif "hint_shown" in h_raw:
                logger.warning("Invalid hud.hint_shown: %r", hint_val)

        # shortcuts
        s_raw = raw.get("shortcuts")
        if isinstance(s_raw, dict):
            ghost_key = s_raw.get("toggle_ghost")
            if isinstance(ghost_key, str) and is_valid_hotkey_str(ghost_key):
                cfg.shortcuts.toggle_ghost = ghost_key.strip()
            elif "toggle_ghost" in s_raw:
                logger.warning("Invalid shortcuts.toggle_ghost: %r", ghost_key)

        return cfg

    def save(self, path: Path) -> None:
        """config.json.tmp 에 쓰고 flush + fsync 후 os.replace로 원자적 저장한다."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(path.name + ".tmp")
        text = json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n"
        with tmp_path.open("w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)

    @classmethod
    def load(cls, path: Path) -> "AppConfig":
        """config.json을 로드한다. 파일이 없으면 기본값을 생성·저장하고, 깨진 JSON이면 .bak 백업 후 기본값으로 재생성한다."""
        if not path.exists():
            cfg = cls()
            cfg.save(path)
            return cfg

        try:
            raw_text = path.read_text(encoding="utf-8")
            parsed = json.loads(raw_text)
            if not isinstance(parsed, dict):
                raise ValueError("Root JSON element must be an object")
        except Exception as exc:
            bak_path = path.with_name(path.name + ".bak")
            try:
                shutil.copyfile(path, bak_path)
            except OSError:
                pass
            logger.warning("Corrupted config.json backed up to %s (%s); resetting to defaults", bak_path, exc)
            cfg = cls()
            cfg.save(path)
            return cfg

        cfg = cls.from_dict(parsed)
        return cfg

