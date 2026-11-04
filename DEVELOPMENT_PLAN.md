# 🛠️ 개발 계획서 & 상세 구현 명세: StudyPet (2D 도트 데스크톱 펫 학습 타이머)

**기준 문서:** `2d_timer_prd.md` (v1.0.0)
**작성일:** 2026-11-02 / **갱신일:** 2026-11-04
**상태:** v0.7 — 구현 코드 교차검증 결과(H1~H6, M1~M7, L1~L4) 및 **통합 액션 카드 UX 개편(`docs/REVISION_PLAN_v0.7.md`)** 반영본.

> 표기 규칙
> - **[실측]** 2026-11-03 `runtime/python-3.12-amd64`를 스크래치 복사본으로 실행해 확인한 사실
> - **[검증 필요]** 구현 전 Phase 0에서 확인해야 하는 가정
> - `sp` = 스프라이트 픽셀(도트 1칸). 화면 픽셀(`px`, 물리 픽셀) = `sp × phys_scale`

---

## 0. 변경 이력

| 버전 | 날짜 | 내용 |
|---|---|---|
| v0.1 | 2026-11-02 | 초안 (Tauri 2 + Rust) |
| v0.2 | 2026-11-02 | PRD 확인 사항 Q1~Q8 결정 |
| v0.3 | 2026-11-03 | SAC 대응 Electron 전환 초안 (Q9) |
| v0.4 | 2026-11-03 | Python 3.12.8 embeddable + Win32(ctypes) 아키텍처로 전환 (Q10) |
| v0.5 | 2026-11-03 | 상세 구현 명세 추가 (클래스·SQL·ctypes 구조체) |
| v0.6 | 2026-11-03 | v0.5 교차검증 결함 수정 + 코딩 가능 수준으로 상세화 (Q11·Q12) |
| **v0.7** | **2026-11-04** | **`docs/REVISION_PLAN_v0.7.md` 반영 (Q8 개정, Q13~Q15 추가).** ① 데이터 안전성(H1~H6): 종료 확인 [기록 유지하고 종료], 복구 창 X = [나중에 결정], 학습 중 과목 변경(`switch_subject`), `ModalQueue` 우선순위 대기열, `WM_QUERYENDSESSION`/`WM_ENDSESSION` 체크포인트 ② UX 개편: 좌·우클릭 통합 **"액션 카드"**(`176×78 sp`), 첫 실행·호버 힌트, 과목 전환 토스트 ③ 설정 부분 패치(`SettingsPatch`), 위치/과목 1초 디바운스 저장, 대시보드 Tab 이동, 통계 라이브 캐시 분리, `Galmuri11.ttf` 동봉, 패키징 출력 경로 분리(`dist/build/StudyPet_Portable/`) |

---

## 1. 요약

| 우선순위 | 핵심 과제 | PRD 근거 | 해결 전략 |
|---|---|---|---|
| 1 | SAC 강제 모드에서 코드 사이닝 없이 개발·실행 | 7장, Q9~Q10 | PSF 서명 `pythonw.exe`를 `StudyPet.exe`로 이름만 변경 + `._pth`의 `import site` + `sitecustomize.py` 가드 |
| 2 | 픽셀 단위 클릭 투과 (2px 정밀도) | 4장, AC#1 | `WS_EX_LAYERED` + `UpdateLayeredWindow(ULW_ALPHA)`. 스프라이트 알파는 0/255만 사용 |
| 3 | 저자원 (CPU < 2%, RAM ≤ 120MB, Cold Start ≤ 1.5s) | 4장, 8-1 | 단일 프로세스, **런타임 픽셀 루프 금지**(사전 스케일 프레임 + 행 단위 `memmove`), 상태별 프레임 타이머 간격 조절 |
| 4 | 포터블 + 크래시 복구 | 3-1 #4, AC#3·#4 | `sys.executable` 기준 `./data/`, SQLite WAL, 60초 체크포인트, 세션 체인 |
| 5 | 상태 머신 + 정밀 타이머 | 3-1 #1·#3, AC#2 | 절전을 제외하는 단조 시계(`QueryUnbiasedInterruptTime`), 크레딧 타임라인 기반 AFK 롤백 |

1차 릴리스: **Windows 10 1703+ / Windows 11 (x64)**. macOS는 범위 밖(10장).

---

## 2. 런타임 & 부트스트랩

### 2-1. 확정 런타임

- 원본: `runtime/python-3.12.8-embed-amd64.zip` → 압축 해제본 `runtime/python-3.12-amd64/` (**두 폴더 모두 수정 금지**)
- [실측] PE 31개 전부 Authenticode `Valid` (PSF 29, Microsoft 2: `vcruntime140*.dll`)
- [실측] 포함: `ctypes`, `sqlite3`(SQLite 3.45.3), `unittest`, `wave`, `zlib`, `struct`, `json`, `csv`, `datetime`, `logging`
- [실측] **사용 불가:** `tkinter`(미포함), `zoneinfo`(모듈은 있으나 시간대 DB가 없어 `ZoneInfoNotFoundError`), `winsound`의 `SND_MEMORY|SND_ASYNC`(`RuntimeError`)
- Python 3.12 계열은 보안 수정이 소스로만 배포되어 Windows 바이너리 갱신이 없다 → Phase 0에서 최신 바이너리 계열 전환 여부 1회 판단(11장 R5)

### 2-2. 폴더별 `._pth` (환경 변수 `PYTHONPATH`는 `._pth`가 있으면 무시된다)

| 용도 | 위치 | `python312._pth` 내용 |
|---|---|---|
| 개발 | `runtime/dev/` (원본 복사본) | `python312.zip` / `.` / `..\..\src` / `..\..\bootstrap` / `import site` |
| 배포 | `dist/StudyPet_Portable/` | `python312.zip` / `.` / `studypet.zip` / `import site` |

- 개발: `sitecustomize.py`는 `bootstrap/`에 있고 `..\..\bootstrap` 경로로 로드된다. (v0.5는 프로젝트 루트에 두어 `sys.path`에 없었다 — C1)
- 배포: `sitecustomize.py`는 루트(`.`)에, 앱 코드는 `studypet.zip`에 있다.
- `runtime/dev/`에는 `studypet_dev_root.txt`(내용: `..\..`)를 둔다 → 개발 모드 판별 + 프로젝트 루트 해석(4-1).
- 개발 런타임 생성: `scripts/setup_dev_runtime.ps1` (원본 복사 → `._pth` 작성 → 마커 파일 작성 → 가드 테스트용 `StudyPet.exe` 복사).

### 2-3. `bootstrap/sitecustomize.py` (전문)

```python
"""StudyPet 부트스트랩. StudyPet.exe(이름 변경된 pythonw.exe)를 인자 없이 실행했을 때만 앱을 기동한다."""
import os
import sys


def _should_autorun() -> bool:
    exe = os.path.basename(sys.executable).lower()
    return exe == "studypet.exe" and sys.argv in ([""], [])   # [실측] 인자 없는 실행 시 sys.argv == ['']


if _should_autorun():
    _code = 1
    try:
        from studypet.app import run_app
        _code = int(run_app() or 0)
    except BaseException:                       # SystemExit·KeyboardInterrupt 포함 전부 포착
        try:
            from studypet.crashlog import write_crash_log
            write_crash_log()                   # data/logs/crash.log (실패해도 무시)
        except BaseException:
            pass
    finally:
        os._exit(_code)                         # [실측] SystemExit는 init_import_site Fatal error → 반드시 os._exit
```

규칙:
1. `run_app()`은 **반환 전에** DB 커밋·`wal_checkpoint(TRUNCATE)`·트레이 아이콘 삭제·핫키 해제·뮤텍스 해제를 끝낸다. `atexit`·`finally`·GC 정리에 의존하지 않는다(`os._exit`가 건너뜀).
2. sitecustomize 실행 시점에는 `site` 임포트가 진행 중이다. 앱에서 `multiprocessing`·`__main__` 참조 피클링·스레드 내 신규 import를 쓰지 않는다.
3. `pythonw`에서는 `sys.stdout`/`sys.stderr`가 `None`이다. 출력은 모두 `logging`(파일)으로만 한다.

### 2-4. 실행 방법

| 목적 | 명령 (프로젝트 루트에서) |
|---|---|
| 개발 실행 | `runtime\dev\pythonw.exe -m studypet` (`src/studypet/__main__.py` → `os._exit(run_app())`) |
| 콘솔 디버그 실행 | `runtime\dev\python.exe -m studypet --console` (로그를 stderr에도 출력) |
| 단위 테스트 | `runtime\dev\python.exe -m unittest discover -s tests -t .` |
| 가드 확인 | `runtime\dev\StudyPet.exe` (앱 기동) / `runtime\dev\python.exe -c pass` (기동 안 함) |
| 에셋 생성 | `runtime\dev\python.exe scripts\gen_sprites.py`, `scripts\gen_sfx.py` |
| 패키징 | `runtime\dev\python.exe scripts\package_portable.py --version 1.0.0` |

### 2-5. 절대 규칙 (SAC 호환)

| 규칙 | 이유 |
|---|---|
| `pip`로 `.pyd`/`.dll` 포함 패키지 설치 금지. 외부 패키지는 순수 `.py`만, `studypet.zip`에 동봉 | 서명 없는 PE는 SAC가 차단 |
| `PyInstaller`/`Nuitka`/`cx_Freeze`/`rcedit` 금지, 런타임 바이너리 수정 금지 | 서명 파괴 |
| 런타임 경로(렌더 루프·틱)에서 **픽셀 단위 Python 루프 금지**. 허용: 로드 시 1회 사전 처리, 행 단위 `memmove`/슬라이스, 스텝 슬라이스(`row[3::4] = ...`) | 프레임당 수십 ms → CPU 2% 초과 |
| 모든 ctypes 함수에 `argtypes`/`restype` 명시, DLL은 `ctypes.WinDLL(name, use_last_error=True)`로 모듈 전용 로드(`windll` 공유 객체 사용 금지) | 64-bit 핸들 절단(`0xC0000005`), 다른 모듈과 argtypes 충돌 |
| `WNDPROC` 등 콜백 객체는 모듈/인스턴스 수준에 보관 | GC 시 크래시 |
| WndProc 본문은 반드시 `try/except Exception` → 로그 기록 후 `DefWindowProcW` 반환 | 콜백 예외는 `stderr=None`이라 조용히 사라짐 |

---

## 3. 아키텍처

### 3-1. 계층과 의존 규칙

```
studypet/
 ├─ domain/      순수 Python. Win32·sqlite3 import 금지. Clock·Repository 프로토콜에만 의존
 │   ├─ clock.py        Clock 프로토콜, FakeClock(테스트)
 │   ├─ timer_engine.py TimerEngine (상태·크레딧·자정 분할·AFK·복구)
 │   ├─ credit_log.py   CreditTimeline (AFK 롤백용 크레딧 이력)
 │   ├─ pet_fsm.py      PetFSM
 │   ├─ physics.py      PetPhysics
 │   ├─ stats.py        기간 계산·달성률 (순수 함수)
 │   └─ events.py       엔진 → UI 이벤트 dataclass
 ├─ infra/       OS·파일·DB 어댑터
 │   ├─ paths.py        PortablePaths, 쓰기 검사, UAC 권한 부여
 │   ├─ config.py       AppConfig 로드/검증/원자적 저장
 │   ├─ db.py           Database, SessionRepository, SubjectRepository, StatsRepository
 │   ├─ csv_export.py   CSV 내보내기
 │   ├─ real_clock.py   QueryUnbiasedInterruptTime 기반 Clock
 │   └─ logging_setup.py
 ├─ win32/       ctypes 바인딩 (UI 로직 없음)
 │   ├─ api.py          DLL·구조체·상수·함수 원형 (4-2)
 │   ├─ monitors.py     DPI 인식, 모니터·작업 영역·DPI 조회
 │   ├─ idle.py         GetLastInputInfo
 │   ├─ audio.py        PlaySoundW 메모리 비동기 재생 + 볼륨
 │   ├─ tray.py         Shell_NotifyIconW
 │   ├─ hotkey.py       RegisterHotKey 파싱/등록
 │   └─ actctx.py       comctl32 v6 활성화 컨텍스트
 ├─ graphics/
 │   ├─ png_codec.py    PNG(RGBA8) 인코드/디코드, ICO 인코드
 │   ├─ sprites.py      SpriteSheet, 사전 스케일 프레임 캐시
 │   ├─ dib.py          DibSurface (CreateDIBSection 래퍼, 행 복사)
 │   ├─ panel.py        9-slice 패널 사전 합성
 │   ├─ text.py         GDI 픽셀 폰트 텍스트 + 알파 복원
 │   └─ compositor.py   펫 캔버스 레이어 합성 (Dirty Rect)
 ├─ ui/
 │   ├─ pet_window.py   펫 창 (메시지·입력·렌더 타이머·트레이·핫키·전원·잠금)
 │   ├─ layout.py       캔버스 좌표 상수, 메뉴/패널 히트 영역
 │   ├─ modals.py       메모·AFK 복귀·크래시 복구·안내 창
 │   ├─ dashboard.py    대시보드 프레임 + 탭
 │   ├─ tab_subjects.py / tab_settings.py / tab_stats.py
 │   └─ chart.py        GDI 막대 차트 컨트롤
 ├─ app.py       AppController: 기동 순서, 이벤트 배선, 메시지 루프, 종료 정리
 ├─ crashlog.py
 └─ __main__.py
```

- `domain`은 `infra`/`win32`/`ui`를 import하지 않는다 → 전부 `unittest`로 검증.
- 모든 UI·엔진 호출은 **메인 스레드 하나**에서만 일어난다(Win32 메시지 루프). 스레드를 만들지 않는다.

### 3-2. 메인 루프와 타이머

펫 창 하나가 앱의 메시지 허브다(트레이 콜백, `WM_HOTKEY`, `WM_POWERBROADCAST`, `WM_WTSSESSION_CHANGE`, `TaskbarCreated` 브로드캐스트를 모두 받는다. 메시지 전용 창(`HWND_MESSAGE`)은 브로드캐스트를 못 받으므로 쓰지 않는다).

