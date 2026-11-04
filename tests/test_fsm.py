"""펫 상태 머신(PetFSM) 전이 규칙 단위 테스트 (DEVELOPMENT_PLAN.md 7-1)."""
from __future__ import annotations

import random
import unittest

from studypet.domain.pet_fsm import FsmContext, PetFSM, PetState


class TestPetFSM(unittest.TestCase):
    def test_seeded_transitions_and_walk_disabled(self) -> None:
        fsm = PetFSM(rng=random.Random(42))
        ctx_no_walk = FsmContext(studying=False, on_ground=True, walk_enabled=False, user_idle_ms=0)
        for _ in range(50):
            fsm.update(10.0, ctx_no_walk)
            self.assertNotEqual(fsm.state, PetState.WALK)

    def test_drag_fall_land_transitions(self) -> None:
        fsm = PetFSM(rng=random.Random(7))
        ctx = FsmContext(studying=False, on_ground=True, walk_enabled=True, user_idle_ms=0)
        fsm.on_drag_start()
        self.assertEqual(fsm.state, PetState.DRAG)

        # 공중에서 놓으면 FALL
        fsm.on_drag_end(airborne=True)
        self.assertEqual(fsm.state, PetState.FALL)

        # 착지하면 LAND -> 0.25초 후 IDLE
        fsm.on_landed()
        self.assertEqual(fsm.state, PetState.LAND)
        fsm.update(0.30, ctx)
        self.assertEqual(fsm.state, PetState.IDLE)

    def test_immediate_study_transition_and_celebrate(self) -> None:
        fsm = PetFSM(rng=random.Random(10))
        ctx_walk = FsmContext(studying=False, on_ground=True, walk_enabled=True, user_idle_ms=0)
        fsm.update(9.0, ctx_walk)

        # AC#2: 학습 시작 시 즉시 STUDY 전환
        fsm.on_study_started()
        self.assertEqual(fsm.state, PetState.STUDY)

        # 세션 종료 시 CELEBRATE -> 2초 후 IDLE
        fsm.on_finished()
        self.assertEqual(fsm.state, PetState.CELEBRATE)
        fsm.update(2.1, FsmContext(studying=False, on_ground=True, walk_enabled=True, user_idle_ms=0))
        self.assertEqual(fsm.state, PetState.IDLE)

    def test_click_wakes_from_sit_or_sleep(self) -> None:
        fsm = PetFSM(rng=random.Random(99))
        fsm.state = PetState.SLEEP
        fsm.on_click()
        self.assertEqual(fsm.state, PetState.IDLE)


if __name__ == "__main__":
    unittest.main()

