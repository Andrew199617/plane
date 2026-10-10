# Agent Development Guide

## Commands

- `pnpm dev` - Start all dev servers (web:3000, admin:3001)
- `pnpm build` - Build all packages and apps
- `pnpm check` - Run all checks (format, lint, types)
- `pnpm check:lint` - OxLint across all packages
- `pnpm check:types` - TypeScript type checking
- `pnpm fix` - Auto-fix format and lint issues
- `pnpm turbo run <command> --filter=<package>` - Target specific package/app

## Code Style

- **Imports**: Use `workspace:*` for internal packages, `catalog:` for external deps
- **TypeScript**: Strict mode enabled, all files must be typed
- **Formatting**: oxfmt, run `pnpm fix:format`
- **Linting**: OxLint with shared `.oxlintrc.json` config
- **Naming**: camelCase for variables/functions, PascalCase for components/types
- **Error Handling**: Use try-catch with proper error types, log errors appropriately
- **State Management**: MobX stores in `packages/shared-state`, reactive patterns
- **Testing**: All features require unit tests, use existing test framework per package
- **Components**: Primitives come from the published `@makeplane/propel` npm package (`@makeplane/propel/components/*`, `elements/*`, `icons`); composite/Plane-specific components live in `@plane/blocks` (`packages/blocks`, subpath imports only, e.g. `@plane/blocks/toast`)

## Backend dependencies (uv)

