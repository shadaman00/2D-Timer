"""SQLite 데이터베이스(스키마 v1, 마이그레이션, Repository 3종) (DEVELOPMENT_PLAN.md 4-5)."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
import logging
from pathlib import Path
import shutil
import sqlite3
from typing import Callable, Iterator


logger = logging.getLogger("studypet.db")


def _iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _date_str(d: str | date) -> str:
    return d.isoformat() if isinstance(d, date) else str(d)


@dataclass(frozen=True)
class SubjectRow:
    id: int
    name: str
    color_code: str
    daily_goal_minutes: int
    is_archived: bool
    sort_order: int
    created_at: str


@dataclass(frozen=True)
class SegmentRow:
    id: int
    subject_id: int
    mode: str
    start_time: str
    end_time: str
    local_date: str
    duration_seconds: int
    memo: str
    is_completed: bool
    chain_id: int
    segment_no: int
    subject_name: str = ""


@dataclass(frozen=True)
class SubjectTotal:
    subject_id: int
    name: str
    color_code: str
    daily_goal_minutes: int
    is_archived: bool
    total_seconds: int


def _migrate_v1(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE subjects (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            name               TEXT    NOT NULL CHECK(length(trim(name)) BETWEEN 1 AND 40),
            color_code         TEXT    NOT NULL DEFAULT '#4F46E5' CHECK(color_code GLOB '#[0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f]'),
            daily_goal_minutes INTEGER NOT NULL DEFAULT 60 CHECK(daily_goal_minutes BETWEEN 1 AND 1440),
            is_archived        INTEGER NOT NULL DEFAULT 0 CHECK(is_archived IN (0,1)),
            sort_order         INTEGER NOT NULL DEFAULT 0,
            created_at         TEXT    NOT NULL
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE study_sessions (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id       INTEGER NOT NULL REFERENCES subjects(id),
            mode             TEXT    NOT NULL CHECK(mode IN ('STOPWATCH','POMODORO')),
            start_time       TEXT    NOT NULL,
            end_time         TEXT    NOT NULL,
            local_date       TEXT    NOT NULL,
            duration_seconds INTEGER NOT NULL DEFAULT 0 CHECK(duration_seconds >= 0),
            memo             TEXT    NOT NULL DEFAULT '',
            is_completed     INTEGER NOT NULL DEFAULT 0 CHECK(is_completed IN (0,1)),
            chain_id         INTEGER NOT NULL DEFAULT 0,
            segment_no       INTEGER NOT NULL DEFAULT 1
        );
        """
    )
    conn.execute("CREATE INDEX idx_sessions_local_date   ON study_sessions(local_date);")
    conn.execute("CREATE INDEX idx_sessions_subject_date ON study_sessions(subject_id, local_date);")
    conn.execute("CREATE INDEX idx_sessions_chain        ON study_sessions(chain_id);")
    conn.execute("CREATE INDEX idx_sessions_open         ON study_sessions(is_completed) WHERE is_completed = 0;")


MIGRATIONS: list[Callable[[sqlite3.Connection], None]] = [
    _migrate_v1,  # index 0 -> target user_version 1
]


