#!/usr/bin/env python3
"""First-run setup for the local Plane DEBUG instance (idempotent).

1. Instance admin sign-up through the same HTTP flow the admin app (god-mode) uses
   (CSRF cookie + form POST to /api/instances/admins/sign-up/). A strong random password
   is generated and written ONLY to the target's credentials file (never printed):
   <repo>/.local/credentials-debug.txt for debug, <repo>/.local/credentials.txt (the RELEASE
   instance admin) only with --i-know-this-is-release. An existing credentials file is never
   overwritten: move it aside first. On an instance that is already set up the password is read
   from the target's file; a debug stack seeded from release falls back to reading (never
   writing) .local/credentials.txt, because the users come from release.
2. Workspace <--workspace-name> (slug <--workspace-slug>) owned by the admin, created through the
   ORM (mirrors WorkSpaceViewSet.create minus the demo-project seed task), and the admin's profile
   is marked onboarded so the web app goes straight into the workspace.
3. Verifies a password sign-in through the web app flow (/auth/sign-in/) and lists workspaces.

Usage (host Python 3, no extra deps; backend must be up):

    python scripts/local/first-run-setup.py --email admin@example.com [--first-name Admin]
        [--last-name User] [--workspace-name "My Workspace"] [--workspace-slug my-workspace]

Each option falls back to an environment variable (PLANE_ADMIN_EMAIL, PLANE_ADMIN_FIRST_NAME,
PLANE_ADMIN_LAST_NAME, PLANE_WORKSPACE_NAME, PLANE_WORKSPACE_SLUG), then to <repo>/.local/first-run.json
(same keys as scripts/local/first-run.example.json; .local/ is never committed), then to the
neutral defaults. The e-mail has no default.

Target (defaults = the DEBUG stack, compose project plane-dev; see AGENTS.md "Local environment"):

    --api http://127.0.0.1:8310  --admin-origin http://127.0.0.1:3301  --web-origin http://127.0.0.1:3310
    --container plane-dev-api-1  --settings plane.settings.local

A debug stack seeded from release with scripts/local/dev-refresh.ps1 does not need this script.
RELEASE (plane-release-* containers or port 3300; before the cutover plane-api-1 or port 8300) is
refused unless --i-know-this-is-release is passed.
"""

import argparse
import datetime
import http.cookiejar
import os
import json
import pathlib
import secrets
import string
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

# Target defaults: the DEBUG stack (compose project plane-dev). Overridable with --api, --admin-origin,
# --web-origin, --container and --settings; filled by parse_settings() before the steps run.
DEFAULT_TARGET = {
    "api": "http://127.0.0.1:8310",
    "admin_origin": "http://127.0.0.1:3301",
    "web_origin": "http://127.0.0.1:3310",
    "container": "plane-dev-api-1",
    "settings": "plane.settings.local",
}
API = DEFAULT_TARGET["api"]
ADMIN_ORIGIN = DEFAULT_TARGET["admin_origin"]
WEB_ORIGIN = DEFAULT_TARGET["web_origin"]
API_CONTAINER = DEFAULT_TARGET["container"]
DJANGO_SETTINGS = DEFAULT_TARGET["settings"]

ROOT = pathlib.Path(__file__).resolve().parents[2]
# .local/credentials.txt holds the RELEASE instance-admin password; it is written only for a release target.
RELEASE_CRED_FILE = ROOT / ".local" / "credentials.txt"
DEBUG_CRED_FILE = ROOT / ".local" / "credentials-debug.txt"
CRED_FILE = DEBUG_CRED_FILE  # set per target in __main__
LOCAL_CONFIG = ROOT / ".local" / "first-run.json"

# Containers / host ports that are RELEASE (after the cutover: plane-release-*, 3300; before it: plane-api-1, 8300).
RELEASE_CONTAINERS = ("plane-api-1",)
RELEASE_PORTS = (3300, 8300)

# option -> (environment variable, key in .local/first-run.json, default)
SETTINGS = {
    "email": ("PLANE_ADMIN_EMAIL", "email", None),
    "first_name": ("PLANE_ADMIN_FIRST_NAME", "first_name", "Admin"),
    "last_name": ("PLANE_ADMIN_LAST_NAME", "last_name", "User"),
    "workspace_name": ("PLANE_WORKSPACE_NAME", "workspace_name", "My Workspace"),
    "workspace_slug": ("PLANE_WORKSPACE_SLUG", "workspace_slug", "my-workspace"),
}

# Filled by parse_settings() before the steps run.
EMAIL = FIRST_NAME = LAST_NAME = WORKSPACE_NAME = WORKSPACE_SLUG = ""


def _url_port(url):
    try:
        return urllib.parse.urlsplit(url).port
    except ValueError:
        return None


