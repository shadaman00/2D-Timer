"""절전 제외 단조 시계 프로토콜 및 테스트용 FakeClock (DEVELOPMENT_PLAN.md 4-4)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Protocol


NS = 1_000_000_000


def iso(dt: datetime) -> str:
    """표준 ISO-8601 초 단위 문자열 생성 (예: 2026-11-03T21:15:00+09:00)."""
    return dt.isoformat(timespec="seconds")


class Clock(Protocol):
    def mono_ns(self) -> int:
        """절전 시간을 포함하지 않는 단조 시계(나노초)."""
        ...

    def now_local(self) -> datetime:
        """타임존 정보가 포함된 로컬 현재 시각."""
        ...


class FakeClock:
    """단위 테스트용 결정론적 시계. 절전 시뮬레이션(advance_sleep)도 지원한다."""

    def __init__(self, initial_local: datetime | None = None, initial_mono_ns: int = 1_000 * NS) -> None:
        if initial_local is None:
            kst = timezone(timedelta(hours=9))
            initial_local = datetime(2026, 11, 3, 9, 0, 0, tzinfo=kst)
        self._now_local: datetime = initial_local
        self._mono_ns: int = int(initial_mono_ns)

    def mono_ns(self) -> int:
        return self._mono_ns

    def now_local(self) -> datetime:
        return self._now_local

    def advance(self, seconds: float) -> None:
        """깨어 있는 상태로 시간을 진행시킨다 (단조 시계와 벽시계 모두 증가)."""
        delta_ns = int(round(seconds * NS))
        self._mono_ns += delta_ns
        self._now_local += timedelta(seconds=seconds)

    def advance_ns(self, delta_ns: int) -> None:
        self._mono_ns += int(delta_ns)
        self._now_local += timedelta(microseconds=delta_ns / 1_000.0)

    def advance_sleep(self, seconds: float) -> None:
        """절전/최대 절전 시뮬레이션: 벽시계만 증가하고 단조 시계(UnbiasedInterruptTime)는 멈춰 있다."""
        self._now_local += timedelta(seconds=seconds)

    def set_wall(self, new_local: datetime) -> None:
        """시스템 시계 수동 변경 시뮬레이션: 단조 시계는 그대로 두고 벽시계만 변경."""
        self._now_local = new_local

