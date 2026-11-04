"""StudyPet 무설치 포터블 배포판 패키징 및 Authenticode 서명 전수 검증 스크립트 (DEVELOPMENT_PLAN.md 6장)."""
from __future__ import annotations

import argparse
from pathlib import Path
import py_compile
import shutil
import subprocess
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SRC = ROOT / "runtime" / "python-3.12-amd64"
SRC_DIR = ROOT / "src" / "studypet"
ASSETS_DIR = ROOT / "assets"
BOOTSTRAP_FILE = ROOT / "bootstrap" / "sitecustomize.py"
DIST_ROOT = ROOT / "dist"


DEPLOY_PTH_CONTENT = """python312.zip
.
studypet.zip
import site
"""

GUIDE_TXT_CONTENT = """====================================================================
  StudyPet (2D 도트 데스크톱 펫 학습 타이머) — 포터블 실행 가이드
====================================================================

1. 압축 해제 위치 안내
   - 바탕화면, 문서, D: 드라이브, 또는 USB 메모리 등 일반 사용자 쓰기 권한이 있는
     폴더에 압축을 풀어 주세요.
   - OneDrive / Dropbox 등 실시간 클라우드 동기화 폴더 내부는 데이터베이스 잠금 충돌이
     발생할 수 있으므로 권장하지 않습니다.

2. 첫 실행 방법
   - 폴더 안의 `StudyPet.exe`를 더블 클릭하면 화면 우측 하단에 도트 고양이 펫이 나타납니다.
   - 별도의 설치 과정이나 관리자 권한 승인이 필요하지 않으며, 첫 실행 시 같은 폴더 안에
     `data/` 폴더가 자동으로 생성됩니다.

3. 기본 조작법
   - 캐릭터 또는 말풍선 클릭(좌클릭/우클릭 동일): 액션 카드 열기 / 닫기
     · 주 버튼: 학습 시작 / 일시정지 / 이어하기
     · 보조 버튼: 끝내기 / 과목 바꾸기 ▾ / 모드 ▾
     · 하단 버튼: 기록 / 설정 / 더보기 … (과목 관리, 말풍선 간단히 보기, 유령 모드, 소환, 종료)
   - 캐릭터 드래그: 원하는 모니터나 위치로 이동 (공중에서 놓으면 바닥으로 착지)
   - 트레이 아이콘 좌클릭: 캐릭터 소환 + 액션 카드 열기
   - 트레이 아이콘 우클릭: 트레이 빠른 메뉴 열기

4. 유령 모드 (투명·클릭 투과 모드)
   - 켜기/끄기:
     ① 전역 단축키 `Ctrl + Alt + G` (설정 탭에서 변경 가능)
     ② 작업 표시줄 시스템 트레이의 StudyPet 아이콘 우클릭 -> `[유령 모드]` 클릭
     ③ 보조 방법: `Alt` 키를 누른 채 캐릭터 위에 마우스를 올리고 `Alt + 마우스 휠` 스크롤

5. 데이터 백업 및 PC 이동 (100% 포터블)
   - 모든 설정(`config.json`), 학습 기록 DB(`study_records.db`), 내보낸 CSV(`exports/`),
     로그(`logs/`)는 `data/` 폴더 안에만 저장됩니다 (`%APPDATA%`나 레지스트리를 사용하지 않음).
   - 다른 PC나 USB로 옮길 때 `StudyPet_Portable` 폴더 전체(또는 `data/` 폴더)를 그대로
     복사하면 모든 기록이 유지됩니다.

6. Windows 보안(SmartScreen / 스마트 앱 컨트롤 / 백신) 안내
   - `StudyPet.exe`는 Python Software Foundation(PSF)이 공식 전자서명한 `pythonw.exe`
     원본 바이너리이며, 동봉된 모든 `.dll`/`.pyd` 파일 역시 정식 서명되어 있어
     Windows 스마트 앱 컨트롤(SAC) 강제 모드에서도 차단 없이 실행됩니다.
   - 만약 인터넷에서 다운로드한 ZIP 파일에 대해 Windows SmartScreen 안내 창이 표시되면,
     ZIP 파일 우클릭 -> [속성] -> 하단 [차단 해제] 체크 후 [확인]을 누른 뒤 압축을 해제하세요.
"""


