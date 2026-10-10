/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: pure work item type rules (owned by the work-item-types feature).
// Kept free of React/MobX so it can be unit tested with `node --test` (see rules.test.mjs).
import {
  JP_DEFAULT_WORK_ITEM_TYPE_COLOR,
  JP_WORK_ITEM_TYPE_COLORS,
  JP_WORK_ITEM_TYPE_ICON_ALIASES,
  JP_WORK_ITEM_TYPE_ICON_DEFAULT_COLORS,
  JP_WORK_ITEM_TYPE_ICON_LOGO_NAMES,
} from "@plane/constants";
import type { TLogoProps, TWorkItemType, TWorkItemTypeHierarchyError, TWorkItemTypeIconKey } from "@plane/types";

type TWorkItemTypeLike = Pick<TWorkItemType, "name"> &
  Partial<Pick<TWorkItemType, "logo_props" | "is_epic" | "is_sub_task">>;

/** Preserve the API's order until every referenced type is loaded; untyped items sort last. */
export const sortWorkItemsByTypeName = <T extends { type_id?: string | null }>(
  items: T[],
  getTypeName: (typeId: string) => string | undefined,
  descending = false
): T[] | undefined => {
  const rows = items.map((item) => ({ item, name: item.type_id ? getTypeName(item.type_id)?.toLowerCase() : null }));
  if (rows.some((row) => row.name === undefined)) return undefined;
  return (
    rows
      // oxlint-disable-next-line unicorn/no-array-sort -- sorts a new array; web targets ES2022
      .sort((a, b) => {
        if (a.name === b.name) return 0;
        if (a.name === null) return 1;
        if (b.name === null) return -1;
        const order = a.name! < b.name! ? -1 : 1;
        return descending ? -order : order;
      })
      .map((row) => row.item)
  );
};

const HEX_COLOR_REGEX = /^#(?:[0-9a-f]{3}|[0-9a-f]{6})$/i;
const WHITE_COLORS = new Set(["#fff", "#ffffff"]);

/** A usable brand color: a hex color that is not white (white is the glyph color). */
const getBrandColor = (color: string | undefined | null): string | undefined => {
  const trimmed = color?.trim();
  if (!trimmed || !HEX_COLOR_REGEX.test(trimmed) || WHITE_COLORS.has(trimmed.toLowerCase())) return undefined;
  return trimmed;
};

/** Maps a work item type name to a Jira glyph (`Sub-task`, `subtask`, `Bug`, ...). */
const getIconKeyFromName = (name: string | undefined | null): TWorkItemTypeIconKey | undefined => {
  const normalized = (name ?? "")
    .trim()
    .toLowerCase()
    .replace(/[\s_-]+/g, "");
  if (!normalized) return undefined;
  if (normalized === "subtask") return "sub_task";
  if (normalized === "task") return "task";
  if (normalized === "story" || normalized === "userstory") return "story";
  if (normalized === "bug" || normalized === "defect") return "bug";
  if (normalized === "epic") return "epic";
  return undefined;
};

/**
 * Resolves the Jira glyph of a work item type. An explicit icon in `logo_props` wins (admins can pick any
 * glyph), then the type flags (`is_epic`, `is_sub_task`), then the type name. Unknown types draw the Task glyph.
 */
export const getWorkItemTypeIconKey = (workItemType: TWorkItemTypeLike | undefined | null): TWorkItemTypeIconKey => {
  if (!workItemType) return "task";
  const logoIconName = workItemType.logo_props?.icon?.name?.trim().toLowerCase();
  if (logoIconName && JP_WORK_ITEM_TYPE_ICON_ALIASES[logoIconName]) return JP_WORK_ITEM_TYPE_ICON_ALIASES[logoIconName];
  if (workItemType.is_epic) return "epic";
  if (workItemType.is_sub_task) return "sub_task";
  return getIconKeyFromName(workItemType.name) ?? "task";
};

/**
 * Resolves the brand color of a work item type: `logo_props.icon.background_color`, then
 * `logo_props.icon.color` (ignoring white, which is the glyph color), then the Jira color for the type name,
 * then the default color of its glyph.
 */
