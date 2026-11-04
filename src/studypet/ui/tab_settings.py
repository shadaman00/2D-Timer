"""대시보드 탭 2: 타이머·캐릭터·사운드·단축키 설정 (DEVELOPMENT_PLAN.md 4-16)."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
import ctypes
from ctypes import wintypes as wt

from studypet.crashlog import write_crash_log
from studypet.infra.config import AppConfig, SettingsPatch
from studypet.strings import MSG_SETTINGS_INVALID, MSG_SETTINGS_SAVED
from studypet.ui.modals import show_info_message
from studypet.win32.api import (
    IDC_ARROW,
    LPARAM,
    LRESULT,
    WM_COMMAND,
    WM_DESTROY,
    WM_SETFONT,
    WNDCLASSEXW,
    WNDPROC,
    WPARAM,
    WS_BORDER,
    WS_CHILD,
    WS_EX_CONTROLPARENT,
    WS_TABSTOP,
    WS_VISIBLE,
    kernel32,
    user32,
)
from studypet.win32.hotkey import hk_word_to_hotkey_string, hotkey_string_to_hk_word


TAB_SET_CLASS = "StudyPetTabSettings"
_tab_set_registered = False

ID_CMB_MODE = 401
ID_EDIT_FOCUS = 402
ID_EDIT_BREAK = 403
ID_EDIT_AFK = 404
ID_CMB_SCALE = 405
ID_CHK_WALK = 406
ID_CMB_FPS = 407
ID_CHK_SOUND = 408
ID_TRK_VOLUME = 409
ID_HK_GHOST = 410
ID_BTN_APPLY = 411

CBS_DROPDOWNLIST = 0x0003
CB_ADDSTRING = 0x0143
CB_SETCURSEL = 0x014E
CB_GETCURSEL = 0x0147

ES_NUMBER = 0x2000
BS_AUTOCHECKBOX = 0x0003
BS_DEFPUSHBUTTON = 0x0001
BM_GETCHECK = 0x00F0
BM_SETCHECK = 0x00F1

WM_USER = 0x0400
TBM_GETPOS = WM_USER
TBM_SETPOS = WM_USER + 5
TBM_SETRANGE = WM_USER + 6

HKM_SETHOTKEY = WM_USER + 1
HKM_GETHOTKEY = WM_USER + 2

COLOR_BTNFACE = 15


class SettingsTab:
    """타이머, 캐릭터 배율·배회·FPS, 효과음 볼륨, 유령 모드 단축키 설정 탭 패널."""

    def __init__(
        self,
        parent_hwnd: wt.HWND,
        x: int,
        y: int,
        w: int,
        h: int,
        dpi: int,
        hfont: wt.HFONT,
        current_config: AppConfig,
        on_apply: Callable[[SettingsPatch], None],
    ) -> None:
        self.s = max(1.0, dpi / 96.0)
        self.hfont = hfont
        self.config = current_config
        self.on_apply = on_apply

        self._wndproc_ref = WNDPROC(self._wnd_proc)
        self._ensure_class()

        hinst = kernel32.GetModuleHandleW(None)
        self.hwnd: wt.HWND = user32.CreateWindowExW(
            WS_EX_CONTROLPARENT,
            TAB_SET_CLASS,
            "",
            WS_CHILD,
            int(x),
            int(y),
            int(w),
            int(h),
            parent_hwnd,
            None,
            hinst,
            None,
        )

        def px(v: int) -> int:
            return int(round(v * self.s))

        # 1. 기본 모드
        self._create_ctrl("STATIC", "기본 타이머 모드:", WS_CHILD | WS_VISIBLE, px(24), px(20), px(160), px(24), 0)
        self._cmb_mode = self._create_ctrl(
            "COMBOBOX",
            "",
            WS_CHILD | WS_VISIBLE | WS_TABSTOP | CBS_DROPDOWNLIST,
            px(200),
            px(16),
            px(180),
            px(120),
            ID_CMB_MODE,
        )
        self._combo_add(self._cmb_mode, "스톱워치 (STOPWATCH)")
        self._combo_add(self._cmb_mode, "뽀모도로 (POMODORO)")

        # 2. 뽀모도로 집중/휴식 및 AFK 분
        self._create_ctrl("STATIC", "뽀모도로 집중(1~180분):", WS_CHILD | WS_VISIBLE, px(24), px(58), px(170), px(24), 0)
        self._edit_focus = self._create_ctrl(
            "EDIT",
            "",
            WS_CHILD | WS_VISIBLE | WS_BORDER | WS_TABSTOP | ES_NUMBER,
            px(200),
            px(54),
            px(80),
            px(26),
            ID_EDIT_FOCUS,
        )

        self._create_ctrl("STATIC", "휴식(1~60분):", WS_CHILD | WS_VISIBLE, px(300), px(58), px(110), px(24), 0)
        self._edit_break = self._create_ctrl(
            "EDIT",
            "",
            WS_CHILD | WS_VISIBLE | WS_BORDER | WS_TABSTOP | ES_NUMBER,
            px(415),
            px(54),
            px(80),
            px(26),
            ID_EDIT_BREAK,
        )

        self._create_ctrl("STATIC", "자리 비움 감지(1~120분):", WS_CHILD | WS_VISIBLE, px(24), px(96), px(170), px(24), 0)
        self._edit_afk = self._create_ctrl(
            "EDIT",
            "",
            WS_CHILD | WS_VISIBLE | WS_BORDER | WS_TABSTOP | ES_NUMBER,
            px(200),
            px(92),
            px(80),
            px(26),
            ID_EDIT_AFK,
        )

        # 3. 캐릭터 배율(1~4), 자율 배회, FPS(30/60)
        self._create_ctrl("STATIC", "캐릭터 배율(1x ~ 4x):", WS_CHILD | WS_VISIBLE, px(24), px(136), px(170), px(24), 0)
        self._cmb_scale = self._create_ctrl(
            "COMBOBOX",
            "",
            WS_CHILD | WS_VISIBLE | WS_TABSTOP | CBS_DROPDOWNLIST,
            px(200),
            px(132),
            px(100),
            px(140),
            ID_CMB_SCALE,
        )
        for sc in ("1x (64px)", "2x (128px)", "3x (192px)", "4x (256px)"):
            self._combo_add(self._cmb_scale, sc)

        self._chk_walk = self._create_ctrl(
            "BUTTON",
            "평상시 캐릭터 자율 배회(걷기) 허용",
            WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_AUTOCHECKBOX,
            px(320),
            px(134),
            px(250),
            px(26),
            ID_CHK_WALK,
        )

        self._create_ctrl("STATIC", "최대 프레임(FPS):", WS_CHILD | WS_VISIBLE, px(24), px(176), px(170), px(24), 0)
        self._cmb_fps = self._create_ctrl(
            "COMBOBOX",
            "",
            WS_CHILD | WS_VISIBLE | WS_TABSTOP | CBS_DROPDOWNLIST,
            px(200),
            px(172),
            px(100),
            px(100),
            ID_CMB_FPS,
        )
        self._combo_add(self._cmb_fps, "30 FPS")
        self._combo_add(self._cmb_fps, "60 FPS")

        # 4. 효과음 및 볼륨 트랙바 (msctls_trackbar32)
        self._chk_sound = self._create_ctrl(
            "BUTTON",
            "효과음 재생 사용",
            WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_AUTOCHECKBOX,
            px(24),
            px(216),
            px(170),
            px(26),
            ID_CHK_SOUND,
        )
        self._create_ctrl("STATIC", "효과음 볼륨(0~100):", WS_CHILD | WS_VISIBLE, px(200), px(218), px(140), px(24), 0)
        self._trk_volume = self._create_ctrl(
            "msctls_trackbar32",
            "",
            WS_CHILD | WS_VISIBLE | WS_TABSTOP,
            px(340),
            px(212),
            px(210),
            px(32),
            ID_TRK_VOLUME,
        )
        user32.SendMessageW(self._trk_volume, TBM_SETRANGE, 1, (100 << 16) | 0)

        # 5. 유령 모드 단축키 (msctls_hotkey32)
        self._create_ctrl("STATIC", "유령 모드 해제 단축키:", WS_CHILD | WS_VISIBLE, px(24), px(262), px(170), px(24), 0)
        self._hk_ghost = self._create_ctrl(
            "msctls_hotkey32",
            "",
            WS_CHILD | WS_VISIBLE | WS_TABSTOP,
            px(200),
            px(258),
            px(180),
            px(26),
            ID_HK_GHOST,
        )

        # 6. 적용 버튼
        self._btn_apply = self._create_ctrl(
            "BUTTON",
            "적용",
            WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_DEFPUSHBUTTON,
            px(240),
            px(312),
            px(120),
            px(34),
            ID_BTN_APPLY,
        )

        self.load_from_config(current_config)

    def _ensure_class(self) -> None:
        global _tab_set_registered
        if _tab_set_registered:
            return
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.style = 0
        wc.lpfnWndProc = self._wndproc_ref
        wc.cbClsExtra = 0
        wc.cbWndExtra = 0
        wc.hInstance = hinst
        wc.hIcon = None
        wc.hCursor = user32.LoadCursorW(None, ctypes.c_void_p(IDC_ARROW))
        wc.hbrBackground = wt.HBRUSH(COLOR_BTNFACE + 1)
        wc.lpszMenuName = None
        wc.lpszClassName = TAB_SET_CLASS
        wc.hIconSm = None
        user32.RegisterClassExW(ctypes.byref(wc))
        _tab_set_registered = True

    def _create_ctrl(self, cls: str, text: str, style: int, x: int, y: int, w: int, h: int, cid: int) -> wt.HWND:
        hinst = kernel32.GetModuleHandleW(None)
        hwnd = user32.CreateWindowExW(
            0,
            cls,
            text,
            style,
            x,
            y,
            w,
            h,
            self.hwnd,
            wt.HMENU(cid) if cid else None,
            hinst,
            None,
        )
        if self.hfont:
            user32.SendMessageW(hwnd, WM_SETFONT, WPARAM(int(self.hfont)), 1)
        return hwnd

    @staticmethod
    def _combo_add(hwnd: wt.HWND, text: str) -> None:
        buf = ctypes.create_unicode_buffer(text)
        user32.SendMessageW(hwnd, CB_ADDSTRING, 0, ctypes.addressof(buf))

    @staticmethod
    def _get_text(hwnd: wt.HWND) -> str:
        length = int(user32.GetWindowTextLengthW(hwnd))
        if length <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 2)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value.strip()

    def load_from_config(self, cfg: AppConfig) -> None:
        self.config = cfg
        mode_idx = 1 if cfg.timer.default_mode == "POMODORO" else 0
        user32.SendMessageW(self._cmb_mode, CB_SETCURSEL, mode_idx, 0)
        user32.SetWindowTextW(self._edit_focus, str(cfg.timer.pomodoro_focus_min))
        user32.SetWindowTextW(self._edit_break, str(cfg.timer.pomodoro_break_min))
        user32.SetWindowTextW(self._edit_afk, str(cfg.timer.afk_timeout_min))
        user32.SendMessageW(self._cmb_scale, CB_SETCURSEL, max(0, min(3, cfg.character.scale - 1)), 0)
        user32.SendMessageW(self._chk_walk, BM_SETCHECK, 1 if cfg.character.walk_enabled else 0, 0)
        user32.SendMessageW(self._cmb_fps, CB_SETCURSEL, 1 if cfg.render.fps == 60 else 0, 0)
        user32.SendMessageW(self._chk_sound, BM_SETCHECK, 1 if cfg.timer.sound_alert else 0, 0)
        vol_int = max(0, min(100, int(round(cfg.audio.volume * 100))))
        user32.SendMessageW(self._trk_volume, TBM_SETPOS, 1, vol_int)
        hk_word = hotkey_string_to_hk_word(cfg.shortcuts.toggle_ghost)
        user32.SendMessageW(self._hk_ghost, HKM_SETHOTKEY, hk_word, 0)

    def _handle_apply(self) -> None:
        focus_s = self._get_text(self._edit_focus)
        break_s = self._get_text(self._edit_break)
        afk_s = self._get_text(self._edit_afk)
        if not (focus_s.isdigit() and break_s.isdigit() and afk_s.isdigit()):
            show_info_message(MSG_SETTINGS_INVALID, warning=True)
            return

        focus_min = int(focus_s)
        break_min = int(break_s)
        afk_min = int(afk_s)
        if not (1 <= focus_min <= 180 and 1 <= break_min <= 60 and 1 <= afk_min <= 120):
            show_info_message(MSG_SETTINGS_INVALID, warning=True)
            return

        mode_idx = int(user32.SendMessageW(self._cmb_mode, CB_GETCURSEL, 0, 0))
        default_mode = "POMODORO" if mode_idx == 1 else "STOPWATCH"
        scale_idx = int(user32.SendMessageW(self._cmb_scale, CB_GETCURSEL, 0, 0))
        scale_val = max(1, min(4, scale_idx + 1))
        walk_enabled = bool(user32.SendMessageW(self._chk_walk, BM_GETCHECK, 0, 0))
        fps_idx = int(user32.SendMessageW(self._cmb_fps, CB_GETCURSEL, 0, 0))
        fps_val = 60 if fps_idx == 1 else 30
        sound_enabled = bool(user32.SendMessageW(self._chk_sound, BM_GETCHECK, 0, 0))
        vol_pos = int(user32.SendMessageW(self._trk_volume, TBM_GETPOS, 0, 0))
        volume_val = max(0.0, min(1.0, vol_pos / 100.0))

        hk_word = int(user32.SendMessageW(self._hk_ghost, HKM_GETHOTKEY, 0, 0))
        shortcut_str = hk_word_to_hotkey_string(hk_word) or self.config.shortcuts.toggle_ghost

        patch = SettingsPatch(
            scale=scale_val,
            walk_enabled=walk_enabled,
            default_mode=default_mode,
            pomodoro_focus_min=focus_min,
            pomodoro_break_min=break_min,
            afk_timeout_min=afk_min,
            sound_alert=sound_enabled,
            volume=volume_val,
            fps=fps_val,
            toggle_ghost=shortcut_str,
        )
        self.config = patch.apply_to(self.config)
        self.on_apply(patch)
        show_info_message(MSG_SETTINGS_SAVED)

    def _wnd_proc(self, hwnd: wt.HWND, msg: int, wparam: int, lparam: int) -> int:
        try:
            if msg == WM_COMMAND:
                cid = int(wparam) & 0xFFFF
                if cid == ID_BTN_APPLY:
                    self._handle_apply()
                return 0
            if msg == WM_DESTROY:
                return 0
        except Exception:
            write_crash_log()
            return 0
        return int(user32.DefWindowProcW(hwnd, msg, WPARAM(wparam), LPARAM(lparam)))
