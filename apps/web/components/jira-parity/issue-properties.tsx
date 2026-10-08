/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity issue property slot (scaffold-owned). Rendered by
// components/issues/issue-detail/sidebar.tsx and components/issues/peek-overview/properties.tsx
// right after the Assignees row. Each child is owned by its feature.
import { observer } from "mobx-react";
// local imports
import { TimeTrackingIssueProperties } from "./time-tracking/issue-properties";
import type { TJiraParityIssuePropertyProps } from "./types";

export const JiraParityIssueProperties = observer(function JiraParityIssueProperties(
  props: TJiraParityIssuePropertyProps
) {
  return (
    <>
      <TimeTrackingIssueProperties {...props} />
    </>
  );
});
