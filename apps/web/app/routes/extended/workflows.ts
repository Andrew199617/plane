/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity routes for the workflows feature (owned by that feature). Merged into the app routes by
// app/routes/extended.ts -> mergeRoutes (layouts are deep-merged by their `file`, so the parent
// layout chain must be repeated with identical file strings).
import { layout, route } from "@react-router/dev/routes";
import type { RouteConfigEntry } from "@react-router/dev/routes";

export const workflowsRoutes: RouteConfigEntry[] = [
  layout("./(all)/layout.tsx", [
    layout("./(all)/[workspaceSlug]/layout.tsx", [
      layout("./(all)/[workspaceSlug]/(settings)/layout.tsx", [
        layout("./(all)/[workspaceSlug]/(settings)/settings/projects/layout.tsx", [
          layout("./(all)/[workspaceSlug]/(settings)/settings/projects/[projectId]/layout.tsx", [
            route(
              ":workspaceSlug/settings/projects/:projectId/workflows",
              "./(all)/[workspaceSlug]/(settings)/settings/projects/[projectId]/workflows/page.tsx"
            ),
          ]),
        ]),
      ]),
    ]),
  ]),
];
