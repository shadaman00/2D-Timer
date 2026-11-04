"""StudyPet 애플리케이션 진입점, 기동/종료 시퀀스 및 이벤트 조정자 (DEVELOPMENT_PLAN.md 3-3, 3-4, REVISION_PLAN_v0.7)."""
from __future__ import annotations

import ctypes
from ctypes import wintypes as wt
from dataclasses import replace
import logging
import os
from pathlib import Path
import sqlite3
import sys

from studypet.crashlog import set_crash_log_dir, write_crash_log
from studypet.domain.events import (
    AfkReturned,
    AfkStarted,
    Event,
    FinalizeRequested,
    Finished,
    Mode,
    Paused,
    PhaseChanged,
    RecoverAction,
    Resumed,
    Started,
    StorageError,
    SubjectSwitched,
    Ticked,
    TimerState,
)
from studypet.domain.pet_fsm import PetFSM
from studypet.domain.stats import format_hms
from studypet.domain.timer_engine import TimerEngine, TimerSettings
from studypet.infra.config import AppConfig, PointPos, SettingsPatch
from studypet.infra.csv_export import prompt_and_export_csv
from studypet.infra.db import (
    Database,
    SegmentRow,
    SessionRepository,
    StatsRepository,
    SubjectRepository,
)
from studypet.infra.logging_setup import setup_logging
from studypet.infra.paths import PortablePaths, ensure_data_writable
from studypet.infra.real_clock import RealClock
from studypet.strings import (
    MSG_CSV_EXPORT_DONE,
    MSG_CSV_EXPORT_ERROR,
    MSG_DB_LOCKED,
    MSG_HOTKEY_CONFLICT,
    MSG_SHORTCUT_CREATED,
    MSG_SHORTCUT_FAILED,
    MSG_STORAGE_ERROR,
    format_afk_message,
    format_memo_prompt,
    format_quit_confirm,
    format_recovery_message,
    format_switch_toast,
)
from studypet.ui.dashboard import DashboardWindow
from studypet.ui.modals import ModalManager, show_info_message
from studypet.ui.pet_window import PET_CLASS_NAME, PetWindow
from studypet.ui.popup import (
    CMD_MORE_BUBBLE_TOGGLE,
    CMD_MORE_GHOST_MODE,
    CMD_MORE_QUIT,
    CMD_MORE_SUBJECTS,
    CMD_MORE_SUMMON_CENTER,
)
from studypet.win32.api import (
    ERROR_ALREADY_EXISTS,
    MSG,
    WM_APP_SUMMON,
    WM_TIMER,
    get_cold_start_ms,
    kernel32,
    user32,
)
from studypet.win32.audio import SoundPlayer
from studypet.win32.hotkey import HotkeyManager
from studypet.win32.idle import get_idle_ms
from studypet.win32.monitors import enable_per_monitor_dpi
from studypet.win32.tray import TrayIcon, create_desktop_shortcut


logger = logging.getLogger(__name__)

MUTEX_NAME = "Local\\StudyPet_SingleInstance_v1"
TID_AUTO_EXIT = 999


