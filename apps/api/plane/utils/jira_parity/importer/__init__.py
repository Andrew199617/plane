# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Jira-parity Jira CSV importer and workspace setup (management commands `import_jira_csv` and
`setup_jira_parity`).

Modules:
- csv_reader: duplicate-header aware Jira CSV reader + locale-proof Jira date parsing
- mapping:    pure Jira -> Plane value mappings (priority, status, type, links, sprint date plan)
- config:     workspace-specific --config file (project names/categories, skips, renames)
- constants:  importer defaults
- projects:   project creation with the API's semantics, project categories
- importer:   JiraCsvImporter (plan / run / summary)
- setup:      run_setup (idempotent workspace configuration)
The description converter lives in plane.utils.jira_parity.wiki_markup.
"""
