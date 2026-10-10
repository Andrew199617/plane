/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { RouteConfigEntry } from "@react-router/dev/routes";
import { mergeRoutes } from "./helper";
// jira-parity feature routes (each file is owned by its feature)
import { agentsRoutes } from "./extended/agents";
import { projectCategoriesRoutes } from "./extended/project-categories";
import { teamsRoutes } from "./extended/teams";
import { workItemTypesRoutes } from "./extended/work-item-types";
import { workflowsRoutes } from "./extended/workflows";

const JIRA_PARITY_ROUTES: RouteConfigEntry[][] = [
  workItemTypesRoutes,
  agentsRoutes,
  workflowsRoutes,
  teamsRoutes,
  projectCategoriesRoutes,
];

export const extendedRoutes: RouteConfigEntry[] = JIRA_PARITY_ROUTES.reduce<RouteConfigEntry[]>(
  (mergedRoutes, featureRoutes) => mergeRoutes(mergedRoutes, featureRoutes),
  []
);
