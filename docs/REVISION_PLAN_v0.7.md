# 🔧 수정 계획서 v0.7 — 구현 코드 교차검증 결과 + 메뉴 조작 개선

**기준:** `DEVELOPMENT_PLAN.md` v0.6, `src/studypet/**` (2026-11-03 17:16 빌드), `dist/StudyPet_Portable` 사용 로그(2026-11-04)
**작성일:** 2026-11-04
**방법:** 코드 정적 검토만 수행(실행·테스트 없음). 동작 근거는 코드 경로와 `data/logs/perf.log` 기록.
**상태:** 구현 완료(2026-11-04, 8장 D1·D2 반영, `DEVELOPMENT_PLAN.md` v0.7 갱신). 구현 후 교차검증에서 발견한 결함 9건 수정 완료(9장), 단위 테스트 71개 통과. 재패키징은 미실시.

---

## 1. 요약

| 구분 | 건수 | 핵심 |
|---|---|---|
| 높음 (데이터 손실·조작 불능) | 6 | 종료 확인 창의 한 번 클릭으로 진행 중 기록 삭제, 복구 창 X 버튼 = 폐기, 과목 변경·종료 시 메모 창이 남아 입력이 버려짐, AFK 결정 유실로 타이머 정지 불능, Windows 종료 시 저장 누락 |
| 중간 (계획 불일치·기능 저하) | 7 | 설정 적용 시 위치·과목 되돌림, 위치 즉시 저장 안 함, 대시보드 Tab 키 불가, 통계 1초 전체 재조회, 픽셀 폰트 미동봉, 패키징이 사용 중 데이터 삭제 위험, 타이머 주기 불일치 |
| 낮음 | 4 | 트레이 좌클릭 무반응, 숨은 제스처(말풍선 클릭 = 축소), 걷기 FPS 고정, `perf.log` 무한 증가 |
| UX 개편 | 1 | **좌클릭 방사형 메뉴 + 우클릭 제어창 → "액션 카드" 하나로 통합** (3장) |

`perf.log`에 08:30~08:36 사이 `menu_latency_ms` 클릭이 59회 기록되어 있다. 원하는 기능을 찾느라 메뉴를 여러 번 여닫은 흔적으로 보이며, 3장 개편의 근거로 삼는다.

---

## 2. 코드 ↔ 계획서 교차검증 결과

### 2-1. 높음

| # | 위치 | 문제 | 계획서 기준 | 수정 |
|---|---|---|---|---|
| H1 | `app.py:462-465`, `:480-482`, `strings.py:43` | 종료 확인의 **[저장하지 않고 종료]** 가 `get_open_segments()` 전체를 `DELETE`한다. 학습 중 트레이 → 완전 종료 → 버튼 한 번으로 오늘 기록이 사라진다. `engine.state`를 직접 바꿔 `_seg`가 남는 문제도 있다 | 3-4: **[기록 유지하고 종료]** = 체크포인트만 저장하고 다음 실행 때 복구 창 | 버튼을 `기록 유지하고 종료`로 바꾸고, `engine.checkpoint_now()` 후 `shutdown()`. `_discard_current_session()` 삭제 |
| H2 | `modals.py:326-332`, `:385-387` | 복구 창에서 **X 버튼·Esc** 가 `IDCANCEL`이 되어 `"discard"`로 처리된다(`delete_segment`). 무심코 창을 닫으면 기록이 영구 삭제된다 | 4-7 알고리즘 6: 폐기는 명시적 선택 | 버튼 ID 분리: 이어하기 `IDOK`, 저장 `ID_SAVE(3)`, 폐기 `ID_DISCARD(4)`. `IDCANCEL`(X·Esc) = **나중에 결정**(행을 그대로 두고 창만 닫음, 다음 실행 때 다시 물음). 폐기는 `MessageBoxW(MB_YESNO)` 재확인 |
| H3 | `app.py:298-304` | 학습 중 과목 변경 시 `stop()`이 `FinalizeRequested`를 보내 **메모 창이 뜬 뒤**, 곧바로 `finalize("")`와 `start()`가 실행된다. 메모 창은 남아 펫 조작을 막고(`modal_locked`), 입력한 메모는 `finalize()` 가드(`state != FINALIZING`)에 걸려 버려진다 | 4-7 알고리즘 7 | 엔진에 `switch_subject(new_id)` 추가(4-1). 메모 창 없이 현재 체인을 확정하고 새 체인을 시작한다. 말풍선에 2초간 `"국어 0:12:34 저장 → 수학 시작"` 표시 |
| H4 | `app.py:476-479` | [저장 후 종료]가 `stop()` → `finalize("")` → `shutdown()`을 한 번에 실행한다. H3과 같은 원인으로 메모 창이 잠깐 떴다가 닫힌다 | 3-4: 메모 창을 거쳐 `finalize` 후 종료 | `stop()` → 메모 창 → `on_done`에서 `finalize(memo)` → `shutdown()`. `_quit_after_finalize` 플래그로 연결 |
| H5 | `modals.py:159` (`close_active()`) | 새 모달을 열 때 기존 모달을 **콜백 없이** 파괴한다. AFK 복귀 창이 떠 있는 상태에서 종료 확인 창 등이 열리면 AFK 결정이 유실되고, 엔진은 `PAUSED_AFK` + `return_pending=True`에 머문다. 이후 일시정지·재개가 모두 무시되고 복귀 창도 다시 뜨지 않는다 | 4-15: 단일 모달 | `ModalQueue` 도입(4-2): 모달을 교체하지 않고 대기열에 넣는다. 우선순위는 복구 > 메모 > AFK > 종료 확인. 강제로 닫아야 할 때(종료 등)는 각 모달의 **기본값 콜백**을 호출한다(AFK = 제외, 메모 = 메모 없이 저장, 복구 = 나중에 결정) |
| H6 | `app.py:496` `shutdown()`, `pet_window.py` | `shutdown()`에 엔진 체크포인트가 없다. `WM_QUERYENDSESSION`/`WM_ENDSESSION`(Windows 종료·로그오프)도 처리하지 않아, 그때 진행 중이던 최대 60초가 사라지고 `wal_checkpoint`도 건너뛴다 | 3-4 첫 단계: 엔진 상태 확인 → 체크포인트 | `shutdown()` 첫 줄에 `if engine.state in ACTIVE: engine.checkpoint_now()`. 펫 창에서 `WM_QUERYENDSESSION(0x11)` → `TRUE` 반환, `WM_ENDSESSION(0x16)`이고 `wParam=TRUE`면 `on_end_session()` → 체크포인트 + `shutdown(post_quit=False)` |

