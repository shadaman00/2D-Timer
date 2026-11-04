# 🍎 macOS 지원 개발 계획서 — StudyPet v1.1 (PyObjC 플랫폼 계층 추가)

**기준:** `DEVELOPMENT_PLAN.md` v0.7, `docs/REVISION_PLAN_v0.7.md` 9장까지 반영된 `src/studypet/**` (2026-11-04)
**작성일:** 2026-11-04
**방식:** 기존 Windows 구현은 그대로 두고, 운영체제에 묶인 부분을 공통 인터페이스 뒤로 분리한 뒤 macOS 구현(Python + PyObjC)을 추가한다.
**상태:** ⏸ **보류** (2026-11-04, 사용자 요청). 착수·결정(8장) 모두 진행하지 않음. 재개 시 M0 착수 전에 당시 코드 기준으로 2장 진단을 다시 확인할 것. 코드 변경 없음.

---

## 1. 요약

| 항목 | 내용 |
|---|---|
| 목표 | 같은 소스 트리에서 Windows(기존)와 macOS 13 이상을 지원한다. 타이머·기록·통계·UX(액션 카드, 확인 창 대기열)는 두 OS에서 동일하게 동작한다 |
| 재사용 | 약 2,600줄(29%)은 그대로 사용: 엔진·AFK·DB·통계·설정·FSM·물리·PNG·스프라이트·레이아웃·문구 |
| 분리 후 재사용 | Windows 모듈 안에 섞인 공통 로직 약 1,500줄을 순수 Python으로 꺼낸다: 펫 입력·카드·말풍선·힌트 로직, 화면 합성, 확인 창 의미 처리, 설정·과목 입력 검증, 차트 계산 |
| 신규 작성 | macOS 구현 약 3,000~3,500줄 (`studypet/mac/`) |
| 기간 | **약 37일(7.5주)**: 사전 검증 1주 → Windows 쪽 구조 분리 1.2주 → macOS 구현 4.2주 → 패키징·QA 1.4주 |
| Windows 영향 | 기능 변경 없음. 구조 분리(M1) 후 Windows 회귀 검사를 통과해야 다음 단계로 간다. macOS 코드는 Windows 패키지에 포함하지 않는다(SAC 영향 없음) |
| 선행 조건 | Mac 실기(Apple Silicon, macOS 14 이상 권장), Apple Developer Program 가입(공증용, 연 $99 — 8장 결정 M-D2) |

> 앞서 답변한 "4~6주"는 macOS 구현만 센 값이다. 이 계획서는 Windows 쪽 구조 분리, 서명·공증 패키징, 두 OS 회귀 검사를 포함해 7.5주로 잡았다.

---

## 2. 현재 구조 진단

### 2-1. 모듈별 OS 의존도

| 구분 | 모듈 | 처리 |
|---|---|---|
| 순수 (그대로) | `domain/*`, `infra/db.py`, `infra/config.py`, `infra/logging_setup.py`, `crashlog.py`, `graphics/panel.py`, `graphics/png_codec.py`, `graphics/sprites.py`, `ui/layout.py`, `strings.py` | 변경 없음 (문구 일부만 OS별 분기) |
| 섞여 있음 (분리) | `ui/pet_window.py`(1,366줄), `ui/modals.py`(561줄), `graphics/compositor.py`, `ui/tab_settings.py`, `ui/tab_subjects.py`, `ui/chart.py`, `win32/audio.py`(`scale_wav`), `win32/idle.py`(`compute_idle_ms`), `win32/monitors.py`(`Rect`·`MonitorInfo`·`phys_scale`), `win32/hotkey.py`(문자열 파싱), `app.py`(735줄) | 공통 로직을 꺼내고 Win32 호출만 남긴다 (4장) |
| Windows 전용 (유지) | `win32/api.py`, `win32/actctx.py`, `win32/tray.py`, `graphics/dib.py`, `graphics/text.py`(GDI), `ui/popup.py`, `ui/dashboard.py`, `infra/paths.py`(ACL), `infra/csv_export.py`(파일 대화상자), `bootstrap/sitecustomize.py` | 위치·동작 그대로. macOS 대응 구현을 새로 만든다 |

### 2-2. 분리가 필요한 지점 (macOS 구현 전에 반드시 해결)

| # | 위치 | 문제 | 분리 방향 |
|---|---|---|---|
| S1 | `pet_window.py` | 카드 열기/닫기, 히트 판정, 힌트·토스트, 드래그 판정, 8초 닫기, 레이어 캐시가 `HWND`·`GetAsyncKeyState`·`SetTimer`와 한 클래스에 있다 | 순수 `PetController`(상태·입력 해석·레이어 구성)와 OS별 `PetSurface`(창·출력·커서·타이머)로 나눈다 |
| S2 | `pet_window.py`, `monitors.py` | `self.scale` 하나가 "화면 좌표 배율"과 "출력 버퍼 배율"을 겸한다. Windows는 둘 다 물리 px이라 같지만, macOS는 화면 좌표가 포인트(pt), 버퍼는 픽셀이라 Retina에서 2배 차이 난다 | `layout_scale`(sp → 화면 좌표 단위)과 `render_scale`(sp → 버퍼 px)로 나눈다. Windows는 두 값이 같다 |
| S3 | `compositor.py` | 합성(행 복사)과 출력(`UpdateLayeredWindow`)이 한 클래스다 | 순수 `FrameComposer`(BGRA 버퍼 반환)와 OS별 `present()`로 나눈다 |
| S4 | `graphics/text.py` | 텍스트 측정·그리기가 GDI `HDC`를 받는다 | `TextRenderer` 인터페이스(`measure(text, scale)`, `render_on_panel(...)`)로 감싼다. macOS는 Core Text 구현 |
| S5 | `modals.py` | `ModalQueue`는 순수하지만, 버튼 ID 의미(복구 4버튼, 폐기 재확인, X = 취소 ID)가 Win32 창 코드에 섞여 있다 | `ModalSpec`(제목·문구·버튼 목록·입력란·기본/취소 ID)과 결과 해석을 공통 `ModalManager`로 올리고, 창 생성만 `ModalHost`로 내린다 |
| S6 | `tab_settings.py`, `tab_subjects.py` | 입력 검증과 `SettingsPatch` 생성이 컨트롤 읽기 코드와 섞여 있다 | `settings_model.py`, `subjects_model.py`(검증·패치 생성)로 분리 |
| S7 | `ui/chart.py` | 막대 좌표 계산과 GDI 그리기가 한 클래스다 | `chart_model.py`(막대·눈금·라벨 좌표 계산)와 OS별 그리기로 분리 |
| S8 | `app.py` | 기동 순서(뮤텍스·DPI·경로·메시지 루프)와 이벤트 조정이 한 파일이다 | 공통 `AppController` + OS별 `run_app_win()` / `run_app_mac()` 진입점 |
| S9 | `infra/paths.py` | "실행 파일 옆 `data/`" 포터블 모델 전제 | `AppPaths` 인터페이스. macOS는 `~/Library/Application Support/StudyPet` (5-2) |

