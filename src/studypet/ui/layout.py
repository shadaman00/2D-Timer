"""펫 캔버스(192x144 sp) 좌표 상수, 말풍선 클램핑, 액션 카드 레이아웃 및 히트 판정 (REVISION_PLAN_v0.7 3-4, 3-5, 4-5)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from studypet.domain.events import Mode as TimerMode, Phase as PomodoroPhase, TimerState
from studypet import strings


CANVAS_W_SP = 192
CANVAS_H_SP = 144

CHAR_X_SP = 64
CHAR_Y_SP = 80
CHAR_W_SP = 64
CHAR_H_SP = 64

ANCHOR_X_SP = 96
ANCHOR_Y_SP = 144

BUBBLE_Y_SP = 52
BUBBLE_H_SP = 24
BUBBLE_MAX_W_SP = 176
BUBBLE_MIN_W_SP = 48


@dataclass(frozen=True)
class BoxSp:
    x: int
    y: int
    w: int
    h: int

    def contains(self, x_sp: int, y_sp: int) -> bool:
        return self.x <= x_sp < (self.x + self.w) and self.y <= y_sp < (self.y + self.h)

    def intersects(self, other: BoxSp) -> bool:
        return not (
            (self.x + self.w) <= other.x
            or (other.x + other.w) <= self.x
            or (self.y + self.h) <= other.y
            or (other.y + other.h) <= self.y
        )


CHARACTER_BOX_SP = BoxSp(CHAR_X_SP, CHAR_Y_SP, CHAR_W_SP, CHAR_H_SP)

# 액션 카드 상수 (v0.7 3-4)
CARD_BOX_SP = BoxSp(8, 0, 176, 78)
CARD_HEADER_LEFT_SP = (14, 4)
CARD_HEADER_RIGHT_X_SP = 178
CARD_HEADER_Y_SP = 4

CARD_BTN_PRIMARY_BOX_SP = BoxSp(14, 20, 164, 18)
CARD_PRIMARY_ICON_SP = (18, 21)
CARD_PRIMARY_LABEL_SP = (38, 23)

CARD_BTN_SEC_A_BOX_SP = BoxSp(14, 41, 80, 16)
CARD_BTN_SEC_B_BOX_SP = BoxSp(98, 41, 80, 16)

CARD_BTN_STATS_BOX_SP = BoxSp(14, 60, 52, 14)
CARD_BTN_SETTINGS_BOX_SP = BoxSp(70, 60, 52, 14)
CARD_BTN_MORE_BOX_SP = BoxSp(126, 60, 52, 14)


@dataclass(frozen=True)
class CardButton:
    key: str            # "primary" | "end" | "subject" | "mode" | "stats" | "settings" | "more"
    box: BoxSp
    label: str
    icon: str | None    # "start" | "pause" | None
    enabled: bool
    style: Literal["primary", "secondary", "footer"]


def _format_hms(seconds: int) -> str:
    sec = max(0, int(seconds))
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f"{h}:{m:02d}:{s:02d}"


def _format_ms(seconds: int) -> str:
    sec = max(0, int(seconds))
    m = sec // 60
    s = sec % 60
    return f"{m}:{s:02d}"


def card_header(
    state: TimerState,
    phase: PomodoroPhase,
    mode: TimerMode,
    subject: str,
    display_s: int,
    remain_s: int | None,
) -> tuple[str, str]:
    """액션 카드 상단 헤더의 (왼쪽 텍스트, 오른쪽 텍스트)를 반환한다 (v0.7 3-5)."""
    if state == TimerState.STOPPED:
        return (f"대기 중 · {subject}", "")

    if state == TimerState.RUNNING:
        if mode == TimerMode.POMODORO and phase == PomodoroPhase.BREAK:
            rem = _format_ms(remain_s if remain_s is not None else 0)
            return ("휴식", f"남은 {rem}")
        hms = _format_hms(display_s)
        if mode == TimerMode.POMODORO and remain_s is not None:
            rem = _format_ms(remain_s)
            return (f"● 집중 {subject}", f"{hms} 남은 {rem}")
        return (f"● 집중 {subject}", hms)

    if state == TimerState.PAUSED:
        return (f"일시정지 {subject}", _format_hms(display_s))

    if state == TimerState.PAUSED_AFK:
        return ("자리 비움 확인 중", "")

    return (f"완료 중 · {subject}", _format_hms(display_s))


def card_buttons(
    state: TimerState,
    phase: PomodoroPhase,
    mode_label: str = "뽀모도로",
) -> list[CardButton]:
    """엔진 상태에 따른 액션 카드 버튼 목록을 반환한다 (v0.7 3-5)."""
    if state == TimerState.FINALIZING:
        return []

    footer = [
        CardButton("stats", CARD_BTN_STATS_BOX_SP, strings.CARD_BTN_STATS, None, True, "footer"),
        CardButton("settings", CARD_BTN_SETTINGS_BOX_SP, strings.CARD_BTN_SETTINGS, None, True, "footer"),
        CardButton("more", CARD_BTN_MORE_BOX_SP, strings.CARD_BTN_MORE, None, True, "footer"),
    ]

    if state == TimerState.STOPPED:
        primary_label = f"학습 시작 ({mode_label})"
        return [
            CardButton("primary", CARD_BTN_PRIMARY_BOX_SP, primary_label, "start", True, "primary"),
            CardButton("subject", CARD_BTN_SEC_A_BOX_SP, strings.CARD_BTN_SUBJECT_SELECT, None, True, "secondary"),
            CardButton("mode", CARD_BTN_SEC_B_BOX_SP, strings.CARD_BTN_MODE_SELECT, None, True, "secondary"),
            *footer,
        ]

    if state == TimerState.RUNNING:
        return [
            CardButton("primary", CARD_BTN_PRIMARY_BOX_SP, strings.CARD_BTN_PAUSE, "pause", True, "primary"),
            CardButton("end", CARD_BTN_SEC_A_BOX_SP, strings.CARD_BTN_END, None, True, "secondary"),
            CardButton("subject", CARD_BTN_SEC_B_BOX_SP, strings.CARD_BTN_SUBJECT_CHANGE, None, True, "secondary"),
            *footer,
        ]

    if state == TimerState.PAUSED:
        return [
            CardButton("primary", CARD_BTN_PRIMARY_BOX_SP, strings.CARD_BTN_RESUME, "start", True, "primary"),
            CardButton("end", CARD_BTN_SEC_A_BOX_SP, strings.CARD_BTN_END, None, True, "secondary"),
            CardButton("subject", CARD_BTN_SEC_B_BOX_SP, strings.CARD_BTN_SUBJECT_CHANGE, None, True, "secondary"),
            *footer,
        ]

    if state == TimerState.PAUSED_AFK:
        return [
            CardButton("primary", CARD_BTN_PRIMARY_BOX_SP, strings.CARD_BTN_OPEN_AFK, None, True, "primary"),
            CardButton("end", CARD_BTN_SEC_A_BOX_SP, strings.CARD_BTN_END, None, True, "secondary"),
            CardButton("subject", CARD_BTN_SEC_B_BOX_SP, strings.CARD_BTN_SUBJECT_CHANGE, None, False, "secondary"),
            *footer,
        ]

    return []


def hit_test_card(buttons: list[CardButton], x_sp: int, y_sp: int) -> str | None:
    """활성화된 카드 버튼에 적중하면 key를 반환하고, 비활성 버튼이나 빈 영역이면 None을 반환한다."""
    for btn in buttons:
        if btn.enabled and btn.box.contains(x_sp, y_sp):
            return btn.key
    return None


def px_to_sp(x_px: int, y_px: int, phys_scale: int) -> tuple[int, int]:
    s = max(1, int(phys_scale))
    return (int(x_px) // s, int(y_px) // s)


def sp_to_px(x_sp: int, y_sp: int, phys_scale: int) -> tuple[int, int]:
    s = max(1, int(phys_scale))
    return (int(x_sp) * s, int(y_sp) * s)


def window_top_left_from_foot(foot_x_px: int, foot_y_px: int, phys_scale: int) -> tuple[int, int]:
    s = max(1, int(phys_scale))
    return (int(foot_x_px) - ANCHOR_X_SP * s, int(foot_y_px) - ANCHOR_Y_SP * s)


def compute_bubble_box_sp(
    text_w_px: int,
    phys_scale: int,
    win_left_px: int,
    work_left_px: int,
    work_right_px: int,
) -> BoxSp:
    """말풍선 폭을 텍스트에 맞춰 8sp 단위로 산출하고, 화면 좌우 밖으로 나가면 캔버스 범위 내에서 안쪽으로 밀어 넣는다."""
    s = max(1, int(phys_scale))
    raw_w_sp = (max(1, int(text_w_px)) + s - 1) // s + 16
    aligned_w_sp = ((raw_w_sp + 7) // 8) * 8
    w_sp = max(BUBBLE_MIN_W_SP, min(BUBBLE_MAX_W_SP, aligned_w_sp))

    # 기본 가로 중앙 정렬 (중심 x = 96)
    x_sp = ANCHOR_X_SP - (w_sp // 2)

    # 화면 작업 영역 좌우 경계 보정
    bubble_left_px = win_left_px + x_sp * s
    bubble_right_px = bubble_left_px + w_sp * s
    if bubble_left_px < work_left_px:
        shift_sp = (work_left_px - bubble_left_px + s - 1) // s
        x_sp += shift_sp
    elif bubble_right_px > work_right_px:
        shift_sp = (bubble_right_px - work_right_px + s - 1) // s
        x_sp -= shift_sp

    # 캔버스 범위 [8, 192 - 8 - w_sp] 안으로 클램프
    x_sp = max(8, min(CANVAS_W_SP - 8 - w_sp, x_sp))
    return BoxSp(x_sp, BUBBLE_Y_SP, w_sp, BUBBLE_H_SP)
