/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: work item types (owned by the work-item-types feature)
import type { TLogoProps } from "../common";

/**
 * Workspace-level work item type as returned by
 * GET /api/workspaces/<slug>/work-item-types/ and
 * GET /api/workspaces/<slug>/projects/<project_id>/work-item-types/
 */
export type TWorkItemType = {
  id: string;
  name: string;
  description: string;
  logo_props: TLogoProps;
  is_epic: boolean;
  is_sub_task: boolean;
  is_default: boolean;
  is_active: boolean;
  level: number;
  workspace_id: string;
};

/** Body for POST / PATCH /api/workspaces/<slug>/work-item-types/[<id>/] */
export type TWorkItemTypePayload = Partial<
  Pick<
    TWorkItemType,
    "name" | "description" | "logo_props" | "is_epic" | "is_sub_task" | "is_default" | "is_active" | "level"
  >
>;

/**
 * Jira-like glyphs the web app draws for a work item type (a white glyph on a colored rounded square).
 * Stored in `logo_props.icon.name` as a Material Symbols ligature (see JP_WORK_ITEM_TYPE_ICON_LOGO_NAMES)
 * so generic logo renderers still show something sensible.
 */
export type TWorkItemTypeIconKey = "task" | "sub_task" | "story" | "bug" | "epic";

/** Why a work item type cannot be used for a work item in its current hierarchy position. */
export type TWorkItemTypeHierarchyError =
  /** The type is a Sub-task and the work item has no parent. */
  | "sub_task_requires_parent"
  /** The parent work item is a Sub-task (Sub-tasks cannot have children). */
  | "parent_is_sub_task"
  /** The work item has children and the type is a Sub-task (Sub-tasks cannot have children). */
  | "sub_task_cannot_have_children";
