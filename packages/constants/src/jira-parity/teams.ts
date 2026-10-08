/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: teams (owned by the teams feature)

/** SWR key for the workspace teams list. */
export const JP_TEAMS_SWR_KEY = (workspaceSlug: string) => `JP_TEAMS_${workspaceSlug}`;

/** Project roles a team can grant (highest first), with their i18n labels (jp-teams namespace). */
export const JP_TEAM_ROLE_OPTIONS: { value: number; i18n_label: string; i18n_description: string }[] = [
  { value: 20, i18n_label: "jp_teams.roles.admin", i18n_description: "jp_teams.roles.admin_description" },
  { value: 15, i18n_label: "jp_teams.roles.member", i18n_description: "jp_teams.roles.member_description" },
  { value: 10, i18n_label: "jp_teams.roles.agent", i18n_description: "jp_teams.roles.agent_description" },
  { value: 5, i18n_label: "jp_teams.roles.guest", i18n_description: "jp_teams.roles.guest_description" },
];

/** Default project role of a new team (Member). */
export const JP_TEAM_DEFAULT_PROJECT_ROLE = 15;

/** Max team badges shown on a member row before collapsing into "+N". */
export const JP_TEAM_BADGES_MAX_VISIBLE = 2;