| 타이머 ID | 주기 | 처리 |
|---|---|---|
| `TID_FRAME = 1` | 이동 중(Walk/Drag/Fall/Celebrate): `1000 // render.fps` ms / 그 외: 현재 애니메이션 프레임 간격 | FSM·물리 갱신, 애니메이션 프레임 진행, 변경 시 렌더 |
| `TID_ENGINE = 2` | 250 ms | `engine.tick()` |
| `TID_IDLE = 3` | 1000 ms | `engine.on_idle_poll(idle_ms)` (항상 1초. 비용 무시 가능) |
| `TID_UI = 4` | 100 ms | 액션 카드 바깥 클릭·8초 미사용 닫기, 힌트·토스트 만료, 유령 모드 Alt+호버 |
| `TID_TOPMOST = 5` | 5000 ms | `SetWindowPos(HWND_TOPMOST, NOMOVE|NOSIZE|NOACTIVATE)` |
| `TID_SAVE_CFG = 6` | 1000 ms (1회성) | 드래그·과목·모드·힌트 변경 시 `config.save()` 1초 디바운스 |

메시지 루프:
```python
msg = MSG()
while True:
    r = user32.GetMessageW(byref(msg), None, 0, 0)
    if r == 0: break            # WM_QUIT
    if r == -1: log_error(); break
    if not dialogs.try_dispatch(msg):   # 열린 모달/대시보드에 대해 IsDialogMessageW
        user32.TranslateMessage(byref(msg)); user32.DispatchMessageW(byref(msg))
```

### 3-3. 기동 순서 (`AppController.run()`) — Cold Start ≤ 1.5s

1. `monitors.enable_per_monitor_dpi()` — 창 생성 전 필수
2. 단일 인스턴스 뮤텍스 `Local\StudyPet_Singleton`. `ERROR_ALREADY_EXISTS(183)`면 `FindWindowW("StudyPetPet", None)`에 `WM_APP_SUMMON` Post 후 `return 0`
3. `PortablePaths.resolve()` → `ensure_data_writable()` (실패 시 `return 2`)
4. 로깅 설정 (`data/logs/studypet.log`, 1MB × 3 회전)
5. `AppConfig.load()`
6. `Database.open()` + 마이그레이션 + `ensure_default_subject()`
7. 스킨 메타 로드 + **Idle 프레임만** 사전 스케일 (나머지는 상태 최초 진입 시 지연 생성)
8. 펫 창 생성 → 첫 `UpdateLayeredWindow` → `perf.log`에 `cold_start_ms` 기록 (`GetProcessTimes` 생성 시각 ~ 현재)
9. 트레이 등록, 핫키 등록, `WTSRegisterSessionNotification`, 타이머 시작
10. `PostMessageW(WM_APP_POST_START)` → 다음 루프에서 크래시 복구 확인(미완료 세션 → 복구 모달), 효과음 버퍼 생성, 폰트 로드
11. 메시지 루프 → 종료 정리(3-4) → 반환

### 3-4. 종료 정리 (`AppController.shutdown()`)

순서 고정: 엔진 상태 확인(RUNNING/PAUSED/PAUSED_AFK면 체크포인트만 저장, 세션은 미완료로 남겨 다음 실행 때 복구 모달) → 설정 저장(위치 포함) → `PlaySoundW(None, None, 0)` → 핫키 해제 → WTS 해제 → 트레이 `NIM_DELETE` → 창 파괴 → `db.close()`(`wal_checkpoint(TRUNCATE)`) → 뮤텍스 `CloseHandle` → 반환.

> 트레이 메뉴 [완전 종료]는 타이머가 돌고 있으면 "세션을 종료하고 저장할까요? [저장 후 종료] [기록 유지하고 종료] [취소]"를 묻는다. [저장 후 종료]는 메모 모달을 거쳐 `finalize` 후 종료한다.

---

## 4. 모듈별 상세 명세

### 4-1. `infra/paths.py`

```python
@dataclass(frozen=True)
class PortablePaths:
    root_dir: Path       # 배포: StudyPet.exe 폴더 / 개발: 프로젝트 루트
    data_dir: Path       # 배포: root/data       / 개발: root/data-dev
    assets_dir: Path     # root/assets
    db_path: Path        # data/study_records.db
    config_path: Path    # data/config.json
    exports_dir: Path    # data/exports
    logs_dir: Path       # data/logs
    is_dev: bool

    @staticmethod
    def resolve() -> "PortablePaths":
        exe_dir = Path(sys.executable).resolve().parent
        marker = exe_dir / "studypet_dev_root.txt"
        if marker.exists():
            root = (exe_dir / marker.read_text("utf-8").strip()).resolve(); data = root / "data-dev"; dev = True
        else:
            root = exe_dir; data = root / "data"; dev = False
        ...
```

`ensure_data_writable(paths) -> bool`:
1. `data_dir.mkdir(parents=True, exist_ok=True)` → `.write_test` 쓰기·삭제. 성공 시 `exports/`, `logs/` 생성 후 `True`.
2. `OSError` 시 `MessageBoxW(None, 안내문, "StudyPet", MB_YESNO|MB_ICONWARNING|MB_TOPMOST)`.
   - 안내문: `"이 폴더에 학습 기록을 저장할 권한이 없습니다.\n{root}\n\n관리자 승인으로 data 폴더에 쓰기 권한을 부여할까요?\n(아니요: 종료 — 바탕화면·문서·USB 등으로 폴더를 옮겨 실행하세요)"`
3. `IDYES(6)`면 `grant_data_acl(data_dir)` → 다시 1번 검사. 그래도 실패하면 이동 안내 `MB_OK` 후 `False`.

`grant_data_acl(data_dir) -> bool` (PowerShell을 거치지 않는다 — v0.5 따옴표 3중 해석 문제 제거):
```python
def grant_data_acl(data_dir: Path) -> bool:
    target = str(data_dir).rstrip("\\/")
    if any(c in target for c in '"%'):          # cmd가 따옴표 안에서도 해석하는 문자
        return False
    sysdir = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
    params = (f'/d /c mkdir "{target}" 2>nul & '
              f'"{sysdir / "icacls.exe"}" "{target}" /grant *S-1-5-32-545:(OI)(CI)M /T /Q')
    sei = SHELLEXECUTEINFOW()
    sei.cbSize = ctypes.sizeof(sei)
    sei.fMask = SEE_MASK_NOCLOSEPROCESS | SEE_MASK_NO_CONSOLE
    sei.lpVerb = "runas"; sei.lpFile = str(sysdir / "cmd.exe"); sei.lpParameters = params; sei.nShow = SW_HIDE
    if not shell32.ShellExecuteExW(byref(sei)):
        return False                             # get_last_error()==1223(ERROR_CANCELLED): UAC 거부
    kernel32.WaitForSingleObject(sei.hProcess, INFINITE)
    kernel32.CloseHandle(sei.hProcess)
    return True
```
- `/c` 뒤 첫 글자가 따옴표가 아니므로 cmd의 앞뒤 따옴표 제거 규칙이 적용되지 않는다. 경로 안의 `&`, `'`, `(`, 공백, 한글은 따옴표로 보호된다.
- Built-in Users(`S-1-5-32-545`)를 쓰는 이유: 표준 사용자가 관리자 자격 증명으로 승인하면 승격 프로세스의 사용자는 관리자 계정이 된다. 권한 범위는 `data/`로 한정(실행 코드가 있는 루트는 건드리지 않음).

### 4-2. `win32/api.py` — 바인딩 명세

DLL 로드: `user32 = ctypes.WinDLL("user32", use_last_error=True)` (gdi32, kernel32, shell32, shcore, wtsapi32, winmm, comdlg32, comctl32 동일). 공통 타입:

```python
from ctypes import wintypes as wt
LRESULT = ctypes.c_ssize_t; WPARAM = ctypes.c_size_t; LPARAM = ctypes.c_ssize_t
LONG_PTR = ctypes.c_ssize_t; UINT_PTR = ctypes.c_size_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, WPARAM, LPARAM)
HWND_TOPMOST = wt.HWND(-1)
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)
```

구조체 (필드 순서 그대로):

| 구조체 | 필드 |
|---|---|
| `POINT`, `SIZE`, `RECT`, `MSG` | `wintypes` 제공분 사용 (`wt.POINT`, `wt.SIZE`, `wt.RECT`, `wt.MSG`) |
| `WNDCLASSEXW` | `cbSize UINT, style UINT, lpfnWndProc WNDPROC, cbClsExtra c_int, cbWndExtra c_int, hInstance HINSTANCE, hIcon HICON, hCursor HANDLE, hbrBackground HBRUSH, lpszMenuName LPCWSTR, lpszClassName LPCWSTR, hIconSm HICON` |
| `BLENDFUNCTION` | `BlendOp c_ubyte, BlendFlags c_ubyte, SourceConstantAlpha c_ubyte, AlphaFormat c_ubyte` |
| `BITMAPINFOHEADER` | `biSize DWORD, biWidth LONG, biHeight LONG, biPlanes WORD, biBitCount WORD, biCompression DWORD, biSizeImage DWORD, biXPelsPerMeter LONG, biYPelsPerMeter LONG, biClrUsed DWORD, biClrImportant DWORD` |
| `BITMAPINFO` | `bmiHeader BITMAPINFOHEADER, bmiColors DWORD * 1` |
| `MONITORINFO` | `cbSize DWORD, rcMonitor RECT, rcWork RECT, dwFlags DWORD` |
| `LASTINPUTINFO` | `cbSize UINT, dwTime DWORD` |
| `NOTIFYICONDATAW` | `cbSize DWORD, hWnd HWND, uID UINT, uFlags UINT, uCallbackMessage UINT, hIcon HICON, szTip WCHAR*128, dwState DWORD, dwStateMask DWORD, szInfo WCHAR*256, uVersion UINT, szInfoTitle WCHAR*64, dwInfoFlags DWORD, guidItem GUID(16바이트 c_ubyte*16), hBalloonIcon HICON` |
| `SHELLEXECUTEINFOW` | `cbSize DWORD, fMask ULONG, hwnd HWND, lpVerb LPCWSTR, lpFile LPCWSTR, lpParameters LPCWSTR, lpDirectory LPCWSTR, nShow c_int, hInstApp HINSTANCE, lpIDList c_void_p, lpClass LPCWSTR, hkeyClass HKEY, dwHotKey DWORD, hIconOrMonitor HANDLE, hProcess HANDLE` |
| `OPENFILENAMEW` | `lStructSize DWORD, hwndOwner HWND, hInstance HINSTANCE, lpstrFilter LPCWSTR, lpstrCustomFilter LPWSTR, nMaxCustFilter DWORD, nFilterIndex DWORD, lpstrFile LPWSTR, nMaxFile DWORD, lpstrFileTitle LPWSTR, nMaxFileTitle DWORD, lpstrInitialDir LPCWSTR, lpstrTitle LPCWSTR, Flags DWORD, nFileOffset WORD, nFileExtension WORD, lpstrDefExt LPCWSTR, lCustData LPARAM, lpfnHook c_void_p, lpTemplateName LPCWSTR, pvReserved c_void_p, dwReserved DWORD, FlagsEx DWORD` |
| `CHOOSECOLORW` | `lStructSize DWORD, hwndOwner HWND, hInstance HWND, rgbResult DWORD, lpCustColors POINTER(DWORD), Flags DWORD, lCustData LPARAM, lpfnHook c_void_p, lpTemplateName LPCWSTR` |
| `ACTCTXW` | `cbSize ULONG, dwFlags DWORD, lpSource LPCWSTR, wProcessorArchitecture USHORT, wLangId USHORT, lpAssemblyDirectory LPCWSTR, lpResourceName LPCWSTR, lpApplicationName LPCWSTR, hModule HMODULE` |
| `INITCOMMONCONTROLSEX` | `dwSize DWORD, dwICC DWORD` |
| `FILETIME` | `wt.FILETIME` |

함수 원형 (`restype` ← `argtypes`):

