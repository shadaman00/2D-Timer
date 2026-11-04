"""infra/csv_export.py 단위 테스트 (DEVELOPMENT_PLAN.md 7-1)."""
from __future__ import annotations

import csv
from pathlib import Path
import tempfile
import unittest

from studypet.infra.csv_export import CSV_HEADERS, export_sessions_to_csv
from studypet.infra.db import Database


class TestCsvExport(unittest.TestCase):
    def test_csv_bom_headers_korean_and_special_chars(self) -> None:
        db = Database.open(":memory:")
        try:
            sub = db.subjects.create("알고리즘 & 자료구조", "#4F46E5", 90)
            # 완료 세션 (쉼표, 큰따옴표, 줄바꿈이 포함된 메모)
            s1 = db.sessions.create_chain(sub.id, "POMODORO", "2026-11-03T09:00:00+09:00", "2026-11-03")
            complex_memo = '백준 12865 "평범한 배낭", DP 점화식\n2회차 복습 필요'
            db.sessions.finalize_chain(
                s1.chain_id,
                s1.id,
                "2026-11-03T10:05:05+09:00",
                3665,
                complex_memo,
            )
            # 미완료 세션 (내보내기에서 제외되어야 함)
            db.sessions.create_chain(sub.id, "STOPWATCH", "2026-11-03T11:00:00+09:00", "2026-11-03")

            with tempfile.TemporaryDirectory() as tmp:
                csv_path = Path(tmp) / "exports" / "test_export.csv"
                count = export_sessions_to_csv(db, csv_path)
                self.assertEqual(count, 1)

                raw_bytes = csv_path.read_bytes()
                # UTF-8 BOM (EF BB BF) 확인
                self.assertTrue(raw_bytes.startswith(b"\xef\xbb\xbf"))

                with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
                    rows = list(csv.reader(f))

                self.assertEqual(len(rows), 2)
                self.assertEqual(rows[0], CSV_HEADERS)
                data_row = rows[1]
                self.assertEqual(data_row[3], "알고리즘 & 자료구조")
                self.assertEqual(data_row[4], "POMODORO")
                self.assertEqual(data_row[5], "2026-11-03")
                self.assertEqual(data_row[8], "3665")
                self.assertEqual(data_row[9], "1:01:05")
                self.assertEqual(data_row[10], complex_memo)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()

