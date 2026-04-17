param(
    [string]$HostAlias = "dirac-key",
    [string]$RemoteWorkDir = "/data/home/zju321/.openclaw/workspace/projects/Dirac",
    [string]$DiracApiBase = "http://127.0.0.1:3001",
    [string]$DiracHarnessBase = "",
    [string]$DiracHarnessFallbackBase = "http://127.0.0.1:8101",
    [int]$DiracDispatchTimeoutSeconds = 1800,
    [int]$DiracExecTimeoutSeconds = 1200,
    [int]$LocalProxyPort = 7890,
    [int]$RemoteProxyPort = 7890,
    [int]$PortTryCount = 1,
    [switch]$AutoTunnel,
    [switch]$SkipServiceStart,
    [int[]]$ForwardPorts = @(3001, 5173, 8000, 8001, 8011, 8101),
    [switch]$SkipPortForward,
    [switch]$RequireComputeSubmit,
    [switch]$NoShell
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$tunnelScript = Join-Path $scriptDir "connect_dirac_with_tunnel.ps1"

if (-not (Test-Path $tunnelScript)) {
    throw "Missing script: $tunnelScript"
}

$sshBaseArgs = @(
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=8"
)

function Write-Step([string]$Message) {
    Write-Host "[connect-server] $Message"
}

function Invoke-RemoteBash([string]$HostAlias, [string]$Script) {
    $normalizedScript = ($Script -replace "`r`n", "`n") -replace "`r", "`n"
    $encodedScript = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($normalizedScript))
    $cmd = "echo $encodedScript | base64 -d | bash"
    $output = (& ssh @sshBaseArgs $HostAlias $cmd 2>&1 | Out-String)
    return [PSCustomObject]@{
        ExitCode = $LASTEXITCODE
        Output = $output
    }
}

function Stop-StaleForward([string]$HostAlias, [int[]]$Ports) {
    try {
        $procs = Get-CimInstance Win32_Process -Filter "Name = 'ssh.exe'"
        foreach ($proc in $procs) {
            $commandLine = [string]$proc.CommandLine
            if (-not $commandLine) { continue }
            if ($commandLine -notlike "*$HostAlias*") { continue }

            $matchesAnyPort = $false
            foreach ($port in $Ports) {
                $patternExact127 = [regex]::Escape("-L $port`:127.0.0.1:$port")
                $patternExactLocalhost = [regex]::Escape("-L $port`:localhost:$port")
                $patternLoose = "-L\s+$port`:\S+:$port"
                if ($commandLine -match $patternExact127 -or $commandLine -match $patternExactLocalhost -or $commandLine -match $patternLoose) {
                    $matchesAnyPort = $true
                    break
                }
            }

            if ($matchesAnyPort) {
                Write-Step "Killing stale local forward pid=$($proc.ProcessId)"
                $null = & taskkill /PID $proc.ProcessId /F /T 2>$null
            }
        }
    } catch {
    }
}

function Wait-RemotePort([string]$HostAlias, [int]$Port, [int]$MaxSeconds = 90) {
    for ($i = 0; $i -lt $MaxSeconds; $i++) {
        $checkScript = "if command -v ss >/dev/null 2>&1; then ss -ltn 2>/dev/null | grep -E '[:.]$Port\\b' >/dev/null 2>&1 && echo OPEN || echo CLOSED; else netstat -ltn 2>/dev/null | grep -E '[:.]$Port\\b' >/dev/null 2>&1 && echo OPEN || echo CLOSED; fi"
        $probe = Invoke-RemoteBash -HostAlias $HostAlias -Script $checkScript
        $out = $probe.Output
        if ($out -match "OPEN") {
            return $true
        }
        Start-Sleep -Seconds 1
    }

    return $false
}

function Wait-RemoteHttp([string]$HostAlias, [string]$Url, [int]$MaxSeconds = 90) {
    for ($i = 0; $i -lt $MaxSeconds; $i++) {
        $probeScript = "curl -sf --max-time 2 '$Url' >/dev/null 2>&1 && echo HTTP_OK || echo HTTP_FAIL"
        $probe = Invoke-RemoteBash -HostAlias $HostAlias -Script $probeScript
        if ($probe.Output -match "HTTP_OK") {
            return $true
        }
        Start-Sleep -Seconds 1
    }

    return $false
}

