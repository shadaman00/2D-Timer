# 📊 Phase 0 — 기술 검증 PoC 결과 보고서 (Go/No-Go)

**측정 일시:** 2026-11-03  
**기준 문서:** [DEVELOPMENT_PLAN.md](file:///d:/0MY/SOURCE/2D-Timer/DEVELOPMENT_PLAN.md) (v0.6, 5장 Phase 0)  
**실행 환경:** Windows 11 (x64, 스마트 앱 컨트롤 강제 모드 `VerifiedAndReputablePolicyState = 1`)  
**최종 판정:** 🟢 **GO (12개 전 항목 통과)**

---

## 1. Phase 0 산출물 목록

| 단계 | 파일 경로 | 구현 및 검증 내용 |
|---|---|---|
| 0-1 | [scripts/setup_dev_runtime.ps1](file:///d:/0MY/SOURCE/2D-Timer/scripts/setup_dev_runtime.ps1) | 원본 `runtime/python-3.12-amd64` 무수정 복사 → `runtime/dev/` 생성, `StudyPet.exe`, `python312._pth`, `studypet_dev_root.txt` 구성 및 서명 검증 |
| 0-2 | [bootstrap/sitecustomize.py](file:///d:/0MY/SOURCE/2D-Timer/bootstrap/sitecustomize.py)<br>[src/studypet/__main__.py](file:///d:/0MY/SOURCE/2D-Timer/src/studypet/__main__.py)<br>[src/studypet/crashlog.py](file:///d:/0MY/SOURCE/2D-Timer/src/studypet/crashlog.py) | `StudyPet.exe` 인자 없는 실행 시에만 자동 기동하는 이중 가드, `%APPDATA%\Python` 사용자 site-packages 격리, `os._exit()` 종료 및 크래시 로거 |
| 0-3 | [src/studypet/win32/api.py](file:///d:/0MY/SOURCE/2D-Timer/src/studypet/win32/api.py)<br>[src/studypet/win32/monitors.py](file:///d:/0MY/SOURCE/2D-Timer/src/studypet/win32/monitors.py)<br>[src/studypet/win32/audio.py](file:///d:/0MY/SOURCE/2D-Timer/src/studypet/win32/audio.py)<br>[src/studypet/win32/actctx.py](file:///d:/0MY/SOURCE/2D-Timer/src/studypet/win32/actctx.py)<br>[src/studypet/graphics/dib.py](file:///d:/0MY/SOURCE/2D-Timer/src/studypet/graphics/dib.py) | 64-bit 안전 Win32 바인딩, Per-Monitor DPI v2, `PlaySoundW` 메모리 비동기 재생, comctl32 v6 활성화 컨텍스트, Top-Down 32bpp `DibSurface` |
| 0-4 | [poc/poc_pet.py](file:///d:/0MY/SOURCE/2D-Timer/poc/poc_pet.py)<br>[poc/verify_phase0.py](file:///d:/0MY/SOURCE/2D-Timer/poc/verify_phase0.py) | 코드로 그린 64×64 도트 고양이(알파 0/255), 좌우 보행, `SetCapture` 드래그, 클릭 시 메뉴 토글+사운드, 30/60FPS 전환, 유령 모드, 성능 로깅 |
| 0-5 | [poc/clickgrid.html](file:///d:/0MY/SOURCE/2D-Timer/poc/clickgrid.html) | 2px 정밀 격자 링크 페이지 (AC#1 브라우저 클릭 투과 시연용) |
| 0-6 | [scripts/perf_monitor.ps1](file:///d:/0MY/SOURCE/2D-Timer/scripts/perf_monitor.ps1) | 프로세스별 1초 주기 CPU%·Working Set·Private Memory CSV 로거 |

---

## 2. Go/No-Go 검증 항목별 실측 결과표

| # | 확인 항목 | 통과 기준 | 실측 결과 | 판정 |
|---|---|---|---|---|
| 1 | 부트스트랩 가드 동작 | `StudyPet.exe` 기동 / `python.exe -c pass` 미기동 / 종료 코드 `0` | `StudyPet.exe`: `guard_ran=True, exit=0`<br>`python.exe -c pass`: `guard_ran=False, exit=0` | ✅ **PASS** |
| 2 | `._pth` 사용자 site-packages 격리 | `%APPDATA%\Python` 미사용 (`site.ENABLE_USER_SITE == False`) | `enable_user_site: false`, `user_site_in_sys_path: false` | ✅ **PASS** |
| 3 | 클릭 투과 2px 정밀도 (AC#1) | 배율 100/125/150%에서 몸통=`Pet`, 외곽 +1px/+2px=` 뒤 창` | 96·120·144 DPI 전 구간에서 몸통 및 외곽 끝 픽셀은 `StudyPetPet` 적중, +1px·+2px 밖은 뒤쪽 타깃 창 100% 적중 | ✅ **PASS** |
| 4 | Cold Start (`GetProcessTimes` ~ 첫 렌더) | ≤ 1,500 ms | **`126.45 ms`** (약 0.13초, 기준 대비 11배 빠름) | ✅ **PASS** |
| 5 | CPU 점유율 (Idle·Walk, 30FPS) | 평균 < 2.0% | **`평균 0.74%`** (샘플: `0.38%, 0.00%, 0.97%, 0.77%, 1.73%, 0.58%`) | ✅ **PASS** |
| 6 | RAM (Working Set) | ≤ 120 MB | **`26.32 MB`** (Private Memory `15.62 MB`, 기준의 22% 수준) | ✅ **PASS** |
| 7 | `present()` 평균 합성·출력 시간 | 배율 2·4 모두 ≤ 3.0 ms | `scale=2`: **`0.100 ms`** / `scale=4`: **`0.266 ms`** (실기동 평균 `0.916 ms`) | ✅ **PASS** |
| 8 | ctypes `PlaySoundW` 메모리 비동기 재생 | `SND_MEMORY \| SND_ASYNC \| SND_NODEFAULT` 정상 동작 | `playsound_memory_async_ok: true` (재생 및 볼륨 스케일링 정상) | ✅ **PASS** |
| 9 | 비활성 창의 `Alt+휠` 수신 및 `Alt` 부작용 | 동작 확인 및 기록 | 비활성(`WS_EX_NOACTIVATE`) 창에서도 커서 호버 시 `WM_MOUSEWHEEL` 정상 수신. 단, 타 앱 포커스 중 `Alt` 단독 키업 시 전면 창 메뉴바 포커스가 발생할 수 있으므로 `Ctrl+Alt+G` 및 트레이 메뉴를 주 해제 경로로 유지하고 `Alt+휠`은 보조 경로로 유지 | ✅ **PASS** |
| 10 | comctl32 v6 활성화 컨텍스트 | `CreateActCtxW` + `ActivateActCtx` 성공 여부 기록 | `assets/studypet.manifest` 로드 및 `comctl_v6_activated: true` 확인 (현대적 비주얼 스타일 사용 가능) | ✅ **PASS** |
| 11 | SAC 강제 모드 & Defender 호환성 | PE 서명 `Valid`, 실행 시 차단/경고 없음 | 31개 PE 파일 및 `StudyPet.exe` 서명 `Valid`, SAC 강제 모드에서 차단 없이 즉시 실행 | ✅ **PASS** |
| 12 | Python 런타임 버전 결정 | 3.12.8 유지 여부 결정 | `python-3.12.8-embed-amd64` 유지 확정 (서명 무결성·성능·안정성 검증 완료) | ✅ **PASS** |

---

## 3. 세부 실측 로그 발췌

### 3-1. `StudyPet.exe` 실기동 리소스 샘플 (`data-dev/logs/perf_samples.csv`)
```csv
timestamp,pid,cpu_percent,working_set_mb,private_mb
2026-11-03T16:30:37,24816,0,19.17,10.55
2026-11-03T16:30:38,24816,0.38,26.32,15.62
2026-11-03T16:30:39,24816,0,26.32,15.62
2026-11-03T16:30:40,24816,0.97,26.32,15.62
2026-11-03T16:30:41,24816,0.77,26.32,15.62
2026-11-03T16:30:42,24816,1.73,26.32,15.62
2026-11-03T16:30:43,24816,0.58,26.32,15.62
```

### 3-2. `perf.log` 기록
```json
{"ts": "2026-11-03T16:30:37", "event": "cold_start", "cold_start_ms": 126.45, "scale": 4}
{"ts": "2026-11-03T16:30:45", "event": "shutdown_summary", "render_ms_avg": 0.916, "frames_rendered": 170}
```

