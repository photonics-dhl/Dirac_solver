param(
    [string]$HostAlias = "dirac-key",
    [string]$RemoteWorkDir = "/data/home/zju321/.openclaw/workspace/projects/Dirac",
    [int]$LocalProxyPort = 7890,
    [int]$RemoteProxyPort = 7890,
    [int]$PortTryCount = 1,
    [switch]$AutoTunnel,
    [switch]$NoShell
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$tunnelScript = Join-Path $scriptDir "start_zchat_proxy_tunnel.ps1"

if (-not (Test-Path $tunnelScript)) {
    throw "Missing tunnel script: $tunnelScript"
}

Write-Host "[dirac-connect] Preparing proxy tunnel and remote MCP..."

$baseArgs = @(
    "-ExecutionPolicy", "Bypass",
    "-File", $tunnelScript,
    "-HostAlias", $HostAlias,
    "-RemoteWorkDir", $RemoteWorkDir,
    "-LocalProxyPort", $LocalProxyPort,
    "-RemoteProxyPort", $RemoteProxyPort,
    "-PortTryCount", $PortTryCount,
    "-AllowManualTunnelFallback"
)

if (-not $AutoTunnel.IsPresent) {
    $baseArgs += "-SkipTunnelSetup"
}

& powershell @baseArgs

if ($LASTEXITCODE -ne 0) {
    throw "Tunnel setup failed with exit code $LASTEXITCODE"
}

if ($NoShell) {
    Write-Host "[dirac-connect] Tunnel/MCP setup done. Skip opening interactive SSH shell (-NoShell)."
    exit 0
}

Write-Host "[dirac-connect] Opening SSH session to $HostAlias ..."
& ssh $HostAlias