| DLL | 함수 | restype | argtypes |
|---|---|---|---|
| user32 | `RegisterClassExW` | `ATOM(WORD)` | `POINTER(WNDCLASSEXW)` |
| | `CreateWindowExW` | `HWND` | `DWORD, LPCWSTR, LPCWSTR, DWORD, c_int, c_int, c_int, c_int, HWND, HMENU, HINSTANCE, LPVOID` |
| | `DefWindowProcW` | `LRESULT` | `HWND, UINT, WPARAM, LPARAM` |
| | `DestroyWindow` / `ShowWindow` / `UpdateWindow` | `BOOL` | `HWND` / `HWND, c_int` / `HWND` |
| | `GetMessageW` | `BOOL` | `POINTER(MSG), HWND, UINT, UINT` |
| | `TranslateMessage` / `DispatchMessageW` | `BOOL` / `LRESULT` | `POINTER(MSG)` |
| | `IsDialogMessageW` | `BOOL` | `HWND, POINTER(MSG)` |
| | `PostMessageW` / `SendMessageW` | `BOOL` / `LRESULT` | `HWND, UINT, WPARAM, LPARAM` |
| | `PostQuitMessage` | `None` | `c_int` |
| | `SetTimer` / `KillTimer` | `UINT_PTR` / `BOOL` | `HWND, UINT_PTR, UINT, c_void_p` / `HWND, UINT_PTR` |
| | `UpdateLayeredWindow` | `BOOL` | `HWND, HDC, POINTER(POINT), POINTER(SIZE), HDC, POINTER(POINT), COLORREF(DWORD), POINTER(BLENDFUNCTION), DWORD` |
| | `SetWindowPos` | `BOOL` | `HWND, HWND, c_int, c_int, c_int, c_int, UINT` |
| | `GetWindowLongPtrW` / `SetWindowLongPtrW` | `LONG_PTR` | `HWND, c_int` / `HWND, c_int, LONG_PTR` |
| | `GetCursorPos` | `BOOL` | `POINTER(POINT)` |
| | `SetCapture` / `ReleaseCapture` / `GetCapture` | `HWND` / `BOOL` / `HWND` | `HWND` / — / — |
| | `GetAsyncKeyState` / `GetKeyState` | `SHORT` | `c_int` |
| | `MonitorFromPoint` | `HMONITOR` | `POINT`(값 전달), `DWORD` |
| | `GetMonitorInfoW` | `BOOL` | `HMONITOR, POINTER(MONITORINFO)` |
| | `EnumDisplayMonitors` | `BOOL` | `HDC, POINTER(RECT), MONITORENUMPROC, LPARAM` (`MONITORENUMPROC = WINFUNCTYPE(BOOL, HMONITOR, HDC, POINTER(RECT), LPARAM)`) |
| | `SetProcessDpiAwarenessContext` | `BOOL` | `c_void_p` |
| | `GetLastInputInfo` | `BOOL` | `POINTER(LASTINPUTINFO)` |
| | `RegisterHotKey` / `UnregisterHotKey` | `BOOL` | `HWND, c_int, UINT, UINT` / `HWND, c_int` |
| | `MessageBoxW` | `c_int` | `HWND, LPCWSTR, LPCWSTR, UINT` |
| | `LoadImageW` / `LoadCursorW` / `DestroyIcon` | `HANDLE` / `HANDLE` / `BOOL` | `HINSTANCE, LPCWSTR, UINT, c_int, c_int, UINT` / `HINSTANCE, c_void_p` / `HICON` |
| | `CreatePopupMenu` / `AppendMenuW` / `TrackPopupMenu` / `DestroyMenu` | `HMENU` / `BOOL` / `BOOL`(TPM_RETURNCMD 시 명령 ID) / `BOOL` | — / `HMENU, UINT, UINT_PTR, LPCWSTR` / `HMENU, UINT, c_int, c_int, c_int, HWND, c_void_p` / `HMENU` |
| | `SetForegroundWindow` / `FindWindowW` / `RegisterWindowMessageW` | `BOOL` / `HWND` / `UINT` | `HWND` / `LPCWSTR, LPCWSTR` / `LPCWSTR` |
| | `GetDC` / `ReleaseDC` | `HDC` / `c_int` | `HWND` / `HWND, HDC` |
| | `FillRect` / `InvalidateRect` / `BeginPaint` / `EndPaint` | 표준 | 표준 |
| gdi32 | `CreateCompatibleDC` / `DeleteDC` | `HDC` / `BOOL` | `HDC` |
| | `CreateDIBSection` | `HBITMAP` | `HDC, POINTER(BITMAPINFO), UINT, POINTER(c_void_p), HANDLE, DWORD` |
| | `SelectObject` / `DeleteObject` | `HGDIOBJ` / `BOOL` | `HDC, HGDIOBJ` / `HGDIOBJ` |
| | `CreateFontW` | `HFONT` | `c_int×5, DWORD×8, LPCWSTR` (height, width, escapement, orientation, weight, italic, underline, strikeout, charset, outprecision, clipprecision, quality, pitchandfamily, facename) |
| | `TextOutW` / `GetTextExtentPoint32W` | `BOOL` | `HDC, c_int, c_int, LPCWSTR, c_int` / `HDC, LPCWSTR, c_int, POINTER(SIZE)` |
| | `SetBkMode` / `SetTextColor` | `c_int` / `COLORREF` | `HDC, c_int` / `HDC, COLORREF` |
| | `AddFontResourceExW` / `RemoveFontResourceExW` | `c_int` / `BOOL` | `LPCWSTR, DWORD, c_void_p` |
| | `GdiFlush` | `BOOL` | — |
| kernel32 | `CreateMutexW` / `CloseHandle` | `HANDLE` / `BOOL` | `c_void_p, BOOL, LPCWSTR` / `HANDLE` |
| | `QueryUnbiasedInterruptTime` | `BOOL` | `POINTER(c_ulonglong)` |
| | `GetTickCount` | `DWORD` | — |
| | `WaitForSingleObject` | `DWORD` | `HANDLE, DWORD` |
| | `GetModuleHandleW` | `HMODULE` | `LPCWSTR` |
| | `GetCurrentProcess` / `GetProcessTimes` / `GetSystemTimeAsFileTime` | `HANDLE` / `BOOL` / `None` | — / `HANDLE, 4×POINTER(FILETIME)` / `POINTER(FILETIME)` |
| | `CreateActCtxW` / `ActivateActCtx` / `DeactivateActCtx` | `HANDLE`(실패 시 `INVALID_HANDLE_VALUE`) / `BOOL` / `BOOL` | `POINTER(ACTCTXW)` / `HANDLE, POINTER(ULONG_PTR)` / `DWORD, ULONG_PTR` |
| shell32 | `Shell_NotifyIconW` / `ShellExecuteExW` | `BOOL` | `DWORD, POINTER(NOTIFYICONDATAW)` / `POINTER(SHELLEXECUTEINFOW)` |
| shcore | `GetDpiForMonitor` | `HRESULT(c_long)` | `HMONITOR, c_int, POINTER(UINT), POINTER(UINT)` |
| wtsapi32 | `WTSRegisterSessionNotification` / `WTSUnRegisterSessionNotification` | `BOOL` | `HWND, DWORD` / `HWND` |
| winmm | `PlaySoundW` | `BOOL` | `c_void_p, HMODULE, DWORD` |
| comdlg32 | `GetSaveFileNameW` / `ChooseColorW` | `BOOL` | `POINTER(OPENFILENAMEW)` / `POINTER(CHOOSECOLORW)` |
| comctl32 | `InitCommonControlsEx` | `BOOL` | `POINTER(INITCOMMONCONTROLSEX)` |

상수:

| 분류 | 값 |
|---|---|
| 창 스타일 | `WS_POPUP=0x80000000, WS_CAPTION=0x00C00000, WS_SYSMENU=0x00080000, WS_CHILD=0x40000000, WS_VISIBLE=0x10000000, WS_TABSTOP=0x00010000, WS_BORDER=0x00800000, WS_MINIMIZEBOX=0x00020000` |
| 확장 스타일 | `WS_EX_LAYERED=0x80000, WS_EX_TRANSPARENT=0x20, WS_EX_TOPMOST=0x8, WS_EX_TOOLWINDOW=0x80, WS_EX_NOACTIVATE=0x08000000, WS_EX_DLGMODALFRAME=0x1` |
| 메시지 | `WM_NULL=0, WM_DESTROY=0x2, WM_CLOSE=0x10, WM_SETTINGCHANGE=0x1A, WM_MOUSEACTIVATE=0x21, WM_SETFONT=0x30, WM_NOTIFY=0x4E, WM_DISPLAYCHANGE=0x7E, WM_COMMAND=0x111, WM_TIMER=0x113, WM_MOUSEMOVE=0x200, WM_LBUTTONDOWN=0x201, WM_LBUTTONUP=0x202, WM_RBUTTONUP=0x205, WM_MOUSEWHEEL=0x20A, WM_CAPTURECHANGED=0x215, WM_POWERBROADCAST=0x218, WM_WTSSESSION_CHANGE=0x2B1, WM_DPICHANGED=0x2E0, WM_HOTKEY=0x312, WM_APP=0x8000` |
| 앱 메시지 | `WM_APP_TRAY=WM_APP+1, WM_APP_SUMMON=WM_APP+2, WM_APP_POST_START=WM_APP+3` |
| 기타 | `GWL_EXSTYLE=-20, MA_NOACTIVATE=3, SW_HIDE=0, SW_SHOWNOACTIVATE=4, SW_SHOW=5, SWP_NOSIZE=0x1, SWP_NOMOVE=0x2, SWP_NOZORDER=0x4, SWP_NOACTIVATE=0x10, SWP_SHOWWINDOW=0x40, MONITOR_DEFAULTTOPRIMARY=1, MONITOR_DEFAULTTONEAREST=2, MDT_EFFECTIVE_DPI=0, ULW_ALPHA=2, AC_SRC_OVER=0, AC_SRC_ALPHA=1, BI_RGB=0, DIB_RGB_COLORS=0, NONANTIALIASED_QUALITY=3, TRANSPARENT=1, FR_PRIVATE=0x10, VK_LBUTTON=1, VK_RBUTTON=2, VK_MENU=0x12, MOD_ALT=1, MOD_CONTROL=2, MOD_SHIFT=4, MOD_NOREPEAT=0x4000, NIM_ADD=0, NIM_MODIFY=1, NIM_DELETE=2, NIF_MESSAGE=1, NIF_ICON=2, NIF_TIP=4, TPM_RIGHTBUTTON=0x2, TPM_NONOTIFY=0x80, TPM_RETURNCMD=0x100, MF_STRING=0, MF_SEPARATOR=0x800, MF_CHECKED=0x8, PBT_APMSUSPEND=4, PBT_APMRESUMESUSPEND=7, PBT_APMRESUMEAUTOMATIC=0x12, WTS_SESSION_LOCK=7, WTS_SESSION_UNLOCK=8, NOTIFY_FOR_THIS_SESSION=0, SEE_MASK_NOCLOSEPROCESS=0x40, SEE_MASK_NO_CONSOLE=0x8000, INFINITE=0xFFFFFFFF, ERROR_ALREADY_EXISTS=183, ERROR_CANCELLED=1223, MB_OK=0, MB_YESNO=4, MB_ICONERROR=0x10, MB_ICONWARNING=0x30, MB_TOPMOST=0x40000, IDYES=6, IDOK=1, IDCANCEL=2, IMAGE_ICON=1, LR_LOADFROMFILE=0x10, IDC_ARROW=32512, SND_ASYNC=0x1, SND_NODEFAULT=0x2, SND_MEMORY=0x4, ICC_LISTVIEW_CLASSES=0x1, ICC_BAR_CLASSES=0x4, ICC_TAB_CLASSES=0x8, ICC_HOTKEY_CLASS=0x40, ICC_STANDARD_CLASSES=0x4000` |

### 4-3. `win32/monitors.py`

```python
def enable_per_monitor_dpi() -> None:
    if not user32.SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2):
        try: shcore.SetProcessDpiAwareness(2)      # Win8.1 API 폴백 (PROCESS_PER_MONITOR_DPI_AWARE)
        except OSError: pass

@dataclass(frozen=True)
class MonitorInfo:
    handle: int; monitor: Rect; work: Rect; dpi: int; is_primary: bool

def list_monitors() -> list[MonitorInfo]
def monitor_at(x: int, y: int) -> MonitorInfo          # MonitorFromPoint(..., NEAREST)
def primary() -> MonitorInfo
def phys_scale(config_scale: int, dpi: int) -> int:
    return max(1, int(config_scale * dpi / 96 + 0.5))   # 반올림(Python round의 은행가 반올림 금지)
```
- 모든 좌표는 **물리 픽셀, 가상 데스크톱 기준**(PMv2이므로 API 값 그대로).
- 캐시: `WM_DISPLAYCHANGE`, `WM_SETTINGCHANGE`(작업 표시줄 이동), `WM_DPICHANGED` 수신 시 무효화.
- `WM_DPICHANGED`는 **창 면적 기준**이라 캐릭터 위치와 어긋날 수 있으므로, 권장 사각형은 무시하고 `0`을 반환한다. 배율은 항상 **캐릭터 발 위치의 모니터 DPI**로 계산한다.

### 4-4. 시계: `domain/clock.py`, `infra/real_clock.py`

```python
class Clock(Protocol):
    def mono_ns(self) -> int: ...              # 절전 시간을 포함하지 않는 단조 시계
    def now_local(self) -> datetime: ...       # tz-aware 로컬 시각 (datetime.now().astimezone())

class RealClock:
    def mono_ns(self) -> int:
        t = ctypes.c_ulonglong(); kernel32.QueryUnbiasedInterruptTime(byref(t)); return t.value * 100
    def now_local(self) -> datetime:
        return datetime.now().astimezone()
```
- `time.monotonic_ns()`는 쓰지 않는다. Python 3.12/Windows에서는 `GetTickCount64` 기반이라 **절전 중에도 증가**해서 깨어난 직후 틱 하나에 절전 시간 전체가 학습 시간으로 들어간다(v0.5 H1). `QueryUnbiasedInterruptTime`은 절전·최대 절전 시간을 제외한다.
- 안전장치: 엔진은 틱 간격이 `MAX_TICK_GAP_NS = 5초`를 넘으면 그 간격을 0으로 처리하고 로그를 남긴다(프로세스 정지·디버거 등).
- 시각 문자열은 한 함수로만 만든다: `iso(dt) = dt.isoformat(timespec="seconds")` → `2026-11-03T21:15:00+09:00`. 날짜 키는 `dt.date().isoformat()`.

### 4-5. `infra/db.py` — 스키마 v1

연결: `sqlite3.connect(path, isolation_level=None, check_same_thread=True)` (자동 커밋 모드). 쓰기는 `with db.tx():`(`BEGIN IMMEDIATE` … `COMMIT`/`ROLLBACK`)로만 한다.

```sql
PRAGMA journal_mode = WAL;        -- 반환값이 'wal'이 아니면(네트워크 드라이브 등) 로그 경고 후 계속
PRAGMA synchronous = NORMAL;      -- 프로세스 강제 종료(AC#3)에는 안전. 전원 차단 시 마지막 커밋 유실 가능
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 3000;

-- user_version 0 → 1
CREATE TABLE subjects (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    name               TEXT    NOT NULL CHECK(length(trim(name)) BETWEEN 1 AND 40),
    color_code         TEXT    NOT NULL DEFAULT '#4F46E5' CHECK(color_code GLOB '#[0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f]'),
    daily_goal_minutes INTEGER NOT NULL DEFAULT 60 CHECK(daily_goal_minutes BETWEEN 1 AND 1440),
    is_archived        INTEGER NOT NULL DEFAULT 0 CHECK(is_archived IN (0,1)),
    sort_order         INTEGER NOT NULL DEFAULT 0,
    created_at         TEXT    NOT NULL
);

CREATE TABLE study_sessions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id       INTEGER NOT NULL REFERENCES subjects(id),
    mode             TEXT    NOT NULL CHECK(mode IN ('STOPWATCH','POMODORO')),
    start_time       TEXT    NOT NULL,              -- iso() 형식
    end_time         TEXT    NOT NULL,              -- 생성 시 start_time과 같은 값 (v0.5 C3 수정)
    local_date       TEXT    NOT NULL,              -- 'YYYY-MM-DD' 로컬 날짜 = 집계 키
    duration_seconds INTEGER NOT NULL DEFAULT 0 CHECK(duration_seconds >= 0),
    memo             TEXT    NOT NULL DEFAULT '',
    is_completed     INTEGER NOT NULL DEFAULT 0 CHECK(is_completed IN (0,1)),
    chain_id         INTEGER NOT NULL DEFAULT 0,    -- 같은 학습 세션의 첫 행 id
    segment_no       INTEGER NOT NULL DEFAULT 1     -- 자정 분할 순번
);
CREATE INDEX idx_sessions_local_date   ON study_sessions(local_date);
CREATE INDEX idx_sessions_subject_date ON study_sessions(subject_id, local_date);
CREATE INDEX idx_sessions_chain        ON study_sessions(chain_id);
CREATE INDEX idx_sessions_open         ON study_sessions(is_completed) WHERE is_completed = 0;
PRAGMA user_version = 1;
```

