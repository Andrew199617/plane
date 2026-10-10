<#
.SYNOPSIS
  Stop the local Plane dev stack started by dev-up.ps1. Touches only Plane.

.DESCRIPTION
  - Kills the process trees recorded in .devlogs\pids\*.pid (packages watcher, web-dev, admin, space, live).
  - Kills any leftover node listener on Plane's dev ports (3301, 3302, 3310, 3400, and 3300 if a dev server
    was ever started there) whose command line lives under this repo (never anything else).
  - Stops the production web container "plane-web-prod" (:3300; dev-up.ps1 recreates it from the last build).
  - Stops the docker compose project "plane" (containers kept; data volumes are NEVER removed).
  Touches only the compose project "plane", the plane-web-prod container and node processes from this repo.

.PARAMETER FrontendOnly
  Only stop the host dev servers.
.PARAMETER BackendOnly
  Only stop the docker compose project.
.PARAMETER Down
  Use "docker compose -p plane down" (removes Plane's containers + network, keeps volumes) instead of "stop".

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
  # Fallback: orphaned listeners on Plane's ports, only if they belong to this repo.
  # (3300 is normally Docker's port publish for plane-web-prod, maybe behind a reverse proxy - only node is considered.)
  foreach ($port in 3300, 3301, 3302, 3310, 3400) {
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

  Write-Step 'Stopping production web (plane-web-prod)'
  if ((& docker ps -q --filter 'name=^plane-web-prod$' 2>$null)) { & docker stop plane-web-prod | Out-Null; Write-Host '    stopped plane-web-prod' }
  else { Write-Host '    plane-web-prod not running' }
}

if (-not $FrontendOnly) {
  Write-Step 'Stopping backend (docker compose project "plane")'
  # plane-web-prod is attached to the compose network; stop it first so "down" can remove the network.
  if ($Down -and (& docker ps -q --filter 'name=^plane-web-prod$' 2>$null)) { & docker stop plane-web-prod | Out-Null }
  if ($Down) { & docker compose -p plane -f $Compose down } else { & docker compose -p plane -f $Compose stop }
}
Write-Host 'Done.' -ForegroundColor Green
