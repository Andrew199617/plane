/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: workspace settings page (owned by the work-item-types feature). Access is gated by
// WORKSPACE_SETTINGS["work-item-types"].access in the (workspace) settings layout.
import { observer } from "mobx-react";
// plane imports
import { useTranslation } from "@plane/i18n";
// components
import { PageHead } from "@/components/core/page-title";
import { WorkItemTypesSettingsRoot } from "@/components/jira-parity/work-item-types";
import { SettingsContentWrapper } from "@/components/settings/content-wrapper";
import { SettingsHeading } from "@/components/settings/heading";
// hooks
import { useWorkspace } from "@/hooks/store/use-workspace";
// local imports
import type { Route } from "./+types/page";
import { WorkItemTypesWorkspaceSettingsHeader } from "./header";

function WorkItemTypesSettingsPage({ params }: Route.ComponentProps) {
  const { workspaceSlug } = params;
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const { currentWorkspace } = useWorkspace();
  // derived values
  const pageTitle = currentWorkspace?.name
    ? `${currentWorkspace.name} - ${t("jp_work_item_types.settings.title")}`
    : undefined;

  return (
    <SettingsContentWrapper header={<WorkItemTypesWorkspaceSettingsHeader />}>
      <PageHead title={pageTitle} />
      <div className="w-full">
        <SettingsHeading
          title={t("jp_work_item_types.settings.heading")}
          description={t("jp_work_item_types.settings.description")}
        />
        <div className="mt-6">
          <WorkItemTypesSettingsRoot workspaceSlug={workspaceSlug} />
        </div>
      </div>
    </SettingsContentWrapper>
  );
}

export default observer(WorkItemTypesSettingsPage);
