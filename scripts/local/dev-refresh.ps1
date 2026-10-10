<#
.SYNOPSIS
  Re-seed the DEBUG stack (compose project "plane-dev") from RELEASE: database dump + uploads copy.

.DESCRIPTION
  Reads release, overwrites debug only. See AGENTS.md "Local environment".
    1. Starts the debug infra (plane-db, plane-redis, plane-mq), waits for Postgres, and stops the debug api,
       worker, beat-worker and plane-minio.
    2. Dumps the release app database (pg_dump -Fc through docker exec; release is only read) to
       .local\checkpoints\release-<yyyyMMdd-HHmmss>.dump - unless -FromDump. Leftover test_plane* databases on
       the release server are not dumped.
    3. Drops, re-creates and pg_restores the debug database (the archive is validated first).
    4. Copies the whole release uploads volume (plane_uploads, incl. .minio.sys) over plane-dev_uploads -
       unless -SkipUploads.
    5. Flushes debug Redis.
    6. Deactivates every webhook in the debug database (debug must not call out).
    7. Starts debug MinIO; runs the debug migrator to the working-tree head (unless -SkipMigrate); starts api,
       worker and beat-worker and waits for http://127.0.0.1:8310/api/instances/ (unless -NoStart).
    8. Prints the dump path and the latest "db" migration on release and on debug.

  Guards, all checked before anything destructive (any failure aborts):
    - source: exactly one RUNNING container labelled com.docker.compose.project=plane and
      com.docker.compose.service=plane-db (plane-release-db; plane-plane-db-1 before the split) that mounts
      volume plane_pgdata at /var/lib/postgresql/data. Only read.
    - target: exactly one container labelled project=plane-dev and service=plane-db, named plane-dev-*, that
      mounts volume plane-dev_pgdata; the debug Redis likewise (project=plane-dev, named plane-dev-*).
    - every existing plane-dev_* volume, and in particular plane-dev_uploads, carries label
      com.docker.compose.project=plane-dev; volume plane_uploads exists (it is never created here).
    - source and target are different containers.

  Users, passwords and sessions carry over from release; sign in again on http://127.0.0.1:3310.

.PARAMETER FromDump
  Restore this pg_dump -Fc archive instead of dumping release (the release database is then not required).
.PARAMETER SkipUploads
  Keep the current debug uploads (no copy from plane_uploads).
.PARAMETER SkipMigrate
  Do not run the debug migrator after the restore.
.PARAMETER NoStart
  Do not start the debug api, worker and beat-worker afterwards (infra and MinIO stay up).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\local\dev-refresh.ps1
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\local\dev-refresh.ps1 -FromDump .local\checkpoints\release-20261009-120000.dump -SkipUploads
#>
[CmdletBinding()]
param(
  [string]$FromDump,
  [switch]$SkipUploads,
  [switch]$SkipMigrate,
  [switch]$NoStart
)

# 'Continue' (not 'Stop'): under Windows PowerShell 5.1, stderr from native tools (docker) can surface as
# terminating NativeCommandErrors. Failures are checked explicitly via $LASTEXITCODE.
$ErrorActionPreference = 'Continue'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Compose = Join-Path $Root 'docker-compose-local.yml'
$CheckpointDir = Join-Path $Root '.local\checkpoints'
$DevProject = 'plane-dev'
$ReleaseProject = 'plane'
$DevVolumes = @('plane-dev_pgdata', 'plane-dev_uploads', 'plane-dev_redisdata', 'plane-dev_rabbitmq_data')
$ReleaseUploads = 'plane_uploads'
$DevApiUrl = 'http://127.0.0.1:8310/api/instances/'
$ts = Get-Date -Format 'yyyyMMdd-HHmmss'
# Unique per run: two refreshes from different sessions must not truncate or delete each other's temp dump.
$tmp = "/tmp/dev-refresh-$ts-$PID.dump"
# psql through stdin (no double quotes inside sh -c strings: Windows PowerShell 5.1 mangles them).
$PsqlQuiet = 'psql -X -q -U $POSTGRES_USER -d $POSTGRES_DB -v ON_ERROR_STOP=1'
$PsqlTuples = 'psql -X -At -U $POSTGRES_USER -d $POSTGRES_DB -v ON_ERROR_STOP=1'
$LatestDbMigrationSql = "select name from django_migrations where app='db' order by id desc limit 1;"