def build_studypet_zip(out_zip_path: Path) -> int:
    """src/studypet/**/*.py 및 UNCHECKED_HASH 모드로 컴파일한 .pyc를 __pycache__ 없이 studypet.zip에 패키징한다."""
    for forbidden in SRC_DIR.rglob("*"):
        if forbidden.suffix.lower() in (".pyd", ".dll", ".exe"):
            raise RuntimeError(f"Forbidden native binary found in src/: {forbidden}")

    file_count = 0
    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        with zipfile.ZipFile(out_zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for py_file in sorted(SRC_DIR.rglob("*.py")):
                rel_to_src = py_file.relative_to(ROOT / "src")
                arc_py = rel_to_src.as_posix()
                arc_pyc = rel_to_src.with_suffix(".pyc").as_posix()

                zf.write(py_file, arcname=arc_py)
                file_count += 1

                compiled_pyc = tmp_dir / f"{file_count}.pyc"
                py_compile.compile(
                    str(py_file),
                    cfile=str(compiled_pyc),
                    dfile=arc_py,
                    doraise=True,
                    invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH,
                )
                zf.write(compiled_pyc, arcname=arc_pyc)
                file_count += 1

    return file_count


def verify_authenticode_all_pe(target_dir: Path) -> list[tuple[str, str]]:
    """target_dir 내의 모든 .exe/.dll/.pyd 파일의 Authenticode 서명 상태를 전수 검사한다."""
    pe_files = sorted(
        p for p in target_dir.rglob("*") if p.is_file() and p.suffix.lower() in (".exe", ".dll", ".pyd")
    )
    if not pe_files:
        raise RuntimeError(f"No PE files found in {target_dir}")

    ps_paths = ",".join(f"'{str(p.resolve()).replace(chr(39), chr(39)*2)}'" for p in pe_files)
    ps_cmd = (
        f"$files = @({ps_paths}); "
        "foreach ($f in $files) { "
        "$sig = Get-AuthenticodeSignature -LiteralPath $f; "
        "Write-Output \"$($sig.Status)|$f\" "
        "}"
    )
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
        capture_output=True,
        text=True,
        check=True,
    )
    results: list[tuple[str, str]] = []
    invalid: list[tuple[str, str]] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        status, fpath = line.split("|", 1)
        results.append((fpath, status))
        if status != "Valid":
            invalid.append((fpath, status))

    if invalid:
        raise RuntimeError(f"Authenticode verification failed for {len(invalid)} file(s): {invalid}")

    return results


def package_portable(version: str) -> Path:
    if not RUNTIME_SRC.exists():
        raise FileNotFoundError(f"Official embeddable runtime not found: {RUNTIME_SRC}")

    out_dir = DIST_ROOT / "build" / "StudyPet_Portable"
    if (out_dir / "data").exists():
        raise RuntimeError(
            f"Packaging aborted: user data directory exists at '{out_dir / 'data'}'. "
            "Move or back up 'data/' before running package_portable.py."
        )
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1~2. 런타임 파일 복사 (python.exe, pythonw.exe, python312._pth 제외, pythonw.exe -> StudyPet.exe 복사)
    excluded_names = {"python.exe", "pythonw.exe", "python312._pth"}
    for item in RUNTIME_SRC.iterdir():
        if item.name.lower() in excluded_names:
            continue
        if item.is_file():
            shutil.copy2(item, out_dir / item.name)

    shutil.copy2(RUNTIME_SRC / "pythonw.exe", out_dir / "StudyPet.exe")

    # 3. 배포용 python312._pth 및 sitecustomize.py 복사
    (out_dir / "python312._pth").write_text(DEPLOY_PTH_CONTENT, encoding="utf-8")
    shutil.copy2(BOOTSTRAP_FILE, out_dir / "sitecustomize.py")

    # 4. studypet.zip 생성 (.py + .pyc)
    packed_count = build_studypet_zip(out_dir / "studypet.zip")

    # 5. assets/ 복사
    shutil.copytree(ASSETS_DIR, out_dir / "assets")

    # 6. 실행 가이드.txt 작성
    (out_dir / "실행 가이드.txt").write_text(GUIDE_TXT_CONTENT, encoding="utf-8")

    # 7. 검증: Authenticode 서명 전수 검사, ._pth import site 확인, data/ 폴더 부재 확인, 폰트 존재 확인
    pth_text = (out_dir / "python312._pth").read_text(encoding="utf-8")
    if "import site" not in pth_text.splitlines():
        raise RuntimeError("python312._pth is missing 'import site'")
    if (out_dir / "data").exists():
        raise RuntimeError("dist/build/StudyPet_Portable must not contain a pre-existing 'data/' directory")
    if not (out_dir / "LICENSE.txt").exists():
        raise RuntimeError("Python LICENSE.txt is missing from portable package")
    if not (out_dir / "assets" / "fonts" / "Galmuri11.ttf").exists():
        raise RuntimeError("Bundled pixel font 'assets/fonts/Galmuri11.ttf' is missing from portable package")

    sig_results = verify_authenticode_all_pe(out_dir)
    print(f"[package_portable] PE 서명 전수 검사 통과: {len(sig_results)}개 파일 모두 Status == Valid")
    print(f"[package_portable] studypet.zip 패키징 완료: {packed_count}개 항목 (.py + .pyc)")

    # 8. dist/StudyPet_Portable_v{version}.zip 생성
    zip_path = DIST_ROOT / f"StudyPet_Portable_v{version}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for file_path in sorted(out_dir.rglob("*")):
            if file_path.is_file():
                arcname = Path("StudyPet_Portable") / file_path.relative_to(out_dir)
                zf.write(file_path, arcname=arcname.as_posix())

    print(f"[package_portable] 포터블 배포 ZIP 생성 완료: {zip_path}")
    return zip_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Package StudyPet Portable distribution")
    parser.add_argument("--version", default="1.0.0", help="Release version string (default: 1.0.0)")
    args = parser.parse_args()
    package_portable(args.version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

