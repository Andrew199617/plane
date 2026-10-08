/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// plane imports
import type { TWorkspaceSettingsItem, TWorkspaceSettingsTabs } from "@plane/types";
import { EUserWorkspaceRoles } from "@plane/types";
// jira-parity
import { JP_HIDE_UPSELL } from "../jira-parity/common";

export enum WORKSPACE_SETTINGS_CATEGORY {
  ADMINISTRATION = "administration",
  FEATURES = "features",
  DEVELOPER = "developer",
}

export const WORKSPACE_SETTINGS_CATEGORIES: WORKSPACE_SETTINGS_CATEGORY[] = [
  WORKSPACE_SETTINGS_CATEGORY.ADMINISTRATION,
  WORKSPACE_SETTINGS_CATEGORY.FEATURES,
  WORKSPACE_SETTINGS_CATEGORY.DEVELOPER,
];

export const WORKSPACE_SETTINGS_CATEGORY_LABELS: Record<WORKSPACE_SETTINGS_CATEGORY, string> = {
  [WORKSPACE_SETTINGS_CATEGORY.ADMINISTRATION]: "common.administration",
  [WORKSPACE_SETTINGS_CATEGORY.FEATURES]: "common.features",
  [WORKSPACE_SETTINGS_CATEGORY.DEVELOPER]: "common.developer",
};

export const WORKSPACE_SETTINGS: Record<TWorkspaceSettingsTabs, TWorkspaceSettingsItem> = {
  general: {
    key: "general",
    i18n_label: "workspace_settings.settings.general.title",
    href: `/settings`,
    access: [EUserWorkspaceRoles.ADMIN, EUserWorkspaceRoles.MEMBER],
    highlight: (pathname: string, baseUrl: string) => pathname === `${baseUrl}/settings/`,
  },
  members: {
    key: "members",
    i18n_label: "workspace_settings.settings.members.title",
    href: `/settings/members`,
    access: [EUserWorkspaceRoles.ADMIN, EUserWorkspaceRoles.MEMBER],
    highlight: (pathname: string, baseUrl: string) => pathname === `${baseUrl}/settings/members/`,
  },
  "billing-and-plans": {
    key: "billing-and-plans",
    i18n_label: "workspace_settings.settings.billing_and_plans.title",
    href: `/settings/billing`,
    access: [EUserWorkspaceRoles.ADMIN],
    highlight: (pathname: string, baseUrl: string) => pathname === `${baseUrl}/settings/billing/`,
  },
  export: {
    key: "export",
    i18n_label: "workspace_settings.settings.exports.title",
    href: `/settings/exports`,
    access: [EUserWorkspaceRoles.ADMIN, EUserWorkspaceRoles.MEMBER],
    highlight: (pathname: string, baseUrl: string) => pathname === `${baseUrl}/settings/exports/`,
  },
  webhooks: {
    key: "webhooks",
    i18n_label: "workspace_settings.settings.webhooks.title",
    href: `/settings/webhooks`,
    access: [EUserWorkspaceRoles.ADMIN],
    highlight: (pathname: string, baseUrl: string) => pathname === `${baseUrl}/settings/webhooks/`,
  },
  // jira-parity
  "work-item-types": {
    key: "work-item-types",
    i18n_label: "jp_work_item_types.settings.title",
    href: `/settings/work-item-types`,
    access: [EUserWorkspaceRoles.ADMIN],
    highlight: (pathname: string, baseUrl: string) => pathname === `${baseUrl}/settings/work-item-types/`,
  },
  agents: {
    key: "agents",
    i18n_label: "jp_agents.settings.title",
    href: `/settings/agents`,
    access: [EUserWorkspaceRoles.ADMIN],
    highlight: (pathname: string, baseUrl: string) => pathname === `${baseUrl}/settings/agents/`,
  },
  teams: {
    key: "teams",
    i18n_label: "jp_teams.settings.title",
    href: `/settings/teams`,
    access: [EUserWorkspaceRoles.ADMIN, EUserWorkspaceRoles.MEMBER],
    highlight: (pathname: string, baseUrl: string) => pathname === `${baseUrl}/settings/teams/`,
  },
  "project-categories": {
    key: "project-categories",
    i18n_label: "jp_categories.settings.title",
    href: `/settings/project-categories`,
    access: [EUserWorkspaceRoles.ADMIN],
    highlight: (pathname: string, baseUrl: string) => pathname === `${baseUrl}/settings/project-categories/`,
  },
};

export const WORKSPACE_SETTINGS_ACCESS = Object.fromEntries(
  Object.entries(WORKSPACE_SETTINGS).map(([_, { href, access }]) => [href, access])
);

export const GROUPED_WORKSPACE_SETTINGS: Record<WORKSPACE_SETTINGS_CATEGORY, TWorkspaceSettingsItem[]> = {
  [WORKSPACE_SETTINGS_CATEGORY.ADMINISTRATION]: [
    WORKSPACE_SETTINGS["general"],
    WORKSPACE_SETTINGS["members"],
    // jira-parity
    WORKSPACE_SETTINGS["agents"],
    WORKSPACE_SETTINGS["teams"],
    ...(JP_HIDE_UPSELL ? [] : [WORKSPACE_SETTINGS["billing-and-plans"]]),
    WORKSPACE_SETTINGS["export"],
  ],
  [WORKSPACE_SETTINGS_CATEGORY.FEATURES]: [
    // jira-parity
    WORKSPACE_SETTINGS["work-item-types"],
    WORKSPACE_SETTINGS["project-categories"],
  ],
  [WORKSPACE_SETTINGS_CATEGORY.DEVELOPER]: [WORKSPACE_SETTINGS["webhooks"]],
};
