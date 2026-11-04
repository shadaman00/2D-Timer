#Requires -Version 5.1
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$SrcRuntime  = Join-Path $ProjectRoot "runtime\python-3.12-amd64"
$DevRuntime  = Join-Path $ProjectRoot "runtime\dev"

if (-not (Test-Path $SrcRuntime)) {
    throw "원본 런타임 폴더가 존재하지 않습니다: $SrcRuntime"
}

if (Test-Path $DevRuntime) {
    Remove-Item -Path $DevRuntime -Recurse -Force
}
New-Item -ItemType Directory -Path $DevRuntime -Force | Out-Null

# 1. 원본 런타임 파일 전체 복사 (원본 수정 금지)
Copy-Item -Path (Join-Path $SrcRuntime "*") -Destination $DevRuntime -Recurse -Force

# 2. pythonw.exe -> StudyPet.exe 복사
Copy-Item -Path (Join-Path $DevRuntime "pythonw.exe") -Destination (Join-Path $DevRuntime "StudyPet.exe") -Force

# 3. 개발용 python312._pth 작성 (UTF-8 No BOM)
$PthLines = @(
    "python312.zip",
    ".",
    "..\..\src",
    "..\..\bootstrap",
    "import site"
)
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllLines((Join-Path $DevRuntime "python312._pth"), $PthLines, $Utf8NoBom)

# 4. 개발 루트 마커 파일 작성
[System.IO.File]::WriteAllText((Join-Path $DevRuntime "studypet_dev_root.txt"), "..\..", $Utf8NoBom)

# 5. 서명 확인
$Sig = Get-AuthenticodeSignature -LiteralPath (Join-Path $DevRuntime "StudyPet.exe")
Write-Host "[setup_dev_runtime] 완료: $DevRuntime"
Write-Host "[setup_dev_runtime] StudyPet.exe Signature Status: $($Sig.Status) ($($Sig.SignerCertificate.Subject))"
if ($Sig.Status -ne "Valid") {
    throw "StudyPet.exe 서명이 유효하지 않습니다: $($Sig.Status)"
}

