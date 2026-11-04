"""infra/db.py 단위 테스트 (DEVELOPMENT_PLAN.md 7-1)."""
from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest

from studypet.infra.db import Database


class TestDatabase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = Database.open(":memory:")

    def tearDown(self) -> None:
        self.db.close()

    def test_schema_v1_and_user_version(self) -> None:
        self.assertEqual(self.db.user_version(), 1)
        sub_id = self.db.subjects.ensure_default_subject("2026-11-03T10:00:00+09:00")
        self.assertEqual(sub_id, 1)
        sub = self.db.subjects.get(sub_id)
        assert sub is not None
        self.assertEqual(sub.name, "자유 학습")
        self.assertEqual(sub.color_code, "#4F46E5")
        self.assertEqual(sub.daily_goal_minutes, 60)
        self.assertFalse(sub.is_archived)

        # CHECK 제약조건 검증 (빈 이름, 잘못된 색상코드, 범위 밖 목표시간 거부)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.subjects.create("   ", "#4F46E5", 60)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.subjects.create("알고리즘", "INVALID", 60)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.subjects.create("알고리즘", "#112233", 0)

    def test_create_chain_and_segments(self) -> None:
        sub_id = self.db.subjects.ensure_default_subject("2026-11-03T10:00:00+09:00")
        start_iso = "2026-11-03T23:50:00+09:00"
        seg1 = self.db.sessions.create_chain(sub_id, "POMODORO", start_iso, "2026-11-03")
        self.assertEqual(seg1.chain_id, seg1.id)
        self.assertEqual(seg1.segment_no, 1)
        self.assertEqual(seg1.start_time, start_iso)
        self.assertEqual(seg1.end_time, start_iso)  # end_time == start_time (C3 수정 검증)
        self.assertEqual(seg1.duration_seconds, 0)
        self.assertFalse(seg1.is_completed)
        self.assertEqual(seg1.subject_name, "자유 학습")

        # 체크포인트 갱신
        self.db.sessions.checkpoint(seg1.id, "2026-11-03T23:55:00+09:00", 300)
        seg1_ckpt = self.db.sessions.get_segment(seg1.id)
        assert seg1_ckpt is not None
        self.assertEqual(seg1_ckpt.duration_seconds, 300)
        self.assertEqual(seg1_ckpt.end_time, "2026-11-03T23:55:00+09:00")

        # 자정 분할 세그먼트 확정 및 다음 세그먼트 생성
        midnight_iso = "2026-11-04T00:00:00+09:00"
        self.db.sessions.complete_segment(seg1.id, midnight_iso, 600)
        seg2 = self.db.sessions.create_next_segment(seg1, midnight_iso, "2026-11-04")
        self.assertEqual(seg2.chain_id, seg1.chain_id)
        self.assertEqual(seg2.segment_no, 2)
        self.assertEqual(seg2.start_time, midnight_iso)
        self.assertEqual(seg2.end_time, midnight_iso)
        self.assertEqual(self.db.sessions.chain_completed_seconds(seg1.chain_id), 600)

        # finalize_chain 호출 시 체인 전체 행에 동일한 메모가 기록되어야 함
        self.db.sessions.finalize_chain(
            seg1.chain_id,
            seg2.id,
            "2026-11-04T00:20:00+09:00",
            1200,
            "DP 문제 3개 풀이 완료",
        )
        chain_rows = self.db.sessions.list_by_chain(seg1.chain_id)
        self.assertEqual(len(chain_rows), 2)
        for r in chain_rows:
            self.assertTrue(r.is_completed)
            self.assertEqual(r.memo, "DP 문제 3개 풀이 완료")

    def test_add_duration_lower_bound_and_delete_open_only(self) -> None:
        sub_id = self.db.subjects.ensure_default_subject()
        seg = self.db.sessions.create_chain(sub_id, "STOPWATCH", "2026-11-03T12:00:00+09:00", "2026-11-03")
        self.db.sessions.checkpoint(seg.id, "2026-11-03T12:05:00+09:00", 300)

        # 음수 차감이 현재 값을 초과해도 0 하한 유지
        self.db.sessions.add_duration(seg.id, -500)
        updated = self.db.sessions.get_segment(seg.id)
        assert updated is not None
        self.assertEqual(updated.duration_seconds, 0)

        self.db.sessions.add_duration(seg.id, 180)
        updated2 = self.db.sessions.get_segment(seg.id)
        assert updated2 is not None
        self.assertEqual(updated2.duration_seconds, 180)

        # 완료된 세그먼트는 delete_segment로 삭제되지 않아야 함
        self.db.sessions.complete_segment(seg.id, "2026-11-03T12:03:00+09:00", 180)
        self.db.sessions.delete_segment(seg.id)
        self.assertIsNotNone(self.db.sessions.get_segment(seg.id))

        # 미완료 세그먼트는 삭제됨
        open_seg = self.db.sessions.create_chain(sub_id, "STOPWATCH", "2026-11-03T14:00:00+09:00", "2026-11-03")
        self.assertEqual(len(self.db.sessions.get_open_segments()), 1)
        self.db.sessions.delete_segment(open_seg.id)
        self.assertIsNone(self.db.sessions.get_segment(open_seg.id))
        self.assertEqual(len(self.db.sessions.get_open_segments()), 0)

    def test_period_totals_archived_subject_inclusion_rules(self) -> None:
        s_active = self.db.subjects.create("운영체제", "#4F46E5", 60, "2026-11-01T09:00:00+09:00")
        s_arch_with_log = self.db.subjects.create("네트워크", "#10B981", 40, "2026-11-01T09:00:00+09:00")
        s_arch_empty = self.db.subjects.create("이전과목", "#F59E0B", 30, "2026-11-01T09:00:00+09:00")

        # s_arch_with_log에 완료된 세션 1건 추가 후 보관 처리
        seg = self.db.sessions.create_chain(
            s_arch_with_log.id,
            "STOPWATCH",
            "2026-11-03T10:00:00+09:00",
            "2026-11-03",
        )
        self.db.sessions.finalize_chain(
            seg.chain_id,
            seg.id,
            "2026-11-03T10:30:00+09:00",
            1800,
            "TCP/IP 정리",
        )
        self.db.subjects.set_archived(s_arch_with_log.id, True)
        self.db.subjects.set_archived(s_arch_empty.id, True)

        totals = self.db.stats.period_totals("2026-11-03", "2026-11-03")
        ids = [t.subject_id for t in totals]
        # 기록 있는 보관 과목과 활성 과목(0초라도)은 포함, 기록 없는 보관 과목은 제외
        self.assertIn(s_arch_with_log.id, ids)
        self.assertIn(s_active.id, ids)
        self.assertNotIn(s_arch_empty.id, ids)
        self.assertEqual(totals[0].subject_id, s_arch_with_log.id)
        self.assertEqual(totals[0].total_seconds, 1800)

    def test_file_db_wal_checkpoint_on_close(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "study_records.db"
            fdb = Database.open(db_path)
            sid = fdb.subjects.ensure_default_subject()
            seg = fdb.sessions.create_chain(sid, "STOPWATCH", "2026-11-03T10:00:00+09:00", "2026-11-03")
            fdb.sessions.finalize_chain(seg.chain_id, seg.id, "2026-11-03T10:10:00+09:00", 600, "메모")
            fdb.close()
            self.assertTrue(db_path.exists())


if __name__ == "__main__":
    unittest.main()

