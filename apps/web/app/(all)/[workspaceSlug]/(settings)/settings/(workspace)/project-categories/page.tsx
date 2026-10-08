/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: workspace settings page (owned by the project-categories feature). Access is gated by
// WORKSPACE_SETTINGS["project-categories"].access in the (workspace) settings layout.
import { observer } from "mobx-react";
// plane imports
import { useTranslation } from "@plane/i18n";
// components
import { PageHead } from "@/components/core/page-title";
import { ProjectCategoriesSettingsRoot } from "@/components/jira-parity/project-categories";
import { SettingsContentWrapper } from "@/components/settings/content-wrapper";
import { SettingsHeading } from "@/components/settings/heading";
// hooks
import { useWorkspace } from "@/hooks/store/use-workspace";
// local imports
import type { Route } from "./+types/page";
import { ProjectCategoriesWorkspaceSettingsHeader } from "./header";

function ProjectCategoriesSettingsPage({ params }: Route.ComponentProps) {
  const { workspaceSlug } = params;
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const { currentWorkspace } = useWorkspace();
  // derived values
  const pageTitle = currentWorkspace?.name
    ? `${currentWorkspace.name} - ${t("jp_categories.settings.title")}`
    : undefined;

  return (
    <SettingsContentWrapper header={<ProjectCategoriesWorkspaceSettingsHeader />}>
      <PageHead title={pageTitle} />
      <div className="w-full">
        <SettingsHeading
          title={t("jp_categories.settings.heading")}
          description={t("jp_categories.settings.description")}
        />
        <div className="mt-6">
          <ProjectCategoriesSettingsRoot workspaceSlug={workspaceSlug} />
        </div>
      </div>
    </SettingsContentWrapper>
  );
}

export default observer(ProjectCategoriesSettingsPage);
