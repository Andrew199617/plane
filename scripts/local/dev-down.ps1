<#
.SYNOPSIS
  Stop the DEBUG Plane stack started by dev-up.ps1. Never touches RELEASE (see AGENTS.md "Local environment").

.DESCRIPTION
  - Kills the process trees recorded in .devlogs\pids\*.pid (packages watcher, web-dev, admin, space, live).
  - Kills any leftover node listener on the debug dev ports (3301, 3302, 3310, 3400) whose command line lives
    under this repo (never anything else).
  - Stops the docker compose project "plane-dev" (containers kept; data volumes are NEVER removed).
  Touches only the compose project "plane-dev" and node processes from this repo. RELEASE (compose project
  "plane", plane-release-* containers, 127.0.0.1:3300 and the phone link) is never stopped or changed here;
  it is driven only by scripts\local\release.ps1.

.PARAMETER FrontendOnly
  Only stop the host dev servers.
.PARAMETER BackendOnly
  Only stop the docker compose project.
.PARAMETER Down
  Use "docker compose -p plane-dev down" (removes the debug containers + network, keeps volumes) instead of "stop".

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\local\dev-down.ps1
#>
[CmdletBinding()]
param(
  [switch]$FrontendOnly,
  [switch]$BackendOnly,
  [switch]$Down
)

# 'Continue' (not 'Stop'): under Windows PowerShell 5.1, stderr from native tools (docker, pnpm) can surface as
# terminating NativeCommandErrors. Failures are checked explicitly via $LASTEXITCODE and throw.
$ErrorActionPreference = 'Continue'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$PidDir = Join-Path $Root '.devlogs\pids'
$Compose = Join-Path $Root 'docker-compose-local.yml'

function Write-Step([string]$msg) { Write-Host "==> $msg" -ForegroundColor Cyan }

function Stop-Tree([int]$ProcId, [string]$Label) {
  if (Get-Process -Id $ProcId -ErrorAction SilentlyContinue) {
    & taskkill.exe /PID $ProcId /T /F 2>&1 | Out-Null
    Write-Host ("    stopped {0} (pid {1})" -f $Label, $ProcId)
  }
}

if (-not $BackendOnly) {
  Write-Step 'Stopping host dev servers'
  if (Test-Path $PidDir) {
    foreach ($f in Get-ChildItem -Path $PidDir -Filter '*.pid') {
      $procId = [int](Get-Content $f.FullName -Raw).Trim()
      Stop-Tree $procId $f.BaseName
      Remove-Item $f.FullName -Force
    }
  }
  # Fallback: orphaned listeners on the debug dev ports, only if they belong to this repo.
  # (3300 is RELEASE - Docker's port publish for plane-release-proxy - and is never considered here.)
  foreach ($port in 3301, 3302, 3310, 3400) {
    $owners = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($o in $owners) {
      $p = Get-CimInstance Win32_Process -Filter "ProcessId = $o" -ErrorAction SilentlyContinue
      if (-not $p -or $p.Name -ne 'node.exe') { continue }
      if ($p.CommandLine -and $p.CommandLine.ToLower().Contains($Root.ToLower())) { Stop-Tree $o "listener :$port" }
      else { Write-Warning ("port {0} is held by pid {1} ({2}) which is not from this repo - left alone" -f $port, $o, $p.Name) }
    }
  }
  # Fallback: orphaned tsdown/turbo watchers from this repo (their parent cmd.exe is gone).
  Get-CimInstance Win32_Process -Filter "Name = 'node.exe' OR Name = 'turbo.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine.ToLower().Contains($Root.ToLower()) -and ($_.CommandLine -match 'tsdown|turbo(\.exe)?"? run dev|react-router(\\|/)|bin(\\|/)react-router') -and -not (Get-Process -Id $_.ParentProcessId -ErrorAction SilentlyContinue) } |
    ForEach-Object { Stop-Tree ([int]$_.ProcessId) 'orphan watcher' }
}

if (-not $FrontendOnly) {
  Write-Step 'Stopping backend (docker compose project "plane-dev")'
  # Never "-v": the plane-dev_* volumes hold the debug data (re-seed with dev-refresh.ps1 instead).
  if ($Down) { & docker compose -p plane-dev -f $Compose down } else { & docker compose -p plane-dev -f $Compose stop }
  if ($LASTEXITCODE -ne 0) { Write-Warning 'docker compose (plane-dev) reported an error - check: docker ps --filter label=com.docker.compose.project=plane-dev' }
}
Write-Host 'Done.' -ForegroundColor Green
