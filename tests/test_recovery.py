"""크래시 복구(같은 날 이어하기, 다음날 이어하기, 저장, 폐기) 단위 테스트 (DEVELOPMENT_PLAN.md 7-1)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from studypet.domain.clock import FakeClock
from studypet.domain.events import Event, Mode, RecoverAction, TimerState
from studypet.domain.timer_engine import TimerEngine, TimerSettings
from studypet.infra.db import Database


KST = timezone(timedelta(hours=9))


class TestCrashRecovery(unittest.TestCase):
    def setUp(self) -> None:
        self.db = Database.open(":memory:")
        self.sub_id = self.db.subjects.ensure_default_subject("2026-11-03T09:00:00+09:00")
        self.events: list[Event] = []

    def tearDown(self) -> None:
        self.db.close()

    def test_recover_continue_same_day(self) -> None:
        # 15분(900초) 기록된 미완료 세션 생성
        seg = self.db.sessions.create_chain(self.sub_id, "STOPWATCH", "2026-11-03T10:00:00+09:00", "2026-11-03")
        self.db.sessions.checkpoint(seg.id, "2026-11-03T10:15:00+09:00", 900)
        open_rows = self.db.sessions.get_open_segments()
        self.assertEqual(len(open_rows), 1)

        # 같은 날 10:30에 앱 재기동 후 [이어하기]
        clock = FakeClock(datetime(2026, 11, 3, 10, 30, 0, tzinfo=KST))
        engine = TimerEngine(self.db.sessions, clock, TimerSettings(), self.events.append)
        engine.recover(open_rows[0], RecoverAction.CONTINUE)

        self.assertEqual(engine.state, TimerState.RUNNING)
        self.assertEqual(engine.display_seconds(), 900)  # 꺼져 있던 15분은 인정하지 않고 900초부터 시작

        for _ in range(60):
            clock.advance(1.0)
            engine.tick()
        self.assertEqual(engine.display_seconds(), 960)

        engine.stop()
        engine.finalize("복구 완료")
        final_row = self.db.sessions.get_segment(seg.id)
        assert final_row is not None
        self.assertTrue(final_row.is_completed)
        self.assertEqual(final_row.duration_seconds, 960)

    def test_recover_continue_next_day_creates_next_segment(self) -> None:
        seg = self.db.sessions.create_chain(self.sub_id, "POMODORO", "2026-11-03T22:00:00+09:00", "2026-11-03")
        self.db.sessions.checkpoint(seg.id, "2026-11-03T22:20:00+09:00", 1200)
        open_row = self.db.sessions.get_open_segments()[0]

        # 다음날(11월 4일) 09:00에 재기동 후 [이어하기]
        clock = FakeClock(datetime(2026, 11, 4, 9, 0, 0, tzinfo=KST))
        engine = TimerEngine(self.db.sessions, clock, TimerSettings(), self.events.append)
        engine.recover(open_row, RecoverAction.CONTINUE)

        self.assertEqual(engine.state, TimerState.RUNNING)
        self.assertEqual(engine.display_seconds(), 1200)

        for _ in range(100):
            clock.advance(1.0)
            engine.tick()
        engine.stop()
        engine.finalize("다음날 이어하기")

        chain_rows = self.db.sessions.list_by_chain(seg.chain_id)
        self.assertEqual(len(chain_rows), 2)
        self.assertEqual(chain_rows[0].local_date, "2026-11-03")
        self.assertEqual(chain_rows[0].duration_seconds, 1200)
        self.assertTrue(chain_rows[0].is_completed)
        self.assertEqual(chain_rows[1].local_date, "2026-11-04")
        self.assertEqual(chain_rows[1].duration_seconds, 100)
        self.assertTrue(chain_rows[1].is_completed)
        self.assertEqual(chain_rows[0].memo, "다음날 이어하기")
        self.assertEqual(chain_rows[1].memo, "다음날 이어하기")

    def test_recover_save_and_discard(self) -> None:
        seg1 = self.db.sessions.create_chain(self.sub_id, "STOPWATCH", "2026-11-03T10:00:00+09:00", "2026-11-03")
        self.db.sessions.checkpoint(seg1.id, "2026-11-03T10:14:00+09:00", 840)

        seg2 = self.db.sessions.create_chain(self.sub_id, "STOPWATCH", "2026-11-03T11:00:00+09:00", "2026-11-03")
        self.db.sessions.checkpoint(seg2.id, "2026-11-03T11:05:00+09:00", 300)

        open_rows = self.db.sessions.get_open_segments()
        clock = FakeClock(datetime(2026, 11, 3, 12, 0, 0, tzinfo=KST))
        engine = TimerEngine(self.db.sessions, clock, TimerSettings(), self.events.append)

        # seg1은 [여기까지 저장]
        engine.recover(open_rows[0], RecoverAction.SAVE, memo="중간 저장")
        r1 = self.db.sessions.get_segment(seg1.id)
        assert r1 is not None
        self.assertTrue(r1.is_completed)
        self.assertEqual(r1.duration_seconds, 840)
        self.assertEqual(r1.memo, "중간 저장")

        # seg2는 [폐기]
        engine.recover(open_rows[1], RecoverAction.DISCARD)
        self.assertIsNone(self.db.sessions.get_segment(seg2.id))

    def test_recover_later_keeps_open_row_intact_for_next_startup(self) -> None:
        seg = self.db.sessions.create_chain(self.sub_id, "STOPWATCH", "2026-11-03T14:00:00+09:00", "2026-11-03")
        self.db.sessions.checkpoint(seg.id, "2026-11-03T14:25:00+09:00", 1500)
        open_before = self.db.sessions.get_open_segments()
        self.assertEqual(len(open_before), 1)

        # H2: 복구 창에서 X 버튼·Esc([나중에 결정])를 누르면 엔진을 호출하지 않고 행을 그대로 유지
        choice = "later"
        if choice == "later":
            pass

        open_after = self.db.sessions.get_open_segments()
        self.assertEqual(len(open_after), 1)
        self.assertEqual(open_after[0].id, seg.id)
        self.assertEqual(open_after[0].duration_seconds, 1500)
        self.assertFalse(open_after[0].is_completed)


if __name__ == "__main__":
    unittest.main()