function Write-Step([string]$msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Fail([string]$msg) { Write-Host "ABORT: $msg" -ForegroundColor Red; exit 1 }

# docker compose -p plane-dev -f docker-compose-local.yml <args>; aborts on a non-zero exit.
function Invoke-DC {
  & docker compose -p $DevProject -f $Compose @args
  if ($LASTEXITCODE -ne 0) { Fail ("docker compose -p $DevProject " + ($args -join ' ') + " failed (exit $LASTEXITCODE)") }
}

# Regular (non one-off) compose containers of <project>/<service>, as objects with Id, Name, State.
function Get-ComposeContainers([string]$Project, [string]$Service, [switch]$RunningOnly) {
  $a = @('ps', '--no-trunc', '--format', '{{.ID}}|{{.Names}}|{{.State}}',
    '--filter', "label=com.docker.compose.project=$Project",
    '--filter', "label=com.docker.compose.service=$Service",
    '--filter', 'label=com.docker.compose.oneoff=False')
  if (-not $RunningOnly) { $a += '-a' }
  $out = & docker @a
  if ($LASTEXITCODE -ne 0) { Fail "docker ps failed while looking up $Project/$Service" }
  foreach ($line in @($out)) {
    if (-not $line) { continue }
    $p = ([string]$line).Split('|')
    [pscustomobject]@{ Id = $p[0]; Name = $p[1]; State = $p[2] }
  }
}

# $null if the volume does not exist, else its com.docker.compose.project label ('' when unlabelled).
function Get-VolumeProject([string]$Name) {
  $j = & docker volume inspect --format '{{json .Labels}}' $Name 2>$null
  if ($LASTEXITCODE -ne 0) { return $null }
  $labels = ($j | Out-String) | ConvertFrom-Json
  if ($labels -and $labels.'com.docker.compose.project') { return [string]$labels.'com.docker.compose.project' }
  return ''
}

function Wait-PgReady([string]$Container, [int]$TimeoutSec) {
  # TCP on 127.0.0.1: the image's init-time temporary server listens on the unix socket only.
  $deadline = (Get-Date).AddSeconds($TimeoutSec)
  while ((Get-Date) -lt $deadline) {
    & docker exec $Container sh -c 'pg_isready -q -h 127.0.0.1 -U $POSTGRES_USER -d $POSTGRES_DB' 2>$null
    if ($LASTEXITCODE -eq 0) { return $true }
    Start-Sleep -Seconds 2
  }
  return $false
}

function Wait-Http([string]$Url, [int]$TimeoutSec) {
  $deadline = (Get-Date).AddSeconds($TimeoutSec)
  while ((Get-Date) -lt $deadline) {
    try {
      $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5 -MaximumRedirection 0 -ErrorAction Stop
      return $resp.StatusCode
    } catch {
      if ($_.Exception.Response) { return [int]$_.Exception.Response.StatusCode }
    }
    Start-Sleep -Seconds 2
  }
  return 0
}

function Get-LatestDbMigration([string]$Container) {
  $r = ($LatestDbMigrationSql | & docker exec -i $Container sh -c $PsqlTuples 2>$null)
  if ($LASTEXITCODE -ne 0 -or -not "$r".Trim()) { return '(unknown)' }
  return "$r".Trim()
}

# ---------------------------------------------------------------- preflight (read-only)
Write-Step 'Preflight'
& docker info --format '{{.ServerVersion}}' *> $null
if ($LASTEXITCODE -ne 0) { Fail 'Docker is not responding (start Docker Desktop, or run dev-up.ps1 -RecoverDocker).' }
if (-not (Test-Path $Compose)) { Fail "missing $Compose" }

if ($FromDump) {
  if (-not (Test-Path -PathType Leaf $FromDump)) { Fail "-FromDump file not found: $FromDump" }
  $dumpPath = (Resolve-Path $FromDump).Path
  if ((Get-Item $dumpPath).Length -le 0) { Fail "-FromDump file is empty: $dumpPath" }
}

$src = $null
$srcList = @(Get-ComposeContainers $ReleaseProject 'plane-db' -RunningOnly)
if ($srcList.Count -eq 1) { $src = $srcList[0] }
elseif (-not $FromDump) {
  Fail ("expected exactly one running release database (labels com.docker.compose.project=$ReleaseProject, " +
    "com.docker.compose.service=plane-db), found $($srcList.Count). Use -FromDump <file> to seed without release.")
} else {
  Write-Warning "release database not found uniquely ($($srcList.Count) matches) - restoring -FromDump only"
}
if ($src) {
  if ($src.Name.StartsWith('plane-dev')) { Fail "release database candidate $($src.Name) looks like a debug container" }
  # The labels are not proof: after a stray `docker compose -p plane -f docker-compose-local.yml up` they belong to a
  # container on the DEBUG volume. The release DB is the one whose data directory is volume plane_pgdata.
  $srcMj = & docker inspect --format '{{json .Mounts}}' $src.Id 2>$null
  $srcCode = $LASTEXITCODE
  $srcMounts = $null
  # Assign before wrapping: Windows PowerShell 5.1's ConvertFrom-Json emits a JSON array as ONE pipeline object.
  if ($srcCode -eq 0) { try { $srcMounts = ($srcMj | Out-String) | ConvertFrom-Json } catch { $srcMounts = $null } }
  $srcPg = @(@($srcMounts) | Where-Object { $_ -and $_.Destination -eq '/var/lib/postgresql/data' })
  if ($srcCode -ne 0 -or $srcPg.Count -ne 1 -or $srcPg[0].Type -ne 'volume' -or $srcPg[0].Name -ne 'plane_pgdata') {
    if (-not $FromDump) { Fail "release database candidate $($src.Name) does not mount volume plane_pgdata at /var/lib/postgresql/data - refusing to treat it as release" }
    Write-Warning "$($src.Name) does not mount plane_pgdata; ignoring it (restoring -FromDump only)"
    $src = $null
  }
}
if ($src) { Write-Host "    source (release, read-only): $($src.Name)" }

foreach ($v in $DevVolumes) {
  $proj = Get-VolumeProject $v
  if ($null -ne $proj -and $proj -ne $DevProject) {
    Fail "volume $v exists but is labelled com.docker.compose.project='$proj', not '$DevProject' - refusing to touch it"
  }
}
if (-not $SkipUploads) {
  $relUploadsProject = Get-VolumeProject $ReleaseUploads
  # Must exist: "docker run -v plane_uploads:..." would otherwise CREATE an empty volume under the release name.
  if ($null -eq $relUploadsProject) { Fail "release uploads volume $ReleaseUploads does not exist (use -SkipUploads to restore the database only)" }
  if ($relUploadsProject -ne $ReleaseProject) { Write-Warning "volume $ReleaseUploads is labelled project '$relUploadsProject' (expected '$ReleaseProject'); it is only read" }
}

# ---------------------------------------------------------------- 1. debug infra up, debug app down
Write-Step "Starting debug infra (project $DevProject): plane-db, plane-redis, plane-mq"
Invoke-DC up -d plane-db plane-redis plane-mq
# Creates plane-dev_uploads with compose labels (and the MinIO container) without starting MinIO.
Invoke-DC create plane-minio
$toStop = @('api', 'worker', 'beat-worker', 'plane-minio' | Where-Object { @(Get-ComposeContainers $DevProject $_ -RunningOnly).Count -gt 0 })
if ($toStop.Count -gt 0) {
  Write-Step ('Stopping debug ' + ($toStop -join ', '))
  Invoke-DC stop @toStop
}

# ---------------------------------------------------------------- guards on the target (before anything destructive)
Write-Step 'Checking debug targets'
$tgtList = @(Get-ComposeContainers $DevProject 'plane-db' -RunningOnly)
if ($tgtList.Count -ne 1) { Fail "expected exactly one running debug database (project=$DevProject, service=plane-db), found $($tgtList.Count)" }
$tgt = $tgtList[0]
if (-not $tgt.Name.StartsWith('plane-dev-')) { Fail "debug database container is named '$($tgt.Name)', expected plane-dev-*" }
if ($src -and $src.Id -eq $tgt.Id) { Fail 'source and target database are the same container' }
# Assign before wrapping: Windows PowerShell 5.1's ConvertFrom-Json emits a JSON array as ONE pipeline object.
$mountsJson = ((& docker inspect --format '{{json .Mounts}}' $tgt.Id) | Out-String) | ConvertFrom-Json
$pgMount = @(@($mountsJson) | Where-Object { $_.Destination -eq '/var/lib/postgresql/data' })
if ($pgMount.Count -ne 1 -or $pgMount[0].Type -ne 'volume' -or $pgMount[0].Name -ne 'plane-dev_pgdata') {
  Fail "$($tgt.Name) does not mount volume plane-dev_pgdata at /var/lib/postgresql/data - refusing"
}
$redisList = @(Get-ComposeContainers $DevProject 'plane-redis' -RunningOnly)
if ($redisList.Count -ne 1 -or -not $redisList[0].Name.StartsWith('plane-dev-')) { Fail "expected exactly one running debug redis named plane-dev-*, found $($redisList.Count)" }
$redis = $redisList[0]
if ((Get-VolumeProject 'plane-dev_uploads') -ne $DevProject) { Fail "volume plane-dev_uploads is missing or not labelled com.docker.compose.project=$DevProject" }
Write-Host "    target (debug): $($tgt.Name), $($redis.Name), plane-dev_uploads"
if (-not (Wait-PgReady $tgt.Id 120)) { Fail "debug Postgres ($($tgt.Name)) did not become ready within 120s" }

# ---------------------------------------------------------------- 2. dump release
if (-not $FromDump) {
  New-Item -ItemType Directory -Force $CheckpointDir | Out-Null
  $dumpPath = Join-Path $CheckpointDir "release-$ts.dump"
  Write-Step "Dumping the release database from $($src.Name) (read-only) -> $dumpPath"
  # Single-quoted pieces + concatenation: no double quotes inside sh -c (PowerShell 5.1), $POSTGRES_* expand in the container.
  & docker exec $src.Id sh -c ('pg_dump -U $POSTGRES_USER -d $POSTGRES_DB -Fc -f ' + $tmp)
  $dumpRc = $LASTEXITCODE
  if ($dumpRc -eq 0) { & docker cp "$($src.Id):$tmp" $dumpPath; $dumpRc = $LASTEXITCODE }
  & docker exec $src.Id rm -f $tmp
  if ($dumpRc -ne 0) { Fail 'dumping the release database failed (nothing was changed)' }
  if (-not (Test-Path $dumpPath) -or (Get-Item $dumpPath).Length -le 0) { Fail "dump $dumpPath is missing or empty (nothing was changed)" }
  Write-Host ("    {0:N0} bytes" -f (Get-Item $dumpPath).Length)
}

# ---------------------------------------------------------------- 3. restore into debug
Write-Step "Restoring into the debug database ($($tgt.Name))"
& docker cp $dumpPath "$($tgt.Id):$tmp"
if ($LASTEXITCODE -ne 0) { Fail 'copying the dump into the debug database container failed (nothing was changed)' }
& docker exec $tgt.Id sh -c ('pg_restore -l ' + $tmp + ' > /dev/null')
if ($LASTEXITCODE -ne 0) {
  & docker exec $tgt.Id rm -f $tmp
  Fail "$dumpPath is not a readable pg_dump -Fc archive (debug database left untouched)"
}
& docker exec $tgt.Id sh -c ('dropdb -U $POSTGRES_USER --if-exists --force $POSTGRES_DB && createdb -U $POSTGRES_USER $POSTGRES_DB && pg_restore -U $POSTGRES_USER -d $POSTGRES_DB --no-owner --no-privileges --exit-on-error ' + $tmp + '; rc=$?; rm -f ' + $tmp + '; exit $rc')
if ($LASTEXITCODE -ne 0) { Fail 'restore into the debug database failed - the debug database may be empty or partial; fix and re-run dev-refresh.ps1' }

# ---------------------------------------------------------------- 4. uploads
if (-not $SkipUploads) {
  Write-Step "Copying uploads: $ReleaseUploads (read-only) -> plane-dev_uploads"
  & docker run --rm -v "${ReleaseUploads}:/from:ro" -v 'plane-dev_uploads:/to' alpine:3 sh -c 'find /to -mindepth 1 -delete && cp -a /from/. /to/'
  if ($LASTEXITCODE -ne 0) { Fail 'copying the uploads volume failed' }
} else {
  Write-Host '    -SkipUploads: debug uploads left as they are'
}

# ---------------------------------------------------------------- 5. redis
Write-Step "Flushing debug Redis ($($redis.Name))"
& docker exec $redis.Id valkey-cli FLUSHALL
if ($LASTEXITCODE -ne 0) { Fail 'FLUSHALL on the debug Redis failed' }

# ---------------------------------------------------------------- 6. webhooks
Write-Step 'Deactivating webhooks in the debug database'
$hooks = ('with u as (update webhooks set is_active = false where is_active returning 1) select count(*) from u;' | & docker exec -i $tgt.Id sh -c $PsqlTuples)
if ($LASTEXITCODE -ne 0) { Fail 'deactivating webhooks failed' }
Write-Host ("    {0} webhook(s) deactivated" -f "$hooks".Trim())

# ---------------------------------------------------------------- 7. minio, migrate, start
Write-Step 'Starting debug MinIO'
Invoke-DC up -d plane-minio
if (-not $SkipMigrate) {
  Write-Step 'Migrating the debug database to the working-tree head (migrator, plane.settings.local)'
  Invoke-DC run --rm -T migrator
} else {
  Write-Host '    -SkipMigrate: migrator not run'
}
if (-not $NoStart) {
  Write-Step 'Starting debug api, worker, beat-worker'
  Invoke-DC up -d api worker beat-worker
  $code = Wait-Http $DevApiUrl 180
  if ($code -eq 0) { Write-Warning "debug api did not answer within 180s - check: docker logs plane-dev-api-1" } else { Write-Host "    api answered HTTP $code" }
} else {
  Write-Host '    -NoStart: debug api, worker and beat-worker not started'
}

# ---------------------------------------------------------------- 8. summary
$relLatest = if ($src) { Get-LatestDbMigration $src.Id } else { '(release database not available)' }
$devLatest = Get-LatestDbMigration $tgt.Id
Write-Host ''
Write-Host 'Debug refreshed from release:' -ForegroundColor Green
Write-Host "  dump                      $dumpPath"
Write-Host "  latest db migration       release: $relLatest"
Write-Host "                            debug:   $devLatest"
Write-Host '  sign in again on http://127.0.0.1:3310 (users and passwords come from release)'
