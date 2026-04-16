param(
    [string]$HostAlias = "dirac-key",
    [string]$RemoteWorkDir = "/data/home/zju321/.openclaw/workspace/projects/Dirac",
    [int]$LocalProxyPort = 7890,
    [int]$RemoteProxyPort = 7890,
    [int]$PortTryCount = 1,
    [switch]$SkipRestartMcp,
    [switch]$AllowManualTunnelFallback,
    [switch]$SkipTunnelSetup
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

$sshBaseArgs = @(
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=8"
)

function Write-Step([string]$Message) {
    Write-Host "[zchat-tunnel] $Message"
}

function Stop-StaleLocalTunnel([string]$HostAlias, [int]$RemotePort, [int]$LocalPort) {
    $pattern = "-R {0}:127.0.0.1:{1}" -f $RemotePort, $LocalPort
    try {
        $procs = Get-CimInstance Win32_Process -Filter "Name = 'ssh.exe'" | Where-Object {
            ($_.CommandLine -like "*$pattern*") -and ($_.CommandLine -like "*$HostAlias*")
        }
        foreach ($proc in $procs) {
            Write-Step "Killing stale local ssh tunnel pid=$($proc.ProcessId) for remote port $RemotePort"
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
        }
    } catch {
        # best-effort cleanup
    }
}

if ($SkipTunnelSetup) {
    Write-Step "SkipTunnelSetup enabled: using manual tunnel mode at remote 127.0.0.1:$RemoteProxyPort"
    $selectedRemotePort = $RemoteProxyPort
} else {
    Write-Step "Checking local proxy on 127.0.0.1:$LocalProxyPort ..."
    $localProxyOk = $false
    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $async = $client.BeginConnect('127.0.0.1', $LocalProxyPort, $null, $null)
        if ($async.AsyncWaitHandle.WaitOne(2000, $false)) {
            $client.EndConnect($async)
            $localProxyOk = $true
        } else {
            $localProxyOk = $false
        }
        $client.Close()
    } catch {
        $localProxyOk = $false
    }

    if (-not $localProxyOk) {
        throw "Local proxy 127.0.0.1:$LocalProxyPort is not reachable. Start your local proxy first."
    }

    $selectedRemotePort = $null
    for ($offset = 0; $offset -lt $PortTryCount; $offset++) {
        $candidatePort = $RemoteProxyPort + $offset
        $reverseSpec = "{0}:127.0.0.1:{1}" -f $candidatePort, $LocalProxyPort
        Write-Step "Trying tunnel port $candidatePort ..."

        Stop-StaleLocalTunnel -HostAlias $HostAlias -RemotePort $candidatePort -LocalPort $LocalProxyPort

        $sshArgs = @(
            "-fN",
            "-o", "ExitOnForwardFailure=yes",
            "-o", "ServerAliveInterval=30",
            "-o", "ServerAliveCountMax=3",
            "-R", $reverseSpec
        ) + $sshBaseArgs + @($HostAlias)

        $launchOut = (& ssh @sshArgs 2>&1 | Out-String)
        if ($LASTEXITCODE -ne 0 -and -not [string]::IsNullOrWhiteSpace($launchOut)) {
            Write-Step ("ssh launch returned {0}: {1}" -f $LASTEXITCODE, $launchOut.Trim())
        }

        $checkCmd = "timeout 5 bash -lc `"</dev/tcp/127.0.0.1/$candidatePort`" >/dev/null 2>&1 && echo TUNNEL_OK || echo TUNNEL_FAIL"
        $checkOut = (& ssh @sshBaseArgs $HostAlias $checkCmd 2>&1 | Out-String)
        if ($checkOut -match "TUNNEL_OK") {
            $selectedRemotePort = $candidatePort
            break
        }
    }

    if (-not $selectedRemotePort) {
        if ($AllowManualTunnelFallback) {
            Write-Step "Auto tunnel failed on ports $RemoteProxyPort..$($RemoteProxyPort + $PortTryCount - 1)."
            Write-Step "Fallback mode: use manual MobaXterm reverse tunnel and continue with remote proxy endpoint 127.0.0.1:$RemoteProxyPort"
            $selectedRemotePort = $RemoteProxyPort
        } else {
            throw "Failed to establish reverse tunnel on ports $RemoteProxyPort..$($RemoteProxyPort + $PortTryCount - 1)"
        }
    }
}

Write-Step "Tunnel is ready on remote 127.0.0.1:$selectedRemotePort"

if (-not $SkipRestartMcp) {
    Write-Step "Restarting remote Octopus MCP with global outbound proxy http://127.0.0.1:$selectedRemotePort ..."
    $restartCmd = @(
        "pkill -f 'python server.py' || true",
        "cd '$RemoteWorkDir'",
        "GLOBAL_PROXY_URL=http://127.0.0.1:$selectedRemotePort ZCHAT_PROXY_URL=http://127.0.0.1:$selectedRemotePort HTTPS_PROXY=http://127.0.0.1:$selectedRemotePort HTTP_PROXY=http://127.0.0.1:$selectedRemotePort ALL_PROXY=http://127.0.0.1:$selectedRemotePort https_proxy=http://127.0.0.1:$selectedRemotePort http_proxy=http://127.0.0.1:$selectedRemotePort all_proxy=http://127.0.0.1:$selectedRemotePort NO_PROXY=localhost,127.0.0.1 no_proxy=localhost,127.0.0.1 nohup ./start_octopus_udocker.sh > logs/octopus_udocker.log 2>&1 < /dev/null &"
    ) -join "; "

    $restartOut = (& ssh @sshBaseArgs $HostAlias $restartCmd 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0) {
        if ($SkipTunnelSetup) {
            Write-Step "Warning: failed to restart remote MCP automatically in manual mode."
            if (-not [string]::IsNullOrWhiteSpace($restartOut)) {
                Write-Step "ssh output: $($restartOut.Trim())"
            }
            Write-Step "Continue with SSH connection. If needed, restart remote services manually after tunnel is ready."
            Write-Step "Done. Active remote proxy endpoint: 127.0.0.1:$selectedRemotePort"
            exit 0
        }
        throw "Failed to restart remote MCP: $($restartOut.Trim())"
    }

    Write-Step "Waiting for /health ..."
    $healthOk = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        try {
            $h = (& ssh @sshBaseArgs $HostAlias "curl -sS http://localhost:8000/health || true" 2>&1 | Out-String)
            if ($h -match '"status"\s*:\s*"ok"') {
                $healthOk = $true
                break
            }
        } catch {
            # keep waiting
        }
    }

    if (-not $healthOk) {
        if ($SkipTunnelSetup) {
            Write-Step "Warning: remote MCP health check timed out in manual mode."
            Write-Step "Continue with SSH connection. Verify MobaXterm reverse tunnel and remote logs if needed."
            Write-Step "Done. Active remote proxy endpoint: 127.0.0.1:$selectedRemotePort"
            exit 0
        }
        throw "Remote MCP did not become healthy in time."
    }
    Write-Step "Remote MCP is healthy."
}

Write-Step "Done. You can run calculations without manually opening MobaXterm tunnel."
Write-Step "Active remote proxy endpoint: 127.0.0.1:$selectedRemotePort"
