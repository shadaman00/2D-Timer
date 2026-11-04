"""CSV 내보내기 및 파일 저장 대화상자 연동 (DEVELOPMENT_PLAN.md 4-9)."""
from __future__ import annotations

import csv
import ctypes
from ctypes import wintypes as wt
from datetime import datetime
from pathlib import Path

from studypet.infra.db import Database
from studypet.win32.api import (
    OFN_NOCHANGEDIR,
    OFN_OVERWRITEPROMPT,
    OFN_PATHMUSTEXIST,
    OPENFILENAMEW,
    comdlg32,
)


CSV_HEADERS = [
    "session_id",
    "chain_id",
    "segment_no",
    "subject",
    "mode",
    "local_date",
    "start_time",
    "end_time",
    "duration_seconds",
    "duration_hms",
    "memo",
]


def format_hms(seconds: int) -> str:
    sec = max(0, int(seconds))
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f"{h}:{m:02d}:{s:02d}"


def export_sessions_to_csv(db: Database, file_path: Path) -> int:
    """완료된(is_completed=1) 모든 세션을 start_time 순으로 UTF-8 BOM(utf-8-sig) CSV 파일에 기록하고 행 수를 반환한다."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    rows = db.conn.execute(
        """
        SELECT s.id AS session_id,
               s.chain_id,
               s.segment_no,
               sub.name AS subject,
               s.mode,
               s.local_date,
               s.start_time,
               s.end_time,
               s.duration_seconds,
               s.memo
          FROM study_sessions s
          JOIN subjects sub ON sub.id = s.subject_id
         WHERE s.is_completed = 1
         ORDER BY s.start_time ASC, s.id ASC;
        """
    ).fetchall()

    with file_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADERS)
        for r in rows:
            dur = int(r["duration_seconds"])
            writer.writerow(
                [
                    int(r["session_id"]),
                    int(r["chain_id"]),
                    int(r["segment_no"]),
                    str(r["subject"]),
                    str(r["mode"]),
                    str(r["local_date"]),
                    str(r["start_time"]),
                    str(r["end_time"]),
                    dur,
                    format_hms(dur),
                    str(r["memo"]),
                ]
            )
    return len(rows)


def prompt_save_csv_path(hwnd_owner: wt.HWND | None, exports_dir: Path) -> Path | None:
    """Win32 GetSaveFileNameW 대화상자로 저장할 CSV 경로를 선택받는다."""
    exports_dir.mkdir(parents=True, exist_ok=True)
    today_str = datetime.now().astimezone().strftime("%Y%m%d")
    default_name = f"study_records_{today_str}.csv"

    file_buf = ctypes.create_unicode_buffer(default_name, 1024)
    init_dir = str(exports_dir.resolve())

    ofn = OPENFILENAMEW()
    ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
    ofn.hwndOwner = hwnd_owner
    ofn.lpstrFilter = "CSV 파일 (*.csv)\0*.csv\0\0"
    ofn.nFilterIndex = 1
    ofn.lpstrFile = ctypes.cast(file_buf, wt.LPWSTR)
    ofn.nMaxFile = len(file_buf)
    ofn.lpstrInitialDir = init_dir
    ofn.lpstrTitle = "학습 기록 CSV 내보내기"
    ofn.Flags = OFN_OVERWRITEPROMPT | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR
    ofn.lpstrDefExt = "csv"

    if not comdlg32.GetSaveFileNameW(ctypes.byref(ofn)):
        return None
    chosen = file_buf.value.strip()
    return Path(chosen) if chosen else None


def prompt_and_export_csv(hwnd_owner: wt.HWND | None, db: Database, exports_dir: Path) -> tuple[Path, int] | None:
    target = prompt_save_csv_path(hwnd_owner, exports_dir)
    if target is None:
        return None
    count = export_sessions_to_csv(db, target)
    return (target, count)