### 2-2. 중간

| # | 위치 | 문제 | 수정 |
|---|---|---|---|
| M1 | `tab_settings.py:310-371`, `app.py:325-328` | 설정 탭은 탭을 열 때 받아 둔 `AppConfig` 사본 전체를 `replace()`해서 넘긴다. 탭을 연 뒤 캐릭터를 옮기거나 과목을 바꾸고 [적용]을 누르면 `last_position`·`last_subject_id`·`bubble_collapsed`가 예전 값으로 되돌아간다 | 설정 탭은 `SettingsPatch`(설정 탭이 다루는 필드만 담은 dataclass)를 넘기고, `AppController`가 **현재** `self.config`에 병합한다 |
| M2 | `app.py:311-318`, `:298-299` | 드래그가 끝나도 위치를 메모리에만 반영하고, 과목 선택도 종료할 때만 저장한다. 강제 종료되면 위치와 마지막 과목을 잃는다 | 드래그 종료·과목 변경 시 `config.save()`(4-6 원자적 저장). 드래그 반복에 대비해 1초 디바운스(`TID_SAVE_CFG = 6`, 1회성) |
| M3 | `app.py:597-600` | `IsDialogMessageW`를 모달에만 적용해서, 대시보드에서는 Tab·Shift+Tab·Enter가 동작하지 않는다 | 메시지 루프에서 `dashboard.hwnd`에도 `IsDialogMessageW` 적용. 탭 패널 창에 `WS_EX_CONTROLPARENT(0x10000)` 추가 |
| M4 | `dashboard.py:284-287` | 기록 탭이 열려 있으면 1초마다 `period_totals` SQL을 다시 실행하고 전체를 다시 그린다 | 기간이 바뀔 때만 DB 조회 결과를 캐시하고, 1초 갱신은 `merge_live()`와 차트 `InvalidateRect`만 수행 |
| M5 | `text.py:27`, `assets/` | `assets/fonts/Galmuri11.ttf`가 없어 항상 "맑은 고딕"을 비안티앨리어스로 렌더링한다. 도트 느낌이 깨지고 작은 크기에서 한글이 뭉개진다 | Galmuri11(OFL 1.1, `.ttf`는 PE가 아니므로 SAC와 무관) 동봉, `LICENSES.md`에 고지 추가, 패키징 5단계 검사에 폰트 존재 여부 포함 |
| M6 | `scripts/package_portable.py` 1단계 | 패키징할 때 `dist/StudyPet_Portable/`을 지우고 다시 만든다. 지금 그 폴더의 `data/study_records.db`를 실제로 사용 중이므로 다시 패키징하면 기록이 삭제된다 | 출력 폴더를 `dist/build/StudyPet_Portable/`로 분리. 대상 폴더에 `data/`가 있으면 패키징을 중단하고 경로를 안내한다. **현재 `dist/StudyPet_Portable/data/`는 수정 작업 전에 백업한다** |
| M7 | `pet_window.py:335-338` | `TID_ENGINE` 250ms(계획 200), `TID_TOPMOST` 5000ms(계획 2000) | 동작상 문제는 없다(초 표시 지연 ≤ 250ms). **계획서를 코드 값으로 갱신**한다 |

### 2-3. 낮음

| # | 위치 | 문제 | 수정 |
|---|---|---|---|
| L1 | `pet_window.py:951-957` | 트레이 아이콘 좌클릭에 반응이 없고, 더블클릭만 소환한다 | 좌클릭 = 캐릭터 소환 + 액션 카드 열기 (3-5) |
| L2 | `pet_window.py:833-840` | 말풍선을 클릭하면 축소/펼침이 토글된다. 사용자가 알기 어려운 숨은 동작이다 | 말풍선 클릭도 액션 카드를 열게 하고, 축소는 [더보기] 메뉴로 옮긴다 (3장) |
| L3 | `pet_window.py:477` | 걷기 프레임 간격이 33ms로 고정되어 `render.fps=60` 설정을 무시한다 | `1000 // fps_limit` |
| L4 | `pet_window.py:343-352` | 클릭할 때마다 `perf.log`에 줄을 추가하고 회전하지 않는다 | `menu_latency_ms`는 60초 평균·최대만 1줄로 기록하고, 파일이 1MB를 넘으면 `.1`로 회전 |

### 2-4. 계획서대로 구현되어 있음을 확인한 항목

`sitecustomize` 가드·`os._exit`, `QueryUnbiasedInterruptTime` 시계, `MAX_TICK_GAP_NS`, 자정 분할(틱을 자정 전/후로 나누는 처리 포함), 크레딧 타임라인 AFK 롤백, `idle_ms` 감소로 복귀 판정, 체인 메모, DB `BEGIN IMMEDIATE`·`MAX(0, …)`·`wal_checkpoint(TRUNCATE)`·마이그레이션 백업, `SetCapture` 드래그와 `WM_CAPTURECHANGED`, `WM_MOUSEACTIVATE → MA_NOACTIVATE`, 유령 모드 3경로, `PlaySoundW` 메모리 재생, 트레이 `TaskbarCreated` 재등록, 패키징 서명 전수 검사.

---

## 3. 메뉴 조작 개선 — "액션 카드"

### 3-1. 현재 방식의 문제

