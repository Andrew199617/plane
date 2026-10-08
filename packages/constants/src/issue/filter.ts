/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type {
  IIssueFilterOptions,
  ILayoutDisplayFiltersOptions,
  TIssueActivityComment,
  TWorkItemFilterProperty,
} from "@plane/types";
import { EIssuesStoreType } from "@plane/types";
import type { TIssueFilterPriorityObject } from "./common";
import { ISSUE_DISPLAY_PROPERTIES_KEYS, SUB_ISSUES_DISPLAY_PROPERTIES_KEYS } from "./common";

import type { TIssueLayout } from "./layout";

export type TIssueFilterKeys = "priority" | "state" | "labels";

export enum EServerGroupByToFilterOptions {
  "state_id" = "state",
  "priority" = "priority",
  "labels__id" = "labels",
  "state__group" = "state_group",
  "assignees__id" = "assignees",
  "cycle_id" = "cycle",
  "issue_module__module_id" = "module",
  "target_date" = "target_date",
  "project_id" = "project",
  "created_by" = "created_by",
  // jira-parity (work item types): legacy `issue_type` param when paging a single type group
  "type_id" = "issue_type",
}

export enum EIssueFilterType {
  FILTERS = "rich_filters",
  DISPLAY_FILTERS = "display_filters",
  DISPLAY_PROPERTIES = "display_properties",
  KANBAN_FILTERS = "kanban_filters",
}

export type TSupportedFilterTypeForUpdate =
  | EIssueFilterType.DISPLAY_FILTERS
  | EIssueFilterType.DISPLAY_PROPERTIES
  | EIssueFilterType.KANBAN_FILTERS;

export const ISSUE_DISPLAY_FILTERS_BY_LAYOUT: {
  [key in TIssueLayout]: Record<"filters", TIssueFilterKeys[]>;
} = {
  list: {
    filters: ["priority", "state", "labels"],
  },
  kanban: {
    filters: ["priority", "state", "labels"],
  },
  calendar: {
    filters: ["priority", "state", "labels"],
  },
  spreadsheet: {
    filters: ["priority", "state", "labels"],
  },
  gantt: {
    filters: ["priority", "state", "labels"],
  },
};

// Jira-parity priorities (class names stay full literals so Tailwind can see them)
export const ISSUE_PRIORITY_FILTERS: TIssueFilterPriorityObject[] = [
  {
    key: "highest",
    titleTranslationKey: "jp_priorities.highest",
    className: "bg-layer-2 text-priority-highest border-strong",
    icon: "keyboard_double_arrow_up",
  },
  {
    key: "high",
    titleTranslationKey: "jp_priorities.high",
    className: "bg-layer-2 text-priority-high border-strong",
    icon: "keyboard_arrow_up",
  },
  {
    key: "medium",
    titleTranslationKey: "jp_priorities.medium",
    className: "bg-layer-2 text-priority-medium border-strong",
    icon: "drag_handle",
  },
  {
    key: "low",
    titleTranslationKey: "jp_priorities.low",
    className: "bg-layer-2 text-priority-low border-strong",
    icon: "keyboard_arrow_down",
  },
  {
    key: "lowest",
    titleTranslationKey: "jp_priorities.lowest",
    className: "bg-layer-2 text-priority-lowest border-strong",
    icon: "keyboard_double_arrow_down",
  },
];

export type TFiltersLayoutOptions = {
  [layoutType: string]: ILayoutDisplayFiltersOptions;
};

export type TFilterPropertiesByPageType = {
  filters: TWorkItemFilterProperty[];
  layoutOptions: TFiltersLayoutOptions;
};

export type TIssueFiltersToDisplayByPageType = {
  [pageType: string]: TFilterPropertiesByPageType;
};

