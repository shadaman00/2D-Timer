"""펫 물리 엔진(경계 반전, 종단 속도, 공중 판정) 단위 테스트 (DEVELOPMENT_PLAN.md 7-1)."""
from __future__ import annotations

import unittest

from studypet.domain.pet_fsm import PetState
from studypet.domain.physics import MAX_FALL_SPEED_SP, PetPhysics, WorkBounds


class TestPhysics(unittest.TestCase):
    def test_walk_boundary_reversal(self) -> None:
        work = WorkBounds(left=0, top=0, right=1000, bottom=800)
        phys = PetPhysics(foot_x=70.0, foot_y=800.0)
        # scale=2일 때 min_x = 0 + 32*2 = 64. 왼쪽(-1)으로 1초 이동(30*2 = 60px)하면 64에서 반전(+1)되어야 함
        facing, landed = phys.step(1.0, PetState.WALK, -1, work, phys_scale=2)
        self.assertEqual(facing, 1)
        self.assertFalse(landed)
        self.assertEqual(phys.foot_x, 64.0)

        # 오른쪽 경계(1000 - 64 = 936) 반전 테스트
        phys.foot_x = 930.0
        facing, landed = phys.step(1.0, PetState.WALK, 1, work, phys_scale=2)
        self.assertEqual(facing, -1)
        self.assertEqual(phys.foot_x, 936.0)

    def test_fall_terminal_velocity_and_landing(self) -> None:
        work = WorkBounds(left=0, top=0, right=1920, bottom=5000)
        phys = PetPhysics(foot_x=500.0, foot_y=300.0)
        self.assertTrue(phys.is_airborne(work))

        # 2초 낙하 시 중력 900 sp/s^2로 가속하되 종단 속도 600 sp/s 상한 적용 확인
        for _ in range(20):
            _, landed = phys.step(0.1, PetState.FALL, 1, work, phys_scale=2)
            self.assertLessEqual(phys.vy_sp, MAX_FALL_SPEED_SP)

        # 바닥 도달 시 착지 이벤트(landed=True) 확인
        phys.foot_y = 4990.0
        _, landed = phys.step(0.1, PetState.FALL, 1, work, phys_scale=2)
        self.assertTrue(landed)
        self.assertEqual(phys.foot_y, 5000.0)
        self.assertEqual(phys.vy_sp, 0.0)


if __name__ == "__main__":
    unittest.main()

