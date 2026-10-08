/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: teams (owned by the teams feature)
import type { TLogoProps } from "../common";

/** GET /api/workspaces/<slug>/teams/[<id>/] */
export type TTeam = {
  id: string;
  name: string;
  description: string;
  logo_props: TLogoProps;
  /** numeric project role applied on auto-join (20 Admin, 15 Member, 10 Agent, 5 Guest) */
  default_project_role: number;
  auto_join: boolean;
  /** user ids of the team's (active workspace) members */
  member_ids: string[];
  member_count: number;
  /** non-archived projects the team is linked to (all of them when auto_join is on) */
  project_ids: string[];
  project_count: number;
  workspace?: string;
  created_at: string;
  updated_at?: string;
};

/**
 * Body for POST / PATCH /api/workspaces/<slug>/teams/[<id>/].
 * `member_ids` / `project_ids` replace the team's members / linked projects (project_ids is
 * ignored while auto_join is on).
 */
export type TTeamPayload = Partial<
  Pick<
    TTeam,
    "name" | "description" | "logo_props" | "default_project_role" | "auto_join" | "member_ids" | "project_ids"
  >
>;

/** Body for POST /api/workspaces/<slug>/teams/<id>/members/ */
export type TTeamMembersPayload = {
  member_ids: string[];
};

/** Body for POST /api/workspaces/<slug>/teams/<id>/projects/ */
export type TTeamProjectsPayload = { project_ids: string[] } | { all_projects: true };