class AppController:
    """엔진, DB, 펫 창, 모달, 대시보드, 트레이, 단축키, 사운드를 연결하는 메인 컨트롤러."""

    def __init__(self, paths: PortablePaths, config: AppConfig, db: Database) -> None:
        self.paths = paths
        self.config = config
        self.db = db

        self.subject_repo: SubjectRepository = db.subjects
        self.session_repo: SessionRepository = db.sessions
        self.stats_repo: StatsRepository = db.stats

        self.clock = RealClock()
        self.engine = TimerEngine(
            repo=self.session_repo,
            clock=self.clock,
            settings=TimerSettings(
                pomodoro_focus_min=config.timer.pomodoro_focus_min,
                pomodoro_break_min=config.timer.pomodoro_break_min,
                afk_timeout_min=config.timer.afk_timeout_min,
            ),
            emit=self._on_engine_event,
        )

        self.fsm = PetFSM()
        init_pos: tuple[int, int] | None = None
        if config.character.last_position is not None:
            init_pos = (config.character.last_position.x, config.character.last_position.y)

        self.pet = PetWindow(
            assets_dir=paths.assets_dir,
            fsm=self.fsm,
            config_scale=config.character.scale,
            fps_limit=config.render.fps,
            walk_enabled=config.character.walk_enabled,
            initial_foot_pos=init_pos,
            perf_log_path=paths.logs_dir / "perf.log",
            hint_shown=config.hud.hint_shown,
        )
        self.pet.bubble_collapsed = config.hud.bubble_collapsed

        manifest_file = paths.assets_dir / "studypet.manifest"
        manifest_arg = manifest_file if manifest_file.exists() else None
        self.modals = ModalManager(manifest_path=manifest_arg)
        self.dashboard = DashboardWindow(
            manifest_path=manifest_arg,
            subject_repo=self.subject_repo,
            stats_repo=self.stats_repo,
            get_config=lambda: self.config,
            on_apply_settings=self._apply_new_config,
            on_subjects_changed=self._on_subjects_changed,
            get_running_subject_id=self._get_running_subject_id,
            get_today=lambda: self.clock.now_local().date(),
            get_live_credit=self.engine.live_credit,
            on_export_csv=self._handle_csv_export,
        )

        self.tray: TrayIcon | None = None
        self.hotkey: HotkeyManager | None = None
        self.sound: SoundPlayer | None = None
        self._storage_error_notified: bool = False
        self._pending_recovery_rows: list[SegmentRow] = []
        self._quit_after_finalize: bool = False
        self._shut_down: bool = False

        self._wire_callbacks()

    def _wire_callbacks(self) -> None:
        self.modals.on_modal_state_changed = self._on_modal_state_changed

        self.pet.on_primary = self._handle_primary_action
        self.pet.on_quick_start_or_toggle = self._handle_quick_start_or_toggle
        self.pet.on_stop_requested = self._handle_stop_requested
        self.pet.on_select_subject = self._handle_select_subject
        self.pet.on_select_mode = self._handle_select_mode
        self.pet.on_more_command = self._handle_more_command
        self.pet.on_card_opened = self._handle_card_opened
        self.pet.on_locked_click = self.modals.bring_active_to_front
        self.pet.on_open_dashboard = self._handle_open_dashboard
        self.pet.on_position_changed = self._handle_position_changed
        self.pet.on_engine_tick = self._handle_engine_tick
        self.pet.on_idle_tick = self._handle_idle_tick
        self.pet.on_tray_menu = self._handle_tray_menu
        self.pet.on_taskbar_created = self._handle_taskbar_created
        self.pet.on_suspend = self.engine.on_suspend
        self.pet.on_resume_power = lambda: None
        self.pet.on_session_lock = self.engine.on_session_lock
        self.pet.on_session_unlock = self.engine.on_session_unlock
        self.pet.on_post_start = self._handle_post_start
        self.pet.on_end_session = self.on_end_session
        self.pet.on_save_config_timer = self._flush_config_save

    def _on_modal_state_changed(self, locked: bool) -> None:
        self.pet.modal_locked = locked
        if locked:
            self.pet.card_open = False
            self.pet.card_hover = None
            self.pet.card_pressed = None
            self.pet.render_and_present()

    def _get_running_subject_id(self) -> int | None:
        if self.engine.state is not TimerState.STOPPED:
            return self.engine.subject_id
        return None

    def _resolve_active_subject(self) -> tuple[int, str]:
        default_sid = self.subject_repo.ensure_default_subject()
        active = self.subject_repo.list(include_archived=False)
        target_id = self.config.timer.last_subject_id
        if target_id is not None:
            for s in active:
                if s.id == target_id:
                    return (s.id, s.name)
        first = active[0] if active else self.subject_repo.get(default_sid)
        assert first is not None
        self.config = replace(self.config, timer=replace(self.config.timer, last_subject_id=first.id))
        return (first.id, first.name)

    def _sync_pet_hud(self) -> None:
        active_list = [(s.id, s.name) for s in self.subject_repo.list(include_archived=False)]
        if self.engine.state is not TimerState.STOPPED and self.engine.subject_id is not None:
            sid = self.engine.subject_id
            subj = self.subject_repo.get(sid)
            sname = subj.name if subj is not None else "자유 학습"
        else:
            sid, sname = self._resolve_active_subject()

        def_mode = Mode.POMODORO if self.config.timer.default_mode == "POMODORO" else Mode.STOPWATCH
        self.pet.update_hud_state(
            engine_state=self.engine.state,
            phase=self.engine.phase,
            subject_id=sid,
            subject_name=sname,
            display_seconds=self.engine.display_seconds(),
            subjects_list=active_list,
            mode=self.engine.mode,
            remain_seconds=self.engine.phase_remaining_seconds(),
            default_mode=def_mode,
            ghost_shortcut=self.config.shortcuts.toggle_ghost,
        )

    def _save_config_soon(self) -> None:
        """드래그·과목·모드·힌트 상태 변경 시 1초 디바운스로 원자적 저장을 예약한다 (v0.7 M2)."""
        if self.pet.hwnd:
            self.pet.schedule_save_config(1000)
        else:
            self._flush_config_save()

    def _flush_config_save(self) -> None:
        if self._shut_down:
            return
        try:
            self.config.save(self.paths.config_path)
        except Exception:
            logger.exception("Failed to save config")

    def start_ui(self) -> wt.HWND:
        self._sync_pet_hud()
        hwnd = self.pet.create_and_show()
        cold_ms = get_cold_start_ms()
        self.pet.log_perf_line(f"cold_start_ms={cold_ms:.2f}")
        return hwnd

    def _handle_post_start(self) -> None:
        """3-3 #9: 첫 프레임 표시 직후 트레이·핫키·효과음·미완료 세션 복구를 초기화한다."""
        ico_path = self.paths.assets_dir / "icons" / "studypet.ico"
        self.tray = TrayIcon(self.pet.hwnd, ico_path)
        self.tray.add()

        self.hotkey = HotkeyManager(self.pet.hwnd)
        if not self.hotkey.register(self.config.shortcuts.toggle_ghost):
            show_info_message(
                MSG_HOTKEY_CONFLICT.format(hotkey=self.config.shortcuts.toggle_ghost),
                warning=True,
            )

        sfx_dir = self.paths.assets_dir / "sfx"
        wav_paths = {
            "start": sfx_dir / "start.wav",
            "phase": sfx_dir / "phase.wav",
            "celebrate": sfx_dir / "celebrate.wav",
            "afk": sfx_dir / "afk.wav",
        }
        self.sound = SoundPlayer(
            wav_paths=wav_paths,
            volume=self.config.audio.volume,
            enabled=self.config.timer.sound_alert,
        )

        # 미완료 기록(크래시 복구) 검사 (4-7 알고리즘 6)
        self._pending_recovery_rows = self.session_repo.get_open_segments()
        self._process_next_recovery_row()

    def _process_next_recovery_row(self) -> None:
        if not self._pending_recovery_rows:
            return
        row = self._pending_recovery_rows.pop(0)
        is_last = len(self._pending_recovery_rows) == 0
        prompt = format_recovery_message(row.subject_name, row.duration_seconds, row.local_date, row.end_time)

        def _on_choice(choice: str) -> None:
            if choice == "resume" and is_last:
                self.engine.recover(row, RecoverAction.CONTINUE)
                self._sync_pet_hud()
            elif choice == "save":
                prompt_memo = format_memo_prompt(row.subject_name, format_hms(row.duration_seconds))

                def _on_memo(memo_str: str) -> None:
                    self.engine.recover(row, RecoverAction.SAVE, memo=memo_str)
                    self._process_next_recovery_row()

                self.modals.show_memo_modal(prompt_memo, self.pet.physics.screen_foot, _on_memo)
                return
            elif choice == "discard":
                self.engine.recover(row, RecoverAction.DISCARD)
            elif choice == "later":
                # H2: 나중에 결정 — 행을 그대로 두고 다음 실행 때 다시 묻는다.
                pass
            self._process_next_recovery_row()

        self.modals.show_recovery_modal(
            prompt=prompt,
            subject_name=row.subject_name,
            duration_s=row.duration_seconds,
            allow_resume=is_last,
            ref_pos=self.pet.physics.screen_foot,
            on_choice=_on_choice,
        )

    def _handle_engine_tick(self) -> None:
        self.engine.tick()

    def _handle_idle_tick(self) -> int:
        idle_ms = get_idle_ms()
        self.engine.on_idle_poll(idle_ms)
        return idle_ms

    def _handle_primary_action(self) -> None:
        if self.engine.state is TimerState.PAUSED_AFK:
            self.modals.bring_active_to_front()
        else:
            self._handle_quick_start_or_toggle()

    def _handle_quick_start_or_toggle(self) -> None:
        if self.engine.state is TimerState.STOPPED:
            sid, _ = self._resolve_active_subject()
            mode = Mode.POMODORO if self.config.timer.default_mode == "POMODORO" else Mode.STOPWATCH
            self.engine.start(sid, mode)
        elif self.engine.state is TimerState.RUNNING:
            self.engine.pause()
        elif self.engine.state is TimerState.PAUSED:
            self.engine.resume()

    def _handle_stop_requested(self) -> None:
        if self.engine.state in (TimerState.RUNNING, TimerState.PAUSED, TimerState.PAUSED_AFK):
            self.engine.stop()

    def _handle_select_subject(self, new_subject_id: int) -> None:
        self.config = replace(self.config, timer=replace(self.config.timer, last_subject_id=new_subject_id))
        self._save_config_soon()
        if self.engine.state in (TimerState.RUNNING, TimerState.PAUSED):
            self.engine.switch_subject(new_subject_id)
        else:
            self._sync_pet_hud()

    def _handle_select_mode(self, mode_str: str) -> None:
        new_mode = "POMODORO" if mode_str == "POMODORO" else "STOPWATCH"
        self.config = replace(self.config, timer=replace(self.config.timer, default_mode=new_mode))
        self._save_config_soon()
        self._sync_pet_hud()

    def _handle_more_command(self, cmd: int) -> None:
        if cmd == CMD_MORE_SUBJECTS:
            self._handle_open_dashboard(0)
        elif cmd == CMD_MORE_BUBBLE_TOGGLE:
            self.config = replace(
                self.config,
                hud=replace(self.config.hud, bubble_collapsed=self.pet.bubble_collapsed),
            )
            self._save_config_soon()
        elif cmd == CMD_MORE_GHOST_MODE:
            self.pet.set_ghost_mode(True)
        elif cmd == CMD_MORE_SUMMON_CENTER:
            self.pet.summon_to_primary_center()
        elif cmd == CMD_MORE_QUIT:
            self.request_quit()

    def _handle_card_opened(self) -> None:
        if not self.config.hud.hint_shown:
            self.config = replace(self.config, hud=replace(self.config.hud, hint_shown=True))
            self._save_config_soon()

    def _handle_open_dashboard(self, tab_idx: int) -> None:
        self.dashboard.open_tab(tab_idx, ref_pos=self.pet.physics.screen_foot)

    def _handle_position_changed(self, foot_pos: tuple[int, int]) -> None:
        self.config = replace(
            self.config,
            character=replace(
                self.config.character,
                last_position=PointPos(x=foot_pos[0], y=foot_pos[1]),
            ),
        )
        self._save_config_soon()

    def _on_subjects_changed(self) -> None:
        self._sync_pet_hud()
        if self.dashboard.tab_stats is not None:
            self.dashboard.tab_stats.refresh_stats()

    def _apply_new_config(self, patch_or_cfg: SettingsPatch | AppConfig) -> None:
        prev_shortcut = self.config.shortcuts.toggle_ghost
        new_cfg = patch_or_cfg.apply_to(self.config) if isinstance(patch_or_cfg, SettingsPatch) else patch_or_cfg
        self.config = new_cfg
        self.config.save(self.paths.config_path)

        self.engine.update_settings(
            TimerSettings(
                pomodoro_focus_min=new_cfg.timer.pomodoro_focus_min,
                pomodoro_break_min=new_cfg.timer.pomodoro_break_min,
                afk_timeout_min=new_cfg.timer.afk_timeout_min,
            )
        )
        self.pet.apply_settings(
            config_scale=new_cfg.character.scale,
            walk_enabled=new_cfg.character.walk_enabled,
            fps_limit=new_cfg.render.fps,
        )
        if self.sound is not None:
            self.sound.set_enabled(new_cfg.timer.sound_alert)
            self.sound.set_volume(new_cfg.audio.volume)
        if self.hotkey is not None and new_cfg.shortcuts.toggle_ghost != prev_shortcut:
            if not self.hotkey.register(new_cfg.shortcuts.toggle_ghost):
                show_info_message(
                    MSG_HOTKEY_CONFLICT.format(hotkey=new_cfg.shortcuts.toggle_ghost),
                    warning=True,
                )
        self._sync_pet_hud()

    def _handle_csv_export(self) -> None:
        owner = self.dashboard.hwnd if self.dashboard.hwnd else self.pet.hwnd
        try:
            saved = prompt_and_export_csv(
                hwnd_owner=owner,
                db=self.db,
                exports_dir=self.paths.exports_dir,
            )
            if saved is not None:
                out_path, _count = saved
                show_info_message(MSG_CSV_EXPORT_DONE.format(path=out_path))
        except Exception as exc:
            show_info_message(MSG_CSV_EXPORT_ERROR.format(error=exc), warning=True)

    def _handle_tray_menu(self) -> None:
        if self.tray is None:
            return
        self.tray.show_popup_menu(
            engine_state=self.engine.state,
            ghost_active=self.pet.ghost_mode,
            on_primary=self._handle_quick_start_or_toggle,
            on_summon=self.pet.summon_to_primary_center,
            on_dashboard=lambda: self._handle_open_dashboard(0),
            on_toggle_ghost=self.pet.toggle_ghost_mode,
            on_shortcut=self._handle_create_shortcut,
            on_quit=self.request_quit,
        )

    def _handle_taskbar_created(self) -> None:
        if self.tray is not None:
            self.tray.re_add()

    def _handle_create_shortcut(self) -> None:
        exe_path = Path(sys.executable).resolve()
        ico_path = self.paths.assets_dir / "icons" / "studypet.ico"
        ok = create_desktop_shortcut(exe_path, self.paths.root_dir, ico_path)
        show_info_message(MSG_SHORTCUT_CREATED if ok else MSG_SHORTCUT_FAILED, warning=not ok)

    def _on_engine_event(self, ev: Event) -> None:
        if isinstance(ev, Started):
            self._storage_error_notified = False
            self._sync_pet_hud()
            self.pet.notify_study_started()
            if self.sound is not None:
                self.sound.play("start")

        elif isinstance(ev, Ticked):
            self._sync_pet_hud()
            self.dashboard.on_second_tick()

        elif isinstance(ev, PhaseChanged):
            self._sync_pet_hud()
            if self.sound is not None:
                self.sound.play("phase")

        elif isinstance(ev, Paused):
            self._sync_pet_hud()
            self.pet.notify_study_stopped()

        elif isinstance(ev, Resumed):
            self._sync_pet_hud()
            self.pet.notify_study_started()

        elif isinstance(ev, AfkStarted):
            self._sync_pet_hud()
            self.pet.notify_study_stopped()

        elif isinstance(ev, AfkReturned):
            if self.sound is not None:
                self.sound.play("afk")
            msg = format_afk_message(ev.away_wall_s, ev.away_awake_s, ev.can_include)

            def _on_afk_decision(include: bool) -> None:
                self.engine.resolve_afk(include)
                self._sync_pet_hud()

            self.modals.show_afk_modal(
                prompt=msg,
                can_include=ev.can_include,
                ref_pos=self.pet.physics.screen_foot,
                on_decision=_on_afk_decision,
            )

        elif isinstance(ev, FinalizeRequested):
            self._sync_pet_hud()
            sid = self.engine.subject_id or 1
            subj = self.subject_repo.get(sid)
            sname = subj.name if subj is not None else "자유 학습"
            prompt = format_memo_prompt(sname, format_hms(ev.total_s))

            def _on_memo_done(memo_text: str) -> None:
                self.engine.finalize(memo_text)
                if self._quit_after_finalize:
                    self._quit_after_finalize = False
                    self.shutdown()

            self.modals.show_memo_modal(
                prompt=prompt,
                ref_pos=self.pet.physics.screen_foot,
                on_done=_on_memo_done,
            )

        elif isinstance(ev, Finished):
            self._sync_pet_hud()
            self.pet.notify_session_finished()
            if self.sound is not None:
                self.sound.play("celebrate")
            if self.dashboard.tab_stats is not None:
                self.dashboard.tab_stats.refresh_stats()

        elif isinstance(ev, SubjectSwitched):
            prev_subj = self.subject_repo.get(ev.prev_subject_id)
            new_subj = self.subject_repo.get(ev.new_subject_id)
            prev_name = prev_subj.name if prev_subj is not None else "이전 과목"
            new_name = new_subj.name if new_subj is not None else "새 과목"
            toast_text = format_switch_toast(prev_name, format_hms(ev.saved_s), new_name, ev.saved_s)
            self._sync_pet_hud()
            self.pet.show_toast(toast_text, 2.0)
            if self.dashboard.tab_stats is not None:
                self.dashboard.tab_stats.refresh_stats()

        elif isinstance(ev, StorageError):
            if not self._storage_error_notified:
                self._storage_error_notified = True
                show_info_message(MSG_STORAGE_ERROR, warning=True)

    def request_quit(self) -> None:
        """3-4 종료 시퀀스 (v0.7 H1·H4): 진행 중 세션이 있으면 확인 모달을 띄우고, 없으면 즉시 정리 후 종료한다."""
        if self.engine.state in (TimerState.RUNNING, TimerState.PAUSED, TimerState.PAUSED_AFK):
            sid = self.engine.subject_id or 1
            subj = self.subject_repo.get(sid)
            sname = subj.name if subj is not None else "자유 학습"
            prompt = format_quit_confirm(sname, format_hms(self.engine.display_seconds()))

            def _on_quit_choice(choice: str) -> None:
                if choice == "save_quit":
                    self._quit_after_finalize = True
                    self.engine.stop()
                elif choice == "keep_quit":
                    self.engine.checkpoint_now()
                    self.shutdown()

            self.modals.show_quit_confirm_modal(
                prompt=prompt,
                ref_pos=self.pet.physics.screen_foot,
                on_choice=_on_quit_choice,
            )
            return

        self.shutdown()

    def on_end_session(self) -> None:
        """Windows 로그오프·종료 시 메시지 루프를 기다리지 않고 즉시 체크포인트 후 정리한다 (v0.7 H6)."""
        self.shutdown(post_quit=False)

    def shutdown(self, post_quit: bool = True) -> None:
        """3-4 종료 정리 (v0.7 4-3): ①체크포인트 ②설정 저장 ③모달 기본값 플러시 ④대시보드 ⑤트레이/핫키/사운드 ⑥펫 ⑦DB."""
        if self._shut_down:
            return
        self._shut_down = True

        # ① 엔진 강제 체크포인트
        try:
            self.engine.checkpoint_now()
        except Exception:
            logger.exception("Failed to checkpoint engine during shutdown")

        # ② 설정 원자적 저장
        try:
            fx, fy = self.pet.physics.screen_foot
            self.config = replace(
                self.config,
                character=replace(
                    self.config.character,
                    last_position=PointPos(x=fx, y=fy),
                ),
                hud=replace(
                    self.config.hud,
                    bubble_collapsed=self.pet.bubble_collapsed,
                    hint_shown=self.pet.hint_shown,
                ),
            )
            self.config.save(self.paths.config_path)
        except Exception:
            logger.exception("Failed to save config during shutdown")

        # ③ 모달 기본값 호출 후 닫기
        self.modals.flush_defaults_and_close()
        if self.engine.state is TimerState.FINALIZING:
            try:
                self.engine.finalize("")
            except Exception:
                logger.exception("Failed to finalize engine during shutdown")

        # ④ 대시보드 닫기
        self.dashboard.close_and_destroy()

        # ⑤ 트레이·단축키·사운드 해제
        if self.tray is not None:
            self.tray.remove()
            self.tray = None
        if self.hotkey is not None:
            self.hotkey.unregister()
            self.hotkey = None
        if self.sound is not None:
            self.sound.stop()
            self.sound = None

        # ⑥ 펫 창 파괴
        self.pet.destroy()

        # ⑦ WAL 체크포인트 후 DB 닫기
        self.db.close()

        # ⑧ 메시지 루프 종료
        if post_quit:
            user32.PostQuitMessage(0)


