<#
.SYNOPSIS
  Build, deploy and operate the RELEASE Plane stack: the owner's real data, compose project "plane",
  served only on 127.0.0.1:3300 (the phone reaches it through a Tailscale Serve TCP forward).

.DESCRIPTION
  RELEASE runs production images (gunicorn, Celery, built web/admin/space, live, stock Caddy) built from
  COMMITTED code in a DETACHED git worktree (default: ..\plane-release next to this checkout). It never
  reads this checkout's working tree, never bind-mounts source, and keeps its data in the external
  volumes plane_pgdata, plane_uploads, plane_redisdata and plane_rabbitmq_data.
  DEBUG (project plane-dev, scripts\local\dev-up.ps1) and TESTS (plane-test-<name>) are separate stacks.
  Read AGENTS.md, section "Local environment (Jira-parity fork)", before using this script.

  Run it from the MAIN checkout (never from the release worktree):
    powershell -ExecutionPolicy Bypass -File scripts\local\release.ps1 <verb> [options]

  Verbs
    init                 Create the detached release worktree from local branch main (once).
    init-env [-Force]    ONE-TIME, PRE-CUTOVER step: generate .local\release\release.env from apps\api\.env
                         (credentials missing there come from .env / apps\live\.env). Prints key names and
                         counts only, never values. After the cutover apps\api\.env holds DEBUG values and
                         init-env refuses: edit release.env by hand (or restore a release.env.bak-* copy).
    build [-Ref <rev>] [-NoCache]
                         Build plane-release/{backend,proxy,space,live}:<sha12> from the worktree HEAD.
                         -Ref first moves the (clean) worktree to that commit (it must be on main unless -Force).
    infra                Start plane-db, plane-redis, plane-mq, plane-minio on the external volumes.
    deploy [-Ref <rev>] [-Rebuild] [-NoCache] [-PlanOnly] [-NoMigrate] [-AllowUnknownApplied] [-Force]
                         The only way release code changes. -Ref defaults to main (resolved in this
                         checkout) and must be a commit on main; the FIRST deploy needs an explicit -Ref.
                         Preflight, build, DB checkpoint, unknown-migration gate, migrate plan, migrate (app
                         services stopped), up --wait, health checks, deployments.tsv row.
                         -PlanOnly moves the worktree, checkpoints the running DB and stops after printing the
                         migration plan (no container is started, stopped or re-created).
                         -NoMigrate aborts before migrating when the plan is not empty.
                         -Force (each case needs the owner's OK) allows: a commit that does not contain the
                         deployed one, a commit not on main, a plan that looks like an empty/wrong database.
    up [-Force]          Re-create the deployed tag (and move the worktree back to its commit) and health-check
                         it (recovery; owner's OK). -Force first removes stray containers that a
                         `docker compose -p plane ...` accident left in project plane (volumes kept).
    rollback [-Tag <sha12>] [-RestoreDump <file>] [-Force]
                         Code rollback (default: the previous 'ok' deploy); the worktree moves to that commit.
                         -RestoreDump also replaces the release database with a checkpoint from
                         .local\checkpoints\release-*.dump or .local\backups\ (other files need -Force); it must
                         be confirmed by typing RESTORE in an interactive console and loses later writes.
                         -Force also removes stray containers in project plane, as for up.
    status               Read-only overview: worktree vs main, deployed tag, containers, last deploys.
    logs [<svc>] [--tail N] [--follow]
    checkpoint [-Name <label>]
                         pg_dump -Fc of the release DB to .local\checkpoints\release-<ts>-<label>.dump.
    manage <manage.py args>
                         Runs in a one-off migrator container (production settings). Free (allowlist):
                         showmigrations [--list|-l|--plan|-p|--no-color] [app labels], and
                         migrate --plan [--no-color] [app_label [migration]]. Any other token (--prune and its
                         abbreviations, --fake*, --database, ...) needs -IKnowThisIsRelease and takes the lock.
    compose <args>       Guarded passthrough. Free: ps (without --no-trunc/--format), logs, images,
                         config --services|--images|--volumes. Anything else (plain config prints secrets, top,
                         exec, run, stop, down, ...) needs -IKnowThisIsRelease. Always refused: down -v /
                         --volumes, --scale, create, and run of anything but migrator (use
                         docker exec plane-release-<svc> ... against the running container instead).
    prune-images [-Keep 3]
                         Remove plane-release/* tags not used by the last N ok deploys, the deployed tag or
                         any container, after a y/N prompt in an interactive console. Never runs docker prune.

  Safety rules (see AGENTS.md)
    - Release changes only through deploy / up / rollback (and guarded compose/manage), and only when the
      owner asks. Never down -v, never prune, never delete plane_* volumes, .local\checkpoints or .local\backups.
    - Never print .local\release\release.env or `docker compose config` output: they hold secrets.
    - Never edit, commit, check out or run pnpm inside the release worktree; only release.ps1 moves it (detached):
      init, build -Ref, deploy, and up/rollback (back to the commit of the tag they run). main never moves
      backwards: fix forward.
    - Options are exact names (case-insensitive, no abbreviations). For logs / manage / compose everything
      after the verb goes to docker compose / manage.py verbatim (-f, -T, --plan, ...), except
      -IKnowThisIsRelease and -Worktree <path>; after a bare -- even those pass through.

  State (gitignored, in this checkout): .local\release\{release.env, tag.env, deployments.tsv, deploy.lock,
  public-host}; checkpoints in .local\checkpoints\; build logs in .devlogs\release-build-<tag>.log.
  Exit codes: 0 ok, 1 failure, 2 deploy refused because release has applied migrations the new code lacks.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\local\release.ps1 status
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\local\release.ps1 deploy -PlanOnly
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\local\release.ps1 logs api --tail 200
#>
#Requires -Version 5.1

# 'Continue' (not 'Stop'): under Windows PowerShell 5.1, stderr from native tools (docker, git) can surface as
# terminating NativeCommandErrors. Every native call checks $LASTEXITCODE explicitly instead.
$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'

# ---------------------------------------------------------------- arguments
# Parsed by hand on purpose: a PowerShell param() block binds any token that prefix-matches a parameter
# (-f -> -Force, -T -> -Tag, --plan -> -PlanOnly, --all -> -AllowUnknownApplied, -d -> -Debug), which would
# silently change docker / manage.py arguments. Options are exact names (case-insensitive, no abbreviations).
# For logs / manage / compose everything after the verb is passed on verbatim, except -IKnowThisIsRelease and
# -Worktree <path>; after a bare -- even those pass through.
$Command = ''
$Ref = 'main'
$RefGiven = $false
$Tag = ''
$RestoreDump = ''
$Name = ''
$Keep = 3
$Worktree = ''
$Rebuild = $false
$NoCache = $false
$PlanOnly = $false
$NoMigrate = $false
$Force = $false
$AllowUnknownApplied = $false
$IKnowThisIsRelease = $false
$ArgError = ''
$PassthroughVerbs = @('logs', 'manage', 'compose')
$restList = New-Object System.Collections.Generic.List[string]
$rawArgs = @($args)
$i = 0
$afterDashDash = $false
while ($i -lt $rawArgs.Count) {
  $a = [string]$rawArgs[$i]
  $lower = $a.ToLowerInvariant()
  $isPass = [bool]$Command -and ($PassthroughVerbs -contains $Command.ToLowerInvariant())
  if ($afterDashDash) { $restList.Add($a); $i++; continue }
  if ($isPass -and $a -eq '--') { $afterDashDash = $true; $i++; continue }
  if ($lower -eq '-iknowthisisrelease') { $IKnowThisIsRelease = $true; $i++; continue }
  if ($isPass -and $lower -ne '-worktree') { $restList.Add($a); $i++; continue }
  if (@('-command', '-ref', '-tag', '-restoredump', '-name', '-keep', '-worktree') -contains $lower) {
    if ($i + 1 -ge $rawArgs.Count) { $ArgError = "option $a needs a value"; break }
    $v = [string]$rawArgs[$i + 1]
    if ($lower -eq '-command') { $Command = $v }
    elseif ($lower -eq '-ref') { $Ref = $v; $RefGiven = $true }
    elseif ($lower -eq '-tag') { $Tag = $v }
    elseif ($lower -eq '-restoredump') { $RestoreDump = $v }
    elseif ($lower -eq '-name') { $Name = $v }
    elseif ($lower -eq '-worktree') { $Worktree = $v }
    elseif (-not [int]::TryParse($v, [ref]$Keep)) { $ArgError = "-Keep needs a number, got '$v'"; break }
    $i += 2; continue
  }
  if ($lower -eq '-rebuild') { $Rebuild = $true; $i++; continue }
  if ($lower -eq '-nocache') { $NoCache = $true; $i++; continue }
  if ($lower -eq '-planonly') { $PlanOnly = $true; $i++; continue }
  if ($lower -eq '-nomigrate') { $NoMigrate = $true; $i++; continue }
  if ($lower -eq '-force') { $Force = $true; $i++; continue }
  if ($lower -eq '-allowunknownapplied') { $AllowUnknownApplied = $true; $i++; continue }
  if (@('-help', '--help', '-?', '/?') -contains $lower) { $Command = 'help'; $i++; continue }
  if ($a.StartsWith('-')) { $ArgError = "unknown option '$a' (options are exact names such as -PlanOnly; see the header of this script)"; break }
  if (-not $Command) { $Command = $a; $i++; continue }
  $ArgError = "unexpected argument '$a' for '$Command'"
  break
}
$Rest = $restList.ToArray()

# ---------------------------------------------------------------- paths and constants
$Main = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (-not $Worktree) { $Worktree = Join-Path (Split-Path -Parent $Main) 'plane-release' }
elseif (-not [System.IO.Path]::IsPathRooted($Worktree)) { $Worktree = Join-Path (Get-Location).Path $Worktree }
$WT = [System.IO.Path]::GetFullPath($Worktree).TrimEnd('\')

$StateDir = Join-Path $Main '.local\release'
$EnvFile = Join-Path $StateDir 'release.env'
$TagFile = Join-Path $StateDir 'tag.env'
$DeployLog = Join-Path $StateDir 'deployments.tsv'
$LockFile = Join-Path $StateDir 'deploy.lock'
$PublicHostFile = Join-Path $StateDir 'public-host'
$CheckpointDir = Join-Path $Main '.local\checkpoints'
$LogDir = Join-Path $Main '.devlogs'
$ComposeFile = Join-Path $WT 'scripts\local\release\docker-compose.release.yml'
$ExampleFile = Join-Path $WT 'scripts\local\release\release.env.example'

$Project = 'plane'
$BaseUrl = 'http://127.0.0.1:3300'
$ReleaseVolumes = @('plane_pgdata', 'plane_uploads', 'plane_redisdata', 'plane_rabbitmq_data')
$ImageNames = @('backend', 'proxy', 'space', 'live')
$StopForMigrate = @('api', 'worker', 'beat-worker', 'live')
$AppContainers = @('plane-release-api', 'plane-release-worker', 'plane-release-beat', 'plane-release-live', 'plane-release-space', 'plane-release-proxy')
$CredentialKeys = @('POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_DB', 'RABBITMQ_USER', 'RABBITMQ_PASSWORD', 'RABBITMQ_VHOST',
  'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_S3_BUCKET_NAME')
$RequiredNonEmpty = @('SECRET_KEY', 'LIVE_SERVER_SECRET_KEY', 'POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_DB',
  'RABBITMQ_USER', 'RABBITMQ_PASSWORD', 'RABBITMQ_VHOST', 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY',
  'CORS_ALLOWED_ORIGINS', 'WEB_URL', 'APP_BASE_URL', 'REDIS_URL', 'GUNICORN_WORKERS')
# Must be absent from release.env: production settings and the default session cookie (logins survive cutover).
$ForbiddenKeys = @('DJANGO_SETTINGS_MODULE', 'SESSION_COOKIE_NAME', 'RELEASE_TAG', 'PLANE_RELEASE_WORKTREE', 'PLANE_RELEASE_ENV_FILE')
# Never removed from this process's environment even if release.env (wrongly) defines them.
$ProtectedEnv = @('PATH', 'PATHEXT', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'USERPROFILE', 'HOME', 'APPDATA', 'LOCALAPPDATA',
  'COMSPEC', 'PROGRAMDATA', 'PROGRAMFILES', 'DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_CONFIG')
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

# Process-local hygiene: read-only git calls must not rewrite the index; stray COMPOSE_* variables must not
# redirect compose; health probes go direct (no corporate proxy) to 127.0.0.1 and the tailnet host.
$env:GIT_OPTIONAL_LOCKS = '0'
foreach ($v in @('COMPOSE_FILE', 'COMPOSE_PROJECT_NAME', 'COMPOSE_PROFILES', 'COMPOSE_ENV_FILES', 'COMPOSE_PATH_SEPARATOR')) {
  Remove-Item -LiteralPath ("Env:\" + $v) -ErrorAction SilentlyContinue
}
[System.Net.WebRequest]::DefaultWebProxy = New-Object System.Net.WebProxy

$script:ExitCode = 0
$script:LockHeld = $false

# ---------------------------------------------------------------- output and failure helpers
function Write-Step([string]$Msg) { Write-Host "==> $Msg" -ForegroundColor Cyan }
function Write-Info([string]$Msg) { Write-Host "    $Msg" }
function Write-Ok([string]$Msg) { Write-Host "    $Msg" -ForegroundColor Green }
function Stop-Release([string]$Msg, [int]$Code = 1) { $script:ExitCode = $Code; throw $Msg }

function Get-RelPath([string]$P) {
  $prefix = $Main.TrimEnd('\') + '\'
  if ($P.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) { return ($P.Substring($prefix.Length) -replace '\\', '/') }
  return $P
}

function ConvertTo-NormPath([string]$P) { return (($P -replace '/', '\').TrimEnd('\')).ToLowerInvariant() }

# Windows PowerShell 5.1 Set-Content/Out-File write a BOM or UTF-16; state files are UTF-8 without BOM, LF.
function Write-Utf8NoBom([string]$Path, [string]$Text) {
  $dir = Split-Path -Parent $Path
  if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
  [System.IO.File]::WriteAllText($Path, ($Text -replace "`r`n", "`n"), $Utf8NoBom)
}

function Add-Utf8NoBom([string]$Path, [string]$Text) {
  [System.IO.File]::AppendAllText($Path, ($Text -replace "`r`n", "`n"), $Utf8NoBom)
}

# ---------------------------------------------------------------- dotenv parsing (values are never printed)
function ConvertFrom-DotEnvText([string]$Text) {
  foreach ($line in ($Text -split "`r?`n")) {
    if ($line -match '^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$') {
      [pscustomobject]@{ Key = $Matches[1]; Value = $Matches[2]; Raw = $line }
    } else {
      [pscustomobject]@{ Key = $null; Value = $null; Raw = $line }
    }
  }
}

function Read-DotEnv([string]$Path) { ConvertFrom-DotEnvText ([System.IO.File]::ReadAllText($Path)) }

function Get-Unquoted([string]$V) {
  $t = $V.Trim()
  if ($t.Length -ge 2 -and (($t.StartsWith('"') -and $t.EndsWith('"')) -or ($t.StartsWith("'") -and $t.EndsWith("'")))) {
    return $t.Substring(1, $t.Length - 2)
  }
  return ($t -replace '\s+#.*$', '')
}

# Key -> value (last occurrence wins, like dotenv). -Raw keeps the value exactly as written.
function Get-EnvMap([object[]]$Entries, [switch]$Raw) {
  $map = [System.Collections.Generic.Dictionary[string, string]]::new([System.StringComparer]::Ordinal)
  foreach ($e in $Entries) {
    if ($e.Key) { if ($Raw) { $map[$e.Key] = $e.Value } else { $map[$e.Key] = (Get-Unquoted $e.Value) } }
  }
  return , $map
}

function Get-DotEnvKeys([string]$Path) {
  @(Read-DotEnv $Path | Where-Object { $_.Key } | ForEach-Object { $_.Key } | Select-Object -Unique)
}

# Naive ${KEY} expansion, only to sanity-check derived URLs (never printed).
function Expand-Naive([string]$Value, $Map) {
  $out = [string]$Value
  foreach ($k in @($Map.Keys)) { $out = $out.Replace('${' + $k + '}', [string]$Map[$k]) }
  return $out
}

# '' when the key is absent, else its naively expanded value (never printed).
function Get-ExpandedValue($Map, [string]$Key) {
  if (-not $Map.ContainsKey($Key)) { return '' }
  return (Expand-Naive $Map[$Key] $Map)
}

# ---------------------------------------------------------------- git helpers
function Invoke-GitOut([string]$Dir, [string[]]$GitArgs, [switch]$AllowFail) {
  $out = & git -C $Dir @GitArgs 2>$null
  $code = $LASTEXITCODE
  if ($code -ne 0) {
    if ($AllowFail) { return $null }
    Stop-Release ("git {0} failed in {1} (exit {2})" -f ($GitArgs -join ' '), $Dir, $code)
  }
  return ((@($out) -join "`n").Trim())
}

function Resolve-Commit([string]$Rev) {
  if (-not $Rev -or $Rev.StartsWith('-')) { Stop-Release "invalid revision '$Rev'" }
  $sha = Invoke-GitOut $Main @('rev-parse', '--verify', '--quiet', ($Rev + '^{commit}')) -AllowFail
  if (-not $sha -or $sha -notmatch '^[0-9a-f]{40}$') { Stop-Release "cannot resolve '$Rev' to a commit in $Main" }
  return $sha
}

function Get-WorktreeHead { return (Invoke-GitOut $WT @('rev-parse', 'HEAD')) }

function Assert-MainCheckout {
  if (-not (Test-Path -LiteralPath (Join-Path $Main '.git') -PathType Container)) {
    Stop-Release "run release.ps1 from the main checkout, not from a linked worktree ($Main has no .git directory)"
  }
  if ((ConvertTo-NormPath $WT) -eq (ConvertTo-NormPath $Main)) { Stop-Release 'the release worktree cannot be the main checkout' }
}

# Exists, belongs to this repository, detached HEAD, no local changes.
function Assert-Worktree {
  if (-not (Test-Path -LiteralPath (Join-Path $WT '.git'))) { Stop-Release "release worktree $WT is missing; run: release.ps1 init" }
  $common = Invoke-GitOut $WT @('rev-parse', '--path-format=absolute', '--git-common-dir')
  if ((ConvertTo-NormPath $common) -ne (ConvertTo-NormPath (Join-Path $Main '.git'))) {
    Stop-Release "$WT is not a worktree of $Main"
  }
  $branch = Invoke-GitOut $WT @('symbolic-ref', '-q', '--short', 'HEAD') -AllowFail
  if ($branch) { Stop-Release "release worktree has branch '$branch' checked out; it must stay detached (only release.ps1 moves it)" }
  $dirty = Invoke-GitOut $WT @('status', '--porcelain')
  if ($dirty) {
    Stop-Release ("release worktree has {0} local change(s); never edit it. Inspect with: git -C {1} status" -f @($dirty -split "`n").Count, $WT)
  }
}

# Move the (clean) detached worktree to $Sha.
function Switch-Worktree([string]$Sha) {
  $head = Get-WorktreeHead
  if ($head -eq $Sha) { Write-Info ("worktree already at {0}" -f $Sha.Substring(0, 12)); return }
  Write-Step ("Worktree: {0} -> {1} (detached)" -f $head.Substring(0, 12), $Sha.Substring(0, 12))
  & git -C $WT checkout --quiet --detach $Sha | Out-Host
  if ($LASTEXITCODE -ne 0) { Stop-Release "git checkout --detach $Sha failed in $WT" }
  Assert-Worktree
}

# Release ships only commits on main (AGENTS.md): refuse anything else unless -Force (owner's OK).
function Assert-OnMain([string]$Sha, [string]$What) {
  & git -C $Main merge-base --is-ancestor $Sha 'main' 2>$null
  $rc = $LASTEXITCODE
  if ($rc -eq 0) { return }
  if ($rc -ne 1) { Stop-Release ("cannot check whether {0} is on main (git merge-base exit {1}); does local branch main exist?" -f $What, $rc) }
  if (-not $Force) {
    Stop-Release ("{0} ({1}) is not on main. Release ships only commits on main: merge it into main first, or pass -Force with the owner's OK." -f $What, $Sha.Substring(0, 12))
  }
  Write-Warning ("-Force: {0} ({1}) is not on main" -f $What, $Sha.Substring(0, 12))
}

# Move the worktree to the commit of an already built tag, so compose, Dockerfiles and release.env.example match
# the images. Returns $false (with a warning) when the commit is unknown; the worktree then stays where it is.
function Switch-WorktreeToTag([string]$T) {
  $s = Get-ShaForTag $T
  if (-not $s) {
    Write-Warning ("the commit of tag {0} is unknown (not in deployments.tsv or this repository); the worktree stays at {1}, so compose and release.env.example may not match the images" -f $T, (Get-WorktreeHead).Substring(0, 12))
    return $false
  }
  Switch-Worktree $s
  return $true
}

# ---------------------------------------------------------------- docker / compose helpers
function Test-DockerUp {
  try {
    $exe = (Get-Command docker -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $exe
    $psi.Arguments = 'info --format {{.ServerVersion}}'
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    $p = [System.Diagnostics.Process]::Start($psi)
    $null = $p.StandardOutput.ReadToEndAsync()
    $null = $p.StandardError.ReadToEndAsync()
    if (-not $p.WaitForExit(20000)) { try { $p.Kill() } catch {}; return $false }
    return ($p.ExitCode -eq 0)
  } catch { return $false }
}

function Assert-Docker {
  if (-not (Test-DockerUp)) { Stop-Release 'Docker is not responding. Start Docker Desktop (dev-up.ps1 -RecoverDocker fixes stale sockets).' }
}

# Points compose at the worktree, the release env file and a tag. Variables that release.env defines are
# removed from this process first: compose prefers the shell environment over --env-file.
function Set-ReleaseEnv([string]$T) {
  if (-not (Test-Path -LiteralPath $EnvFile)) { Stop-Release ("{0} is missing; run: release.ps1 init-env" -f (Get-RelPath $EnvFile)) }
  if (-not (Test-Path -LiteralPath $ComposeFile)) { Stop-Release "release compose file missing: $ComposeFile (run: release.ps1 init)" }
  foreach ($e in @(Read-DotEnv $EnvFile)) {
    if ($e.Key -and ($ProtectedEnv -notcontains $e.Key.ToUpperInvariant())) {
      Remove-Item -LiteralPath ("Env:\" + $e.Key) -ErrorAction SilentlyContinue
    }
  }
  $env:PLANE_RELEASE_WORKTREE = ($WT -replace '\\', '/')
  $env:PLANE_RELEASE_ENV_FILE = ($EnvFile -replace '\\', '/')
  $env:RELEASE_TAG = $T
}

function Get-RCArgs([string[]]$A) { return @('compose', '-p', $Project, '-f', $ComposeFile, '--env-file', $EnvFile) + @($A) }

# Streams output; throws on failure.
function Invoke-RC([string[]]$A) {
  $argv = Get-RCArgs $A
  & docker @argv | Out-Host
  $code = $LASTEXITCODE
  if ($code -ne 0) { Stop-Release ("docker compose {0} failed (exit {1})" -f ($A -join ' '), $code) }
}

# Streams output; returns the exit code.
function Invoke-RCCode([string[]]$A) {
  $argv = Get-RCArgs $A
  & docker @argv | Out-Host
  return $LASTEXITCODE
}

# Captures stdout and stderr separately, in memory (used for output that must not be shown or must be parsed).
function Invoke-RCCapture([string[]]$A) {
  $argv = Get-RCArgs $A
  $out = New-Object System.Collections.Generic.List[string]
  $err = New-Object System.Collections.Generic.List[string]
  & docker @argv 2>&1 | ForEach-Object {
    if ($_ -is [System.Management.Automation.ErrorRecord]) { $err.Add([string]$_.Exception.Message) } else { $out.Add([string]$_) }
  }
  $code = $LASTEXITCODE
  return [pscustomobject]@{ Code = $code; Out = $out.ToArray(); Err = $err.ToArray() }
}

# Project "plane", service "plane-db": plane-plane-db-1 before the cutover, plane-release-db after it. The labels
# alone are not proof (a stray `-p plane -f docker-compose-local.yml up` gives them to a container on the DEBUG
# volume), so the container must also mount volume plane_pgdata as its data directory.
function Get-ReleaseDb {
  $raw = @(& docker ps --filter 'label=com.docker.compose.project=plane' --filter 'label=com.docker.compose.service=plane-db' --format '{{.Names}}' 2>$null)
  if ($LASTEXITCODE -ne 0) { Stop-Release 'docker ps failed; cannot find the release DB container' }
  $names = @($raw | Where-Object { $_ })
  if ($names.Count -ne 1) {
    Stop-Release ("expected exactly one running release DB container (compose project plane, service plane-db); found {0}. Start it with: release.ps1 infra" -f $names.Count)
  }
  $db = [string]$names[0]
  $mj = & docker inspect --format '{{json .Mounts}}' $db 2>$null
  $code = $LASTEXITCODE
  $mounts = $null
  # Assign before wrapping: Windows PowerShell 5.1's ConvertFrom-Json emits a JSON array as ONE pipeline object.
  if ($code -eq 0) { try { $mounts = ($mj | Out-String) | ConvertFrom-Json } catch { $mounts = $null } }
  $pg = @(@($mounts) | Where-Object { $_ -and $_.Destination -eq '/var/lib/postgresql/data' })
  if ($code -ne 0 -or $pg.Count -ne 1 -or [string]$pg[0].Type -ne 'volume' -or [string]$pg[0].Name -ne 'plane_pgdata') {
    Stop-Release ("{0} does not mount volume plane_pgdata at /var/lib/postgresql/data; refusing to treat it as the release DB (a stray 'docker compose -p plane' run? see AGENTS.md)" -f $db)
  }
  return $db
}

function Get-MissingImages([string]$T) {
  $missing = @()
  foreach ($n in $ImageNames) {
    $ref = "plane-release/${n}:$T"
    & docker image inspect --format '{{.Id}}' $ref 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { $missing += $ref }
  }
  return $missing
}

function Assert-Volumes {
  $missing = @()
  foreach ($v in $ReleaseVolumes) {
    & docker volume inspect --format '{{.Name}}' $v 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { $missing += $v }
  }
  if ($missing.Count) {
    Stop-Release ("release data volume(s) missing: {0}. Never create them by hand: stop and tell the owner." -f ($missing -join ', '))
  }
}

# Project "plane" must hold only plane-release-* (and one-off plane-migrator-run-*) containers.
# Before the cutover it still holds the pre-split dev containers (plane-api-1, plane-plane-db-1, ...): any release
# `up` would replace them in place, so refuse until cutover Phase C (C6) removed them.
# After the cutover (tag.env exists) other names are strays from a `docker compose -p plane ...` accident that
# replaced release containers. With -Replace (up/rollback -Force, owner's OK) they are stopped and removed by exact
# name (never `compose down`, never -v: volumes are kept) so the deployed tag can be re-created.
function Assert-NoLegacyContainers([switch]$Replace) {
  $raw = @(& docker ps -a --filter 'label=com.docker.compose.project=plane' --format '{{.Names}}' 2>$null)
  if ($LASTEXITCODE -ne 0) { Stop-Release 'docker ps failed; cannot verify that project plane has no pre-split or stray containers' }
  $names = @($raw | Where-Object { $_ })
  $legacy = @($names | Where-Object { $_ -notlike 'plane-release-*' -and $_ -notlike 'plane-migrator-run-*' })
  if (-not $legacy.Count) { return }
  $deployed = Get-DeployedTag
  if ($Replace -and $deployed) {
    Write-Warning ("removing stray containers in project plane (volumes kept): {0}" -f ($legacy -join ', '))
    & docker stop --time 60 @legacy | Out-Host
    & docker rm @legacy | Out-Host
    if ($LASTEXITCODE -ne 0) { Stop-Release 'docker rm of the stray containers failed; nothing else was changed' }
    return
  }
  if ($deployed) {
    Stop-Release ("compose project 'plane' has containers that are not plane-release-* ({0}): strays from a 'docker compose -p plane ...' command. Tell the owner; with the owner's OK rerun: release.ps1 up -Force (removes them by name, keeps volumes)." -f ($legacy -join ', '))
  }
  Stop-Release ("compose project 'plane' still has pre-split containers ({0}). Finish the cutover (C6: old stack stopped and removed, volumes kept) first; see AGENTS.md." -f ($legacy -join ', '))
}

function Assert-Port3300 {
  $raw = @(& docker ps --filter 'publish=3300' --format '{{.Names}}' 2>$null)
  if ($LASTEXITCODE -ne 0) { Stop-Release 'docker ps failed; cannot verify who publishes port 3300' }
  $holders = @($raw | Where-Object { $_ -and $_ -ne 'plane-release-proxy' })
  if ($holders.Count) {
    Stop-Release ("port 3300 is published by {0}; only plane-release-proxy may hold 127.0.0.1:3300" -f ($holders -join ', '))
  }
  $dockerProcs = @('com.docker.backend', 'com.docker.proxy', 'wslrelay', 'vpnkit', 'dockerd', 'docker-proxy')
  $conns = @(Get-NetTCPConnection -State Listen -LocalPort 3300 -ErrorAction SilentlyContinue |
      Where-Object { @('127.0.0.1', '0.0.0.0', '::', '::1') -contains $_.LocalAddress })
  foreach ($c in $conns) {
    $p = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
    $pn = if ($p) { $p.ProcessName } else { "pid $($c.OwningProcess)" }
    if ($dockerProcs -notcontains $pn) {
      Stop-Release ("{0} port 3300 is held by a non-Docker process ({1}); nothing but the release proxy may use 3300" -f $c.LocalAddress, $pn)
    }
  }
}

function Assert-ReleaseEnvFile {
  if (-not (Test-Path -LiteralPath $EnvFile)) { Stop-Release ("{0} is missing; run: release.ps1 init-env" -f (Get-RelPath $EnvFile)) }
  if (-not (Test-Path -LiteralPath $ExampleFile)) { Stop-Release "release.env.example is missing in the worktree ($ExampleFile)" }
  $map = Get-EnvMap @(Read-DotEnv $EnvFile)
  $missing = @(Get-DotEnvKeys $ExampleFile | Where-Object { -not $map.ContainsKey($_) })
  $forbidden = @($map.Keys | Where-Object { ($ForbiddenKeys -contains $_) -or ($_ -like 'COMPOSE_*') })
  $empty = @($RequiredNonEmpty | Where-Object { -not $map.ContainsKey($_) -or -not $map[$_] })
  $problems = @()
  if ($missing.Count) { $problems += ("keys missing (listed in release.env.example): " + ($missing -join ', ')) }
  if ($forbidden.Count) { $problems += ("keys that must be absent: " + ($forbidden -join ', ')) }
  if ($empty.Count) { $problems += ("required keys that are empty: " + ($empty -join ', ')) }
  # Values must point at the release services (a wrong host would migrate/serve an empty or foreign database).
  $wrong = @()
  if ((Get-ExpandedValue $map 'POSTGRES_HOST') -cne 'plane-db') { $wrong += 'POSTGRES_HOST (must be plane-db)' }
  if ((Get-ExpandedValue $map 'DATABASE_URL') -and ((Get-ExpandedValue $map 'DATABASE_URL') -notmatch '@plane-db(:5432)?/')) { $wrong += 'DATABASE_URL (must point at plane-db:5432)' }
  if ((Get-ExpandedValue $map 'REDIS_URL') -notmatch '^redis://plane-redis:6379/?$') { $wrong += 'REDIS_URL (must be redis://plane-redis:6379/)' }
  if ((Get-ExpandedValue $map 'AWS_S3_ENDPOINT_URL') -cne 'http://plane-minio:9000') { $wrong += 'AWS_S3_ENDPOINT_URL (must be http://plane-minio:9000)' }
  if ((Get-ExpandedValue $map 'RABBITMQ_HOST') -cne 'plane-mq') { $wrong += 'RABBITMQ_HOST (must be plane-mq)' }
  if ((Get-ExpandedValue $map 'AMQP_URL') -and ((Get-ExpandedValue $map 'AMQP_URL') -notmatch '@plane-mq(:5672)?/')) { $wrong += 'AMQP_URL (must point at plane-mq:5672)' }
  $debugish = @($map.Keys | Where-Object { (Get-ExpandedValue $map $_) -match 'host\.docker\.internal|:(8310|55433|56380|9310|9391)(?![0-9])' } | Sort-Object)
  if ($debugish.Count) { $wrong += ('values that point at the host or a DEBUG port (host.docker.internal, 8310, 55433, 56380, 9310, 9391): ' + ($debugish -join ', ')) }
  if ($wrong.Count) { $problems += ('wrong values (not shown): ' + ($wrong -join '; ')) }
  if ($problems.Count) {
    foreach ($p in $problems) { Write-Host "    - $p" -ForegroundColor Red }
    Stop-Release ("{0} failed the checks above (values are never shown); edit it by hand" -f (Get-RelPath $EnvFile))
  }
}

# Parses `docker compose config --format json` IN MEMORY (it expands secrets; never print it) and asserts the
# release invariants. Requires Set-ReleaseEnv first.
function Assert-ComposeConfig {
  # --profile migrate: without it the migrator (the one service that writes the schema) is not in the output.
  $r = Invoke-RCCapture @('--profile', 'migrate', 'config', '--format', 'json')
  if ($r.Code -ne 0) {
    # A failed config names keys and files, never values.
    $r.Err | Select-Object -Last 8 | ForEach-Object { Write-Host "    $_" -ForegroundColor Red }
    Stop-Release 'docker compose config failed (see above)'
  }
  $cfg = $null
  try { $cfg = ($r.Out -join "`n") | ConvertFrom-Json } catch { $cfg = $null }
  if (-not $cfg) { Stop-Release 'could not parse the docker compose config output (not shown: it contains secrets)' }

  $problems = New-Object System.Collections.Generic.List[string]
  if ([string]$cfg.name -ne $Project) { $problems.Add(("project name is '{0}', expected '{1}'" -f $cfg.name, $Project)) }

  $volNames = @()
  $volByKey = @{}
  if ($cfg.PSObject.Properties['volumes']) {
    foreach ($v in @($cfg.volumes.PSObject.Properties)) {
      $isExt = ($null -ne $v.Value.PSObject.Properties['external']) -and ($v.Value.external -eq $true)
      if (-not $isExt) { $problems.Add(("volume '{0}' is not external" -f $v.Name)) }
      $volNames += [string]$v.Value.name
      $volByKey[[string]$v.Name] = [string]$v.Value.name
    }
  }
  $haveVols = (@($volNames | Sort-Object) -join ',')
  $wantVols = (@($ReleaseVolumes | Sort-Object) -join ',')
  if ($haveVols -ne $wantVols) { $problems.Add(("volumes are [{0}], expected exactly [{1}]" -f $haveVols, $wantVols)) }

  # Networks: only the project's own non-external default network (plane_default). An external network (e.g. the
  # debug plane-dev_dev_env) would put two `plane-db` DNS names on one network.
  $netKeys = @()
  if ($cfg.PSObject.Properties['networks'] -and $cfg.networks) {
    foreach ($nw in @($cfg.networks.PSObject.Properties)) {
      $netKeys += [string]$nw.Name
      if ($nw.Value -and $nw.Value.PSObject.Properties['external'] -and $nw.Value.external -eq $true) { $problems.Add(("network '{0}' is external" -f $nw.Name)) }
    }
  }
  if ((@($netKeys | Sort-Object) -join ',') -ne 'default') { $problems.Add(("networks are [{0}], expected only the project's own 'default'" -f (@($netKeys | Sort-Object) -join ','))) }

  # Each data volume belongs to exactly one service at one path (two postmasters on plane_pgdata corrupt it).
  $volOwner = @{
    'plane_pgdata'        = 'plane-db|/var/lib/postgresql/data'
    'plane_uploads'       = 'plane-minio|/export'
    'plane_redisdata'     = 'plane-redis|/data'
    'plane_rabbitmq_data' = 'plane-mq|/var/lib/rabbitmq'
  }
  $volUse = @{}

  $wtN = ConvertTo-NormPath $WT
  $published = New-Object System.Collections.Generic.List[string]
  $services = @($cfg.services.PSObject.Properties)
  $backendImage = 'plane-release/backend:' + $env:RELEASE_TAG
  if (-not ($services | Where-Object { $_.Name -eq 'migrator' })) { $problems.Add('service migrator is missing (profile migrate)') }
  foreach ($s in $services) {
    $n = $s.Name
    $svc = $s.Value
    $cn = if ($svc.PSObject.Properties['container_name']) { [string]$svc.container_name } else { '' }
    $img = if ($svc.PSObject.Properties['image']) { [string]$svc.image } else { '' }
    $vols = if ($svc.PSObject.Properties['volumes'] -and $svc.volumes) { @($svc.volumes) } else { @() }
    if ($n -eq 'migrator') {
      # One-off only (run --rm): no fixed name, the backend image of this tag, production settings, no mounts.
      if ($cn) { $problems.Add(("service migrator has container_name '{0}'; it must have none (one-off runs only)" -f $cn)) }
      if ($img -cne $backendImage) { $problems.Add(("service migrator runs image '{0}', expected {1}" -f $img, $backendImage)) }
      if ($vols.Count) { $problems.Add('service migrator has volumes; it must have none') }
    } elseif (-not $cn.StartsWith('plane-release-')) { $problems.Add(("service {0} has container_name '{1}', expected plane-release-*" -f $n, $cn)) }
    if (@('migrator', 'api', 'worker', 'beat-worker') -contains $n) {
      $cmd = if ($svc.PSObject.Properties['command'] -and $svc.command) { (@($svc.command) -join ' ') } else { '' }
      if ($cmd -match '--settings') { $problems.Add(("service {0} passes --settings in its command; release uses production settings" -f $n)) }
      if ($svc.PSObject.Properties['environment'] -and $svc.environment -and $svc.environment.PSObject.Properties['DJANGO_SETTINGS_MODULE']) {
        $problems.Add(("service {0} sets DJANGO_SETTINGS_MODULE; release uses production settings" -f $n))
      }
    }
    if ($svc.PSObject.Properties['network_mode'] -and $svc.network_mode) { $problems.Add(("service {0} sets network_mode" -f $n)) }
    if ($svc.PSObject.Properties['networks'] -and $svc.networks) {
      $sn = @($svc.networks.PSObject.Properties | ForEach-Object { $_.Name })
      if ((@($sn | Sort-Object) -join ',') -ne 'default') { $problems.Add(("service {0} joins networks [{1}], expected only default" -f $n, ($sn -join ','))) }
    }
    if ($svc.PSObject.Properties['ports']) {
      foreach ($p in @($svc.ports)) { $published.Add(('{0} {1}:{2}->{3}' -f $n, $p.host_ip, $p.published, $p.target)) }
    }
    if ($svc.PSObject.Properties['build'] -and $svc.build) {
      $ctx = ConvertTo-NormPath ([string]$svc.build.context)
      if (-not ($ctx -eq $wtN -or $ctx.StartsWith($wtN + '\'))) { $problems.Add(("service {0} builds from {1}, outside the release worktree" -f $n, $svc.build.context)) }
    }
    foreach ($m in $vols) {
      if (@('volume', 'tmpfs') -notcontains [string]$m.type) { $problems.Add(("service {0} has a {1} mount at {2}" -f $n, $m.type, $m.target)); continue }
      if ([string]$m.type -eq 'volume') {
        $vn = if ($volByKey.ContainsKey([string]$m.source)) { $volByKey[[string]$m.source] } else { [string]$m.source }
        if (-not $volUse.ContainsKey($vn)) { $volUse[$vn] = @() }
        $volUse[$vn] += ('{0}|{1}' -f $n, $m.target)
      }
    }
    if ($n -eq 'plane-db') {
      if ($img -notlike 'postgres:15.*') { $problems.Add(("service plane-db runs image '{0}', expected postgres:15.* (plane_pgdata is a PostgreSQL 15 cluster)" -f $img)) }
      $pgd = ''
      if ($svc.PSObject.Properties['environment'] -and $svc.environment -and $svc.environment.PSObject.Properties['PGDATA']) { $pgd = [string]$svc.environment.PGDATA }
      if ($pgd -cne '/var/lib/postgresql/data') { $problems.Add("service plane-db must set PGDATA=/var/lib/postgresql/data") }
    }
    if ($img -like 'plane-release/*' -and $img -notlike ('*:' + $env:RELEASE_TAG)) { $problems.Add(("service {0} image {1} does not carry tag {2}" -f $n, $img, $env:RELEASE_TAG)) }
    if (@('api', 'worker', 'beat-worker', 'live', 'space', 'proxy') -contains $n -and $img -notlike 'plane-release/*') {
      $problems.Add(("service {0} runs image '{1}', expected plane-release/*" -f $n, $img))
    }
  }
  foreach ($vn in $volOwner.Keys) {
    $uses = if ($volUse.ContainsKey($vn)) { @($volUse[$vn]) } else { @() }
    if ((@($uses) -join ',') -cne $volOwner[$vn]) {
      $problems.Add(("volume {0} is mounted by [{1}], expected exactly [{2}]" -f $vn, (@($uses) -join ', '), $volOwner[$vn]))
    }
  }
  $pub = ($published.ToArray() -join '; ')
  if ($pub -ne 'proxy 127.0.0.1:3300->80') { $problems.Add(("published ports are [{0}], expected only 'proxy 127.0.0.1:3300->80'" -f $pub)) }

  if ($problems.Count) {
    foreach ($p in $problems) { Write-Host "    - $p" -ForegroundColor Red }
    Stop-Release 'the release compose config failed the safety checks above'
  }
  Write-Info ("compose config OK: project plane, 4 external plane_* volumes each owned by its one service, only network default, only 127.0.0.1:3300, builds from the worktree, no bind mounts, migrator one-off on {0} ({1} services)" -f $backendImage, $services.Count)
}

# ---------------------------------------------------------------- lock, tag and deployment log
function Enter-Lock {
  if ($script:LockHeld) { return }
  if (-not (Test-Path -LiteralPath $StateDir)) { New-Item -ItemType Directory -Force -Path $StateDir | Out-Null }
  $fs = $null
  try {
    $fs = [System.IO.File]::Open($LockFile, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::Read)
  } catch [System.IO.IOException] {
    $fs = $null
  }
  if (-not $fs) {
    $info = ''
    try { $info = ([System.IO.File]::ReadAllText($LockFile)).Trim() } catch { $info = '(unreadable)' }
    $lockPid = 0
    if ($info -match '^pid=(\d+)') { $lockPid = [int]$Matches[1] }
    $alive = ($lockPid -gt 0) -and [bool](Get-Process -Id $lockPid -ErrorAction SilentlyContinue)
    $state = if ($alive) { "process $lockPid is still running" } else { "process $lockPid is NOT running, so the lock looks stale: make sure no release.ps1 is running, then delete the file by hand" }
    Stop-Release ("deploy lock is held: {0} [{1}]; {2}" -f (Get-RelPath $LockFile), $info, $state)
  }
  try {
    $bytes = $Utf8NoBom.GetBytes(("pid={0} started={1} verb={2}`n" -f $PID, (Get-Date -Format s), $Command))
    $fs.Write($bytes, 0, $bytes.Length)
  } finally { $fs.Close() }
  $script:LockHeld = $true
}

function Exit-Lock {
  if (-not $script:LockHeld) { return }
  try {
    $info = [System.IO.File]::ReadAllText($LockFile)
    if ($info -match ('^pid=' + $PID + '\s')) { Remove-Item -LiteralPath $LockFile -Force }
  } catch {}
  $script:LockHeld = $false
}

function Get-DeployedTag {
  if (-not (Test-Path -LiteralPath $TagFile)) { return '' }
  foreach ($l in [System.IO.File]::ReadAllLines($TagFile)) {
    if ($l -match '^\s*RELEASE_TAG=([0-9a-f]{12})\s*$') { return $Matches[1] }
  }
  return ''
}

function Write-TagFile([string]$T) { Write-Utf8NoBom $TagFile ("RELEASE_TAG={0}`n" -f $T) }

function Get-DeployRows {
  if (-not (Test-Path -LiteralPath $DeployLog)) { return }
  foreach ($line in [System.IO.File]::ReadAllLines($DeployLog)) {
    if (-not $line -or $line.StartsWith('utc')) { continue }
    $f = $line -split "`t"
    if ($f.Count -lt 7) { continue }
    [pscustomobject]@{ Utc = $f[0]; Tag = $f[1]; Sha = $f[2]; Prev = $f[3]; Checkpoint = $f[4]; Migrations = $f[5]; Result = $f[6]; Line = $line }
  }
}

# Columns: utc, tag, full sha, prev tag, checkpoint, migrations applied, result.
function Add-DeployRow([string]$T, [string]$Sha, [string]$Prev, [string]$Checkpoint, [string]$Migrations, [string]$Result) {
  if (-not (Test-Path -LiteralPath $DeployLog)) { Write-Utf8NoBom $DeployLog "utc`ttag`tsha`tprev`tcheckpoint`tmigrations`tresult`n" }
  $utc = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
  $cells = foreach ($c in @($utc, $T, $Sha, $Prev, $Checkpoint, $Migrations, $Result)) {
    if ([string]::IsNullOrEmpty($c)) { '-' } else { ($c -replace "[`t`r`n]", ' ') }
  }
  Add-Utf8NoBom $DeployLog ((@($cells) -join "`t") + "`n")
}

function Get-ShaForTag([string]$T) {
  if (-not $T) { return '' }
  $row = @(Get-DeployRows | Where-Object { $_.Tag -eq $T -and $_.Sha -match '^[0-9a-f]{40}$' }) | Select-Object -Last 1
  if ($row) { return $row.Sha }
  $sha = Invoke-GitOut $Main @('rev-parse', '--verify', '--quiet', ($T + '^{commit}')) -AllowFail
  if ($sha) { return $sha }
  return ''
}

# ---------------------------------------------------------------- health
function Invoke-Probe([string]$Url) {
  $res = [pscustomobject]@{ Code = 0; Type = ''; Body = ''; Error = '' }
  try {
    $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 10 -ErrorAction Stop
    $res.Code = [int]$r.StatusCode
    $res.Type = [string]$r.Headers['Content-Type']
    $res.Body = [string]$r.Content
  } catch {
    $resp = $_.Exception.Response
    if ($resp) { $res.Code = [int]$resp.StatusCode; $res.Type = [string]$resp.ContentType }
    else { $res.Error = [string]$_.Exception.Message }
  }
  return $res
}

function Format-Probe($R) {
  if ($R.Code) { return ("HTTP {0} {1}" -f $R.Code, $R.Type).Trim() }
  return 'no answer'
}

# Returns failure descriptions (none = healthy).
function Get-HealthReport([string]$ExpectedTag) {
  $fails = New-Object System.Collections.Generic.List[string]
  $r = Invoke-Probe "$BaseUrl/"
  if ($r.Code -ne 200 -or $r.Type -notlike 'text/html*') { $fails.Add(("/ -> {0} (want 200 text/html)" -f (Format-Probe $r))) }
  $r = Invoke-Probe "$BaseUrl/api/instances/"
  if ($r.Code -ne 200 -or $r.Type -notlike '*json*') { $fails.Add(("/api/instances/ -> {0} (want 200 JSON)" -f (Format-Probe $r))) }
  $r = Invoke-Probe "$BaseUrl/god-mode/"
  if ($r.Code -ne 200 -or $r.Body -notmatch '/god-mode/assets') { $fails.Add(("/god-mode/ -> {0} (want 200 with /god-mode/assets in the page)" -f (Format-Probe $r))) }
  $r = Invoke-Probe "$BaseUrl/spaces/"
  if ($r.Code -ne 200) { $fails.Add(("/spaces/ -> {0} (want 200)" -f (Format-Probe $r))) }
  $r = Invoke-Probe "$BaseUrl/live/health"
  if ($r.Code -ne 200) { $fails.Add(("/live/health -> {0} (want 200)" -f (Format-Probe $r))) }
  $r = Invoke-Probe "$BaseUrl/uploads/"
  if (@(400, 403) -notcontains $r.Code) { $fails.Add(("/uploads/ -> {0} (want 400 or 403 from MinIO)" -f (Format-Probe $r))) }

  foreach ($c in $AppContainers) {
    $info = @(& docker inspect -f '{{.State.Status}}|{{.Config.Image}}' $c 2>$null)
    if ($LASTEXITCODE -ne 0 -or -not $info.Count -or -not $info[0]) { $fails.Add("container $c is missing"); continue }
    $parts = ([string]$info[0]).Split('|')
    if ($parts[0] -ne 'running') { $fails.Add(("container {0} is {1}" -f $c, $parts[0])) }
    if ($ExpectedTag -and $parts[1] -notlike ('plane-release/*:' + $ExpectedTag)) { $fails.Add(("container {0} runs {1}, expected tag {2}" -f $c, $parts[1], $ExpectedTag)) }
  }
  $top = @(& docker top plane-release-worker 2>$null)
  if ($LASTEXITCODE -eq 0) {
    $celery = @($top | Where-Object { $_ -match 'celery' }).Count
    if ($celery -gt 3) { $fails.Add(("plane-release-worker runs {0} celery processes (want at most 3: CELERY_WORKER_CONCURRENCY=2)" -f $celery)) }
  }
  return $fails.ToArray()
}

function Test-ReleaseHealth([string]$ExpectedTag, [int]$TimeoutSec = 180) {
  Write-Step ("Health checks via {0} (up to {1}s)" -f $BaseUrl, $TimeoutSec)
  $deadline = (Get-Date).AddSeconds($TimeoutSec)
  $fails = @()
  while ($true) {
    $fails = @(Get-HealthReport $ExpectedTag)
    if ($fails.Count -eq 0) {
      Write-Ok 'healthy: / /api/instances/ /god-mode/ /spaces/ /live/health /uploads/, containers on the expected tag, celery <= 3 processes'
      return $true
    }
    if ((Get-Date) -ge $deadline) { break }
    Start-Sleep -Seconds 5
  }
  foreach ($f in $fails) { Write-Host "    FAIL $f" -ForegroundColor Red }
  return $false
}

# The phone path (Tailscale Serve -> 127.0.0.1:3300). Warning only: a failure here is a Tailscale problem, and
# reverting a healthy deploy would not fix it. The host name is not printed.
function Test-PublicHost {
  if (-not (Test-Path -LiteralPath $PublicHostFile)) { Write-Info 'no .local/release/public-host: phone-path check skipped'; return }
  $h = ([System.IO.File]::ReadAllText($PublicHostFile)).Trim()
  if ($h -notmatch '^[A-Za-z0-9.-]+$') { Write-Warning 'public-host file is empty or malformed; phone-path check skipped'; return }
  $r = $null
  for ($i = 0; $i -lt 3; $i++) {
    $r = Invoke-Probe ("http://{0}:3300/api/instances/" -f $h)
    if ($r.Code -eq 200) { Write-Ok 'phone path OK: /api/instances/ through the public host (Tailscale Serve)'; return }
    Start-Sleep -Seconds 3
  }
  $what = if ($r.Code) { "HTTP $($r.Code)" } else { 'no answer' }
  Write-Warning ("phone path check FAILED ({0}) for /api/instances/ through the public host. 127.0.0.1:3300 is healthy; check Tailscale Serve (tcp 3300 -> 127.0.0.1:3300) and tell the owner." -f $what)
}

function Write-RecoveryHint([string]$PrevTag, [string]$Checkpoint) {
  Write-Host 'Recovery options (each only with the owner''s OK):' -ForegroundColor Yellow
  $cmd = 'powershell -ExecutionPolicy Bypass -File scripts\local\release.ps1'
  if ($PrevTag) { Write-Host ("  code only : {0} rollback -Tag {1}   (migrations stay applied)" -f $cmd, $PrevTag) }
  if ($Checkpoint) {
    $t = if ($PrevTag) { $PrevTag } else { '<sha12>' }
    Write-Host ("  code+data : {0} rollback -Tag {1} -RestoreDump {2}   (loses writes since the checkpoint)" -f $cmd, $t, $Checkpoint)
  }
  if (-not $PrevTag) {
    Write-Host '  first deploy (there is no earlier release tag to go back to):'
    Write-Host ("    1. {0} compose -IKnowThisIsRelease down   (never -v; the plane_* volumes are external and stay)" -f $cmd)
    Write-Host '    2. tell the owner; the pre-split stack can be restarted from the tooling backed up under .local\backups\pre-split-*'
    Write-Host '       (its docker-compose-local.yml, dev-up.ps1 and web-prod.ps1), which runs on the same plane_* volumes'
    if ($Checkpoint) { Write-Host ("    3. only if the data is suspect: restore {0} into that database (owner's OK; the dropdb/createdb/pg_restore steps of rollback -RestoreDump)" -f $Checkpoint) }
  }
}

# ---------------------------------------------------------------- building blocks
function Write-DriftWarning {
  $web = Join-Path $WT 'apps\web\Dockerfile.web'
  $fe = Join-Path $WT 'scripts\local\release\Dockerfile.frontend'
  if (-not (Test-Path -LiteralPath $web) -or -not (Test-Path -LiteralPath $fe)) { Write-Warning 'drift check skipped: Dockerfile.web or Dockerfile.frontend not found in the worktree'; return }
  $get = {
    param($Path, $Pattern)
    $m = Select-String -LiteralPath $Path -Pattern $Pattern | Select-Object -First 1
    if ($m) { $m.Matches[0].Groups[1].Value } else { '' }
  }
  $nodeWeb = & $get $web '^\s*FROM\s+(node:\S+)'
  $nodeFe = & $get $fe '^\s*FROM\s+(node:\S+)'
  $turboWeb = & $get $web '^\s*ARG\s+TURBO_VERSION=(\S+)'
  $turboFe = & $get $fe '^\s*ARG\s+TURBO_VERSION=(\S+)'
  # Upstream bumps APK_SECURITY_PATCH to force a fresh `apk upgrade` layer; both Dockerfile.frontend stages use one value.
  $apkWeb = & $get $web '^\s*ARG\s+APK_SECURITY_PATCH=(\S+)'
  $apkFe = & $get $fe '^\s*ARG\s+APK_SECURITY_PATCH=(\S+)'
  $drift = @()
  if (-not $nodeWeb -or $nodeWeb -ne $nodeFe) { $drift += ("node base image: apps/web/Dockerfile.web '{0}' vs Dockerfile.frontend '{1}'" -f $nodeWeb, $nodeFe) }
  if (-not $turboWeb -or $turboWeb -ne $turboFe) { $drift += ("TURBO_VERSION: apps/web/Dockerfile.web '{0}' vs Dockerfile.frontend '{1}'" -f $turboWeb, $turboFe) }
  if (-not $apkWeb -or $apkWeb -ne $apkFe) { $drift += ("APK_SECURITY_PATCH: apps/web/Dockerfile.web '{0}' vs Dockerfile.frontend '{1}'" -f $apkWeb, $apkFe) }
  foreach ($d in $drift) { Write-Warning ("upstream drift: {0}; update scripts/local/release/Dockerfile.frontend" -f $d) }
}

function Invoke-ReleaseBuild([string]$T) {
  Write-DriftWarning
  if (-not (Test-Path -LiteralPath $LogDir)) { New-Item -ItemType Directory -Force -Path $LogDir | Out-Null }
  $log = Join-Path $LogDir ("release-build-{0}.log" -f $T)
  $a = @('build')
  if ($NoCache) { $a += '--no-cache' }
  $a += @('api', 'proxy', 'space', 'live')
  $argv = Get-RCArgs $a
  Write-Step ("Building plane-release/{{backend,proxy,space,live}}:{0} from {1} (log: {2})" -f $T, $WT, (Get-RelPath $log))
  $sw = New-Object System.IO.StreamWriter($log, $true, $Utf8NoBom)
  $sw.NewLine = "`n"
  $code = 1
  try {
    $sw.WriteLine(("===== {0} build {1} {2}" -f (Get-Date -Format s), $T, ($a -join ' ')))
    & docker @argv 2>&1 | ForEach-Object {
      $l = if ($_ -is [System.Management.Automation.ErrorRecord]) { [string]$_.Exception.Message } else { [string]$_ }
      $sw.WriteLine($l)
      Write-Host $l
    }
    $code = $LASTEXITCODE
  } finally { $sw.Close() }
  if ($code -ne 0) { Stop-Release ("build failed (exit {0}); see {1}" -f $code, (Get-RelPath $log)) }
  $missing = @(Get-MissingImages $T)
  if ($missing.Count) { Stop-Release ("build finished but images are missing: {0}" -f ($missing -join ', ')) }
  Write-Ok ("built plane-release/{{backend,proxy,space,live}}:{0} (i18n and caddy validate gates ran inside the build)" -f $T)
}

function Start-Infra {
  Write-Step 'Infra: plane-db, plane-redis, plane-mq, plane-minio (external plane_* volumes)'
  Invoke-RC @('up', '-d', '--no-build', '--wait', '--wait-timeout', '180', 'plane-db', 'plane-redis', 'plane-mq', 'plane-minio')
}

function New-Checkpoint([string]$Label) {
  if ($Label -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$') { Stop-Release "invalid checkpoint label '$Label' (letters, digits, dot, underscore, dash)" }
  $db = Get-ReleaseDb
  $ts = Get-Date -Format 'yyyyMMdd-HHmmss'
  if (-not (Test-Path -LiteralPath $CheckpointDir)) { New-Item -ItemType Directory -Force -Path $CheckpointDir | Out-Null }
  $file = Join-Path $CheckpointDir ("release-{0}-{1}.dump" -f $ts, $Label)
  $tmp = "/tmp/release-ck-$ts.dump"
  Write-Step ("Checkpoint: pg_dump -Fc in {0} -> {1}" -f $db, (Get-RelPath $file))
  $err = ''
  $entries = 0
  try {
    # No double quotes inside sh -c strings (PowerShell 5.1 mangles them); $POSTGRES_* expand inside the container.
    & docker exec $db sh -c ('pg_dump -U $POSTGRES_USER -d $POSTGRES_DB -Fc -f ' + $tmp) | Out-Host
    if ($LASTEXITCODE -ne 0) { $err = "pg_dump failed in $db" }
    if (-not $err) {
      $toc = @(& docker exec $db pg_restore -l $tmp 2>$null)
      if ($LASTEXITCODE -ne 0) { $err = 'pg_restore -l could not read the dump' }
      else {
        $entries = @($toc | Where-Object { $_ -and -not ([string]$_).StartsWith(';') }).Count
        if ($entries -eq 0) { $err = 'the dump lists no entries' }
      }
    }
    if (-not $err) {
      # Binary files move with docker cp, never through a PowerShell redirect.
      & docker cp ("{0}:{1}" -f $db, $tmp) $file | Out-Host
      if ($LASTEXITCODE -ne 0) { $err = 'docker cp of the dump failed' }
    }
  } finally {
    & docker exec $db rm -f $tmp 2>$null | Out-Null
  }
  if ($err) { Stop-Release ("checkpoint failed: {0}" -f $err) }
  if (-not (Test-Path -LiteralPath $file) -or (Get-Item -LiteralPath $file).Length -le 0) { Stop-Release "checkpoint file $file is missing or empty" }
  Write-Info ("{0} ({1:N1} MB, {2} entries)" -f (Get-RelPath $file), ((Get-Item -LiteralPath $file).Length / 1MB), $entries)
  return $file
}

# Applied migrations (django_migrations rows) of migrated apps that the image's code does not have on disk:
# renamed or deleted migrations such as the stale 0132_jp_sprints_releases row.
function Get-UnknownApplied {
  $py = @'
from django.db import connection; from django.db.migrations.loader import MigrationLoader; l = MigrationLoader(connection); u = sorted(a + '.' + n for (a, n) in l.applied_migrations if a in l.migrated_apps and (a, n) not in l.disk_migrations); [print('UNKNOWN-APPLIED ' + x) for x in u]; print('UNKNOWN-APPLIED-CHECK-DONE')
'@
  $r = Invoke-RCCapture @('run', '--rm', '--no-deps', '-T', 'migrator', 'python', 'manage.py', 'shell', '-c', $py.Trim())
  if ($r.Code -ne 0 -or ($r.Out -notcontains 'UNKNOWN-APPLIED-CHECK-DONE')) {
    $r.Err | Select-Object -Last 15 | ForEach-Object { Write-Host "    $_" }
    Stop-Release 'the unknown-applied-migrations check did not run'
  }
  return @($r.Out | Where-Object { $_ -like 'UNKNOWN-APPLIED *' } | ForEach-Object { $_.Substring(16).Trim() })
}

function Get-MigrationPlan {
  $r = Invoke-RCCapture @('run', '--rm', '--no-deps', '-T', 'migrator', 'python', 'manage.py', 'migrate', '--plan')
  if ($r.Code -ne 0) {
    $r.Err | Select-Object -Last 15 | ForEach-Object { Write-Host "    $_" }
    Stop-Release 'migrate --plan failed'
  }
  $lines = @($r.Out)
  $empty = (@($lines | Where-Object { $_ -match 'No planned migration operations' }).Count -gt 0)
  $migs = @($lines | Where-Object { $_ -match '^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z0-9_]+$' })
  return [pscustomobject]@{ Lines = $lines; Empty = $empty; Migrations = $migs }
}

# ---------------------------------------------------------------- verbs
function Invoke-Init {
  if (Test-Path -LiteralPath $WT) { Stop-Release "$WT already exists; init never touches an existing directory" }
  $listed = Invoke-GitOut $Main @('worktree', 'list', '--porcelain')
  $wtFwd = $WT -replace '\\', '/'
  if (@($listed -split "`n" | Where-Object { $_ -eq "worktree $wtFwd" }).Count) {
    Stop-Release "git still lists a worktree at $WT although the directory is gone; check and run git worktree prune by hand"
  }
  $sha = Resolve-Commit 'main'
  Write-Step ("git worktree add --detach {0} main ({1})" -f $WT, $sha.Substring(0, 12))
  & git -C $Main worktree add --detach $WT main | Out-Host
  if ($LASTEXITCODE -ne 0) { Stop-Release 'git worktree add failed' }
  $dirty = Invoke-GitOut $WT @('status', '--porcelain')
  if ($dirty) { Stop-Release "the new worktree is not clean; investigate before building from it" }
  Write-Ok ("release worktree ready at {0}, detached at {1}" -f $WT, (Get-WorktreeHead).Substring(0, 12))
  Write-Info 'packages/i18n/locales checks out as a small text file there (core.symlinks=false): expected, the image build re-links it.'
  Write-Info 'Next: release.ps1 init-env, then release.ps1 build'
}

function Invoke-InitEnv {
  $apiEnv = Join-Path $Main 'apps\api\.env'
  $rootEnv = Join-Path $Main '.env'
  $liveEnv = Join-Path $Main 'apps\live\.env'
  if (-not (Test-Path -LiteralPath $apiEnv)) { Stop-Release "missing $apiEnv (init-env copies the release values from it)" }
  if ((Test-Path -LiteralPath $EnvFile) -and -not $Force) {
    Stop-Release ("{0} already exists; pass -Force to regenerate it (the current file is kept as a .bak copy)" -f (Get-RelPath $EnvFile))
  }
  $example = $ExampleFile
  if (-not (Test-Path -LiteralPath $example)) {
    $example = Join-Path $Main 'scripts\local\release\release.env.example'
    Write-Warning 'the release worktree has no release.env.example; using the main checkout copy'
  }
  if (-not (Test-Path -LiteralPath $example)) { Stop-Release 'release.env.example not found' }

  $apiEntries = @(Read-DotEnv $apiEnv)
  $api = Get-EnvMap $apiEntries
  $rootEntries = @(); if (Test-Path -LiteralPath $rootEnv) { $rootEntries = @(Read-DotEnv $rootEnv) }
  $liveEntries = @(); if (Test-Path -LiteralPath $liveEnv) { $liveEntries = @(Read-DotEnv $liveEnv) }
  $root = Get-EnvMap $rootEntries
  $rootRaw = Get-EnvMap $rootEntries -Raw
  $live = Get-EnvMap $liveEntries
  $liveRaw = Get-EnvMap $liveEntries -Raw

  # The release must reuse the credentials the volumes were created with: refuse if the sources disagree.
  $conflicts = @()
  foreach ($k in $CredentialKeys) {
    if ($api.ContainsKey($k) -and $root.ContainsKey($k) -and ($api[$k] -cne $root[$k])) { $conflicts += ".env vs apps/api/.env: $k" }
  }
  if ($api.ContainsKey('LIVE_SERVER_SECRET_KEY') -and $live.ContainsKey('LIVE_SERVER_SECRET_KEY') -and ($api['LIVE_SERVER_SECRET_KEY'] -cne $live['LIVE_SERVER_SECRET_KEY'])) {
    $conflicts += 'apps/live/.env vs apps/api/.env: LIVE_SERVER_SECRET_KEY'
  }
  if ($conflicts.Count) { Stop-Release ("the env files disagree (values not shown): {0}. Fix the mismatch first." -f ($conflicts -join '; ')) }

  # init-env is a one-time, pre-cutover step: after Phase D apps/api/.env holds DEBUG values. Regenerating from it
  # would drop the tailnet origins and point WEB_URL at localhost (phone login and export links break silently).
  $debugHint = 'apps/api/.env holds DEBUG values (post-cutover); edit .local/release/release.env by hand or restore a .local/release/release.env.bak-* copy'
  $markers = @(@('SESSION_COOKIE_NAME', 'DJANGO_SETTINGS_MODULE') | Where-Object { $api.ContainsKey($_) })
  if ($markers.Count) { Stop-Release ("release.env NOT written: apps/api/.env defines {0} (debug markers). {1}." -f ($markers -join ', '), $debugHint) }

  # Origins: keep the existing :3300 entries (localhost, 127.0.0.1, MagicDNS host, tailnet IP).
  $corsRaw = ''
  if ($api.ContainsKey('CORS_ALLOWED_ORIGINS')) { $corsRaw = $api['CORS_ALLOWED_ORIGINS'] }
  $origins = New-Object System.Collections.Generic.List[string]
  foreach ($o in ($corsRaw -split ',')) {
    $t = $o.Trim().TrimEnd('/')
    if ($t -match ':3300$' -and -not $origins.Contains($t)) { $origins.Add($t) }
  }
  $addedLocal = @()
  foreach ($o in @('http://127.0.0.1:3300', 'http://localhost:3300')) {
    if (-not $origins.Contains($o)) { $origins.Insert(0, $o); $addedLocal += $o }
  }
  if ($addedLocal.Count) { Write-Warning ("added missing origin(s): {0}" -f ($addedLocal -join ', ')) }
  $nonHttp = @($origins | Where-Object { $_ -notlike 'http://*' })
  if ($nonHttp.Count) { Write-Warning ("{0} origin(s) are not http://; with any https origin the session/CSRF cookies become Secure and plain-http login breaks" -f $nonHttp.Count) }
  if ($origins.Count -ne 4) {
    Write-Warning ("expected 4 :3300 origins (localhost, 127.0.0.1, MagicDNS host, tailnet IP); found {0}. apps/api/.env may already hold debug values: check release.env by hand" -f $origins.Count)
  }

  $publicHost = ''; $ipOrigin = ''; $dnsOrigin = ''
  foreach ($o in $origins) {
    $u = $null
    try { $u = [Uri]$o } catch { $u = $null }
    if (-not $u) { continue }
    $h = $u.Host
    if (@('localhost', '127.0.0.1') -contains $h) { continue }
    if ($h -match '^\d{1,3}(\.\d{1,3}){3}$') { if (-not $ipOrigin) { $ipOrigin = $o }; continue }
    if ($h -match '^[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$' -and -not $publicHost) { $publicHost = $h; $dnsOrigin = $o }
  }
  if (-not $ipOrigin -and -not $dnsOrigin) {
    Stop-Release ("release.env NOT written: CORS_ALLOWED_ORIGINS in apps/api/.env has no non-local :3300 origin (MagicDNS host or tailnet IP), so the phone could not sign in. {0}." -f $debugHint)
  }

  $overrides = [ordered]@{
    POSTGRES_HOST        = 'plane-db'
    POSTGRES_PORT        = '5432'
    REDIS_HOST           = 'plane-redis'
    REDIS_PORT           = '6379'
    RABBITMQ_HOST        = 'plane-mq'
    RABBITMQ_PORT        = '5672'
    AWS_S3_ENDPOINT_URL  = 'http://plane-minio:9000'
    USE_MINIO            = '1'
    MINIO_ENDPOINT_SSL   = '0'
    DOCKERIZED           = '1'
    DEBUG                = '0'
    GUNICORN_WORKERS     = '2'
    CORS_ALLOWED_ORIGINS = ($origins.ToArray() -join ',')
    APP_BASE_PATH        = ''
    ADMIN_BASE_URL       = ''
    ADMIN_BASE_PATH      = '/god-mode'
    SPACE_BASE_URL       = ''
    SPACE_BASE_PATH      = '/spaces'
    LIVE_BASE_URL        = 'http://live:3000'
    LIVE_BASE_PATH       = '/live'
  }
  # WEB_URL / APP_BASE_URL are kept verbatim; they must already point at a :3300 origin (anything else means the
  # source is not the release config: they drive sign-in redirects and the MinIO custom domain).
  $badUrls = @(@('WEB_URL', 'APP_BASE_URL') | Where-Object { -not $api.ContainsKey($_) -or ($api[$_].TrimEnd('/') -notmatch '^http://[^/]+:3300$') })
  if ($badUrls.Count) {
    Stop-Release ("release.env NOT written: {0} in apps/api/.env missing or not an http://<host>:3300 origin (values not shown). {1}." -f ($badUrls -join ', '), $debugHint)
  }
  $defaults = [ordered]@{
    POSTGRES_DB            = 'plane'
    AWS_S3_BUCKET_NAME     = 'uploads'
    AWS_REGION             = ''
    FILE_SIZE_LIMIT        = '5242880'
    SIGNED_URL_EXPIRATION  = '3600'
    HARD_DELETE_AFTER_DAYS = '60'
    API_KEY_RATE_LIMIT     = ''
  }

  $seen = New-Object 'System.Collections.Generic.HashSet[string]'
  $body = New-Object System.Collections.Generic.List[string]
  $removed = 0; $overridden = 0; $kept = 0
  foreach ($e in $apiEntries) {
    if (-not $e.Key) { $body.Add($e.Raw); continue }
    if (($ForbiddenKeys -contains $e.Key) -or ($e.Key -like 'COMPOSE_*')) { $removed++; continue }
    [void]$seen.Add($e.Key)
    if ($overrides.Contains($e.Key)) { $body.Add(('{0}={1}' -f $e.Key, $overrides[$e.Key])); $overridden++; continue }
    $body.Add($e.Raw); $kept++
  }
  # Keys missing from apps/api/.env go to the TOP, so later ${...} references can use them.
  $top = New-Object System.Collections.Generic.List[string]
  foreach ($k in $CredentialKeys) {
    if (-not $seen.Contains($k) -and $rootRaw.ContainsKey($k)) { $top.Add(('{0}={1}' -f $k, $rootRaw[$k])); [void]$seen.Add($k) }
  }
  if (-not $seen.Contains('LIVE_SERVER_SECRET_KEY') -and $liveRaw.ContainsKey('LIVE_SERVER_SECRET_KEY')) {
    $top.Add(('LIVE_SERVER_SECRET_KEY={0}' -f $liveRaw['LIVE_SERVER_SECRET_KEY'])); [void]$seen.Add('LIVE_SERVER_SECRET_KEY')
  }
  foreach ($k in @($overrides.Keys)) { if (-not $seen.Contains($k)) { $top.Add(('{0}={1}' -f $k, $overrides[$k])); [void]$seen.Add($k) } }
  foreach ($k in @($defaults.Keys)) { if (-not $seen.Contains($k)) { $top.Add(('{0}={1}' -f $k, $defaults[$k])); [void]$seen.Add($k) } }
  # Derived URLs go to the END, after the values they reference (dotenv expands ${...} from earlier lines).
  $tail = New-Object System.Collections.Generic.List[string]
  if (-not $seen.Contains('REDIS_URL')) { $tail.Add('REDIS_URL=redis://${REDIS_HOST}:${REDIS_PORT}/') }
  if (-not $seen.Contains('DATABASE_URL')) { $tail.Add('DATABASE_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}') }

  $lines = New-Object System.Collections.Generic.List[string]
  $lines.Add(('# RELEASE stack env, generated {0} by scripts/local/release.ps1 init-env from apps/api/.env' -f (Get-Date -Format s)))
  $lines.Add('# (credentials missing there come from .env / apps/live/.env). Holds real secrets: never print, copy or commit it.')
  $lines.Add('# Edit by hand when release config changes. SECRET_KEY and the Postgres/RabbitMQ/MinIO credentials must never change.')
  if ($top.Count) { $lines.Add('# --- added by init-env (missing from apps/api/.env) ---'); $lines.AddRange($top) }
  $lines.Add('# --- apps/api/.env, release values overridden in place ---')
  $lines.AddRange($body)
  if ($tail.Count) { $lines.Add('# --- derived by init-env ---'); $lines.AddRange($tail) }
  $text = (($lines.ToArray() -join "`n").TrimEnd([char]10)) + "`n"

  $final = Get-EnvMap @(ConvertFrom-DotEnvText $text)
  $emptyReq = @($RequiredNonEmpty | Where-Object { -not $final.ContainsKey($_) -or -not $final[$_] })
  if ($emptyReq.Count) { Stop-Release ("release.env NOT written: required keys missing or empty: {0}" -f ($emptyReq -join ', ')) }
  $missing = @(Get-DotEnvKeys $example | Where-Object { -not $final.ContainsKey($_) })
  if ((Expand-Naive $final['REDIS_URL'] $final) -notmatch '^redis://plane-redis:6379/?$') {
    Stop-Release 'release.env NOT written: REDIS_URL does not resolve to redis://plane-redis:6379/ (value not shown); fix REDIS_URL in apps/api/.env (it is copied verbatim)'
  }
  if ($final.ContainsKey('DATABASE_URL') -and $final['DATABASE_URL'] -and ((Expand-Naive $final['DATABASE_URL'] $final) -notmatch '@plane-db(:5432)?/')) {
    Stop-Release 'release.env NOT written: DATABASE_URL does not point at plane-db:5432 (value not shown); fix DATABASE_URL in apps/api/.env (it is copied verbatim)'
  }

  if (Test-Path -LiteralPath $EnvFile) {
    $bak = $EnvFile + '.bak-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
    try { Copy-Item -LiteralPath $EnvFile -Destination $bak -ErrorAction Stop }
    catch { Stop-Release ("could not back up {0} ({1}); release.env NOT rewritten" -f (Get-RelPath $EnvFile), $_.Exception.Message) }
    Write-Info ("previous file kept as {0}" -f (Get-RelPath $bak))
  }
  Write-Utf8NoBom $EnvFile $text
  if ($publicHost) { Write-Utf8NoBom $PublicHostFile ($publicHost + "`n") }

  Write-Ok ("wrote {0}: {1} keys ({2} kept verbatim, {3} overridden, {4} added, {5} removed)" -f (Get-RelPath $EnvFile), $final.Count, $kept, $overridden, ($top.Count + $tail.Count), $removed)
  Write-Info ("CORS_ALLOWED_ORIGINS: {0} :3300 origin(s)" -f $origins.Count)
  if ($publicHost) { Write-Info ("public-host: written to {0} (MagicDNS host from the origins)" -f (Get-RelPath $PublicHostFile)) }
  else { Write-Warning 'no MagicDNS host among the :3300 origins: .local/release/public-host not written (phone-path check will be skipped)' }
  if ($missing.Count) {
    Write-Warning ("keys listed in release.env.example but missing from release.env: {0}. Add them by hand before deploy." -f ($missing -join ', '))
    $script:ExitCode = 1
  } else { Write-Info 'missing vs release.env.example: none' }
}

function Invoke-BuildVerb {
  Enter-Lock
  Assert-Docker
  Assert-Worktree
  if ($RefGiven) {
    $bsha = Resolve-Commit $Ref
    Assert-OnMain $bsha ("-Ref {0}" -f $Ref)
    Switch-Worktree $bsha
  }
  Assert-ReleaseEnvFile
  $t = (Get-WorktreeHead).Substring(0, 12)
  Set-ReleaseEnv $t
  Assert-ComposeConfig
  Invoke-ReleaseBuild $t
}

function Invoke-InfraVerb {
  Enter-Lock
  Assert-Docker
  Assert-Worktree
  Assert-ReleaseEnvFile
  Assert-Volumes
  Assert-NoLegacyContainers
  $t = Get-DeployedTag
  if (-not $t) { $t = (Get-WorktreeHead).Substring(0, 12) }
  Set-ReleaseEnv $t
  Assert-ComposeConfig
  Start-Infra
}

function Invoke-CheckpointVerb {
  Enter-Lock
  Assert-Docker
  $label = $Name
  if (-not $label) { $label = Get-DeployedTag }
  if (-not $label) { $label = 'initial' }
  $null = New-Checkpoint $label
}

function Invoke-Deploy {
  Enter-Lock
  Write-Step 'Preflight'
  Assert-Docker
  Assert-Worktree
  Assert-Volumes
  Assert-NoLegacyContainers
  Assert-Port3300

  $prev = Get-DeployedTag
  # main is the live development branch and can move at any time: the first deploy (the cutover) must name the
  # exact commit that was built and rehearsed, so it cannot pick up unrehearsed commits or migrations.
  if (-not $prev -and -not $RefGiven) {
    Stop-Release 'first deploy: pass the exact commit built and rehearsed before the cutover, e.g. release.ps1 deploy -Ref <sha> -NoMigrate'
  }
  $sha = Resolve-Commit $Ref
  $tag = $sha.Substring(0, 12)
  Assert-OnMain $sha ("{0}" -f $Ref)
  $mainSha = Invoke-GitOut $Main @('rev-parse', '--verify', '--quiet', 'main^{commit}') -AllowFail
  if ($mainSha -and $mainSha -ne $sha) { Write-Warning ("deploying {0} ({1}), which is not the tip of main" -f $Ref, $tag) }
  if ($prev) {
    $prevSha = Get-ShaForTag $prev
    if ($prevSha) {
      & git -C $Main merge-base --is-ancestor $prevSha $sha 2>$null
      if ($LASTEXITCODE -eq 1) {
        if (-not $Force) {
          Stop-Release ("{0} ({1}) does not contain the deployed commit {2}. Fix forward on main, use 'rollback -Tag' to go back, or pass -Force with the owner's OK." -f $Ref, $tag, $prev)
        }
        Write-Warning ("-Force: {0} does not contain the deployed commit {1}" -f $tag, $prev)
      }
    }
  }
  $mainDirty = Invoke-GitOut $Main @('status', '--porcelain') -AllowFail
  if ($mainDirty) { Write-Info ("note: the main checkout has {0} uncommitted change(s); they are NOT part of this deploy" -f @($mainDirty -split "`n").Count) }

  Switch-Worktree $sha
  # Checked against the NEW commit's release.env.example, after the switch.
  Assert-ReleaseEnvFile
  Set-ReleaseEnv $tag
  Assert-ComposeConfig
  Write-Ok ("preflight OK: deploying {0} ({1}); deployed now: {2}" -f $tag, $Ref, $(if ($prev) { $prev } else { 'nothing (first deploy)' }))

  # 2. images
  $missing = @(Get-MissingImages $tag)
  if ($Rebuild -or $missing.Count) { Invoke-ReleaseBuild $tag } else { Write-Step ("Images plane-release/*:{0} exist; build skipped (-Rebuild forces it)" -f $tag) }

  # 3. infra + checkpoint. -PlanOnly never starts or re-creates containers: it needs the release DB already running
  # (`up` with the new commit's compose file could re-create infra under the running app).
  if ($PlanOnly) { $null = Get-ReleaseDb } else { Start-Infra }
  $ckLabel = if ($prev) { $prev } else { 'initial' }
  $ck = New-Checkpoint $ckLabel
  $ckRel = Get-RelPath $ck

  # 4. applied migrations the new code does not know (renamed/deleted files) => abort
  Write-Step 'Checking for applied migrations missing from the new code'
  $unknown = @(Get-UnknownApplied)
  if ($unknown.Count) {
    foreach ($u in $unknown) { Write-Host "    applied but not on disk: $u" -ForegroundColor Red }
    if (-not $AllowUnknownApplied) {
      Stop-Release ("release has {0} applied migration(s) that {1} does not contain (renamed or deleted). Reconcile them first (see the plan's Phase B); -AllowUnknownApplied overrides with the owner's OK." -f $unknown.Count, $tag) 2
    }
    Write-Warning '-AllowUnknownApplied: continuing despite unknown applied migrations'
  } else { Write-Info 'none' }

  # 5. plan
  Write-Step 'Migration plan (python manage.py migrate --plan)'
  $plan = Get-MigrationPlan
  foreach ($l in $plan.Lines) { Write-Host "    $l" }
  # A plan that starts from scratch means the DB the release services reach is empty or not the real one (a
  # changed PGDATA/mount, a wrong DATABASE_URL): migrating would build a fresh schema next to orphaned real data.
  $fresh = @($plan.Migrations | Where-Object { @('contenttypes.0001_initial', 'db.0001_initial') -contains $_ })
  if ($fresh.Count) {
    if (-not $Force) {
      Stop-Release ("the migration plan includes {0}: the release DB looks empty or wrong; not migrating. Nothing was migrated or restarted. Tell the owner (-Force overrides only with the owner's OK)." -f ($fresh -join ', '))
    }
    Write-Warning ("-Force: migrating although the plan includes {0}" -f ($fresh -join ', '))
  }
  if ($PlanOnly) {
    Write-Ok ("-PlanOnly: stopped after the plan. Nothing was migrated and no container was started, stopped or re-created. The worktree was moved to {0} (release.ps1 status shows it; release.ps1 up moves it back to the deployed tag); checkpoint {1}." -f $tag, $ckRel)
    return
  }
  if ($NoMigrate -and -not $plan.Empty) {
    Stop-Release ("-NoMigrate: the plan above is not empty; nothing was migrated and the app containers were not touched (checkpoint {0}). The worktree is at {1}; tag.env still says {2}." -f $ckRel, $tag, $(if ($prev) { $prev } else { 'nothing' }))
  }

  # 6. migrate with the app services stopped (the proxy keeps serving the SPA; the API answers 502 meanwhile)
  $migrated = ''
  if (-not $plan.Empty) {
    Write-Step ("Migrating: stopping {0}" -f ($StopForMigrate -join ', '))
    Invoke-RC (@('stop') + $StopForMigrate)
    Write-Step 'Running the migrator (production settings)'
    $code = Invoke-RCCode @('run', '--rm', '--no-deps', '-T', 'migrator')
    if ($code -ne 0) {
      Write-Host 'Migration FAILED; restarting the previous app containers' -ForegroundColor Red
      $null = Invoke-RCCode (@('start') + $StopForMigrate)
      Add-DeployRow $tag $sha $prev $ckRel (@($plan.Migrations) -join ',') 'failed-migrate'
      Write-Host ("Checkpoint taken before migrating: {0}" -f $ckRel) -ForegroundColor Yellow
      Write-RecoveryHint $prev $ckRel
      Stop-Release ("migrator failed (exit {0}); the database may be partially migrated" -f $code)
    }
    $migrated = (@($plan.Migrations) -join ',')
    if (-not $migrated) { $migrated = 'yes' }
  }

  # 7. switch the tag and bring everything up
  Write-TagFile $tag
  Write-Step ("Starting release {0}" -f $tag)
  $upCode = Invoke-RCCode @('up', '-d', '--no-build', '--wait', '--wait-timeout', '300', '--remove-orphans')
  if ($upCode -ne 0) { Write-Warning ("docker compose up --wait exited {0}; checking health anyway" -f $upCode) }

  # 8. health
  $healthy = Test-ReleaseHealth $tag 180
  if ($healthy) {
    Test-PublicHost
    Add-DeployRow $tag $sha $prev $ckRel $migrated 'ok'
    Write-Host ''
    Write-Host ("Deployed {0} ({1})" -f $tag, $sha) -ForegroundColor Green
    Write-Host ("  previous   : {0}" -f $(if ($prev) { $prev } else { '-' }))
    Write-Host ("  checkpoint : {0}" -f $ckRel)
    Write-Host ("  migrations : {0}" -f $(if ($migrated) { $migrated } else { 'none' }))
    Write-Host '  Ask the owner to check the phone link (http://<PLANE_PUBLIC_HOST>:3300).'
    return
  }

  # 9. unhealthy
  if (-not $migrated -and $prev -and $prev -ne $tag) {
    Write-Host ("Release {0} is unhealthy and no migration ran: reverting to {1}" -f $tag, $prev) -ForegroundColor Yellow
    Write-TagFile $prev
    # Re-create the old tag with ITS compose file and env example, not the failed commit's.
    try { $null = Switch-WorktreeToTag $prev } catch { Write-Warning ("could not move the worktree back to {0}: {1}; reverting with the current compose file" -f $prev, $_.Exception.Message) }
    Set-ReleaseEnv $prev
    $null = Invoke-RCCode @('up', '-d', '--no-build', '--wait', '--wait-timeout', '300')
    $back = Test-ReleaseHealth $prev 180
    Add-DeployRow $tag $sha $prev $ckRel '-' $(if ($back) { 'reverted' } else { 'revert-unhealthy' })
    if (-not $back) { Write-RecoveryHint $prev $ckRel }
    Stop-Release ("deploy of {0} failed its health checks; {1}" -f $tag, $(if ($back) { "reverted to $prev (healthy)" } else { "revert to $prev is ALSO unhealthy - tell the owner" }))
  }
  Add-DeployRow $tag $sha $prev $ckRel $migrated 'failed-health'
  Write-RecoveryHint $prev $ckRel
  Stop-Release ("deploy of {0} failed its health checks; it is still running (tag.env = {0}). Inspect: release.ps1 logs api --tail 200" -f $tag)
}

function Invoke-Up {
  Enter-Lock
  Assert-Docker
  Assert-Worktree
  Assert-Volumes
  $t = Get-DeployedTag
  if (-not $t) { Stop-Release 'nothing is deployed yet (.local/release/tag.env missing); use deploy' }
  $missing = @(Get-MissingImages $t)
  if ($missing.Count) { Stop-Release ("images for the deployed tag are missing: {0}" -f ($missing -join ', ')) }
  # A failed or -PlanOnly deploy can leave the worktree on a newer commit: re-create the tag with its own files.
  if (-not $Force) { Assert-NoLegacyContainers }
  if ((Get-WorktreeHead).Substring(0, 12) -ne $t) { $null = Switch-WorktreeToTag $t }
  Assert-ReleaseEnvFile
  Set-ReleaseEnv $t
  Assert-ComposeConfig
  # Strays are removed only after every check passed (-Force, owner's OK).
  if ($Force) { Assert-NoLegacyContainers -Replace }
  Assert-Port3300
  Write-Step ("Re-creating release {0}" -f $t)
  $code = Invoke-RCCode @('up', '-d', '--no-build', '--wait', '--wait-timeout', '300')
  if ($code -ne 0) { Write-Warning ("docker compose up --wait exited {0}; checking health anyway" -f $code) }
  $ok = Test-ReleaseHealth $t 180
  Add-DeployRow $t (Get-ShaForTag $t) $t '-' '-' $(if ($ok) { 'up-ok' } else { 'up-failed' })
  if (-not $ok) { Stop-Release ("release {0} is unhealthy after up; inspect: release.ps1 logs api --tail 200" -f $t) }
  Test-PublicHost
}

function Test-UnderDir([string]$Path, [string]$Dir) {
  $d = [System.IO.Path]::GetFullPath($Dir).TrimEnd('\') + '\'
  return [System.IO.Path]::GetFullPath($Path).StartsWith($d, [System.StringComparison]::OrdinalIgnoreCase)
}

# Read-Host reads piped stdin under Windows PowerShell 5.1, so a confirmation is only valid from a real console.
function Assert-InteractiveConsole([string]$What) {
  $redirected = $true
  try { $redirected = [Console]::IsInputRedirected } catch { $redirected = $true }
  if ($redirected) { Stop-Release ("{0} must be confirmed by the owner in an interactive console (stdin is redirected); nothing changed" -f $What) }
}

function Invoke-Rollback {
  Enter-Lock
  Assert-Docker
  Assert-Worktree
  Assert-Volumes
  if (-not $Force) { Assert-NoLegacyContainers }
  $current = Get-DeployedTag
  if (-not $current) { Stop-Release 'nothing is deployed yet (.local/release/tag.env missing)' }
  $target = $Tag
  if ($target) {
    if ($target -notmatch '^[0-9a-f]{12}$') { Stop-Release "-Tag must be a 12-character image tag (sha12), got '$target'" }
  } else {
    $cands = @(Get-DeployRows | Where-Object { $_.Result -eq 'ok' -and $_.Tag -ne $current })
    if (-not $cands.Count) { Stop-Release 'no earlier ok deploy in deployments.tsv; pass -Tag <sha12>' }
    $target = $cands[-1].Tag
  }
  $missing = @(Get-MissingImages $target)
  if ($missing.Count) { Stop-Release ("images for {0} are missing: {1}" -f $target, ($missing -join ', ')) }

  $dump = ''
  if ($RestoreDump) {
    $resolved = Resolve-Path -LiteralPath $RestoreDump -ErrorAction SilentlyContinue
    if (-not $resolved) { Stop-Release "dump not found: $RestoreDump" }
    $dump = $resolved.Path
    # Only release checkpoints and backups: a dump from anywhere else (e.g. of the debug DB) would load foreign
    # data into release.
    $isCheckpoint = ((Split-Path -Parent $dump).TrimEnd('\') -ieq $CheckpointDir.TrimEnd('\')) -and ((Split-Path -Leaf $dump) -like 'release-*.dump')
    $isBackup = Test-UnderDir $dump (Join-Path $Main '.local\backups')
    if (-not $isCheckpoint -and -not $isBackup) {
      if (-not $Force) { Stop-Release ("-RestoreDump accepts only .local\checkpoints\release-*.dump or files under .local\backups\ ({0} is neither); -Force overrides with the owner's OK" -f $dump) }
      Write-Warning ("-Force: restoring a dump from outside .local\checkpoints and .local\backups: {0}" -f $dump)
    }
    $head = New-Object byte[] 5
    $fs = [System.IO.File]::OpenRead($dump)
    try { $null = $fs.Read($head, 0, 5) } finally { $fs.Close() }
    if ([System.Text.Encoding]::ASCII.GetString($head) -ne 'PGDMP') { Stop-Release "$dump is not a pg_dump custom-format file" }
    # Confirm before anything changes (the worktree included).
    Assert-InteractiveConsole 'rollback -RestoreDump'
    Write-Host ("This REPLACES the release database with {0}. Every write since that dump is lost." -f (Get-RelPath $dump)) -ForegroundColor Yellow
    $answer = ''
    try { $answer = Read-Host 'Type RESTORE to continue' } catch { $answer = '' }
    if ($answer -cne 'RESTORE') { Stop-Release 'restore not confirmed; nothing changed' }
  }

  Write-Step ("Rollback: {0} -> {1}{2}" -f $current, $target, $(if ($dump) { " and restore the database from $(Get-RelPath $dump)" } else { ' (code only; migrations stay applied)' }))
  # Run the old tag with ITS compose file, Dockerfiles and release.env.example (the worktree is detached and clean).
  $moved = Switch-WorktreeToTag $target
  Assert-ReleaseEnvFile
  Set-ReleaseEnv $target
  Assert-ComposeConfig
  # Strays are removed only after every check passed (-Force, owner's OK).
  if ($Force) { Assert-NoLegacyContainers -Replace }
  Assert-Port3300

  $ckRel = ''
  if ($dump) {
    Set-ReleaseEnv $current
    Start-Infra
    $ckRel = Get-RelPath (New-Checkpoint 'pre-restore')
    Write-Step ("Stopping {0}" -f ($StopForMigrate -join ', '))
    Invoke-RC (@('stop') + $StopForMigrate)
    $db = Get-ReleaseDb
    Write-Step ("Restoring {0} into {1}" -f (Get-RelPath $dump), $db)
    & docker cp $dump ("{0}:/tmp/restore.dump" -f $db) | Out-Host
    if ($LASTEXITCODE -ne 0) {
      $null = Invoke-RCCode (@('start') + $StopForMigrate)
      Stop-Release 'docker cp of the dump into the DB container failed; database untouched, app containers restarted'
    }
    $sh = 'dropdb -U $POSTGRES_USER --force $POSTGRES_DB && createdb -U $POSTGRES_USER $POSTGRES_DB && pg_restore -U $POSTGRES_USER -d $POSTGRES_DB --no-owner --no-privileges --exit-on-error /tmp/restore.dump; rc=$?; rm -f /tmp/restore.dump; exit $rc'
    & docker exec $db sh -c $sh | Out-Host
    if ($LASTEXITCODE -ne 0) {
      Add-DeployRow $target (Get-ShaForTag $target) $current $ckRel '-' 'restore-failed'
      Stop-Release ("pg_restore FAILED; app containers left stopped. The database may be empty or partial. Pre-restore checkpoint: {0}. Tell the owner." -f $ckRel)
    }
    Write-Ok 'database restored'
  }

  Write-TagFile $target
  Set-ReleaseEnv $target
  $code = Invoke-RCCode @('up', '-d', '--no-build', '--wait', '--wait-timeout', '300')
  if ($code -ne 0) { Write-Warning ("docker compose up --wait exited {0}; checking health anyway" -f $code) }
  $ok = Test-ReleaseHealth $target 180
  Add-DeployRow $target (Get-ShaForTag $target) $current $ckRel '-' $(if ($ok) { 'rollback-ok' } else { 'rollback-failed' })
  if (-not $ok) { Stop-Release ("rolled back to {0} but it is unhealthy; inspect: release.ps1 logs api --tail 200" -f $target) }
  Test-PublicHost
  $wtNote = if ($moved) { 'the worktree was moved to that commit' } else { ("the worktree stays at {0} (commit of {1} unknown)" -f (Get-WorktreeHead).Substring(0, 12), $target) }
  Write-Ok ("release now runs {0} (was {1}); {2}. main does not move: the next deploy fixes forward from main." -f $target, $current, $wtNote)
}

function Invoke-Status {
  Write-Host 'Release status (read-only)' -ForegroundColor Green
  $mainSha = Invoke-GitOut $Main @('rev-parse', '--verify', '--quiet', 'main^{commit}') -AllowFail
  if ($mainSha) {
    $subject = Invoke-GitOut $Main @('log', '-1', '--format=%s', $mainSha) -AllowFail
    Write-Host ("  main           : {0}  {1}" -f $mainSha.Substring(0, 12), $subject)
  } else { Write-Host '  main           : (no local branch main)' }
  $mainDirty = Invoke-GitOut $Main @('status', '--porcelain') -AllowFail
  if ($mainDirty) { Write-Host ("  main checkout  : {0} uncommitted change(s), not deployable until committed to main" -f @($mainDirty -split "`n").Count) }

  $wtSha = ''
  if (Test-Path -LiteralPath (Join-Path $WT '.git')) {
    $wtSha = Invoke-GitOut $WT @('rev-parse', 'HEAD') -AllowFail
    $branch = Invoke-GitOut $WT @('symbolic-ref', '-q', '--short', 'HEAD') -AllowFail
    $wtDirty = Invoke-GitOut $WT @('status', '--porcelain') -AllowFail
    $mode = if ($branch) { "ON BRANCH $branch (must be detached)" } else { 'detached' }
    $clean = if ($wtDirty) { 'DIRTY (never edit it)' } else { 'clean' }
    $short = if ($wtSha) { $wtSha.Substring(0, 12) } else { '?' }
    Write-Host ("  worktree       : {0}  {1}, {2}, {3}" -f $WT, $short, $mode, $clean)
    if ($mainSha -and $wtSha) {
      if ($wtSha -eq $mainSha) { Write-Host '  worktree/main  : worktree is at main' }
      else {
        $lr = Invoke-GitOut $Main @('rev-list', '--left-right', '--count', ($wtSha + '...' + $mainSha)) -AllowFail
        if ($lr -match '^(\d+)\s+(\d+)$') { Write-Host ("  worktree/main  : main has {0} commit(s) the worktree lacks; worktree has {1} not on main" -f $Matches[2], $Matches[1]) }
      }
    }
  } else { Write-Host ("  worktree       : {0} (missing; run: release.ps1 init)" -f $WT) }

  $deployed = Get-DeployedTag
  if ($deployed) {
    $dSha = Get-ShaForTag $deployed
    Write-Host ("  deployed tag   : {0} (.local/release/tag.env)" -f $deployed)
    if ($wtSha -and $wtSha.Substring(0, 12) -ne $deployed) {
      Write-Host ("  worktree/tag   : worktree is at {0}, not at the deployed {1} (failed or -PlanOnly deploy); release.ps1 up moves it back" -f $wtSha.Substring(0, 12), $deployed) -ForegroundColor Yellow
    }
    $pending = $null
    if ($dSha -and $mainSha) { $pending = Invoke-GitOut $Main @('rev-list', '--count', ($dSha + '..' + $mainSha)) -AllowFail }
    if ($pending -notmatch '^\d+$') { Write-Host '  not deployed   : unknown (the deployed commit is not in this repository)' }
    else {
      Write-Host ("  not deployed   : {0} commit(s) on main after the deployed one" -f $pending)
      if ([int]$pending -gt 0) {
        $list = Invoke-GitOut $Main @('log', '--oneline', '-15', ($dSha + '..' + $mainSha)) -AllowFail
        foreach ($l in @($list -split "`n")) { if ($l) { Write-Host "                   $l" } }
      }
    }
  } else { Write-Host '  deployed tag   : none yet (.local/release/tag.env missing)' }

  $envState = if (Test-Path -LiteralPath $EnvFile) { 'present (values not shown)' } else { 'missing (run: release.ps1 init-env)' }
  Write-Host ("  release.env    : {0}" -f $envState)
  $phState = if (Test-Path -LiteralPath $PublicHostFile) { 'present' } else { 'missing (phone-path check skipped)' }
  Write-Host ("  public-host    : {0}" -f $phState)
  if (Test-Path -LiteralPath $LockFile) {
    $info = ''
    try { $info = ([System.IO.File]::ReadAllText($LockFile)).Trim() } catch { $info = '(unreadable)' }
    Write-Host ("  deploy lock    : HELD [{0}]" -f $info) -ForegroundColor Yellow
  } else { Write-Host '  deploy lock    : free' }

  if (Test-DockerUp) {
    $rows = @(& docker ps -a --filter 'label=com.docker.compose.project=plane' --format '{{.Names}}|{{.Image}}|{{.Status}}' 2>$null | Where-Object { $_ })
    $web = @(& docker ps -a --filter 'name=^plane-web-prod$' --format '{{.Names}}|{{.Image}}|{{.Status}}' 2>$null | Where-Object { $_ })
    Write-Host '  containers (compose project plane):'
    if (-not $rows.Count) { Write-Host '    (none)' }
    foreach ($r in ($rows + $web | Sort-Object)) {
      $p = $r.Split('|')
      $flag = ''
      if ($p[0] -notlike 'plane-release-*' -and $p[0] -notlike 'plane-migrator-run-*') { $flag = '  <- pre-split (legacy) container' }
      elseif ($deployed -and $p[1] -like 'plane-release/*' -and $p[1] -notlike ('*:' + $deployed)) { $flag = "  <- MISMATCH: tag.env says $deployed" }
      Write-Host ("    {0,-24} {1,-46} {2}{3}" -f $p[0], $p[1], $p[2], $flag)
    }
  } else { Write-Host '  docker         : not responding' }

  $last = @(Get-DeployRows | Select-Object -Last 5)
  Write-Host '  last deploys (.local/release/deployments.tsv):'
  if (-not $last.Count) { Write-Host '    (none)' }
  foreach ($r in $last) { Write-Host ("    {0}  {1}  prev {2}  {3}  migrations: {4}  ckpt: {5}" -f $r.Utc, $r.Tag, $r.Prev, $r.Result, $r.Migrations, $r.Checkpoint) }
}

function Invoke-Logs {
  Assert-Docker
  $t = Get-DeployedTag
  if (-not $t) { $t = 'undeployed' }
  Set-ReleaseEnv $t
  $script:ExitCode = Invoke-RCCode (@('logs') + $Rest)
}

function Invoke-Manage {
  if (-not $Rest.Count) { Stop-Release 'usage: release.ps1 manage <manage.py args>, e.g. manage showmigrations db' }
  # Allowlist, not a deny-list: Django's migrate runs --prune (deletes django_migrations rows) BEFORE it honours
  # --plan, and its argparse accepts abbreviations (--pru == --prune). Every token after the command must be a
  # known read-only flag or a positional (app label / migration name).
  $tail = @($Rest | Select-Object -Skip 1)
  $readOnly = $false
  if ($Rest[0] -ceq 'showmigrations') {
    $readOnly = (@($tail | Where-Object { $_ -cnotmatch '^(--list|-l|--plan|-p|--no-color|[A-Za-z0-9_]+)$' }).Count -eq 0)
  } elseif ($Rest[0] -ceq 'migrate') {
    $readOnly = ($tail -ccontains '--plan') -and (@($tail | Where-Object { $_ -cnotmatch '^(--plan|--no-color|[A-Za-z0-9_]+)$' }).Count -eq 0)
  }
  if (-not $readOnly -and -not $IKnowThisIsRelease) {
    Stop-Release ("'manage {0}' can change the release database. Without -IKnowThisIsRelease (owner's OK) only these run: showmigrations [--list|-l|--plan|-p|--no-color] [app ...], migrate --plan [--no-color] [app [migration]]." -f ($Rest -join ' '))
  }
  Assert-Docker
  $t = Get-DeployedTag
  if (-not $t) { Stop-Release 'nothing is deployed yet (.local/release/tag.env missing)' }
  if (-not $readOnly) {
    Enter-Lock
    Assert-Worktree
    Write-Warning ("running 'manage {0}' against the RELEASE database (production settings)" -f ($Rest -join ' '))
  }
  Set-ReleaseEnv $t
  $missing = @(Get-MissingImages $t)
  if ($missing.Count) { Stop-Release ("images for the deployed tag are missing: {0}" -f ($missing -join ', ')) }
  $script:ExitCode = Invoke-RCCode (@('run', '--rm', '--no-deps', '-T', 'migrator', 'python', 'manage.py') + $Rest)
}

function Invoke-ComposePassthrough {
  if (-not $Rest.Count) { Stop-Release 'usage: release.ps1 compose <subcommand> [args], e.g. compose ps' }
  if ($Rest[0].StartsWith('-')) { Stop-Release 'global compose options (-p, -f, --env-file, --profile, ...) are set by release.ps1; pass only a subcommand and its arguments' }
  $sub = $Rest[0].ToLowerInvariant()
  $tail = @($Rest | Select-Object -Skip 1)
  # compose accepts its global flags after the subcommand too; those select files/projects and stay ours.
  $globalFlags = @($tail | Where-Object { $_ -ceq '-p' -or $_ -match '^--(project-name|project-directory|env-file|file|profile)(=|$)' -or ($_ -ceq '-f' -and @('logs', 'rm') -notcontains $sub) })
  if ($globalFlags.Count) {
    Stop-Release ("refused: {0}. Files, project, env file and profiles are fixed by release.ps1 (use --follow / --force instead of -f outside logs and rm)" -f ($globalFlags -join ' '))
  }
  $volumeFlag = @($tail | Where-Object { $_ -like '--volumes*' -or $_ -cmatch '^-[A-Za-z]*v[A-Za-z]*$' })
  if ((@('down', 'rm') -contains $sub) -and $volumeFlag.Count) { Stop-Release 'down -v / rm -v / --volumes is always refused: the release volumes hold the real data' }
  if ($sub -ne 'config' -and @($tail | Where-Object { $_ -like '--volumes*' }).Count) { Stop-Release '--volumes is always refused outside config --volumes' }
  # Never a second instance of a data service: `run`/`create`/`--scale` of plane-db starts a second postmaster on
  # plane_pgdata (corruption); `run plane-minio <anything>` always runs its /bin/sh -c entrypoint, i.e. a second
  # MinIO server on plane_uploads. Refused even with -IKnowThisIsRelease.
  $infra = @('plane-db', 'plane-minio', 'plane-redis', 'plane-mq')
  $appSvcs = @('api', 'worker', 'beat-worker', 'live', 'space', 'proxy')
  $execHint = 'use docker exec plane-release-<svc> ... against the running container instead'
  if (@($tail | Where-Object { $_ -like '--scale*' }).Count) { Stop-Release ("--scale is always refused on the release project; {0}" -f $execHint) }
  if ($sub -eq 'create') { Stop-Release ("compose create is always refused on the release project (it would re-create containers without starting them); use release.ps1 up / deploy") }
  if ($sub -eq 'run') {
    $named = @($tail | Where-Object { ($infra + $appSvcs) -ccontains $_ })
    if ($named.Count -or ($tail -cnotcontains 'migrator')) {
      Stop-Release ("compose run is allowed only for the migrator service on the release project (refused: {0}); {1}" -f ($Rest -join ' '), $execHint)
    }
  }
  # Free (no -IKnowThisIsRelease): never shows process command lines in full (ps --no-trunc / --format, top).
  $psDetail = @($tail | Where-Object { $_ -like '--no-trunc*' -or $_ -like '--format*' })
  $readOnly = (@('logs', 'images') -contains $sub) -or (($sub -eq 'ps') -and -not $psDetail.Count) -or
    (($sub -eq 'config') -and $tail.Count -ge 1 -and (@($tail | Where-Object { @('--services', '--images', '--volumes') -notcontains $_ }).Count -eq 0))
  if (-not $readOnly -and -not $IKnowThisIsRelease) {
    Stop-Release ("'compose {0}' is not on the read-only list (ps without --no-trunc/--format, logs, images, config --services|--images|--volumes; plain config prints secrets, top and full ps show command lines). It needs -IKnowThisIsRelease and the owner's OK." -f ($Rest -join ' '))
  }
  Assert-Docker
  $t = Get-DeployedTag
  if (-not $readOnly) {
    Enter-Lock
    Assert-Worktree
    if (-not $t) { $t = (Get-WorktreeHead).Substring(0, 12); Write-Warning "nothing deployed yet; using the worktree HEAD tag $t" }
    Set-ReleaseEnv $t
    Assert-ComposeConfig
    Write-Warning ("running 'docker compose {0}' on the RELEASE project" -f ($Rest -join ' '))
  } else {
    if (-not $t) { $t = 'undeployed' }
    Set-ReleaseEnv $t
  }
  $script:ExitCode = Invoke-RCCode $Rest
}

function Invoke-PruneImages {
  if ($Keep -lt 1) { Stop-Release '-Keep must be at least 1' }
  Enter-Lock
  Assert-Docker
  $current = Get-DeployedTag
  $okTags = New-Object System.Collections.Generic.List[string]
  $rows = @(Get-DeployRows)
  [array]::Reverse($rows)
  foreach ($r in $rows) {
    if ($okTags.Count -ge $Keep) { break }
    if ($r.Result -eq 'ok' -and -not $okTags.Contains($r.Tag)) { $okTags.Add($r.Tag) }
  }
  $keepTags = @(@($okTags.ToArray()) + @($current) | Where-Object { $_ })
  $inUse = @(& docker ps -a --format '{{.Image}}' 2>$null | Where-Object { $_ -like 'plane-release/*' } | ForEach-Object { ($_ -split ':')[-1] })
  $refs = @(& docker image ls --filter 'reference=plane-release/*' --format '{{.Repository}}:{{.Tag}}' 2>$null |
      Where-Object { $_ -like 'plane-release/*' -and $_ -notlike '*:<none>' })
  $cands = @($refs | Where-Object { $t = ($_ -split ':')[-1]; ($keepTags -notcontains $t) -and ($inUse -notcontains $t) } | Sort-Object -Unique)
  Write-Step ("Keeping tags: {0}" -f $(if ($keepTags.Count) { ($keepTags -join ', ') } else { '(none)' }))
  if (-not $cands.Count) { Write-Info 'nothing to remove'; return }
  foreach ($c in $cands) { Write-Info $c }
  Assert-InteractiveConsole 'prune-images'
  $answer = ''
  try { $answer = Read-Host ("Remove these {0} image tag(s)? [y/N]" -f $cands.Count) } catch { $answer = '' }
  if ($answer -notmatch '^(y|yes)$') { Write-Info 'nothing removed'; return }
  foreach ($c in $cands) {
    & docker image rm $c | Out-Host
    if ($LASTEXITCODE -ne 0) { Write-Warning "could not remove $c" }
  }
}

function Show-Usage {
  Write-Host 'usage: powershell -ExecutionPolicy Bypass -File scripts\local\release.ps1 <verb> [options]'
  Write-Host '  verbs: init | init-env | build | infra | deploy | up | rollback | status | logs | checkpoint | manage | compose | prune-images'
  Write-Host '  options (exact names): -Ref <rev> -Tag <sha12> -RestoreDump <file> -Name <label> -Keep <n> -Worktree <path>'
  Write-Host '                         -Rebuild -NoCache -PlanOnly -NoMigrate -Force -AllowUnknownApplied -IKnowThisIsRelease'
  Write-Host '  details: the header of scripts\local\release.ps1, and AGENTS.md "Local environment (Jira-parity fork)"'
}

# ---------------------------------------------------------------- dispatch
try {
  if ($ArgError) { Stop-Release $ArgError }
  Assert-MainCheckout
  switch ($Command.ToLowerInvariant()) {
    'help' { Show-Usage }
    'init' { Invoke-Init }
    'init-env' { Invoke-InitEnv }
    'build' { Invoke-BuildVerb }
    'infra' { Invoke-InfraVerb }
    'deploy' { Invoke-Deploy }
    'up' { Invoke-Up }
    'rollback' { Invoke-Rollback }
    'status' { Invoke-Status }
    'logs' { Invoke-Logs }
    'checkpoint' { Invoke-CheckpointVerb }
    'manage' { Invoke-Manage }
    'compose' { Invoke-ComposePassthrough }
    'prune-images' { Invoke-PruneImages }
    default { Show-Usage; if ($Command) { $script:ExitCode = 1 } }
  }
} catch {
  Write-Host ("ERROR: " + $_.Exception.Message) -ForegroundColor Red
  if (-not $script:ExitCode) { $script:ExitCode = 1 }
} finally {
  Exit-Lock
}
exit $script:ExitCode