| 문제 | 원인 |
|---|---|
| 같은 펫인데 좌클릭과 우클릭이 서로 다른 메뉴를 연다 | Q8 결정(좌 = 방사형, 우 = 제어창). 어느 쪽에 무엇이 있는지 외워야 한다 |
| 방사형 메뉴는 16×16 아이콘 4개뿐이고 글자가 없다 | 아이콘 뜻을 추측해야 한다. 같은 자리의 아이콘이 상태에 따라 "시작"과 "일시정지"로 바뀐다 |
| 일시정지·종료·과목 변경은 우클릭 창에만 있다 | 학습 중에 가장 자주 쓰는 동작이 숨은 쪽에 있다 |
| 말풍선 클릭은 축소/펼침 토글이다 | 눈에 보이지 않는 동작이다 |
| 호버 강조가 남는다 | `WM_MOUSELEAVE`를 처리하지 않는다 |

### 3-2. 설계 원칙

1. **입구는 하나:** 펫이나 말풍선을 클릭하면 좌클릭이든 우클릭이든 같은 "액션 카드"가 열린다. 다시 클릭하면 닫힌다.
2. **글자로 보여주기:** 모든 버튼에 한국어 라벨을 붙이고, 상태별로 지금 할 수 있는 동작만 보여준다.
3. **가장 자주 쓰는 동작을 가장 크게:** 주 버튼 한 개(시작 / 일시정지 / 이어하기)를 카드 폭 전체로 만든다.
4. **포커스를 뺏지 않기:** 카드는 지금처럼 펫 캔버스 안에 그리는 레이어다. 공부하던 앱의 포커스를 유지한다.
5. **드물게 쓰는 기능은 [더보기]로:** 이 메뉴만 Windows 기본 팝업 메뉴(`TrackPopupMenu`)를 쓴다.

### 3-3. 마우스 조작표 (변경 후)

| 입력 | 대상 | 동작 |
|---|---|---|
| 좌클릭 또는 우클릭 | 캐릭터·말풍선 | 액션 카드 열기 / 닫기 (`fsm.on_click()` 유지) |
| 좌클릭 | 카드 버튼 | 실행 (눌린 버튼과 뗀 버튼이 같을 때만) |
| 우클릭 | 카드 위 | 무시 |
| 드래그 (4·s px 이상) | 캐릭터 | 이동 (카드는 닫힘), 기존과 같음 |
| 카드 밖 클릭 / 8초간 카드 위에 커서 없음 / 같은 캐릭터 다시 클릭 | — | 카드 닫기 |
| Alt + 휠 | 캐릭터 | 유령 모드 토글 (보조 경로, 기존과 같음) |
| 트레이 좌클릭 | 트레이 아이콘 | 캐릭터가 화면 밖이면 소환 + 카드 열기 |
| 트레이 우클릭 | 트레이 아이콘 | 트레이 메뉴 (맨 위에 `학습 시작/일시정지` 추가) |

### 3-4. 카드 레이아웃 (`ui/layout.py`, 단위 sp, 캔버스 192×144)

```
x: 8                                                184
y:0 ┌───────────────────────────────────────────────┐
  4 │ ● 집중  국어            0:12:34   남은 12:26  │  헤더 (y 4~18)
 20 │ ┌───────────────────────────────────────────┐ │
    │ │  ⏸  일시정지                              │ │  주 버튼 (y 20~38)
 38 │ └───────────────────────────────────────────┘ │
 41 │ ┌───────────────────┐  ┌───────────────────┐ │
    │ │  ■ 끝내기          │  │  과목 바꾸기 ▾     │ │  보조 버튼 (y 41~57)
 57 │ └───────────────────┘  └───────────────────┘ │
 60 │  [ 기록 ]      [ 설정 ]      [ 더보기 … ]     │  하단 (y 60~74)
 78 └───────────────────────────────────────────────┘
 80                ┌──────────┐
                   │  캐릭터  │  (64,80)–(128,144) 그대로
144                └──────────┘
```

| 요소 | 상자 `(x, y, w, h)` |
|---|---|
| 카드 패널(9-slice) | `(8, 0, 176, 78)` |
| 헤더 텍스트 | 왼쪽 `(14, 4)`, 오른쪽 정렬 끝 `x = 178` |
| 주 버튼 `primary` | `(14, 20, 164, 18)`, 아이콘 16×16 `(18, 21)` + 라벨 `(38, 23)` |
| 보조 버튼 `secondary_a` / `secondary_b` | `(14, 41, 80, 16)` / `(98, 41, 80, 16)` |
| 하단 버튼 `stats` / `settings` / `more` | `(14, 60, 52, 14)` / `(70, 60, 52, 14)` / `(126, 60, 52, 14)` |

- 카드는 캐릭터 상자(y ≥ 80)와 겹치지 않으므로 v0.6 원칙대로 행 복사 합성만으로 그린다.
- 카드가 열려 있으면 말풍선은 숨긴다(헤더가 말풍선 역할을 대신한다).
- 모든 버튼 영역은 불투명(α=255)이어서 클릭 투과 판정과 그려진 영역이 일치한다.
- 글리프: `⏸`(U+23F8)은 폰트에 없을 수 있으므로 주 버튼 아이콘은 기존 `assets/ui/menu_start.png`·`menu_pause.png`를 쓰고, 텍스트에는 `■`(U+25A0)·`▾`(U+25BE)·`…`만 쓴다(Galmuri11과 맑은 고딕 모두 포함).

### 3-5. 상태별 카드 내용

| 엔진 상태 | 헤더 | 주 버튼 | 보조 A | 보조 B |
|---|---|---|---|---|
| `STOPPED` | `대기 중 · {과목}` | ▶ `학습 시작 ({뽀모도로·스톱워치})` | `과목 ▾` | `모드 ▾` |
| `RUNNING` + `FOCUS` | `● 집중 {과목} {h:mm:ss}` (+뽀모도로면 `남은 {m:ss}`) | ⏸ `일시정지` | `■ 끝내기` | `과목 바꾸기 ▾` |
| `RUNNING` + `BREAK` | `☕ 휴식 남은 {m:ss}` | ⏸ `일시정지` | `■ 끝내기` | `과목 바꾸기 ▾` |
| `PAUSED` | `일시정지 {과목} {h:mm:ss}` | ▶ `이어하기` | `■ 끝내기` | `과목 바꾸기 ▾` |
| `PAUSED_AFK` | `자리 비움 확인 중` | `확인 창 열기` (AFK 창을 앞으로) | `■ 끝내기` | (비활성, 회색) |
| `FINALIZING` | 카드를 열지 않음 (메모 창이 떠 있음) | — | — | — |

