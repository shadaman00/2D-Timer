"""펫 자율 행동 상태 머신(FSM) (DEVELOPMENT_PLAN.md 4-10)."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import random


class PetState(Enum):
    IDLE = "idle"
    WALK = "walk"
    SIT = "sit"
    SLEEP = "sleep"
    DRAG = "drag"
    FALL = "fall"
    LAND = "land"
    STUDY = "study"
    CELEBRATE = "celebrate"


@dataclass(frozen=True)
class FsmContext:
    studying: bool
    on_ground: bool
    walk_enabled: bool
    user_idle_ms: int


class PetFSM:
    """DOM/Win32에 의존하지 않는 순수 도메인 캐릭터 상태 머신."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng: random.Random = rng if rng is not None else random.Random()
        self.state: PetState = PetState.IDLE
        self.facing: int = -1  # -1 왼쪽, +1 오른쪽
        self._studying: bool = False
        self._elapsed: float = 0.0
        self._duration: float = self._roll_duration(PetState.IDLE)

    def _roll_duration(self, state: PetState) -> float:
        if state is PetState.IDLE:
            return self._rng.uniform(2.0, 8.0)
        if state is PetState.WALK:
            return self._rng.uniform(3.0, 10.0)
        if state in (PetState.SIT, PetState.SLEEP):
            return self._rng.uniform(5.0, 20.0)
        if state is PetState.LAND:
            return 0.25
        if state is PetState.CELEBRATE:
            return 2.0
        return 999999.0

    def _transition(self, next_state: PetState) -> None:
        self.state = next_state
        self._elapsed = 0.0
        self._duration = self._roll_duration(next_state)

    def _pick_next_from_idle(self, ctx: FsmContext) -> PetState:
        if ctx.user_idle_ms >= 180_000:
            weights = [
                (PetState.SLEEP, 40),
                (PetState.SIT, 30),
                (PetState.IDLE, 20),
                (PetState.WALK, 10 if ctx.walk_enabled else 0),
            ]
        else:
            weights = [
                (PetState.WALK, 40 if ctx.walk_enabled else 0),
                (PetState.IDLE, 30),
                (PetState.SIT, 20),
                (PetState.SLEEP, 10),
            ]

        total = sum(w for _, w in weights)
        pick = self._rng.uniform(0.0, float(total))
        acc = 0.0
        chosen = PetState.IDLE
        for st, w in weights:
            if w <= 0:
                continue
            acc += w
            if pick <= acc:
                chosen = st
                break

        if chosen is PetState.WALK:
            self.facing = self._rng.choice([-1, 1])
        return chosen

    def update(self, dt: float, ctx: FsmContext) -> None:
        self._studying = ctx.studying
        if dt <= 0.0:
            return

        if self.state in (PetState.DRAG, PetState.FALL):
            return

        if ctx.studying and self.state not in (PetState.STUDY, PetState.LAND, PetState.CELEBRATE):
            self._transition(PetState.STUDY)
            return

        if self.state is PetState.WALK and not ctx.walk_enabled:
            self._transition(PetState.IDLE)
            return

        self._elapsed += dt
        if self._elapsed < self._duration:
            return

        if self.state is PetState.IDLE:
            nxt = self._pick_next_from_idle(ctx)
            self._transition(nxt)
        elif self.state in (PetState.WALK, PetState.SIT, PetState.SLEEP):
            self._transition(PetState.IDLE)
        elif self.state is PetState.LAND:
            self._transition(PetState.STUDY if self._studying else PetState.IDLE)
        elif self.state is PetState.CELEBRATE:
            self._transition(PetState.STUDY if self._studying else PetState.IDLE)

    def on_drag_start(self) -> None:
        self._transition(PetState.DRAG)

    def on_drag_end(self, airborne: bool) -> None:
        if airborne:
            self._transition(PetState.FALL)
        else:
            self._transition(PetState.STUDY if self._studying else PetState.IDLE)

    def on_landed(self) -> None:
        if self.state is PetState.FALL:
            self._transition(PetState.LAND)

    def on_click(self) -> None:
        if self.state in (PetState.SIT, PetState.SLEEP):
            self._transition(PetState.STUDY if self._studying else PetState.IDLE)

    def on_study_started(self) -> None:
        self._studying = True
        if self.state not in (PetState.DRAG, PetState.FALL):
            self._transition(PetState.STUDY)

    def on_study_stopped(self) -> None:
        self._studying = False
        if self.state is PetState.STUDY:
            self._transition(PetState.IDLE)

    def on_finished(self) -> None:
        self._studying = False
        self._transition(PetState.CELEBRATE)

    def animation_key(self) -> str:
        return self.state.value