function Wait-RemoteHttpPostJson([string]$HostAlias, [string]$Url, [string]$JsonPayload, [int]$MaxSeconds = 90) {
    for ($i = 0; $i -lt $MaxSeconds; $i++) {
        $probeScript = "curl -sf --max-time 2 -H 'Content-Type: application/json' -X POST '$Url' -d '$JsonPayload' >/dev/null 2>&1 && echo HTTP_OK || echo HTTP_FAIL"
        $probe = Invoke-RemoteBash -HostAlias $HostAlias -Script $probeScript
        if ($probe.Output -match "HTTP_OK") {
            return $true
        }
        Start-Sleep -Seconds 1
    }

    return $false
}

function Test-RemoteHttpStatus([string]$HostAlias, [string]$Url, [string]$Method = "GET", [string]$JsonPayload = "") {
    $methodUpper = $Method.ToUpperInvariant()
    if ($methodUpper -eq "POST") {
        $probeScript = "code=`$(curl -sS --max-time 3 -o /dev/null -w '%{http_code}' -H 'Content-Type: application/json' -X POST '$Url' -d '$JsonPayload' || echo 000); echo `$code"
    } else {
        $probeScript = "code=`$(curl -sS --max-time 3 -o /dev/null -w '%{http_code}' '$Url' || echo 000); echo `$code"
    }
    $probe = Invoke-RemoteBash -HostAlias $HostAlias -Script $probeScript
    $status = (($probe.Output -split "`n") | ForEach-Object { $_.Trim() } | Where-Object { $_ -match '^\d{3}$' } | Select-Object -Last 1)
    if (-not $status) {
        $status = "000"
    }
    return [PSCustomObject]@{
        Status = [int]$status
        Output = $probe.Output
    }
}

function Wait-RemoteRouteExists([string]$HostAlias, [string[]]$Urls, [int]$MaxSeconds = 45) {
    for ($i = 0; $i -lt $MaxSeconds; $i++) {
        foreach ($url in $Urls) {
            $status = Test-RemoteHttpStatus -HostAlias $HostAlias -Url $url -Method "GET"
            if ($status.Status -ne 0 -and $status.Status -ne 404) {
                return [PSCustomObject]@{
                    Ready = $true
                    Url = $url
                    Status = $status.Status
                }
            }
        }
        Start-Sleep -Seconds 1
    }

    return [PSCustomObject]@{
        Ready = $false
        Url = ""
        Status = 0
    }
}