- 하단 3개는 모든 상태에서 같다: `기록`(대시보드 기록 탭), `설정`(설정 탭), `더보기 …`.
- `과목 ▾` / `모드 ▾` / `과목 바꾸기 ▾`는 `TrackPopupMenu`로 목록을 띄운다(현재 `_show_subject_popup_menu` 재사용). 목록 마지막에 `과목 관리…`(과목 탭)를 둔다.
- `모드 ▾` 선택은 `config.timer.default_mode`를 바꾸고 바로 저장한다.
- `과목 바꾸기`는 학습 중이면 `engine.switch_subject()`를 호출한다(H3).
- `■ 끝내기`는 기존 `engine.stop()`과 같다(메모 창 → 축하 애니메이션).
- `☕`(U+2615)는 폰트에 없으면 생략하고 `휴식`만 표시한다.
- `[더보기 …]` 메뉴 항목:

  | 항목 | 동작 |
  |---|---|
  | 과목 관리 | 대시보드 과목 탭 |
  | 말풍선 간단히 보기 ✓ | `bubble_collapsed` 토글 (기존 말풍선 클릭 동작) |
  | 유령 모드 (Ctrl+Alt+G) | 유령 모드 켜기. 단축키 문자열은 설정값으로 표시 |
  | 캐릭터를 화면 가운데로 | `summon_to_primary_center()` |
  | ── | |
  | StudyPet 종료 | `request_quit()` |

### 3-6. 처음 쓰는 사람을 위한 안내

- 첫 실행(`config.hud.hint_shown == false`)이면 기동 2초 뒤 말풍선에 `"안녕! 나를 클릭하면 메뉴가 열려요"`를 10초간 보여주고, 사용자가 카드를 한 번이라도 열면 `hint_shown = true`로 저장한다.
- 학습 중이 아닐 때 커서가 캐릭터 위에 0.8초 머물면 말풍선에 `"클릭: 메뉴 · 끌기: 이동"`을 표시하고, 커서가 벗어나면 숨긴다(카드가 열려 있으면 표시하지 않음).

### 3-7. 시각 피드백

| 상태 | 표현 |
|---|---|
| 보통 | 버튼 바탕 `#2B2F4A`, 글자 `#FFF8E6`. 주 버튼은 바탕 `#4F46E5` |
| 호버 | 바탕을 한 단계 밝게(`#3A3F63` / 주 버튼 `#6366F1`) |
| 눌림 | 바탕 `#1E2136`, 라벨을 1sp 아래로 |
| 비활성 | 글자 `#7A7F99`, 호버·클릭 무시 |

- 버튼 바탕은 `graphics/panel.py`에 추가하는 `fill_rect(buf, buf_w_px, x, y, w, h, bgra)`로 칠한다. 행마다 `bytes(bgra) * w` 슬라이스를 대입하므로 픽셀 단위 루프 규칙(2-5)을 지킨다.
- 카드 레이어 캐시 키: `(state, phase, header_text, hover_key, pressed_key, enabled_mask, scale)`. 헤더 시간 때문에 1초에 한 번 다시 그린다.
- 호버 해제: `WM_MOUSEMOVE`를 처음 받을 때 `TrackMouseEvent(TME_LEAVE)`를 등록하고, `WM_MOUSELEAVE(0x2A3)`에서 `hover_key = None`으로 바꾼 뒤 다시 그린다.

---

## 4. 수정 명세

### 4-1. `domain/timer_engine.py`

```python
def checkpoint_now(self) -> None:
    """종료·세션 종료 직전 강제 체크포인트 (H1·H6)."""
    if self.state in ACTIVE_STATES and self._seg is not None:
        self._checkpoint(self.clock.mono_ns(), self.clock.now_local())

def switch_subject(self, new_subject_id: int) -> None:
    """학습 중 과목 변경 (H3). 메모 창 없이 현재 체인을 확정하고 같은 모드로 새 체인을 시작한다."""
    if self.state not in (TimerState.RUNNING, TimerState.PAUSED) or self._seg is None:
        return
    if int(new_subject_id) == self.subject_id:
        return
    mode, total_s = self.mode, self.display_seconds()
    prev_subject = self.subject_id
    if total_s == 0 and self._seg.segment_no == 1:   # 0초 체인은 남기지 않음 (8장 D2)
        self.repo.delete_segment(self._seg.row_id)
        self._reset_to_stopped()                     # finalize()의 상태 초기화 부분을 분리한 헬퍼
    else:
        self.state = TimerState.FINALIZING           # finalize() 가드 통과
        self.finalize("", silent=True)               # Finished를 보내지 않음 (축하 애니메이션·효과음 생략)
    self.start(new_subject_id, mode)
    self.emit(SubjectSwitched(prev_subject, new_subject_id, total_s))
```
- `finalize()`에 `silent: bool = False` 인자를 추가하고, `silent=True`이면 `Finished` 대신 아무 이벤트도 보내지 않는다(축하 애니메이션·효과음 생략). `switch_subject`는 `finalize("", silent=True)`를 호출한다.
- `events.py`에 `SubjectSwitched(prev_subject_id, new_subject_id, saved_s)`를 추가한다. UI는 말풍선에 2초 토스트를 띄운다.
- `PAUSED` 상태에서 바꾸면 새 체인은 `RUNNING`으로 시작한다(사용자가 과목을 바꾼 것은 다시 공부하겠다는 뜻).

### 4-2. `ui/modals.py` — `ModalQueue`

