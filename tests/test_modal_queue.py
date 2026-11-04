"""ui/modals.py ModalQueue 우선순위·대체·강제 종료 기본값 단위 테스트 (REVISION_PLAN_v0.7 4-2, 5장)."""
from __future__ import annotations

from ctypes import wintypes as wt
import unittest

from studypet.ui.modals import ModalQueue, ModalRequest


class TestModalQueue(unittest.TestCase):
    def test_push_shows_immediately_when_idle_and_queues_by_priority(self) -> None:
        q = ModalQueue()
        shown: list[str] = []

        def make_req(kind: str, tag: str) -> ModalRequest:
            return ModalRequest(
                kind=kind,  # type: ignore[arg-type]
                show=lambda: (shown.append(tag) or wt.HWND(1)),
                default=lambda: None,
            )

        q.push(make_req("afk", "afk_1"))
        self.assertEqual(shown, ["afk_1"])
        self.assertIsNotNone(q.active)
        self.assertEqual(q.pending_count, 0)

        # 활성 중에 quit(우선순위 3)과 memo(우선순위 1), recovery(우선순위 0)를 넣으면
        # recovery -> memo -> quit 순서로 정렬되어야 함
        q.push(make_req("quit", "quit_1"))
        q.push(make_req("memo", "memo_1"))
        q.push(make_req("recovery", "rec_1"))
        self.assertEqual(q.pending_count, 3)

        q.on_closed()
        self.assertEqual(shown[-1], "rec_1")
        q.on_closed()
        self.assertEqual(shown[-1], "memo_1")
        q.on_closed()
        self.assertEqual(shown[-1], "quit_1")
        q.on_closed()
        self.assertIsNone(q.active)

    def test_same_kind_in_queue_is_replaced(self) -> None:
        q = ModalQueue()
        shown: list[str] = []

        q.push(ModalRequest("afk", lambda: (shown.append("afk") or wt.HWND(1)), lambda: None))
        q.push(ModalRequest("quit", lambda: (shown.append("quit_old") or wt.HWND(2)), lambda: None))
        q.push(ModalRequest("quit", lambda: (shown.append("quit_new") or wt.HWND(3)), lambda: None))
        self.assertEqual(q.pending_count, 1)

        q.on_closed()
        self.assertEqual(shown, ["afk", "quit_new"])

    def test_flush_defaults_invokes_active_and_pending_defaults(self) -> None:
        q = ModalQueue()
        defaults_called: list[str] = []

        q.push(
            ModalRequest(
                "afk",
                lambda: wt.HWND(10),
                lambda: defaults_called.append("afk_exclude"),
            )
        )
        q.push(
            ModalRequest(
                "quit",
                lambda: wt.HWND(11),
                lambda: defaults_called.append("quit_cancel"),
            )
        )
        q.push(
            ModalRequest(
                "memo",
                lambda: wt.HWND(12),
                lambda: defaults_called.append("memo_save_empty"),
            )
        )

        q.flush_defaults()
        self.assertIsNone(q.active)
        self.assertEqual(q.pending_count, 0)
        # 활성(afk) + 대기열 우선순위 순(memo -> quit) 모두 기본값 콜백이 호출됨
        self.assertEqual(defaults_called, ["afk_exclude", "memo_save_empty", "quit_cancel"])

    def test_shutdown_inside_result_callback_does_not_rerun_finished_modal_default(self) -> None:
        """결과 콜백 안에서 종료(flush_defaults)가 일어나도 방금 끝난 모달의 기본값은 다시 불리지 않는다."""
        q = ModalQueue()
        calls: list[str] = []
        q.push(ModalRequest("quit", lambda: wt.HWND(1), lambda: calls.append("quit_default")))

        q.begin_release()
        calls.append("quit_result")
        q.flush_defaults()  # 콜백에서 shutdown() 호출
        q.end_release()

        self.assertEqual(calls, ["quit_result"])
        self.assertIsNone(q.active)

    def test_push_during_release_respects_priority(self) -> None:
        """콜백 중 들어온 요청도 기존 대기열과 함께 우선순위대로 표시된다."""
        q = ModalQueue()
        shown: list[str] = []
        q.push(ModalRequest("afk", lambda: (shown.append("afk") or wt.HWND(1)), lambda: None))
        q.push(ModalRequest("recovery", lambda: (shown.append("rec") or wt.HWND(2)), lambda: None))

        q.begin_release()
        q.push(ModalRequest("quit", lambda: (shown.append("quit") or wt.HWND(3)), lambda: None))
        self.assertEqual(shown, ["afk"])  # 콜백 실행 중에는 새 창을 만들지 않음
        q.end_release()

        self.assertEqual(shown, ["afk", "rec"])
        q.on_closed()
        self.assertEqual(shown, ["afk", "rec", "quit"])

    def test_push_while_closing_applies_default_without_showing(self) -> None:
        """종료 중 기본값 콜백이 다음 모달을 요청하면(복구 '나중에 결정' → 다음 행) 창 없이 기본값으로 처리한다."""
        q = ModalQueue()
        shown: list[str] = []
        calls: list[str] = []

        def rec_default(tag: str, then: ModalRequest | None) -> None:
            calls.append(tag)
            if then is not None:
                q.push(then)

        second = ModalRequest("recovery", lambda: (shown.append("rec2") or wt.HWND(2)), lambda: rec_default("rec2_later", None))
        first = ModalRequest("recovery", lambda: (shown.append("rec1") or wt.HWND(1)), lambda: rec_default("rec1_later", second))
        q.push(first)

        q.flush_defaults()
        self.assertEqual(shown, ["rec1"])
        self.assertEqual(calls, ["rec1_later", "rec2_later"])
        self.assertIsNone(q.active)

    def test_show_failure_falls_back_to_default_and_unblocks_queue(self) -> None:
        q = ModalQueue()
        calls: list[str] = []

        def boom() -> wt.HWND:
            raise OSError("CreateWindowExW failed")

        q.push(ModalRequest("memo", boom, lambda: calls.append("memo_default")))
        self.assertEqual(calls, ["memo_default"])
        self.assertIsNone(q.active)

        q.push(ModalRequest("quit", lambda: (calls.append("quit_shown") or wt.HWND(1)), lambda: None))
        self.assertEqual(calls, ["memo_default", "quit_shown"])


if __name__ == "__main__":
    unittest.main()

