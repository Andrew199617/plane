/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity data loaders (scaffold-owned). They render nothing and only call each feature's
// bootstrap hooks (components/jira-parity/<feature>/bootstrap.ts), which are owned by the features.
import { observer } from "mobx-react";
// local imports
import { usePrioritiesProjectBootstrap, usePrioritiesWorkspaceBootstrap } from "./priorities/bootstrap";
import { useTimeTrackingProjectBootstrap, useTimeTrackingWorkspaceBootstrap } from "./time-tracking/bootstrap";

type TJiraParityWorkspaceDataLoaderProps = {
  workspaceSlug: string;
};

/** Mounted once in layouts/auth-layout/workspace-wrapper.tsx after the workspace is loaded. */
export const JiraParityWorkspaceDataLoader = observer(function JiraParityWorkspaceDataLoader(
  props: TJiraParityWorkspaceDataLoaderProps
) {
  const { workspaceSlug } = props;

  useTimeTrackingWorkspaceBootstrap(workspaceSlug);
  usePrioritiesWorkspaceBootstrap(workspaceSlug);

  return null;
});

type TJiraParityProjectDataLoaderProps = {
  workspaceSlug: string;
  projectId: string;
};

/** Mounted once in layouts/auth-layout/project-wrapper.tsx when the project is accessible. */
export const JiraParityProjectDataLoader = observer(function JiraParityProjectDataLoader(
  props: TJiraParityProjectDataLoaderProps
) {
  const { workspaceSlug, projectId } = props;

  useTimeTrackingProjectBootstrap(workspaceSlug, projectId);
  usePrioritiesProjectBootstrap(workspaceSlug, projectId);

  return null;
});
