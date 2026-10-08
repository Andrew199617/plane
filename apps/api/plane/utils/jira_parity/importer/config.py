# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Workspace-specific Jira-parity configuration for `setup_jira_parity` and `import_jira_csv`.

The built-in default is empty: projects are named from the CSV, no categories are seeded, no Jira
project is skipped, names are not rewritten and the timezone comes from the command line or the
acting user. A JSON file passed with ``--config <path>`` (or named by the ``JIRA_PARITY_CONFIG``
environment variable) supplies a workspace's own data; ``jira_parity.example.json`` next to this
module documents the format:

    {
      "timezone": "Europe/Berlin",
      "categories": [{"name": "Product", "description": "...", "emoji": 128640}],
      "projects": {"ABC": {"name": "Example App", "category": "Product", "emoji": "128241"}},
      "skip_projects": ["IDEA"],
      "name_replacements": {"Legacy": "Current"}
    }

- categories: created in list order (sidebar / board order); description and logo fill empty fields.
- projects: Jira project key -> Plane project name, category and logo (all optional).
- skip_projects: Jira project keys not imported unless --skip-projects says otherwise.
- name_replacements: whole-word replacements applied to project names and descriptions from the CSV.
- emoji: a decimal code point (127918), Plane's "-"-joined decimal string, or the emoji itself.
"""

# Python imports
import json
import os
import re
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

CONFIG_ENV_VAR = "JIRA_PARITY_CONFIG"
TIMEZONE_ENV_VAR = "JIRA_PARITY_TIMEZONE"
FALLBACK_TIMEZONE = "UTC"

_DECIMAL_EMOJI_RE = re.compile(r"^\d+(-\d+)*$")
_TOP_LEVEL_KEYS = {"timezone", "categories", "projects", "skip_projects", "name_replacements"}


class JiraParityConfigError(ValueError):
    """The config file is missing, is not valid JSON or does not match the expected shape."""


def _emoji_value(value, where):
    """Normalize an emoji to Plane's logo value: "-"-joined decimal code points."""
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        raise JiraParityConfigError(f"{where}: emoji must be a code point or an emoji, not {value!r}")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        text = value.strip()
        if _DECIMAL_EMOJI_RE.match(text):
            return text
        return "-".join(str(ord(char)) for char in text)
    raise JiraParityConfigError(f"{where}: emoji must be a code point or an emoji, not {value!r}")


def _logo_props(emoji):
    return {"in_use": "emoji", "emoji": {"value": emoji}} if emoji else {}


@dataclass(frozen=True)
class CategorySpec:
    name: str
    description: str = ""
    emoji: str = ""

    @property
    def logo_props(self):
        return _logo_props(self.emoji)


@dataclass(frozen=True)
class ProjectSpec:
    identifier: str
    name: str = ""
    category: str = ""
    emoji: str = ""

    @property
    def logo_props(self):
        return _logo_props(self.emoji)


@dataclass
class JiraParityConfig:
    categories: Tuple[CategorySpec, ...] = ()
    projects: Dict[str, ProjectSpec] = field(default_factory=dict)
    skip_projects: Tuple[str, ...] = ()
    name_replacements: Dict[str, str] = field(default_factory=dict)
    timezone: str = ""
    source: str = ""

    def __post_init__(self):
        self._replacements = [
            (re.compile(r"\b" + re.escape(old) + r"\b"), new) for old, new in self.name_replacements.items() if old
        ]

    @property
    def project_category_map(self):
        """{Jira project key: category name} for the projects that name a category."""
        return {key: spec.category for key, spec in self.projects.items() if spec.category}

    def category_names(self):
        """Configured categories in order, then categories only named by a project (no duplicates)."""
        names = []
        seen = set()
        for name in [spec.name for spec in self.categories] + [spec.category for spec in self.projects.values()]:
            if name and name.casefold() not in seen:
                seen.add(name.casefold())
                names.append(name)
        return names

    def rename(self, text):
        """Apply the whole-word name replacements to a project name or description."""
        text = text or ""
        for pattern, replacement in self._replacements:
            text = pattern.sub(replacement, text)
        return text


