"""애플리케이션 로깅 및 성능 로그 설정 (DEVELOPMENT_PLAN.md 4-17)."""
from __future__ import annotations

from datetime import datetime
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys


LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def setup_logging(logs_dir: Path, console: bool = False) -> logging.Logger:
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "studypet.log"

    root_logger = logging.getLogger("studypet")
    root_logger.setLevel(logging.INFO)
    root_logger.propagate = False

    # 기존 핸들러 정리 (중복 등록 방지)
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)
        try:
            h.close()
        except Exception:
            pass

    formatter = logging.Formatter(LOG_FORMAT)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=1_048_576,  # 1 MB
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    if console and sys.stderr is not None:
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setFormatter(formatter)
        root_logger.addHandler(stream_handler)

    return root_logger


class PerfLogger:
    """data/logs/perf.log 에 성능 측정 지표(cold_start_ms, menu_latency_ms, render_ms)를 기록한다."""

    def __init__(self, logs_dir: Path) -> None:
        logs_dir.mkdir(parents=True, exist_ok=True)
        self.path: Path = logs_dir / "perf.log"

    def log(self, event: str, **metrics: object) -> None:
        try:
            payload = {
                "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
                "event": event,
                **metrics,
            }
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except OSError:
            pass