```python
@dataclass
class ModalRequest:
    kind: Literal["recovery", "memo", "afk", "quit"]
    show: Callable[[], wt.HWND]          # 실제 창 생성
    default: Callable[[], None]          # 강제 닫기 시 호출 (AFK=제외, 메모=메모 없이, 복구=나중에, 종료=취소)

class ModalQueue:                        # 창 생성과 분리된 순수 로직 → tests/test_modal_queue.py
    PRIORITY = {"recovery": 0, "memo": 1, "afk": 2, "quit": 3}
    def push(self, req) -> None          # 활성 모달이 없으면 즉시 show, 있으면 우선순위 순으로 대기
    def on_closed(self) -> None          # 다음 요청 show
    def flush_defaults(self) -> None     # 종료 시: 활성 + 대기 전부 default() 호출 후 비움
```
- `_create_base_modal()` 맨 앞의 `self.close_active()`를 삭제한다. 교체는 일어나지 않는다.
- 같은 `kind`가 이미 대기 중이면 새 요청으로 대체한다(예: 종료 확인 2회).
- 복구 창 버튼: `IDOK=이어하기`, `3=여기까지 저장`, `4=폐기`, `IDCANCEL(X·Esc)=나중에 결정`. 폐기는 `MessageBoxW("이 기록({과목} {분}분)을 삭제할까요? 되돌릴 수 없습니다.", MB_YESNO|MB_ICONWARNING|MB_TOPMOST)` 재확인.
- 종료 확인 버튼: `IDOK=저장 후 종료`, `3=기록 유지하고 종료`, `IDCANCEL=취소`.

### 4-3. `app.py`

| 메서드 | 변경 |
|---|---|
| `_handle_select_subject` | 학습 중이면 `engine.switch_subject(id)`, 아니면 설정만 변경. 두 경우 모두 `_save_config_soon()` |
| `request_quit` `save_quit` | `self._quit_after_finalize = True; engine.stop()` → `FinalizeRequested`의 메모 창 `on_done`에서 `finalize(memo)` 후 플래그가 켜져 있으면 `shutdown()` |
| `request_quit` `keep_quit` | `engine.checkpoint_now(); shutdown()` |
| `_discard_current_session` | 삭제 |
| `shutdown(post_quit=True)` | ① `engine.checkpoint_now()` ② 설정 저장 ③ `modals.flush_defaults()` ④ 대시보드 ⑤ 트레이·핫키·사운드 ⑥ 펫 창 ⑦ `db.close()` ⑧ `post_quit`이면 `PostQuitMessage(0)`. 두 번 호출되면 무시(`_shut_down` 플래그) |
| `on_end_session` (신규) | `shutdown(post_quit=False)` — Windows가 곧 프로세스를 끝내므로 루프를 기다리지 않는다 |
| `_apply_new_config(patch: SettingsPatch)` | `self.config = patch.apply_to(self.config)` → 저장 → 반영 (M1) |
| `_handle_position_changed` | 메모리 반영 + `_save_config_soon()` (M2) |
| `_save_config_soon` (신규) | `SetTimer(pet.hwnd, TID_SAVE_CFG=6, 1000)` → 타이머에서 `KillTimer` 후 `config.save()` |
| 메시지 루프 | `for h in (modals.active_hwnd, dashboard.hwnd): if h and IsDialogMessageW(h, msg): break` (M3) |
| `_on_engine_event` | `SubjectSwitched` → `pet.show_toast(f"{이전과목} {h:mm:ss} 저장 → {새과목} 시작", 2.0)` / `AfkReturned` → `ModalQueue.push(afk)` |

### 4-4. `ui/pet_window.py`

| 대상 | 변경 |
|---|---|
| 상태 변수 | `radial_open`, `compact_open`, `radial_hover_key`, `_pressed_menu_item`, `_pressed_panel_btn` → `card_open`, `card_hover`, `card_pressed`, `_toast: tuple[str, float] \| None`, `_hint_until`, `_hover_since`, `_tracking_leave` |
| `_build_radial_menu_layer`, `_build_compact_panel_layer` | 삭제 → `_build_action_card_layer()` (3-4·3-5·3-7) |
| `_handle_lbutton_down` | 카드가 열려 있고 카드 버튼 위면 `card_pressed = key`. 캐릭터·말풍선 위면 기존 드래그 준비 |
| `_handle_lbutton_up` | 드래그가 아니었고 `card_pressed == hit`이며 활성 버튼이면 `_execute_card(key)`. 캐릭터·말풍선 클릭이면 `toggle_card()`. 말풍선 축소 토글 삭제 |
| `WM_RBUTTONUP` | 캐릭터·말풍선 위면 `toggle_card()` (좌클릭과 같음), 카드 위면 무시 |
| `WM_MOUSELEAVE` (신규) | 호버 해제·`_hover_since` 초기화·다시 그리기 |
| `WM_QUERYENDSESSION` / `WM_ENDSESSION` (신규) | 2-1 H6 |
| `_on_ui_timer` | 닫기 조건에 8초 미사용 반영. 힌트·토스트 만료 처리. 호버 0.8초 힌트 |
| `_execute_card(key)` | `primary` → `on_primary()` (시작·일시정지·이어하기·AFK 창 앞으로) / `end` → `on_stop_requested` / `subject` → 과목 팝업 / `mode` → 모드 팝업 / `stats`·`settings` → 대시보드 2·1 / `more` → 더보기 팝업 |
| `_desired_frame_interval_ms` | 이동 상태 `1000 // fps_limit` (L3). 카드가 열려 있어도 애니메이션 간격 유지(카드는 이벤트가 있을 때만 다시 그림) |
| 콜백 추가 | `on_primary`, `on_select_mode(str)`, `on_more_command(int)`, `on_card_opened()`(힌트 완료 저장) |

### 4-5. `ui/layout.py`

```python
CARD_BOX_SP = BoxSp(8, 0, 176, 78)

@dataclass(frozen=True)
class CardButton:
    key: str            # "primary" | "end" | "subject" | "mode" | "stats" | "settings" | "more"
    box: BoxSp
    label: str
    icon: str | None    # "start" | "pause" | None
    enabled: bool
    style: Literal["primary", "secondary", "footer"]

def card_header(state, phase, mode, subject, display_s, remain_s) -> tuple[str, str]   # (왼쪽, 오른쪽)
def card_buttons(state, phase, mode_label: str) -> list[CardButton]                    # 3-5 표 그대로
def hit_test_card(buttons, x_sp, y_sp) -> str | None                                   # 비활성 버튼은 None
```
- `RADIAL_*`, `PANEL_*`, `hit_test_radial_menu`, `hit_test_compact_panel`은 삭제한다. `assets/ui/menu_subjects|settings|stats*.png`는 쓰지 않게 되지만 다른 스킨 대비로 남겨 둔다.

