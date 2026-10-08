/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type {
  TIssueGroupByOptions,
  TIssueOrderByOptions,
  IIssueDisplayProperties,
  IIssueFilterOptions,
  TIssue,
  EIssuesStoreType,
} from "@plane/types";
import type { TIssuePriorities as TIssuePrioritiesBase } from "@plane/types";

export const ALL_ISSUES = "All Issues";

// Jira-parity priorities (highest/high/medium/low/lowest); the union lives in @plane/types.
export type TIssuePriorities = TIssuePrioritiesBase;

/** Default priority for new work items (Jira: Medium). */
export const DEFAULT_ISSUE_PRIORITY: TIssuePriorities = "medium";

export type TIssueFilterPriorityObject = {
  key: TIssuePriorities;
  titleTranslationKey: string;
  className: string;
  icon: string;
};

export enum EIssueGroupByToServerOptions {
  "state" = "state_id",
  "priority" = "priority",
  "labels" = "labels__id",
  "state_detail.group" = "state__group",
  "assignees" = "assignees__id",
  "cycle" = "cycle_id",
  "module" = "issue_module__module_id",
  "target_date" = "target_date",
  // oxlint-disable-next-line typescript/no-duplicate-enum-values -- "team_project" reuses this value on purpose
  "project" = "project_id",
  "created_by" = "created_by",
  // eslint-disable-next-line @typescript-eslint/no-duplicate-enum-values
  "team_project" = "project_id",
  // jira-parity (work item types)
  "issue_type" = "type_id",
}

export enum EIssueGroupBYServerToProperty {
  "state_id" = "state_id",
  "priority" = "priority",
  "labels__id" = "label_ids",
  "state__group" = "state__group",
  "assignees__id" = "assignee_ids",
  "cycle_id" = "cycle_id",
  "issue_module__module_id" = "module_ids",
  "target_date" = "target_date",
  "project_id" = "project_id",
  "created_by" = "created_by",
  // jira-parity (work item types)
  "type_id" = "type_id",
}

export enum EIssueCommentAccessSpecifier {
  EXTERNAL = "EXTERNAL",
  INTERNAL = "INTERNAL",
}

export enum EIssueListRow {
  HEADER = "HEADER",
  ISSUE = "ISSUE",
  NO_ISSUES = "NO_ISSUES",
  QUICK_ADD = "QUICK_ADD",
}

// Jira-parity: ordered most -> least important (drives select order, group-by columns and client sorting).
// `i18n_label` is the translated label (jp-priorities namespace); `title` is the English fallback.
export const ISSUE_PRIORITIES: {
  key: TIssuePriorities;
  title: string;
  i18n_label: string;
}[] = [
  {
    key: "highest",
    title: "Highest",
    i18n_label: "jp_priorities.highest",
  },
  {
    key: "high",
    title: "High",
    i18n_label: "jp_priorities.high",
  },
  {
    key: "medium",
    title: "Medium",
    i18n_label: "jp_priorities.medium",
  },
  {
    key: "low",
    title: "Low",
    i18n_label: "jp_priorities.low",
  },
  {
    key: "lowest",
    title: "Lowest",
    i18n_label: "jp_priorities.lowest",
  },
];

export const DRAG_ALLOWED_GROUPS: TIssueGroupByOptions[] = [
  "state",
  "priority",
  "assignees",
  "labels",
  "module",
  "cycle",
];

export type TCreateModalStoreTypes =
  | EIssuesStoreType.TEAM
  | EIssuesStoreType.PROJECT
  | EIssuesStoreType.TEAM_VIEW
  | EIssuesStoreType.PROJECT_VIEW
  | EIssuesStoreType.PROFILE
  | EIssuesStoreType.CYCLE
  | EIssuesStoreType.MODULE
  | EIssuesStoreType.EPIC
  | EIssuesStoreType.TEAM_PROJECT_WORK_ITEMS;

export const ISSUE_GROUP_BY_OPTIONS: {
  key: TIssueGroupByOptions;
  titleTranslationKey: string;
}[] = [
  { key: "state", titleTranslationKey: "common.states" },
  { key: "state_detail.group", titleTranslationKey: "common.state_groups" },
  { key: "priority", titleTranslationKey: "common.priority" },
  { key: "team_project", titleTranslationKey: "common.team_project" }, // required this on team issues
  { key: "project", titleTranslationKey: "common.project" }, // required this on my issues
  { key: "cycle", titleTranslationKey: "common.cycle" }, // required this on my issues
  { key: "module", titleTranslationKey: "common.module" }, // required this on my issues
  { key: "labels", titleTranslationKey: "common.labels" },
  { key: "assignees", titleTranslationKey: "common.assignees" },
  { key: "created_by", titleTranslationKey: "common.created_by" },
  // jira-parity (work item types)
  { key: "issue_type", titleTranslationKey: "jp_work_item_types.group_by" },
  { key: null, titleTranslationKey: "common.none" },
];

