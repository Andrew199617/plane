/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity routes for the teams feature (owned by that feature). Merged into the app routes by
// app/routes/extended.ts -> mergeRoutes (layouts are deep-merged by their `file`, so the parent
// layout chain must be repeated with identical file strings).
import { layout, route } from "@react-router/dev/routes";
import type { RouteConfigEntry } from "@react-router/dev/routes";

export const teamsRoutes: RouteConfigEntry[] = [
  layout("./(all)/layout.tsx", [
    layout("./(all)/[workspaceSlug]/layout.tsx", [
      layout("./(all)/[workspaceSlug]/(settings)/layout.tsx", [
        layout("./(all)/[workspaceSlug]/(settings)/settings/(workspace)/layout.tsx", [
          route(
            ":workspaceSlug/settings/teams",
            "./(all)/[workspaceSlug]/(settings)/settings/(workspace)/teams/page.tsx"
          ),
        ]),
      ]),
    ]),
  ]),
];
