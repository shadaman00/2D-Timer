"""기간 범위, 목표 달성률 및 실시간 세션 병합 순수 함수 (DEVELOPMENT_PLAN.md 4-8)."""
from __future__ import annotations

import calendar
from dataclasses import replace
from datetime import date, timedelta
from typing import Literal, Protocol, Sequence


PeriodKind = Literal["day", "week", "month"]


class StatRowLike(Protocol):
    @property
    def subject_id(self) -> int: ...
    @property
    def name(self) -> str: ...
    @property
    def color_code(self) -> str: ...
    @property
    def daily_goal_minutes(self) -> int: ...
    @property
    def is_archived(self) -> bool: ...
    @property
    def total_seconds(self) -> int: ...


def period_range(kind: PeriodKind, anchor: date) -> tuple[date, date]:
    """day: (d, d) / week: 월요일~일요일 / month: 1일~말일."""
    if kind == "day":
        return (anchor, anchor)
    if kind == "week":
        monday = anchor - timedelta(days=anchor.weekday())
        sunday = monday + timedelta(days=6)
        return (monday, sunday)
    if kind == "month":
        _, last_day = calendar.monthrange(anchor.year, anchor.month)
        return (date(anchor.year, anchor.month, 1), date(anchor.year, anchor.month, last_day))
    raise ValueError(f"Unknown period kind: {kind!r}")


def period_days(kind: PeriodKind, start: date, end: date) -> int:
    """Q4: 전체 일수 기준 분모 (일=1, 주=7, 월=28~31)."""
    if kind == "day":
        return 1
    if kind == "week":
        return 7
    if kind == "month":
        return (end - start).days + 1
    raise ValueError(f"Unknown period kind: {kind!r}")


def achievement_pct(total_s: int, goal_min: int, days: int) -> float:
    if goal_min <= 0 or days <= 0:
        return 0.0
    return (total_s / 60.0) / (goal_min * days) * 100.0


def overall_pct(rows: Sequence[StatRowLike], days: int) -> float:
    """전체 달성률: 분모는 보관되지 않은(is_archived=False) 과목들의 목표 시간 합 × days."""
    if days <= 0:
        return 0.0
    total_goal_min = sum(r.daily_goal_minutes for r in rows if not r.is_archived and r.daily_goal_minutes > 0)
    if total_goal_min <= 0:
        return 0.0
    total_actual_s = sum(r.total_seconds for r in rows)
    return (total_actual_s / 60.0) / (total_goal_min * days) * 100.0


def merge_live(
    rows: list[T],
    live: tuple[int, date, int] | None,
    start: date,
    end: date,
) -> list[T]:
    """진행 중 세션의 실시간 크레딧(subject_id, local_date, seconds)이 조회 기간 안에 있으면 합산하고 내림차순 정렬한다."""
    if live is None:
        out = list(rows)
        out.sort(key=lambda x: (-x.total_seconds, x.subject_id))
        return out
    live_sub_id, live_date, live_sec = live
    if live_sec <= 0 or not (start <= live_date <= end):
        out = list(rows)
        out.sort(key=lambda x: (-x.total_seconds, x.subject_id))
        return out

    out = []
    for r in rows:
        if r.subject_id == live_sub_id:
            out.append(replace(r, total_seconds=r.total_seconds + live_sec))  # type: ignore[type-var]
        else:
            out.append(r)
    out.sort(key=lambda x: (-x.total_seconds, x.subject_id))
    return out


def format_hms(seconds: int) -> str:
    sec = max(0, int(seconds))
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f"{h}:{m:02d}:{s:02d}"


def format_korean_hm(seconds: int) -> str:
    total_min = max(0, int(seconds)) // 60
    h = total_min // 60
    m = total_min % 60
    if h > 0:
        return f"{h}시간 {m}분"
    return f"{m}분"
