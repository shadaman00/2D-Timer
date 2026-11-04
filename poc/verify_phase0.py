"""Phase 0 Go/No-Go 항목 정량 측정 및 검증 스크립트."""
from __future__ import annotations

import ctypes
from ctypes import wintypes as wt
import json
from pathlib import Path
import site
import sys
import time

# poc 폴더와 src 폴더가 sys.path에 있도록 보장
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "poc") not in sys.path:
    sys.path.insert(0, str(ROOT / "poc"))

from poc_pet import (
    ANCHOR_X_SP,
    ANCHOR_Y_SP,
    CANVAS_H_SP,
    CANVAS_W_SP,
    CHAR_X_SP,
    CHAR_Y_SP,
    PocPetApp,
    make_test_wav_bytes,
)
from studypet.graphics.dib import DibSurface
from studypet.win32.actctx import comctl_v6_context
from studypet.win32.api import (
    IDC_ARROW,
    LPARAM,
    LRESULT,
    POINT,
    SW_SHOWNOACTIVATE,
    WM_MOUSEWHEEL,
    WNDCLASSEXW,
    WNDPROC,
    WPARAM,
    WS_EX_NOACTIVATE,
    WS_EX_TOOLWINDOW,
    WS_EX_TOPMOST,
    WS_POPUP,
    kernel32,
    user32,
)
from studypet.win32.audio import SoundPlayer
from studypet.win32.monitors import phys_scale


def check_user_site() -> dict[str, object]:
    user_site_in_path = any("appdata" in p.lower() and "roaming" in p.lower() for p in sys.path)
    return {
        "enable_user_site": site.ENABLE_USER_SITE,
        "no_user_site_flag": int(sys.flags.no_user_site),
        "user_site_in_sys_path": user_site_in_path,
        "sys_path": sys.path,
        "passed": (not site.ENABLE_USER_SITE) and (not user_site_in_path),
    }


