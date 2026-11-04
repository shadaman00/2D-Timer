"""AFK 롤백 및 유휴 의심 구간 역산을 위한 크레딧 타임라인 (DEVELOPMENT_PLAN.md 4-7)."""
from __future__ import annotations

from bisect import bisect_right
from collections import deque
from dataclasses import dataclass

from studypet.domain.clock import NS
from studypet.domain.events import Phase


@dataclass(frozen=True)
class CreditMark:
    mono_ns: int
    cum_credit_ns: int
    phase: Phase
    phase_elapsed_ns: int


class CreditTimeline:
    """틱마다 (mono_ns, cum_credit_ns, phase, phase_elapsed_ns)를 보존하고 bisect로 과거 시점을 조회한다."""

    def __init__(self, retention_seconds: int = 720) -> None:
        self._retention_ns: int = max(60, int(retention_seconds)) * NS
        self._marks: deque[CreditMark] = deque()
        self._monos: list[int] = []

    def set_retention_seconds(self, seconds: int) -> None:
        self._retention_ns = max(60, int(seconds)) * NS

    def clear(self) -> None:
        self._marks.clear()
        self._monos.clear()

    def record(
        self,
        mono_ns: int,
        cum_credit_ns: int,
        phase: Phase,
        phase_elapsed_ns: int,
    ) -> None:
        mark = CreditMark(
            mono_ns=int(mono_ns),
            cum_credit_ns=int(cum_credit_ns),
            phase=phase,
            phase_elapsed_ns=int(phase_elapsed_ns),
        )
        self._marks.append(mark)
        self._monos.append(mark.mono_ns)
        self._prune(mark.mono_ns)

    def _prune(self, current_mono_ns: int) -> None:
        cutoff = current_mono_ns - self._retention_ns
        # 최소 1개(가장 오래된 기준점)는 남겨 둔다
        while len(self._marks) > 2 and self._marks[1].mono_ns < cutoff:
            self._marks.popleft()
            del self._monos[0]

    def at(self, target_mono_ns: int) -> CreditMark:
        """target_mono_ns 시점 이하의 마지막 기록을 반환한다 (이전 기록이 없으면 첫 기록 반환)."""
        if not self._marks:
            return CreditMark(int(target_mono_ns), 0, Phase.FOCUS, 0)
        idx = bisect_right(self._monos, int(target_mono_ns)) - 1
        if idx < 0:
            return self._marks[0]
        return self._marks[idx]

