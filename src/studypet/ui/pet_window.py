"""데스크톱 펫 레이어드 창(StudyPetPet), 입력·드래그·액션 카드·말풍선·유령 모드 제어 (DEVELOPMENT_PLAN.md 4-12, REVISION_PLAN_v0.7)."""
from __future__ import annotations

from collections.abc import Callable
import ctypes
from ctypes import wintypes as wt
import logging
import os
from pathlib import Path
import time

from studypet import strings
from studypet.crashlog import write_crash_log
from studypet.domain.events import Mode as TimerMode, Phase, TimerState
from studypet.domain.pet_fsm import FsmContext, PetFSM, PetState
from studypet.domain.physics import PetPhysics, WorkBounds
from studypet.domain.stats import format_hms
from studypet.graphics.compositor import Compositor
from studypet.graphics.panel import NineSlicePanel, fill_rect
from studypet.graphics.png_codec import decode_png_rgba, rgba_to_premultiplied_bgra
from studypet.graphics.sprites import SpriteSheet, scale_frame
from studypet.graphics.text import PixelFontRenderer
from studypet.ui.layout import (
    ANCHOR_X_SP,
    ANCHOR_Y_SP,
    CANVAS_H_SP,
    CANVAS_W_SP,
    CARD_BOX_SP,
    CARD_HEADER_LEFT_SP,
    CARD_HEADER_RIGHT_X_SP,
    CARD_HEADER_Y_SP,
    CARD_PRIMARY_ICON_SP,
    CARD_PRIMARY_LABEL_SP,
    CHARACTER_BOX_SP,
    CardButton,
    card_buttons,
    card_header,
    compute_bubble_box_sp,
    hit_test_card,
    px_to_sp,
    window_top_left_from_foot,
)
from studypet.ui.popup import (
    CMD_MANAGE_SUBJECTS,
    CMD_MODE_POMODORO,
    CMD_MODE_STOPWATCH,
    CMD_MORE_BUBBLE_TOGGLE,
    CMD_MORE_GHOST_MODE,
    CMD_MORE_QUIT,
    CMD_MORE_SUBJECTS,
    CMD_MORE_SUMMON_CENTER,
    CMD_SUBJECT_BASE,
    show_popup,
)
from studypet.win32.api import (
    GWL_EXSTYLE,
    HWND_TOPMOST,
    IDC_ARROW,
    LONG_PTR,
    LPARAM,
    MA_NOACTIVATE,
    MF_CHECKED,
    MF_SEPARATOR,
    MF_STRING,
    NOTIFY_FOR_THIS_SESSION,
    PBT_APMRESUMEAUTOMATIC,
    PBT_APMRESUMESUSPEND,
    PBT_APMSUSPEND,
    POINT,
    SW_SHOWNOACTIVATE,
    SWP_NOACTIVATE,
    SWP_NOMOVE,
    SWP_NOSIZE,
    TME_LEAVE,
    TRACKMOUSEEVENT,
    VK_LBUTTON,
    VK_MENU,
    VK_RBUTTON,
    WM_APP_POST_START,
    WM_APP_SUMMON,
    WM_APP_TRAY,
    WM_CAPTURECHANGED,
    WM_DESTROY,
    WM_DISPLAYCHANGE,
    WM_DPICHANGED,
    WM_ENDSESSION,
    WM_HOTKEY,
    WM_LBUTTONDBLCLK,
    WM_LBUTTONDOWN,
    WM_LBUTTONUP,
    WM_MOUSEACTIVATE,
    WM_MOUSELEAVE,
    WM_MOUSEMOVE,
    WM_MOUSEWHEEL,
    WM_POWERBROADCAST,
    WM_QUERYENDSESSION,
    WM_RBUTTONUP,
    WM_SETTINGCHANGE,
    WM_TIMER,
    WM_WTSSESSION_CHANGE,
    WNDCLASSEXW,
    WNDPROC,
    WPARAM,
    WS_EX_LAYERED,
    WS_EX_NOACTIVATE,
    WS_EX_TOOLWINDOW,
    WS_EX_TOPMOST,
    WS_EX_TRANSPARENT,
    WS_POPUP,
    WTS_SESSION_LOCK,
    WTS_SESSION_UNLOCK,
    kernel32,
    user32,
    wtsapi32,
)
from studypet.win32.monitors import (
    MonitorInfo,
    invalidate_monitor_cache,
    list_monitors,
    monitor_at,
    phys_scale,
    primary,
)


logger = logging.getLogger(__name__)

# 타이머 ID (DEVELOPMENT_PLAN.md 3-2, REVISION_PLAN_v0.7 M2·M7)
TID_FRAME = 1
TID_ENGINE = 2
TID_IDLE = 3
TID_UI = 4
TID_TOPMOST = 5
TID_SAVE_CFG = 6

ICON_SIZE_SP = 16

# 액션 카드 버튼 색상 (Premultiplied BGRA, α=255) (v0.7 3-7)
BGRA_BTN_NORMAL = b"\x4a\x2f\x2b\xff"        # #2B2F4A
BGRA_BTN_HOVER = b"\x63\x3f\x3a\xff"         # #3A3F63
BGRA_BTN_PRIMARY = b"\xe5\x46\x4f\xff"       # #4F46E5
BGRA_BTN_PRIMARY_HOVER = b"\xf1\x66\x63\xff" # #6366F1
BGRA_BTN_PRESSED = b"\x36\x21\x1e\xff"       # #1E2136

RGB_TEXT_NORMAL = (255, 248, 230)            # #FFF8E6
RGB_TEXT_DISABLED = (122, 127, 153)          # #7A7F99
RGB_TEXT_SUB = (165, 210, 255)

PET_CLASS_NAME = "StudyPetPet"
_class_registered = False


def _signed_loword(val: int) -> int:
    v = val & 0xFFFF
    return v - 0x10000 if v >= 0x8000 else v


def _signed_hiword(val: int) -> int:
    v = (val >> 16) & 0xFFFF
    return v - 0x10000 if v >= 0x8000 else v


class MenuIconCache:
    """주 버튼용 16x16 아이콘(start/pause)을 로드하고 버튼 배경색과 합성해 배율별로 캐시한다."""

    def __init__(self, ui_dir: Path) -> None:
        self._raw: dict[str, bytes] = {}
        self._cache: dict[tuple[str, bytes, int], bytes] = {}
        for kind in ("start", "pause"):
            p = ui_dir / f"menu_{kind}.png"
            if p.exists():
                _, _, rgba = decode_png_rgba(p.read_bytes())
                self._raw[kind] = rgba_to_premultiplied_bgra(rgba)

    def get_icon_on_bg(self, kind: str, bg_bgra: bytes, scale: int) -> bytes:
        s = max(1, int(scale))
        key = (kind, bg_bgra, s)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        raw = self._raw.get(kind) or self._raw.get("start") or (bg_bgra * (ICON_SIZE_SP * ICON_SIZE_SP))
        # 16x16 원본의 투명 모서리(α=0)를 버튼 배경색으로 치환한 뒤 정수 스케일링
        baked = bytearray(raw)
        for off in range(0, len(baked), 4):
            if baked[off + 3] == 0:
                baked[off : off + 4] = bg_bgra
        scaled = scale_frame(bytes(baked), ICON_SIZE_SP, ICON_SIZE_SP, s, flip=False)
        self._cache[key] = scaled
        return scaled

    def clear_cache(self) -> None:
        self._cache.clear()