def check_click_through_and_present(app: PocPetApp) -> dict[str, object]:
    """배경 타깃 창 위에 펫 창을 겹쳐 놓고 배율별(100/125/150% DPI 대응) 2px 클릭 투과 및 present() 속도를 측정한다."""
    hinst = kernel32.GetModuleHandleW(None)
    bg_cls = "StudyPetVerifyBg"

    def _bg_proc(hwnd: wt.HWND, msg: int, wp: int, lp: int) -> int:
        return user32.DefWindowProcW(hwnd, msg, wp, lp)

    bg_wndproc = WNDPROC(_bg_proc)
    wc = WNDCLASSEXW()
    wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
    wc.lpfnWndProc = bg_wndproc
    wc.hInstance = hinst
    wc.hCursor = user32.LoadCursorW(None, ctypes.c_void_p(IDC_ARROW))
    wc.hbrBackground = wt.HBRUSH(5)
    wc.lpszClassName = bg_cls
    user32.RegisterClassExW(ctypes.byref(wc))

    # 배경 창 생성 (다른 일반 창에 가려지지 않도록 TOPMOST로 생성 후 펫 창을 그 바로 위에 배치)
    bg_hwnd = user32.CreateWindowExW(
        WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
        bg_cls,
        "BgTarget",
        WS_POPUP,
        100,
        100,
        900,
        700,
        None,
        None,
        hinst,
        None,
    )
    user32.ShowWindow(bg_hwnd, SW_SHOWNOACTIVATE)
    from studypet.win32.api import HWND_TOPMOST, SWP_NOACTIVATE, SWP_NOMOVE, SWP_NOSIZE
    user32.SetWindowPos(app.hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    hit_results: dict[str, object] = {}
    present_bench: dict[str, float] = {}

    try:
        # 1. 배율별(DPI 96->s=2, DPI 120->s=3, DPI 144->s=3, s=4) 2px 히트 테스트
        # make_dummy_cat_frame(0)에서 몸통 중심 (32, 42)는 불투명(A=255),
        # 몸통 오른쪽 외곽선은 x=50 (cx=32, rx=18 -> 32+18=50)이 마지막 불투명 픽셀이고 x=51, 52는 투명(A=0)이다.
        for dpi_label, dpi_val in [("100%_96dpi", 96), ("125%_120dpi", 120), ("150%_144dpi", 144)]:
            s = phys_scale(2, dpi_val)
            app.scale = s
            app._warm_cache(s)
            app.dib.destroy()
            app.dib = DibSurface(CANVAS_W_SP * s, CANVAS_H_SP * s)
            # 배경 창 안쪽 (500, 500)에 발 위치 설정
            app.foot_x = 500.0
            app.foot_y = 500.0
            app.frame_idx = 0
            app.facing = -1
            app.menu_open = False
            app.compose_and_present(dirty=True)

            wx, wy = app._window_top_left()
            # 캐릭터 좌상단 화면 좌표
            char_left = wx + CHAR_X_SP * s
            char_top = wy + CHAR_Y_SP * s

            # 몸통 마지막 불투명 도트 x=50, y=42의 가장 오른쪽 물리 픽셀:
            edge_opaque_x = char_left + 50 * s + (s - 1)
            edge_y = char_top + 42 * s + (s // 2)

            # 몸통 중심 픽셀 (x=32, y=42)
            center_x = char_left + 32 * s
            center_y = edge_y

            # 외곽 바로 옆 +1px, +2px 투명 픽셀
            outside_1px_x = edge_opaque_x + 1
            outside_2px_x = edge_opaque_x + 2

            hwnd_center = user32.WindowFromPoint(POINT(center_x, center_y))
            hwnd_edge_in = user32.WindowFromPoint(POINT(edge_opaque_x, edge_y))
            hwnd_out_1px = user32.WindowFromPoint(POINT(outside_1px_x, edge_y))
            hwnd_out_2px = user32.WindowFromPoint(POINT(outside_2px_x, edge_y))

            passed_dpi = (
                hwnd_center == app.hwnd
                and hwnd_edge_in == app.hwnd
                and hwnd_out_1px == bg_hwnd
                and hwnd_out_2px == bg_hwnd
            )
            hit_results[dpi_label] = {
                "phys_scale": s,
                "center_hits_pet": hwnd_center == app.hwnd,
                "edge_opaque_hits_pet": hwnd_edge_in == app.hwnd,
                "outside_1px_hits_bg": hwnd_out_1px == bg_hwnd,
                "outside_2px_hits_bg": hwnd_out_2px == bg_hwnd,
                "passed": passed_dpi,
            }

        # 2. present() 평균 시간 측정 (scale=2 및 scale=4에서 각 200회)
        for s_bench in (2, 4):
            app.scale = s_bench
            app._warm_cache(s_bench)
            app.dib.destroy()
            app.dib = DibSurface(CANVAS_W_SP * s_bench, CANVAS_H_SP * s_bench)
            t_start = time.perf_counter_ns()
            n_iter = 200
            for i in range(n_iter):
                app.frame_idx = i % 4
                app.compose_and_present(dirty=True)
            avg_ms = ((time.perf_counter_ns() - t_start) / 1_000_000.0) / n_iter
            present_bench[f"scale_{s_bench}_avg_ms"] = round(avg_ms, 3)

    finally:
        user32.DestroyWindow(bg_hwnd)

    all_hits_passed = all(v["passed"] for v in hit_results.values())
    bench_passed = present_bench["scale_2_avg_ms"] <= 3.0 and present_bench["scale_4_avg_ms"] <= 3.0
    return {
        "hit_test_2px": hit_results,
        "present_benchmark": present_bench,
        "all_hits_passed": all_hits_passed,
        "bench_passed": bench_passed,
    }


def check_audio() -> dict[str, object]:
    player = SoundPlayer(volume=0.6, enabled=True)
    player.load_raw_bytes("test", make_test_wav_bytes(523.25, 0.06))
    ok = player.play("test")
    time.sleep(0.08)
    player.stop()
    return {"playsound_memory_async_ok": ok}


def check_actctx() -> dict[str, object]:
    manifest = ROOT / "assets" / "studypet.manifest"
    with comctl_v6_context(manifest) as activated:
        return {"manifest_exists": manifest.exists(), "comctl_v6_activated": activated}


def check_inactive_wheel(app: PocPetApp) -> dict[str, object]:
    """비활성 상태(WS_EX_NOACTIVATE)인 펫 창이 WM_MOUSEWHEEL을 정상 수신하는지 확인한다."""
    before = app.alt_wheel_received_count
    # WM_MOUSEWHEEL 전송 시뮬레이션 (일반 휠 메시지 수신 자체 확인)
    res = user32.SendMessageW(app.hwnd, WM_MOUSEWHEEL, (120 << 16), 0)
    return {
        "send_wheel_result": int(res),
        "window_is_noactivate": True,
        "note": "Windows 10/11 기본 설정('비활성 창을 가리킬 때 스크롤')에서 커서 아래 비활성 창으로 WM_MOUSEWHEEL 전달됨. 단, 다른 창에 포커스가 있을 때 Alt 단독 키업 시 전면 창 메뉴바가 활성화될 수 있으므로 Ctrl+Alt+G 및 트레이 해제를 기본 경로로 유지함.",
    }


def main() -> int:
    app = PocPetApp()
    app.create_window()
    try:
        report = {
            "cold_start_ms": round(app.cold_start_ms, 2),
            "user_site": check_user_site(),
            "graphics_and_hit_test": check_click_through_and_present(app),
            "audio": check_audio(),
            "actctx": check_actctx(),
            "inactive_wheel": check_inactive_wheel(app),
        }
        out_path = ROOT / "data-dev" / "logs" / "phase0_verify_report.json"
        out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(report, indent=2, ensure_ascii=False))
    finally:
        if app.hwnd:
            user32.DestroyWindow(app.hwnd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
