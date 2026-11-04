"""StudyPet 한국어 UI 문자열 상수 모듈 (DEVELOPMENT_PLAN.md 8장, REVISION_PLAN_v0.7)."""
from __future__ import annotations

# 앱 기본 정보
APP_TITLE = "StudyPet"
TRAY_TOOLTIP = "StudyPet"

# 트레이 메뉴 항목
TRAY_START_STUDY = "학습 시작"
TRAY_PAUSE_STUDY = "일시정지"
TRAY_RESUME_STUDY = "이어하기"
TRAY_SUMMON = "캐릭터 소환"
TRAY_OPEN_DASHBOARD = "대시보드 열기"
TRAY_GHOST_MODE = "유령 모드"
TRAY_CREATE_SHORTCUT = "바탕화면 바로가기 만들기"
TRAY_QUIT = "완전 종료"

# 대시보드 탭 제목
TAB_SUBJECTS = "📋 과목 관리"
TAB_SETTINGS = "⏱️ 설정"
TAB_STATS = "📊 공부 기록장"

# 액션 카드(Action Card) 버튼 및 헤더 라벨 (v0.7 3-4, 3-5)
CARD_BTN_START_POMODORO = "학습 시작 (뽀모도로)"
CARD_BTN_START_STOPWATCH = "학습 시작 (스톱워치)"
CARD_BTN_PAUSE = "일시정지"
CARD_BTN_RESUME = "이어하기"
CARD_BTN_OPEN_AFK = "확인 창 열기"
CARD_BTN_END = "■ 끝내기"
CARD_BTN_SUBJECT_SELECT = "과목 ▾"
CARD_BTN_SUBJECT_CHANGE = "과목 바꾸기 ▾"
CARD_BTN_MODE_SELECT = "모드 ▾"
CARD_BTN_STATS = "기록"
CARD_BTN_SETTINGS = "설정"
CARD_BTN_MORE = "더보기 …"

# 팝업 메뉴 항목 (v0.7 3-5, 8장 D1)
MORE_MANAGE_SUBJECTS = "과목 관리"
MORE_MANAGE_SUBJECTS_ELLIPSIS = "과목 관리…"
MORE_BUBBLE_COLLAPSED = "말풍선 간단히 보기"
MORE_SUMMON_CENTER = "캐릭터를 화면 가운데로"
MORE_QUIT_APP = "StudyPet 종료"
MODE_LABEL_POMODORO = "뽀모도로 (집중/휴식)"
MODE_LABEL_STOPWATCH = "스톱워치 (연속 측정)"

# 처음 사용자 안내 힌트 (v0.7 3-6)
HINT_FIRST_RUN = "안녕! 나를 클릭하면 메뉴가 열려요"
HINT_HOVER = "클릭: 메뉴 · 끌기: 이동"

# 모달 제목 및 버튼
MODAL_TITLE_MEMO = "세션 완료 메모"
MODAL_BTN_SAVE_MEMO = "저장"
MODAL_BTN_SAVE_NO_MEMO = "메모 없이 저장"

MODAL_TITLE_AFK = "자리 비움 감지"
MODAL_BTN_AFK_EXCLUDE = "기록에서 제외"
MODAL_BTN_AFK_INCLUDE = "기록에 포함"

MODAL_TITLE_RECOVERY = "미완료 학습 기록 복구"
MODAL_BTN_RECOVER_RESUME = "이어하기"
MODAL_BTN_RECOVER_SAVE = "여기까지 저장"
MODAL_BTN_RECOVER_DISCARD = "폐기"
MODAL_BTN_RECOVER_LATER = "나중에 결정"

MODAL_TITLE_QUIT = "StudyPet 종료"
MODAL_BTN_QUIT_SAVE = "저장 후 종료"
MODAL_BTN_QUIT_KEEP = "기록 유지하고 종료"
MODAL_BTN_CANCEL = "취소"