def _require(condition, message):
    if not condition:
        raise JiraParityConfigError(message)


def _text(value, where):
    _require(value is None or isinstance(value, str), f"{where} must be a string")
    return (value or "").strip()


def parse_config(data, source=""):
    """Build a JiraParityConfig from already-decoded JSON data (a dict)."""
    prefix = f"{source}: " if source else ""
    _require(isinstance(data, dict), f"{prefix}the config must be a JSON object")
    unknown = sorted(set(data) - _TOP_LEVEL_KEYS)
    _require(not unknown, f"{prefix}unknown key(s): {', '.join(unknown)}")

    categories = []
    raw_categories = data.get("categories") or []
    _require(isinstance(raw_categories, list), f"{prefix}'categories' must be a list")
    for index, item in enumerate(raw_categories):
        where = f"{prefix}categories[{index}]"
        if isinstance(item, str):
            item = {"name": item}
        _require(isinstance(item, dict), f"{where} must be an object or a name")
        name = _text(item.get("name"), f"{where}.name")
        _require(name, f"{where}.name is required")
        categories.append(
            CategorySpec(
                name=name,
                description=_text(item.get("description"), f"{where}.description"),
                emoji=_emoji_value(item.get("emoji"), where),
            )
        )

    projects = {}
    raw_projects = data.get("projects") or {}
    _require(isinstance(raw_projects, dict), f"{prefix}'projects' must be an object keyed by Jira project key")
    for key, item in raw_projects.items():
        identifier = str(key).strip().upper()
        where = f"{prefix}projects.{identifier}"
        _require(identifier, f"{prefix}'projects' has an empty key")
        _require(isinstance(item, dict), f"{where} must be an object")
        projects[identifier] = ProjectSpec(
            identifier=identifier,
            name=_text(item.get("name"), f"{where}.name"),
            category=_text(item.get("category"), f"{where}.category"),
            emoji=_emoji_value(item.get("emoji"), where),
        )

    raw_skip = data.get("skip_projects") or []
    _require(
        isinstance(raw_skip, list) and all(isinstance(key, str) for key in raw_skip),
        f"{prefix}'skip_projects' must be a list of Jira project keys",
    )
    skip_projects = tuple(key.strip().upper() for key in raw_skip if key.strip())

    raw_replacements = data.get("name_replacements") or {}
    _require(
        isinstance(raw_replacements, dict) and all(isinstance(v, str) for v in raw_replacements.values()),
        f"{prefix}'name_replacements' must map words to replacement strings",
    )

    return JiraParityConfig(
        categories=tuple(categories),
        projects=projects,
        skip_projects=skip_projects,
        name_replacements={str(k): v for k, v in raw_replacements.items()},
        timezone=_text(data.get("timezone"), f"{prefix}timezone"),
        source=source,
    )


def load_config(path: Optional[str] = None, *, use_env: bool = True) -> JiraParityConfig:
    """Load the config from `path`, else from $JIRA_PARITY_CONFIG, else return the empty default."""
    path = (path or "").strip() or ((os.environ.get(CONFIG_ENV_VAR) or "").strip() if use_env else "")
    if not path:
        return JiraParityConfig()
    try:
        with open(path, encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except FileNotFoundError as e:
        raise JiraParityConfigError(f"Config file not found: {path}") from e
    except (OSError, ValueError) as e:
        raise JiraParityConfigError(f"Could not read config {path}: {e}") from e
    return parse_config(data, source=path)


def resolve_timezone(explicit="", config=None, user=None):
    """Timezone precedence: explicit value > $JIRA_PARITY_TIMEZONE > config > the user's own
    timezone (when it is not UTC) > UTC."""
    for candidate in (
        explicit,
        os.environ.get(TIMEZONE_ENV_VAR),
        config.timezone if config is not None else "",
    ):
        if candidate and candidate.strip():
            return candidate.strip()
    user_timezone = getattr(user, "user_timezone", None) if user is not None else None
    if user_timezone and user_timezone != FALLBACK_TIMEZONE:
        return user_timezone
    return FALLBACK_TIMEZONE