def parse_settings(argv=None):
    """CLI option > environment variable > .local/first-run.json > default."""
    parser = argparse.ArgumentParser(description="First-run setup for the local Plane DEBUG instance (idempotent).")
    for option, (env, _, default) in SETTINGS.items():
        parser.add_argument(
            "--" + option.replace("_", "-"),
            dest=option,
            default=None,
            help=f"(env {env}; default {default!r})" if default else f"(env {env}; required)",
        )
    target = parser.add_argument_group("target (defaults: the DEBUG stack, compose project plane-dev; see AGENTS.md)")
    target.add_argument("--api", default=DEFAULT_TARGET["api"], help="API base URL (default %(default)s)")
    target.add_argument("--admin-origin", dest="admin_origin", default=DEFAULT_TARGET["admin_origin"],
                        help="origin of the admin (god-mode) app (default %(default)s)")
    target.add_argument("--web-origin", dest="web_origin", default=DEFAULT_TARGET["web_origin"],
                        help="origin of the web app (default %(default)s)")
    target.add_argument("--container", default=DEFAULT_TARGET["container"],
                        help="API container for the Django shell step (default %(default)s)")
    target.add_argument("--settings", default=DEFAULT_TARGET["settings"],
                        help="Django settings module for the shell step (default %(default)s)")
    target.add_argument("--i-know-this-is-release", dest="i_know_this_is_release", action="store_true",
                        help="allow a release container (plane-release*, plane-api-1) or a :3300/:8300 URL "
                             "(RELEASE = the owner's real data); credentials then go to .local/credentials.txt")
    args = parser.parse_args(argv)
    local = {}
    if LOCAL_CONFIG.exists():
        local = json.loads(LOCAL_CONFIG.read_text(encoding="utf-8-sig"))
    values = {}
    for option, (env, key, default) in SETTINGS.items():
        values[option] = (getattr(args, option) or os.environ.get(env) or local.get(key) or default or "").strip()
    if not values["email"]:
        parser.error("the admin e-mail is required: pass --email or set PLANE_ADMIN_EMAIL")
    for key in ("api", "admin_origin", "web_origin"):
        values[key] = getattr(args, key).strip().rstrip("/")
    values["container"] = args.container.strip()
    values["settings"] = args.settings.strip()
    release_targets = []
    if values["container"].startswith("plane-release") or values["container"] in RELEASE_CONTAINERS:
        release_targets.append("--container " + values["container"])
    for key in ("api", "admin_origin", "web_origin"):
        if _url_port(values[key]) in RELEASE_PORTS:
            release_targets.append("--" + key.replace("_", "-") + " " + values[key])
    if release_targets and not args.i_know_this_is_release:
        parser.error(
            "refusing to target RELEASE (" + ", ".join(release_targets) + "). This script is for the DEBUG "
            "stack; pass --i-know-this-is-release only with the owner's explicit OK (see AGENTS.md)."
        )
    values["release"] = bool(args.i_know_this_is_release)
    return values


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def new_session():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), _NoRedirect), jar


def get_json(opener, path, origin=None):
    req = urllib.request.Request(API + path, headers={"Accept": "application/json", **({"Origin": origin} if origin else {})})
    with opener.open(req, timeout=30) as r:
        return r.status, json.loads(r.read() or b"null")


def post_form(opener, path, fields, origin):
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(
        API + path, data=data, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded", "Origin": origin, "Referer": origin + "/"},
    )
    try:
        with opener.open(req, timeout=30) as r:
            return r.status, r.headers.get("Location")
    except urllib.error.HTTPError as e:  # 3xx surface here because redirects are disabled
        return e.code, e.headers.get("Location")


def csrf(opener):
    _, body = get_json(opener, "/auth/get-csrf-token/")
    return body["csrf_token"]


def gen_password(n=24):
    alphabet = string.ascii_letters + string.digits + "!#%*-_=+"
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(n))
        if (any(c.islower() for c in pw) and any(c.isupper() for c in pw)
                and any(c.isdigit() for c in pw) and any(c in "!#%*-_=+" for c in pw)):
            return pw


def read_password(path):
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("password:"):
            return line.split(":", 1)[1].strip()
    raise SystemExit(f"No password line in {path}")