### 4-6. 기타 파일

| 파일 | 변경 |
|---|---|
| `domain/events.py` | `SubjectSwitched` 추가 |
| `infra/config.py` | `hud.hint_shown: bool = False` 추가(검증: bool, 기본 False). `SettingsPatch` dataclass + `apply_to(cfg)` |
| `ui/tab_settings.py` | `on_apply(SettingsPatch)`로 변경 |
| `ui/dashboard.py` | `on_second_tick` → `tab_stats.refresh_live()`(캐시 + 라이브 합산만). 패널 창에 `WS_EX_CONTROLPARENT` |
| `ui/tab_stats.py` | `refresh_stats()`(DB 조회 + 캐시)와 `refresh_live()` 분리 |
| `win32/api.py` | `TRACKMOUSEEVENT(cbSize DWORD, dwFlags DWORD, hwndTrack HWND, dwHoverTime DWORD)`, `TrackMouseEvent(POINTER(TRACKMOUSEEVENT)) -> BOOL`, 상수 `TME_LEAVE=0x2, WM_MOUSELEAVE=0x2A3, WM_QUERYENDSESSION=0x11, WM_ENDSESSION=0x16, WM_RBUTTONDOWN=0x204, WS_EX_CONTROLPARENT=0x10000, WM_LBUTTONUP(트레이용) 재사용` |
| `win32/tray.py` | 메뉴 맨 위에 `학습 시작` / `일시정지` / `이어하기`(상태별 라벨) + 구분선 |
| `graphics/panel.py` | `fill_rect()` 추가 |
| `ui/popup.py` (신규) | `show_popup()` 공통 함수 (8장 D1). `pet_window._show_subject_popup_menu`와 `tray.show_popup_menu`가 이를 사용 |
| `strings.py` | 카드 라벨·헤더·힌트·토스트·버튼명(`기록 유지하고 종료`, `나중에 결정`) 추가, `BTN_*`(제어창) 삭제 |
| `assets/fonts/Galmuri11.ttf` | 동봉 (M5) |
| `scripts/package_portable.py` | 출력 `dist/build/StudyPet_Portable/`, 대상에 `data/`가 있으면 중단 (M6), 폰트 존재 검사 |
| `pet_window.log_perf_line` | 메뉴 지연은 60초 집계, 1MB 회전 (L4) |

---

## 5. 테스트 추가·변경

| 파일 | 케이스 |
|---|---|
| `tests/test_layout.py` (변경) | 상태 5종 × `card_buttons` 라벨·활성 여부 / 카드 상자가 캐릭터 상자와 겹치지 않음 / 모든 버튼이 카드 안 / 버튼끼리 겹치지 않음 / 비활성 버튼 히트 = `None` / 배율 1~4에서 `px_to_sp` 경계 |
| `tests/test_timer_engine.py` (추가) | `switch_subject`: 이전 체인 `is_completed=1`·메모 빈 값·`Finished` 미발행·`SubjectSwitched` 발행·새 체인 RUNNING / 같은 과목이면 무시 / PAUSED에서 전환 → RUNNING / `checkpoint_now`가 STOPPED에서 무동작 |
| `tests/test_modal_queue.py` (신규) | 활성 중 push → 대기 / 우선순위 순서 / 같은 kind 대체 / `flush_defaults`가 활성·대기 모두 기본값 호출 / AFK 대기 중 종료 → AFK 제외 처리 |
| `tests/test_config.py` (추가) | `hint_shown` 기본값·검증 / `SettingsPatch.apply_to`가 `last_position`·`last_subject_id`·`bubble_collapsed`를 보존 |
| `tests/test_recovery.py` (추가) | "나중에 결정"이 행을 그대로 둠 (엔진 호출 없음) |

수동 체크리스트(추가):

| 항목 | 방법 | 기준 |
|---|---|---|
| 단일 입구 | 좌클릭·우클릭으로 각각 카드 열기 | 같은 카드가 열림 |
| 상태별 카드 | 대기 → 시작 → 일시정지 → 이어하기 → 끝내기 | 3-5 표와 일치, 주 버튼 한 번으로 전환 |
| 과목 바꾸기 | 학습 중 과목 변경 | 메모 창이 뜨지 않고 토스트 표시, 통계에 두 과목 모두 기록 |
| 종료 안전성 | 학습 중 종료 → [기록 유지하고 종료] → 재실행 | 복구 창에 기록 존재 |
| 복구 창 X | 복구 창을 X로 닫고 재실행 | 같은 복구 창이 다시 뜸 |
| 모달 겹침 | AFK 창이 뜬 상태에서 트레이 → 완전 종료 → 취소 | AFK 창 유지, 결정 후 정상 재개 |
| Windows 로그오프 | 학습 중 로그오프 → 재로그인 실행 | 복구 창, 손실 ≤ 1초 |
| 첫 실행 힌트 | `data-dev` 삭제 후 실행 | 힌트 10초 표시, 카드 열면 이후 표시 안 함 |
| 포커스 유지 | 메모장에 입력하는 중 카드 조작(시작·일시정지) | 메모장 캐럿 유지 (팝업 메뉴 사용 시는 예외 — 8장 D1) |
| 팝업 위치 | 카드의 `과목 ▾`·`더보기 …` 클릭, 화면 네 모서리 근처에서 반복 | 메뉴가 버튼 바로 아래(또는 OS 보정 위치)에 뜨고, 바깥 클릭·Esc로 닫힘, 닫힌 뒤 카드 닫힘 상태 |
| 응답 속도 | `perf.log` 메뉴 지연 | 평균 ≤ 100ms (현재 1~2ms 수준 유지) |

---

## 6. 작업 순서와 일정