- PRD 6-2 대비 추가 열: `local_date`, `chain_id`, `segment_no`, `subjects.sort_order` (9장 PRD 개정).
- 마이그레이션: `MIGRATIONS: list[Callable[[Connection], None]]`, `user_version`보다 큰 인덱스만 순서대로 한 트랜잭션에서 실행. 마이그레이션 전 `study_records.db`를 `study_records.db.v{n}.bak`으로 복사.
- 집계에 `local_date`를 쓰는 이유: UTC 오프셋이 다른 문자열(서머타임 국가, PC 시간대 변경)을 섞어 문자열 비교하면 순서가 깨진다(v0.5 H6).

`SessionRepository` (모두 `with tx()` 내부):

| 메서드 | SQL 요지 |
|---|---|
| `create_chain(subject_id, mode, start_iso, local_date) -> SegmentRow` | `INSERT (..., end_time=start_iso, chain_id=0, segment_no=1)` → `UPDATE SET chain_id=id WHERE id=?` |
| `create_next_segment(prev: SegmentRow, start_iso, local_date) -> SegmentRow` | `INSERT (subject_id, mode 동일, chain_id=prev.chain_id, segment_no=prev.segment_no+1, end_time=start_iso)` |
| `checkpoint(seg_id, end_iso, duration_s)` | `UPDATE SET end_time=?, duration_seconds=? WHERE id=? AND is_completed=0` |
| `complete_segment(seg_id, end_iso, duration_s)` | `UPDATE SET end_time=?, duration_seconds=?, is_completed=1 WHERE id=?` |
| `add_duration(seg_id, delta_s)` | `UPDATE SET duration_seconds = MAX(0, duration_seconds + ?) WHERE id=?` |
| `finalize_chain(chain_id, seg_id, end_iso, duration_s, memo)` | `complete_segment(...)` + `UPDATE SET memo=? WHERE chain_id=?` |
| `delete_segment(seg_id)` | `DELETE WHERE id=? AND is_completed=0` |
| `get_open_segments() -> list[SegmentRow]` | `WHERE is_completed=0 ORDER BY id` (JOIN subjects로 과목명) |
| `chain_completed_seconds(chain_id) -> int` | `SUM(duration_seconds) WHERE chain_id=? AND is_completed=1` |

`SubjectRepository`: `list(include_archived: bool)`, `create(name, color, goal)`, `update(id, name, color, goal)`, `set_archived(id, flag)`, `ensure_default_subject() -> int` (비어 있으면 `"자유 학습"`, `#4F46E5`, 60분), `exists_active(id)`. 삭제 기능은 두지 않는다(아카이브만).

`StatsRepository.period_totals(from_date, to_date) -> list[SubjectTotal]`:
```sql
SELECT sub.id, sub.name, sub.color_code, sub.daily_goal_minutes, sub.is_archived,
       COALESCE(SUM(s.duration_seconds), 0) AS total_seconds
FROM subjects sub
LEFT JOIN study_sessions s
       ON s.subject_id = sub.id AND s.is_completed = 1
      AND s.local_date BETWEEN :from_date AND :to_date
GROUP BY sub.id
HAVING sub.is_archived = 0 OR total_seconds > 0
ORDER BY total_seconds DESC, sub.sort_order, sub.id;
```
`Database.close()`: `PRAGMA wal_checkpoint(TRUNCATE)` → `close()`.

### 4-6. `infra/config.py`

전체 스키마와 검증 규칙(로드 시 기본값과 깊은 병합 → 필드별 검증, 범위를 벗어나면 기본값으로 대체하고 로그):

```json
{
  "version": 1,
  "character": { "skin_id": "default_pixel_cat", "scale": 2, "opacity": 1.0,
                 "last_position": null, "walk_enabled": true },
  "timer": { "default_mode": "POMODORO", "pomodoro_focus_min": 25, "pomodoro_break_min": 5,
             "afk_timeout_min": 10, "sound_alert": true, "last_subject_id": null },
  "audio": { "volume": 0.7 },
  "render": { "fps": 30 },
  "hud": { "bubble_collapsed": false },
  "shortcuts": { "toggle_ghost": "Ctrl+Alt+G" }
}
```

| 필드 | 타입·범위 | 비고 |
|---|---|---|
| `character.scale` | int 1~4 | PRD의 `2.0`(실수)은 `int(round)`로 정규화 |
| `character.opacity` | float 0.3~1.0 | 유령 모드와 별개(평상시 투명도) |
| `character.last_position` | `null` 또는 `{"x": int, "y": int}` | **캐릭터 발 위치**, 물리 픽셀·가상 데스크톱 좌표 |
| `timer.default_mode` | `"STOPWATCH"`/`"POMODORO"` | |
| `timer.pomodoro_focus_min` / `break_min` | int 1~180 / 1~60 | |
| `timer.afk_timeout_min` | int 1~120 | |
| `timer.last_subject_id` | int 또는 null | 없거나 보관된 과목이면 첫 활성 과목 |
| `audio.volume` | float 0.0~1.0 | |
| `render.fps` | 30 또는 60 | |
| `shortcuts.toggle_ghost` | `"Ctrl+Alt+G"` 형식 | 파싱 실패 시 기본값 |

- 파싱 실패: 원본을 `config.json.bak`으로 복사 → 기본값으로 다시 저장.
- 저장: `config.json.tmp`에 쓰기 → `flush()` → `os.fsync()` → `os.replace()`. 위치는 드래그 종료·종료 시에만 저장(이동 중 저장 금지).
- `AppConfig`는 `dataclass` 트리로 표현하고 `to_dict()`/`from_dict()`를 둔다.

### 4-7. `domain/timer_engine.py` — 타이머 엔진 (핵심)

#### 상태·상수

```python
NS = 1_000_000_000
MAX_TICK_GAP_NS = 5 * NS
CHECKPOINT_NS = 60 * NS
SUSPECT_IDLE_MS = 60_000                       # 체크포인트에서 유휴 의심 구간 제외 기준

class TimerState(Enum): STOPPED; RUNNING; PAUSED; PAUSED_AFK; FINALIZING
class Mode(Enum): STOPWATCH; POMODORO
class Phase(Enum): FOCUS; BREAK               # STOPWATCH는 항상 FOCUS

@dataclass
class Segment:
    row_id: int; chain_id: int; segment_no: int; local_date: date; credited_ns: int

@dataclass
class AfkSnapshot:
    start_mono: int                # 마지막 입력 시각 (단조)
    start_wall: datetime           # 마지막 입력 시각 (벽시계, 표시용)
    phase: Phase; phase_elapsed_ns: int        # 마지막 입력 시점의 뽀모도로 상태(롤백 후 상태)
    split_mono: int | None = None  # AFK 중 자정 분할이 일어난 단조 시각
    splits: int = 0                # AFK 중 자정 분할 횟수
    return_pending: bool = False
```

#### 공개 API

```python
class TimerEngine:
    def __init__(self, repo: SessionRepo, clock: Clock, settings: TimerSettings, emit: Callable[[Event], None]): ...
    # 조회
    state; mode; phase; subject_id
    def display_seconds(self) -> int        # 체인 전체 인정 시간(자정 지나도 HUD가 0으로 돌아가지 않음)
    def phase_remaining_seconds(self) -> int | None
    def live_credit(self) -> tuple[int, date, int] | None   # (subject_id, local_date, 현재 세그먼트 인정 초) — 통계용
    def can_include_afk(self) -> bool       # AFK 중 자정 분할이 1회 이하일 때만 True
    # 명령
    def start(self, subject_id: int, mode: Mode) -> None            # STOPPED → RUNNING
    def pause(self) -> None                                          # RUNNING → PAUSED
    def resume(self) -> None                                         # PAUSED → RUNNING
    def stop(self) -> None                                           # RUNNING/PAUSED/PAUSED_AFK → FINALIZING (AFK면 제외로 확정)
    def finalize(self, memo: str) -> None                            # FINALIZING → STOPPED
    def resolve_afk(self, include: bool) -> None                     # PAUSED_AFK(복귀 대기) → RUNNING
    def recover(self, row: SegmentRow, action: RecoverAction) -> None  # CONTINUE / SAVE / DISCARD
    def update_settings(self, s: TimerSettings) -> None              # 다음 페이즈부터 적용
    # 주기 입력
    def tick(self) -> None                                           # 250ms (TID_ENGINE)
    def on_idle_poll(self, idle_ms: int) -> None                     # 1s
    def on_session_lock(self) -> None; def on_session_unlock(self) -> None
    def on_suspend(self) -> None
```

이벤트(`domain/events.py`): `Started`, `Ticked(display_s)`(표시 초가 바뀔 때만), `PhaseChanged(phase)`, `Paused`, `Resumed`, `AfkStarted`, `AfkReturned(away_wall_s, away_awake_s, can_include)`, `FinalizeRequested(total_s)`, `Finished(total_s)`, `Recovered`, `StorageError(msg)`.

#### 알고리즘 1 — 틱과 크레딧 누적

```python
def tick(self):
    mono = self.clock.mono_ns(); wall = self.clock.now_local()
    delta = mono - self._last_mono; self._last_mono = mono
    if delta < 0 or delta > MAX_TICK_GAP_NS: log_gap(delta); delta = 0
    if self.state is RUNNING:
        self._advance(delta)                     # 아래
        self._timeline.record(mono, self._cum_credit_ns, self.phase, self._phase_elapsed_ns)
    if self.state in ACTIVE and wall.date() != self._seg.local_date:   # ACTIVE = RUNNING, PAUSED, PAUSED_AFK
        self._split_at_midnight(mono, wall)
    if self.state in ACTIVE and mono - self._last_ckpt_mono >= CHECKPOINT_NS:
        self._checkpoint(mono, wall)
    self._emit_tick_if_changed()

def _advance(self, delta):
    if self.mode is STOPWATCH:
        self._credit(delta); return
    while delta > 0:                             # 뽀모도로: 페이즈 경계를 넘는 delta를 쪼갠다
        target = self._focus_ns if self.phase is FOCUS else self._break_ns
        step = min(delta, target - self._phase_elapsed_ns)
        if self.phase is FOCUS: self._credit(step)
        self._phase_elapsed_ns += step; delta -= step
        if self._phase_elapsed_ns >= target:
            self.phase = BREAK if self.phase is FOCUS else FOCUS
            self._phase_elapsed_ns = 0
            self.emit(PhaseChanged(self.phase))

def _credit(self, ns):
    self._seg.credited_ns += ns; self._cum_credit_ns += ns
```

- `_cum_credit_ns`: 체인 전체 누적 크레딧(롤백 시 감소).
- `CreditTimeline`: `(mono, cum_credit_ns, phase, phase_elapsed_ns)`를 틱마다 기록하는 `deque`. 보존 범위 = `afk_timeout + 120초`(250ms 틱 기준 최대 약 2,900개). `at(mono)`는 `bisect`로 해당 시각 이전의 마지막 기록을 반환.

#### 알고리즘 2 — 체크포인트

```python
def _checkpoint(self, mono, wall):
    dur_ns = self._seg.credited_ns
    if self._last_idle_ms >= SUSPECT_IDLE_MS and self.state is RUNNING:   # 유휴 의심 구간은 저장하지 않음
        suspect = self._cum_credit_ns - self._timeline.at(mono - self._last_idle_ms * 1_000_000).cum_credit_ns
        dur_ns = max(0, dur_ns - suspect)
    self.repo.checkpoint(self._seg.row_id, iso(wall), dur_ns // NS)
    self._last_ckpt_mono = mono
```
일시정지·AFK 중에도 60초마다 `end_time`을 갱신한다(크래시 복구 시 마지막 생존 시각).

#### 알고리즘 3 — 자정 분할 (세션 체인)

```python
def _split_at_midnight(self, mono, wall):
    midnight = datetime.combine(wall.date(), time(0), tzinfo=wall.tzinfo)
    prev = self._seg
    self.repo.complete_segment(prev.row_id, iso(midnight), prev.credited_ns // NS)   # 배타적 종료: 다음날 00:00:00
    row = self.repo.create_next_segment(prev.row, iso(midnight), wall.date())
    self._prev_seg = prev                     # AFK 롤백·포함 처리를 위해 직전 세그먼트 1개만 보관
    self._seg = Segment(row.id, prev.chain_id, prev.segment_no + 1, wall.date(), 0)
    if self.state is PAUSED_AFK:
        self._afk.splits += 1; self._afk.split_mono = mono
```
- `23:59:59`를 쓰지 않는다(1초 누락, v0.5 H5).
- 앱이 꺼져 있다가 다음날 켜진 경우는 분할이 아니라 **복구(알고리즘 6)** 로 처리한다.
- 메모는 `finalize_chain`에서 체인 전체 행에 같은 값으로 기록한다.

#### 알고리즘 4 — AFK 진입

