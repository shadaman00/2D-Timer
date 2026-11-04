"""자정(00:00:00) 세션 자동 분할 및 체인 테스트 (DEVELOPMENT_PLAN.md 7-1)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from studypet.domain.clock import FakeClock
from studypet.domain.events import Event, Mode, TimerState
from studypet.domain.timer_engine import TimerEngine, TimerSettings
from studypet.infra.db import Database


KST = timezone(timedelta(hours=9))


class TestMidnightSplit(unittest.TestCase):
    def setUp(self) -> None:
        self.db = Database.open(":memory:")
        self.sub_id = self.db.subjects.ensure_default_subject("2026-11-03T09:00:00+09:00")
        self.events: list[Event] = []

    def tearDown(self) -> None:
        self.db.close()

    def test_running_across_midnight_splits_into_two_segments(self) -> None:
        clock = FakeClock(datetime(2026, 11, 3, 23, 59, 30, tzinfo=KST))
        engine = TimerEngine(self.db.sessions, clock, TimerSettings(), self.events.append)
        engine.start(self.sub_id, Mode.STOPWATCH)

        # 23:59:30 -> 00:00:30 (60초 진행)
        for _ in range(60):
            clock.advance(1.0)
            engine.tick()

        # HUD 표시 초는 체인 전체 합계인 60초를 유지해야 함
        self.assertEqual(engine.display_seconds(), 60)

        engine.stop()
        engine.finalize("자정 넘김 공부")

        rows = self.db.sessions.list_by_chain(1)
        self.assertEqual(len(rows), 2)
        seg1, seg2 = rows[0], rows[1]

        self.assertEqual(seg1.segment_no, 1)
        self.assertEqual(seg1.local_date, "2026-11-03")
        self.assertEqual(seg1.start_time, "2026-11-03T23:59:30+09:00")
        self.assertEqual(seg1.end_time, "2026-11-04T00:00:00+09:00")  # 배타적 종료 시각
        self.assertEqual(seg1.duration_seconds, 30)
        self.assertTrue(seg1.is_completed)
        self.assertEqual(seg1.memo, "자정 넘김 공부")

        self.assertEqual(seg2.segment_no, 2)
        self.assertEqual(seg2.local_date, "2026-11-04")
        self.assertEqual(seg2.start_time, "2026-11-04T00:00:00+09:00")
        self.assertEqual(seg2.end_time, "2026-11-04T00:00:30+09:00")
        self.assertEqual(seg2.duration_seconds, 30)
        self.assertTrue(seg2.is_completed)
        self.assertEqual(seg2.memo, "자정 넘김 공부")

    def test_paused_across_midnight_splits_cleanly(self) -> None:
        clock = FakeClock(datetime(2026, 11, 3, 23, 59, 40, tzinfo=KST))
        engine = TimerEngine(self.db.sessions, clock, TimerSettings(), self.events.append)
        engine.start(self.sub_id, Mode.STOPWATCH)

        for _ in range(10):
            clock.advance(1.0)
            engine.tick()
        engine.pause()  # 23:59:50에 일시정지 (10초 누적)

        # 일시정지 상태로 20초 경과 -> 00:00:10
        for _ in range(20):
            clock.advance(1.0)
            engine.tick()

        engine.resume()
        for _ in range(15):
            clock.advance(1.0)
            engine.tick()
        engine.stop()
        engine.finalize("일시정지 자정")

        rows = self.db.sessions.list_by_chain(1)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].duration_seconds, 10)
        self.assertEqual(rows[1].duration_seconds, 15)

    def test_afk_across_single_midnight_and_include(self) -> None:
        # 23:50:00 시작 -> 5분(300초) 학습 후 23:55:00부터 손 뗌 -> 00:05:00(10분 유휴)에 AFK 진입 -> 00:10:00 복귀 후 [포함]
        clock = FakeClock(datetime(2026, 11, 3, 23, 50, 0, tzinfo=KST))
        engine = TimerEngine(
            self.db.sessions,
            clock,
            TimerSettings(afk_timeout_min=10),
            self.events.append,
        )
        engine.start(self.sub_id, Mode.STOPWATCH)
        for _ in range(300):
            clock.advance(1.0)
            engine.tick()
            engine.on_idle_poll(0)

        # 23:55:00 ~ 00:05:00 (600초 유휴: 자정 전 300초 + 자정 후 300초)
        for s in range(1, 601):
            clock.advance(1.0)
            engine.tick()
            engine.on_idle_poll(s * 1_000)

        self.assertEqual(engine.state, TimerState.PAUSED_AFK)
        # 롤백 직후에는 자정 전 300초만 남고 자정 후 세그먼트는 0초여야 함
        self.assertEqual(engine.display_seconds(), 300)

        # 00:05:00 ~ 00:10:00 (추가 300초 유휴)
        for s in range(601, 901):
            clock.advance(1.0)
            engine.tick()
            engine.on_idle_poll(s * 1_000)

        # 복귀 및 [포함] 선택 -> 자정 전 +300초(총 600초), 자정 후 +600초(총 600초) 배분!
        engine.on_idle_poll(0)
        self.assertTrue(engine.can_include_afk())
        engine.resolve_afk(include=True)
        self.assertEqual(engine.display_seconds(), 1200)

        engine.stop()
        engine.finalize("인강 시청 자정 포함")
        rows = self.db.sessions.list_by_chain(1)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].local_date, "2026-11-03")
        self.assertEqual(rows[0].duration_seconds, 600)
        self.assertEqual(rows[1].local_date, "2026-11-04")
        self.assertEqual(rows[1].duration_seconds, 600)

    def test_afk_across_two_midnights_disables_include(self) -> None:
        clock = FakeClock(datetime(2026, 11, 3, 23, 58, 0, tzinfo=KST))
        engine = TimerEngine(self.db.sessions, clock, TimerSettings(afk_timeout_min=1), self.events.append)
        engine.start(self.sub_id, Mode.STOPWATCH)

        # 1분 유휴 -> 23:59:00에 AFK 진입
        for s in range(1, 61):
            clock.advance(1.0)
            engine.tick()
            engine.on_idle_poll(s * 1_000)
        self.assertEqual(engine.state, TimerState.PAUSED_AFK)

        # 첫 번째 자정 통과 (11월 4일 00:00:10)
        for _ in range(70):
            clock.advance(1.0)
            engine.tick()
        self.assertTrue(engine.can_include_afk())

        # 두 번째 자정 통과 (11월 5일 00:00:10로 벽시계 점프 후 틱)
        clock.set_wall(datetime(2026, 11, 5, 0, 0, 10, tzinfo=KST))
        clock.advance(1.0)
        engine.tick()
        self.assertFalse(engine.can_include_afk())


if __name__ == "__main__":
    unittest.main()

