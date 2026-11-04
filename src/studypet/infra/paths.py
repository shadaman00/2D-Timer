"""포터블 경로 해석, 쓰기 권한 검사 및 UAC 권한 부여 (DEVELOPMENT_PLAN.md 4-1)."""
from __future__ import annotations

import ctypes
from dataclasses import dataclass
import os
from pathlib import Path
import sys

from studypet.win32.api import (
    IDYES,
    INFINITE,
    MB_ICONERROR,
    MB_ICONWARNING,
    MB_OK,
    MB_TOPMOST,
    MB_YESNO,
    SEE_MASK_NO_CONSOLE,
    SEE_MASK_NOCLOSEPROCESS,
    SHELLEXECUTEINFOW,
    SW_HIDE,
    kernel32,
    shell32,
    user32,
)


@dataclass(frozen=True)
class PortablePaths:
    root_dir: Path
    data_dir: Path
    assets_dir: Path
    db_path: Path
    config_path: Path
    exports_dir: Path
    logs_dir: Path
    is_dev: bool

    @staticmethod
    def resolve(executable: Path | None = None) -> "PortablePaths":
        exe_path = Path(executable if executable is not None else sys.executable).resolve()
        exe_dir = exe_path.parent
        marker = exe_dir / "studypet_dev_root.txt"
        if marker.exists():
            rel = marker.read_text(encoding="utf-8").strip()
            root = (exe_dir / rel).resolve()
            data = root / "data-dev"
            dev = True
        else:
            root = exe_dir
            data = root / "data"
            dev = False

        return PortablePaths(
            root_dir=root,
            data_dir=data,
            assets_dir=root / "assets",
            db_path=data / "study_records.db",
            config_path=data / "config.json",
            exports_dir=data / "exports",
            logs_dir=data / "logs",
            is_dev=dev,
        )


def _probe_writable(paths: PortablePaths) -> bool:
    try:
        paths.data_dir.mkdir(parents=True, exist_ok=True)
        test_file = paths.data_dir / ".write_test"
        test_file.write_bytes(b"ok")
        test_file.unlink()
        paths.exports_dir.mkdir(parents=True, exist_ok=True)
        paths.logs_dir.mkdir(parents=True, exist_ok=True)
        return True
    except OSError:
        return False


def grant_data_acl(data_dir: Path) -> bool:
    """ShellExecuteExW(runas)로 cmd.exe /d /c mkdir & icacls를 호출해 Built-in Users 권한을 부여한다."""
    target = str(data_dir).rstrip("\\/")
    if not target or any(c in target for c in '"%'):
        return False

    sysdir = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
    cmd_exe = str(sysdir / "cmd.exe")
    icacls_exe = str(sysdir / "icacls.exe")
    params = (
        f'/d /c mkdir "{target}" 2>nul & '
        f'"{icacls_exe}" "{target}" /grant *S-1-5-32-545:(OI)(CI)M /T /Q'
    )

    sei = SHELLEXECUTEINFOW()
    sei.cbSize = ctypes.sizeof(SHELLEXECUTEINFOW)
    sei.fMask = SEE_MASK_NOCLOSEPROCESS | SEE_MASK_NO_CONSOLE
    sei.hwnd = None
    sei.lpVerb = "runas"
    sei.lpFile = cmd_exe
    sei.lpParameters = params
    sei.lpDirectory = None
    sei.nShow = SW_HIDE

    if not shell32.ShellExecuteExW(ctypes.byref(sei)):
        return False

    if sei.hProcess:
        kernel32.WaitForSingleObject(sei.hProcess, INFINITE)
        kernel32.CloseHandle(sei.hProcess)
    return True


def ensure_data_writable(paths: PortablePaths) -> bool:
    """데이터 폴더 쓰기 권한을 확인하고, 실패 시 UAC 권한 부여 흐름을 수행한다."""
    if _probe_writable(paths):
        return True

    prompt_msg = (
        f"이 폴더에 학습 기록을 저장할 권한이 없습니다.\n{paths.root_dir}\n\n"
        "관리자 승인으로 data 폴더에 쓰기 권한을 부여할까요?\n"
        "(아니요: 종료 — 바탕화면·문서·USB 등으로 폴더를 옮겨 실행하세요)"
    )
    ans = user32.MessageBoxW(
        None,
        prompt_msg,
        "StudyPet",
        MB_YESNO | MB_ICONWARNING | MB_TOPMOST,
    )
    if ans != IDYES:
        return False

    if grant_data_acl(paths.data_dir) and _probe_writable(paths):
        return True

    fail_msg = (
        "쓰기 권한을 부여하지 못했습니다.\n"
        "폴더를 바탕화면, 문서 또는 USB 드라이브 등 쓰기 가능한 위치로 옮긴 뒤 다시 실행해 주세요."
    )
    user32.MessageBoxW(
        None,
        fail_msg,
        "StudyPet",
        MB_OK | MB_ICONERROR | MB_TOPMOST,
    )
    return False

