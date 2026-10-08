# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity importer defaults.

Product defaults only. Workspace-specific data (project names, categories, skipped projects, name
replacements, timezone) comes from the --config file (see config.py); no workspace slug or user
e-mail is hard-coded here either (the commands take them as arguments).
"""

JIRA_EXTERNAL_SOURCE = "jira"
DEFAULT_TIMEZONE = "UTC"

# Project feature toggles switched on for projects the importer creates (Jira sprints -> cycles).
IMPORTED_PROJECT_FLAGS = {"cycle_view": True, "module_view": True, "issue_views_view": True}