def step_admin_signup():
    opener, _ = new_session()
    _, inst = get_json(opener, "/api/instances/")
    if inst["instance"]["is_setup_done"]:
        # Read-only. A debug stack seeded from release (dev-refresh.ps1) has the release users, so the release
        # credentials file is a valid read-only fallback there.
        candidates = [CRED_FILE] + ([RELEASE_CRED_FILE] if CRED_FILE != RELEASE_CRED_FILE else [])
        for path in candidates:
            if path.exists():
                print(f"[1] instance already set up - skipping admin sign-up (password from {path.name})")
                return read_password(path), path
        raise SystemExit("Instance already set up but no credentials file found ("
                         + ", ".join(str(p) for p in candidates) + ") - cannot continue.")

    # Never overwrite a credentials file: it may hold the only copy of another instance's admin password
    # (.local/credentials.txt is the RELEASE instance admin).
    if CRED_FILE.exists():
        raise SystemExit(f"[1] {CRED_FILE} already exists and this instance is not set up yet. It may hold another "
                         "instance's admin password, so it is never overwritten: move it aside (keep it!) and re-run.")
    password = gen_password()
    CRED_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(CRED_FILE, "x", encoding="utf-8") as f:  # exclusive create
            f.write(
                "# Local Plane instance - instance admin (god-mode) + workspace owner\n"
                f"# target: api {API}, container {API_CONTAINER}\n"
                f"# created {datetime.datetime.now().isoformat(timespec='seconds')}\n"
                f"name: {FIRST_NAME} {LAST_NAME}\nemail: {EMAIL}\npassword: {password}\n"
                f"web: {WEB_ORIGIN}/{WORKSPACE_SLUG}\nadmin: {ADMIN_ORIGIN}/god-mode/\n"
            )
    except FileExistsError:
        raise SystemExit(f"[1] {CRED_FILE} appeared meanwhile; it is never overwritten - move it aside and re-run.")
    token = csrf(opener)
    status, location = post_form(opener, "/api/instances/admins/sign-up/", {
        "csrfmiddlewaretoken": token, "first_name": FIRST_NAME, "last_name": LAST_NAME, "email": EMAIL,
        "company_name": WORKSPACE_NAME, "password": password, "is_telemetry_enabled": "False",
    }, ADMIN_ORIGIN)
    if status != 302 or not location or "error_code" in location or not location.rstrip("/").endswith("general"):
        raise SystemExit(f"[1] admin sign-up failed: HTTP {status} -> {location}")
    print(f"[1] instance admin created ({EMAIL}); redirect -> {location}")
    return password, CRED_FILE


DJANGO_SNIPPET = r"""
from django.db import transaction
from plane.db.models import User, Workspace, WorkspaceMember, Profile
EMAIL, NAME, SLUG = %r, %r, %r
with transaction.atomic():
    u = User.objects.get(email=EMAIL)
    u.is_email_verified = True
    u.save(update_fields=["is_email_verified"])
    ws = Workspace.objects.filter(slug=SLUG).first()
    created = ws is None
    if created:
        ws = Workspace.objects.create(name=NAME, slug=SLUG, owner=u, organization_size="Just myself")
    m, _ = WorkspaceMember.objects.get_or_create(workspace=ws, member=u, defaults={"role": 20})
    if m.role != 20 or not m.is_active:
        m.role, m.is_active = 20, True
        m.save()
    p, _ = Profile.objects.get_or_create(user=u)
    p.is_onboarded = True
    p.onboarding_step = {"profile_complete": True, "workspace_create": True, "workspace_invite": True, "workspace_join": True}
    p.last_workspace_id = ws.id
    p.is_tour_completed = True
    p.save()
print("workspace", "created" if created else "exists", ws.slug, ws.id)
"""


def step_workspace_and_onboarding():
    code = DJANGO_SNIPPET % (EMAIL, WORKSPACE_NAME, WORKSPACE_SLUG)
    r = subprocess.run(
        ["docker", "exec", "-i", API_CONTAINER, "python", "manage.py", "shell", "--settings=" + DJANGO_SETTINGS],
        input=code, capture_output=True, text=True, timeout=180,
    )
    if r.returncode != 0:
        raise SystemExit(f"[2] django shell failed:\n{r.stdout}\n{r.stderr}")
    print("[2]", r.stdout.strip().splitlines()[-1], "| profile onboarded")


def step_verify_signin(password):
    opener, _ = new_session()
    token = csrf(opener)
    status, location = post_form(opener, "/auth/sign-in/", {"csrfmiddlewaretoken": token, "email": EMAIL, "password": password}, WEB_ORIGIN)
    if status != 302 or not location or "error_code" in location:
        raise SystemExit(f"[3] sign-in failed: HTTP {status} -> {location}")
    print(f"[3] password sign-in OK; redirect -> {location}")
    _, me = get_json(opener, "/api/users/me/", WEB_ORIGIN)
    print(f"    /api/users/me/ -> {me['email']} ({me['first_name']} {me['last_name']})")
    _, wss = get_json(opener, "/api/users/me/workspaces/", WEB_ORIGIN)
    print("    workspaces:", [(w["name"], w["slug"], w.get("role")) for w in wss])
    if not any(w["slug"] == WORKSPACE_SLUG for w in wss):
        raise SystemExit("[3] workspace not visible to user")


if __name__ == "__main__":
    settings = parse_settings()
    EMAIL, FIRST_NAME, LAST_NAME = settings["email"], settings["first_name"], settings["last_name"]
    WORKSPACE_NAME, WORKSPACE_SLUG = settings["workspace_name"], settings["workspace_slug"]
    API, ADMIN_ORIGIN, WEB_ORIGIN = settings["api"], settings["admin_origin"], settings["web_origin"]
    API_CONTAINER, DJANGO_SETTINGS = settings["container"], settings["settings"]
    CRED_FILE = RELEASE_CRED_FILE if settings["release"] else DEBUG_CRED_FILE
    print(f"target: api {API}, container {API_CONTAINER} ({DJANGO_SETTINGS}); credentials file {CRED_FILE.name}")
    pw, cred_path = step_admin_signup()
    step_workspace_and_onboarding()
    step_verify_signin(pw)
    print(f"done - credentials in {cred_path}")
    sys.exit(0)
