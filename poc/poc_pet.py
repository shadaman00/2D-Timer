"""Phase 0 기술 검증용 PoC 데스크톱 펫 (DEVELOPMENT_PLAN.md 5장 Phase 0-4)."""
from __future__ import annotations

import ctypes
from ctypes import wintypes as wt
import json
import math
import os
from pathlib import Path
import struct
import sys
import time
import wave
import io

from studypet.graphics.dib import DibSurface
from studypet.win32.actctx import comctl_v6_context
from studypet.win32.api import (
    AC_SRC_ALPHA,
    AC_SRC_OVER,
    BLENDFUNCTION,
    GWL_EXSTYLE,
    HWND_TOPMOST,
    IDC_ARROW,
    LPARAM,
    LRESULT,
    MA_NOACTIVATE,
    MSG,
    POINT,
    SIZE,
    SW_SHOWNOACTIVATE,
    SWP_NOACTIVATE,
    SWP_NOMOVE,
    SWP_NOSIZE,
    SWP_NOZORDER,
    ULW_ALPHA,
    VK_LBUTTON,
    VK_MENU,
    WM_CAPTURECHANGED,
    WM_CLOSE,
    WM_DESTROY,
    WM_DPICHANGED,
    WM_LBUTTONDOWN,
    WM_LBUTTONUP,
    WM_MOUSEACTIVATE,
    WM_MOUSEMOVE,
    WM_MOUSEWHEEL,
    WM_RBUTTONUP,
    WM_TIMER,
    WNDCLASSEXW,
    WNDPROC,
    WPARAM,
    WS_EX_LAYERED,
    WS_EX_NOACTIVATE,
    WS_EX_TOOLWINDOW,
    WS_EX_TOPMOST,
    WS_EX_TRANSPARENT,
    WS_POPUP,
    get_cold_start_ms,
    kernel32,
    user32,
)
from studypet.win32.audio import SoundPlayer
from studypet.win32.monitors import enable_per_monitor_dpi, monitor_at, phys_scale, primary


CANVAS_W_SP = 192
CANVAS_H_SP = 144
CHAR_X_SP = 64
CHAR_Y_SP = 80
CHAR_W_SP = 64
CHAR_H_SP = 64
ANCHOR_X_SP = 96
ANCHOR_Y_SP = 144

TID_FRAME = 1
TID_UI = 4
TID_AUTO_EXIT = 99


def scale_frame(src_bgra: bytes, w: int, h: int, s: int, flip: bool) -> bytes:
    """로드 시 1회 실행하는 사전 스케일 함수 (DEVELOPMENT_PLAN.md 4-11)."""
    rows = []
    for y in range(h):
        row = src_bgra[y * w * 4 : (y + 1) * w * 4]
        px = [row[i : i + 4] for i in range(0, w * 4, 4)]
        if flip:
            px.reverse()
        srow = b"".join(p * s for p in px)
        rows.append(srow * s)
    return b"".join(rows)