export const ISSUE_DISPLAY_FILTERS_BY_PAGE: TIssueFiltersToDisplayByPageType = {
  profile_issues: {
    filters: ["priority", "state_group", "label_id", "start_date", "target_date", "type_id"],
    layoutOptions: {
      list: {
        display_properties: ISSUE_DISPLAY_PROPERTIES_KEYS,
        display_filters: {
          group_by: ["state_detail.group", "priority", "project", "labels", null],
          order_by: ["sort_order", "-created_at", "-updated_at", "start_date", "-priority"],
          type: ["active", "backlog"],
        },
        extra_options: {
          access: true,
          values: ["show_empty_groups", "sub_issue"],
        },
      },
      kanban: {
        display_properties: ISSUE_DISPLAY_PROPERTIES_KEYS,
        display_filters: {
          group_by: ["state_detail.group", "priority", "project", "labels"],
          order_by: ["sort_order", "-created_at", "-updated_at", "start_date", "-priority"],
          type: ["active", "backlog"],
        },
        extra_options: {
          access: true,
          values: ["show_empty_groups"],
        },
      },
    },
  },
  archived_issues: {
    filters: [
      "priority",
      "state_group",
      "state_id",
      "cycle_id",
      "module_id",
      "assignee_id",
      "created_by_id",
      "label_id",
      "start_date",
      "target_date",
      "type_id",
    ],
    layoutOptions: {
      list: {
        display_properties: ISSUE_DISPLAY_PROPERTIES_KEYS,
        display_filters: {
          group_by: ["state", "cycle", "module", "priority", "labels", "assignees", "created_by", null],
          order_by: ["sort_order", "-created_at", "-updated_at", "start_date", "-priority"],
          type: ["active", "backlog"],
        },
        extra_options: {
          access: true,
          values: ["show_empty_groups"],
        },
      },
    },
  },
  my_issues: {
    filters: [
      "priority",
      "state_group",
      "label_id",
      "assignee_id",
      "created_by_id",
      "subscriber_id",
      "project_id",
      "start_date",
      "target_date",
      "type_id",
    ],
    layoutOptions: {
      spreadsheet: {
        display_properties: ISSUE_DISPLAY_PROPERTIES_KEYS,
        display_filters: {
          order_by: [],
          type: ["active", "backlog"],
        },
        extra_options: {
          access: true,
          values: ["sub_issue"],
        },
      },
      list: {
        display_properties: ISSUE_DISPLAY_PROPERTIES_KEYS,
        display_filters: {
          type: ["active", "backlog"],
        },
        extra_options: {
          access: false,
          values: [],
        },
      },
    },
  },
  issues: {
    filters: [
      "priority",
      "state_group",
      "state_id",
      "cycle_id",
      "module_id",
      "assignee_id",
      "mention_id",
      "created_by_id",
      "label_id",
      "start_date",
      "target_date",
      "type_id",
    ],
    layoutOptions: {
      list: {
        display_properties: ISSUE_DISPLAY_PROPERTIES_KEYS,
        display_filters: {
          // jira-parity: "issue_type" (group by work item type)
          group_by: ["state", "issue_type", "priority", "cycle", "module", "labels", "assignees", "created_by", null],
          order_by: ["sort_order", "-created_at", "-updated_at", "start_date", "-priority", "target_date"],
          type: ["active", "backlog"],
        },
        extra_options: {
          access: true,
          values: ["show_empty_groups", "sub_issue"],
        },
      },
      kanban: {
        display_properties: ISSUE_DISPLAY_PROPERTIES_KEYS,
        display_filters: {
          // jira-parity: "issue_type" (group by work item type)
          group_by: ["state", "issue_type", "priority", "cycle", "module", "labels", "assignees", "created_by"],
          sub_group_by: [
            "state",
            "issue_type",
            "priority",
            "cycle",
            "module",
            "labels",
            "assignees",
            "created_by",
            null,
          ],
          order_by: ["sort_order", "-created_at", "-updated_at", "start_date", "-priority", "target_date"],
          type: ["active", "backlog"],
        },
        extra_options: {
          access: true,
          values: ["show_empty_groups", "sub_issue"],
        },
      },
      calendar: {
        display_properties: ["key", "issue_type"],
        display_filters: {
          type: ["active", "backlog"],
        },
        extra_options: {
          access: true,
          values: ["sub_issue"],
        },
      },
      spreadsheet: {
        display_properties: ISSUE_DISPLAY_PROPERTIES_KEYS,
        display_filters: {
          order_by: ["sort_order", "-created_at", "-updated_at", "start_date", "-priority"],
          type: ["active", "backlog"],
        },
        extra_options: {
          access: true,
          values: ["sub_issue"],
        },
      },
      gantt_chart: {
        display_properties: ["key", "issue_type"],
        display_filters: {
          order_by: ["sort_order", "-created_at", "-updated_at", "start_date", "-priority"],
          type: ["active", "backlog"],
        },
        extra_options: {
          access: true,
          values: ["sub_issue"],
        },
      },
    },
  },
  sub_work_items: {
    filters: ["priority", "state_id", "assignee_id", "start_date", "target_date", "type_id"],
    layoutOptions: {
      list: {
        display_properties: SUB_ISSUES_DISPLAY_PROPERTIES_KEYS,
        display_filters: {
          order_by: ["-created_at", "-updated_at", "start_date", "-priority"],
          group_by: ["state", "priority", "assignees", null],
        },
        extra_options: {
          access: true,
          values: ["sub_issue"],
        },
      },
    },
  },
};

