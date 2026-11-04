"""domain/timer_engine.py 기본 동작 및 switch_subject/checkpoint_now 단위 테스트 (DEVELOPMENT_PLAN.md 7-1, REVISION_PLAN_v0.7 5장)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from studypet.domain.clock import FakeClock
from studypet.domain.events import (
    Event,
    Finished,
    Mode,
    Phase,
    PhaseChanged,
    StorageError,
    SubjectSwitched,
    TimerState,
)
from studypet.domain.timer_engine import TimerEngine, TimerSettings
from studypet.infra.db import Database


KST = timezone(timedelta(hours=9))


class TestTimerEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.db = Database.open(":memory:")
        self.sub_id = self.db.subjects.ensure_default_subject("2026-11-03T09:00:00+09:00")
        self.sub2_id = self.db.subjects.create("수학", "#4CC37D", 60, "2026-11-03T09:00:00+09:00").id
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

    def _step_seconds(self, total_s: int, step_s: float = 1.0) -> None:
        steps = int(round(total_s / step_s))
        for _ in range(steps):
            self.clock.advance(step_s)
            self.engine.tick()

    def test_stopwatch_accumulation_and_pause_exclusion(self) -> None:
        self.engine.start(self.sub_id, Mode.STOPWATCH)
        self.assertEqual(self.engine.state, TimerState.RUNNING)
        self.assertEqual(self.engine.display_seconds(), 0)

        self._step_seconds(10)
        self.assertEqual(self.engine.display_seconds(), 10)

        self.engine.pause()
        self.assertEqual(self.engine.state, TimerState.PAUSED)
        self._step_seconds(30)
        self.assertEqual(self.engine.display_seconds(), 10)

        self.engine.resume()
        self.assertEqual(self.engine.state, TimerState.RUNNING)
        self._step_seconds(5)
        self.assertEqual(self.engine.display_seconds(), 15)

        self.engine.stop()
        self.assertEqual(self.engine.state, TimerState.FINALIZING)
        self.engine.finalize("스톱워치 테스트")
        self.assertEqual(self.engine.state, TimerState.STOPPED)

        rows = self.db.sessions.list_by_chain(1)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].is_completed)
        self.assertEqual(rows[0].duration_seconds, 15)
        self.assertEqual(rows[0].memo, "스톱워치 테스트")

    def test_pomodoro_focus_break_transition_and_break_exclusion(self) -> None:
        self.engine.start(self.sub_id, Mode.POMODORO)
        self.assertEqual(self.engine.phase, Phase.FOCUS)
        self.assertEqual(self.engine.phase_remaining_seconds(), 25 * 60)

        self._step_seconds(25 * 60)
        self.assertEqual(self.engine.phase, Phase.BREAK)
        self.assertEqual(self.engine.display_seconds(), 25 * 60)
        self.assertEqual(self.engine.phase_remaining_seconds(), 5 * 60)

        self._step_seconds(5 * 60)
        self.assertEqual(self.engine.phase, Phase.FOCUS)
        self.assertEqual(self.engine.display_seconds(), 25 * 60)

        self._step_seconds(10)
        self.assertEqual(self.engine.display_seconds(), 25 * 60 + 10)

        phase_events = [e for e in self.events if isinstance(e, PhaseChanged)]
        self.assertEqual([e.phase for e in phase_events], [Phase.BREAK, Phase.FOCUS])

    def test_abnormal_tick_gap_over_5s_ignored(self) -> None:
        self.engine.start(self.sub_id, Mode.STOPWATCH)
        self._step_seconds(5)
        self.assertEqual(self.engine.display_seconds(), 5)

        self.clock.advance(10.0)
        self.engine.tick()
        self.assertEqual(self.engine.display_seconds(), 5)

    def test_checkpoint_every_60_seconds_and_checkpoint_now(self) -> None:
        # STOPPED 상태에서 checkpoint_now는 무동작
        self.engine.checkpoint_now()
        self.assertEqual(self.db.sessions.get_open_segments(), [])

        self.engine.start(self.sub_id, Mode.STOPWATCH)
        self._step_seconds(59)
        seg_before = self.db.sessions.get_segment(1)
        assert seg_before is not None
        self.assertEqual(seg_before.duration_seconds, 0)

        # checkpoint_now 호출 시 60초 주기 전이어도 즉시 DB 기록
        self.engine.checkpoint_now()
        seg_forced = self.db.sessions.get_segment(1)
        assert seg_forced is not None
        self.assertEqual(seg_forced.duration_seconds, 59)

        self._step_seconds(1)
        self.engine.checkpoint_now()
        seg_at_60 = self.db.sessions.get_segment(1)
        assert seg_at_60 is not None
        self.assertEqual(seg_at_60.duration_seconds, 60)

    def test_switch_subject_finalizes_silently_and_starts_new_chain(self) -> None:
        self.engine.start(self.sub_id, Mode.POMODORO)
        self._step_seconds(120)

        # 같은 과목으로 전환 시 무시
        self.engine.switch_subject(self.sub_id)
        self.assertEqual(self.engine.subject_id, self.sub_id)
        self.assertEqual(self.engine.display_seconds(), 120)

        # 다른 과목으로 전환
        self.events.clear()
        self.engine.switch_subject(self.sub2_id)
        self.assertEqual(self.engine.state, TimerState.RUNNING)
        self.assertEqual(self.engine.subject_id, self.sub2_id)
        self.assertEqual(self.engine.mode, Mode.POMODORO)
        self.assertEqual(self.engine.display_seconds(), 0)

        # 이전 체인은 완료(is_completed=1), 메모 빈 문자열
        prev_rows = self.db.sessions.list_by_chain(1)
        self.assertEqual(len(prev_rows), 1)
        self.assertTrue(prev_rows[0].is_completed)
        self.assertEqual(prev_rows[0].duration_seconds, 120)
        self.assertEqual(prev_rows[0].memo, "")

        # Finished 미발행, SubjectSwitched 발행
        self.assertFalse(any(isinstance(e, Finished) for e in self.events))
        sw_events = [e for e in self.events if isinstance(e, SubjectSwitched)]
        self.assertEqual(len(sw_events), 1)
        self.assertEqual(sw_events[0].prev_subject_id, self.sub_id)
        self.assertEqual(sw_events[0].new_subject_id, self.sub2_id)
        self.assertEqual(sw_events[0].saved_s, 120)

    def test_switch_subject_from_paused_starts_running_and_zero_sec_deleted(self) -> None:
        # 1. 0초 체인에서 전환 -> 이전 미완료 행 삭제되고 새 체인만 남음 (8장 D2)
        self.engine.start(self.sub_id, Mode.STOPWATCH)
        self.engine.switch_subject(self.sub2_id)
        self.assertIsNone(self.db.sessions.get_segment(1))
        open_rows = self.db.sessions.get_open_segments()
        self.assertEqual(len(open_rows), 1)
        self.assertEqual(open_rows[0].subject_id, self.sub2_id)

        # 2. PAUSED 상태에서 전환 -> 새 체인은 RUNNING
        self._step_seconds(30)
        self.engine.pause()
        self.assertEqual(self.engine.state, TimerState.PAUSED)
        self.engine.switch_subject(self.sub_id)
        self.assertEqual(self.engine.state, TimerState.RUNNING)
        self.assertEqual(self.engine.subject_id, self.sub_id)

        # 3. PAUSED_AFK 상태에서 switch_subject 호출 -> 무시 (8장 D2)
        self._step_seconds(60)
        self.engine.on_idle_poll(10 * 60 * 1000)
        self.assertEqual(self.engine.state, TimerState.PAUSED_AFK)
        self.engine.switch_subject(self.sub2_id)
        self.assertEqual(self.engine.state, TimerState.PAUSED_AFK)
        self.assertEqual(self.engine.subject_id, self.sub_id)

    def test_switch_subject_finalize_failure_restores_previous_state(self) -> None:
        """저장 실패 시 FINALIZING에 갇히지 않고 이전 상태로 돌아가며, 전환 토스트 이벤트를 보내지 않는다."""
        self.engine.start(self.sub_id, Mode.STOPWATCH)
        self._step_seconds(30)

        def fail(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("disk full")

        self.db.sessions.finalize_chain = fail  # type: ignore[method-assign]
        self.engine.switch_subject(self.sub2_id)

        self.assertEqual(self.engine.state, TimerState.RUNNING)
        self.assertEqual(self.engine.subject_id, self.sub_id)
        self.assertFalse(any(isinstance(e, SubjectSwitched) for e in self.events))
        self.assertTrue(any(isinstance(e, StorageError) for e in self.events))

        # 다시 정상 동작: 계속 누적되고 끝내기가 가능하다
        self._step_seconds(5)
        self.assertEqual(self.engine.display_seconds(), 35)
        self.engine.stop()
        self.assertEqual(self.engine.state, TimerState.FINALIZING)

    def test_switch_subject_start_failure_emits_no_switch_toast(self) -> None:
        self.engine.start(self.sub_id, Mode.STOPWATCH)
        self._step_seconds(30)

        def fail(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("disk full")

        self.db.sessions.create_chain = fail  # type: ignore[method-assign]
        self.engine.switch_subject(self.sub2_id)

        self.assertEqual(self.engine.state, TimerState.STOPPED)
        self.assertFalse(any(isinstance(e, SubjectSwitched) for e in self.events))
        self.assertTrue(any(isinstance(e, StorageError) for e in self.events))


if __name__ == "__main__":
    unittest.main()
