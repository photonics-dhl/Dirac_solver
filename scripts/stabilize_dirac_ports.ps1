param(
    [string]$SshAlias = "dirac-key"
)

$ErrorActionPreference = "Stop"

Write-Host "[stabilize] Cleaning duplicated ssh forwarders..."
$match = '-L (3001|8001|8101|5173):127.0.0.1'
$forwarders = Get-CimInstance Win32_Process |
    Where-Object { $_.Name -eq 'ssh.exe' -and $_.CommandLine -match $match }

foreach ($proc in $forwarders) {
    try {
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
        Write-Host "[stabilize] Killed PID=$($proc.ProcessId)"
    }
    catch {
        Write-Host "[stabilize] Skip kill PID=$($proc.ProcessId): $($_.Exception.Message)"
    }
}

Start-Sleep -Seconds 1

Write-Host "[stabilize] Starting single persistent forwarder..."
$sshArgs = @(
    '-N',
    '-o', 'ServerAliveInterval=30',
    '-o', 'ServerAliveCountMax=3',
    '-o', 'ExitOnForwardFailure=yes',
    '-L', '3001:127.0.0.1:3001',
    '-L', '8001:127.0.0.1:8001',
    '-L', '5173:127.0.0.1:5173',
    '-L', '8101:127.0.0.1:8101',
    $SshAlias
)

$proc = Start-Process -FilePath 'ssh' -ArgumentList $sshArgs -PassThru -WindowStyle Hidden
Write-Host "[stabilize] New forwarder PID=$($proc.Id)"

Start-Sleep -Seconds 2

Write-Host "[stabilize] Quick checks:"
$urls = @(
    'http://127.0.0.1:3001/api/dev-state',
    'http://127.0.0.1:8101/harness/case_registry',
    'http://127.0.0.1:8101/harness/case_types'
)

foreach ($url in $urls) {
    try {
        $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8
        Write-Host "[stabilize] OK $url => $($resp.StatusCode)"
    }
    catch {
        Write-Host "[stabilize] ERR $url => $($_.Exception.Message)"
    }
}

Write-Host "[stabilize] Done. Prefer harness base: http://127.0.0.1:8101"