export const getWorkItemTypeColor = (workItemType: TWorkItemTypeLike | undefined | null): string => {
  if (!workItemType) return JP_DEFAULT_WORK_ITEM_TYPE_COLOR;
  const icon = workItemType.logo_props?.icon;
  return (
    getBrandColor(icon?.background_color) ??
    getBrandColor(icon?.color) ??
    JP_WORK_ITEM_TYPE_COLORS[workItemType.name] ??
    JP_WORK_ITEM_TYPE_ICON_DEFAULT_COLORS[getWorkItemTypeIconKey(workItemType)] ??
    JP_DEFAULT_WORK_ITEM_TYPE_COLOR
  );
};

/** Builds the `logo_props` saved for a Jira glyph + color (both icon colors carry the brand color). */
export const buildWorkItemTypeLogoProps = (iconKey: TWorkItemTypeIconKey, color: string): TLogoProps => {
  const brandColor = getBrandColor(color) ?? JP_WORK_ITEM_TYPE_ICON_DEFAULT_COLORS[iconKey];
  return {
    in_use: "icon",
    icon: {
      name: JP_WORK_ITEM_TYPE_ICON_LOGO_NAMES[iconKey],
      color: brandColor,
      background_color: brandColor,
    },
  };
};

/** Sort rank: the default type first, then standard types, then Epics, then Sub-tasks. */
const getSortRank = (workItemType: TWorkItemType): number => {
  if (workItemType.is_default) return 0;
  if (workItemType.is_sub_task) return 3;
  if (workItemType.is_epic) return 2;
  return 1;
};

/** Sorts work item types Jira-style: default (Task) first, standard types by name, then Epic, then Sub-task. */
export const sortWorkItemTypes = (workItemTypes: TWorkItemType[]): TWorkItemType[] =>
  // oxlint-disable-next-line unicorn/no-array-sort -- sorts a copy; web targets ES2022 (no toSorted)
  [...workItemTypes].sort((a, b) => {
    const rankDiff = getSortRank(a) - getSortRank(b);
    if (rankDiff !== 0) return rankDiff;
    return a.name.localeCompare(b.name);
  });

export type TWorkItemTypeHierarchyContext = {
  /** Whether the work item has (or will have) a parent. */
  hasParent: boolean;
  /** Type of the parent work item, when known. */
  parentType?: TWorkItemType | undefined | null;
  /** Whether the work item already has children (sub-work items). */
  hasChildren?: boolean;
};

/**
 * Validates a work item type against the work item's hierarchy position. Mirrors the server rules:
 * a Sub-task requires a parent, and a Sub-task can never be the parent of another work item.
 * Returns `undefined` when the combination is valid.
 */
export const getWorkItemTypeHierarchyError = (
  workItemType: TWorkItemType | undefined | null,
  context: TWorkItemTypeHierarchyContext
): TWorkItemTypeHierarchyError | undefined => {
  if (context.hasParent && context.parentType?.is_sub_task) return "parent_is_sub_task";
  if (!workItemType?.is_sub_task) return undefined;
  if (!context.hasParent) return "sub_task_requires_parent";
  if (context.hasChildren) return "sub_task_cannot_have_children";
  return undefined;
};

/**
 * Whether a type can be picked for a work item that is being edited in place (sidebar, peek, spreadsheet,
 * header switcher). Picking Sub-task needs an existing parent there, and is not allowed for a work item
 * that already has children.
 */
export const isWorkItemTypeSelectable = (
  workItemType: TWorkItemType,
  context: Omit<TWorkItemTypeHierarchyContext, "parentType">
): boolean => getWorkItemTypeHierarchyError(workItemType, context) === undefined;

/**
 * Type suggested for a new work item created under `parentType`: Sub-task under a standard work item
 * (Task, Story, Bug), otherwise the default type. `undefined` keeps the current selection.
 */
export const getSuggestedWorkItemTypeForParent = (
  workItemTypes: TWorkItemType[],
  parentType: TWorkItemType | undefined | null
): TWorkItemType | undefined => {
  const activeTypes = workItemTypes.filter((workItemType) => workItemType.is_active);
  if (parentType && !parentType.is_epic && !parentType.is_sub_task) {
    const subTaskType = activeTypes.find((workItemType) => workItemType.is_sub_task);
    if (subTaskType) return subTaskType;
  }
  return activeTypes.find((workItemType) => workItemType.is_default);
};