| 단계 | 내용 | 기간 | 완료 조건 |
|---|---|---|---|
| R0 | `dist/StudyPet_Portable/data/` 백업, 패키징 출력 경로 분리(M6) | 0.5일 | 백업 파일 확인 |
| R1 | 데이터 안전 수정: H1·H2·H4·H5·H6, M1·M2 (`engine.checkpoint_now`, `ModalQueue`, `SettingsPatch`, 종료 흐름) | 3일 | 5장 엔진·모달 큐·설정 테스트 통과, 수동 "종료 안전성·복구 창 X·모달 겹침·로그오프" 통과 |
| R2 | 엔진 `switch_subject` + H3 | 1일 | 테스트 통과, 수동 "과목 바꾸기" 통과 |
| R3 | 액션 카드: `layout.py` → `panel.fill_rect` → `pet_window.py` 입력·렌더 → 더보기·트레이 메뉴 → 힌트·토스트 | 4일 | 5장 레이아웃 테스트, 수동 "단일 입구·상태별 카드·첫 실행 힌트·포커스 유지" 통과 |
| R4 | 나머지: M3·M4·M5·L1~L4, 계획서 v0.7 반영(4-11 레이아웃, 4-12 메시지 표, 4-15 모달, 3-2 타이머 주기, Q8 결정 변경) | 1.5일 | 전체 단위 테스트 통과 |
| R5 | 재측정·재패키징 | 1일 | Phase 0 성능 기준(CPU < 2%, RAM ≤ 120MB, Cold Start ≤ 1.5s, present ≤ 3ms) 재통과, 서명 전수 `Valid` |

**합계 약 11일(2.2주).** 기존 12.5주 일정 안에서는 Phase 7 안정화 앞에 끼워 넣는다.

---

## 7. 결정 기록 변경 (승인 시 `DEVELOPMENT_PLAN.md` 12장 반영)

| # | 항목 | 변경 전 | 변경 후 |
|---|---|---|---|
| Q8 | 좌/우클릭 | 좌클릭 = 방사형 메뉴, 우클릭 = 컴팩트 제어창 | **좌·우클릭 모두 액션 카드 하나.** 목록·드문 기능은 Windows 기본 팝업 메뉴(8장 D1, 버튼 아래 고정 위치, 포커스 일시 이동 허용) |
| Q13 (신규) | 학습 중 과목 변경 | (미정, 코드는 메모 창 유령 표시) | 메모 없이 현재 체인 확정 → 새 체인 시작, 토스트 2초, 0초 체인은 삭제 (8장 D2) |
| Q14 (신규) | 종료 확인 두 번째 버튼 | (코드: 저장하지 않고 종료 = 삭제) | 기록 유지하고 종료 = 다음 실행 때 복구. 삭제 경로는 복구 창의 [폐기]+재확인뿐 |
| Q15 (신규) | 모달 동시 요청 | (코드: 기존 모달 무조건 교체) | 우선순위 대기열, 강제 종료 시 각 모달의 안전한 기본값 |

## 8. 확정된 결정 (2026-11-04, 제안안 채택)

| # | 항목 | 결정 | 구현 기준 |
|---|---|---|---|
| D1 | [더보기]·`과목 ▾`·`모드 ▾`·`과목 바꾸기 ▾` 목록 표시 방식 | **Windows 기본 팝업 메뉴(`TrackPopupMenu`) 사용.** 카드 내부 목록 그리기(+2일)는 채택하지 않음 | 아래 D1 규칙 |
| D2 | 학습 중 과목 변경 | **메모 창 없이 현재 체인 확정 → 같은 모드로 새 체인 시작 → 말풍선 토스트 2초** (Q13) | 4-1 `switch_subject`, 4-3 `_handle_select_subject` |

**D1 구현 규칙** (기존 `_show_subject_popup_menu`와 트레이 메뉴의 검증된 순서를 공통 함수로 묶는다):

```python
# ui/popup.py (신규)
def show_popup(hwnd, items: list[tuple[int, str, int]], anchor_px: tuple[int, int] | None = None) -> int:
    """items: (명령 ID, 라벨, MF_* 플래그). 0 = 취소. 반환 후 호출자가 명령 실행."""
    hmenu = user32.CreatePopupMenu()
    try:
        for cid, label, flags in items:
            user32.AppendMenuW(hmenu, flags, cid, label if not (flags & MF_SEPARATOR) else None)
        x, y = anchor_px or cursor_pos()
        user32.SetForegroundWindow(hwnd)                       # 없으면 바깥 클릭 시 메뉴가 닫히지 않음
        cmd = int(user32.TrackPopupMenu(hmenu, TPM_RETURNCMD | TPM_RIGHTBUTTON | TPM_NONOTIFY,
                                        x, y, 0, hwnd, None))
        user32.PostMessageW(hwnd, WM_NULL, 0, 0)               # 알려진 메뉴 잔류 문제 회피
        return cmd
    finally:
        user32.DestroyMenu(hmenu)
```

- **위치:** 카드 버튼에서 연 메뉴는 커서가 아니라 **해당 버튼의 왼쪽 아래 모서리**(화면 px)에 띄운다. `anchor = (win_x + box.x·s, win_y + (box.y + box.h)·s)`. 화면 밖으로 넘치는 경우는 OS가 위치를 보정한다.
- **카드 상태:** 메뉴를 띄우기 직전에 카드를 닫고 다시 그린다(`card_open = False`). `TrackPopupMenu`는 메뉴가 닫힐 때까지 반환하지 않으므로, 메뉴가 떠 있는 동안 `TID_UI`의 카드 닫기·호버 판정이 꼬이지 않게 하기 위해서다. 반환 후 명령이 있으면 실행하고, 취소(0)면 아무것도 하지 않는다.
- **명령 ID 범위:** 과목 `1000 + subject_id`, 모드 `2001`(뽀모도로)·`2002`(스톱워치), 더보기 `3001~3005`, `과목 관리…` `3010`. 과목 ID를 그대로 쓰던 기존 방식은 더보기 ID와 겹칠 수 있으므로 바꾼다.
- **포커스:** 메뉴를 쓰는 동안에는 포커스가 펫 창으로 넘어온다. 메뉴가 닫힌 뒤 이전 앱으로 포커스를 **되돌리지 않는다**. 되돌리면 `SetForegroundWindow` 제한에 걸려 작업 표시줄이 깜박일 수 있다. 사용자가 공부하던 창을 한 번 클릭하면 된다. 5장 수동 체크리스트의 "포커스 유지" 예외로 명시한다.
- **유령 모드·모달 잠금:** `modal_locked` 상태이거나 유령 모드이면 메뉴를 띄우지 않는다.

