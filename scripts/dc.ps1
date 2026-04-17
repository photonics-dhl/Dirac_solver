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
    [switch]$SkipComputeSubmitCheck,
    [switch]$TunnelOnly,
    [switch]$NoShell
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

if ($TunnelOnly.IsPresent) {
    $target = Join-Path $scriptDir "connect_dirac_with_tunnel.ps1"
} else {
    $target = Join-Path $scriptDir "connect_server.ps1"
}

if (-not (Test-Path $target)) {
    throw "Missing script: $target"
}

$invocationParameters = @(
    "-ExecutionPolicy", "Bypass",
    "-File", $target,
    "-HostAlias", $HostAlias,
    "-LocalProxyPort", $LocalProxyPort,
    "-RemoteProxyPort", $RemoteProxyPort,
    "-PortTryCount", $PortTryCount
)

if (-not $TunnelOnly.IsPresent) {
    $invocationParameters += @(
        "-RemoteWorkDir", $RemoteWorkDir
    )

    $invocationParameters += @(
        "-DiracApiBase", $DiracApiBase,
        "-DiracHarnessFallbackBase", $DiracHarnessFallbackBase,
        "-DiracDispatchTimeoutSeconds", $DiracDispatchTimeoutSeconds,
        "-DiracExecTimeoutSeconds", $DiracExecTimeoutSeconds
    )

    if ([string]::IsNullOrWhiteSpace($DiracHarnessBase) -eq $false) {
        $invocationParameters += @("-DiracHarnessBase", $DiracHarnessBase)
    }

    if ($PSBoundParameters.ContainsKey("ForwardPorts")) {
        $invocationParameters += "-ForwardPorts"
        $invocationParameters += $ForwardPorts
    }

    if ($SkipServiceStart.IsPresent) {
        $invocationParameters += "-SkipServiceStart"
    }

    if ($SkipPortForward.IsPresent) {
        $invocationParameters += "-SkipPortForward"
    }

    if (-not $SkipComputeSubmitCheck.IsPresent) {
        $invocationParameters += "-RequireComputeSubmit"
    }
}

if ($AutoTunnel.IsPresent) {
    $invocationParameters += "-AutoTunnel"
}

if ($NoShell.IsPresent) {
    $invocationParameters += "-NoShell"
}

& powershell @invocationParameters

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
