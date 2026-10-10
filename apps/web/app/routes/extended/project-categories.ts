/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity routes for the project-categories feature (owned by that feature). Merged into the app
// routes by app/routes/extended.ts -> mergeRoutes (layouts are deep-merged by their `file`, so the
// parent layout chain must be repeated with identical file strings).
import { layout, route } from "@react-router/dev/routes";
import type { RouteConfigEntry } from "@react-router/dev/routes";

export const projectCategoriesRoutes: RouteConfigEntry[] = [
  layout("./(all)/layout.tsx", [
    layout("./(all)/[workspaceSlug]/layout.tsx", [
      // Master boards (app shell)
      layout("./(all)/[workspaceSlug]/(projects)/layout.tsx", [
        layout("./(all)/[workspaceSlug]/(projects)/boards/[categoryId]/layout.tsx", [
          route(":workspaceSlug/boards/:categoryId", "./(all)/[workspaceSlug]/(projects)/boards/[categoryId]/page.tsx"),
        ]),
      ]),
      // Workspace settings > Project categories
      layout("./(all)/[workspaceSlug]/(settings)/layout.tsx", [
        layout("./(all)/[workspaceSlug]/(settings)/settings/(workspace)/layout.tsx", [
          route(
            ":workspaceSlug/settings/project-categories",
            "./(all)/[workspaceSlug]/(settings)/settings/(workspace)/project-categories/page.tsx"
          ),
        ]),
      ]),
    ]),
  ]),
];