def run_app(argv: list[str] | None = None) -> int:
    """StudyPet 메인 실행 함수 (DEVELOPMENT_PLAN.md 3-3)."""
    args = argv if argv is not None else sys.argv[1:]

    # Phase 0/8 부트스트랩 가드 자동 검증용 훅
    guard_out = os.environ.get("STUDYPET_GUARD_TEST")
    if guard_out:
        try:
            Path(guard_out).write_text("STUDYPET_STARTED_OK\n", encoding="utf-8")
        except OSError:
            pass
        return 0

    # 1. Per-Monitor DPI v2 활성화
    enable_per_monitor_dpi()

    # 2. 단일 인스턴스 뮤텍스 검사
    hmutex = kernel32.CreateMutexW(None, True, MUTEX_NAME)
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        existing_hwnd = user32.FindWindowW(PET_CLASS_NAME, None)
        if existing_hwnd:
            user32.PostMessageW(existing_hwnd, WM_APP_SUMMON, 0, 0)
        if hmutex:
            kernel32.CloseHandle(hmutex)
        return 0

    try:
        # 3. 포터블 경로 해석 및 데이터 폴더 쓰기 권한 보장
        paths = PortablePaths.resolve(Path(sys.executable))
        if not ensure_data_writable(paths):
            return 1

        set_crash_log_dir(paths.logs_dir)

        # 4. 로깅 초기화
        setup_logging(paths.logs_dir, console=("--console" in args))

        # 5. 설정 로드
        config = AppConfig.load(paths.config_path)

        # 6. SQLite DB 초기화
        try:
            db = Database.open(paths.db_path)
        except sqlite3.OperationalError:
            show_info_message(MSG_DB_LOCKED, warning=True)
            return 1

        # 7~9. 컨트롤러 및 펫 창 생성
        controller = AppController(paths=paths, config=config, db=db)
        pet_hwnd = controller.start_ui()

        # 자동 종료 테스트 훅 (STUDYPET_AUTO_EXIT_MS)
        auto_exit_str = os.environ.get("STUDYPET_AUTO_EXIT_MS", "")
        if auto_exit_str.isdigit() and int(auto_exit_str) > 0:
            user32.SetTimer(pet_hwnd, TID_AUTO_EXIT, int(auto_exit_str), None)

        # 10. 단일 메시지 루프 (3-2, v0.7 M3)
        msg = MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_TIMER and int(msg.wParam) == TID_AUTO_EXIT:
                user32.KillTimer(pet_hwnd, TID_AUTO_EXIT)
                controller.shutdown()
                continue

            handled_dlg = False
            for dlg_hwnd in (controller.modals.active_hwnd, controller.dashboard.hwnd):
                if dlg_hwnd and user32.IsDialogMessageW(dlg_hwnd, ctypes.byref(msg)):
                    handled_dlg = True
                    break
            if handled_dlg:
                continue

            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        return 0

    except Exception:
        write_crash_log()
        return 1
    finally:
        if hmutex:
            kernel32.CloseHandle(hmutex)


run = run_app
