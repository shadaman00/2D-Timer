"""펫 물리 엔진(보행, 중력 낙하, 모니터 작업 영역 경계 충돌) (DEVELOPMENT_PLAN.md 4-10)."""
from __future__ import annotations

from dataclasses import dataclass

from studypet.domain.pet_fsm import PetState


WALK_SPEED_SP = 30.0
GRAVITY_SP = 900.0
MAX_FALL_SPEED_SP = 600.0
HALF_CHAR_W_SP = 32
CANVAS_H_SP = 144


@dataclass(frozen=True)
class WorkBounds:
    left: int
    top: int
    right: int
    bottom: int


class PetPhysics:
    """물리 픽셀 위치(float) 및 속도(sp/s)를 관리하는 순수 도메인 물리 모듈."""

    def __init__(self, foot_x: float, foot_y: float) -> None:
        self.foot_x: float = float(foot_x)
        self.foot_y: float = float(foot_y)
        self.vy_sp: float = 0.0

    @property
    def screen_foot(self) -> tuple[int, int]:
        return (int(round(self.foot_x)), int(round(self.foot_y)))

    def clamp_to_work(self, work: WorkBounds, phys_scale: int) -> None:
        s = max(1, int(phys_scale))
        min_x = float(work.left + HALF_CHAR_W_SP * s)
        max_x = float(work.right - HALF_CHAR_W_SP * s)
        min_y = float(work.top + CANVAS_H_SP * s)
        max_y = float(work.bottom)

        if min_x <= max_x:
            self.foot_x = max(min_x, min(max_x, self.foot_x))
        if min_y <= max_y:
            self.foot_y = max(min_y, min(max_y, self.foot_y))

    def is_airborne(self, work: WorkBounds) -> bool:
        return self.foot_y < float(work.bottom - 1)

    def snap_to_ground_if_close(self, work: WorkBounds) -> bool:
        """공중이면 True(airborne)를 반환하고, 바닥 근처면 바닥에 맞추고 False를 반환한다."""
        if self.is_airborne(work):
            self.vy_sp = 0.0
            return True
        self.foot_y = float(work.bottom)
        self.vy_sp = 0.0
        return False

    def step(
        self,
        dt: float,
        state: PetState,
        facing: int,
        work: WorkBounds,
        phys_scale: int,
    ) -> tuple[int, bool]:
        """물리 상태를 dt초 진행시키고 (새 facing, 착지 이벤트 발생 여부)를 반환한다."""
        s = max(1, int(phys_scale))
        new_facing = -1 if facing < 0 else 1
        landed = False
        if dt <= 0.0:
            return (new_facing, landed)

        min_x = float(work.left + HALF_CHAR_W_SP * s)
        max_x = float(work.right - HALF_CHAR_W_SP * s)
        ground_y = float(work.bottom)

        if state is PetState.WALK:
            self.foot_x += new_facing * WALK_SPEED_SP * s * dt
            if self.foot_x <= min_x:
                self.foot_x = min_x
                new_facing = 1
            elif self.foot_x >= max_x:
                self.foot_x = max_x
                new_facing = -1
            self.foot_y = ground_y
            self.vy_sp = 0.0

        elif state is PetState.FALL:
            self.vy_sp = min(MAX_FALL_SPEED_SP, self.vy_sp + GRAVITY_SP * dt)
            self.foot_y += self.vy_sp * s * dt
            if self.foot_y >= ground_y:
                self.foot_y = ground_y
                self.vy_sp = 0.0
                landed = True

        elif state is not PetState.DRAG:
            self.foot_y = ground_y
            self.vy_sp = 0.0
            self.clamp_to_work(work, s)

        return (new_facing, landed)

