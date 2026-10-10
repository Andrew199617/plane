/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: workspace settings page (owned by the teams feature). Access is gated by
// WORKSPACE_SETTINGS["teams"].access in the (workspace) settings layout.
import { observer } from "mobx-react";
// plane imports
import { useTranslation } from "@plane/i18n";
// components
import { PageHead } from "@/components/core/page-title";
import { TeamsSettingsRoot } from "@/components/jira-parity/teams";
import { SettingsContentWrapper } from "@/components/settings/content-wrapper";
import { SettingsHeading } from "@/components/settings/heading";
// hooks
import { useWorkspace } from "@/hooks/store/use-workspace";
// local imports
import type { Route } from "./+types/page";
import { TeamsWorkspaceSettingsHeader } from "./header";

function TeamsSettingsPage({ params }: Route.ComponentProps) {
  const { workspaceSlug } = params;
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const { currentWorkspace } = useWorkspace();
  // derived values
  const pageTitle = currentWorkspace?.name ? `${currentWorkspace.name} - ${t("jp_teams.settings.title")}` : undefined;

  return (
    <SettingsContentWrapper header={<TeamsWorkspaceSettingsHeader />}>
      <PageHead title={pageTitle} />
      <div className="w-full">
        <SettingsHeading title={t("jp_teams.settings.heading")} description={t("jp_teams.settings.description")} />
        <div className="mt-6">
          <TeamsSettingsRoot workspaceSlug={workspaceSlug} />
        </div>
      </div>
    </SettingsContentWrapper>
  );
}

export default observer(TeamsSettingsPage);