export const ISSUE_STORE_TO_FILTERS_MAP: Partial<Record<EIssuesStoreType, TFilterPropertiesByPageType>> = {
  [EIssuesStoreType.PROJECT]: ISSUE_DISPLAY_FILTERS_BY_PAGE.issues,
};

export const SUB_WORK_ITEM_AVAILABLE_FILTERS_FOR_WORK_ITEM_PAGE: (keyof IIssueFilterOptions)[] = [
  "priority",
  "state",
  "issue_type",
  "assignees",
  "start_date",
  "target_date",
];

export enum EActivityFilterType {
  ACTIVITY = "ACTIVITY",
  COMMENT = "COMMENT",
  STATE = "STATE",
  ASSIGNEE = "ASSIGNEE",
  DEFAULT = "DEFAULT",
}

export type TActivityFilters = EActivityFilterType;

export type TActivityFilterOptionsKey = Exclude<TActivityFilters, EActivityFilterType.DEFAULT>;

export const ACTIVITY_FILTER_TYPE_OPTIONS: Record<TActivityFilterOptionsKey, { labelTranslationKey: string }> = {
  [EActivityFilterType.ACTIVITY]: {
    labelTranslationKey: "common.updates",
  },
  [EActivityFilterType.COMMENT]: {
    labelTranslationKey: "common.comments",
  },
  [EActivityFilterType.STATE]: {
    labelTranslationKey: "common.state",
  },
  [EActivityFilterType.ASSIGNEE]: {
    labelTranslationKey: "common.assignee",
  },
};

export type TActivityFilterOption = {
  key: TActivityFilters;
  labelTranslationKey: string;
  isSelected: boolean;
  onClick: () => void;
};

export const defaultActivityFilters: TActivityFilters[] = [
  EActivityFilterType.ACTIVITY,
  EActivityFilterType.COMMENT,
  EActivityFilterType.STATE,
  EActivityFilterType.ASSIGNEE,
];

export const filterActivityOnSelectedFilters = (
  activity: TIssueActivityComment[],
  filters: TActivityFilters[]
): TIssueActivityComment[] =>
  activity.filter((item) => {
    if (item.activity_type === EActivityFilterType.DEFAULT) return true;
    return filters.includes(item.activity_type as TActivityFilters);
  });

export const ENABLE_ISSUE_DEPENDENCIES = false;

export const BASE_ACTIVITY_FILTER_TYPES = [
  EActivityFilterType.ACTIVITY,
  EActivityFilterType.STATE,
  EActivityFilterType.ASSIGNEE,
  EActivityFilterType.DEFAULT,
];
