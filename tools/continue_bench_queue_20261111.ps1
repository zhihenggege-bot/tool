param([int] $AfterProcess, [switch] $AfterPair22, [switch] $ResumeAfterPause)
$ErrorActionPreference = 'Stop'
$benchPy = 'C:/Users/Administrator/AppData/Local/Programs/Python/Python312/python.exe'
$workspace = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $workspace
$evidence = Join-Path $workspace '测试证据/台架执行_20261111'
$journal = Join-Path $evidence ('continuation_' + (Get-Date -Format HHmmss) + '.log')

function Write-Journal([string] $Message) {
    $line = "$(Get-Date -Format o) $Message"
    Add-Content -LiteralPath $journal -Value $line -Encoding utf8
    Write-Output $line
}

function Invoke-BoardAudit {
    for ($auditAttempt=1; $auditAttempt -le 3; $auditAttempt++) {
        & $benchPy -X utf8 -u tools/audit_shared_type_board_20261110.py
        if ($LASTEXITCODE -eq 0) { return }
        Write-Journal "Recovery audit attempt $auditAttempt failed; retry before any start"
        Start-Sleep -Seconds 2
    }
    throw 'Independent board recovery check failed after three attempts; do not issue the next start'
}

function Invoke-BenchCase([string] $Script, [string] $Argument, [bool] $PressureFixture = $false) {
    if (Test-Path -LiteralPath (Join-Path $workspace '.codex-tmp/continuous_v1055_pause.request')) {
        throw 'User pause request present; no next case'
    }
    Write-Journal "START $Script $Argument"
    if ($Argument) { & $benchPy -X utf8 -u $Script $Argument }
    else { & $benchPy -X utf8 -u $Script }
    $caseExit = $LASTEXITCODE
    Invoke-BoardAudit
    if ($PressureFixture) {
        & $benchPy -X utf8 -u tools/restore_b03_ai_20261111.py
        if ($LASTEXITCODE -ne 0) { throw 'Pressure fixture span restoration could not be verified' }
    }
    Write-Journal "END $Script $Argument EXIT=$caseExit RECOVERY_VERIFIED=1"
    & $benchPy -X utf8 -u tools/record_bench_queue_20261111.py
}

try {
    if ($AfterProcess) {
        Write-Journal "WAIT FOR prior controller PID $AfterProcess"
        $prior = Get-Process -Id $AfterProcess -ErrorAction SilentlyContinue
        if ($prior) { Wait-Process -InputObject $prior -Timeout 1800 }
    }
    Invoke-BoardAudit
    & $benchPy -X utf8 -u tools/restore_b03_ai_20261111.py
    if ($LASTEXITCODE -ne 0) { throw 'Pressure fixture span restoration could not be verified' }
    if ($ResumeAfterPause) {
        Write-Journal 'RESUME interrupted dispatch5 after recovery; earlier completed batches retained'
        Invoke-BenchCase 'tools/bench_extra_20261111.py' 'dispatch5'
    } else {
        $pairs=if($AfterPair22){@('24')}else{@('13','22','24')}
        foreach ($pair in $pairs) { Invoke-BenchCase 'tools/bench_b03_fixed_vfd_20261111.py' $pair $true }
        foreach ($kind in @('0','1')) { Invoke-BenchCase 'tools/bench_b03_type_i_20261111.py' $kind }
        foreach ($kind in 1..7) { Invoke-BenchCase 'tools/bench_extra_20261111.py' "contact$kind" }
        foreach ($kind in 0..5) { Invoke-BenchCase 'tools/bench_extra_20261111.py' "dispatch$kind" }
    }
    Invoke-BenchCase 'tools/bench_extra_20261111.py' 'heatfans'
    foreach ($kind in @('0','1','2')) { Invoke-BenchCase 'tools/bench_b04_ambient_20261111.py' $kind }
    Invoke-BenchCase 'tools/bench_b05_normal_defrost_20261111.py' ''
    Invoke-BenchCase 'tools/bench_extra_20261111.py' 'emergency'
    Invoke-BenchCase 'tools/bench_extra_20261111.py' 'allocation'
    foreach ($action in @('refrigerant','da8','coil')) { Invoke-BenchCase 'tools/bench_b06_indoor_20261111.py' $action }
    Invoke-BenchCase 'tools/bench_b07_vent_ntc_20261111.py' ''
    Invoke-BenchCase 'tools/bench_b06_indoor_20261111.py' 'soak'
    & $benchPy -X utf8 -u tools/finalize_bench_20261111.py
    if ($LASTEXITCODE -ne 0) { throw 'Final evidence reconciliation failed' }
    Write-Journal 'END scheduled cases; remaining rows still require disposition'
} catch {
    Write-Journal "STOP $($_.Exception.Message)"
    throw
}