---

## 3. 목표 구조

### 3-1. 디렉터리

Windows 파일 위치는 바꾸지 않는다(SAC 검증된 패키징·테스트 경로 유지, 회귀 위험 최소화). 공통 로직은 새 파일로 꺼내고, macOS는 `studypet/mac/` 아래에 모은다.

```
src/studypet/
├── ports.py                  # 신규: OS 공통 인터페이스(Protocol) 정의
├── app.py                    # 공통 AppController (OS 무관 부분만)
├── app_win.py                # 신규: Windows 진입점 run_app_win() (기존 run_app 이동)
├── domain/ infra/(db, config, logging_setup) strings.py      # 그대로
├── graphics/
│   ├── composer.py           # 신규: FrameComposer (S3, 순수)
│   ├── compositor.py         # Windows: composer + UpdateLayeredWindow
│   ├── panel.py png_codec.py sprites.py                         # 그대로
│   ├── text.py               # Windows GDI TextRenderer
│   └── dib.py                # Windows 전용
├── ui/
│   ├── pet_controller.py     # 신규: 펫 입력·카드·말풍선·힌트·토스트 로직 (S1, 순수)
│   ├── pet_window.py         # Windows PetSurface
│   ├── modal_core.py         # 신규: ModalQueue + ModalSpec + 결과 해석 (S5, 순수)
│   ├── modals.py             # Windows ModalHost
│   ├── settings_model.py subjects_model.py chart_model.py      # 신규 (S6·S7, 순수)
│   ├── layout.py             # 그대로
│   └── dashboard.py tab_*.py chart.py popup.py                  # Windows 전용
├── win32/                    # Windows 전용 (그대로)
└── mac/                      # 신규: macOS 구현 (PyObjC). Windows 패키지에서 제외
    ├── app_mac.py            # run_app_mac(), NSApplication 델리게이트
    ├── runloop.py            # NSTimer(공통 모드) 래퍼, post()
    ├── pet_surface.py        # NSPanel + CALayer 출력, 마우스 이벤트
    ├── text_coretext.py      # Core Text TextRenderer
    ├── displays.py           # NSScreen → MonitorInfo
    ├── status_item.py        # 메뉴 막대 아이콘 (트레이 대응)
    ├── popup.py              # NSMenu 팝업 (show_popup 대응)
    ├── modal_host.py         # NSPanel 확인 창
    ├── dashboard.py tab_subjects.py tab_settings.py tab_stats.py chart_view.py
    ├── hotkey_carbon.py      # Carbon RegisterEventHotKey (ctypes)
    ├── idle.py sound.py system_events.py dialogs.py paths.py single_instance.py
    └── fonts.py              # Galmuri11 프로세스 범위 등록
```

### 3-2. 공통 인터페이스 (`ports.py`)

