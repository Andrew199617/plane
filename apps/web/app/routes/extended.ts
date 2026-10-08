/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { RouteConfigEntry } from "@react-router/dev/routes";
import { mergeRoutes } from "./helper";
// jira-parity feature routes (each file is owned by its feature)
import { projectCategoriesRoutes } from "./extended/project-categories";
import { workItemTypesRoutes } from "./extended/work-item-types";

const JIRA_PARITY_ROUTES: RouteConfigEntry[][] = [workItemTypesRoutes, projectCategoriesRoutes];

export const extendedRoutes: RouteConfigEntry[] = JIRA_PARITY_ROUTES.reduce<RouteConfigEntry[]>(
  (mergedRoutes, featureRoutes) => mergeRoutes(mergedRoutes, featureRoutes),
  []
);
