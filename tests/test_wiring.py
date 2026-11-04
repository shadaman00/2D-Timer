"""모듈 간 호출 형식(인자 이름·개수) 정적 검증.

엔진·모달·트레이 등은 각자 단위 테스트가 있지만, app.py 같은 연결부는 Win32 창 없이 실행할 수 없어
호출부와 피호출부의 인자 형식이 어긋나도 테스트가 통과했다(v0.7 검증: 트레이 메뉴·복구 창 TypeError).
이 테스트는 소스를 AST로 읽어 각 호출을 실제 함수 시그니처에 bind()해 본다. 창을 만들거나 앱을 실행하지 않는다.
"""
from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path
import unittest

from studypet.domain.timer_engine import TimerEngine
from studypet.ui.dashboard import DashboardWindow
from studypet.ui.modals import ModalManager
from studypet.ui.pet_window import PetWindow
from studypet.win32.tray import TrayIcon


SRC_ROOT = Path(__file__).resolve().parents[1] / "src" / "studypet"

# app.py 의 self.<속성>.<메서드>(...) 호출에서 <속성> → 클래스
APP_RECEIVERS: dict[str, type] = {
    "tray": TrayIcon,
    "modals": ModalManager,
    "pet": PetWindow,
    "engine": TimerEngine,
    "dashboard": DashboardWindow,
}

# 모듈 전역 이름(함수·클래스) 직접 호출을 검사할 모듈
MODULES = [
    "studypet.app",
    "studypet.ui.pet_window",
    "studypet.ui.modals",
    "studypet.ui.dashboard",
    "studypet.ui.tab_settings",
    "studypet.ui.tab_stats",
    "studypet.ui.tab_subjects",
    "studypet.win32.tray",
]


def _bind(target: object, call: ast.Call, is_method: bool) -> str | None:
    """call 의 인자를 target 시그니처에 bind 한다. 실패하면 오류 문자열, 검사 불가면 None."""
    if any(isinstance(a, ast.Starred) for a in call.args) or any(k.arg is None for k in call.keywords):
        return None
    try:
        sig = inspect.signature(target)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    args: list[object] = [object()] * len(call.args)
    if is_method:
        args = [object(), *args]
    kwargs = {k.arg: object() for k in call.keywords if k.arg is not None}
    try:
        sig.bind(*args, **kwargs)
    except TypeError as exc:
        return str(exc)
    return None


def _module_path(mod_name: str) -> Path:
    rel = mod_name.split(".")[1:]
    return SRC_ROOT.joinpath(*rel).with_suffix(".py")


class TestCrossModuleCallSignatures(unittest.TestCase):
    def test_app_calls_to_components_match_signatures(self) -> None:
        tree = ast.parse(_module_path("studypet.app").read_text(encoding="utf-8"))
        checked = 0
        errors: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            recv = node.func.value
            if not (
                isinstance(recv, ast.Attribute)
                and isinstance(recv.value, ast.Name)
                and recv.value.id == "self"
                and recv.attr in APP_RECEIVERS
            ):
                continue
            cls = APP_RECEIVERS[recv.attr]
            member = inspect.getattr_static(cls, node.func.attr, None)
            if not inspect.isfunction(member):
                continue  # 콜백 속성·인스턴스 속성은 검사 대상 아님
            checked += 1
            err = _bind(member, node, is_method=True)
            if err:
                errors.append(f"app.py:{node.lineno} self.{recv.attr}.{node.func.attr}(): {err}")
        self.assertGreater(checked, 20)
        self.assertEqual(errors, [])

    def test_module_level_function_and_class_calls_match_signatures(self) -> None:
        errors: list[str] = []
        checked = 0
        for mod_name in MODULES:
            mod = importlib.import_module(mod_name)
            path = _module_path(mod_name)
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                    continue
                target = vars(mod).get(node.func.id)
                if target is None:
                    continue  # 내장 함수·지역 이름
                if not (inspect.isfunction(target) or inspect.isclass(target)):
                    continue
                if getattr(target, "__module__", "").split(".")[0] != "studypet":
                    continue  # 표준 라이브러리·ctypes 구조체 등
                checked += 1
                err = _bind(target, node, is_method=False)
                if err:
                    errors.append(f"{path.name}:{node.lineno} {node.func.id}(): {err}")
        self.assertGreater(checked, 20)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