```python
class Clock(Protocol):                      # 기존 domain.clock 규약 유지
    def mono_ns(self) -> int: ...           # 절전 중 멈추는 단조 시계
    def now_local(self) -> datetime: ...

class Displays(Protocol):
    def list_monitors(self) -> list[MonitorInfo]: ...
    def monitor_at(self, x: int, y: int) -> MonitorInfo: ...   # 화면 좌표(아래 3-3)
    def primary(self) -> MonitorInfo: ...
    def invalidate(self) -> None: ...

class TextRenderer(Protocol):
    def measure(self, text: str, scale: int) -> tuple[int, int]: ...
    def render_on_panel(self, panel_bgra: bytes, w_px: int, h_px: int, scale: int,
                        lines: list[tuple[int, int, str, tuple[int, int, int]]]) -> bytes: ...
    def destroy(self) -> None: ...

class PetSurface(Protocol):                 # PetController가 사용하는 창 기능
    def create(self, controller: "PetController") -> None: ...
    def present(self, frame: bytes, w_px: int, h_px: int, x: int, y: int, opacity: float) -> bool: ...
    def set_ghost(self, enabled: bool) -> None: ...              # 클릭 투과 + 반투명
    def set_temp_interactive(self, enabled: bool) -> None: ...   # 유령 모드 Alt/Option 임시 해제
    def cursor_pos(self) -> tuple[int, int]: ...
    def poll_mouse_clicked(self) -> bool: ...                    # 카드 바깥 클릭 감지 (V7)
    def is_modifier_down(self, key: Literal["alt"]) -> bool: ...
    def begin_capture(self) -> None: ...
    def end_capture(self) -> None: ...
    def set_timer(self, tid: int, ms: int) -> None: ...
    def kill_timer(self, tid: int) -> None: ...
    def destroy(self) -> None: ...

class PopupMenu(Protocol):
    def show(self, items: list[MenuItem], anchor: tuple[int, int] | None) -> int: ...   # 0 = 취소

class StatusIcon(Protocol):                  # 트레이 / 메뉴 막대
    def add(self) -> bool: ...
    def remove(self) -> None: ...
    def show_menu(self, state: TimerState, ghost_active: bool, actions: TrayActions) -> None: ...

class ModalHost(Protocol):
    def open(self, spec: ModalSpec, on_button: Callable[[int, str], None]) -> object: ...
    def close(self, handle: object) -> None: ...
    def bring_to_front(self, handle: object) -> None: ...
    def confirm(self, text: str, title: str) -> bool: ...        # 폐기 재확인

class DashboardHost(Protocol):
    def open_tab(self, idx: int, ref_pos: tuple[int, int] | None) -> None: ...
    def on_second_tick(self) -> None: ...
    def refresh_stats(self) -> None: ...
    def close(self) -> None: ...

class Hotkeys(Protocol):
    def register(self, shortcut: str, on_fire: Callable[[], None]) -> bool: ...
    def unregister(self) -> None: ...

class Sound(Protocol):  ...                 # 기존 SoundPlayer 메서드 그대로 (play/set_volume/set_enabled/stop)
class IdleSource(Protocol):
    def idle_ms(self) -> int: ...
class Dialogs(Protocol):
    def info(self, message: str, warning: bool = False) -> None: ...
    def ask_save_path(self, default_dir: Path, default_name: str) -> Path | None: ...
class SystemEvents(Protocol):               # 절전·깨어남·잠금·해제·세션 종료 → 콜백 연결
    def connect(self, on_suspend, on_resume, on_lock, on_unlock, on_end_session) -> None: ...

@dataclass(frozen=True)
class Platform:                             # 진입점이 조립해서 AppController에 넘긴다
    clock: Clock; displays: Displays; text: TextRenderer; surface: PetSurface
    popup: PopupMenu; status: StatusIcon; modals: ModalHost; dashboard_factory: Callable[..., DashboardHost]
    hotkeys: Hotkeys; sound: Sound; idle: IdleSource; dialogs: Dialogs; events: SystemEvents
    paths: AppPaths; features: PlatformFeatures   # 예: desktop_shortcut=False (macOS)
```

- `AppController`는 `Platform`만 받는다. `user32` 등 OS 모듈을 직접 import하지 않는다(2-2 S8).
- `tests/test_wiring.py`(v0.7 9장)를 확장해 `ports.py` 규약과 각 구현 클래스의 시그니처 일치를 검사한다(6장).

### 3-3. 좌표·배율 규약 (S2)

| 값 | Windows | macOS |
|---|---|---|
| 화면 좌표 단위 | 물리 px, 원점 = 가상 화면 좌상단, y 아래로 증가 | **포인트(pt)**, 원점 = 주 모니터 좌상단, y 아래로 증가 (Cocoa의 좌하단·y 위 좌표를 어댑터에서 뒤집는다) |
| `layout_scale` (sp → 화면 단위) | `phys_scale(config_scale, dpi)` | `config_scale` |
| `render_scale` (sp → 버퍼 px) | `layout_scale`과 같음 | `config_scale × backingScaleFactor` (Retina = 2) |
| 작업 영역 | `MONITORINFO.rcWork` | `NSScreen.visibleFrame` (메뉴 막대·Dock 제외) |
| `MonitorInfo.dpi` | 실제 DPI | `96 × backingScaleFactor` (기존 계산식 재사용) |

- `PetController`·`physics`·`layout`은 화면 단위와 `layout_scale`만 쓰고, 버퍼 크기 계산에만 `render_scale`을 쓴다.
- macOS의 y 뒤집기: `y_down = primary.frame.height − y_up`. 창 위치: `frame.origin.y = primary_h − (top + height)`.
- 모니터 변경 감지: Windows `WM_DISPLAYCHANGE` ↔ macOS `NSApplicationDidChangeScreenParametersNotification`.

---

## 4. 단계 M1 — Windows 쪽 구조 분리 (동작 변경 없음)

macOS 코드를 쓰기 전에 Windows에서 끝낸다. 이 단계의 완료 조건은 **Windows 동작이 바이트 단위로 같은 것**이다(출력 버퍼 비교 테스트 포함).

| 순서 | 작업 | 산출물 | 검증 |
|---|---|---|---|
| 1 | `ports.py` 작성, 기존 `RealClock`·`SoundPlayer`·`get_idle_ms` 등을 규약에 맞게 감싼 Windows 어댑터 | `ports.py`, `win32/*` 소폭 수정 | 시그니처 규약 테스트 |
| 2 | `FrameComposer` 분리 (S3) | `graphics/composer.py` | 같은 입력 → `compositor` 이전 결과와 BGRA 바이트 동일 |
| 3 | `TextRenderer` 인터페이스 적용 (S4) | `graphics/text.py`가 규약 구현 | 기존 렌더 결과 동일 |
| 4 | `PetController` 분리 (S1·S2): 상태 변수, `toggle_card`, `_execute_card`, 히트 판정, 힌트·토스트, 드래그 임계값, 8초 닫기, 레이어 빌드, 메뉴 지연 집계 | `ui/pet_controller.py`, `pet_window.py`는 `PetSurface` 구현만 남김(목표 500줄 이하) | 신규 `tests/test_pet_controller.py`: 가짜 Surface로 클릭·드래그·우클릭·모달 잠금 클릭·바깥 클릭·8초 닫기·힌트 표시 시나리오 |
| 5 | `modal_core.py` 분리 (S5): `ModalQueue`, `ModalSpec`, 복구·메모·AFK·종료 버튼 의미, 폐기 재확인 흐름 | `ui/modal_core.py`, `modals.py`는 `ModalHost` 구현만 | 기존 `test_modal_queue.py` + 신규 버튼 의미 테스트(가짜 Host) |
| 6 | `settings_model.py`·`subjects_model.py`·`chart_model.py` 분리 (S6·S7) | 3개 파일 | 검증 규칙·차트 좌표 단위 테스트 |
| 7 | `app.py` → 공통 `AppController` + `app_win.py` (S8), `paths`를 `AppPaths` 규약으로 | `app_win.py`, `__main__.py` 분기 | `test_wiring.py` 확장 통과 |
| 8 | `package_portable.py`: `studypet/mac/` 제외 규칙 추가 | 스크립트 | 패키지 목록에 `mac/` 없음 확인 |

