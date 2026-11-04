"""infra/config.py 단위 테스트 (DEVELOPMENT_PLAN.md 7-1)."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from studypet.infra.config import AppConfig, PointPos, SettingsPatch


class TestAppConfig(unittest.TestCase):
    def test_default_creation_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "data" / "config.json"
            cfg = AppConfig.load(cfg_path)
            self.assertTrue(cfg_path.exists())
            self.assertEqual(cfg.version, 1)
            self.assertEqual(cfg.character.skin_id, "default_pixel_cat")
            self.assertEqual(cfg.character.scale, 2)
            self.assertAlmostEqual(cfg.character.opacity, 1.0)
            self.assertIsNone(cfg.character.last_position)
            self.assertTrue(cfg.character.walk_enabled)
            self.assertEqual(cfg.timer.default_mode, "POMODORO")
            self.assertEqual(cfg.timer.pomodoro_focus_min, 25)
            self.assertEqual(cfg.timer.pomodoro_break_min, 5)
            self.assertEqual(cfg.timer.afk_timeout_min, 10)
            self.assertTrue(cfg.timer.sound_alert)
            self.assertIsNone(cfg.timer.last_subject_id)
            self.assertAlmostEqual(cfg.audio.volume, 0.7)
            self.assertEqual(cfg.render.fps, 30)
            self.assertFalse(cfg.hud.bubble_collapsed)
            self.assertEqual(cfg.shortcuts.toggle_ghost, "Ctrl+Alt+G")

    def test_partial_merge_and_float_scale_normalization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.json"
            # PRD 6-3 형식 (scale: 2.0 실수, audio/render/hud/shortcuts 누락)
            raw = {
                "character": {
                    "skin_id": "default_pixel_cat",
                    "scale": 2.0,
                    "opacity": 0.8,
                    "last_position": {"x": 1650, "y": 920},
                    "walk_enabled": False,
                },
                "timer": {
                    "default_mode": "STOPWATCH",
                    "pomodoro_focus_min": 50,
                },
            }
            cfg_path.write_text(json.dumps(raw), encoding="utf-8")

            cfg = AppConfig.load(cfg_path)
            self.assertIsInstance(cfg.character.scale, int)
            self.assertEqual(cfg.character.scale, 2)
            self.assertAlmostEqual(cfg.character.opacity, 0.8)
            self.assertEqual(cfg.character.last_position, PointPos(1650, 920))
            self.assertFalse(cfg.character.walk_enabled)
            self.assertEqual(cfg.timer.default_mode, "STOPWATCH")
            self.assertEqual(cfg.timer.pomodoro_focus_min, 50)
            # 누락된 필드는 기본값 유지
            self.assertEqual(cfg.timer.pomodoro_break_min, 5)
            self.assertAlmostEqual(cfg.audio.volume, 0.7)
            self.assertEqual(cfg.render.fps, 30)
            self.assertEqual(cfg.shortcuts.toggle_ghost, "Ctrl+Alt+G")

    def test_out_of_range_values_fallback_to_defaults(self) -> None:
        raw = {
            "character": {
                "skin_id": "   ",
                "scale": 9,
                "opacity": 0.05,
                "last_position": {"x": "bad", "y": 10},
                "walk_enabled": "yes",
            },
            "timer": {
                "default_mode": "INVALID_MODE",
                "pomodoro_focus_min": 0,
                "pomodoro_break_min": 99,
                "afk_timeout_min": -5,
                "last_subject_id": -1,
            },
            "audio": {"volume": 1.5},
            "render": {"fps": 120},
            "shortcuts": {"toggle_ghost": "InvalidShortcut"},
        }
        cfg = AppConfig.from_dict(raw)
        self.assertEqual(cfg.character.skin_id, "default_pixel_cat")
        self.assertEqual(cfg.character.scale, 2)
        self.assertAlmostEqual(cfg.character.opacity, 1.0)
        self.assertIsNone(cfg.character.last_position)
        self.assertTrue(cfg.character.walk_enabled)
        self.assertEqual(cfg.timer.default_mode, "POMODORO")
        self.assertEqual(cfg.timer.pomodoro_focus_min, 25)
        self.assertEqual(cfg.timer.pomodoro_break_min, 5)
        self.assertEqual(cfg.timer.afk_timeout_min, 10)
        self.assertIsNone(cfg.timer.last_subject_id)
        self.assertAlmostEqual(cfg.audio.volume, 0.7)
        self.assertEqual(cfg.render.fps, 30)
        self.assertEqual(cfg.shortcuts.toggle_ghost, "Ctrl+Alt+G")

    def test_corrupted_json_creates_bak_and_resets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.json"
            corrupted_content = "{ broken json: 123"
            cfg_path.write_text(corrupted_content, encoding="utf-8")

            cfg = AppConfig.load(cfg_path)
            bak_path = Path(tmp) / "config.json.bak"
            self.assertTrue(bak_path.exists())
            self.assertEqual(bak_path.read_text(encoding="utf-8"), corrupted_content)
            self.assertEqual(cfg.character.scale, 2)
            # 새로 저장된 config.json은 정상 파싱 가능해야 함
            reloaded_json = json.loads(cfg_path.read_text(encoding="utf-8"))
            self.assertEqual(reloaded_json["version"], 1)

    def test_atomic_save_and_reload_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.json"
            cfg = AppConfig()
            cfg.character.scale = 3
            cfg.character.last_position = PointPos(800, 1000)
            cfg.timer.last_subject_id = 4
            cfg.render.fps = 60
            cfg.shortcuts.toggle_ghost = "Ctrl+Shift+F12"
            cfg.save(cfg_path)

            self.assertFalse(cfg_path.with_name("config.json.tmp").exists())
            loaded = AppConfig.load(cfg_path)
            self.assertEqual(loaded.to_dict(), cfg.to_dict())

    def test_hint_shown_default_and_validation(self) -> None:
        cfg_default = AppConfig()
        self.assertFalse(cfg_default.hud.hint_shown)

        cfg_true = AppConfig.from_dict({"hud": {"bubble_collapsed": True, "hint_shown": True}})
        self.assertTrue(cfg_true.hud.bubble_collapsed)
        self.assertTrue(cfg_true.hud.hint_shown)

        cfg_invalid = AppConfig.from_dict({"hud": {"hint_shown": "not_a_bool"}})
        self.assertFalse(cfg_invalid.hud.hint_shown)

    def test_settings_patch_preserves_position_subject_and_hud_state(self) -> None:
        cfg = AppConfig()
        cfg.character.last_position = PointPos(1420, 880)
        cfg.timer.last_subject_id = 7
        cfg.hud.bubble_collapsed = True
        cfg.hud.hint_shown = True

        patch = SettingsPatch(
            scale=3,
            walk_enabled=False,
            default_mode="STOPWATCH",
            pomodoro_focus_min=45,
            pomodoro_break_min=10,
            afk_timeout_min=15,
            sound_alert=False,
            volume=0.5,
            fps=60,
            toggle_ghost="Ctrl+Shift+G",
        )
        updated = patch.apply_to(cfg)

        self.assertEqual(updated.character.scale, 3)
        self.assertFalse(updated.character.walk_enabled)
        self.assertEqual(updated.timer.default_mode, "STOPWATCH")
        self.assertEqual(updated.timer.pomodoro_focus_min, 45)
        self.assertEqual(updated.render.fps, 60)
        self.assertEqual(updated.shortcuts.toggle_ghost, "Ctrl+Shift+G")
        # 설정 탭 외의 런타임 상태(위치, 과목, 말풍선 축소, 힌트 완료)는 그대로 보존되어야 함 (v0.7 M1)
        self.assertEqual(updated.character.last_position, PointPos(1420, 880))
        self.assertEqual(updated.timer.last_subject_id, 7)
        self.assertTrue(updated.hud.bubble_collapsed)
        self.assertTrue(updated.hud.hint_shown)


if __name__ == "__main__":
    unittest.main()

