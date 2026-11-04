"""infra/paths.py 단위 테스트 (DEVELOPMENT_PLAN.md 7-1)."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from studypet.infra.paths import (
    PortablePaths,
    ensure_data_writable,
    grant_data_acl,
)
from studypet.win32.api import IDNO, IDYES


class TestPortablePaths(unittest.TestCase):
    def test_resolve_portable_mode_without_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            exe_dir = Path(tmp) / "StudyPet_Portable"
            exe_dir.mkdir(parents=True)
            fake_exe = exe_dir / "StudyPet.exe"
            fake_exe.write_bytes(b"MZ")

            paths = PortablePaths.resolve(executable=fake_exe)
            self.assertFalse(paths.is_dev)
            self.assertEqual(paths.root_dir, exe_dir.resolve())
            self.assertEqual(paths.data_dir, (exe_dir / "data").resolve())
            self.assertEqual(paths.db_path, (exe_dir / "data" / "study_records.db").resolve())
            self.assertEqual(paths.config_path, (exe_dir / "data" / "config.json").resolve())
            self.assertEqual(paths.exports_dir, (exe_dir / "data" / "exports").resolve())
            self.assertEqual(paths.logs_dir, (exe_dir / "data" / "logs").resolve())

    def test_resolve_dev_mode_with_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proj_root = Path(tmp) / "project"
            dev_dir = proj_root / "runtime" / "dev"
            dev_dir.mkdir(parents=True)
            fake_exe = dev_dir / "StudyPet.exe"
            fake_exe.write_bytes(b"MZ")
            (dev_dir / "studypet_dev_root.txt").write_text("..\\..", encoding="utf-8")

            paths = PortablePaths.resolve(executable=fake_exe)
            self.assertTrue(paths.is_dev)
            self.assertEqual(paths.root_dir, proj_root.resolve())
            self.assertEqual(paths.data_dir, (proj_root / "data-dev").resolve())
            self.assertEqual(paths.db_path, (proj_root / "data-dev" / "study_records.db").resolve())

    def test_grant_data_acl_rejects_unsafe_chars(self) -> None:
        with patch("studypet.infra.paths.shell32.ShellExecuteExW") as mock_exec:
            self.assertFalse(grant_data_acl(Path(r'C:\bad"path\data')))
            self.assertFalse(grant_data_acl(Path(r"C:\bad%path%\data")))
            mock_exec.assert_not_called()

    def test_grant_data_acl_invokes_shellexecute_and_waits(self) -> None:
        with (
            patch("studypet.infra.paths.shell32.ShellExecuteExW") as mock_exec,
            patch("studypet.infra.paths.kernel32.WaitForSingleObject") as mock_wait,
            patch("studypet.infra.paths.kernel32.CloseHandle") as mock_close,
        ):
            def _side_effect(sei_ptr: object) -> int:
                sei = sei_ptr._obj  # type: ignore[attr-defined]
                self.assertEqual(sei.lpVerb, "runas")
                self.assertTrue(sei.lpFile.lower().endswith("cmd.exe"))
                self.assertIn("*S-1-5-32-545:(OI)(CI)M /T /Q", sei.lpParameters)
                self.assertIn(r'C:\Program Files (x86)\StudyPet & Co\data', sei.lpParameters)
                sei.hProcess = 12345
                return 1

            mock_exec.side_effect = _side_effect
            ok = grant_data_acl(Path(r"C:\Program Files (x86)\StudyPet & Co\data\\"))
            self.assertTrue(ok)
            mock_exec.assert_called_once()
            mock_wait.assert_called_once()
            mock_close.assert_called_once_with(12345)

    def test_ensure_data_writable_success_and_uac_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_exe = Path(tmp) / "StudyPet.exe"
            fake_exe.write_bytes(b"MZ")
            paths = PortablePaths.resolve(executable=fake_exe)

            # 1. 정상 쓰기 가능 폴더
            self.assertTrue(ensure_data_writable(paths))
            self.assertTrue(paths.data_dir.is_dir())
            self.assertTrue(paths.exports_dir.is_dir())
            self.assertTrue(paths.logs_dir.is_dir())
            self.assertFalse((paths.data_dir / ".write_test").exists())

            # 2. 쓰기 실패 -> 사용자가 아니요(IDNO) 선택 시 False
            with (
                patch("studypet.infra.paths._probe_writable", return_value=False),
                patch("studypet.infra.paths.user32.MessageBoxW", return_value=IDNO) as mock_mb,
            ):
                self.assertFalse(ensure_data_writable(paths))
                mock_mb.assert_called_once()

            # 3. 쓰기 실패 -> 예(IDYES) -> grant_data_acl 성공 -> 재검사 성공 시 True
            with (
                patch("studypet.infra.paths._probe_writable", side_effect=[False, True]),
                patch("studypet.infra.paths.user32.MessageBoxW", return_value=IDYES),
                patch("studypet.infra.paths.grant_data_acl", return_value=True) as mock_acl,
            ):
                self.assertTrue(ensure_data_writable(paths))
                mock_acl.assert_called_once_with(paths.data_dir)


if __name__ == "__main__":
    unittest.main()