```python
def on_idle_poll(self, idle_ms):
    prev_idle = self._last_idle_ms; self._last_idle_ms = idle_ms
    mono = self.clock.mono_ns(); wall = self.clock.now_local()
    if self.state is RUNNING and idle_ms >= self._afk_timeout_ms:
        input_mono = mono - idle_ms * 1_000_000
        mark = self._timeline.at(input_mono)
        rollback = self._cum_credit_ns - mark.cum_credit_ns
        if self.mode is POMODORO and rollback == 0 and self.phase is BREAK:
            return                                  # 휴식 중 자리 비움은 정상 — AFK로 보지 않음
        self._rollback(rollback)
        self.phase, self._phase_elapsed_ns = mark.phase, mark.phase_elapsed_ns
        self._afk = AfkSnapshot(input_mono, wall - timedelta(milliseconds=idle_ms), mark.phase, mark.phase_elapsed_ns)
        self.state = PAUSED_AFK
        self._checkpoint(mono, wall); self.emit(AfkStarted())
    elif self.state is PAUSED_AFK and not self._afk.return_pending and idle_ms < prev_idle:
        self._afk.return_pending = True             # 복귀 판정: 유휴 시간이 줄었다 = 입력이 있었다
        self.emit(AfkReturned(int((wall - self._afk.start_wall).total_seconds()),
                              (mono - self._afk.start_mono) // NS, self.can_include_afk()))

def _rollback(self, ns):                            # 현재 세그먼트에서 먼저, 남으면 직전 세그먼트에서
    take = min(ns, self._seg.credited_ns); self._seg.credited_ns -= take; rest = ns - take
    if rest and self._prev_seg:
        self.repo.add_duration(self._prev_seg.row_id, -((rest + NS - 1) // NS)); self._prev_seg.credited_ns -= rest
    self._cum_credit_ns -= ns
```
- v0.5의 `idle_sec < 2` 복귀 조건은 폴링 간격보다 짧아 복귀를 놓쳤다. **"이번 값 < 직전 값"** 으로 판정한다.
- `GetLastInputInfo` 계산은 `idle_ms = (GetTickCount() - lii.dwTime) & 0xFFFFFFFF` (49.7일 되감기 대응, `win32/idle.py`).
- 화면 잠금: `on_session_lock()` → RUNNING이면 `idle_ms = 현재 유휴`로 위와 같은 진입 처리. `on_session_unlock()` → PAUSED_AFK면 복귀 판정.
- 절전: `on_suspend()` → 잠금과 동일하게 즉시 AFK 진입. 복귀는 입력 또는 잠금 해제로 판정. 단조 시계가 절전을 제외하므로 `away_awake_s`에 절전 시간이 들어가지 않는다.

#### 알고리즘 5 — AFK 해소

```python
def resolve_afk(self, include):
    mono = self.clock.mono_ns(); wall = self.clock.now_local(); afk = self._afk
    if include and self.can_include_afk():
        if afk.splits == 0:
            self._simulate(mono - afk.start_mono, target=self._seg)
        else:                                       # AFK 도중 자정 1회: 자정 전/후로 나눠 시뮬레이션
            self._simulate(afk.split_mono - afk.start_mono, target=self._prev_seg, persist=True)
            self._simulate(mono - afk.split_mono, target=self._seg)
    self.state = RUNNING; self._afk = None; self._last_mono = mono
    self._timeline.clear(); self._checkpoint(mono, wall); self.emit(Resumed())
```
- `_simulate(ns, target)`: 알고리즘 1의 `_advance`와 같은 페이즈 루프를 돌리되, FOCUS 크레딧을 `target` 세그먼트에 더한다(`persist=True`면 `repo.add_duration`). 뽀모도로에서는 "그동안 타이머가 계속 돌았다면"과 같은 결과가 된다(휴식 시간 제외, 페이즈 전환 반영).
- [제외]: 롤백된 크레딧과 페이즈(마지막 입력 시점)에서 그대로 재개.
- 자정을 2번 이상 넘긴 자리 비움은 [포함]을 비활성화한다(`can_include_afk() == False`).
- 모달 문구: `"자리 비운 시간: {away_wall}분"` + 절전 시간이 있으면 `"(절전 {away_wall - away_awake}분은 제외)"`.

#### 알고리즘 6 — 크래시 복구

앱 기동 후 `get_open_segments()`의 각 행(오래된 것부터)에 대해 복구 모달을 띄운다: `"정상 종료되지 않은 기록: {과목} {duration}분 ({local_date} {end_time 시각}까지)"`.

| 선택 | 처리 |
|---|---|
| [이어하기] | `row.local_date == 오늘`: 그 행을 현재 세그먼트로 삼아(`credited_ns = duration × NS`) RUNNING. 날짜가 지났으면 `complete_segment(row, row.end_time, row.duration)` 후 `create_next_segment(row, now, today)`로 같은 체인을 이어 RUNNING. **꺼져 있던 시간은 인정하지 않는다.** 뽀모도로는 FOCUS 0초부터 |
| [여기까지 저장] | `complete_segment(row, row.end_time, row.duration)` → 메모 모달(선택) → `UPDATE memo WHERE chain_id` |
| [폐기] | `delete_segment(row.id)` (같은 체인의 이미 확정된 이전 날짜 행은 유지) |

미완료 행이 여러 개면 [이어하기]는 마지막 행에만 제공한다.

#### 알고리즘 7 — 종료

`stop()`: PAUSED_AFK면 `resolve_afk(False)`와 같은 처리 후 진행 → 체크포인트 → `FINALIZING`(크레딧 정지) → `FinalizeRequested`. `finalize(memo)`: `finalize_chain(chain_id, seg.row_id, iso(now), seg.credited_ns // NS, memo.strip()[:200])` → `STOPPED` → `Finished`.

### 4-8. `domain/stats.py`

```python
def period_range(kind: Literal["day","week","month"], anchor: date) -> tuple[date, date]:
    # day: (d, d) / week: 월요일~일요일 / month: 1일~말일 (calendar.monthrange)
def period_days(kind, start, end) -> int          # 1 / 7 / 해당 월 일수 (Q4: 전체 일수)
def achievement_pct(total_s: int, goal_min: int, days: int) -> float:
    return 0.0 if goal_min <= 0 else total_s / 60 / (goal_min * days) * 100
def overall_pct(rows, days) -> float              # 분모 = 보관되지 않은 과목들의 goal 합 × days
def merge_live(rows, live: tuple[int, date, int] | None, start, end) -> rows   # 진행 중 세션 합산 (v0.5 M)
```
- 표시용 시간 형식: `h:mm:ss`(HUD), `N시간 M분`(통계).
- 미완료 행(크래시 복구 대기)은 집계에서 제외한다. 진행 중 세션은 `engine.live_credit()`로 더한다.

### 4-9. `infra/csv_export.py`

- 저장 대화상자: `GetSaveFileNameW`, 필터 `"CSV 파일 (*.csv)\0*.csv\0\0"`, 기본 폴더 `data/exports`, 기본 이름 `study_records_YYYYMMDD.csv`, `OFN_OVERWRITEPROMPT(0x2)|OFN_PATHMUSTEXIST(0x800)|OFN_NOCHANGEDIR(0x8)`.
- 인코딩 `utf-8-sig`, `newline=""`, `csv.writer`.
- 열: `session_id, chain_id, segment_no, subject, mode, local_date, start_time, end_time, duration_seconds, duration_hms, memo` (완료된 행만, `start_time` 순).

### 4-10. `domain/pet_fsm.py` & `domain/physics.py`

FSM 상태: `IDLE, WALK, SIT, SLEEP, DRAG, FALL, LAND, STUDY, CELEBRATE`.

```python
@dataclass
class FsmContext:
    studying: bool; on_ground: bool; walk_enabled: bool; user_idle_ms: int

class PetFSM:
    def __init__(self, rng: random.Random): ...
    state: PetState; facing: int   # -1 왼쪽, +1 오른쪽
    def update(self, dt: float, ctx: FsmContext) -> None
    def on_drag_start(self) -> None; def on_drag_end(self, airborne: bool) -> None
    def on_landed(self) -> None; def on_click(self) -> None
    def on_study_started(self) -> None; def on_study_stopped(self) -> None; def on_finished(self) -> None
    def animation_key(self) -> str          # meta.json 상태 이름
```

| 상태 | 진입 | 지속/종료 |
|---|---|---|
| IDLE | 기본 | 2~8초 후 추첨. 가중치: 기본 `Walk 40, Idle 30, Sit 20, Sleep 10` / `user_idle_ms ≥ 180000`이면 `Sleep 40, Sit 30, Idle 20, Walk 10` / `walk_enabled=False`면 Walk 0 |
| WALK | 추첨 | 3~10초, 작업 영역 좌우 경계에서 방향 반전 |
| SIT/SLEEP | 추첨 | 5~20초 후 IDLE, `on_click` 시 즉시 IDLE |
| DRAG | `on_drag_start` | `on_drag_end(airborne)` → FALL 또는 (STUDY 중이면 STUDY, 아니면 IDLE) |
| FALL | 공중에서 놓음 | `on_landed` → LAND |
| LAND | 착지 | 0.25초 후 STUDY(학습 중) 또는 IDLE |
| STUDY | `on_study_started` (DRAG/FALL 중이면 착지 후) | `on_study_stopped`/`on_finished`까지 유지 |
| CELEBRATE | `on_finished` | 애니메이션 1회(약 2초) 후 IDLE |

AC#2: `on_study_started`는 즉시 상태를 바꾸고, 펫 창이 같은 메시지 처리 안에서 다시 그린다(다음 프레임 타이머를 기다리지 않는다).

물리(단위 sp, 화면 변환은 `× phys_scale`):
- 걷기 `30 sp/s`, 중력 `900 sp/s²`, 종단 속도 `600 sp/s`. 위치는 `float`로 누적하고 창 좌표만 `int`로 반올림.
- 경계: 발 x ∈ `[work.left + 32·s, work.right − 32·s]`, 발 y ≤ `work.bottom`, 캔버스 상단 ≥ `work.top` (= 발 y ≥ `work.top + 144·s`). `s = phys_scale`.
- 걷기는 현재 모니터의 작업 영역 안에서만 한다. 모니터 간 이동은 드래그로만 한다.
- 드래그 놓기: 발 y < `work.bottom − 1` → FALL, 아니면 바닥에 맞춤.

### 4-11. 그래픽

#### 에셋 형식 (`scripts/gen_sprites.py`가 생성)

- `art/default_pixel_cat/palette.txt`: `문자 = #RRGGBB` 줄 목록, `.` = 투명. 16색 이내.
- `art/default_pixel_cat/parts/*.txt`: 64열 문자 격자 부품(몸통, 머리, 꼬리 프레임, 책상, 노트북, Zzz, 별 등).
- `art/default_pixel_cat/frames.json`: 프레임마다 부품 목록과 오프셋. 예: `{"walk_0": [["body",0,1],["legs_walk_0",0,0],["tail_1",0,0]]}`.
- 출력 `assets/skins/default_pixel_cat/sheet.png`(가로로 이어 붙인 64×64 프레임, RGBA8, 알파 0/255만) + `meta.json`:

```json
{ "frame_w": 64, "frame_h": 64, "anchor": [32, 63],
  "states": {
    "idle":      {"frames": [0,1,2,3],         "fps": 4,  "loop": true},
    "walk":      {"frames": [4,5,6,7,8,9],     "fps": 8,  "loop": true},
    "sit":       {"frames": [10,11],           "fps": 2,  "loop": true},
    "sleep":     {"frames": [12,13,14,15],     "fps": 2,  "loop": true},
    "drag":      {"frames": [16,17],           "fps": 6,  "loop": true},
    "fall":      {"frames": [18,19],           "fps": 8,  "loop": true},
    "land":      {"frames": [20,21],           "fps": 8,  "loop": false},
    "study":     {"frames": [22,23,24,25,26,27], "fps": 6, "loop": true},
    "celebrate": {"frames": [28,29,30,31,32,33], "fps": 6, "loop": false}
  } }
```

- UI 에셋(같은 스크립트): `ui/panel.png`(9-slice 원본 12×12, 모서리 4), `ui/menu_start|subjects|settings|stats.png`(16×16, 각각 보통·강조 2벌), `icons/studypet.ico`(16·32·48은 BMP 형식 항목, 256은 PNG 형식 항목).
- `graphics/png_codec.py`: 디코더는 **우리가 만든 PNG만** 지원(색 형식 6, 8비트, 비인터레이스, 필터 0~4 전부). 다른 형식이면 `ValueError`.

#### 사전 스케일 (`graphics/sprites.py`) — 로드 시 1회

```python
def scale_frame(src_bgra: bytes, w: int, h: int, s: int, flip: bool) -> bytes:
    rows = []
    for y in range(h):
        row = src_bgra[y*w*4:(y+1)*w*4]
        px = [row[i:i+4] for i in range(0, w*4, 4)]
        if flip: px.reverse()
        srow = b"".join(p * s for p in px)        # 가로 s배
        rows.append(srow * s)                     # 세로 s배 (행 반복)
    return b"".join(rows)
```
- PNG 디코딩 직후 **Premultiplied BGRA**로 변환(알파 0/255뿐이므로 α=0 픽셀을 0,0,0,0으로 만들고 나머지는 RGB→BGR만).
- 캐시 키 `(state, frame_index, phys_scale, flip)`. 기동 시 idle만 만들고 나머지는 처음 필요할 때 만든다. 배율이 바뀌면 캐시를 비운다.

#### 펫 캔버스 레이아웃 (`ui/layout.py`, 단위 sp)

| 항목 | 값 |
|---|---|
| 캔버스 | `192 × 144` |
| 캐릭터 박스 | `(64, 80) – (128, 144)`, 발 기준점 `(96, 144)` |
| 말풍선 영역 | `y 52~76`, 폭은 텍스트에 맞춰 8sp 단위(최대 176), 기본 가로 중앙 정렬. 화면 밖으로 나가면 작업 영역 안쪽으로 밀어 그린다(캔버스 범위 내). 우선순위: 토스트(2초) > 학습/휴식 상태 > 첫 실행 힌트(10초) > 대기 호버 힌트(0.8초) |
| 액션 카드 (v0.7) | 9-slice 패널 `CARD_BOX_SP = (8, 0, 176, 78)`. 헤더 `(14, 4)`~`x=178`, 주 버튼 `primary (14, 20, 164, 18)` (아이콘 16×16 `(18, 21)` + 라벨 `(38, 23)`), 보조 버튼 `secondary_a (14, 41, 80, 16)` / `secondary_b (98, 41, 80, 16)`, 하단 버튼 `stats (14, 60, 52, 14)` / `settings (70, 60, 52, 14)` / `more (126, 60, 52, 14)`. 카드가 열리면 말풍선은 숨긴다 |