**D2 구현 규칙:**

- 토스트 문구는 `"{이전 과목} {h:mm:ss} 저장 → {새 과목} 시작"`이다(`strings.format_switch_toast`). 이전 체인이 0초면 `"{새 과목}(으)로 바꿨어요"`로 표시하고, 0초 체인은 저장하지 않고 삭제한다(`delete_segment`, 미완료 행만 해당).
- 토스트는 카드가 닫혀 있을 때 말풍선 자리에 2초간 표시하고, 그동안 일반 말풍선보다 우선한다.
- 효과음은 `start`만 재생하고 `celebrate`는 재생하지 않는다(`finalize(silent=True)`).
- `PAUSED`에서 과목을 바꾸면 새 체인은 `RUNNING`으로 시작한다. `PAUSED_AFK`·`FINALIZING`에서는 과목 바꾸기 버튼을 비활성화한다(3-5 표).
- 메모는 바뀐 이전 체인에 남지 않는다. 필요하면 기록 탭에서 편집한다(범위 밖, v1.1 후보).

**D2에 따른 추가 테스트** (`tests/test_timer_engine.py`): 0초 체인에서 전환 → 이전 행 삭제, 새 체인 1개 / `PAUSED_AFK`에서 `switch_subject` 호출 → 무시.

## 9. 구현 후 교차검증 결과와 후속 수정 (2026-11-04)

정적 검토로 아래 결함을 찾아 수정했다. V1은 사용 중인 `data/logs/crash.log`에서 실제 발생이 확인되었다(10:11, 5회).

| # | 등급 | 위치 | 결함 | 수정 |
|---|---|---|---|---|
| V1 | 높음 | `app.py` `_handle_tray_menu` | `tray.show_popup_menu()`를 옛 인자(`study_action_label`)로 호출해 `TypeError`. 트레이 우클릭 메뉴가 뜨지 않음 | `engine_state`·`on_primary`로 호출 |
| V2 | 높음 | `app.py` `_process_next_recovery_row` | `show_recovery_modal()`에 `discard_confirm_msg`를 넘기고 `subject_name`·`duration_s`를 빠뜨려 `TypeError`. 복구 창이 뜨지 않아 H1·H2가 실제로 작동하지 않음 | 시그니처대로 호출, 중복 문구 생성 제거 |
| V3 | 중간 | `modals.py` `_finish` | 결과 콜백 실행 후에 활성 모달을 해제해, 콜백 안에서 종료하면 끝난 모달의 기본값이 다시 호출됨 | `ModalQueue.begin_release()`/`end_release()`: 콜백 전에 해제, 콜백 중 요청은 대기열에 넣고 우선순위대로 표시 |
| V4 | 중간 | `ModalQueue.flush_defaults` | 종료 중 복구 '나중에 결정' 기본값이 다음 복구 창을 새로 띄움 | `closing` 상태에서는 새 요청을 창 없이 기본값으로 즉시 처리 |
| V5 | 중간 | `ModalQueue.push` | `show()` 예외 시 활성 표시가 남아 이후 모든 모달이 대기열에 갇힘 | 예외 시 기본값 처리 후 다음 요청으로 진행 |
| V6 | 중간 | `timer_engine.switch_subject` | 저장 실패 시 메모 창 없는 `FINALIZING`에 갇힘. 새 체인 생성 실패에도 전환 토스트 표시 | 저장 실패 → 이전 상태 복원, 시작 실패 → `SubjectSwitched` 미발행 |
| V7 | 낮음 | `pet_window._on_ui_timer` | 100ms 폴링이라 짧은 바깥 클릭을 놓쳐 카드가 8초 뒤에야 닫힘. 캔버스 투명 영역 클릭은 바깥으로 보지 않음 | `GetAsyncKeyState & 0x8001`(직전 호출 이후 눌림)을 매 틱 확인, 카드를 열 때 비트 초기화. 카드·캐릭터 밖이면 바깥 클릭 |
| V8 | 낮음 | `pet_window` 모달 잠금 | AFK 창이 떠 있으면 카드가 열리지 않아 [확인 창 열기]에 닿을 수 없음 | 모달이 떠 있을 때 캐릭터·말풍선 클릭(좌·우, 트레이 좌클릭) = 그 모달을 앞으로 (`on_locked_click`) |
| V9 | 낮음 | 더보기·트레이 메뉴, `DEVELOPMENT_PLAN.md` | `MF_CHECKED`와 라벨의 `✓`가 겹쳐 체크가 두 번 보임. 계획서 틱 주기 표기 200ms 잔존 | 라벨에서 `✓` 제거(`*_CHECKED` 문자열 삭제). 계획서 567·609행을 250ms로 갱신 |

**재발 방지:** `tests/test_wiring.py` 추가. 소스를 AST로 읽어 `app.py`의 `self.tray/modals/pet/engine/dashboard.<메서드>()` 호출과 UI 모듈의 전역 함수·클래스 호출을 실제 시그니처에 `bind()`한다(창 생성·앱 실행 없음). V1·V2의 원래 호출 형식을 넣으면 실패함을 확인했다.

**추가 테스트:** `test_modal_queue.py` 4건(콜백 중 종료, 콜백 중 요청 우선순위, 종료 중 요청, `show()` 실패), `test_timer_engine.py` 2건(저장 실패 복원, 시작 실패 시 토스트 없음).

**남은 일:** `scripts/package_portable.py` 재실행 후 `dist/build/StudyPet_Portable/studypet.zip`을 사용 중인 폴더에 반영. 수동 체크리스트(5장)의 "종료 안전성·복구 창 X·모달 겹침" 재확인.
