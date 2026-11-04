"""domain/stats.py 기간 계산, 달성률 분모 및 실시간 병합 테스트 (DEVELOPMENT_PLAN.md 7-1)."""
from __future__ import annotations

from datetime import date
import unittest

from studypet.domain.stats import (
    achievement_pct,
    merge_live,
    overall_pct,
    period_days,
    period_range,
)
from studypet.infra.db import SubjectTotal


class TestStatsDomain(unittest.TestCase):
    def test_period_range_and_days(self) -> None:
        # 2026-11-04 (수요일)
        d = date(2026, 11, 4)
        self.assertEqual(period_range("day", d), (date(2026, 11, 4), date(2026, 11, 4)))
        self.assertEqual(period_days("day", *period_range("day", d)), 1)

        # 주간: 월요일(11/02) ~ 일요일(11/08), 7일
        w_start, w_end = period_range("week", d)
        self.assertEqual(w_start, date(2026, 11, 2))
        self.assertEqual(w_end, date(2026, 11, 8))
        self.assertEqual(period_days("week", w_start, w_end), 7)

        # 월간: 11월은 30일, 평년 2월은 28일, 윤년(2024) 2월은 29일
        m_start, m_end = period_range("month", d)
        self.assertEqual((m_start, m_end), (date(2026, 11, 1), date(2026, 11, 30)))
        self.assertEqual(period_days("month", m_start, m_end), 30)

        feb26_s, feb26_e = period_range("month", date(2026, 2, 15))
        self.assertEqual(period_days("month", feb26_s, feb26_e), 28)

        feb24_s, feb24_e = period_range("month", date(2024, 2, 10))
        self.assertEqual(period_days("month", feb24_s, feb24_e), 29)

    def test_achievement_and_overall_pct_excludes_archived_goal(self) -> None:
        # 일일 목표 60분 과목에서 주간(7일) 동안 210분(12600초) 학습 -> 210 / 420 = 50%
        self.assertAlmostEqual(achievement_pct(12600, 60, 7), 50.0)

        rows = [
            SubjectTotal(1, "알고리즘", "#4F46E5", 60, False, 1800),     # 활성, 목표 60분, 실제 30분
            SubjectTotal(2, "운영체제", "#10B981", 60, False, 1800),     # 활성, 목표 60분, 실제 30분
            SubjectTotal(3, "보관과목", "#F59E0B", 120, True, 3600),     # 보관됨(분모 제외!), 실제 60분
        ]
        # 일간(days=1): 분모는 활성 과목 목표 합 = 60 + 60 = 120분, 분자는 30 + 30 + 60 = 120분 -> 100.0%
        self.assertAlmostEqual(overall_pct(rows, 1), 100.0)

    def test_merge_live_credit(self) -> None:
        rows = [
            SubjectTotal(1, "알고리즘", "#4F46E5", 60, False, 1000),
            SubjectTotal(2, "운영체제", "#10B981", 60, False, 1500),
        ]
        # 범위 안의 진행 중 세션 (+800초 -> 과목 1이 1800초가 되어 1위로 정렬)
        merged = merge_live(rows, (1, date(2026, 11, 3), 800), date(2026, 11, 3), date(2026, 11, 3))
        self.assertEqual(merged[0].subject_id, 1)
        self.assertEqual(merged[0].total_seconds, 1800)

        # 범위 밖 날짜의 진행 중 세션은 합산되지 않음
        unchanged = merge_live(rows, (1, date(2026, 11, 4), 800), date(2026, 11, 3), date(2026, 11, 3))
        self.assertEqual(unchanged[0].subject_id, 2)
        self.assertEqual(unchanged[1].total_seconds, 1000)


if __name__ == "__main__":
    unittest.main()

