"""StudyPet 부트스트랩. StudyPet.exe(이름 변경된 pythonw.exe)를 인자 없이 실행했을 때만 앱을 기동한다."""
import os
import site
import sys

# 포터블 격리: 사용자 PC에 %APPDATA%\Python\Python312\site-packages가 존재하더라도 sys.path에서 제거 (AC#4)
site.ENABLE_USER_SITE = False
if getattr(site, "USER_SITE", None):
    _user_site_norm = os.path.normcase(os.path.abspath(site.USER_SITE))
    sys.path[:] = [
        p for p in sys.path
        if os.path.normcase(os.path.abspath(p)) != _user_site_norm
    ]


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
