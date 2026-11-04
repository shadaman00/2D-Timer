"""타이머 엔진 -> UI 이벤트 정의 (DEVELOPMENT_PLAN.md 4-7)."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TimerState(Enum):
    STOPPED = "STOPPED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    PAUSED_AFK = "PAUSED_AFK"
    FINALIZING = "FINALIZING"


class Mode(Enum):
    STOPWATCH = "STOPWATCH"
    POMODORO = "POMODORO"


class Phase(Enum):
    FOCUS = "FOCUS"
    BREAK = "BREAK"


class RecoverAction(Enum):
    CONTINUE = "CONTINUE"
    SAVE = "SAVE"
    DISCARD = "DISCARD"


@dataclass(frozen=True)
class Event:
    pass


@dataclass(frozen=True)
class Started(Event):
    subject_id: int
    mode: Mode
    phase: Phase


@dataclass(frozen=True)
class Ticked(Event):
    display_s: int
    phase_remaining_s: int | None = None


@dataclass(frozen=True)
class PhaseChanged(Event):
    phase: Phase


@dataclass(frozen=True)
class Paused(Event):
    pass


@dataclass(frozen=True)
class Resumed(Event):
    pass


@dataclass(frozen=True)
class AfkStarted(Event):
    pass


@dataclass(frozen=True)
class AfkReturned(Event):
    away_wall_s: int
    away_awake_s: int
    can_include: bool


@dataclass(frozen=True)
class FinalizeRequested(Event):
    total_s: int


@dataclass(frozen=True)
class Finished(Event):
    total_s: int


@dataclass(frozen=True)
class Recovered(Event):
    action: RecoverAction
    subject_id: int
    total_s: int


@dataclass(frozen=True)
class StorageError(Event):
    msg: str


@dataclass(frozen=True)
class SubjectSwitched(Event):
    prev_subject_id: int
    new_subject_id: int
    saved_s: int


