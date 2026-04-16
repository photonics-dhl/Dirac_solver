param(
    [string]$HostAlias = "dirac-key",
    [switch]$SkipRemote,
    [switch]$NoRestartRemoteWorker,
    [switch]$PruneLocalShells
)

$ErrorActionPreference = "Stop"

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host "== $Title =="
}

function Get-StaleSshProcesses {
    $patterns = @(
        "OPENCLAW_BIN=",
        "BatchMode=yes",
        "pkill -f"
    )

    $protectedRegex = @(
        "-L\s*3001:",
        "-L\s*8001:",
        "-L\s*7890:",
        "-L\s*8101:",
        "-R\s*7890:"
    )

    $all = Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^ssh(\.exe)?$' }
    return $all | Where-Object {
        $cmd = [string]$_.CommandLine
        $isProtected = $false
        foreach ($rx in $protectedRegex) {
            if ($cmd -match $rx) {
                $isProtected = $true
                break
            }
        }
        if ($isProtected) {
            return $false
        }
        return [bool]($patterns | Where-Object { $cmd -like "*$_*" })
    }
}

function Get-ProtectedSshProcessIds {
    $patterns = @(
        "-L\s*3001:",
        "-L\s*8001:",
        "-L\s*7890:",
        "-L\s*8101:",
        "-R\s*7890:"
    )

    $protected = @()
    $all = Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^ssh(\.exe)?$' }
    foreach ($proc in $all) {
        $cmd = [string]$proc.CommandLine
        if (-not $cmd) {
            continue
        }
        foreach ($pattern in $patterns) {
            if ($cmd -match $pattern) {
                $protected += $proc.ProcessId
                break
            }
        }
    }
    return @($protected | Select-Object -Unique)
}

function Get-PreserveShellProcessIds {
    param([int[]]$ProtectedSshPids)

    $preserve = @($PID)

    $listeners = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -in 3001, 8001 }
    if ($listeners) {
        $preserve += @($listeners | Select-Object -ExpandProperty OwningProcess)
    }

    if ($ProtectedSshPids) {
        foreach ($sshPid in $ProtectedSshPids) {
            $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$sshPid" -ErrorAction SilentlyContinue
            if ($proc -and $proc.ParentProcessId) {
                $preserve += $proc.ParentProcessId
            }
        }
    }

    $extensionHosts = Get-CimInstance Win32_Process | Where-Object {
        ($_.Name -in @("pwsh.exe", "powershell.exe")) -and ([string]$_.CommandLine -like "*PowerShell Extension*")
    }
    if ($extensionHosts) {
        $preserve += @($extensionHosts | Select-Object -ExpandProperty ProcessId)
    }

    return @($preserve | Where-Object { $_ } | Select-Object -Unique)
}

function Invoke-LocalShellPrune {
    $protectedSsh = Get-ProtectedSshProcessIds
    $preserve = Get-PreserveShellProcessIds -ProtectedSshPids $protectedSsh

    $beforePwsh = (Get-Process pwsh -ErrorAction SilentlyContinue | Measure-Object).Count
    $beforePowershell = (Get-Process powershell -ErrorAction SilentlyContinue | Measure-Object).Count

    Write-Host "Protected SSH PIDs: $(@($protectedSsh) -join ',')"
    Write-Host "Preserve shell PIDs: $(@($preserve) -join ',')"

    $targets = Get-CimInstance Win32_Process | Where-Object {
        ($_.Name -in @("pwsh.exe", "powershell.exe")) -and ($_.ProcessId -notin $preserve)
    }

    $killed = @()
    foreach ($target in $targets) {
        try {
            Stop-Process -Id $target.ProcessId -Force -ErrorAction Stop
            $killed += $target.ProcessId
        } catch {
        }
    }

    $afterPwsh = (Get-Process pwsh -ErrorAction SilentlyContinue | Measure-Object).Count
    $afterPowershell = (Get-Process powershell -ErrorAction SilentlyContinue | Measure-Object).Count

    if ($killed.Count -gt 0) {
        Write-Host "Pruned shell PIDs: $($killed -join ',')"
    } else {
        Write-Host "No redundant local shell process pruned."
    }
    Write-Host "pwsh: $beforePwsh -> $afterPwsh"
    Write-Host "powershell: $beforePowershell -> $afterPowershell"
}

function Show-LocalPorts {
    Write-Host "Local listener snapshot (3001/5173/8000/8001/8011/8101/18789/18791):"
    Get-NetTCPConnection -State Listen |
        Where-Object { $_.LocalPort -in 3001, 5173, 8000, 8001, 8011, 8101, 18789, 18791 } |
        Sort-Object LocalPort |
        Select-Object LocalAddress, LocalPort, OwningProcess |
        Format-Table -AutoSize
}

Write-Section "Local cleanup"
$stale = @(Get-StaleSshProcesses)
if ($stale.Count -gt 0) {
    $ids = @($stale | Select-Object -ExpandProperty ProcessId)
    foreach ($procId in $ids) {
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    }
    Write-Host "Killed stale local ssh processes: $($ids -join ',')"
} else {
    Write-Host "No stale local ssh helper processes found."
}

Show-LocalPorts

if ($PruneLocalShells.IsPresent) {
    Write-Section "Local shell prune"
    Invoke-LocalShellPrune
    Show-LocalPorts
}

if (-not $SkipRemote.IsPresent) {
    Write-Section "Remote cleanup"
    $restartFlag = if ($NoRestartRemoteWorker.IsPresent) { "0" } else { "1" }
    $remoteTemplate = @'
set -u
cd ~/.openclaw/workspace/projects/Dirac || exit 2

run_pids=$(ps -eo pid,args | grep -F -- "scripts/run_dirac_exec_worker.sh" | grep -v grep | awk '{print $1}' | tr '\n' ' ')
once_pids=$(ps -eo pid,args | grep -F -- "scripts/dirac_exec_worker.py --once" | grep -v grep | awk '{print $1}' | tr '\n' ' ')

echo "run_worker_pids_before=${run_pids:-none}"
echo "once_worker_pids_before=${once_pids:-none}"

if [ -n "${run_pids:-}" ]; then
  kill $run_pids || true
fi
if [ -n "${once_pids:-}" ]; then
  kill $once_pids || true
fi

sleep 1

if [ "__RESTART_REMOTE_WORKER__" = "1" ]; then
  nohup bash scripts/run_dirac_exec_worker.sh > ~/.openclaw/logs/dirac-worker-supervisor.log 2>&1 < /dev/null &
  disown || true
  sleep 1
fi

echo "run_worker_count_after=$(ps -eo pid,args | grep 'scripts/run_dirac_exec_worker.sh' | grep -v grep | wc -l)"
echo "once_worker_count_after=$(ps -eo pid,args | grep 'scripts/dirac_exec_worker.py --once' | grep -v grep | wc -l)"
echo "ports_after="
(ss -lntp 2>/dev/null || netstat -lntp 2>/dev/null) | grep -E ':(3001|5173|8000|8001|8011|8101)\b' | head -n 40 || true
'@
    $remoteCmd = ($remoteTemplate.Replace("__RESTART_REMOTE_WORKER__", $restartFlag) -replace "`r", "")
    $remoteCmd | ssh $HostAlias "bash --noprofile --norc -s"
}

Write-Section "Done"
Write-Host "Runtime hygiene cleanup completed."