class Database:
    """SQLite3 WAL 연결, 트랜잭션 컨텍스트, 마이그레이션 관리."""

    def __init__(self, path: Path | str) -> None:
        self.path_str = str(path)
        self.is_memory = self.path_str == ":memory:"
        if not self.is_memory:
            Path(self.path_str).parent.mkdir(parents=True, exist_ok=True)

        self.conn = sqlite3.connect(
            self.path_str,
            isolation_level=None,  # 수동 BEGIN IMMEDIATE / COMMIT 제어
            check_same_thread=True,
        )
        self.conn.row_factory = sqlite3.Row
        self._configure_pragmas()
        self._run_migrations()

        self.subjects = SubjectRepository(self)
        self.sessions = SessionRepository(self)
        self.stats = StatsRepository(self)

    @classmethod
    def open(cls, path: Path | str) -> "Database":
        return cls(path)

    def _configure_pragmas(self) -> None:
        mode_row = self.conn.execute("PRAGMA journal_mode = WAL;").fetchone()
        mode_val = str(mode_row[0]).lower() if mode_row else ""
        if mode_val != "wal" and not self.is_memory:
            logger.warning("SQLite journal_mode is %r instead of 'wal' (path=%s)", mode_val, self.path_str)
        self.conn.execute("PRAGMA synchronous = NORMAL;")
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self.conn.execute("PRAGMA busy_timeout = 3000;")

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        if self.conn.in_transaction:
            yield self.conn
            return
        self.conn.execute("BEGIN IMMEDIATE;")
        try:
            yield self.conn
        except BaseException:
            if self.conn.in_transaction:
                self.conn.execute("ROLLBACK;")
            raise
        else:
            if self.conn.in_transaction:
                self.conn.execute("COMMIT;")

    def user_version(self) -> int:
        row = self.conn.execute("PRAGMA user_version;").fetchone()
        return int(row[0]) if row else 0

    def _run_migrations(self) -> None:
        current = self.user_version()
        target = len(MIGRATIONS)
        if current >= target:
            return

        # 기존 DB 파일이 있고 업그레이드하는 경우 백업 생성
        if not self.is_memory and current > 0:
            db_file = Path(self.path_str)
            if db_file.exists() and db_file.stat().st_size > 0:
                bak_file = db_file.with_name(f"{db_file.name}.v{current}.bak")
                try:
                    shutil.copyfile(db_file, bak_file)
                except OSError as exc:
                    logger.warning("Failed to backup DB before migration: %s", exc)

        for idx in range(current, target):
            ver = idx + 1
            with self.tx() as conn:
                MIGRATIONS[idx](conn)
                conn.execute(f"PRAGMA user_version = {ver};")

    def close(self) -> None:
        if getattr(self, "conn", None) is not None:
            try:
                if not self.is_memory:
                    self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            except sqlite3.Error as exc:
                logger.warning("wal_checkpoint failed on close: %s", exc)
            finally:
                self.conn.close()
                self.conn = None  # type: ignore[assignment]


class SubjectRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    @staticmethod
    def _to_row(r: sqlite3.Row) -> SubjectRow:
        return SubjectRow(
            id=int(r["id"]),
            name=str(r["name"]),
            color_code=str(r["color_code"]),
            daily_goal_minutes=int(r["daily_goal_minutes"]),
            is_archived=bool(r["is_archived"]),
            sort_order=int(r["sort_order"]),
            created_at=str(r["created_at"]),
        )

    def list(self, include_archived: bool = False) -> list[SubjectRow]:
        if include_archived:
            rows = self._db.conn.execute(
                "SELECT * FROM subjects ORDER BY is_archived ASC, sort_order ASC, id ASC;"
            ).fetchall()
        else:
            rows = self._db.conn.execute(
                "SELECT * FROM subjects WHERE is_archived = 0 ORDER BY sort_order ASC, id ASC;"
            ).fetchall()
        return [self._to_row(r) for r in rows]

    def get(self, subject_id: int) -> SubjectRow | None:
        r = self._db.conn.execute("SELECT * FROM subjects WHERE id = ?;", (int(subject_id),)).fetchone()
        return self._to_row(r) if r else None

    def exists_active(self, subject_id: int) -> bool:
        r = self._db.conn.execute(
            "SELECT 1 FROM subjects WHERE id = ? AND is_archived = 0;",
            (int(subject_id),),
        ).fetchone()
        return r is not None

    def create(
        self,
        name: str,
        color_code: str = "#4F46E5",
        daily_goal_minutes: int = 60,
        created_at: str | None = None,
    ) -> SubjectRow:
        clean_name = name.strip()
        ts = created_at or _iso_now()
        with self._db.tx() as conn:
            cur = conn.execute(
                """
                INSERT INTO subjects (name, color_code, daily_goal_minutes, is_archived, sort_order, created_at)
                VALUES (?, ?, ?, 0, 0, ?);
                """,
                (clean_name, color_code, int(daily_goal_minutes), ts),
            )
            new_id = int(cur.lastrowid)
        row = self.get(new_id)
        assert row is not None
        return row

    def update(self, subject_id: int, name: str, color_code: str, daily_goal_minutes: int) -> SubjectRow:
        clean_name = name.strip()
        with self._db.tx() as conn:
            conn.execute(
                """
                UPDATE subjects
                   SET name = ?, color_code = ?, daily_goal_minutes = ?
                 WHERE id = ?;
                """,
                (clean_name, color_code, int(daily_goal_minutes), int(subject_id)),
            )
        row = self.get(subject_id)
        if row is None:
            raise KeyError(f"Subject not found: {subject_id}")
        return row

    def set_archived(self, subject_id: int, flag: bool) -> None:
        with self._db.tx() as conn:
            conn.execute(
                "UPDATE subjects SET is_archived = ? WHERE id = ?;",
                (1 if flag else 0, int(subject_id)),
            )

    def ensure_default_subject(self, created_at: str | None = None) -> int:
        active = self.list(include_archived=False)
        if active:
            return active[0].id
        all_subs = self.list(include_archived=True)
        if all_subs:
            self.set_archived(all_subs[0].id, False)
            return all_subs[0].id
        created = self.create("자유 학습", "#4F46E5", 60, created_at=created_at)
        return created.id


class SessionRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    @staticmethod
    def _to_row(r: sqlite3.Row) -> SegmentRow:
        keys = r.keys()
        return SegmentRow(
            id=int(r["id"]),
            subject_id=int(r["subject_id"]),
            mode=str(r["mode"]),
            start_time=str(r["start_time"]),
            end_time=str(r["end_time"]),
            local_date=str(r["local_date"]),
            duration_seconds=int(r["duration_seconds"]),
            memo=str(r["memo"]),
            is_completed=bool(r["is_completed"]),
            chain_id=int(r["chain_id"]),
            segment_no=int(r["segment_no"]),
            subject_name=str(r["subject_name"]) if "subject_name" in keys and r["subject_name"] is not None else "",
        )

    def get_segment(self, seg_id: int) -> SegmentRow | None:
        r = self._db.conn.execute(
            """
            SELECT s.*, sub.name AS subject_name
              FROM study_sessions s
              JOIN subjects sub ON sub.id = s.subject_id
             WHERE s.id = ?;
            """,
            (int(seg_id),),
        ).fetchone()
        return self._to_row(r) if r else None

    def create_chain(
        self,
        subject_id: int,
        mode: str,
        start_iso: str,
        local_date: str | date,
    ) -> SegmentRow:
        ld = _date_str(local_date)
        with self._db.tx() as conn:
            cur = conn.execute(
                """
                INSERT INTO study_sessions
                    (subject_id, mode, start_time, end_time, local_date, duration_seconds, memo, is_completed, chain_id, segment_no)
                VALUES (?, ?, ?, ?, ?, 0, '', 0, 0, 1);
                """,
                (int(subject_id), str(mode), start_iso, start_iso, ld),
            )
            seg_id = int(cur.lastrowid)
            conn.execute("UPDATE study_sessions SET chain_id = ? WHERE id = ?;", (seg_id, seg_id))
        row = self.get_segment(seg_id)
        assert row is not None
        return row

    def create_next_segment(
        self,
        prev: SegmentRow,
        start_iso: str,
        local_date: str | date,
    ) -> SegmentRow:
        ld = _date_str(local_date)
        next_no = int(prev.segment_no) + 1
        with self._db.tx() as conn:
            cur = conn.execute(
                """
                INSERT INTO study_sessions
                    (subject_id, mode, start_time, end_time, local_date, duration_seconds, memo, is_completed, chain_id, segment_no)
                VALUES (?, ?, ?, ?, ?, 0, '', 0, ?, ?);
                """,
                (int(prev.subject_id), str(prev.mode), start_iso, start_iso, ld, int(prev.chain_id), next_no),
            )
            seg_id = int(cur.lastrowid)
        row = self.get_segment(seg_id)
        assert row is not None
        return row

    def checkpoint(self, seg_id: int, end_iso: str, duration_s: int) -> None:
        with self._db.tx() as conn:
            conn.execute(
                """
                UPDATE study_sessions
                   SET end_time = ?, duration_seconds = ?
                 WHERE id = ? AND is_completed = 0;
                """,
                (end_iso, max(0, int(duration_s)), int(seg_id)),
            )

    def complete_segment(self, seg_id: int, end_iso: str, duration_s: int) -> None:
        with self._db.tx() as conn:
            conn.execute(
                """
                UPDATE study_sessions
                   SET end_time = ?, duration_seconds = ?, is_completed = 1
                 WHERE id = ?;
                """,
                (end_iso, max(0, int(duration_s)), int(seg_id)),
            )

    def add_duration(self, seg_id: int, delta_s: int) -> None:
        with self._db.tx() as conn:
            conn.execute(
                """
                UPDATE study_sessions
                   SET duration_seconds = MAX(0, duration_seconds + ?)
                 WHERE id = ?;
                """,
                (int(delta_s), int(seg_id)),
            )

    def finalize_chain(
        self,
        chain_id: int,
        seg_id: int,
        end_iso: str,
        duration_s: int,
        memo: str,
    ) -> None:
        clean_memo = memo.strip()[:200]
        with self._db.tx() as conn:
            conn.execute(
                """
                UPDATE study_sessions
                   SET end_time = ?, duration_seconds = ?, is_completed = 1
                 WHERE id = ?;
                """,
                (end_iso, max(0, int(duration_s)), int(seg_id)),
            )
            conn.execute(
                "UPDATE study_sessions SET memo = ? WHERE chain_id = ?;",
                (clean_memo, int(chain_id)),
            )

    def update_chain_memo(self, chain_id: int, memo: str) -> None:
        clean_memo = memo.strip()[:200]
        with self._db.tx() as conn:
            conn.execute(
                "UPDATE study_sessions SET memo = ? WHERE chain_id = ?;",
                (clean_memo, int(chain_id)),
            )

    def delete_segment(self, seg_id: int) -> None:
        with self._db.tx() as conn:
            conn.execute(
                "DELETE FROM study_sessions WHERE id = ? AND is_completed = 0;",
                (int(seg_id),),
            )

    def get_open_segments(self) -> list[SegmentRow]:
        rows = self._db.conn.execute(
            """
            SELECT s.*, sub.name AS subject_name
              FROM study_sessions s
              JOIN subjects sub ON sub.id = s.subject_id
             WHERE s.is_completed = 0
             ORDER BY s.id ASC;
            """
        ).fetchall()
        return [self._to_row(r) for r in rows]

    def chain_completed_seconds(self, chain_id: int) -> int:
        r = self._db.conn.execute(
            """
            SELECT COALESCE(SUM(duration_seconds), 0)
              FROM study_sessions
             WHERE chain_id = ? AND is_completed = 1;
            """,
            (int(chain_id),),
        ).fetchone()
        return int(r[0]) if r else 0

    def list_by_chain(self, chain_id: int) -> list[SegmentRow]:
        rows = self._db.conn.execute(
            """
            SELECT s.*, sub.name AS subject_name
              FROM study_sessions s
              JOIN subjects sub ON sub.id = s.subject_id
             WHERE s.chain_id = ?
             ORDER BY s.segment_no ASC, s.id ASC;
            """,
            (int(chain_id),),
        ).fetchall()
        return [self._to_row(r) for r in rows]


class StatsRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def period_totals(self, from_date: str | date, to_date: str | date) -> list[SubjectTotal]:
        f_str = _date_str(from_date)
        t_str = _date_str(to_date)
        rows = self._db.conn.execute(
            """
            SELECT sub.id AS subject_id,
                   sub.name,
                   sub.color_code,
                   sub.daily_goal_minutes,
                   sub.is_archived,
                   COALESCE(SUM(s.duration_seconds), 0) AS total_seconds
              FROM subjects sub
              LEFT JOIN study_sessions s
                     ON s.subject_id = sub.id
                    AND s.is_completed = 1
                    AND s.local_date BETWEEN :from_date AND :to_date
             GROUP BY sub.id
            HAVING sub.is_archived = 0 OR total_seconds > 0
             ORDER BY total_seconds DESC, sub.sort_order ASC, sub.id ASC;
            """,
            {"from_date": f_str, "to_date": t_str},
        ).fetchall()
        return [
            SubjectTotal(
                subject_id=int(r["subject_id"]),
                name=str(r["name"]),
                color_code=str(r["color_code"]),
                daily_goal_minutes=int(r["daily_goal_minutes"]),
                is_archived=bool(r["is_archived"]),
                total_seconds=int(r["total_seconds"]),
            )
            for r in rows
        ]