`apps/api` dependencies are managed with [uv](https://docs.astral.sh/uv/): declared in `apps/api/pyproject.toml`, pinned in `apps/api/uv.lock` (commit both). Groups: `dev` and `test` (installed by default; they use `psycopg-binary`), `production` (gunicorn + the source-built `psycopg-c`; production image and migration-check only). Lint config lives in `apps/api/ruff.toml`.

- uv must be exactly the `required-version` in `apps/api/pyproject.toml` (`uv self update <version>`); bump it together with the uv image in both Dockerfiles
- Set up a local env: `cd apps/api && uv sync`
- Inside the dev/test containers, always pass `--inexact` (`uv sync --inexact`): uv targets the image's system Python there, and an exact sync would uninstall pip
- Add/upgrade a dependency: `uv add <pkg>==<version>` (or `--group test`/`--group dev`), or edit `pyproject.toml` and run `uv lock`
- Run tools: `uv run python manage.py ...`, `uv run ruff check .`

## Backend tests (Docker)

The Django/pytest suite for `apps/api` runs in an isolated stack defined by `docker-compose-test.yml` at the repo root.

Prereq (once): `./setup.sh` — generates `apps/api/.env` from `.env.example`.

- Full suite: `docker compose -f docker-compose-test.yml up --build --abort-on-container-exit --exit-code-from api-tests`
- Subset: `docker compose -f docker-compose-test.yml run --rm --build api-tests pytest -m unit`
- Teardown: `docker compose -f docker-compose-test.yml down -v`

See `apps/api/tests/RUNNING_TESTS.md` for the full walkthrough and troubleshooting; see `apps/api/tests/TESTING_GUIDE.md` for test conventions and fixtures.

<!-- BEGIN fork: local environment (Jira-parity fork). Fork-owned; keep at the end so upstream merges leave it alone. -->

## Local environment (Jira-parity fork): read this before you touch Docker, ports, env files, migrations, git branches or `scripts/local/`

This machine runs the owner's real Plane instance (RELEASE) and a disposable development copy (DEBUG) side by side. Two things above do not apply here: the upstream `pnpm dev` ports, and the bare `docker compose` commands in `apps/api/tests/RUNNING_TESTS.md`.

|                 | RELEASE                                                                                                                                                                                           | DEBUG                                                                                                                                                                                                                                                         | TESTS                     |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------- |
| What            | Real data, always on, desktop and phone                                                                                                                                                           | Your sandbox for this working tree                                                                                                                                                                                                                            | Throwaway pytest stacks   |
| Compose project | `plane`                                                                                                                                                                                           | `plane-dev`                                                                                                                                                                                                                                                   | `plane-test-<your-name>`  |
| Driven by       | `scripts/local/release.ps1` only                                                                                                                                                                  | `scripts/local/dev-up.ps1`, `dev-down.ps1`, `dev-refresh.ps1`                                                                                                                                                                                                 | `docker-compose-test.yml` |
| Code            | A committed `main` sha, checked out detached in worktree `../plane-release` and built into images `plane-release/{backend,proxy,space,live}:<sha12>`                                              | This working tree, uncommitted edits included. The API is bind-mounted with autoreload; Vite runs on the host                                                                                                                                                 | This working tree         |
| URLs            | `http://localhost:3300`, bound to 127.0.0.1 only. Phones reach it through a Tailscale Serve TCP forward to 127.0.0.1:3300 (host name in `$env:PLANE_PUBLIC_HOST` or `.local/release/public-host`) | web `http://127.0.0.1:3310`, admin `http://127.0.0.1:3301/god-mode/`, space `http://127.0.0.1:3302/spaces/`, live `127.0.0.1:3400`, API `http://127.0.0.1:8310`, Postgres `127.0.0.1:55433`, Redis `127.0.0.1:56380`, MinIO `127.0.0.1:9310` (console `9391`) | No host ports             |
| Containers      | `plane-release-{api,worker,beat,live,space,proxy,db,redis,mq,minio}`                                                                                                                              | `plane-dev-<service>-1`                                                                                                                                                                                                                                       | `plane-test-<name>-*`     |
| Data            | External volumes `plane_pgdata`, `plane_uploads`, `plane_redisdata`, `plane_rabbitmq_data`. This is THE REAL DATA                                                                                 | A copy in `plane-dev_pgdata`, `plane-dev_uploads`, `plane-dev_redisdata`, `plane-dev_rabbitmq_data`                                                                                                                                                           | tmpfs                     |
| Settings        | `plane.settings.production`, gunicorn, Celery concurrency 2                                                                                                                                       | `plane.settings.local` (console email), runserver                                                                                                                                                                                                             | test                      |
| Env             | `.local/release/release.env` (gitignored)                                                                                                                                                         | `.env`, `apps/*/.env` (gitignored)                                                                                                                                                                                                                            | test compose              |

Retired. Any note that still uses these is out of date:

- ports 8300, 55432, 56379, 9300 and 9390
- containers `plane-api-1`, `plane-worker-1`, `plane-plane-db-1` and `plane-web-prod`
- network `plane_dev_env`
- `scripts/local/web-prod.ps1`

### Git

- There is one branch, `main`, pushed to remote `fork`. Work in this tree on `main`, or on a short feature branch that you merge into `main`.
- Release ships only committed `main`. `release.ps1 deploy` resolves `main` to a sha and checks that sha out detached in `../plane-release`. Uncommitted edits in this tree never reach release.
- `../plane-release` is detached on purpose, because git cannot check out `main` in two worktrees. Do not attach it to a branch.

### Never

- Run `docker compose` without an explicit `-p` and `-f`.
- Use the upstream `docker-compose.yml`. It is pinned to the dummy project `plane-upstream-unused`, but `-p plane` would still point it at the real data.
- Pass `-p plane` to any compose file.
- Start, stop, restart, rebuild, `up` or `down` project `plane`, or run `exec` write commands in `plane-release-*` containers. Release changes only through `scripts/local/release.ps1 deploy|rollback|up`, and only when the owner asks.
- Run `down -v`, `docker volume rm` or any `docker ... prune`.
- Delete `plane_*` volumes, `plane-release/*` images, `.local/checkpoints/` or `.local/backups/`.
- In `../plane-release`: edit files, commit, check out, reset, run pnpm, or run `git worktree remove` or `git worktree prune`. Only `release.ps1` moves it: `init`, `build -Ref`, `deploy`, and `up`/`rollback` (which return it to the commit of the tag they run).
- Rebase, reset, amend pushed commits on, or force-push `main`. Deploys and rollbacks refer to its shas, so fix forward.
- Run `git push` (to any remote) unless the owner asks. This fork is public; the owner decides when `main` is pushed, after checking it holds no private values.
- Run `migrate`, `makemigrations`, `shell`, `loaddata`, `dbshell` or SQL writes against release.
  - Read-only is fine: `docker exec plane-release-api python manage.py showmigrations`, `release.ps1 status|logs`, or read-only `psql` in `plane-release-db`.
- Point debug, tests or scripts at release containers, volumes or `.local/release/*`, or send writes to `localhost:3300/api`.
- Copy data from debug into release.
- Bind anything to port 3300, or publish a release port on 0.0.0.0.
- Edit or rename a migration once it is committed on `main` or applied to release. Add a new one instead.
- Print `.local/**`, any `.env`, or `docker compose config` output, because it expands secrets. Use `config --services`, `--images` or `--volumes` instead.
- Write private host names, IPs or emails into tracked files. This fork is public; use `$env:PLANE_PUBLIC_HOST`.
- Touch the compose projects `buddy` or `mongoserver`, or other agents' `plane-test-*` projects.

### Debug stack (yours)

- Start: `powershell -ExecutionPolicy Bypass -File scripts/local/dev-up.ps1`.
  - Add `-Build` after changing Python dependencies or `Dockerfile.dev`.
  - Other switches: `-BackendOnly`, `-FrontendOnly`, `-RecoverDocker`.
- Stop: `scripts/local/dev-down.ps1`. `-Down` removes the containers and keeps the volumes.
- Logs: `.devlogs/<name>.log`.
- Open debug only on `127.0.0.1` and release only on `localhost`. Browsers share cookies across ports.
  - Debug sets `SESSION_COOKIE_NAME=plane-dev-session-id`.
  - `admin-session-id` and `csrftoken` have fixed names, so they still collide if you mix hosts.
- Django: `docker exec plane-dev-api-1 python manage.py <cmd> --settings=plane.settings.local`.
- The API reloads on save; Celery does not. Restart it with `docker compose -p plane-dev -f docker-compose-local.yml restart worker beat-worker`.
- Refresh debug data: `powershell -ExecutionPolicy Bypass -File scripts/local/dev-refresh.ps1`.
  - Options: `-FromDump <file>`, `-SkipUploads`, `-SkipMigrate`, `-NoStart`.
  - It only reads release: it dumps the DB to `.local/checkpoints/release-<ts>.dump` and copies `plane_uploads`.
  - It overwrites debug only, then flushes debug Redis, disables webhooks and migrates to the working-tree head.
  - Run it before rehearsing a migration, after switching to a branch with different migrations, or when debug data has drifted.
  - Users and passwords carry over; sign in again.
- Debug sends no email (console backend) and has webhooks disabled. Other integrations copied from release may still call out; do not trigger them.

### Migrations

- Create and apply them in debug only. Start with `docker exec plane-dev-api-1 python manage.py makemigrations db --dry-run -v 3 --settings=plane.settings.local`, then write the file. Number it after the newest migration on `main`.
- Tests run with `--nomigrations`, so they do not cover migrations. To test a migration: commit, run `dev-refresh.ps1`, read the migrator output, then smoke-test on 127.0.0.1:3310.
- Release migrates only inside `release.ps1 deploy`. Deploy takes a checkpoint first, then stops api, worker, beat and live, and runs the migrator. It aborts if release has applied migrations that the new code does not know (renamed or deleted files).

### Deploy release (only when the owner asks)

1. Commit to `main` with explicit paths, or merge your feature branch into `main`. Other sessions may have uncommitted edits in this tree.
2. Make sure everything is green:
   - backend tests in your `plane-test-<name>`
   - `pnpm check` for the packages you touched
   - a migration rehearsal on freshly refreshed debug data
3. Run `powershell -ExecutionPolicy Bypass -File scripts/local/release.ps1 deploy`. It builds the current committed `main`.
   - `-Ref <commit-ish>` deploys another commit. It must be on `main`; deploy refuses anything else unless `-Force` (owner's OK).
   - `-PlanOnly` moves the worktree, checkpoints the running DB and stops after printing the migration plan. It starts, stops and re-creates nothing.
   - `-NoMigrate` aborts before migrating if the plan is not empty.
   - In order, it: checks out the sha detached in `../plane-release` (refuses if that tree is dirty), builds the images, gates on translations and `caddy validate`, takes a DB checkpoint, migrates, runs `up --wait`, health-checks 127.0.0.1:3300, and logs to `.local/release/deployments.tsv`.
4. Report the tag and the checkpoint path, and ask the owner to check the phone link.

After deploy:

- Code rollback: `release.ps1 rollback [-Tag <sha12>]`. This switches back to an older image and does not undo migrations.
- Data rollback: add `-RestoreDump <checkpoint>` (a `.local/checkpoints/release-*.dump` or a file under `.local/backups/`). This loses every write since that checkpoint, so the owner must confirm it by typing `RESTORE` in an interactive console; agents cannot run it.
- Status: `release.ps1 status` shows the deployed tag against the running images, the worktree sha against `main`, and recent deploys. Also `release.ps1 logs api --tail 200`.
- After a reboot, release comes back only once Docker Desktop is running.

### Tests

- Run: `docker compose -p plane-test-<name> -f docker-compose-test.yml run --rm --build api-tests pytest <path> -q`.
- Tear down only your own project: `docker compose -p plane-test-<name> -f docker-compose-test.yml down -v`.
- Ignore the "stop the local stack" advice in `RUNNING_TESTS.md`; the tests publish no ports.
- Pure frontend helpers: `node --test <file>`.

### Troubleshooting

- Docker Desktop won't start (stale sockets): `dev-up.ps1 -RecoverDocker`.
- Raw i18n keys in debug: `packages/i18n/locales` must be a junction to `src/locales` with skip-worktree set.
  - Fix: `Remove-Item packages\i18n\locales; New-Item -ItemType Junction -Path packages\i18n\locales -Target (Resolve-Path packages\i18n\src\locales); git update-index --skip-worktree packages/i18n/locales`.
  - Release images re-create the link in `scripts/local/release/Dockerfile.frontend`.
- Upload 403 or SignatureDoesNotMatch: either the browser origin is missing from `CORS_ALLOWED_ORIGINS`, or a proxy rewrote `Host`. Presigned URLs are signed for `<origin>/uploads`.
- Logged out of release after using debug: debug was opened on `localhost`. Use `127.0.0.1`.
- Release containers stopped or replaced by a stray command (for example `docker compose -p plane -f docker-compose-local.yml up`): tell the owner. With the owner's OK, `release.ps1 up -Force` removes the stray containers in project `plane` by name (volumes are kept) and re-creates the deployed tag. Plain `release.ps1 up` is enough when the release containers are only stopped.
- High RAM: `docker top plane-release-worker` should show at most 3 celery processes.

<!-- END fork: local environment -->
