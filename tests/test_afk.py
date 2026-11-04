"""AFK 진입, 롤백, 유휴 의심 체크포인트 제외, 복귀 해소, 잠금/절전, GetTickCount 되감기 테스트 (DEVELOPMENT_PLAN.md 7-1)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from studypet.domain.clock import FakeClock
from studypet.domain.events import AfkReturned, AfkStarted, Event, Mode, Phase, TimerState
from studypet.domain.timer_engine import TimerEngine, TimerSettings
from studypet.infra.db import Database
from studypet.win32.idle import compute_idle_ms


KST = timezone(timedelta(hours=9))


class TestAfkEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.db = Database.open(":memory:")
        self.sub_id = self.db.subjects.ensure_default_subject("2026-11-03T09:00:00+09:00")
        self.clock = FakeClock(datetime(2026, 11, 3, 9, 0, 0, tzinfo=KST))
        self.events: list[Event] = []
        self.engine = TimerEngine(
            repo=self.db.sessions,
            clock=self.clock,
            settings=TimerSettings(pomodoro_focus_min=25, pomodoro_break_min=5, afk_timeout_min=10),
            emit=self.events.append,
        )

    def tearDown(self) -> None:
        self.db.close()

    def test_afk_entry_rollback_suspect_checkpoint_and_exclude(self) -> None:
        self.engine.start(self.sub_id, Mode.STOPWATCH)
        # 5분(300초) 동안 활발히 입력하며 학습
        for _ in range(300):
            self.clock.advance(1.0)
            self.engine.tick()
            self.engine.on_idle_poll(0)
        self.assertEqual(self.engine.display_seconds(), 300)

        # 이후 입력 없이 10분(600초) 경과
        for s in range(1, 601):
            self.clock.advance(1.0)
            # 60초 이상 유휴일 때 체크포인트가 유휴 의심 구간을 제외하고 300초로 유지하는지 확인
            self.engine.on_idle_poll(s * 1_000)
            self.engine.tick()
            if s == 120:
                seg_mid = self.db.sessions.get_segment(1)
                assert seg_mid is not None
                self.assertEqual(seg_mid.duration_seconds, 300)

        # 600초 시점에 PAUSED_AFK 진입 및 300초로 롤백
        self.assertEqual(self.engine.state, TimerState.PAUSED_AFK)
        self.assertEqual(self.engine.display_seconds(), 300)
        self.assertTrue(any(isinstance(e, AfkStarted) for e in self.events))

        # 추가로 5분(300초) 더 자리 비움 (총 15분 = 900초 유휴)
        for s in range(601, 901):
            self.clock.advance(1.0)
            self.engine.tick()
            self.engine.on_idle_poll(s * 1_000)

        # 사용자 복귀 (idle_ms가 줄어듦) -> AfkReturned 이벤트가 정확히 1회만 발생해야 함
        self.engine.on_idle_poll(100)
        self.engine.on_idle_poll(50)
        returned_events = [e for e in self.events if isinstance(e, AfkReturned)]
        self.assertEqual(len(returned_events), 1)
        self.assertEqual(returned_events[0].away_wall_s, 900)
        self.assertEqual(returned_events[0].away_awake_s, 900)
        self.assertTrue(returned_events[0].can_include)

        # [제외] 선택 -> 300초에서 그대로 재개
        self.engine.resolve_afk(include=False)
        self.assertEqual(self.engine.state, TimerState.RUNNING)
        self.assertEqual(self.engine.display_seconds(), 300)

    def test_afk_include_in_pomodoro_excludes_break_time(self) -> None:
        self.engine.start(self.sub_id, Mode.POMODORO)
        # 20분(1200초) 동안 집중 후 손 뗌 (집중 잔여 5분)
        for _ in range(1200):
            self.clock.advance(1.0)
            self.engine.tick()
            self.engine.on_idle_poll(0)

        # 10분(600초) 유휴로 AFK 진입 -> 20분 시점으로 롤백됨
        for s in range(1, 601):
            self.clock.advance(1.0)
            self.engine.tick()
            self.engine.on_idle_poll(s * 1_000)
        self.assertEqual(self.engine.state, TimerState.PAUSED_AFK)
        self.assertEqual(self.engine.display_seconds(), 1200)
        self.assertEqual(self.engine.phase, Phase.FOCUS)

        # 복귀 후 [포함] 선택: 자리 비운 10분 중 앞 5분은 FOCUS, 뒤 5분은 BREAK로 시뮬레이션되어
        # 순공 시간은 +300초(총 1500초 = 25분)만 인정되고 새 FOCUS 페이즈(0초)로 진입해야 함
        self.engine.on_idle_poll(0)
        self.engine.resolve_afk(include=True)
        self.assertEqual(self.engine.state, TimerState.RUNNING)
        self.assertEqual(self.engine.display_seconds(), 1500)
        self.assertEqual(self.engine.phase, Phase.FOCUS)
        self.assertEqual(self.engine.phase_remaining_seconds(), 25 * 60)

    def test_idle_purely_during_pomodoro_break_is_not_afk(self) -> None:
        # 집중 25분 완료 후 BREAK 진입, 휴식 시간을 15분으로 설정한 경우
        self.engine.update_settings(TimerSettings(pomodoro_focus_min=5, pomodoro_break_min=15, afk_timeout_min=10))
        self.engine.start(self.sub_id, Mode.POMODORO)
        for _ in range(5 * 60):
            self.clock.advance(1.0)
            self.engine.tick()
            self.engine.on_idle_poll(0)
        self.assertEqual(self.engine.phase, Phase.BREAK)

        # BREAK 상태에서 10분간 자리 비움 -> rollback == 0이고 BREAK이므로 AFK 진입하지 않음
        for s in range(1, 601):
            self.clock.advance(1.0)
            self.engine.tick()
            self.engine.on_idle_poll(s * 1_000)
        self.assertEqual(self.engine.state, TimerState.RUNNING)
        self.assertEqual(self.engine.phase, Phase.BREAK)

    def test_lock_and_suspend_immediate_afk_and_sleep_excluded(self) -> None:
        self.engine.start(self.sub_id, Mode.STOPWATCH)
        for _ in range(60):
            self.clock.advance(1.0)
            self.engine.tick()
            self.engine.on_idle_poll(0)

        # 절전 진입 -> 즉시 PAUSED_AFK
        self.engine.on_suspend()
        self.assertEqual(self.engine.state, TimerState.PAUSED_AFK)

        # 30분(1800초) 동안 PC 절전(벽시계만 흐르고 단조 시계는 정지) + 깨어난 뒤 10초 경과
        self.clock.advance_sleep(1800)
        self.clock.advance(10)
        self.engine.on_session_unlock()

        ret = [e for e in self.events if isinstance(e, AfkReturned)][-1]
        self.assertEqual(ret.away_wall_s, 1810)
        self.assertEqual(ret.away_awake_s, 10)  # 절전 1800초는 제외됨!

        # [포함]을 눌러도 절전 시간은 들어가지 않고 깨어 있던 10초만 합산됨
        self.engine.resolve_afk(include=True)
        self.assertEqual(self.engine.display_seconds(), 70)

    def test_gettickcount_wraparound_calculation(self) -> None:
        # dw_time = 0xFFFFFF00, tick_count = 0x00000100 -> 차이는 0x200 (512ms)
        self.assertEqual(compute_idle_ms(0x00000100, 0xFFFFFF00), 0x200)


if __name__ == "__main__":
    unittest.main()