def make_dummy_cat_frame(frame_idx: int) -> bytes:
    """코드로 그린 64x64 도트 고양이 (원 몸통 + 뾰족 귀 + 눈 + 발). 알파는 정확히 0 또는 255만 사용."""
    buf = bytearray(64 * 64 * 4)
    bob = 1 if (frame_idx % 2 == 1) else 0
    step = (frame_idx % 4) - 1

    # 색상 (Premultiplied BGRA, A=255)
    c_outline = bytes([45, 35, 35, 255])     # 진한 외곽선
    c_body = bytes([235, 195, 165, 255])     # 연회색/크림 파스텔 바디
    c_ear_in = bytes([180, 145, 235, 255])   # 분홍 귀 안쪽
    c_eye = bytes([30, 30, 35, 255])         # 눈
    c_cheek = bytes([160, 140, 245, 255])    # 볼터치

    def put_px(x: int, y: int, bgra: bytes) -> None:
        if 0 <= x < 64 and 0 <= y < 64:
            idx = (y * 64 + x) * 4
            buf[idx : idx + 4] = bgra

    # 1. 양쪽 귀 (삼각형, x: 16..26, 37..47, y: 14+bob..28+bob)
    for y in range(14 + bob, 29 + bob):
        half_w = (y - (14 + bob)) // 2
        # 왼쪽 귀
        lx_center = 21
        for x in range(lx_center - half_w, lx_center + half_w + 1):
            is_edge = (x == lx_center - half_w or x == lx_center + half_w or y == 14 + bob)
            put_px(x, y, c_outline if is_edge else c_ear_in)
        # 오른쪽 귀
        rx_center = 42
        for x in range(rx_center - half_w, rx_center + half_w + 1):
            is_edge = (x == rx_center - half_w or x == rx_center + half_w or y == 14 + bob)
            put_px(x, y, c_outline if is_edge else c_ear_in)

    # 2. 몸통 (타원형, 중심 (32, 42+bob), rx=18, ry=18)
    cx, cy = 32, 42 + bob
    rx, ry = 18, 18
    for y in range(cy - ry, cy + ry + 1):
        for x in range(cx - rx, cx + rx + 1):
            dist_sq = ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2
            if dist_sq <= 1.0:
                inner_sq = ((x - cx) / (rx - 1.5)) ** 2 + ((y - cy) / (ry - 1.5)) ** 2
                put_px(x, y, c_outline if inner_sq > 1.0 else c_body)

    # 3. 발 2개 (바닥 y=58..63)
    foot_l_x = 24 + (1 if step > 0 else 0)
    foot_r_x = 39 - (1 if step > 0 else 0)
    for fx in (foot_l_x, foot_r_x):
        for y in range(58, 64):
            for x in range(fx - 3, fx + 4):
                is_edge = (x in (fx - 3, fx + 3) or y == 63)
                put_px(x, y, c_outline if is_edge else c_body)

    # 4. 눈 & 볼터치 & 입
    for dy in range(3):
        for dx in range(2):
            put_px(25 + dx, 38 + bob + dy, c_eye)
            put_px(37 + dx, 38 + bob + dy, c_eye)
    for dx in range(3):
        put_px(21 + dx, 42 + bob, c_cheek)
        put_px(40 + dx, 42 + bob, c_cheek)
    put_px(31, 43 + bob, c_outline)
    put_px(32, 44 + bob, c_outline)
    put_px(33, 43 + bob, c_outline)

    return bytes(buf)


def make_dummy_menu_icon(color_bgr: tuple[int, int, int]) -> bytes:
    """16x16 원형 도트 아이콘 (알파 0 또는 255)."""
    buf = bytearray(16 * 16 * 4)
    b, g, r = color_bgr
    c_fill = bytes([b, g, r, 255])
    c_border = bytes([30, 30, 30, 255])
    for y in range(16):
        for x in range(16):
            d2 = (x - 7.5) ** 2 + (y - 7.5) ** 2
            if d2 <= 52:
                idx = (y * 16 + x) * 4
                buf[idx : idx + 4] = c_border if d2 >= 36 else c_fill
    return bytes(buf)


