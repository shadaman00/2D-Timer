"""펫 캔버스 좌표 변환, 액션 카드 레이아웃·버튼·히트 판정, 말풍선 클램핑 테스트 (REVISION_PLAN_v0.7 5장)."""
from __future__ import annotations

import unittest

from studypet.domain.events import Mode as TimerMode, Phase as PomodoroPhase, TimerState
from studypet.ui.layout import (
    BUBBLE_MAX_W_SP,
    BUBBLE_MIN_W_SP,
    CARD_BOX_SP,
    CHARACTER_BOX_SP,
    card_buttons,
    card_header,
    compute_bubble_box_sp,
    hit_test_card,
    px_to_sp,
    sp_to_px,
    window_top_left_from_foot,
)


class TestLayout(unittest.TestCase):
    def test_sp_px_conversion_and_foot_anchor_across_scales_1_to_4(self) -> None:
        self.assertEqual(sp_to_px(96, 144, 3), (288, 432))
        self.assertEqual(px_to_sp(289, 433, 3), (96, 144))
        self.assertEqual(window_top_left_from_foot(1000, 900, 2), (1000 - 192, 900 - 288))

        for s in (1, 2, 3, 4):
            # CARD_BOX_SP (8, 0, 176, 78) 경계 테스트
            self.assertEqual(px_to_sp(8 * s, 0, s), (8, 0))
            self.assertEqual(px_to_sp(8 * s - 1, 0, s), (7, 0))
            self.assertEqual(px_to_sp((8 + 176) * s - 1, 78 * s - 1, s), (183, 77))
            self.assertEqual(px_to_sp((8 + 176) * s, 78 * s, s), (184, 78))

    def test_card_box_does_not_overlap_character_box(self) -> None:
        self.assertFalse(CARD_BOX_SP.intersects(CHARACTER_BOX_SP))
        self.assertLessEqual(CARD_BOX_SP.y + CARD_BOX_SP.h, CHARACTER_BOX_SP.y)

    def test_card_buttons_5_states_labels_and_enabled(self) -> None:
        # 1. STOPPED
        btns_stopped = card_buttons(TimerState.STOPPED, PomodoroPhase.FOCUS, "뽀모도로")
        self.assertEqual([b.key for b in btns_stopped], ["primary", "subject", "mode", "stats", "settings", "more"])
        self.assertEqual(btns_stopped[0].label, "학습 시작 (뽀모도로)")
        self.assertEqual(btns_stopped[1].label, "과목 ▾")
        self.assertEqual(btns_stopped[2].label, "모드 ▾")
        self.assertTrue(all(b.enabled for b in btns_stopped))

        # 2. RUNNING + FOCUS
        btns_focus = card_buttons(TimerState.RUNNING, PomodoroPhase.FOCUS, "뽀모도로")
        self.assertEqual([b.key for b in btns_focus], ["primary", "end", "subject", "stats", "settings", "more"])
        self.assertEqual(btns_focus[0].label, "일시정지")
        self.assertEqual(btns_focus[1].label, "■ 끝내기")
        self.assertEqual(btns_focus[2].label, "과목 바꾸기 ▾")
        self.assertTrue(all(b.enabled for b in btns_focus))

        # 3. RUNNING + BREAK
        btns_break = card_buttons(TimerState.RUNNING, PomodoroPhase.BREAK, "뽀모도로")
        self.assertEqual([b.key for b in btns_break], ["primary", "end", "subject", "stats", "settings", "more"])
        self.assertEqual(btns_break[0].label, "일시정지")
        self.assertTrue(all(b.enabled for b in btns_break))

        # 4. PAUSED
        btns_paused = card_buttons(TimerState.PAUSED, PomodoroPhase.FOCUS, "뽀모도로")
        self.assertEqual([b.key for b in btns_paused], ["primary", "end", "subject", "stats", "settings", "more"])
        self.assertEqual(btns_paused[0].label, "이어하기")
        self.assertTrue(all(b.enabled for b in btns_paused))

        # 5. PAUSED_AFK (과목 바꾸기 비활성)
        btns_afk = card_buttons(TimerState.PAUSED_AFK, PomodoroPhase.FOCUS, "뽀모도로")
        self.assertEqual([b.key for b in btns_afk], ["primary", "end", "subject", "stats", "settings", "more"])
        self.assertEqual(btns_afk[0].label, "확인 창 열기")
        self.assertFalse(btns_afk[2].enabled)
        self.assertTrue(btns_afk[0].enabled and btns_afk[1].enabled)

        # FINALIZING -> 빈 목록
        self.assertEqual(card_buttons(TimerState.FINALIZING, PomodoroPhase.FOCUS), [])

    def test_all_buttons_inside_card_and_mutually_non_overlapping(self) -> None:
        states = [
            (TimerState.STOPPED, PomodoroPhase.FOCUS),
            (TimerState.RUNNING, PomodoroPhase.FOCUS),
            (TimerState.RUNNING, PomodoroPhase.BREAK),
            (TimerState.PAUSED, PomodoroPhase.FOCUS),
            (TimerState.PAUSED_AFK, PomodoroPhase.FOCUS),
        ]
        for st, ph in states:
            btns = card_buttons(st, ph)
            for i, b in enumerate(btns):
                self.assertGreaterEqual(b.box.x, CARD_BOX_SP.x)
                self.assertGreaterEqual(b.box.y, CARD_BOX_SP.y)
                self.assertLessEqual(b.box.x + b.box.w, CARD_BOX_SP.x + CARD_BOX_SP.w)
                self.assertLessEqual(b.box.y + b.box.h, CARD_BOX_SP.y + CARD_BOX_SP.h)
                for b2 in btns[i + 1 :]:
                    self.assertFalse(b.box.intersects(b2.box))

    def test_hit_test_card_and_disabled_button_returns_none(self) -> None:
        btns_run = card_buttons(TimerState.RUNNING, PomodoroPhase.FOCUS)
        self.assertEqual(hit_test_card(btns_run, 50, 25), "primary")
        self.assertEqual(hit_test_card(btns_run, 30, 45), "end")
        self.assertEqual(hit_test_card(btns_run, 120, 45), "subject")
        self.assertEqual(hit_test_card(btns_run, 25, 65), "stats")
        self.assertEqual(hit_test_card(btns_run, 80, 65), "settings")
        self.assertEqual(hit_test_card(btns_run, 140, 65), "more")
        self.assertIsNone(hit_test_card(btns_run, 96, 100))

        # PAUSED_AFK에서 보조 B(과목 바꾸기)는 비활성이므로 None 반환
        btns_afk = card_buttons(TimerState.PAUSED_AFK, PomodoroPhase.FOCUS)
        self.assertIsNone(hit_test_card(btns_afk, 120, 45))

    def test_card_header_per_state(self) -> None:
        self.assertEqual(
            card_header(TimerState.STOPPED, PomodoroPhase.FOCUS, TimerMode.POMODORO, "국어", 0, None),
            ("대기 중 · 국어", ""),
        )
        self.assertEqual(
            card_header(TimerState.RUNNING, PomodoroPhase.FOCUS, TimerMode.POMODORO, "국어", 754, 746),
            ("● 집중 국어", "0:12:34 남은 12:26"),
        )
        self.assertEqual(
            card_header(TimerState.RUNNING, PomodoroPhase.BREAK, TimerMode.POMODORO, "국어", 1500, 299),
            ("휴식", "남은 4:59"),
        )
        self.assertEqual(
            card_header(TimerState.PAUSED, PomodoroPhase.FOCUS, TimerMode.STOPWATCH, "수학", 3661, None),
            ("일시정지 수학", "1:01:01"),
        )
        self.assertEqual(
            card_header(TimerState.PAUSED_AFK, PomodoroPhase.FOCUS, TimerMode.STOPWATCH, "수학", 600, None),
            ("자리 비움 확인 중", ""),
        )

    def test_bubble_clamping_and_8sp_alignment(self) -> None:
        b1 = compute_bubble_box_sp(text_w_px=120, phys_scale=2, win_left_px=500, work_left_px=0, work_right_px=1920)
        self.assertEqual(b1.w % 8, 0)
        self.assertGreaterEqual(b1.w, BUBBLE_MIN_W_SP)
        self.assertLessEqual(b1.w, BUBBLE_MAX_W_SP)
        self.assertEqual(b1.x, 96 - b1.w // 2)

        b_left = compute_bubble_box_sp(text_w_px=260, phys_scale=2, win_left_px=-40, work_left_px=0, work_right_px=1920)
        self.assertGreaterEqual(b_left.x, 8)
        self.assertLessEqual(b_left.x + b_left.w, 184)


if __name__ == "__main__":
    unittest.main()
