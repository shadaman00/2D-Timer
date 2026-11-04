"""정밀 학습 타이머 엔진 (스톱워치/뽀모도로, 자정 자동 분할, AFK 롤백·시뮬레이션, 크래시 복구) (DEVELOPMENT_PLAN.md 4-7)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import logging
from typing import Callable, Protocol

from studypet.domain.clock import NS, Clock, iso
from studypet.domain.credit_log import CreditTimeline
from studypet.domain.events import (
    AfkReturned,
    AfkStarted,
    Event,
    FinalizeRequested,
    Finished,
    Mode,
    Paused,
    Phase,
    PhaseChanged,
    RecoverAction,
    Recovered,
    Resumed,
    Started,
    StorageError,
    SubjectSwitched,
    Ticked,
    TimerState,
)


logger = logging.getLogger("studypet.timer")

MAX_TICK_GAP_NS = 5 * NS
CHECKPOINT_NS = 60 * NS
SUSPECT_IDLE_MS = 60_000

ACTIVE_STATES = (TimerState.RUNNING, TimerState.PAUSED, TimerState.PAUSED_AFK)


class SegmentRowLike(Protocol):
    @property
    def id(self) -> int: ...
    @property
    def subject_id(self) -> int: ...
    @property
    def mode(self) -> str: ...
    @property
    def start_time(self) -> str: ...
    @property
    def end_time(self) -> str: ...
    @property
    def local_date(self) -> str: ...
    @property
    def duration_seconds(self) -> int: ...
    @property
    def memo(self) -> str: ...
    @property
    def is_completed(self) -> bool: ...
    @property
    def chain_id(self) -> int: ...
    @property
    def segment_no(self) -> int: ...


class SessionRepoProtocol(Protocol):
    def create_chain(self, subject_id: int, mode: str, start_iso: str, local_date: str | date) -> SegmentRowLike: ...
    def create_next_segment(self, prev: SegmentRowLike, start_iso: str, local_date: str | date) -> SegmentRowLike: ...
    def checkpoint(self, seg_id: int, end_iso: str, duration_s: int) -> None: ...
    def complete_segment(self, seg_id: int, end_iso: str, duration_s: int) -> None: ...
    def add_duration(self, seg_id: int, delta_s: int) -> None: ...
    def finalize_chain(self, chain_id: int, seg_id: int, end_iso: str, duration_s: int, memo: str) -> None: ...
    def update_chain_memo(self, chain_id: int, memo: str) -> None: ...
    def delete_segment(self, seg_id: int) -> None: ...
    def chain_completed_seconds(self, chain_id: int) -> int: ...


@dataclass(frozen=True)
class TimerSettings:
    pomodoro_focus_min: int = 25
    pomodoro_break_min: int = 5
    afk_timeout_min: int = 10


@dataclass
class Segment:
    row_id: int
    chain_id: int
    segment_no: int
    local_date: date
    credited_ns: int
    row: SegmentRowLike


@dataclass
class AfkSnapshot:
    start_mono: int
    start_wall: datetime
    phase: Phase
    phase_elapsed_ns: int
    split_mono: int | None = None
    splits: int = 0
    return_pending: bool = False


class TimerEngine:
    """순수 도메인 타이머 엔진."""

    def __init__(
        self,
        repo: SessionRepoProtocol,
        clock: Clock,
        settings: TimerSettings | None = None,
        emit: Callable[[Event], None] | None = None,
    ) -> None:
        self.repo = repo
        self.clock = clock
        self._settings = settings or TimerSettings()
        self.emit: Callable[[Event], None] = emit or (lambda _e: None)

        self.state: TimerState = TimerState.STOPPED
        self.mode: Mode = Mode.POMODORO
        self.phase: Phase = Phase.FOCUS
        self.subject_id: int | None = None

        self._focus_ns: int = self._settings.pomodoro_focus_min * 60 * NS
        self._break_ns: int = self._settings.pomodoro_break_min * 60 * NS
        self._afk_timeout_ms: int = self._settings.afk_timeout_min * 60 * 1_000

        self._seg: Segment | None = None
        self._prev_seg: Segment | None = None
        self._completed_chain_ns: int = 0
        self._cum_credit_ns: int = 0
        self._phase_elapsed_ns: int = 0

        self._last_mono: int = 0
        self._last_ckpt_mono: int = 0
        self._last_idle_ms: int = 0
        self._last_emitted_display_s: int = -1
        self._last_split_mono: int | None = None

        self._afk: AfkSnapshot | None = None
        self._timeline = CreditTimeline(retention_seconds=self._settings.afk_timeout_min * 60 + 120)

    def _apply_phase_durations(self) -> None:
        self._focus_ns = max(1, int(self._settings.pomodoro_focus_min)) * 60 * NS
        self._break_ns = max(1, int(self._settings.pomodoro_break_min)) * 60 * NS
        self._afk_timeout_ms = max(1, int(self._settings.afk_timeout_min)) * 60 * 1_000
        self._timeline.set_retention_seconds(self._settings.afk_timeout_min * 60 + 120)

    def update_settings(self, s: TimerSettings) -> None:
        """타이머 설정을 변경한다. AFK 임계값은 즉시 반영하고 집중/휴식 길이는 다음 페이즈부터 반영한다."""
        self._settings = s
        self._afk_timeout_ms = max(1, int(s.afk_timeout_min)) * 60 * 1_000
        self._timeline.set_retention_seconds(s.afk_timeout_min * 60 + 120)
        if self.state is TimerState.STOPPED:
            self._apply_phase_durations()

    def display_seconds(self) -> int:
        """현재 세션 체인 전체의 인정 학습 시간(초). 자정이 지나도 0으로 리셋되지 않는다."""
        if self._seg is None:
            return 0
        return (self._completed_chain_ns // NS) + (self._seg.credited_ns // NS)

    def phase_remaining_seconds(self) -> int | None:
        if self.state is TimerState.STOPPED or self.mode is not Mode.POMODORO:
            return None
        target = self._focus_ns if self.phase is Phase.FOCUS else self._break_ns
        remain_ns = max(0, target - self._phase_elapsed_ns)
        return (remain_ns + NS - 1) // NS

    def live_credit(self) -> tuple[int, date, int] | None:
        """통계 화면에서 진행 중인 세그먼트를 실시간 합산하기 위한 (subject_id, local_date, 초) 튜플."""
        if self.state is TimerState.STOPPED or self._seg is None or self.subject_id is None:
            return None
        return (self.subject_id, self._seg.local_date, self._seg.credited_ns // NS)

    def can_include_afk(self) -> bool:
        """AFK 도중 자정 분할이 1회 이하일 때만 [포함]을 허용한다."""
        if self._afk is None:
            return False
        return self._afk.splits <= 1

    # --- 명령 ---
    def start(self, subject_id: int, mode: Mode) -> None:
        if self.state is not TimerState.STOPPED:
            return
        self._apply_phase_durations()
        mono = self.clock.mono_ns()
        wall = self.clock.now_local()

        try:
            row = self.repo.create_chain(int(subject_id), mode.value, iso(wall), wall.date())
        except Exception as exc:
            logger.error("Failed to create session chain: %s", exc)
            self.emit(StorageError(str(exc)))
            return

        self.subject_id = int(subject_id)
        self.mode = mode
        self.phase = Phase.FOCUS
        self.state = TimerState.RUNNING

        self._seg = Segment(
            row_id=row.id,
            chain_id=row.chain_id,
            segment_no=row.segment_no,
            local_date=wall.date(),
            credited_ns=0,
            row=row,
        )
        self._prev_seg = None
        self._completed_chain_ns = 0
        self._cum_credit_ns = 0
        self._phase_elapsed_ns = 0
        self._last_mono = mono
        self._last_ckpt_mono = mono
        self._last_idle_ms = 0
        self._last_emitted_display_s = 0
        self._last_split_mono = None
        self._afk = None

        self._timeline.clear()
        self._timeline.record(mono, 0, self.phase, 0)
        self.emit(Started(self.subject_id, self.mode, self.phase))
        self.emit(Ticked(0, self.phase_remaining_seconds()))

    def pause(self) -> None:
        if self.state is not TimerState.RUNNING:
            return
        mono = self.clock.mono_ns()
        wall = self.clock.now_local()
        self.state = TimerState.PAUSED
        self._last_mono = mono
        self._checkpoint(mono, wall)
        self.emit(Paused())

    def resume(self) -> None:
        if self.state is not TimerState.PAUSED:
            return
        mono = self.clock.mono_ns()
        self.state = TimerState.RUNNING
        self._last_mono = mono
        self._last_idle_ms = 0
        self._timeline.clear()
        self._timeline.record(mono, self._cum_credit_ns, self.phase, self._phase_elapsed_ns)
        self.emit(Resumed())

    def stop(self) -> None:
        if self.state not in ACTIVE_STATES or self._seg is None:
            return
        mono = self.clock.mono_ns()
        wall = self.clock.now_local()
        if self.state is TimerState.PAUSED_AFK:
            # AFK 상태에서 바로 종료 시 자리 비운 시간은 제외된 상태 그대로 확정
            self._afk = None
        self._checkpoint(mono, wall)
        self.state = TimerState.FINALIZING
        self.emit(FinalizeRequested(self.display_seconds()))

    def _reset_to_stopped(self) -> None:
        self.state = TimerState.STOPPED
        self._seg = None
        self._prev_seg = None
        self._afk = None
        self._timeline.clear()

    def checkpoint_now(self) -> None:
        """종료·세션 종료 직전 강제 체크포인트 (H1·H6)."""
        if self.state in ACTIVE_STATES and self._seg is not None:
            self._checkpoint(self.clock.mono_ns(), self.clock.now_local())

    def switch_subject(self, new_subject_id: int) -> None:
        """학습 중 과목 변경 (H3). 메모 창 없이 현재 체인을 확정하고 같은 모드로 새 체인을 시작한다."""
        if self.state not in (TimerState.RUNNING, TimerState.PAUSED) or self._seg is None:
            return
        if int(new_subject_id) == self.subject_id:
            return
        mode, total_s = self.mode, self.display_seconds()
        prev_subject = int(self.subject_id or 0)
        if total_s == 0 and self._seg.segment_no == 1:
            try:
                self.repo.delete_segment(self._seg.row_id)
            except Exception as exc:
                logger.error("Failed to delete 0-second segment on switch: %s", exc)
                self.emit(StorageError(str(exc)))
                return
            self._reset_to_stopped()
        else:
            prev_state = self.state
            self.state = TimerState.FINALIZING
            self.finalize("", silent=True)
            if self.state is TimerState.FINALIZING:
                # 저장 실패(StorageError 발행됨): 메모 창 없는 FINALIZING에 갇히지 않도록 이전 상태로 되돌린다
                self.state = prev_state
                return
        self.start(int(new_subject_id), mode)
        if self.state is TimerState.STOPPED:
            # 새 체인 생성 실패(StorageError 발행됨): 전환 완료 토스트를 띄우지 않는다
            return
        self.emit(SubjectSwitched(prev_subject, int(new_subject_id), total_s))

    def finalize(self, memo: str = "", silent: bool = False) -> None:
        if self.state is not TimerState.FINALIZING or self._seg is None:
            return
        wall = self.clock.now_local()
        total_s = self.display_seconds()
        clean_memo = memo.strip()[:200]
        try:
            self.repo.finalize_chain(
                self._seg.chain_id,
                self._seg.row_id,
                iso(wall),
                self._seg.credited_ns // NS,
                clean_memo,
            )
        except Exception as exc:
            logger.error("Failed to finalize chain: %s", exc)
            self.emit(StorageError(str(exc)))
            return

        self._reset_to_stopped()
        if not silent:
            self.emit(Finished(total_s))

    # --- 알고리즘 1: 틱과 크레딧 누적 ---
    def tick(self) -> None:
        if self.state not in ACTIVE_STATES or self._seg is None:
            return
        mono = self.clock.mono_ns()
        wall = self.clock.now_local()
        delta = mono - self._last_mono
        self._last_mono = mono

        if delta < 0 or delta > MAX_TICK_GAP_NS:
            logger.warning("Abnormal tick gap ignored: %d ns", delta)
            delta = 0

        # 자정 경계를 가로지르는 틱인 경우 자정 전/후로 delta를 정확히 배분한다
        if wall.date() != self._seg.local_date:
            midnight = datetime.combine(wall.date(), time(0), tzinfo=wall.tzinfo)
            after_s = (wall - midnight).total_seconds()
            after_ns = max(0, min(delta, int(round(after_s * NS)))) if delta > 0 else 0
            before_ns = delta - after_ns

            if self.state is TimerState.RUNNING and before_ns > 0:
                self._advance(before_ns)
                self._timeline.record(mono - after_ns, self._cum_credit_ns, self.phase, self._phase_elapsed_ns)

            self._split_at_midnight(mono - after_ns, wall)

            if self.state is TimerState.RUNNING and after_ns > 0:
                self._advance(after_ns)
                self._timeline.record(mono, self._cum_credit_ns, self.phase, self._phase_elapsed_ns)
        else:
            if self.state is TimerState.RUNNING and delta > 0:
                self._advance(delta)
                self._timeline.record(mono, self._cum_credit_ns, self.phase, self._phase_elapsed_ns)

        if mono - self._last_ckpt_mono >= CHECKPOINT_NS:
            self._checkpoint(mono, wall)

        self._emit_tick_if_changed()

    def _advance(self, delta: int) -> None:
        if self.mode is Mode.STOPWATCH:
            self._credit(delta)
            return

        while delta > 0:
            target = self._focus_ns if self.phase is Phase.FOCUS else self._break_ns
            step = min(delta, target - self._phase_elapsed_ns)
            if self.phase is Phase.FOCUS:
                self._credit(step)
            self._phase_elapsed_ns += step
            delta -= step
            if self._phase_elapsed_ns >= target:
                # 다음 페이즈 전환 시 새 설정값 반영
                self._apply_phase_durations()
                self.phase = Phase.BREAK if self.phase is Phase.FOCUS else Phase.FOCUS
                self._phase_elapsed_ns = 0
                self.emit(PhaseChanged(self.phase))

    def _credit(self, ns: int, target_seg: Segment | None = None) -> None:
        seg = target_seg if target_seg is not None else self._seg
        if seg is not None:
            seg.credited_ns += ns
        self._cum_credit_ns += ns

    def _emit_tick_if_changed(self) -> None:
        disp = self.display_seconds()
        if disp != self._last_emitted_display_s:
            self._last_emitted_display_s = disp
            self.emit(Ticked(disp, self.phase_remaining_seconds()))

    # --- 알고리즘 2: 체크포인트 ---
    def _checkpoint(self, mono: int, wall: datetime) -> None:
        if self._seg is None:
            return
        dur_ns = self._seg.credited_ns
        if self._last_idle_ms >= SUSPECT_IDLE_MS and self.state is TimerState.RUNNING:
            mark = self._timeline.at(mono - self._last_idle_ms * 1_000_000)
            suspect = max(0, self._cum_credit_ns - mark.cum_credit_ns)
            dur_ns = max(0, dur_ns - suspect)
        try:
            self.repo.checkpoint(self._seg.row_id, iso(wall), dur_ns // NS)
            self._last_ckpt_mono = mono
        except Exception as exc:
            logger.error("Checkpoint failed: %s", exc)
            self.emit(StorageError(str(exc)))

    # --- 알고리즘 3: 자정 분할 (세션 체인) ---
    def _split_at_midnight(self, mono: int, wall: datetime) -> None:
        if self._seg is None:
            return
        midnight = datetime.combine(wall.date(), time(0), tzinfo=wall.tzinfo)
        prev = self._seg
        prev_sec = prev.credited_ns // NS
        try:
            self.repo.complete_segment(prev.row_id, iso(midnight), prev_sec)
            row = self.repo.create_next_segment(prev.row, iso(midnight), wall.date())
        except Exception as exc:
            logger.error("Midnight split failed: %s", exc)
            self.emit(StorageError(str(exc)))
            return

        self._prev_seg = prev
        self._completed_chain_ns += prev_sec * NS
        self._last_split_mono = mono
        self._seg = Segment(
            row_id=row.id,
            chain_id=prev.chain_id,
            segment_no=prev.segment_no + 1,
            local_date=wall.date(),
            credited_ns=0,
            row=row,
        )
        if self.state is TimerState.PAUSED_AFK and self._afk is not None:
            self._afk.splits += 1
            self._afk.split_mono = mono

    # --- 알고리즘 4: AFK 진입 및 복귀 감지 ---
    def on_idle_poll(self, idle_ms: int) -> None:
        prev_idle = self._last_idle_ms
        self._last_idle_ms = int(idle_ms)
        mono = self.clock.mono_ns()
        wall = self.clock.now_local()

        if self.state is TimerState.RUNNING and idle_ms >= self._afk_timeout_ms:
            self._enter_afk(idle_ms, mono, wall, check_break_only=True)
        elif (
            self.state is TimerState.PAUSED_AFK
            and self._afk is not None
            and not self._afk.return_pending
            and idle_ms < prev_idle
        ):
            self._trigger_afk_return(mono, wall)

    def _enter_afk(self, idle_ms: int, mono: int, wall: datetime, check_break_only: bool) -> None:
        if self._seg is None:
            return
        input_mono = mono - int(idle_ms) * 1_000_000
        mark = self._timeline.at(input_mono)
        rollback = max(0, self._cum_credit_ns - mark.cum_credit_ns)
        if check_break_only and self.mode is Mode.POMODORO and rollback == 0 and self.phase is Phase.BREAK:
            return  # 휴식 중 자리 비움은 정상 — AFK로 보지 않음

        self._rollback(rollback)
        self.phase = mark.phase
        self._phase_elapsed_ns = mark.phase_elapsed_ns
        start_wall = wall - timedelta(milliseconds=int(idle_ms))
        pre_splits = max(0, (wall.date() - start_wall.date()).days)
        split_mono = (
            self._last_split_mono
            if pre_splits == 1 and self._last_split_mono is not None and self._last_split_mono >= input_mono
            else None
        )
        self._afk = AfkSnapshot(
            start_mono=input_mono,
            start_wall=start_wall,
            phase=mark.phase,
            phase_elapsed_ns=mark.phase_elapsed_ns,
            split_mono=split_mono,
            splits=pre_splits,
        )
        self.state = TimerState.PAUSED_AFK
        self._checkpoint(mono, wall)
        self._emit_tick_if_changed()
        self.emit(AfkStarted())

    def _rollback(self, ns: int) -> None:
        if self._seg is None or ns <= 0:
            return
        take = min(ns, self._seg.credited_ns)
        self._seg.credited_ns -= take
        rest = ns - take
        if rest > 0 and self._prev_seg is not None:
            deduct_s = (rest + NS - 1) // NS
            actual_deduct_s = min(deduct_s, self._prev_seg.credited_ns // NS)
            try:
                self.repo.add_duration(self._prev_seg.row_id, -actual_deduct_s)
            except Exception as exc:
                logger.error("Failed to rollback previous segment: %s", exc)
                self.emit(StorageError(str(exc)))
            self._prev_seg.credited_ns = max(0, self._prev_seg.credited_ns - rest)
            self._completed_chain_ns = max(0, self._completed_chain_ns - actual_deduct_s * NS)
        self._cum_credit_ns = max(0, self._cum_credit_ns - ns)

    def _trigger_afk_return(self, mono: int, wall: datetime) -> None:
        if self._afk is None:
            return
        # 복귀 시점에 날짜가 바뀌어 있고 아직 분할되지 않았다면 분할 수행
        if self._seg is not None and wall.date() != self._seg.local_date:
            self._split_at_midnight(mono, wall)
        self._afk.return_pending = True
        away_wall_s = max(0, int((wall - self._afk.start_wall).total_seconds()))
        away_awake_s = max(0, (mono - self._afk.start_mono) // NS)
        self.emit(AfkReturned(away_wall_s, away_awake_s, self.can_include_afk()))

    def on_session_lock(self) -> None:
        if self.state is TimerState.RUNNING:
            mono = self.clock.mono_ns()
            wall = self.clock.now_local()
            self._enter_afk(self._last_idle_ms, mono, wall, check_break_only=False)

    def on_session_unlock(self) -> None:
        if self.state is TimerState.PAUSED_AFK and self._afk is not None and not self._afk.return_pending:
            mono = self.clock.mono_ns()
            wall = self.clock.now_local()
            self._trigger_afk_return(mono, wall)

    def on_suspend(self) -> None:
        if self.state is TimerState.RUNNING:
            mono = self.clock.mono_ns()
            wall = self.clock.now_local()
            self._enter_afk(self._last_idle_ms, mono, wall, check_break_only=False)

    # --- 알고리즘 5: AFK 해소 ---
    def resolve_afk(self, include: bool) -> None:
        if self.state is not TimerState.PAUSED_AFK or self._afk is None or self._seg is None:
            return
        mono = self.clock.mono_ns()
        wall = self.clock.now_local()
        if wall.date() != self._seg.local_date:
            self._split_at_midnight(mono, wall)

        afk = self._afk
        if include and self.can_include_afk():
            if afk.splits == 0:
                self._simulate(max(0, mono - afk.start_mono), target=self._seg, persist=False)
            elif afk.splits == 1 and afk.split_mono is not None and self._prev_seg is not None:
                self._simulate(max(0, afk.split_mono - afk.start_mono), target=self._prev_seg, persist=True)
                self._simulate(max(0, mono - afk.split_mono), target=self._seg, persist=False)

        self.state = TimerState.RUNNING
        self._afk = None
        self._last_mono = mono
        self._last_idle_ms = 0
        self._timeline.clear()
        self._timeline.record(mono, self._cum_credit_ns, self.phase, self._phase_elapsed_ns)
        self._checkpoint(mono, wall)
        self.emit(Resumed())
        self._emit_tick_if_changed()

    def _simulate(self, ns: int, target: Segment, persist: bool = False) -> None:
        if ns <= 0:
            return
        before_ns = target.credited_ns
        if self.mode is Mode.STOPWATCH:
            self._credit(ns, target_seg=target)
        else:
            rem = ns
            while rem > 0:
                phase_len = self._focus_ns if self.phase is Phase.FOCUS else self._break_ns
                step = min(rem, phase_len - self._phase_elapsed_ns)
                if self.phase is Phase.FOCUS:
                    self._credit(step, target_seg=target)
                self._phase_elapsed_ns += step
                rem -= step
                if self._phase_elapsed_ns >= phase_len:
                    self._apply_phase_durations()
                    self.phase = Phase.BREAK if self.phase is Phase.FOCUS else Phase.FOCUS
                    self._phase_elapsed_ns = 0
                    self.emit(PhaseChanged(self.phase))

        if persist:
            added_s = (target.credited_ns // NS) - (before_ns // NS)
            if added_s > 0:
                try:
                    self.repo.add_duration(target.row_id, added_s)
                    self._completed_chain_ns += added_s * NS
                except Exception as exc:
                    logger.error("Failed to persist simulated AFK duration: %s", exc)
                    self.emit(StorageError(str(exc)))

    # --- 알고리즘 6: 크래시 복구 ---
    def recover(self, row: SegmentRowLike, action: RecoverAction, memo: str = "") -> None:
        mono = self.clock.mono_ns()
        wall = self.clock.now_local()
        today = wall.date()

        try:
            if action is RecoverAction.DISCARD:
                self.repo.delete_segment(row.id)
                self.emit(Recovered(RecoverAction.DISCARD, row.subject_id, 0))
                return

            if action is RecoverAction.SAVE:
                self.repo.complete_segment(row.id, row.end_time, row.duration_seconds)
                if memo.strip():
                    self.repo.update_chain_memo(row.chain_id, memo.strip()[:200])
                total_s = self.repo.chain_completed_seconds(row.chain_id)
                self.emit(Recovered(RecoverAction.SAVE, row.subject_id, total_s))
                return

            # CONTINUE
            self._apply_phase_durations()
            prior_s = self.repo.chain_completed_seconds(row.chain_id)
            row_date = date.fromisoformat(row.local_date)
            if row_date == today:
                self._completed_chain_ns = prior_s * NS
                self._seg = Segment(
                    row_id=row.id,
                    chain_id=row.chain_id,
                    segment_no=row.segment_no,
                    local_date=today,
                    credited_ns=row.duration_seconds * NS,
                    row=row,
                )
            else:
                self.repo.complete_segment(row.id, row.end_time, row.duration_seconds)
                next_row = self.repo.create_next_segment(row, iso(wall), today)
                self._completed_chain_ns = (prior_s + row.duration_seconds) * NS
                self._seg = Segment(
                    row_id=next_row.id,
                    chain_id=next_row.chain_id,
                    segment_no=next_row.segment_no,
                    local_date=today,
                    credited_ns=0,
                    row=next_row,
                )

            self._prev_seg = None
            self.subject_id = int(row.subject_id)
            self.mode = Mode(row.mode)
            self.phase = Phase.FOCUS
            self._phase_elapsed_ns = 0
            self._cum_credit_ns = self._completed_chain_ns + self._seg.credited_ns
            self.state = TimerState.RUNNING
            self._last_mono = mono
            self._last_ckpt_mono = mono
            self._last_idle_ms = 0
            self._last_emitted_display_s = self.display_seconds()
            self._afk = None

            self._timeline.clear()
            self._timeline.record(mono, self._cum_credit_ns, self.phase, 0)
            self.emit(Recovered(RecoverAction.CONTINUE, self.subject_id, self.display_seconds()))
            self.emit(Started(self.subject_id, self.mode, self.phase))
            self.emit(Ticked(self.display_seconds(), self.phase_remaining_seconds()))
        except Exception as exc:
            logger.error("Failed to recover session %d: %s", row.id, exc)
            self.emit(StorageError(str(exc)))