def make_test_wav_bytes(freq_hz: float = 660.0, duration_s: float = 0.08, sample_rate: int = 22050) -> bytes:
    """메모리 비동기 재생 검증용 16-bit PCM WAV 바이트 생성."""
    n_samples = int(sample_rate * duration_s)
    bio = io.BytesIO()
    with wave.open(bio, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        frames = bytearray()
        for i in range(n_samples):
            val = 8000 if (int(i * freq_hz * 2 / sample_rate) % 2 == 0) else -8000
            frames.extend(struct.pack("<h", val))
        wf.writeframes(bytes(frames))
    return bio.getvalue()


class PocPetApp:
    """Phase 0 PoC 창 컨트롤러."""

    def __init__(self, auto_exit_ms: int | None = None) -> None:
        enable_per_monitor_dpi()
        self.root_dir = self._resolve_root()
        self.logs_dir = self.root_dir / "data-dev" / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.perf_log_path = self.logs_dir / "perf.log"

        mon = primary()
        self.config_scale = 2
        self.scale = phys_scale(self.config_scale, mon.dpi)
        self.fps = 30
        self.ghost = False
        self.ghost_temp_untransparent = False
        self.menu_open = False

        # 발 기준 좌표 (물리 픽셀)
        self.foot_x = float(mon.work.right - 120 * self.scale)
        self.foot_y = float(mon.work.bottom)
        self.vx = -30.0  # 30 sp/s
        self.facing = -1

        # 드래그 상태
        self.pressing = False
        self.dragging = False
        self.press_cursor = (0, 0)
        self.press_foot = (0.0, 0.0)

        # 애니메이션 프레임 & 사전 스케일 캐시
        self.raw_frames = [make_dummy_cat_frame(i) for i in range(4)]
        self.raw_icons = [
            make_dummy_menu_icon((230, 120, 80)),
            make_dummy_menu_icon((120, 210, 90)),
            make_dummy_menu_icon((90, 180, 240)),
            make_dummy_menu_icon((200, 120, 230)),
        ]
        self.frame_idx = 0
        self.frame_cache: dict[tuple[int, int, bool], bytes] = {}
        self.icon_cache: dict[tuple[int, int], bytes] = {}
        self._warm_cache(self.scale)

        # 사운드 플레이어 (메모리 비동기 재생 검증)
        self.sound = SoundPlayer(volume=0.5, enabled=True)
        self.sound.load_raw_bytes("beep", make_test_wav_bytes())

        # 측정 지표
        self.cold_start_ms: float = -1.0
        self.present_times_ms: list[float] = []
        self.menu_latencies_ms: list[float] = []
        self.alt_wheel_received_count: int = 0
        self.auto_exit_ms = auto_exit_ms

        self.dib = DibSurface(CANVAS_W_SP * self.scale, CANVAS_H_SP * self.scale)
        self.hwnd: wt.HWND | None = None
        self._wndproc_ref = WNDPROC(self._wnd_proc)
        self._last_tick_ns = time.perf_counter_ns()

    @staticmethod
    def _resolve_root() -> Path:
        exe_dir = Path(sys.executable).resolve().parent
        marker = exe_dir / "studypet_dev_root.txt"
        if marker.exists():
            return (exe_dir / marker.read_text("utf-8").strip()).resolve()
        return Path(__file__).resolve().parent.parent

    def _warm_cache(self, s: int) -> None:
        for idx, raw in enumerate(self.raw_frames):
            for flip in (False, True):
                key = (idx, s, flip)
                if key not in self.frame_cache:
                    self.frame_cache[key] = scale_frame(raw, 64, 64, s, flip)
        for idx, iraw in enumerate(self.raw_icons):
            ikey = (idx, s)
            if ikey not in self.icon_cache:
                self.icon_cache[ikey] = scale_frame(iraw, 16, 16, s, False)

    def _window_top_left(self) -> tuple[int, int]:
        return (
            int(round(self.foot_x)) - ANCHOR_X_SP * self.scale,
            int(round(self.foot_y)) - ANCHOR_Y_SP * self.scale,
        )

    def compose_and_present(self, dirty: bool = True, position_only: bool = False) -> float:
        if not self.hwnd:
            return 0.0
        t0 = time.perf_counter_ns()
        wx, wy = self._window_top_left()
        s = self.scale

        if position_only and not dirty:
            user32.SetWindowPos(
                self.hwnd,
                None,
                wx,
                wy,
                0,
                0,
                SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE,
            )
        else:
            self.dib.clear_all()
            frame_bytes = self.frame_cache[(self.frame_idx % 4, s, self.facing > 0)]
            self.dib.blit_rows(frame_bytes, 64 * s, 64 * s, CHAR_X_SP * s, CHAR_Y_SP * s)

            if self.menu_open:
                menu_centers = [(48, 112), (62, 78), (130, 78), (144, 112)]
                for idx, (cx, cy) in enumerate(menu_centers):
                    ibytes = self.icon_cache[(idx, s)]
                    self.dib.blit_rows(ibytes, 16 * s, 16 * s, (cx - 8) * s, (cy - 8) * s)

            pos = POINT(wx, wy)
            size = SIZE(CANVAS_W_SP * s, CANVAS_H_SP * s)
            src_pt = POINT(0, 0)
            alpha_val = int(255 * (0.3 if self.ghost else 1.0))
            blend = BLENDFUNCTION(AC_SRC_OVER, 0, alpha_val, AC_SRC_ALPHA)
            user32.UpdateLayeredWindow(
                self.hwnd,
                None,
                ctypes.byref(pos),
                ctypes.byref(size),
                self.dib.hdc,
                ctypes.byref(src_pt),
                0,
                ctypes.byref(blend),
                ULW_ALPHA,
            )

        elapsed_ms = (time.perf_counter_ns() - t0) / 1_000_000.0
        self.present_times_ms.append(elapsed_ms)
        return elapsed_ms

    def _log_perf(self, event: str, **kwargs: object) -> None:
        record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "event": event, **kwargs}
        with self.perf_log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def create_window(self) -> None:
        hinst = kernel32.GetModuleHandleW(None)
        cls_name = "StudyPetPet"
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.style = 0
        wc.lpfnWndProc = self._wndproc_ref
        wc.hInstance = hinst
        wc.hCursor = user32.LoadCursorW(None, ctypes.c_void_p(IDC_ARROW))
        wc.lpszClassName = cls_name
        user32.RegisterClassExW(ctypes.byref(wc))

        wx, wy = self._window_top_left()
        ex_style = WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        self.hwnd = user32.CreateWindowExW(
            ex_style,
            cls_name,
            "StudyPet PoC",
            WS_POPUP,
            wx,
            wy,
            CANVAS_W_SP * self.scale,
            CANVAS_H_SP * self.scale,
            None,
            None,
            hinst,
            None,
        )
        if not self.hwnd:
            raise RuntimeError("CreateWindowExW failed")

        user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
        self.compose_and_present(dirty=True)
        self.cold_start_ms = get_cold_start_ms()
        self._log_perf("cold_start", cold_start_ms=round(self.cold_start_ms, 2), scale=self.scale)

        user32.SetTimer(self.hwnd, TID_FRAME, 1000 // self.fps, None)
        user32.SetTimer(self.hwnd, TID_UI, 100, None)
        if self.auto_exit_ms is not None:
            user32.SetTimer(self.hwnd, TID_AUTO_EXIT, self.auto_exit_ms, None)

    def _toggle_ghost(self) -> None:
        if not self.hwnd:
            return
        self.ghost = not self.ghost
        ex = user32.GetWindowLongPtrW(self.hwnd, GWL_EXSTYLE)
        if self.ghost:
            user32.SetWindowLongPtrW(self.hwnd, GWL_EXSTYLE, ex | WS_EX_TRANSPARENT)
        else:
            user32.SetWindowLongPtrW(self.hwnd, GWL_EXSTYLE, ex & ~WS_EX_TRANSPARENT)
        self.ghost_temp_untransparent = False
        self.compose_and_present(dirty=True)

    def _on_frame_timer(self) -> None:
        now_ns = time.perf_counter_ns()
        dt = min(0.1, max(0.0, (now_ns - self._last_tick_ns) / 1_000_000_000.0))
        self._last_tick_ns = now_ns

        if not self.dragging:
            mon = monitor_at(int(self.foot_x), int(self.foot_y))
            old_x = int(round(self.foot_x))
            self.foot_x += self.vx * self.scale * dt
            left_bound = mon.work.left + 32 * self.scale
            right_bound = mon.work.right - 32 * self.scale
            if self.foot_x <= left_bound:
                self.foot_x = float(left_bound)
                self.vx = abs(self.vx)
                self.facing = 1
            elif self.foot_x >= right_bound:
                self.foot_x = float(right_bound)
                self.vx = -abs(self.vx)
                self.facing = -1

            # 8 FPS 캐릭터 애니메이션 프레임 전환
            new_frame = int(now_ns // 125_000_000) % 4
            frame_changed = new_frame != self.frame_idx
            self.frame_idx = new_frame
            pos_changed = int(round(self.foot_x)) != old_x
            if frame_changed or pos_changed:
                self.compose_and_present(dirty=frame_changed, position_only=not frame_changed)

    def _on_ui_timer(self) -> None:
        if not self.hwnd:
            return
        # 유령 모드 중 Alt+호버 보조 해제 감시 (DEVELOPMENT_PLAN.md 4-12)
        if self.ghost:
            alt_down = bool(user32.GetAsyncKeyState(VK_MENU) & 0x8000)
            pt = POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            wx, wy = self._window_top_left()
            s = self.scale
            in_char = (
                wx + CHAR_X_SP * s <= pt.x < wx + (CHAR_X_SP + CHAR_W_SP) * s
                and wy + CHAR_Y_SP * s <= pt.y < wy + (CHAR_Y_SP + CHAR_H_SP) * s
            )
            should_untransparent = alt_down and in_char
            if should_untransparent != self.ghost_temp_untransparent:
                ex = user32.GetWindowLongPtrW(self.hwnd, GWL_EXSTYLE)
                if should_untransparent:
                    user32.SetWindowLongPtrW(self.hwnd, GWL_EXSTYLE, ex & ~WS_EX_TRANSPARENT)
                else:
                    user32.SetWindowLongPtrW(self.hwnd, GWL_EXSTYLE, ex | WS_EX_TRANSPARENT)
                self.ghost_temp_untransparent = should_untransparent

    def _wnd_proc(self, hwnd: wt.HWND, msg: int, wparam: int, lparam: int) -> int:
        try:
            if msg == WM_MOUSEACTIVATE:
                return MA_NOACTIVATE
            if msg == WM_DPICHANGED:
                return 0
            if msg == WM_TIMER:
                if wparam == TID_FRAME:
                    self._on_frame_timer()
                elif wparam == TID_UI:
                    self._on_ui_timer()
                elif wparam == TID_AUTO_EXIT:
                    user32.DestroyWindow(hwnd)
                return 0
            if msg == WM_LBUTTONDOWN:
                user32.SetCapture(hwnd)
                pt = POINT()
                user32.GetCursorPos(ctypes.byref(pt))
                self.pressing = True
                self.dragging = False
                self.press_cursor = (pt.x, pt.y)
                self.press_foot = (self.foot_x, self.foot_y)
                return 0
            if msg == WM_MOUSEMOVE:
                if self.pressing:
                    pt = POINT()
                    user32.GetCursorPos(ctypes.byref(pt))
                    dx = pt.x - self.press_cursor[0]
                    dy = pt.y - self.press_cursor[1]
                    if not self.dragging and (abs(dx) >= 4 * self.scale or abs(dy) >= 4 * self.scale):
                        self.dragging = True
                        self.menu_open = False
                    if self.dragging:
                        self.foot_x = self.press_foot[0] + dx
                        self.foot_y = self.press_foot[1] + dy
                        mon = monitor_at(int(self.foot_x), int(self.foot_y))
                        new_s = phys_scale(self.config_scale, mon.dpi)
                        if new_s != self.scale:
                            self.scale = new_s
                            self._warm_cache(new_s)
                            self.dib.destroy()
                            self.dib = DibSurface(CANVAS_W_SP * new_s, CANVAS_H_SP * new_s)
                            self.compose_and_present(dirty=True)
                        else:
                            self.compose_and_present(dirty=False, position_only=True)
                return 0
            if msg == WM_LBUTTONUP:
                if self.pressing:
                    user32.ReleaseCapture()
                    self.pressing = False
                    if self.dragging:
                        self.dragging = False
                        mon = monitor_at(int(self.foot_x), int(self.foot_y))
                        self.foot_y = float(mon.work.bottom)
                        self.compose_and_present(dirty=False, position_only=True)
                    else:
                        t_click = time.perf_counter_ns()
                        self.menu_open = not self.menu_open
                        self.compose_and_present(dirty=True)
                        lat_ms = (time.perf_counter_ns() - t_click) / 1_000_000.0
                        self.menu_latencies_ms.append(lat_ms)
                        self.sound.play("beep")
                        self._log_perf("menu_click", menu_latency_ms=round(lat_ms, 3))
                return 0
            if msg == WM_CAPTURECHANGED:
                self.pressing = False
                self.dragging = False
                return 0
            if msg == WM_RBUTTONUP:
                self.fps = 60 if self.fps == 30 else 30
                user32.SetTimer(hwnd, TID_FRAME, 1000 // self.fps, None)
                self._log_perf("fps_toggle", fps=self.fps)
                return 0
            if msg == WM_MOUSEWHEEL:
                if user32.GetKeyState(VK_MENU) < 0:
                    self.alt_wheel_received_count += 1
                    self._toggle_ghost()
                return 0
            if msg == WM_CLOSE:
                user32.DestroyWindow(hwnd)
                return 0
            if msg == WM_DESTROY:
                avg_render = (
                    sum(self.present_times_ms) / len(self.present_times_ms)
                    if self.present_times_ms
                    else 0.0
                )
                self._log_perf(
                    "shutdown_summary",
                    render_ms_avg=round(avg_render, 3),
                    frames_rendered=len(self.present_times_ms),
                )
                user32.KillTimer(hwnd, TID_FRAME)
                user32.KillTimer(hwnd, TID_UI)
                self.sound.stop()
                self.dib.destroy()
                user32.PostQuitMessage(0)
                return 0
        except Exception:
            from studypet.crashlog import write_crash_log
            write_crash_log("WndProc exception in PocPetApp")
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def run(self) -> int:
        self.create_window()
        msg = MSG()
        while True:
            r = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if r == 0 or r == -1:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        return 0

