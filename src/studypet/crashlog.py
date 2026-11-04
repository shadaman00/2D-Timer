"""비정상 예외 발생 시 data/logs/crash.log (또는 실행 파일 폴더)에 트레이스백을 기록한다."""
from __future__ import annotations

import sys
import traceback
from datetime import datetime
from pathlib import Path


_custom_crash_dir: Path | None = None


def set_crash_log_dir(logs_dir: Path) -> None:
    global _custom_crash_dir
    _custom_crash_dir = logs_dir


def _resolve_crash_log_path() -> Path:
    try:
        if _custom_crash_dir is not None:
            _custom_crash_dir.mkdir(parents=True, exist_ok=True)
            return _custom_crash_dir / "crash.log"
        exe_dir = Path(sys.executable).resolve().parent
        marker = exe_dir / "studypet_dev_root.txt"
        if marker.exists():
            root = (exe_dir / marker.read_text("utf-8").strip()).resolve()
            logs_dir = root / "data-dev" / "logs"
        else:
            logs_dir = exe_dir / "data" / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        return logs_dir / "crash.log"
    except BaseException:
        return Path(sys.executable).resolve().parent / "crash.log"


def write_crash_log(extra_msg: str = "") -> Path | None:
    try:
        log_path = _resolve_crash_log_path()
        ts = datetime.now().astimezone().isoformat(timespec="seconds")
        tb = traceback.format_exc()
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"=== CRASH [{ts}] ===\n")
            if extra_msg:
                f.write(f"{extra_msg}\n")
            f.write(tb)
            f.write("\n")
        return log_path
    except BaseException:
        return None