**Windows 회귀 관문(M1 종료 조건):**
- 단위 테스트 전체 통과 (현재 71개 + 신규).
- `REVISION_PLAN_v0.7.md` 5장 수동 체크리스트 전부 재통과.
- Phase 0 성능 기준 유지: CPU < 2%, RAM ≤ 120MB, Cold Start ≤ 1.5s, present ≤ 3ms.
- 재패키징 후 서명 전수 `Valid`.

---

## 5. 단계 M2~M6 — macOS 구현 상세

### 5-1. 실행 환경과 앱 수명주기 (`mac/app_mac.py`, `runloop.py`)

| 항목 | 구현 |
|---|---|
| Python | python.org 3.12.x **universal2** 프레임워크 빌드 (Apple Silicon·Intel 공용) |
| 의존성 | `pyobjc-core`, `pyobjc-framework-Cocoa`, `pyobjc-framework-Quartz` (CoreText·CoreGraphics·CALayer 포함). 버전 고정(`requirements-mac.txt`) |
| 앱 형태 | 메뉴 막대 앱: `Info.plist`의 `LSUIElement = YES` (Dock 아이콘 없음, Windows의 도구 창과 같은 위치) |
| 이벤트 루프 | `NSApplication.sharedApplication().run()`. 기존 `SetTimer` 대응은 `NSTimer`를 **`NSRunLoopCommonModes`** 에 등록한다. 기본 모드에만 등록하면 메뉴가 열려 있는 동안(이벤트 추적 모드) 엔진 틱이 멈춘다 |
| 타이머 ID | 기존 ID(1~6)와 주기(프레임 16/33ms, 엔진 250ms, 유휴 1s, UI 100ms, 최상위 5s, 설정 저장 1s) 그대로. 최상위 재지정(TID_TOPMOST)은 macOS에서 불필요하므로 생략 |
| 단일 실행 | `Info.plist` `LSMultipleInstancesProhibited = YES` + 데이터 폴더의 `instance.lock`에 `fcntl.flock`. 이미 실행 중이면 Finder 재실행 시 `applicationShouldHandleReopen_hasVisibleWindows_`에서 캐릭터 소환(`WM_APP_SUMMON` 대응) |
| 첫 프레임 뒤 초기화 | `WM_APP_POST_START` 대응: `performSelector_withObject_afterDelay_(…, 0)`로 메뉴 막대·단축키·효과음·복구 검사 |
| 종료 | `applicationShouldTerminate_`에서 `AppController.shutdown(post_quit=False)` 후 `NSTerminateNow`. 로그아웃·재시동 시에도 이 경로로 들어온다(H6 대응). `NSProcessInfo.disableSuddenTermination()`으로 강제 즉시 종료를 막는다 |
| 크래시 로그 | 기존 `crashlog.py` 그대로. PyObjC 콜백 진입점마다 `try/except → write_crash_log()` (Windows `_wnd_proc`와 같은 규칙) |

### 5-2. 데이터 위치 (`mac/paths.py`)

- Windows의 "실행 파일 옆 `data/`" 방식은 macOS에서 쓸 수 없다. 서명된 `.app` 안에 쓰면 서명이 깨지고, 격리(App Translocation)된 실행에서는 앱 위치가 읽기 전용 임시 경로가 된다.
- 위치: `~/Library/Application Support/StudyPet/` 아래 `config.json`, `study_records.db`, `logs/`, `exports/`. `paths.py`의 폴더 구조(`config_path`, `db_path`, `logs_dir`, `exports_dir`)는 그대로 유지한다.
- CSV 내보내기 기본 폴더는 `~/Documents`(저장 대화상자에서 변경 가능).
- [더보기]에 `데이터 폴더 열기` 추가 (macOS 전용, `NSWorkspace.openURL_`).
- Windows → Mac 이전: 스키마·설정 형식이 같으므로 `data/`의 두 파일을 복사하면 된다. `last_position`은 화면 밖이면 기존 클램핑 로직이 처리한다. 안내를 `실행 가이드`에 추가한다.

### 5-3. 펫 창 (`mac/pet_surface.py`) — M3의 핵심

