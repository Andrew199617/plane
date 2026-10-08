/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity time tracking: inbox notification rendering for the original / remaining estimate activity
// fields (values are minutes stored as strings; clearing an estimate records an empty new value).
import type {
  TNotificationContentHandler,
  TNotificationContentMap,
} from "@/components/workspace-notifications/sidebar/notification-card/content";
import { formatDuration } from "./duration";

const estimateNotificationContent =
  (label: string): TNotificationContentHandler =>
  ({ newValue }) => {
    const minutes = newValue === undefined || newValue === null || newValue === "" ? null : Number(newValue);
    if (minutes === null || !Number.isFinite(minutes)) {
      return { action: `removed the ${label}`, value: null, showConnector: false };
    }
    return { action: `set the ${label}`, value: formatDuration(minutes), showConnector: true };
  };

export const JP_TIME_TRACKING_NOTIFICATION_CONTENT_MAP: TNotificationContentMap = {
  original_estimate: estimateNotificationContent("original estimate"),
  remaining_estimate: estimateNotificationContent("remaining estimate"),
};
