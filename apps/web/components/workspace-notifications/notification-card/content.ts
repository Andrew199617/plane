/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { replaceUnderscoreIfSnakeCase } from "@plane/utils";
import type {
  TNotificationContentHandler,
  TNotificationContentMap,
} from "@/components/workspace-notifications/sidebar/notification-card/content";
// jira-parity: estimate fields render as Jira durations ("1w 2d") instead of raw minutes
import { JP_TIME_TRACKING_NOTIFICATION_CONTENT_MAP } from "@/components/jira-parity/time-tracking/notification-content";

// jira-parity: cycles / modules are labelled Sprint / Release; describe the change instead of the raw field key
const sprintReleaseContent =
  (label: string): TNotificationContentHandler =>
  ({ verb }) => {
    if (verb === "updated") return { action: `set the ${label}`, showConnector: true };
    if (verb === "deleted") return { action: `removed this work item from the ${label}`, value: null };
    return { action: `added this work item to the ${label}`, showConnector: false };
  };

// Additional notification content map for CE (empty - EE extends this)
export const ADDITIONAL_NOTIFICATION_CONTENT_MAP: TNotificationContentMap = {
  ...JP_TIME_TRACKING_NOTIFICATION_CONTENT_MAP,
  cycles: sprintReleaseContent("sprint"),
  modules: sprintReleaseContent("release"),
};

// Fallback action renderer for fields not in the map
export const renderAdditionalAction = (notificationField: string, verb: string | undefined) => {
  const baseAction = !["comment", "archived_at"].includes(notificationField) ? verb : "";
  return `${baseAction} ${replaceUnderscoreIfSnakeCase(notificationField)}`;
};

// Fallback value renderer for fields not in the map
export const renderAdditionalValue = (
  _notificationField: string | undefined,
  newValue: string | undefined,
  _oldValue: string | undefined
) => newValue;

export const shouldShowConnector = (notificationField: string | undefined) =>
  !["comment", "archived_at", "None", "assignees", "labels", "start_date", "target_date", "parent"].includes(
    notificationField || ""
  );

export const shouldRender = (notificationField: string | undefined, verb: string | undefined) => verb !== "deleted";