레이어끼리 겹치지 않게 배치하므로 **합성은 블렌딩 없이 행 복사만으로 끝난다.**

#### `graphics/dib.py` & `compositor.py`

```python
class DibSurface:
    def __init__(self, w_px: int, h_px: int):   # CreateCompatibleDC(None) + CreateDIBSection(top-down, 32bpp)
        self.bits = (ctypes.c_ubyte * (w_px*h_px*4)).from_address(ppv.value)
    def clear_rect(self, x, y, w, h): ...         # 행마다 ctypes.memset
    def blit_rows(self, src: bytes, src_w: int, src_h: int, x: int, y: int): ...   # 행마다 ctypes.memmove (클리핑 포함)
    def destroy(self): ...

class Compositor:
    def __init__(self, scale: int): ...           # 캔버스 DibSurface 192·s × 144·s
    def set_character(self, frame_bytes): ...     # 캐릭터 박스 clear + blit (dirty)
    def set_bubble(self, layer: bytes | None, x_sp: int): ...
    def set_menu(self, icons: list | None): ...
    def set_panel(self, layer: bytes | None): ...
    def present(self, hwnd, screen_x, screen_y, opacity: float) -> None:
        # dirty일 때만 UpdateLayeredWindow(hwnd, None, &pos, &size, memdc, &(0,0), 0,
        #   BLENDFUNCTION(AC_SRC_OVER, 0, int(255*opacity), AC_SRC_ALPHA), ULW_ALPHA)
        # 위치만 바뀌면 SetWindowPos(hwnd, None, x, y, 0, 0, SWP_NOSIZE|SWP_NOZORDER|SWP_NOACTIVATE)
```
- 유령 모드 30%와 평상시 투명도는 버퍼를 다시 곱하지 않고 **`SourceConstantAlpha`** 로만 처리한다.
- 클릭 투과는 OS가 알파로 판정하므로, 알파 0/255 원칙만 지키면 그려진 것과 클릭 영역이 정확히 일치한다.

#### `graphics/text.py` — 픽셀 폰트 텍스트

1. 기동 시 `AddFontResourceExW(assets/fonts/Galmuri11.ttf, FR_PRIVATE)`. 실패 시 `"맑은 고딕"`.
2. 폰트: `CreateFontW(-11 * s, 0, 0, 0, 400, 0, 0, 0, 1(DEFAULT_CHARSET), 0, 0, NONANTIALIASED_QUALITY, 0, "Galmuri11")`(원래 크기의 정수배라 도트가 선명하게 유지된다).
3. 말풍선 레이어 = 9-slice 패널(불투명)을 DIB에 복사 → `SetBkMode(TRANSPARENT)`, `SetTextColor`, `TextOutW`.
4. **GDI는 글자 픽셀의 알파를 0으로 만든다.** 패널 내부는 전부 불투명이므로 `GdiFlush()` 후 내부 행마다 `row[3::4] = b"\xff" * w`로 알파를 복원한다(스텝 슬라이스, 픽셀 루프 아님).
5. 말풍선 내용은 1초에 한 번 바뀐다 → 그때만 다시 만든다.

#### 9-slice (`graphics/panel.py`)
원본 12×12(모서리 4)를 `(w, h, s)`로 합성해 캐시한다. 모서리는 사전 스케일 복사, 변과 가운데는 행 반복과 `bytes` 곱셈으로 채운다.

### 4-12. `ui/pet_window.py`

창 생성: 클래스 `"StudyPetPet"`, 스타일 `WS_POPUP`, 확장 `WS_EX_LAYERED|WS_EX_TOPMOST|WS_EX_TOOLWINDOW|WS_EX_NOACTIVATE`, 크기 `192·s × 144·s`. `ShowWindow(SW_SHOWNOACTIVATE)`.

| 메시지 | 처리 |
|---|---|
| `WM_MOUSEACTIVATE` | `return MA_NOACTIVATE` (클릭해도 다른 앱 포커스 유지) |
| `WM_LBUTTONDOWN` | 클라이언트 좌표 → sp. 액션 카드 버튼 위면 `card_pressed` 기록. 캐릭터 위면 `SetCapture(hwnd)`, 시작 커서(`GetCursorPos`)·발 위치 기록, `pressing=True`. 말풍선 위면 `pressing_bubble=True` |
| `WM_MOUSEMOVE` | 최초 수신 시 `TrackMouseEvent(TME_LEAVE)` 등록. `pressing`이고 이동량 ≥ `4·s` px → 드래그 시작(`fsm.on_drag_start`, 카드 닫기). 드래그 중이면 발 위치 = 시작 위치 + 커서 이동량(경계 적용), 발 위치 모니터의 DPI로 `phys_scale` 재계산. 카드가 열려 있으면 `card_hover` 갱신 |
| `WM_MOUSELEAVE` | `card_hover = None`, `_hover_since = None` 초기화 후 다시 그리기 |
| `WM_LBUTTONUP` | `ReleaseCapture()`. 드래그였으면 `fsm.on_drag_end(airborne)` + 위치 디바운스 저장. 아니면 클릭: 카드 버튼 실행(`card_pressed == hit`) / 캐릭터·말풍선 클릭 → 액션 카드 열기·닫기(`toggle_card()`, `fsm.on_click()`) |
| `WM_CAPTURECHANGED` | 드래그 중이면 드래그 종료로 처리 (v0.5 H3: 캡처가 없으면 커서가 α=0 위로 나갈 때 드래그가 끊김) |
| `WM_RBUTTONUP` | 캐릭터·말풍선 위면 액션 카드 열기·닫기(좌클릭과 동일), 카드 위면 무시 |
| `WM_MOUSEWHEEL` | `GetKeyState(VK_MENU) < 0`이면 유령 모드 토글 |
| `WM_TIMER` | 3-2 표 |
| `WM_HOTKEY` | id 1 → 유령 모드 토글 |
| `WM_APP_TRAY` | `lParam == WM_RBUTTONUP` → 트레이 메뉴 / `WM_LBUTTONDBLCLK(0x203)` → 소환 / `WM_LBUTTONUP(0x202)` → 화면 밖이면 소환 + 액션 카드 열기 |
| `WM_QUERYENDSESSION` / `WM_ENDSESSION` | `WM_QUERYENDSESSION` → `1` 반환, `WM_ENDSESSION(wParam=TRUE)` → `on_end_session()` (`checkpoint_now()` + `shutdown(post_quit=False)`) |
| `TaskbarCreated`(등록 메시지) | 트레이 아이콘 다시 추가 |
| `WM_POWERBROADCAST` | `PBT_APMSUSPEND` → `engine.on_suspend()` / 재개 → 모니터 캐시 무효화 |
| `WM_WTSSESSION_CHANGE` | `wParam` 7 → `on_session_lock`, 8 → `on_session_unlock` |
| `WM_DISPLAYCHANGE`/`WM_SETTINGCHANGE` | 모니터 캐시 무효화, 위치 보정 |
| `WM_DPICHANGED` | `return 0` (4-3) |
| `WM_APP_SUMMON` | 주 모니터 작업 영역 하단 중앙으로 이동, 유령 모드 해제 |

액션 카드 닫기(`TID_UI` 100ms): 카드가 열려 있고 `GetAsyncKeyState(VK_LBUTTON|VK_RBUTTON) & 0x8000`이며 커서가 캔버스 사각형 밖이면 닫는다. 8초 동안 카드·캐릭터 위에 커서가 없으면 닫는다.

액션 카드 동작 (`docs/REVISION_PLAN_v0.7.md` 3장·8장):
- **주 버튼(`primary`):** `STOPPED` → `학습 시작 ({모드})`, `RUNNING` → `일시정지`, `PAUSED` → `이어하기`, `PAUSED_AFK` → `확인 창 열기`.
- **보조 버튼:** `STOPPED` → `과목 ▾` / `모드 ▾`, `RUNNING`·`PAUSED` → `■ 끝내기` / `과목 바꾸기 ▾`(`engine.switch_subject()`), `PAUSED_AFK` → `■ 끝내기` / `과목 바꾸기 ▾(비활성)`.
- **하단 버튼:** `기록`(대시보드 기록 탭), `설정`(대시보드 설정 탭), `더보기 …`(과목 관리, 말풍선 간단히 보기 토글, 유령 모드, 화면 가운데로 소환, StudyPet 종료).
- 팝업 메뉴(`과목 ▾`, `모드 ▾`, `과목 바꾸기 ▾`, `더보기 …`)는 클릭한 카드 버튼의 왼쪽 아래 모서리 `(win_x + box.x·s, win_y + (box.y + box.h)·s)`에 `ui/popup.py:show_popup()`으로 띄우며, 메뉴를 띄우기 직전에 카드를 닫는다.

유령 모드:
- 켜기: `ghost=True`, `SetWindowLongPtrW(GWL_EXSTYLE, ex | WS_EX_TRANSPARENT)`, 투명도 0.3.
- 해제 경로: ① 전역 단축키 ② 트레이 메뉴 ③ 보조 경로 — `TID_UI`에서 `GetAsyncKeyState(VK_MENU) & 0x8000`이고 커서가 캐릭터 박스 안이면 임시로 `WS_EX_TRANSPARENT`를 떼고, 그 상태에서 `Alt+휠`이면 해제한다. Alt를 떼거나 커서가 벗어나면 다시 붙인다.
- 제약(Phase 0 확인): 펫 창은 포커스가 없으므로 휠 메시지는 Windows "비활성 창 스크롤" 설정이 켜져 있어야 온다(기본값 켜짐). Alt를 눌렀다 떼면 앞 창의 메뉴바가 활성화될 수 있다. 그래서 ①②가 기본 경로다.

위치 복원: `last_position`(발 위치)이 어떤 모니터의 작업 영역 안이면 사용하고, 아니면 주 모니터 `(work.right − 96·s, work.bottom)`.

### 4-13. `win32/tray.py`, `win32/hotkey.py`

- 트레이: `NOTIFYICONDATAW(uID=1, uFlags=NIF_MESSAGE|NIF_ICON|NIF_TIP, uCallbackMessage=WM_APP_TRAY, szTip="StudyPet")`. 아이콘은 `LoadImageW(None, ico_path, IMAGE_ICON, 16·dpi/96, 같은 값, LR_LOADFROMFILE)`.
- 메뉴: `[캐릭터 소환] [대시보드 열기] [유령 모드 ✓] [바탕화면 바로가기 만들기] ── [완전 종료]`. 표시 순서: `SetForegroundWindow(hwnd)` → `TrackPopupMenu(..., TPM_RETURNCMD|TPM_RIGHTBUTTON|TPM_NONOTIFY)` → `PostMessageW(hwnd, WM_NULL, 0, 0)`(메뉴가 안 닫히는 알려진 문제 회피).
- 단축키 문자열 파싱: `Ctrl`/`Alt`/`Shift` + 한 글자(A~Z, 0~9) 또는 `F1`~`F12`. `RegisterHotKey(hwnd, 1, mods | MOD_NOREPEAT, vk)` 실패(다른 앱이 사용 중) 시 트레이 메뉴로만 해제할 수 있다고 알림 모달.
- 바로가기: `powershell.exe -NoProfile -NonInteractive -EncodedCommand <UTF-16LE Base64>`. 스크립트에서 경로의 `'`는 `''`로 이스케이프. 내용: `$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\StudyPet.lnk'); $s.TargetPath='{exe}'; $s.WorkingDirectory='{root}'; $s.IconLocation='{ico},0'; $s.Save()`.

### 4-14. `win32/audio.py`

```python
class SoundPlayer:
    def __init__(self, wav_paths: dict[str, Path], volume: float): ...   # WAV 원본 바이트 로드(16-bit mono 22050Hz)
    def set_volume(self, v: float) -> None:      # 재생 중지 후 효과음별 스케일 버퍼 재생성
        winmm.PlaySoundW(None, None, 0)
        self._buffers = {k: ctypes.create_string_buffer(scale_wav(raw, v)) for k, raw in self._raw.items()}
    def play(self, key: str) -> None:
        if not self.enabled or self.volume <= 0: return
        buf = self._buffers[key]; self._playing = buf            # 재생 중 GC 방지
        winmm.PlaySoundW(ctypes.cast(buf, ctypes.c_void_p), None, SND_MEMORY | SND_ASYNC | SND_NODEFAULT)
```
- `scale_wav`: 헤더 44바이트는 그대로, 샘플은 `array('h')`로 읽어 `int(x * v)`(로드·볼륨 변경 시에만, 재생 경로 아님).
- [실측] Python `winsound`는 이 플래그 조합에서 `RuntimeError`를 던지지만, Win32 `PlaySoundW`는 버퍼가 살아 있으면 지원한다(Phase 0 확인).
- 효과음 4종(`scripts/gen_sfx.py`, 구형파·노이즈, 진폭 0.5 상한):

| 키 | 용도 | 구성 |
|---|---|---|
| `start` | 학습 시작 | 구형파 C5→E5→G5, 각 80ms |
| `phase` | 뽀모도로 전환 | 구형파 G5 120ms, 쉼 60ms, G5 120ms |
| `celebrate` | 세션 종료 | C5 E5 G5 C6 아르페지오(각 90ms) + 노이즈 반짝임 200ms |
| `afk` | AFK 복귀 알림 | 삼각파 E5→C5 하강 300ms |

### 4-15. `ui/modals.py` — `ModalQueue`

공통: 클래스 `"StudyPetModal"`, `WS_POPUP|WS_CAPTION|WS_SYSMENU`, 확장 `WS_EX_TOPMOST|WS_EX_DLGMODALFRAME`, 펫이 있는 모니터 작업 영역 중앙. `IsDialogMessageW`가 Enter·Esc·Tab을 처리한다. 모달이 열려 있는 동안 펫 메뉴는 비활성화한다(중첩 메시지 루프는 쓰지 않는다).