# 안내 메시지
MSG_SINGLE_INSTANCE = "StudyPet이 이미 실행 중입니다."
MSG_PERM_GRANT_QUESTION = (
    "현재 폴더에 학습 기록을 저장할 쓰기 권한이 없습니다.\n"
    "관리자 권한으로 현재 폴더의 쓰기 권한을 부여하시겠습니까?"
)
MSG_PERM_DENIED_MOVE_FOLDER = (
    "데이터 폴더에 쓰기 권한이 없어 실행할 수 없습니다.\n"
    "바탕화면이나 문서 등 쓰기 가능한 폴더로 StudyPet 폴더를 이동한 뒤 다시 실행해 주세요."
)
MSG_DB_LOCKED = (
    "데이터베이스 파일이 다른 프로그램에서 사용 중이어서 열 수 없습니다.\n"
    "동기화 프로그램이나 다른 인스턴스를 확인한 뒤 다시 실행해 주세요."
)
MSG_HOTKEY_CONFLICT = (
    "유령 모드 해제 단축키({hotkey})를 다른 프로그램이 사용 중이어서 등록할 수 없습니다.\n"
    "유령 모드는 작업 표시줄 트레이 메뉴에서 해제할 수 있습니다."
)
MSG_SHORTCUT_CREATED = "바탕화면에 StudyPet 바로가기를 만들었습니다."
MSG_SHORTCUT_FAILED = "바탕화면 바로가기 생성에 실패했습니다."
MSG_STORAGE_ERROR = "학습 기록 저장 중 오류가 발생했습니다. 다음 저장 주기에 자동으로 재시도합니다."
MSG_SUBJECT_NAME_INVALID = "과목명은 공백을 제외한 1~40자여야 하며 중복될 수 없습니다."
MSG_SUBJECT_GOAL_INVALID = "일일 목표 시간은 1~1440분 사이의 정수여야 합니다."
MSG_SUBJECT_ARCHIVE_ACTIVE = "현재 학습 진행 중인 과목은 보관할 수 없습니다."
MSG_SUBJECT_ARCHIVE_LAST = "최소 1개의 활성 과목이 남아 있어야 합니다."
MSG_SETTINGS_SAVED = "설정이 적용되었습니다."
MSG_SETTINGS_INVALID = "입력한 설정값이 허용 범위를 벗어났습니다. 값을 확인해 주세요."
MSG_CSV_EXPORT_DONE = "CSV 내보내기가 완료되었습니다:\n{path}"
MSG_CSV_EXPORT_ERROR = "CSV 내보내기 중 오류가 발생했습니다:\n{error}"
MSG_RECOVER_DISCARD_CONFIRM = "이 기록({subject} {minutes}분)을 삭제할까요? 되돌릴 수 없습니다."


def format_afk_message(away_wall_s: int, away_awake_s: int, can_include: bool) -> str:
    away_wall_min = max(1, away_wall_s // 60)
    away_awake_min = max(0, away_awake_s // 60)
    sleep_min = max(0, away_wall_min - away_awake_min)
    msg = f"자리 비운 시간: {away_wall_min}분"
    if sleep_min > 0:
        msg += f" (절전 {sleep_min}분은 제외)"
    if not can_include:
        msg += "\n※ 자정을 2회 이상 넘긴 자리 비움은 기록에 포함할 수 없습니다."
    return msg


def format_recovery_message(subject_name: str, duration_s: int, local_date: str, end_time_iso: str) -> str:
    dur_min = duration_s // 60
    time_part = end_time_iso[11:19] if len(end_time_iso) >= 19 else end_time_iso
    return f"정상 종료되지 않은 기록: {subject_name} {dur_min}분 ({local_date} {time_part}까지)"


def format_memo_prompt(subject_name: str, hms: str) -> str:
    return f"{subject_name} {hms} 학습 완료! 한 줄 메모를 남겨보세요 (최대 200자):"


def format_quit_confirm(subject_name: str, hms: str) -> str:
    return f"진행 중인 학습({subject_name}, {hms})을 저장하고 종료할까요?"


def format_switch_toast(prev_name: str, hms: str, new_name: str, saved_s: int) -> str:
    if saved_s <= 0:
        return f"{new_name}(으)로 바꿨어요"
    return f"{prev_name} {hms} 저장 → {new_name} 시작"


def format_more_ghost(shortcut: str) -> str:
    return f"유령 모드 ({shortcut})"