function Ensure-RemoteProxyDefaults([string]$HostAlias) {
    $script = @'
mkdir -p ~/.openclaw
cat > ~/.openclaw/proxy-default.env <<'EOF'
export GLOBAL_PROXY_URL=${GLOBAL_PROXY_URL:-http://127.0.0.1:7890}
export HTTP_PROXY=${HTTP_PROXY:-$GLOBAL_PROXY_URL}
export HTTPS_PROXY=${HTTPS_PROXY:-$GLOBAL_PROXY_URL}
export ALL_PROXY=${ALL_PROXY:-socks5h://127.0.0.1:7890}
export NO_PROXY=${NO_PROXY:-127.0.0.1,localhost}
export http_proxy=${http_proxy:-$HTTP_PROXY}
export https_proxy=${https_proxy:-$HTTPS_PROXY}
export all_proxy=${all_proxy:-$ALL_PROXY}
EOF

if [ -f ~/.bashrc ] && ! grep -q "proxy-default.env" ~/.bashrc; then
  printf "\n# Dirac/OpenClaw proxy defaults\n[ -f ~/.openclaw/proxy-default.env ] && source ~/.openclaw/proxy-default.env\n" >> ~/.bashrc
fi

if [ -f ~/.openclaw/proxy-default.env ]; then
  echo "PROXY_DEFAULTS_OK"
else
  echo "PROXY_DEFAULTS_FAIL"
fi
'@
    $res = Invoke-RemoteBash -HostAlias $HostAlias -Script $script
    return ($res.Output -match "PROXY_DEFAULTS_OK")
}

function Get-RemoteStartupDiagnostics([string]$HostAlias, [string]$RemoteWorkDir) {
    $diagScriptTemplate = @'
cd '__REMOTE_WORK_DIR__' || exit 0
echo '=== HEALTH ==='
curl -sS --max-time 3 http://127.0.0.1:8000/health || echo 'health8000_fail'
curl -sS --max-time 3 http://127.0.0.1:3001/api/dev-state || echo 'health3001_fail'
echo '=== PORTS ==='
ss -ltn 2>/dev/null | grep -E ':(3001|5173|8000|8001|8011|8101)\\b' || true
echo '=== PROCESSES ==='
ps -ef | grep -E 'server.ts|uvicorn|backend_engine|octopus|docker compose|udocker' | grep -v grep || true
echo '=== LOG:start_all_auto ==='
tail -n 80 logs/start_all_auto.log 2>/dev/null || true
echo '=== LOG:node_api ==='
tail -n 80 logs/node_api.log 2>/dev/null || true
echo '=== LOG:python_engine ==='
tail -n 80 logs/python_engine.log 2>/dev/null || true
echo '=== LOG:octopus_udocker ==='
tail -n 80 logs/octopus_udocker.log 2>/dev/null || true
'@
    $diagScript = $diagScriptTemplate.Replace("__REMOTE_WORK_DIR__", $RemoteWorkDir)
    return Invoke-RemoteBash -HostAlias $HostAlias -Script $diagScript
}

function Test-RemoteComputeSubmitPrereq([string]$HostAlias, [string]$RemoteWorkDir) {
        $checkScriptTemplate = @'
cd '__REMOTE_WORK_DIR__' || true
command -v qsub >/dev/null 2>&1 && command -v qstat >/dev/null 2>&1 && echo 'HPC_SUBMIT_READY' || echo 'HPC_SUBMIT_MISSING'
'@
        $checkScript = $checkScriptTemplate.Replace("__REMOTE_WORK_DIR__", $RemoteWorkDir)

    $check = Invoke-RemoteBash -HostAlias $HostAlias -Script $checkScript
    return [PSCustomObject]@{
        Ready = ($check.Output -match "HPC_SUBMIT_READY")
        Output = $check.Output
    }
}

Write-Step "Preparing tunnel and remote MCP ..."
$tunnelArgs = @(
    "-ExecutionPolicy", "Bypass",
    "-File", $tunnelScript,
    "-HostAlias", $HostAlias,
    "-RemoteWorkDir", $RemoteWorkDir,
    "-LocalProxyPort", $LocalProxyPort,
    "-RemoteProxyPort", $RemoteProxyPort,
    "-PortTryCount", $PortTryCount,
    "-NoShell"
)

if ($AutoTunnel.IsPresent) {
    $tunnelArgs += "-AutoTunnel"
}

& powershell @tunnelArgs
if ($LASTEXITCODE -ne 0) {
    throw "Tunnel/MCP preparation failed with exit code $LASTEXITCODE"
}

Write-Step "Ensuring remote default proxy env (127.0.0.1:7890) ..."
$proxyDefaultsReady = Ensure-RemoteProxyDefaults -HostAlias $HostAlias
if ($proxyDefaultsReady) {
    Write-Step "Remote proxy defaults configured"
} else {
    Write-Step "Warning: failed to persist remote proxy defaults"
}

if (-not $SkipServiceStart) {
    Write-Step "Starting remote dev services under $RemoteWorkDir ..."
    $harnessBaseExport = ""
    if ([string]::IsNullOrWhiteSpace($DiracHarnessBase) -eq $false) {
        $harnessBaseExport = "export DIRAC_HARNESS_BASE='$DiracHarnessBase'"
    }

    $startScriptTemplate = @'
set -e
cd '__REMOTE_WORK_DIR__'
export DIRAC_API_BASE='__DIRAC_API_BASE__'
__DIRAC_HARNESS_BASE_EXPORT__
export DIRAC_HARNESS_FALLBACK_BASE='__DIRAC_HARNESS_FALLBACK_BASE__'
export DIRAC_DISPATCH_TIMEOUT_SECONDS='__DIRAC_DISPATCH_TIMEOUT_SECONDS__'
export DIRAC_EXEC_TIMEOUT_SECONDS='__DIRAC_EXEC_TIMEOUT_SECONDS__'
mkdir -p logs
nohup ./start_all.sh > logs/start_all_auto.log 2>&1 < /dev/null &
echo START_TRIGGERED
'@
    $startScript = $startScriptTemplate.Replace("__REMOTE_WORK_DIR__", $RemoteWorkDir)
    $startScript = $startScript.Replace("__DIRAC_API_BASE__", $DiracApiBase)
    $startScript = $startScript.Replace("__DIRAC_HARNESS_BASE_EXPORT__", $harnessBaseExport)
    $startScript = $startScript.Replace("__DIRAC_HARNESS_FALLBACK_BASE__", $DiracHarnessFallbackBase)
    $startScript = $startScript.Replace("__DIRAC_DISPATCH_TIMEOUT_SECONDS__", [string]$DiracDispatchTimeoutSeconds)
    $startScript = $startScript.Replace("__DIRAC_EXEC_TIMEOUT_SECONDS__", [string]$DiracExecTimeoutSeconds)

    $startResult = Invoke-RemoteBash -HostAlias $HostAlias -Script $startScript
    $startOut = $startResult.Output
    if ($startResult.ExitCode -ne 0 -or $startOut -notmatch "START_TRIGGERED") {
        throw "Failed to start remote services: $($startOut.Trim())"
    }

    foreach ($port in $ForwardPorts) {
        $ok = Wait-RemotePort -HostAlias $HostAlias -Port $port -MaxSeconds 8
        if ($ok) {
            Write-Step "Remote port $port is listening"
        } else {
            Write-Step "Warning: remote port $port is not listening yet"
        }
    }

    Write-Step "Checking Octopus MCP health endpoint ..."
    $octopusReady = Wait-RemoteHttp -HostAlias $HostAlias -Url "http://127.0.0.1:8000/health" -MaxSeconds 90
    if (-not $octopusReady) {
        $diag = Get-RemoteStartupDiagnostics -HostAlias $HostAlias -RemoteWorkDir $RemoteWorkDir
        throw "Octopus MCP is not healthy on remote 127.0.0.1:8000. Diagnostics:`n$($diag.Output.Trim())"
    }

    Write-Step "Checking Node API readiness endpoint ..."
    $nodeProbe = Wait-RemoteRouteExists -HostAlias $HostAlias -Urls @(
        "http://127.0.0.1:3001/api/dev-state",
        "http://127.0.0.1:3001/health",
        "http://127.0.0.1:3001/api/health"
    ) -MaxSeconds 90
    if (-not $nodeProbe.Ready) {
        $diag = Get-RemoteStartupDiagnostics -HostAlias $HostAlias -RemoteWorkDir $RemoteWorkDir
        throw "Node API is not ready on remote 127.0.0.1:3001. Diagnostics:`n$($diag.Output.Trim())"
    }
    Write-Step "Node API route ready via $($nodeProbe.Url) (status=$($nodeProbe.Status))"

    Write-Step "Checking Harness route readiness (primary 8001, emergency 8101) ..."
    $harnessPort = 8001
    $harnessProbe = Wait-RemoteRouteExists -HostAlias $HostAlias -Urls @(
        "http://127.0.0.1:8001/harness/cases",
        "http://127.0.0.1:8001/harness/case_registry"
    ) -MaxSeconds 45
    if (-not $harnessProbe.Ready) {
        $postStatus = Test-RemoteHttpStatus -HostAlias $HostAlias -Url "http://127.0.0.1:8001/harness/run_case" -Method "POST" -JsonPayload '{"case_id":"infinite_well_v1","config":{}}'
        if ($postStatus.Status -ne 0 -and $postStatus.Status -ne 404) {
            $harnessProbe = [PSCustomObject]@{ Ready = $true; Url = "http://127.0.0.1:8001/harness/run_case"; Status = $postStatus.Status }
        }
    }
    if (-not $harnessProbe.Ready) {
        $harnessPort = 8101
        $harnessProbe = Wait-RemoteRouteExists -HostAlias $HostAlias -Urls @(
            "http://127.0.0.1:8101/harness/cases",
            "http://127.0.0.1:8101/harness/case_registry"
        ) -MaxSeconds 45
        if (-not $harnessProbe.Ready) {
            $postStatus = Test-RemoteHttpStatus -HostAlias $HostAlias -Url "http://127.0.0.1:8101/harness/run_case" -Method "POST" -JsonPayload '{"case_id":"infinite_well_v1","config":{}}'
            if ($postStatus.Status -ne 0 -and $postStatus.Status -ne 404) {
                $harnessProbe = [PSCustomObject]@{ Ready = $true; Url = "http://127.0.0.1:8101/harness/run_case"; Status = $postStatus.Status }
            }
        }
    }
    if (-not $harnessProbe.Ready) {
        $diag = Get-RemoteStartupDiagnostics -HostAlias $HostAlias -RemoteWorkDir $RemoteWorkDir
        throw "Harness route is not ready on remote 8001/8101. Diagnostics:`n$($diag.Output.Trim())"
    }
    if ($harnessPort -eq 8101) {
        Write-Step "Warning: using emergency harness port 8101 (primary 8001 unavailable)"
    } else {
        Write-Step "Harness route is ready on primary port 8001"
    }
    Write-Step "Harness route ready via $($harnessProbe.Url) (status=$($harnessProbe.Status))"

    Write-Step "Checking KB route readiness on selected harness port ..."
    $kbReady = Wait-RemoteHttpPostJson -HostAlias $HostAlias -Url "http://127.0.0.1:$harnessPort/kb/query" -JsonPayload '{"query":"health","top_k":1}' -MaxSeconds 45
    if (-not $kbReady) {
        $diag = Get-RemoteStartupDiagnostics -HostAlias $HostAlias -RemoteWorkDir $RemoteWorkDir
        throw "KB route is not ready on remote port $harnessPort (/kb/query). Diagnostics:`n$($diag.Output.Trim())"
    }

    if ($RequireComputeSubmit.IsPresent) {
        Write-Step "Checking HPC compute submit prerequisites (qsub/qstat) ..."
        $submitCheck = Test-RemoteComputeSubmitPrereq -HostAlias $HostAlias -RemoteWorkDir $RemoteWorkDir
        if (-not $submitCheck.Ready) {
            throw "Compute submit prerequisite check failed (qsub/qstat unavailable for runtime). Details:`n$($submitCheck.Output.Trim())"
        }
        Write-Step "HPC compute submit prerequisites are ready"
    }
}

if (-not $SkipPortForward) {
    Write-Step "Setting local forwards for ports: $($ForwardPorts -join ', ')"
    $failedForwardPorts = @()

    foreach ($port in $ForwardPorts) {
        $singleForwardArgs = @(
            "-fN",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=8",
            "-o", "ExitOnForwardFailure=yes",
            "-o", "ServerAliveInterval=30",
            "-o", "ServerAliveCountMax=3",
            "-L", "$port`:127.0.0.1:$port",
            $HostAlias
        )

        $argLine = ($singleForwardArgs | ForEach-Object {
            if ($_ -match "\s") { '"' + ($_ -replace '"', '\\"') + '"' } else { $_ }
        }) -join " "

        $proc = Start-Process -FilePath "ssh" -ArgumentList $argLine -PassThru -WindowStyle Hidden
        $exited = $proc.WaitForExit(12000)
        if (-not $exited) {
            $localProbe = Test-NetConnection -ComputerName "127.0.0.1" -Port $port -WarningAction SilentlyContinue
            if ($localProbe.TcpTestSucceeded) {
                Write-Step "Local forward established (detected by probe): $port -> remote 127.0.0.1:$port"
                continue
            }

            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
            $failedForwardPorts += $port
            Write-Step "Warning: local forward command timeout for $port"
            continue
        }

        if ($proc.ExitCode -ne 0) {
            $failedForwardPorts += $port
            Write-Step "Warning: failed local forward for $port (exit=$($proc.ExitCode))"
            continue
        }

        Write-Step "Local forward established: $port -> remote 127.0.0.1:$port"
    }

    if ($failedForwardPorts.Count -gt 0) {
        Write-Step "Warning: some local forwards failed: $($failedForwardPorts -join ', ')"
    }
}

if ($NoShell) {
    Write-Step "Done. Tunnel + remote services + local forwards are ready (NoShell)."
    exit 0
}

Write-Step "Opening interactive SSH shell to $HostAlias ..."
& ssh $HostAlias