class PetWindow:
    """StudyPet 캐릭터 및 인플레이스 오버레이(말풍선, 액션 카드)를 담당하는 레이어드 창."""

    def __init__(
        self,
        assets_dir: Path,
        fsm: PetFSM,
        config_scale: int = 2,
        fps_limit: int = 30,
        walk_enabled: bool = True,
        initial_foot_pos: tuple[int, int] | None = None,
        perf_log_path: Path | None = None,
        hint_shown: bool = False,
    ) -> None:
        self.assets_dir = assets_dir
        self.fsm = fsm
        self.config_scale: int = max(1, min(4, int(config_scale)))
        self.fps_limit: int = 60 if int(fps_limit) == 60 else 30
        self.walk_enabled: bool = bool(walk_enabled)
        self.perf_log_path = perf_log_path
        self.hint_shown: bool = bool(hint_shown)

        # 모니터 및 초기 발 위치 결정 (4-12 위치 복원)
        foot_x, foot_y, mon = self._resolve_initial_foot(initial_foot_pos)
        self._current_dpi: int = mon.dpi
        self.scale: int = phys_scale(self.config_scale, self._current_dpi)
        self.physics = PetPhysics(float(foot_x), float(foot_y))
        self.physics.clamp_to_work(self._to_work_bounds(mon), self.scale)

        # 그래픽 리소스 초기화
        skin_dir = assets_dir / "skins" / "default_pixel_cat"
        self.sprites = SpriteSheet(skin_dir / "sheet.png", skin_dir / "meta.json", initial_scale=self.scale)
        self.panel_renderer = NineSlicePanel(assets_dir / "ui" / "panel.png")
        self.menu_icons = MenuIconCache(assets_dir / "ui")
        font_path = assets_dir / "fonts" / "Galmuri11.ttf"
        self.font_renderer = PixelFontRenderer(font_path if font_path.exists() else None)
        self.compositor = Compositor(self.scale)

        # 상태 변수
        self.hwnd: wt.HWND = wt.HWND(0)
        self.modal_locked: bool = False
        self.ghost_mode: bool = False
        self._ghost_temp_interactive: bool = False

        # 액션 카드·말풍선·힌트·토스트 상태 (v0.7 4-4)
        self.card_open: bool = False
        self.card_hover: str | None = None
        self.card_pressed: str | None = None
        self.bubble_collapsed: bool = False
        self._toast: tuple[str, float] | None = None
        self._first_run_hint_due: float | None = (time.perf_counter() + 2.0) if not self.hint_shown else None
        self._hint_until: float = 0.0
        self._hover_since: float | None = None
        self._tracking_leave: bool = False
        self._last_card_activity_mono: float = time.perf_counter()

        # 타이머 HUD 표시 데이터
        self._engine_state: TimerState = TimerState.STOPPED
        self._engine_phase: Phase = Phase.FOCUS
        self._engine_mode: TimerMode = TimerMode.POMODORO
        self._default_mode: TimerMode = TimerMode.POMODORO
        self._subject_name: str = "기본 학습"
        self._display_seconds: int = 0
        self._remain_seconds: int | None = None
        self._subjects_list: list[tuple[int, str]] = []
        self._active_subject_id: int = 1
        self._ghost_shortcut: str = "Ctrl+Alt+G"

        self._last_bubble_key: tuple[object, ...] | None = None
        self._cached_bubble_layer: tuple[bytes, int, int, int, int] | None = None
        self._last_card_key: tuple[object, ...] | None = None
        self._cached_card_layer: tuple[bytes, int, int, int, int] | None = None

        # 마우스 드래그/클릭 상태
        self._pressing: bool = False
        self._pressing_bubble: bool = False
        self._dragging: bool = False
        self._drag_start_cursor: tuple[int, int] = (0, 0)
        self._drag_start_foot: tuple[float, float] = (0.0, 0.0)

        # 애니메이션 타이머 상태
        self._anim_step: int = 0
        self._anim_accum: float = 0.0
        self._last_frame_mono: float = time.perf_counter()
        self._current_frame_interval_ms: int = 0
        self._user_idle_ms: int = 0

        # 성능 계측 (60초 집계 및 1MB 회전, v0.7 L4)
        self._render_sum_ms: float = 0.0
        self._render_count: int = 0
        self._menu_lat_sum_ms: float = 0.0
        self._menu_lat_max_ms: float = 0.0
        self._menu_lat_count: int = 0
        self._last_perf_flush: float = time.perf_counter()

        # 콜백 훅 (AppController에서 연결)
        self.on_primary: Callable[[], None] | None = None
        self.on_quick_start_or_toggle: Callable[[], None] | None = None
        self.on_stop_requested: Callable[[], None] | None = None
        self.on_select_subject: Callable[[int], None] | None = None
        self.on_select_mode: Callable[[str], None] | None = None
        self.on_more_command: Callable[[int], None] | None = None
        self.on_card_opened: Callable[[], None] | None = None
        self.on_locked_click: Callable[[], None] | None = None
        self.on_open_dashboard: Callable[[int], None] | None = None
        self.on_position_changed: Callable[[tuple[int, int]], None] | None = None
        self.on_ghost_toggled: Callable[[bool], None] | None = None
        self.on_engine_tick: Callable[[], None] | None = None
        self.on_idle_tick: Callable[[], int] | None = None
        self.on_tray_menu: Callable[[], None] | None = None
        self.on_taskbar_created: Callable[[], None] | None = None
        self.on_suspend: Callable[[], None] | None = None
        self.on_resume_power: Callable[[], None] | None = None
        self.on_session_lock: Callable[[], None] | None = None
        self.on_session_unlock: Callable[[], None] | None = None
        self.on_post_start: Callable[[], None] | None = None
        self.on_end_session: Callable[[], None] | None = None
        self.on_save_config_timer: Callable[[], None] | None = None

        # GC 방지용 WndProc 참조
        self._wndproc_ref = WNDPROC(self._wnd_proc)
        self._msg_taskbar_created: int = 0

    @staticmethod
    def _to_work_bounds(mon: MonitorInfo) -> WorkBounds:
        return WorkBounds(mon.work.left, mon.work.top, mon.work.right, mon.work.bottom)

    def _resolve_initial_foot(self, pos: tuple[int, int] | None) -> tuple[int, int, MonitorInfo]:
        if pos is not None:
            px, py = int(pos[0]), int(pos[1])
            for m in list_monitors():
                if m.work.left <= px <= m.work.right and m.work.top <= py <= m.work.bottom:
                    return (px, py, m)
        m = primary()
        s = phys_scale(self.config_scale, m.dpi)
        return (m.work.right - ANCHOR_X_SP * s, m.work.bottom, m)

    def create_and_show(self) -> wt.HWND:
        global _class_registered
        hinst = kernel32.GetModuleHandleW(None)
        if not _class_registered:
            wc = WNDCLASSEXW()
            wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
            wc.style = 0
            wc.lpfnWndProc = self._wndproc_ref
            wc.cbClsExtra = 0
            wc.cbWndExtra = 0
            wc.hInstance = hinst
            wc.hIcon = None
            wc.hCursor = user32.LoadCursorW(None, ctypes.c_void_p(IDC_ARROW))
            wc.hbrBackground = None
            wc.lpszMenuName = None
            wc.lpszClassName = PET_CLASS_NAME
            wc.hIconSm = None
            user32.RegisterClassExW(ctypes.byref(wc))
            _class_registered = True

        self._msg_taskbar_created = int(user32.RegisterWindowMessageW("TaskbarCreated") or 0)

        fx, fy = self.physics.screen_foot
        win_x, win_y = window_top_left_from_foot(fx, fy, self.scale)
        win_w = CANVAS_W_SP * self.scale
        win_h = CANVAS_H_SP * self.scale

        ex_style = WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        self.hwnd = user32.CreateWindowExW(
            ex_style,
            PET_CLASS_NAME,
            "StudyPet",
            WS_POPUP,
            win_x,
            win_y,
            win_w,
            win_h,
            None,
            None,
            hinst,
            None,
        )
        if not self.hwnd:
            raise OSError("Failed to create StudyPetPet window")

        try:
            wtsapi32.WTSRegisterSessionNotification(self.hwnd, NOTIFY_FOR_THIS_SESSION)
        except OSError:
            pass

        # 첫 프레임 즉시 출력 (Cold Start 단축)
        self.render_and_present(force=True)
        user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)

        # 타이머 등록 (3-2)
        self._update_frame_timer_interval()
        user32.SetTimer(self.hwnd, TID_ENGINE, 250, None)
        user32.SetTimer(self.hwnd, TID_IDLE, 1000, None)
        user32.SetTimer(self.hwnd, TID_UI, 100, None)
        user32.SetTimer(self.hwnd, TID_TOPMOST, 5000, None)

        user32.PostMessageW(self.hwnd, WM_APP_POST_START, 0, 0)
        return self.hwnd

    def schedule_save_config(self, delay_ms: int = 1000) -> None:
        """위치·과목 변경 시 설정 저장을 1초 디바운스한다 (v0.7 M2)."""
        if self.hwnd:
            user32.SetTimer(self.hwnd, TID_SAVE_CFG, max(100, int(delay_ms)), None)

    def log_perf_line(self, line: str) -> None:
        """성능 로그를 기록하고 1MB 초과 시 .1 파일로 회전한다 (v0.7 L4)."""
        if self.perf_log_path is None:
            return
        try:
            self.perf_log_path.parent.mkdir(parents=True, exist_ok=True)
            if self.perf_log_path.exists() and self.perf_log_path.stat().st_size >= 1_048_576:
                rot_path = self.perf_log_path.with_name(self.perf_log_path.name + ".1")
                os.replace(self.perf_log_path, rot_path)
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            with self.perf_log_path.open("a", encoding="utf-8") as f:
                f.write(f"{ts} {line}\n")
        except OSError:
            pass

    def _record_menu_latency(self, latency_ms: float) -> None:
        self._menu_lat_sum_ms += latency_ms
        if latency_ms > self._menu_lat_max_ms:
            self._menu_lat_max_ms = latency_ms
        self._menu_lat_count += 1

    def show_toast(self, text: str, duration_s: float = 2.0) -> None:
        """말풍선 위치에 지정 시간 동안 우선 표시되는 토스트를 띄운다 (v0.7 8장 D2)."""
        self._toast = (text, time.perf_counter() + max(0.5, float(duration_s)))
        self._last_bubble_key = None
        self.render_and_present(force=True)

    def apply_settings(self, config_scale: int, walk_enabled: bool, fps_limit: int) -> None:
        self.walk_enabled = bool(walk_enabled)
        self.fps_limit = 60 if int(fps_limit) == 60 else 30
        new_cfg_scale = max(1, min(4, int(config_scale)))
        if new_cfg_scale != self.config_scale:
            self.config_scale = new_cfg_scale
            self._recalc_scale_for_foot()
        self._update_frame_timer_interval()
        self.render_and_present(force=True)

    def update_hud_state(
        self,
        engine_state: TimerState,
        phase: Phase,
        subject_id: int,
        subject_name: str,
        display_seconds: int,
        subjects_list: list[tuple[int, str]] | None = None,
        mode: TimerMode | None = None,
        remain_seconds: int | None = None,
        default_mode: TimerMode | None = None,
        ghost_shortcut: str | None = None,
    ) -> None:
        if mode is None:
            mode = self._engine_mode
        if default_mode is None:
            default_mode = self._default_mode
        if ghost_shortcut is None:
            ghost_shortcut = self._ghost_shortcut

        changed = (
            self._engine_state != engine_state
            or self._engine_phase != phase
            or self._engine_mode != mode
            or self._default_mode != default_mode
            or self._active_subject_id != subject_id
            or self._subject_name != subject_name
            or self._display_seconds != display_seconds
            or self._remain_seconds != remain_seconds
        )
        self._engine_state = engine_state
        self._engine_phase = phase
        self._engine_mode = mode
        self._default_mode = default_mode
        self._active_subject_id = subject_id
        self._subject_name = subject_name
        self._display_seconds = max(0, int(display_seconds))
        self._remain_seconds = remain_seconds
        self._ghost_shortcut = ghost_shortcut
        if subjects_list is not None:
            self._subjects_list = list(subjects_list)

        if self._engine_state == TimerState.FINALIZING and self.card_open:
            self.card_open = False
            self.card_hover = None
            self.card_pressed = None
            changed = True

        if changed and self.hwnd:
            self.render_and_present()

    def notify_study_started(self) -> None:
        """AC#2: 학습 시작 시 다음 프레임 타이머를 기다리지 않고 즉시 STUDY 상태로 전환하고 다시 그린다."""
        self.fsm.on_study_started()
        self._anim_step = 0
        self._anim_accum = 0.0
        self._update_frame_timer_interval()
        self.render_and_present(force=True)

    def notify_study_stopped(self) -> None:
        self.fsm.on_study_stopped()
        self._anim_step = 0
        self._anim_accum = 0.0
        self._update_frame_timer_interval()
        self.render_and_present(force=True)

    def notify_session_finished(self) -> None:
        self.fsm.on_finished()
        self._anim_step = 0
        self._anim_accum = 0.0
        self._update_frame_timer_interval()
        self.render_and_present(force=True)

    def set_ghost_mode(self, enabled: bool) -> None:
        if not self.hwnd:
            return
        self.ghost_mode = bool(enabled)
        self._ghost_temp_interactive = False
        ex_style = int(user32.GetWindowLongPtrW(self.hwnd, GWL_EXSTYLE))
        if self.ghost_mode:
            self.card_open = False
            self.card_hover = None
            self.card_pressed = None
            ex_style |= WS_EX_TRANSPARENT
        else:
            ex_style &= ~WS_EX_TRANSPARENT
        user32.SetWindowLongPtrW(self.hwnd, GWL_EXSTYLE, LONG_PTR(ex_style))
        self.render_and_present(force=True)
        if self.on_ghost_toggled is not None:
            self.on_ghost_toggled(self.ghost_mode)

    def toggle_ghost_mode(self) -> None:
        self.set_ghost_mode(not self.ghost_mode)

    def _is_off_screen(self) -> bool:
        fx, fy = self.physics.screen_foot
        for m in list_monitors():
            if m.work.left <= fx <= m.work.right and m.work.top <= fy <= m.work.bottom:
                return False
        return True

    def summon_to_primary_center(self) -> None:
        invalidate_monitor_cache()
        mon = primary()
        self._current_dpi = mon.dpi
        self.scale = phys_scale(self.config_scale, self._current_dpi)
        self.sprites.set_scale(self.scale)
        self.panel_renderer.clear_cache()
        self.menu_icons.clear_cache()
        self.compositor.set_scale(self.scale)
        self._last_bubble_key = None
        self._last_card_key = None

        cx = (mon.work.left + mon.work.right) // 2
        cy = mon.work.bottom
        self.physics.foot_x = float(cx)
        self.physics.foot_y = float(cy)
        self.physics.vy_sp = 0.0
        self.physics.clamp_to_work(self._to_work_bounds(mon), self.scale)

        if self.ghost_mode:
            self.set_ghost_mode(False)
        else:
            self.render_and_present(force=True)

        if self.on_position_changed is not None:
            self.on_position_changed(self.physics.screen_foot)

    def _recalc_scale_for_foot(self) -> None:
        fx, fy = self.physics.screen_foot
        mon = monitor_at(fx, fy)
        new_scale = phys_scale(self.config_scale, mon.dpi)
        self._current_dpi = mon.dpi
        if new_scale != self.scale:
            self.scale = new_scale
            self.sprites.set_scale(new_scale)
            self.panel_renderer.clear_cache()
            self.menu_icons.clear_cache()
            self.compositor.set_scale(new_scale)
            self._last_bubble_key = None
            self._last_card_key = None
        self.physics.clamp_to_work(self._to_work_bounds(mon), self.scale)

    def _desired_frame_interval_ms(self) -> int:
        if self._dragging or self.fsm.state in (PetState.DRAG, PetState.FALL, PetState.LAND, PetState.CELEBRATE):
            return 16 if self.fps_limit == 60 else 33
        if self.fsm.state is PetState.WALK:
            return 1000 // self.fps_limit
        meta = self.sprites.state_meta(self.fsm.animation_key())
        return max(125, min(500, int(1000 // max(1, meta.fps))))

    def _update_frame_timer_interval(self) -> None:
        if not self.hwnd:
            return
        desired = self._desired_frame_interval_ms()
        if desired != self._current_frame_interval_ms:
            self._current_frame_interval_ms = desired
            user32.SetTimer(self.hwnd, TID_FRAME, desired, None)

    def _current_mode_label(self) -> str:
        return "뽀모도로" if self._default_mode == TimerMode.POMODORO else "스톱워치"

    def _current_card_buttons(self) -> list[CardButton]:
        return card_buttons(self._engine_state, self._engine_phase, self._current_mode_label())

    def _active_bubble_text_and_color(self) -> tuple[str, tuple[int, int, int]] | None:
        if self.card_open:
            return None

        now = time.perf_counter()
        # 1. 토스트가 가장 우선 (v0.7 8장 D2)
        if self._toast is not None:
            t_text, t_until = self._toast
            if now < t_until:
                return (t_text, (255, 248, 190))
            self._toast = None

        # 2. 학습/휴식/일시정지 상태 말풍선
        if self._engine_state is not TimerState.STOPPED:
            hms = format_hms(self._display_seconds)
            if self.bubble_collapsed:
                text = hms
            else:
                phase_prefix = "[휴식] " if self._engine_phase is Phase.BREAK else ""
                pause_prefix = "(일시정지) " if self._engine_state in (TimerState.PAUSED, TimerState.PAUSED_AFK) else ""
                subj = self._subject_name[:10]
                text = f"{pause_prefix}{phase_prefix}{subj} | {hms}"
            color = (160, 235, 190) if self._engine_phase is Phase.BREAK else (255, 250, 240)
            return (text, color)

        # 3. 첫 실행 안내 힌트 (v0.7 3-6)
        if now < self._hint_until:
            return (strings.HINT_FIRST_RUN, (255, 248, 230))

        # 4. 대기 중 캐릭터 호버 0.8초 안내 힌트 (v0.7 3-6)
        if self._hover_since is not None and (now - self._hover_since) >= 0.8:
            return (strings.HINT_HOVER, (220, 235, 255))

        return None

    def _build_bubble_layer(self, win_left_px: int, mon: MonitorInfo) -> tuple[bytes, int, int, int, int] | None:
        pair = self._active_bubble_text_and_color()
        if pair is None:
            self._cached_bubble_layer = None
            self._last_bubble_key = None
            return None

        text, color = pair
        key = (text, color, self.scale, win_left_px, mon.work.left, mon.work.right)
        if key == self._last_bubble_key and self._cached_bubble_layer is not None:
            return self._cached_bubble_layer

        tw_px, th_px = self.font_renderer.measure_text(self.compositor.surface.hdc, text, self.scale)
        box_sp = compute_bubble_box_sp(tw_px, self.scale, win_left_px, mon.work.left, mon.work.right)
        w_px = box_sp.w * self.scale
        h_px = box_sp.h * self.scale
        panel_bgra = self.panel_renderer.get_panel(box_sp.w, box_sp.h, self.scale)
        tx = max(4 * self.scale, (w_px - tw_px) // 2)
        ty = max(2 * self.scale, (h_px - th_px) // 2)
        rendered = self.font_renderer.render_on_panel(
            panel_bgra,
            w_px,
            h_px,
            self.scale,
            [(tx, ty, text, color)],
        )
        layer = (rendered, box_sp.x, box_sp.y, box_sp.w, box_sp.h)
        self._last_bubble_key = key
        self._cached_bubble_layer = layer
        return layer

    def _build_action_card_layer(self) -> tuple[bytes, int, int, int, int] | None:
        """상태별 액션 카드(176x78 sp)를 합성하고 캐시한다 (v0.7 3-4, 3-5, 3-7)."""
        if not self.card_open or self._engine_state == TimerState.FINALIZING:
            return None

        active_mode = self._default_mode if self._engine_state == TimerState.STOPPED else self._engine_mode
        header_left, header_right = card_header(
            self._engine_state,
            self._engine_phase,
            active_mode,
            self._subject_name[:8],
            self._display_seconds,
            self._remain_seconds,
        )
        mode_lbl = self._current_mode_label()
        buttons = card_buttons(self._engine_state, self._engine_phase, mode_lbl)
        enabled_mask = tuple(b.enabled for b in buttons)

        key = (
            self._engine_state,
            self._engine_phase,
            header_left,
            header_right,
            mode_lbl,
            self.card_hover,
            self.card_pressed,
            enabled_mask,
            self.scale,
        )
        if key == self._last_card_key and self._cached_card_layer is not None:
            return self._cached_card_layer

        s = self.scale
        w_px = CARD_BOX_SP.w * s
        h_px = CARD_BOX_SP.h * s
        buf = bytearray(self.panel_renderer.get_panel(CARD_BOX_SP.w, CARD_BOX_SP.h, s))

        text_lines: list[tuple[int, int, str, tuple[int, int, int]]] = []
        hdc = self.compositor.surface.hdc

        # 헤더 왼쪽·오른쪽 텍스트
        hx_left = (CARD_HEADER_LEFT_SP[0] - CARD_BOX_SP.x) * s
        hy_left = (CARD_HEADER_LEFT_SP[1] - CARD_BOX_SP.y) * s
        text_lines.append((hx_left, hy_left, header_left, RGB_TEXT_NORMAL))

        if header_right:
            rw_px, _ = self.font_renderer.measure_text(hdc, header_right, s)
            hx_right = max(hx_left, (CARD_HEADER_RIGHT_X_SP - CARD_BOX_SP.x) * s - rw_px)
            hy_right = (CARD_HEADER_Y_SP - CARD_BOX_SP.y) * s
            text_lines.append((hx_right, hy_right, header_right, RGB_TEXT_SUB))

        # 각 버튼 배경 사각형, 주 버튼 아이콘, 버튼 라벨 배치
        for btn in buttons:
            is_pressed = btn.enabled and (self.card_pressed == btn.key)
            is_hover = btn.enabled and (self.card_hover == btn.key)

            if not btn.enabled:
                bg_color = BGRA_BTN_NORMAL
            elif is_pressed:
                bg_color = BGRA_BTN_PRESSED
            elif is_hover:
                bg_color = BGRA_BTN_PRIMARY_HOVER if btn.style == "primary" else BGRA_BTN_HOVER
            else:
                bg_color = BGRA_BTN_PRIMARY if btn.style == "primary" else BGRA_BTN_NORMAL

            bx_px = (btn.box.x - CARD_BOX_SP.x) * s
            by_px = (btn.box.y - CARD_BOX_SP.y) * s
            bw_px = btn.box.w * s
            bh_px = btn.box.h * s
            fill_rect(buf, w_px, bx_px, by_px, bw_px, bh_px, bg_color)

            y_off_sp = 1 if is_pressed else 0
            txt_color = RGB_TEXT_NORMAL if btn.enabled else RGB_TEXT_DISABLED

            if btn.icon is not None:
                ibytes = self.menu_icons.get_icon_on_bg(btn.icon, bg_color, s)
                ix_px = (CARD_PRIMARY_ICON_SP[0] - CARD_BOX_SP.x) * s
                iy_px = (CARD_PRIMARY_ICON_SP[1] - CARD_BOX_SP.y + y_off_sp) * s
                iw_px = ICON_SIZE_SP * s
                ih_px = ICON_SIZE_SP * s
                stride = w_px * 4
                icon_stride = iw_px * 4
                for ry in range(ih_px):
                    dst_row = (iy_px + ry) * stride + ix_px * 4
                    src_row = ry * icon_stride
                    buf[dst_row : dst_row + icon_stride] = ibytes[src_row : src_row + icon_stride]

                lx_px = (CARD_PRIMARY_LABEL_SP[0] - CARD_BOX_SP.x) * s
                ly_px = (CARD_PRIMARY_LABEL_SP[1] - CARD_BOX_SP.y + y_off_sp) * s
                text_lines.append((lx_px, ly_px, btn.label, txt_color))
            else:
                tw_px, th_px = self.font_renderer.measure_text(hdc, btn.label, s)
                lx_px = bx_px + max(2 * s, (bw_px - tw_px) // 2)
                ly_px = by_px + max(1 * s, (bh_px - th_px) // 2) + y_off_sp * s
                text_lines.append((lx_px, ly_px, btn.label, txt_color))

        rendered = self.font_renderer.render_on_panel(bytes(buf), w_px, h_px, s, text_lines)
        layer = (rendered, CARD_BOX_SP.x, CARD_BOX_SP.y, CARD_BOX_SP.w, CARD_BOX_SP.h)
        self._last_card_key = key
        self._cached_card_layer = layer
        return layer

    def render_and_present(self, force: bool = False) -> None:
        if not self.hwnd:
            return
        t0 = time.perf_counter()
        fx, fy = self.physics.screen_foot
        mon = monitor_at(fx, fy)
        win_x, win_y = window_top_left_from_foot(fx, fy, self.scale)

        anim_key = self.fsm.animation_key()
        flip = self.fsm.facing > 0 and anim_key in ("idle", "walk", "sit", "drag", "fall", "land")
        char_bytes = self.sprites.get_frame(anim_key, self._anim_step, self.scale, flip=flip)
        self.compositor.set_character(char_bytes)

        self.compositor.set_menu(None)
        if self.card_open and self._engine_state != TimerState.FINALIZING:
            self.compositor.set_panel(self._build_action_card_layer())
            self.compositor.set_bubble(None)
        else:
            self.compositor.set_panel(None)
            self.compositor.set_bubble(self._build_bubble_layer(win_x, mon))

        if force:
            self.compositor.mark_dirty()

        opacity = 0.30 if self.ghost_mode else 1.0
        presented = self.compositor.present(self.hwnd, win_x, win_y, opacity=opacity)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        if presented:
            self._render_sum_ms += elapsed_ms
            self._render_count += 1

        now_p = time.perf_counter()
        if now_p - self._last_perf_flush >= 60.0:
            if self._render_count > 0:
                avg_ms = self._render_sum_ms / self._render_count
                self.log_perf_line(f"render_ms={avg_ms:.3f} samples={self._render_count}")
                self._render_sum_ms = 0.0
                self._render_count = 0
            if self._menu_lat_count > 0:
                lat_avg = self._menu_lat_sum_ms / self._menu_lat_count
                self.log_perf_line(
                    f"menu_latency_ms_avg={lat_avg:.3f} max={self._menu_lat_max_ms:.3f} count={self._menu_lat_count}"
                )
                self._menu_lat_sum_ms = 0.0
                self._menu_lat_max_ms = 0.0
                self._menu_lat_count = 0
            self._last_perf_flush = now_p

    def _on_frame_timer(self) -> None:
        now = time.perf_counter()
        dt = max(0.0, min(0.25, now - self._last_frame_mono))
        self._last_frame_mono = now

        fx, fy = self.physics.screen_foot
        mon = monitor_at(fx, fy)
        work = self._to_work_bounds(mon)
        studying = self._engine_state is TimerState.RUNNING
        ctx = FsmContext(
            studying=studying,
            on_ground=not self.physics.is_airborne(work),
            walk_enabled=self.walk_enabled,
            user_idle_ms=self._user_idle_ms,
        )

        prev_state = self.fsm.state
        self.fsm.update(dt, ctx)
        if not self._dragging:
            new_facing, landed = self.physics.step(dt, self.fsm.state, self.fsm.facing, work, self.scale)
            self.fsm.facing = new_facing
            if landed:
                self.fsm.on_landed()

        if self.fsm.state != prev_state:
            self._anim_step = 0
            self._anim_accum = 0.0
        else:
            meta = self.sprites.state_meta(self.fsm.animation_key())
            frame_dur = 1.0 / max(1, meta.fps)
            self._anim_accum += dt
            while self._anim_accum >= frame_dur:
                self._anim_accum -= frame_dur
                self._anim_step += 1

        self._update_frame_timer_interval()
        self.render_and_present()

    def _on_ui_timer(self) -> None:
        if not self.hwnd:
            return
        pt = POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        fx, fy = self.physics.screen_foot
        win_x, win_y = window_top_left_from_foot(fx, fy, self.scale)
        win_w = CANVAS_W_SP * self.scale
        win_h = CANVAS_H_SP * self.scale
        inside_canvas = (win_x <= pt.x < win_x + win_w) and (win_y <= pt.y < win_y + win_h)
        rel_x_sp, rel_y_sp = px_to_sp(pt.x - win_x, pt.y - win_y, self.scale)

        now = time.perf_counter()
        needs_redraw = False

        # 1. 첫 실행 2초 후 안내 힌트 시작 (v0.7 3-6)
        if not self.hint_shown and self._first_run_hint_due is not None and now >= self._first_run_hint_due:
            self._first_run_hint_due = None
            self._hint_until = now + 10.0
            needs_redraw = True

        # 2. 첫 실행 힌트·토스트 만료 확인
        if self._hint_until > 0.0 and now >= self._hint_until:
            self._hint_until = 0.0
            needs_redraw = True
        if self._toast is not None and now >= self._toast[1]:
            self._toast = None
            needs_redraw = True

        # 3. 대기 중 캐릭터 호버 0.8초 힌트 판정
        if self._hover_since is not None and not self.card_open and self._engine_state == TimerState.STOPPED:
            if 0.8 <= (now - self._hover_since) < 0.95:
                needs_redraw = True

        # 4. 카드 외부 클릭 또는 8초간 카드/캐릭터 위에 커서 없음 시 닫기 (v0.7 3-3, 4-4)
        # 버튼 상태는 매 틱 읽어 '직전 호출 이후 눌림' 비트(0x0001)를 최신으로 유지한다.
        # 100ms 폴링 사이에 끝난 짧은 클릭도 이 비트로 잡는다.
        clicked = self._poll_mouse_clicked()
        if self.card_open:
            on_card_or_char = inside_canvas and (
                CARD_BOX_SP.contains(rel_x_sp, rel_y_sp) or CHARACTER_BOX_SP.contains(rel_x_sp, rel_y_sp)
            )
            if on_card_or_char:
                self._last_card_activity_mono = now
            # 캔버스의 투명 영역 클릭은 아래 창으로 투과되므로 바깥 클릭으로 본다
            outside_click = clicked and not on_card_or_char
            inactive_8s = (now - self._last_card_activity_mono) >= 8.0
            if outside_click or inactive_8s:
                self.card_open = False
                self.card_hover = None
                self.card_pressed = None
                needs_redraw = True

        # 5. 유령 모드 보조 해제 경로: Alt 키를 누른 채 캐릭터 박스 위에 호버하면 임시로 WS_EX_TRANSPARENT 해제 (4-12)
        if self.ghost_mode:
            alt_down = bool(user32.GetAsyncKeyState(VK_MENU) & 0x8000)
            inside_char = CHARACTER_BOX_SP.contains(rel_x_sp, rel_y_sp)
            want_interactive = alt_down and inside_char
            if want_interactive != self._ghost_temp_interactive:
                self._ghost_temp_interactive = want_interactive
                ex_style = int(user32.GetWindowLongPtrW(self.hwnd, GWL_EXSTYLE))
                if want_interactive:
                    ex_style &= ~WS_EX_TRANSPARENT
                else:
                    ex_style |= WS_EX_TRANSPARENT
                user32.SetWindowLongPtrW(self.hwnd, GWL_EXSTYLE, LONG_PTR(ex_style))

        if needs_redraw:
            self.render_and_present()

    def _is_inside_bubble(self, x_sp: int, y_sp: int) -> bool:
        if self.card_open or self._cached_bubble_layer is None:
            return False
        _, bx, by, bw, bh = self._cached_bubble_layer
        return bx <= x_sp < (bx + bw) and by <= y_sp < (by + bh)

    @staticmethod
    def _poll_mouse_clicked() -> bool:
        """좌·우 버튼이 지금 눌려 있거나 직전 호출 이후 눌린 적이 있으면 True."""
        l_state = int(user32.GetAsyncKeyState(VK_LBUTTON))
        r_state = int(user32.GetAsyncKeyState(VK_RBUTTON))
        return bool((l_state | r_state) & 0x8001)

    def _handle_locked_click(self) -> None:
        """모달이 떠 있을 때 캐릭터·말풍선을 클릭하면 카드 대신 해당 모달을 앞으로 가져온다 (AFK 창 등)."""
        if self.on_locked_click is not None:
            self.on_locked_click()

    def toggle_card(self) -> None:
        """액션 카드 열기/닫기 토글 (v0.7 3-3)."""
        if self.modal_locked:
            self._handle_locked_click()
            return
        if self.ghost_mode or self._engine_state == TimerState.FINALIZING:
            return
        self.card_open = not self.card_open
        self.card_hover = None
        self.card_pressed = None
        self._last_card_activity_mono = time.perf_counter()
        if self.card_open:
            self._poll_mouse_clicked()  # 카드를 연 클릭(트레이 클릭 등)이 바깥 클릭으로 오인되지 않도록 비트를 비운다
            self._hint_until = 0.0
            self._first_run_hint_due = None
            if not self.hint_shown:
                self.hint_shown = True
                if self.on_card_opened is not None:
                    self.on_card_opened()
        self.render_and_present(force=True)

    def _button_anchor_px(self, key: str) -> tuple[int, int] | None:
        """카드 버튼의 왼쪽 아래 모서리 화면 좌표(px)를 반환한다 (v0.7 8장 D1)."""
        fx, fy = self.physics.screen_foot
        win_x, win_y = window_top_left_from_foot(fx, fy, self.scale)
        s = self.scale
        for btn in self._current_card_buttons():
            if btn.key == key:
                return (win_x + btn.box.x * s, win_y + (btn.box.y + btn.box.h) * s)
        return None

    def _show_subject_popup_menu(self, anchor_px: tuple[int, int] | None = None) -> None:
        if self.modal_locked or self.ghost_mode or not self.hwnd:
            return
        items: list[tuple[int, str, int]] = []
        for sid, sname in self._subjects_list:
            flags = MF_STRING | (MF_CHECKED if sid == self._active_subject_id else 0)
            items.append((CMD_SUBJECT_BASE + int(sid), sname, flags))
        if items:
            items.append((0, "", MF_SEPARATOR))
        items.append((CMD_MANAGE_SUBJECTS, strings.MORE_MANAGE_SUBJECTS_ELLIPSIS, MF_STRING))

        cmd = show_popup(self.hwnd, items, anchor_px)
        if cmd == CMD_MANAGE_SUBJECTS:
            if self.on_open_dashboard is not None:
                self.on_open_dashboard(0)
        elif cmd > CMD_SUBJECT_BASE:
            sid = cmd - CMD_SUBJECT_BASE
            if self.on_select_subject is not None:
                self.on_select_subject(sid)

    def _show_mode_popup_menu(self, anchor_px: tuple[int, int] | None = None) -> None:
        if self.modal_locked or self.ghost_mode or not self.hwnd:
            return
        pomo_flags = MF_STRING | (MF_CHECKED if self._default_mode == TimerMode.POMODORO else 0)
        sw_flags = MF_STRING | (MF_CHECKED if self._default_mode == TimerMode.STOPWATCH else 0)
        items = [
            (CMD_MODE_POMODORO, strings.MODE_LABEL_POMODORO, pomo_flags),
            (CMD_MODE_STOPWATCH, strings.MODE_LABEL_STOPWATCH, sw_flags),
        ]
        cmd = show_popup(self.hwnd, items, anchor_px)
        if cmd == CMD_MODE_POMODORO and self.on_select_mode is not None:
            self.on_select_mode("POMODORO")
        elif cmd == CMD_MODE_STOPWATCH and self.on_select_mode is not None:
            self.on_select_mode("STOPWATCH")

    def _show_more_popup_menu(self, anchor_px: tuple[int, int] | None = None) -> None:
        if self.modal_locked or self.ghost_mode or not self.hwnd:
            return
        bubble_lbl = strings.MORE_BUBBLE_COLLAPSED  # 체크 표시는 MF_CHECKED 하나로만 표시
        bubble_flags = MF_STRING | (MF_CHECKED if self.bubble_collapsed else 0)
        items = [
            (CMD_MORE_SUBJECTS, strings.MORE_MANAGE_SUBJECTS, MF_STRING),
            (CMD_MORE_BUBBLE_TOGGLE, bubble_lbl, bubble_flags),
            (CMD_MORE_GHOST_MODE, strings.format_more_ghost(self._ghost_shortcut), MF_STRING),
            (CMD_MORE_SUMMON_CENTER, strings.MORE_SUMMON_CENTER, MF_STRING),
            (0, "", MF_SEPARATOR),
            (CMD_MORE_QUIT, strings.MORE_QUIT_APP, MF_STRING),
        ]
        cmd = show_popup(self.hwnd, items, anchor_px)
        if cmd == CMD_MORE_BUBBLE_TOGGLE:
            self.bubble_collapsed = not self.bubble_collapsed
            self._last_bubble_key = None
            self.render_and_present(force=True)
        if cmd > 0 and self.on_more_command is not None:
            self.on_more_command(cmd)

    def _execute_card(self, key: str) -> None:
        """카드 버튼 실행 (v0.7 4-4, 8장 D1)."""
        anchor = self._button_anchor_px(key)
        self.card_open = False
        self.card_hover = None
        self.card_pressed = None
        self.render_and_present(force=True)

        if key == "primary":
            if self.on_primary is not None:
                self.on_primary()
            elif self.on_quick_start_or_toggle is not None:
                self.on_quick_start_or_toggle()
        elif key == "end":
            if self.on_stop_requested is not None:
                self.on_stop_requested()
        elif key == "subject":
            self._show_subject_popup_menu(anchor)
        elif key == "mode":
            self._show_mode_popup_menu(anchor)
        elif key == "stats":
            if self.on_open_dashboard is not None:
                self.on_open_dashboard(2)
        elif key == "settings":
            if self.on_open_dashboard is not None:
                self.on_open_dashboard(1)
        elif key == "more":
            self._show_more_popup_menu(anchor)

    def _handle_lbutton_down(self, x_px: int, y_px: int) -> None:
        if self.modal_locked:
            return
        x_sp, y_sp = px_to_sp(x_px, y_px, self.scale)
        self.card_pressed = None
        self._pressing_bubble = False

        if self.card_open:
            self._last_card_activity_mono = time.perf_counter()
            hit = hit_test_card(self._current_card_buttons(), x_sp, y_sp)
            if hit is not None:
                self.card_pressed = hit
                self.render_and_present()
                return
            if CARD_BOX_SP.contains(x_sp, y_sp):
                return

        if CHARACTER_BOX_SP.contains(x_sp, y_sp):
            pt = POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            self._drag_start_cursor = (int(pt.x), int(pt.y))
            self._drag_start_foot = (self.physics.foot_x, self.physics.foot_y)
            self._pressing = True
            self._dragging = False
            user32.SetCapture(self.hwnd)
        elif self._is_inside_bubble(x_sp, y_sp):
            self._pressing_bubble = True

    def _handle_mouse_move(self, x_px: int, y_px: int) -> None:
        now = time.perf_counter()
        if not self._tracking_leave and self.hwnd:
            tme = TRACKMOUSEEVENT(ctypes.sizeof(TRACKMOUSEEVENT), TME_LEAVE, self.hwnd, 0)
            if user32.TrackMouseEvent(ctypes.byref(tme)):
                self._tracking_leave = True

        x_sp, y_sp = px_to_sp(x_px, y_px, self.scale)

        if self._pressing:
            pt = POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            dx = int(pt.x) - self._drag_start_cursor[0]
            dy = int(pt.y) - self._drag_start_cursor[1]
            threshold = 4 * self.scale
            if not self._dragging and (abs(dx) >= threshold or abs(dy) >= threshold):
                self._dragging = True
                self.card_open = False
                self.card_hover = None
                self.card_pressed = None
                self._hover_since = None
                self.fsm.on_drag_start()
                self._update_frame_timer_interval()

            if self._dragging:
                self.physics.foot_x = self._drag_start_foot[0] + dx
                self.physics.foot_y = self._drag_start_foot[1] + dy
                self._recalc_scale_for_foot()
                self.render_and_present()
                return

        if CHARACTER_BOX_SP.contains(x_sp, y_sp) and not self.card_open:
            if self._hover_since is None:
                self._hover_since = now
        else:
            if self._hover_since is not None:
                self._hover_since = None
                self.render_and_present()

        if self.card_open:
            if CARD_BOX_SP.contains(x_sp, y_sp) or CHARACTER_BOX_SP.contains(x_sp, y_sp):
                self._last_card_activity_mono = now
            hover = hit_test_card(self._current_card_buttons(), x_sp, y_sp)
            if hover != self.card_hover:
                self.card_hover = hover
                self.render_and_present()

    def _handle_mouse_leave(self) -> None:
        self._tracking_leave = False
        changed = (self.card_hover is not None) or (self._hover_since is not None)
        self.card_hover = None
        self._hover_since = None
        if changed:
            self.render_and_present()

    def _handle_lbutton_up(self, x_px: int, y_px: int) -> None:
        click_t0 = time.perf_counter()
        if self._pressing:
            user32.ReleaseCapture()

        was_pressing = self._pressing
        was_pressing_bubble = self._pressing_bubble
        was_dragging = self._dragging
        self._pressing = False
        self._pressing_bubble = False
        self._dragging = False

        if was_dragging:
            fx, fy = self.physics.screen_foot
            mon = monitor_at(fx, fy)
            airborne = self.physics.snap_to_ground_if_close(self._to_work_bounds(mon))
            self.fsm.on_drag_end(airborne)
            self._update_frame_timer_interval()
            self.render_and_present()
            if self.on_position_changed is not None:
                self.on_position_changed(self.physics.screen_foot)
            return

        x_sp, y_sp = px_to_sp(x_px, y_px, self.scale)

        if self.modal_locked:
            self.card_pressed = None
            if CHARACTER_BOX_SP.contains(x_sp, y_sp) or self._is_inside_bubble(x_sp, y_sp):
                self._handle_locked_click()
            return

        if self.card_pressed is not None:
            target = self.card_pressed
            self.card_pressed = None
            hit = hit_test_card(self._current_card_buttons(), x_sp, y_sp)
            self.render_and_present()
            if hit == target:
                self._execute_card(target)
            return

        if (was_pressing and CHARACTER_BOX_SP.contains(x_sp, y_sp)) or (
            was_pressing_bubble and self._is_inside_bubble(x_sp, y_sp)
        ):
            self.fsm.on_click()
            self.toggle_card()
            latency_ms = (time.perf_counter() - click_t0) * 1000.0
            self._record_menu_latency(latency_ms)

    def _wnd_proc(self, hwnd: wt.HWND, msg: int, wparam: int, lparam: int) -> int:
        try:
            if msg == WM_MOUSEACTIVATE:
                return MA_NOACTIVATE

            if msg == WM_DPICHANGED:
                return 0

            if msg == WM_QUERYENDSESSION:
                return 1

            if msg == WM_ENDSESSION:
                if int(wparam):
                    if self.on_end_session is not None:
                        self.on_end_session()
                return 0

            if msg == WM_TIMER:
                tid = int(wparam)
                if tid == TID_FRAME:
                    self._on_frame_timer()
                elif tid == TID_ENGINE:
                    if self.on_engine_tick is not None:
                        self.on_engine_tick()
                elif tid == TID_IDLE:
                    if self.on_idle_tick is not None:
                        self._user_idle_ms = self.on_idle_tick()
                elif tid == TID_UI:
                    self._on_ui_timer()
                elif tid == TID_TOPMOST:
                    user32.SetWindowPos(
                        hwnd,
                        HWND_TOPMOST,
                        0,
                        0,
                        0,
                        0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
                    )
                elif tid == TID_SAVE_CFG:
                    user32.KillTimer(hwnd, TID_SAVE_CFG)
                    if self.on_save_config_timer is not None:
                        self.on_save_config_timer()
                return 0

            if msg == WM_LBUTTONDOWN:
                self._handle_lbutton_down(_signed_loword(lparam), _signed_hiword(lparam))
                return 0

            if msg == WM_MOUSEMOVE:
                self._handle_mouse_move(_signed_loword(lparam), _signed_hiword(lparam))
                return 0

            if msg == WM_MOUSELEAVE:
                self._handle_mouse_leave()
                return 0

            if msg == WM_LBUTTONUP:
                self._handle_lbutton_up(_signed_loword(lparam), _signed_hiword(lparam))
                return 0

            if msg == WM_CAPTURECHANGED:
                if self._dragging:
                    self._pressing = False
                    self._dragging = False
                    fx, fy = self.physics.screen_foot
                    mon = monitor_at(fx, fy)
                    airborne = self.physics.snap_to_ground_if_close(self._to_work_bounds(mon))
                    self.fsm.on_drag_end(airborne)
                    self._update_frame_timer_interval()
                    self.render_and_present()
                return 0

            if msg == WM_RBUTTONUP:
                x_sp, y_sp = px_to_sp(_signed_loword(lparam), _signed_hiword(lparam), self.scale)
                on_pet = CHARACTER_BOX_SP.contains(x_sp, y_sp) or self._is_inside_bubble(x_sp, y_sp)
                if self.modal_locked:
                    if on_pet:
                        self._handle_locked_click()
                else:
                    if self.card_open and CARD_BOX_SP.contains(x_sp, y_sp):
                        return 0
                    if on_pet:
                        click_t0 = time.perf_counter()
                        self.fsm.on_click()
                        self.toggle_card()
                        self._record_menu_latency((time.perf_counter() - click_t0) * 1000.0)
                return 0

            if msg == WM_MOUSEWHEEL:
                if user32.GetKeyState(VK_MENU) < 0:
                    self.toggle_ghost_mode()
                return 0

            if msg == WM_HOTKEY:
                if int(wparam) == 1:
                    self.toggle_ghost_mode()
                return 0

            if msg == WM_APP_TRAY:
                ev = int(lparam) & 0xFFFF
                if ev == WM_RBUTTONUP:
                    if self.on_tray_menu is not None:
                        self.on_tray_menu()
                elif ev == WM_LBUTTONDBLCLK:
                    self.summon_to_primary_center()
                elif ev == WM_LBUTTONUP:
                    if self._is_off_screen() or self.ghost_mode:
                        self.summon_to_primary_center()
                    if not self.card_open:
                        self.toggle_card()
                return 0

            if self._msg_taskbar_created and msg == self._msg_taskbar_created:
                if self.on_taskbar_created is not None:
                    self.on_taskbar_created()
                return 0

            if msg == WM_POWERBROADCAST:
                wp = int(wparam)
                if wp == PBT_APMSUSPEND:
                    if self.on_suspend is not None:
                        self.on_suspend()
                elif wp in (PBT_APMRESUMESUSPEND, PBT_APMRESUMEAUTOMATIC):
                    invalidate_monitor_cache()
                    if self.on_resume_power is not None:
                        self.on_resume_power()
                return 1

            if msg == WM_WTSSESSION_CHANGE:
                wp = int(wparam)
                if wp == WTS_SESSION_LOCK:
                    if self.on_session_lock is not None:
                        self.on_session_lock()
                elif wp == WTS_SESSION_UNLOCK:
                    if self.on_session_unlock is not None:
                        self.on_session_unlock()
                return 0

            if msg in (WM_DISPLAYCHANGE, WM_SETTINGCHANGE):
                invalidate_monitor_cache()
                self._recalc_scale_for_foot()
                self.render_and_present(force=True)
                return 0

            if msg == WM_APP_SUMMON:
                self.summon_to_primary_center()
                return 0

            if msg == WM_APP_POST_START:
                if self.on_post_start is not None:
                    self.on_post_start()
                return 0

            if msg == WM_DESTROY:
                return 0

        except Exception:
            write_crash_log()
            return 0

        return int(user32.DefWindowProcW(hwnd, msg, WPARAM(wparam), LPARAM(lparam)))

    def destroy(self) -> None:
        if self.hwnd:
            for tid in (TID_FRAME, TID_ENGINE, TID_IDLE, TID_UI, TID_TOPMOST, TID_SAVE_CFG):
                user32.KillTimer(self.hwnd, tid)
            try:
                wtsapi32.WTSUnRegisterSessionNotification(self.hwnd)
            except OSError:
                pass
            user32.DestroyWindow(self.hwnd)
            self.hwnd = wt.HWND(0)
        self.compositor.destroy()
        self.font_renderer.destroy()