export const ISSUE_ORDER_BY_OPTIONS: {
  key: TIssueOrderByOptions;
  titleTranslationKey: string;
}[] = [
  { key: "sort_order", titleTranslationKey: "common.order_by.manual" },
  { key: "-created_at", titleTranslationKey: "common.order_by.last_created" },
  { key: "-updated_at", titleTranslationKey: "common.order_by.last_updated" },
  { key: "start_date", titleTranslationKey: "common.order_by.start_date" },
  { key: "target_date", titleTranslationKey: "common.order_by.due_date" },
  { key: "-priority", titleTranslationKey: "common.priority" },
];

export const ISSUE_DISPLAY_PROPERTIES_KEYS: (keyof IIssueDisplayProperties)[] = [
  "assignee",
  "start_date",
  "due_date",
  "labels",
  "key",
  "priority",
  "state",
  "sub_issue_count",
  "link",
  "attachment_count",
  "estimate",
  "created_on",
  "updated_on",
  "modules",
  "cycle",
  "issue_type",
  // jira-parity (time tracking)
  "original_estimate",
  "remaining_estimate",
];

export const SUB_ISSUES_DISPLAY_PROPERTIES_KEYS: (keyof IIssueDisplayProperties)[] = [
  "key",
  "assignee",
  "start_date",
  "due_date",
  "priority",
  "state",
];

export const ISSUE_DISPLAY_PROPERTIES: {
  key: keyof IIssueDisplayProperties;
  titleTranslationKey: string;
}[] = [
  {
    key: "key",
    titleTranslationKey: "issue.display.properties.id",
  },
  {
    key: "assignee",
    titleTranslationKey: "common.assignee",
  },
  {
    key: "start_date",
    titleTranslationKey: "common.order_by.start_date",
  },
  {
    key: "due_date",
    titleTranslationKey: "common.order_by.due_date",
  },
  { key: "labels", titleTranslationKey: "common.labels" },
  {
    key: "priority",
    titleTranslationKey: "common.priority",
  },
  { key: "state", titleTranslationKey: "common.state" },
  {
    key: "sub_issue_count",
    titleTranslationKey: "issue.display.properties.sub_issue_count",
  },
  {
    key: "attachment_count",
    titleTranslationKey: "issue.display.properties.attachment_count",
  },
  { key: "link", titleTranslationKey: "common.link" },
  {
    key: "estimate",
    titleTranslationKey: "common.estimate",
  },
  { key: "modules", titleTranslationKey: "common.module" },
  { key: "cycle", titleTranslationKey: "common.cycle" },
  // jira-parity
  { key: "issue_type", titleTranslationKey: "jp_work_item_types.display_property" },
  { key: "original_estimate", titleTranslationKey: "jp_time_tracking.original_estimate" },
  { key: "remaining_estimate", titleTranslationKey: "jp_time_tracking.remaining_estimate" },
];

export const SPREADSHEET_PROPERTY_LIST: (keyof IIssueDisplayProperties)[] = [
  // jira-parity
  "issue_type",
  "state",
  "priority",
  "assignee",
  "labels",
  "modules",
  "cycle",
  "start_date",
  "due_date",
  "estimate",
  // jira-parity (time tracking)
  "original_estimate",
  "remaining_estimate",
  "created_on",
  "updated_on",
  "link",
  "attachment_count",
  "sub_issue_count",
];

