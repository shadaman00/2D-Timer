#Requires -Version 5.1
param(
    [string]$ProcessName = "StudyPet",
    [int]$DurationSeconds = 10,
    [int]$IntervalSeconds = 1,
    [string]$OutputCsv = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutputCsv) {
    $LogsDir = Join-Path $ProjectRoot "data-dev\logs"
    New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null
    $OutputCsv = Join-Path $LogsDir "perf_samples.csv"
}

$LogicalCores = [Environment]::ProcessorCount
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($OutputCsv, "timestamp,pid,cpu_percent,working_set_mb,private_mb`r`n", $Utf8NoBom)

$PrevCpu = @{}
$PrevTime = @{}

for ($i = 0; $i -lt $DurationSeconds; $i += $IntervalSeconds) {
    $Now = Get-Date
    $Procs = Get-Process -Name $ProcessName -ErrorAction SilentlyContinue
    foreach ($p in $Procs) {
        $pidVal = $p.Id
        $cpuTotal = $p.TotalProcessorTime.TotalSeconds
        $wsMb = [Math]::Round($p.WorkingSet64 / 1MB, 2)
        $privMb = [Math]::Round($p.PrivateMemorySize64 / 1MB, 2)
        $cpuPct = 0.0

        if ($PrevCpu.ContainsKey($pidVal)) {
            $dt = ($Now - $PrevTime[$pidVal]).TotalSeconds
            if ($dt -gt 0) {
                $dCpu = $cpuTotal - $PrevCpu[$pidVal]
                $cpuPct = [Math]::Round(($dCpu / ($dt * $LogicalCores)) * 100.0, 2)
            }
        }
        $PrevCpu[$pidVal] = $cpuTotal
        $PrevTime[$pidVal] = $Now

        $tsStr = $Now.ToString("yyyy-MM-ddTHH:mm:ss")
        $line = "$tsStr,$pidVal,$cpuPct,$wsMb,$privMb`r`n"
        [System.IO.File]::AppendAllText($OutputCsv, $line, $Utf8NoBom)
    }
    Start-Sleep -Seconds $IntervalSeconds
}

Write-Host "[perf_monitor] 완료: $OutputCsv"