- **`ModalQueue` 우선순위 대기열 (v0.7 H5):** 새 모달 요청이 들어왔을 때 이미 활성 모달이 있으면 기존 모달을 파괴하지 않고 우선순위(`recovery(0) < memo(1) < afk(2) < quit(3)`) 순으로 대기열에 넣는다(같은 `kind`가 대기 중이면 대체). 활성 모달이 닫히면(`on_closed`) 다음 모달을 띄운다. 앱 종료(`flush_defaults`) 시에는 활성·대기 모달 모두 안전한 기본값 콜백(AFK=제외, 메모=메모 없이 저장, 복구=나중에 결정, 종료=취소)을 호출한다.

| 모달 | 구성 | 포커스 |
|---|---|---|
| 세션 종료 메모 | `"{과목} {h:mm:ss} 학습 완료!"`, `EDIT`(`ES_AUTOHSCROLL`, `EM_LIMITTEXT` 200), `[저장](IDOK)` `[메모 없이 저장](IDCANCEL)` | 사용자가 펫을 클릭한 직후라 `SetForegroundWindow` 허용 → EDIT에 `SetFocus`(한글 IME 사용) |
| AFK 복귀 | 자리 비운 시간·절전 제외 안내, `[기록에서 제외](IDCANCEL)` `[기록에 포함](IDOK, can_include=False면 비활성)` | **포커스 없이 표시**(`SW_SHOWNOACTIVATE`) — 입력이 다른 앱으로 갔으므로 `SetForegroundWindow`가 실패할 수 있다. 최상단이라 바로 클릭 가능 |
| 크래시 복구 | 4-7 알고리즘 6 문구, `[이어하기](IDOK)` `[여기까지 저장](3)` `[폐기](4, MessageBoxW MB_YESNO 재확인)` `[나중에 결정](IDCANCEL: X·Esc)` | 기동 직후라 포커스 허용 |
| 종료 확인 | 3-4 문구, `[저장 후 종료](IDOK)` `[기록 유지하고 종료](3)` `[취소](IDCANCEL)` | 메뉴 직후라 허용 |
| 안내 | 메시지 + `[확인]` | `MessageBoxW(MB_TOPMOST)` 사용 |

### 4-16. `ui/dashboard.py` + 탭

- comctl32 v6: `assets/studypet.manifest`(Common-Controls 6.0.0.0 의존성 선언)로 `CreateActCtxW` → `ActivateActCtx` 상태에서 대시보드 창과 컨트롤을 만든다. 실패하면 클래식 스타일로 계속한다([검증 필요]).
- `InitCommonControlsEx(ICC_TAB_CLASSES|ICC_LISTVIEW_CLASSES|ICC_BAR_CLASSES|ICC_HOTKEY_CLASS|ICC_STANDARD_CLASSES)`.
- 프레임: `WS_CAPTION|WS_SYSMENU|WS_MINIMIZEBOX`, 고정 크기 `640 × 480` × (DPI/96). 탭 컨트롤 `"SysTabControl32"` 아래 탭별 자식 패널 창(보이기/숨기기). 모든 컨트롤에 픽셀 폰트 `WM_SETFONT`.
- 닫으면 `DestroyWindow` → 컨트롤·GDI 객체·폰트 핸들 해제(메모리 회수). 다시 열 때 새로 만든다.

| 탭 | 컨트롤 | 동작 |
|---|---|---|
| 📋 과목 관리 | `SysListView32`(`LVS_REPORT|LVS_SINGLESEL`, 열: 색·과목명·일일 목표·상태), `EDIT` 과목명(40자), `EDIT` 목표 분(`ES_NUMBER`, 1~1440), 색 버튼(오너 드로우 견본 → `ChooseColorW`, 프리셋 8색을 사용자 지정 색으로 미리 채움), `[추가] [수정] [보관/복원]`, `BUTTON(BS_AUTOCHECKBOX)` "보관된 과목 표시" | 검증 실패 시 `MessageBoxW`. 보관하는 과목이 `last_subject_id`면 다음 활성 과목으로 변경. 진행 중 세션의 과목은 보관 불가 |
| ⏱️ 설정 | 모드 `COMBOBOX(CBS_DROPDOWNLIST)`, 집중·휴식·AFK `EDIT(ES_NUMBER)`, 배율 콤보(1~4), 배회 체크, FPS 콤보(30/60), 효과음 체크, 볼륨 `msctls_trackbar32`(0~100), 단축키 `msctls_hotkey32`, `[적용]` | `[적용]` 시 4-6 범위 검증 → 저장 → 엔진·펫·사운드·핫키에 즉시 반영(타이머 설정은 다음 페이즈부터) |
| 📊 공부 기록장 | `[일] [주] [월]` 라디오형 버튼, `[◀] [▶] [오늘]`, 기간 라벨, 전체 달성률 바, 차트 컨트롤(`ui/chart.py`), `[CSV 내보내기]` | 탭 표시·기간 변경 시 `period_totals` + `merge_live` 다시 조회. 진행 중이면 1초마다 오늘 막대만 갱신 |

`ui/chart.py`: 자식 창, `WM_PAINT`에서 메모리 DC(`CreateCompatibleBitmap`) 더블 버퍼링 → 과목별 가로 막대(`FillRect`, 과목 색), 라벨 `과목명  N시간 M분  (달성률 %)`, 목표선(점선). 과목이 10개를 넘으면 세로 스크롤.

### 4-17. 로깅·크래시 로그·성능 로그

- `infra/logging_setup.py`: `RotatingFileHandler(data/logs/studypet.log, 1MB, 3)`, 형식 `%(asctime)s %(levelname)s %(name)s: %(message)s`. `--console`이면 stderr 핸들러 추가.
- `crashlog.write_crash_log()`: `traceback.format_exc()`를 `data/logs/crash.log`에 추가(경로를 못 구하면 실행 파일 폴더).
- `data/logs/perf.log`: `cold_start_ms`, `menu_latency_ms`(클릭~present), `render_ms`(present 평균, 60초마다 1줄).

---

## 5. 단계별 구현 계획 (WBS)

> 각 단계의 **완료 조건(DoD)** 을 만족해야 다음 단계로 넘어간다. 1인 개발 기준.

### Phase 0 — 기술 검증 PoC (1주) 🔴 Go/No-Go
| # | 작업 | 산출물 |
|---|---|---|
| 0-1 | `scripts/setup_dev_runtime.ps1`: 원본 → `runtime/dev/` 복사, 개발용 `._pth`, `studypet_dev_root.txt`, `StudyPet.exe` 복사 | `runtime/dev/` |
| 0-2 | `bootstrap/sitecustomize.py`(2-3 전문), `src/studypet/__main__.py`, `crashlog.py` | 가드 동작 |
| 0-3 | `win32/api.py`(PoC에 필요한 부분), `graphics/dib.py` | |
| 0-4 | `poc/poc_pet.py`: 코드로 그린 64×64 더미 캐릭터(원+귀, 알파 0/255), 좌우 걷기, 드래그(`SetCapture`), 클릭 시 `MessageBeep`, 30/60FPS 전환, `perf.log` 기록 | PoC 창 |
| 0-5 | `poc/clickgrid.html`: 2px 격자 링크 페이지 | AC#1 시연 |
| 0-6 | `scripts/perf_monitor.ps1`: 프로세스 이름별 CPU%·Working Set 1초 샘플링 → CSV | |
| 0-7 | 측정·확인 후 `docs/phase0-poc.md`에 결과 기록 | 결과표 |

확인 항목과 통과 기준:

| 항목 | 기준 | 실패 시 |
|---|---|---|
| 가드: `StudyPet.exe` 기동 / `python.exe -c pass` 미기동 / 종료 코드 0 | 모두 통과 | 부트스트랩 재설계 |
| `._pth` 모드에서 사용자 site-packages(`%APPDATA%\Python`) 미사용 (`site.ENABLE_USER_SITE`, `sys.flags`) | 미사용 | `._pth`·실행 인자 조정 (AC#4) |
| 클릭 투과 2px (배율 100/125/150%) | 성공 | **No-Go** — 아키텍처 재검토 |
| Cold Start | ≤ 1.5s | 지연 로딩 확대, `.pyc` 동봉 |
| CPU (Idle·Walk, 30FPS) | < 2% | 프레임 타이머 간격 조정. 그래도 미달이면 No-Go |
| RAM (Working Set) | ≤ 120MB | No-Go |
| `present()` 평균 시간 (배율 2·4) | ≤ 3ms | 레이어 분리·dirty rect 강화 |
| ctypes `PlaySoundW` 메모리 비동기 재생 | 재생됨 | 볼륨별 WAV 파일을 `data/cache`에 써서 `SND_FILENAME` 재생 |
| 비활성 펫 창의 Alt+휠 수신, Alt 메뉴바 부작용 | 기록 | 보조 경로 제거 여부 결정 |
| comctl32 v6 활성화 컨텍스트 | 기록 | 클래식 스타일 확정 |
| Windows Defender·V3가 `StudyPet.exe`에 경고하는지 | 기록 | 실행 가이드 보강(R4) |
| Python 버전 결정(3.12.8 유지 / 최신 바이너리 계열) | 결정 | 전환 시 서명 전수·가드 재검사 |

### Phase 1 — 데이터 계층 (1주)
- `infra/paths.py`(UAC 포함), `infra/config.py`, `infra/db.py`(스키마 v1·마이그레이션·Repository 3종), `infra/csv_export.py`, `infra/logging_setup.py`
- 테스트: `tests/test_paths.py`, `test_config.py`, `test_db.py`, `test_csv.py`
- DoD: 7장 Storage 테스트 전부 통과, `C:\Program Files` 복사 시나리오에서 UAC 흐름 수동 확인

### Phase 2 — 타이머 엔진 (1.5주)
- `domain/clock.py`, `credit_log.py`, `timer_engine.py`, `events.py`, `stats.py`, `infra/real_clock.py`, `win32/idle.py`
- 테스트: `tests/test_timer_engine.py`, `test_afk.py`, `test_midnight.py`, `test_recovery.py`, `test_stats.py` (FakeClock + 메모리 DB)
- DoD: 7장 엔진 테스트 전부 통과

### Phase 3 — 그래픽·펫 (2.5주)
- `graphics/png_codec.py`, `sprites.py`, `panel.py`, `text.py`, `compositor.py`, `scripts/gen_sprites.py`, `art/default_pixel_cat/*`(전 상태 34프레임 + UI 에셋)
- `domain/pet_fsm.py`, `physics.py`, `ui/layout.py`, `ui/pet_window.py`(입력·렌더·메뉴·제어창), `win32/monitors.py`
- 테스트: `test_png.py`, `test_sprites.py`, `test_fsm.py`, `test_physics.py`, `test_layout.py`
- 중간 점검(1.5주차): 스프라이트 시안 리뷰 1회
- DoD: 펫이 걷기·드래그·낙하·메뉴 표시. Phase 0 성능 기준 재측정 통과

### Phase 4 — 통합·모달·OS 연동 (1주)
- `app.py`(기동·종료 정리), `ui/modals.py`, `win32/tray.py`, `hotkey.py`, `audio.py`, `scripts/gen_sfx.py`, 유령 모드, 크래시 복구 흐름
- DoD: AC#2·AC#3 수동 시연 통과, 효과음·트레이·핫키 동작

### Phase 5 — 대시보드: 과목·설정 (2.5주)
- `win32/actctx.py`, `ui/dashboard.py`, `tab_subjects.py`, `tab_settings.py`
- DoD: 과목 추가·수정·보관/복원, 설정 적용이 즉시 반영되고 재시작 후 유지

### Phase 6 — 통계·CSV (1.5주)
- `ui/tab_stats.py`, `ui/chart.py`, CSV 내보내기 연결
- DoD: 일/주/월 이동, 진행 중 세션 실시간 반영, Excel에서 CSV 한글 정상

### Phase 7 — 안정화 (1주)
- 3시간 연속 구동(누수 < 5MB, 평균 CPU ≤ 1.5%), 혼합 DPI 멀티 모니터(100/125/150%), 절전·최대 절전·화면 잠금·시계 변경·자정·DB 잠금·디스크 가득 참·config 손상 시나리오
- DoD: 7장 수동 체크리스트 전부 통과

### Phase 8 — 패키징·인수 (0.5주)
- `scripts/package_portable.py` (6장), 실행 가이드, 클린 Windows 10/11 VM(SAC 강제 모드 포함) 인수 테스트

**총 12.5주** (1 + 1 + 1.5 + 2.5 + 1 + 2.5 + 1.5 + 1 + 0.5)

---

## 6. 패키징 명세 (`scripts/package_portable.py`)

1. `dist/StudyPet_Portable/` 삭제 후 생성.
2. `runtime/python-3.12-amd64/`의 파일을 복사하되 `python.exe`, `pythonw.exe`, `python312._pth`는 제외. `pythonw.exe`는 `StudyPet.exe`라는 이름으로 복사.
3. 배포용 `python312._pth`(2-2) 작성, `bootstrap/sitecustomize.py` 복사.
4. `studypet.zip`: `src/studypet/**/*.py` + `py_compile`(`invalidation_mode=UNCHECKED_HASH`)로 만든 `.pyc`를 `__pycache__` 없이 같은 경로에 넣는다(Cold Start 단축). `.pyd`/`.dll`이 있으면 실패.
5. `assets/` 복사(스킨, sfx, icons, fonts, `studypet.manifest`, `LICENSES.md`), Python `LICENSE.txt` 포함.
6. `실행 가이드.txt`: 압축 해제 위치, 첫 실행, SmartScreen·백신 안내, 데이터 백업(`data/` 폴더 복사), 유령 모드 해제(`Ctrl+Alt+G`/트레이).
7. 검사: 모든 `.exe/.dll/.pyd`에 대해 `powershell -NoProfile -Command "Get-AuthenticodeSignature -LiteralPath ... | Select -Expand Status"` → 전부 `Valid`. `._pth`에 `import site`가 있는지, `data/` 폴더가 없는지 확인.
8. `dist/StudyPet_Portable_v{version}.zip` 생성.

배포 구조:
```text
StudyPet_Portable/
 ├── StudyPet.exe                 # PSF 서명 pythonw.exe (이름만 변경)
 ├── python312._pth               # python312.zip / . / studypet.zip / import site
 ├── sitecustomize.py
 ├── studypet.zip                 # 앱 코드 (.py + .pyc)
 ├── python312.dll, python3.dll, vcruntime140*.dll, python312.zip, *.pyd, libffi-8.dll 등
 ├── assets/ (skins, sfx, icons, fonts, studypet.manifest, LICENSES.md)
 ├── 실행 가이드.txt
 └── data/                        # 첫 실행 때 생성 (config.json, study_records.db, exports/, logs/)
```

---

## 7. 테스트 명세

### 7-1. 자동 테스트 (`unittest`, 2-4의 명령)

| 파일 | 주요 케이스 |
|---|---|
| `test_config.py` | 기본값 생성 / 일부 필드 누락 병합 / 범위 밖 값 대체 / 깨진 JSON → `.bak` + 기본값 / `scale: 2.0` → 2 / 원자적 저장 후 재로드 동일 |
| `test_paths.py` | 개발 마커 있음·없음 경로 해석 / `grant_data_acl` 문자 검사(`"`, `%` 거부) — `ShellExecuteExW`는 모킹 |
| `test_db.py` | 스키마 v1 생성·`user_version` / `create_chain` 후 `chain_id == id`, `end_time == start_time` / 체크포인트 / `add_duration` 음수는 0 하한 / `finalize_chain`이 체인 전체 메모 기록 / `delete_segment`는 미완료만 / `period_totals` 보관 과목 포함 규칙 |
| `test_csv.py` | BOM, 헤더, 한글, 쉼표·줄바꿈 메모 인용 |
| `test_timer_engine.py` | 스톱워치 1초 누적 / 일시정지 시간 미인정 / 뽀모도로 25분 → 휴식 → 집중 전환, 휴식 미인정 / 틱 간격 5초 초과는 0 처리 / 60초마다 체크포인트 / 표시 초는 체인 합계 |
| `test_afk.py` | 10분 유휴 → AFK 진입 + 유휴 크레딧 롤백 / 유휴 의심 구간 체크포인트 제외 / 복귀 판정(`idle_ms` 감소, 1회만 이벤트) / 제외 → 재개 / 포함 → 스톱워치 전액, 뽀모도로 시뮬레이션(휴식 제외) / 휴식 중 유휴는 AFK 아님 / 잠금·절전 즉시 진입 / `GetTickCount` 되감기 계산 |
| `test_midnight.py` | 23:59:30 시작 → 00:00:30: 행 2개, 첫 행 `end_time = 다음날 00:00:00`, 30초씩 / 일시정지 중 자정 / AFK 중 자정 + 포함(자정 전·후 배분) / AFK 중 자정 2회 → 포함 불가 / 메모가 체인 전체에 기록 |
| `test_recovery.py` | 같은 날 이어하기 / 다음날 이어하기(이전 행 확정 + 새 세그먼트, 꺼져 있던 시간 미인정) / 저장 / 폐기 |
| `test_stats.py` | 일·주(월요일 시작)·월(28~31일) 범위 / 달성률 분모 / 보관 과목 제외 합계 / 진행 중 세션 합산 |
| `test_png.py`·`test_sprites.py` | 인코드→디코드 왕복 / 필터 0~4 / 사전 스케일 크기·반전·Premultiplied 변환 / 알파 0/255 외 값 거부(생성기) |
| `test_fsm.py`·`test_physics.py`·`test_layout.py` | 고정 시드 확률 전이 / walk_enabled=False / 드래그·낙하·착지 전이 / 학습 시작 즉시 STUDY / 경계 반전 / 종단 속도 / sp↔px 변환, 메뉴 히트 영역 |

### 7-2. 수동·인수 체크리스트

| 항목 | 방법 | 기준 | Phase |
|---|---|---|---|
| SAC·서명 | 패키지 전 PE `Get-AuthenticodeSignature`, SAC 강제 모드 PC에서 실행 | 전부 `Valid`, 차단 0건 | 0, 8 |
| AC#1 | `clickgrid.html` 위에서 몸통 클릭 / 외곽 2px 클릭, 배율 100·125·150% | 메뉴 열림 / 뒤 링크 클릭 | 0, 7 |
| AC#2 | 걷는 중 빠른 시작 | 즉시 STUDY + 1초마다 카운터 증가 | 4 |
| AC#3 | 15분 구동 → 작업 관리자 강제 종료 → 재실행 | DB ≥ 14분 + 복구 모달 | 4 |
| AC#4 | 폴더 이름 변경·USB 이동·바로가기 실행, `%APPDATA%` 확인 | 데이터 동일, `%APPDATA%` 생성 0건 | 1, 8 |
| KPI 리소스 | `perf_monitor.ps1` 3시간 | 누수 < 5MB, 평균 CPU ≤ 1.5%, RAM ≤ 120MB | 0, 7 |
| 응답 속도 | `perf.log` | Cold Start ≤ 1.5s, 메뉴 ≤ 100ms | 0, 3, 4 |
| 전체 화면 | 브라우저 F11 영상 위 표시 (US-02) | 캐릭터 보임 (독점 전체 화면 게임 제외) | 7 |

---

## 8. 코딩 규약

- Python 3.12 문법, 모든 공개 함수에 타입 힌트, `dataclass(frozen=True)`를 우선 사용. 외부 패키지 없음.
- 파일 인코딩 UTF-8, 경로는 `pathlib.Path`, 사용자 표시 문자열은 `studypet/strings.py`(한국어)에 모은다.
- `domain`은 시각·난수·저장소를 주입받는다(`Clock`, `random.Random`, Repository 프로토콜).
- Win32 핸들(GDI 객체·DC·아이콘·폰트)은 소유 객체의 `destroy()`에서 해제하고 생성·해제를 짝지어 테스트한다(Phase 7 누수 대비).
- DB 오류(`sqlite3.Error`)는 엔진에서 `StorageError` 이벤트로 바꿔 UI에 알리고, 메모리 상태는 유지해 다음 체크포인트에서 재시도한다.

---

## 9. PRD 개정 필요 항목

| PRD 위치 | 현재 | 개정 제안 |
|---|---|---|
| 6-1 기술 스택 | Tauri / Godot / PyQt6 / (조건부) Electron | Python 공식 embeddable + Win32(ctypes) 채택, 사유(SAC) 기재 |
| 7장 제약 | SmartScreen만 언급 | 스마트 앱 컨트롤 제약, 이름 바꾼 인터프리터의 EDR 탐지 가능성 |
| 6-2 스키마 | — | `local_date`, `chain_id`, `segment_no`, `subjects.sort_order` 추가, 자정 분할 규칙 |
| 6-3 config | `scale: 2.0`, 일부 필드 없음 | 4-6 전체 스키마, `scale` 정수, `last_position`은 발 위치 |
| 3-1 #4 | `study_log.db` | `study_records.db` (Q6) |
| 5-1 유령 모드 | Alt+휠 토글만 | 단축키·트레이 해제 경로 추가, Alt+휠 제약 |
| 3-1 #3 AFK | 자리 비움 처리 | 절전 시간 제외, 휴식(뽀모도로 BREAK) 중 유휴는 AFK 아님 |

---

## 10. 범위 밖

- macOS(v1.1), 설치형/Microsoft Store 배포, 스킨 교체 UI, 다국어, 자동 업데이트.
- PRD 3-2 배제 기능(클라우드 동기화, 멀티플레이, 모바일, RPG 요소).

---

## 11. 리스크 & 대응

| # | 리스크 | 영향 | 대응 |
|---|---|---|---|
| R1 | 클릭 투과 2px·혼합 DPI에서 실패 | 높음 | Phase 0 No-Go 항목. 알파 0/255 원칙, 발 위치 모니터 DPI 기준 배율 |
| R2 | 순수 Python 렌더링 부하 | 높음 | 런타임 픽셀 루프 금지(2-5), 사전 스케일·행 복사·레이어 비중첩, 상태별 타이머 간격. Phase 0·3 측정 |
| R3 | Win32 대시보드 구현 공수 | 높음 | 공용 컨트롤·시스템 대화상자 중심, 커스텀 드로잉은 차트만. Phase 5·6에 4주 |
| R4 | 이름 바꾼 인터프리터(`OriginalFilename=pythonw.exe`)를 EDR이 탐지 | 중 | Phase 0·8에서 Defender·V3 확인, 실행 가이드. 근본 해결은 자체 코드 사이닝(별도 비용) |
| R5 | Python 3.12 Windows 바이너리 갱신 중단 | 중 | Phase 0에서 버전 결정. 업그레이드 시 서명 전수·가드·Phase 0 회귀 측정 |
| R6 | sitecustomize 가드 오작동 | 중 | 이름·인자 이중 조건, 가드 테스트(Phase 0) |
| R7 | 절전·시계 변경으로 시간 왜곡 | 중 | `QueryUnbiasedInterruptTime`, 틱 간격 상한, 집계 키 `local_date` |
| R8 | Alt+휠 미수신·Alt 메뉴바 활성화 | 낮음 | 단축키·트레이 기본 경로, Phase 0 결과로 보조 경로 유지 여부 결정 |
| R9 | OneDrive 등 동기화 폴더에서 `-wal` 충돌 | 중 | 종료 시 `wal_checkpoint(TRUNCATE)`, 실행 가이드에 안내 |
| R10 | UAC 권한 없음(회사 PC) | 낮음 | 이동 안내 후 종료 |
| R11 | 자체 제작 스프라이트 품질 | 중 | 부품 조합 방식으로 반복 수정 용이, Phase 3 중간 리뷰 |

---

## 12. 결정 기록

| # | 항목 | 결정 |
|---|---|---|
| Q1 | 캐릭터 아트 | 자체 제작, 64×64, 부품 조합 생성기 |
| Q2 | 유령 모드 해제 | 기본: `Ctrl+Alt+G`·트레이 / 보조: Alt+호버 후 Alt+휠 (Phase 0 결과로 유지 여부 결정) |
| Q3 | AFK vs 강의 시청 | 예외 없이 감지, [포함]으로 복구. 절전 시간은 제외, 휴식 중 유휴는 AFK 아님 |
| Q4 | 달성률 분모 | 전체 일수 (주 7일, 월 28~31일), 주는 월요일 시작 |
| Q5 | 쓰기 권한 | `ShellExecuteExW(runas)` → `cmd /d /c mkdir & icacls *S-1-5-32-545`, 완료 대기 |
| Q6 | DB 파일명 | `study_records.db` |
| Q7 | 효과음·볼륨 | 자체 합성 4종, ctypes `PlaySoundW` 메모리 비동기 재생 |
| Q8 | 좌/우클릭 (v0.7 개정) | **좌·우클릭 모두 액션 카드 하나.** 목록·드문 기능은 Windows 기본 팝업 메뉴(`ui/popup.py`, 버튼 아래 고정 위치, 포커스 일시 이동 허용) |
| Q9 | 스택 1차 변경 | Tauri 포기 (SAC가 빌드 스크립트 차단) |
| Q10 | 스택 확정 | Python 3.12.8 embeddable + Win32(ctypes) + sqlite3 |
| Q11 | 런타임 실측 반영 | `._pth` `import site` 필수, `os._exit` 종료, `winsound`·`zoneinfo` 미사용 |
| Q12 | v0.6 설계 확정 | sitecustomize는 `bootstrap/`(개발)·루트(배포), 절전 제외 단조 시계, 크레딧 타임라인 기반 AFK 롤백, 세션 체인(`chain_id`)·배타적 자정 경계·`local_date` 집계, 행 복사 합성(블렌딩 없음), `SetCapture` 드래그, 대시보드 공용 컨트롤, 일정 12.5주 |
| Q13 | 학습 중 과목 변경 (v0.7) | 메모 없이 현재 체인 확정(`finalize("", silent=True)`) → 같은 모드로 새 체인 시작, 말풍선 토스트 2초, 0초 단일 세그먼트 체인은 삭제 |
| Q14 | 종료 확인 두 번째 버튼 (v0.7) | `[기록 유지하고 종료]` = 체크포인트 저장 후 종료하여 다음 실행 때 복구. 삭제 경로는 복구 창의 `[폐기]`+재확인뿐 |
| Q15 | 모달 동시 요청 (v0.7) | `ModalQueue` 우선순위 대기열, 강제 종료 시 각 모달의 안전한 기본값 호출 |

---

## 13. 저장소 구조

```text
D:\0MY\SOURCE\2D-Timer\
 ├── 2d_timer_prd.md
 ├── DEVELOPMENT_PLAN.md
 ├── bootstrap/
 │    └── sitecustomize.py
 ├── runtime/
 │    ├── python-3.12.8-embed-amd64.zip     # 원본 (수정 금지)
 │    ├── python-3.12-amd64/                # 원본 해제본 (수정 금지)
 │    └── dev/                              # setup_dev_runtime.ps1 생성물 (git 제외)
 ├── src/studypet/                          # 3-1 구조
 ├── tests/                                 # 7-1 목록
 ├── poc/ (poc_pet.py, clickgrid.html)
 ├── art/default_pixel_cat/ (palette.txt, parts/*.txt, frames.json)
 ├── assets/
 │    ├── skins/default_pixel_cat/ (sheet.png, meta.json)
 │    ├── ui/ (panel.png, menu_*.png)
 │    ├── sfx/ (start.wav, phase.wav, celebrate.wav, afk.wav)
 │    ├── icons/studypet.ico
 │    ├── fonts/Galmuri11.ttf (OFL)
 │    ├── studypet.manifest
 │    └── LICENSES.md
 ├── docs/phase0-poc.md
 ├── data-dev/                              # 개발 실행 데이터 (git 제외)
 ├── dist/                                  # 패키징 결과 (git 제외)
 └── scripts/ (setup_dev_runtime.ps1, gen_sprites.py, gen_sfx.py, package_portable.py, perf_monitor.ps1)
```