| Windows | macOS 구현 |
|---|---|
| `WS_EX_LAYERED` + `UpdateLayeredWindow` | `NSPanel`, `styleMask = Borderless \| NonactivatingPanel`, `setOpaque_(False)`, `backgroundColor = clearColor`, `hasShadow = False` |
| BGRA 버퍼 출력 | 콘텐츠 뷰를 layer-backed로 만들고 `CALayer.contents = CGImage`. 이미지는 `CGImageCreate(w, h, 8, 32, stride, sRGB, kCGImageAlphaPremultipliedFirst \| kCGBitmapByteOrder32Little, provider, …)`로 만든다. 기존 premultiplied BGRA 버퍼를 **변환 없이** 그대로 쓴다. `contentsScale = backingScaleFactor`, `magnificationFilter = kCAFilterNearest` |
| `WS_EX_TOPMOST` | `setLevel_(NSFloatingWindowLevel)` + `collectionBehavior = CanJoinAllSpaces \| Stationary \| FullScreenAuxiliary \| IgnoresCycle` (모든 데스크톱 공간·전체 화면 앱 위에 표시, ⌘` 순환 제외) |
| `WS_EX_NOACTIVATE`, `MA_NOACTIVATE` | 비활성화 패널 + `canBecomeKeyWindow → False`, `canBecomeMainWindow → False` 재정의. 클릭해도 공부하던 앱의 포커스가 유지된다 |
| 투명 픽셀 클릭 투과 | **위험 R1 (7장).** 1안: 투명 창의 알파 0 영역 투과(창 서버 기본 동작)를 PoC에서 확인. 2안(대비책): UI 타이머(30ms)에서 커서 아래 알파 마스크를 보고 `setIgnoresMouseEvents_`를 전환. 알파 마스크는 합성 시 행 단위로 함께 만든다(픽셀 루프 금지 원칙 유지) |
| 유령 모드 | `setIgnoresMouseEvents_(True)` + `setAlphaValue_(0.3)`. Option 키 임시 해제는 `NSEvent.modifierFlags()`(클래스 메서드, 권한 불필요)로 폴링 |
| `WM_LBUTTONDOWN/UP`, `WM_RBUTTONUP` | `mouseDown_`, `mouseUp_`, `rightMouseUp_`. **Control+클릭은 우클릭으로 처리**(macOS 관례). 트랙패드 두 손가락 클릭은 시스템이 `rightMouse*`로 전달 |
| `SetCapture` 드래그 | `mouseDragged_`는 버튼을 누른 동안 창 밖에서도 들어온다. 좌표는 `NSEvent.mouseLocation()`(화면 pt)을 3-3 규약으로 변환. `WM_CAPTURECHANGED` 대응은 `mouseUp_` 누락 대비로 `NSEvent.pressedMouseButtons() == 0` 확인 |
| `TrackMouseEvent` / `WM_MOUSELEAVE` | `NSTrackingArea(MouseEnteredAndExited \| MouseMoved \| ActiveAlways \| InVisibleRect)` |
| Alt + 휠 | `scrollWheel_`에서 Option 키 확인 |
| `GetAsyncKeyState & 0x8001` (V7) | `NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(LeftMouseDown \| RightMouseDown)`로 다른 앱 위 클릭을 감지해 `poll_mouse_clicked()`에 기록한다. 마우스 이벤트 전역 모니터는 손쉬운 사용 권한이 필요 없다(키보드 이벤트만 필요) |
| 디스플레이 배율 | 창이 다른 모니터로 이동하면 `windowDidChangeBackingProperties`에서 `render_scale` 재계산 → 레이어 캐시 무효화 |

**성능 기준 (Windows Phase 0과 동일 항목):** 대기 중 CPU < 2%, RAM ≤ 150MB(PyObjC 상주분 +30MB 허용), Cold Start ≤ 2.0s, present ≤ 3ms(배율 2 × Retina = 768×576 버퍼 기준).

### 5-4. 텍스트 (`mac/text_coretext.py`, `fonts.py`)

- Galmuri11: `CTFontManagerRegisterFontsForURL(url, kCTFontManagerScopeProcess, None)`로 프로세스 범위 등록. 실패하면 `Apple SD Gothic Neo`로 대체(Windows의 맑은 고딕 대응).
- 그리기: `CGBitmapContextCreate`(BGRA premultiplied)에 패널 바이트를 올리고 `CTLineDraw`. 도트 느낌을 위해 `CGContextSetShouldAntialias(False)`, `CGContextSetShouldSmoothFonts(False)`. CG 좌표는 y 위 방향이므로 줄 위치를 뒤집는다.
- 측정: `CTLineGetTypographicBounds`. 카드·말풍선 폭 계산은 기존 `compute_bubble_box_sp`를 그대로 쓴다.
- 검증: Windows와 같은 문자열의 측정 폭 차이가 ±1sp 이내여야 한다. 넘으면 카드 라벨 자리를 다시 맞춘다(`test_layout`에 폭 상한 테스트 추가).

### 5-5. 메뉴 막대·팝업·단축키·효과음·유휴 (M4)

| Windows | macOS |
|---|---|
| 트레이 아이콘 (`Shell_NotifyIcon`) | `NSStatusBar.systemStatusBar().statusItemWithLength_(Variable)`. 템플릿 이미지(흑백 18×18pt, `@2x` 포함)로 다크 모드 자동 대응. 새 에셋 `assets/icons/statusbar_template.png` |
| 트레이 좌클릭 = 카드 열기, 우클릭 = 메뉴 | 결정 M-D3 (8장). 권장: **클릭 = 메뉴**(macOS 관례). 메뉴 맨 위에 `학습 시작/일시정지/이어하기`, 다음에 `메뉴 카드 열기` |
| `TaskbarCreated` 재등록 | 불필요 |
| `TrackPopupMenu` (`ui/popup.py`) | `NSMenu.popUpMenuPositioningItem_atLocation_inView_`. 메뉴가 닫힐 때까지 반환하지 않으므로 기존 `show_popup()`과 같은 "선택한 명령 ID 반환" 방식으로 감쌀 수 있다. 항목마다 `tag = 명령 ID`, 공통 target이 선택 tag를 기록. `SetForegroundWindow`·`WM_NULL` 처리는 필요 없고, **포커스 이동도 없다**(v0.7 D1의 포커스 예외가 macOS에서는 생기지 않음) |
| 단축키 `RegisterHotKey` | Carbon `RegisterEventHotKey` + `InstallEventHandler`를 ctypes로 호출(권한 불필요, Apple Silicon에서 동작). 설정 문자열은 그대로 쓰고 해석만 바꾼다: `Ctrl → ⌃`, `Alt → ⌥`, `Shift → ⇧`, 신규 `Cmd → ⌘`. 기본값 `Ctrl+Alt+G`(⌃⌥G)는 유지 → 설정 마이그레이션 없음. 메뉴 표시는 `⌃⌥G` 기호로 |
| `PlaySoundW` 메모리 재생 | `NSSound.alloc().initWithData_(NSData)`, `setVolume_`. 기존 `scale_wav`는 쓰지 않고 `setVolume_` 사용 |
| `GetLastInputInfo` | `CGEventSourceSecondsSinceLastEventType(kCGEventSourceStateHIDSystemState, kCGAnyInputEventType)` × 1000 (권한 불필요) |
| `QueryUnbiasedInterruptTime` | `time.monotonic_ns()`. macOS에서는 `mach_absolute_time` 기반이라 **절전 중에 멈춘다** → 엔진 가정(절전 시간 제외)과 같다. PoC에서 실제 절전·깨어남으로 확인(위험 R5) |
| `WM_POWERBROADCAST` | `NSWorkspaceWillSleepNotification` / `NSWorkspaceDidWakeNotification` |
| `WM_WTSSESSION_CHANGE` 잠금/해제 | 분산 알림 `com.apple.screenIsLocked` / `com.apple.screenIsUnlocked` + `NSWorkspaceSessionDidResignActiveNotification`(빠른 사용자 전환) |

### 5-6. 확인 창 (`mac/modal_host.py`, M5)

- `NSAlert.runModal()`은 중첩 모달 루프라서 v0.6의 "단일 메시지 루프" 원칙과 v0.7 `ModalQueue`(비차단 표시 + 콜백) 구조에 맞지 않는다. 그래서 **`NSPanel`로 직접 만든다**(titled, closable, floating level).
- `ModalSpec` → 문구 `NSTextField`(라벨), 메모 입력란(`NSTextField`, 200자 제한 `NSFormatter`), 버튼 `NSButton` 목록.
- 키보드: 기본 버튼 `keyEquivalent = "\r"`(Return), 취소 버튼 `"\x1b"`(Esc). 닫기 버튼(빨간 원)은 `windowShouldClose_`에서 `cancel_id`로 처리 → 복구 창 X = `나중에 결정` 규칙(H2) 그대로.
- 활성화: 메모·복구·종료 확인은 `NSApp.activateIgnoringOtherApps_(True)` 후 `makeKeyAndOrderFront_`. AFK 복귀 창은 비활성화 패널 + `orderFrontRegardless()`(포커스를 뺏지 않음, Windows `SW_SHOWNOACTIVATE`와 같음).
- 폐기 재확인은 이 경우에 한해 `NSAlert.runModal()`을 쓴다(사용자가 직접 누른 직후의 짧은 확인이라 허용).
- 정보 메시지(`show_info_message`)도 `NSAlert`.

### 5-7. 대시보드 (`mac/dashboard.py` 외, M6)

| 탭 | Windows 컨트롤 | macOS 구현 |
|---|---|---|
| 프레임 | `SysTabControl32` 640×480 | `NSWindow`(titled·closable·miniaturizable) 640×480pt + `NSTabView` |
| 과목 관리 | ListView, Edit, 색상 버튼 | `NSTableView` + PyObjC 데이터 소스, `NSColorWell`, 목표 분 `NSTextField` + `NSNumberFormatter`. 검증은 `subjects_model.py` 공용 |
| 설정 | 콤보·트랙바·체크·HOTKEY_CLASS | `NSPopUpButton`, `NSSlider`, `NSButton`(체크), 배율 `NSSegmentedControl`, 단축키 입력은 `keyDown_`·`performKeyEquivalent_`를 가로채는 `NSTextField` 하위 클래스. [적용] → `settings_model.build_patch()` → `SettingsPatch` (M1 공용) |
| 공부 기록장 | 기간 버튼, 요약, GDI 차트, CSV | `NSSegmentedControl`(일·주·월), 이전/다음 버튼, 요약 라벨, `chart_view.py`(`NSView.drawRect_` + `NSBezierPath`, 좌표는 `chart_model.py` 공용), CSV는 `NSSavePanel` |
| 키보드 이동 | `IsDialogMessageW` + `WS_EX_CONTROLPARENT` | Cocoa 기본 키 뷰 순환(`nextKeyView`). `window.setAutorecalculatesKeyViewLoop_(True)` |
| 1초 갱신 | `on_second_tick → refresh_live()` | 같음 (캐시 + 진행 중 시간 합산, M4 규칙 유지) |

### 5-8. macOS용 UX 차이 정리

| 항목 | Windows | macOS |
|---|---|---|
| 우클릭 | 우클릭 | 우클릭, Control+클릭, 두 손가락 클릭 |
| 단축키 표기 | `Ctrl+Alt+G` | `⌃⌥G` (설정 값은 같음) |
| 유령 모드 보조 경로 | Alt + 휠, Alt 누른 채 호버 | Option + 휠, Option 누른 채 호버 |
| 트레이 문구 | "트레이" | "메뉴 막대" (`strings.py`에 OS별 분기 추가) |
| 바탕화면 바로가기 메뉴 | 있음 | 숨김(`features.desktop_shortcut = False`). 로그인 시 자동 실행(`SMAppService`, macOS 13+)은 v1.2 후보 |
| 팝업 메뉴 포커스 | 일시 이동(D1 예외) | 이동 없음 |
| 데이터 폴더 | 실행 파일 옆 `data/` | `~/Library/Application Support/StudyPet/` + [더보기] `데이터 폴더 열기` |
| 전체 화면 앱 | 최상위 창 | 모든 데스크톱 공간과 전체 화면 위에 표시 |

---

## 6. 단계 M7·M8 — 패키징·서명·검증

### 6-1. 패키징 (`scripts/package_mac.py`, Mac에서 실행)

| 순서 | 작업 |
|---|---|
| 1 | **py2app**(권장, 결정 M-D4)으로 `StudyPet.app` 생성, `--arch universal2`. `Info.plist`: `CFBundleIdentifier = <조직>.studypet`, `LSUIElement`, `LSMultipleInstancesProhibited`, `LSMinimumSystemVersion = 13.0`, `NSHumanReadableCopyright` |
| 2 | 포함 범위: `studypet/`(Windows 전용 `win32/`·`app_win.py`·`ui/dashboard.py` 등 제외), `assets/`(Windows `.ico`·`.manifest` 제외, 메뉴 막대 아이콘·`.icns` 추가) |
| 3 | 서명: 내부 `.so`·`.dylib`·`Python.framework`부터 바깥 순서로 `codesign --options runtime --timestamp -s "Developer ID Application: …"`. 엔타이틀먼트는 기본값으로 시작. ctypes 콜백(Carbon 단축키)이 Hardened Runtime에서 막히면 `com.apple.security.cs.allow-unsigned-executable-memory`를 추가한다(위험 R4, PoC에서 확정) |
| 4 | 공증: `xcrun notarytool submit StudyPet.dmg --wait` → `xcrun stapler staple` |
| 5 | 배포 파일: `StudyPet_v1.1.0_mac.dmg`(`hdiutil create`, Applications 바로가기 포함) |
| 6 | 검증: `spctl --assess --type execute -v StudyPet.app` = accepted, `codesign --verify --deep --strict`, 격리 속성(quarantine)을 붙인 사본으로 첫 실행 확인 |

**공증 없이 배포할 때(결정 M-D2에서 미가입 선택 시):** ad-hoc 서명(`codesign -s -`)만 한다. 사용자는 첫 실행 때 시스템 설정 → 개인정보 보호 및 보안 → [그래도 열기]를 눌러야 한다(macOS 15부터는 Finder 우클릭 → 열기로 우회할 수 없다). 배포 범위가 본인·소수라면 허용 가능하지만, 일반 배포에는 권하지 않는다.

### 6-2. 테스트

| 종류 | 내용 | 실행 OS |
|---|---|---|
| 기존 단위 테스트 | `domain`·`db`·`config`·`layout`·`modal_queue`·AFK·자정·복구 등 | Windows, macOS 모두 (같은 결과여야 함) |
| M1 신규 | `test_pet_controller.py`, 확인 창 버튼 의미, `settings_model`·`subjects_model`·`chart_model`, `FrameComposer` 바이트 동일성 | 두 OS |
| 규약 검사 | `test_wiring.py` 확장: `ports.py` Protocol ↔ Windows·macOS 구현 클래스 시그니처 일치, `app.py`의 Platform 호출 bind 검사 | 각 OS에서 해당 구현만 |
| macOS 어댑터 | 좌표 뒤집기(다중 모니터·서로 다른 배율), 단축키 문자열 ↔ Carbon 키코드, `MonitorInfo` 변환 | macOS |
| 성능 | `perf.log` 동일 형식(`render_ms`, `menu_latency_ms_avg`) + Activity Monitor CPU·메모리 | macOS |

**macOS 수동 체크리스트 (v0.7 5장 항목 + macOS 고유):**

| 항목 | 방법 | 기준 |
|---|---|---|
| v0.7 5장 전 항목 | 단일 입구, 상태별 카드, 과목 바꾸기, 종료 안전성, 복구 창 X, 모달 겹침, 첫 실행 힌트, 팝업 위치, 응답 속도 | Windows와 같은 결과 |
| 포커스 유지 | 메모 앱에 입력하는 중 카드 조작·팝업 메뉴 | 메모 앱 캐럿 유지 (팝업 포함) |
| 클릭 투과 | 캐릭터 옆 투명 영역 아래의 Finder 아이콘 클릭 | Finder가 클릭을 받음 |
| Retina / 일반 모니터 | 두 모니터 사이로 드래그 | 도트가 흐려지지 않고 크기 유지 |
| 데스크톱 공간·전체 화면 | Mission Control 공간 전환, 전체 화면 Safari 위 | 펫이 계속 보임 |
| Stage Manager | 켠 상태에서 앱 전환 | 펫이 무대 밖으로 밀리지 않음 |
| 절전·잠금 | 학습 중 덮개 닫기 10분 / 화면 잠금 | 절전 시간 제외, 잠금은 AFK 규칙대로 |
| 로그아웃·재시동 | 학습 중 로그아웃 | 다음 실행 때 복구 창, 손실 ≤ 1초 |
| 단축키 | ⌃⌥G, 다른 앱과 충돌하는 조합 | 동작 / 충돌 시 안내 메시지 |
| 다크 모드 | 시스템 다크 모드 전환 | 메뉴 막대 아이콘·대시보드 정상 |
| 첫 실행(공증본) | 다운로드한 DMG에서 설치·실행 | 경고 없이 실행 |

**검사 대상 OS:** macOS 13 Ventura, 14 Sonoma, 15 Sequoia (Apple Silicon). Intel Mac은 1대 확보 가능하면 14에서 1회 확인한다(결정 M-D5).

---

## 7. 위험과 대응

| # | 위험 | 영향 | 대응 | 확인 시점 |
|---|---|---|---|---|
| R1 | 투명 패널의 알파 0 영역 클릭 투과가 CALayer 출력에서 기대대로 동작하지 않음 | 캐릭터 주변이 클릭을 막음 | 5-3 2안(커서 위치 알파 마스크 + `setIgnoresMouseEvents_` 전환) | M0 PoC |
| R2 | 비활성화 패널이라도 클릭 시 앱이 활성화되어 포커스를 뺏음 | 핵심 UX 위반 | `NonactivatingPanel` 마스크는 생성 시점에만 유효 → 생성자에서 지정. `acceptsFirstMouse_ → True` | M0 PoC |
| R3 | Python 행 복사 합성이 Retina 4배 버퍼(768×576)에서 3ms를 넘음 | 프레임 지연 | 버퍼를 `layout_scale` 해상도로 만들고 CALayer 최근접 확대(`kCAFilterNearest`)로 Retina 배율을 GPU에 맡긴다(텍스트는 약간 굵어짐) | M0 PoC |
| R4 | Hardened Runtime에서 ctypes 콜백(Carbon 단축키) 실패 | 단축키 불가 | 엔타이틀먼트 추가 → 그래도 실패하면 단축키를 PyObjC `NSEvent` 로컬 처리 + [더보기] 메뉴만 제공 | M0 PoC (서명 빌드로) |
| R5 | `time.monotonic_ns()`의 절전 중 동작이 기대와 다름 | 절전 시간이 공부 시간에 포함 | `clock_gettime_ns(CLOCK_UPTIME_RAW)` 직접 사용 | M0 PoC |
| R6 | PyObjC·py2app이 Python 3.12 universal2에서 충돌 | 패키징 실패 | 버전 고정. 대안: Briefcase 또는 수동 번들 + python-build-standalone | M0 (빈 앱 패키징·공증 시험) |
| R7 | M1 분리 중 Windows 회귀 | 기존 사용자 영향 | M1을 독립 단계로 두고 4장 회귀 관문을 통과해야 macOS 작업 시작. 버퍼 바이트 동일성 테스트 | M1 |
| R8 | 개발 PC(Windows, SAC)에서 macOS 코드를 실행·검증할 수 없음 | 일정 지연 | Mac 실기 확보가 선행 조건. 순수 로직은 Windows에서, 어댑터는 Mac에서 개발 | 착수 전 |
| R9 | 같은 데이터를 두 OS에서 동시에 쓰려는 요구(클라우드 폴더 공유) | SQLite WAL 손상 위험 | 범위 밖. 이전은 "복사 1회"만 지원한다고 안내 | 문서 |

---

## 8. 결정이 필요한 항목

| # | 항목 | 선택지 | 권장 |
|---|---|---|---|
| M-D1 | 최소 지원 macOS | 12 / **13** / 14 | **13 Ventura**: 테스트 범위를 3개 버전으로 줄이고, `SMAppService`(로그인 시 실행) 같은 신규 API를 쓸 수 있다 |
| M-D2 | Apple Developer Program 가입(연 $99) | 가입·공증 / 미가입·ad-hoc | **가입**: 공증하지 않으면 macOS 15부터 사용자가 시스템 설정에서 직접 허용해야 한다 |
| M-D3 | 메뉴 막대 아이콘 클릭 | **클릭 = 메뉴** / Windows처럼 클릭 = 카드 | **클릭 = 메뉴**: macOS 관례. 메뉴에 `메뉴 카드 열기` 항목을 둔다 |
| M-D4 | 패키징 도구 | **py2app** / Briefcase / 수동 번들 | **py2app**: universal2·Python 3.12 지원, 설정 파일 하나로 끝난다. M0에서 서명·공증까지 시험 후 확정 |
| M-D5 | Intel Mac 지원 | universal2 빌드 + 1회 확인 / Apple Silicon 전용 | **universal2 빌드**(추가 비용 거의 없음). 실기 확인은 장비가 있으면 |
| M-D6 | 버전 번호 | 두 OS 모두 v1.1.0 / macOS만 1.1 | **두 OS 모두 v1.1.0**(M1 구조 분리가 Windows에도 들어가므로) |

---

## 9. 일정

| 단계 | 내용 | 기간 | 완료 조건 |
|---|---|---|---|
| M0 | 사전 검증(PoC, Mac): 투명 비활성화 패널에 BGRA 버퍼 출력, 클릭 투과, 포커스 유지, NSMenu 팝업 반환, 메뉴 막대, Carbon 단축키(서명 빌드), Core Text 비안티앨리어스, 절전 중 단조 시계, 빈 앱 py2app 패키징·공증 | 5일 | 7장 R1~R6 결론 기록, 성능 측정값 확보 |
| M1 | Windows 쪽 구조 분리 (4장) | 6일 | 4장 Windows 회귀 관문 통과, Windows v1.1.0 후보 빌드 |
| M2 | macOS 기반: 앱 수명주기, 런루프·타이머, 데이터 경로, 단일 실행, 시계·유휴, 시스템 이벤트, 로깅 | 3일 | 빈 펫 창으로 엔진 틱·절전·잠금 이벤트 로그 확인 |
| M3 | 펫 창: 출력, 좌표·배율, 입력(클릭·드래그·우클릭·휠·호버), 유령 모드, Core Text, 카드·말풍선·힌트·토스트 | 5일 | 수동 "단일 입구·상태별 카드·클릭 투과·포커스 유지·Retina" 통과, 성능 기준 충족 |
| M4 | 메뉴 막대, 팝업 메뉴, 단축키, 효과음 | 3일 | 수동 "팝업 위치·단축키" 통과 |
| M5 | 확인 창(메모·AFK·복구·종료), 정보 메시지, 폐기 재확인 | 3일 | 수동 "종료 안전성·복구 창 X·모달 겹침" 통과 |
| M6 | 대시보드 3개 탭, 차트, CSV 저장 | 5일 | 설정 적용·과목 CRUD·통계 일치(같은 DB를 Windows와 비교) |
| M7 | 패키징·서명·공증·DMG | 3일 | 6-1 검증 6번 통과 |
| M8 | QA·안정화: 6-2 체크리스트, macOS 13/14/15, 문서(`DEVELOPMENT_PLAN.md` v1.1, 실행 가이드 macOS편) | 4일 | 체크리스트 전부 통과, 성능 기준 재확인 |

**합계 37일(약 7.5주).** M0 결과에 따라 M3·M7 기간이 달라질 수 있으므로, M0 종료 시점에 일정을 다시 확정한다.

**작업 순서 원칙:**
1. M0에서 위험을 먼저 확인한다. R1·R2 중 하나라도 대비책으로도 해결되지 않으면 방식 재검토(2번 Qt 방식 포함)를 보고하고 멈춘다.
2. M1은 Windows만으로 완결되는 단계라서 M0과 병행할 수 있다(Mac 확보 전에 착수 가능).
3. M1이 끝나기 전에는 macOS 어댑터 코드를 `main`에 합치지 않는다.

---

## 10. 문서 반영 (승인 시)

- `DEVELOPMENT_PLAN.md` v1.1: 1장 범위에 macOS 추가, 2장 기술 스택에 PyObjC·py2app, 3장 구조도에 `ports.py`·`mac/`, 4-11 좌표·배율 규약(3-3), 12장 결정 기록에 M-D1~M-D6.
- `scripts/package_portable.py`: `mac/` 제외 규칙.
- `실행 가이드.txt`: macOS 설치·데이터 이전 절.