export const SPREADSHEET_PROPERTY_DETAILS: {
  [key in keyof IIssueDisplayProperties]: {
    i18n_title: string;
    ascendingOrderKey: TIssueOrderByOptions;
    ascendingOrderTitle: string;
    descendingOrderKey: TIssueOrderByOptions;
    descendingOrderTitle: string;
    icon: string;
  };
} = {
  assignee: {
    i18n_title: "common.assignees",
    ascendingOrderKey: "assignees__first_name",
    ascendingOrderTitle: "A",
    descendingOrderKey: "-assignees__first_name",
    descendingOrderTitle: "Z",
    icon: "MembersPropertyIcon",
  },
  created_on: {
    i18n_title: "common.sort.created_on",
    ascendingOrderKey: "-created_at",
    ascendingOrderTitle: "New",
    descendingOrderKey: "created_at",
    descendingOrderTitle: "Old",
    icon: "CalendarDays",
  },
  due_date: {
    i18n_title: "common.order_by.due_date",
    ascendingOrderKey: "-target_date",
    ascendingOrderTitle: "New",
    descendingOrderKey: "target_date",
    descendingOrderTitle: "Old",
    icon: "DueDatePropertyIcon",
  },
  estimate: {
    i18n_title: "common.estimate",
    ascendingOrderKey: "estimate_point__key",
    ascendingOrderTitle: "Low",
    descendingOrderKey: "-estimate_point__key",
    descendingOrderTitle: "High",
    icon: "EstimatePropertyIcon",
  },
  labels: {
    i18n_title: "common.labels",
    ascendingOrderKey: "labels__name",
    ascendingOrderTitle: "A",
    descendingOrderKey: "-labels__name",
    descendingOrderTitle: "Z",
    icon: "LabelPropertyIcon",
  },
  modules: {
    i18n_title: "common.modules",
    ascendingOrderKey: "issue_module__module__name",
    ascendingOrderTitle: "A",
    descendingOrderKey: "-issue_module__module__name",
    descendingOrderTitle: "Z",
    icon: "DiceIcon",
  },
  cycle: {
    i18n_title: "common.cycle",
    ascendingOrderKey: "issue_cycle__cycle__name",
    ascendingOrderTitle: "A",
    descendingOrderKey: "-issue_cycle__cycle__name",
    descendingOrderTitle: "Z",
    icon: "ContrastIcon",
  },
  priority: {
    i18n_title: "common.priority",
    ascendingOrderKey: "priority",
    ascendingOrderTitle: "Lowest",
    descendingOrderKey: "-priority",
    descendingOrderTitle: "Highest",
    icon: "PriorityPropertyIcon",
  },
  start_date: {
    i18n_title: "common.order_by.start_date",
    ascendingOrderKey: "-start_date",
    ascendingOrderTitle: "New",
    descendingOrderKey: "start_date",
    descendingOrderTitle: "Old",
    icon: "StartDatePropertyIcon",
  },
  state: {
    i18n_title: "common.state",
    ascendingOrderKey: "state__name",
    ascendingOrderTitle: "A",
    descendingOrderKey: "-state__name",
    descendingOrderTitle: "Z",
    icon: "StatePropertyIcon",
  },
  updated_on: {
    i18n_title: "common.sort.updated_on",
    ascendingOrderKey: "-updated_at",
    ascendingOrderTitle: "New",
    descendingOrderKey: "updated_at",
    descendingOrderTitle: "Old",
    icon: "CalendarDays",
  },
  link: {
    i18n_title: "common.link",
    ascendingOrderKey: "-link_count",
    ascendingOrderTitle: "Most",
    descendingOrderKey: "link_count",
    descendingOrderTitle: "Least",
    icon: "Link2",
  },
  attachment_count: {
    i18n_title: "common.attachment",
    ascendingOrderKey: "-attachment_count",
    ascendingOrderTitle: "Most",
    descendingOrderKey: "attachment_count",
    descendingOrderTitle: "Least",
    icon: "Paperclip",
  },
  sub_issue_count: {
    i18n_title: "issue.display.properties.sub_issue",
    ascendingOrderKey: "-sub_issues_count",
    ascendingOrderTitle: "Most",
    descendingOrderKey: "sub_issues_count",
    descendingOrderTitle: "Least",
    icon: "LayersIcon",
  },
  // jira-parity
  issue_type: {
    i18n_title: "jp_work_item_types.spreadsheet_column",
    ascendingOrderKey: "type__name",
    ascendingOrderTitle: "A",
    descendingOrderKey: "-type__name",
    descendingOrderTitle: "Z",
    icon: "WorkItemsOutline",
  },
  original_estimate: {
    i18n_title: "jp_time_tracking.original_estimate",
    ascendingOrderKey: "original_estimate",
    ascendingOrderTitle: "Low",
    descendingOrderKey: "-original_estimate",
    descendingOrderTitle: "High",
    icon: "EstimateOutline",
  },
  remaining_estimate: {
    i18n_title: "jp_time_tracking.remaining_estimate",
    ascendingOrderKey: "remaining_estimate",
    ascendingOrderTitle: "Low",
    descendingOrderKey: "-remaining_estimate",
    descendingOrderTitle: "High",
    icon: "EstimateOutline",
  },
};

// Map filter keys to their corresponding issue property keys
export const FILTER_TO_ISSUE_MAP: Partial<Record<keyof IIssueFilterOptions, keyof TIssue>> = {
  assignees: "assignee_ids",
  created_by: "created_by",
  labels: "label_ids",
  priority: "priority",
  cycle: "cycle_id",
  module: "module_ids",
  project: "project_id",
  state: "state_id",
  issue_type: "type_id",
  state_group: "state__group",
} as const;
