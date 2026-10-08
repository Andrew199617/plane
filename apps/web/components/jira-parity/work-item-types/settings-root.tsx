/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: workspace settings > Work item types (owned by the work-item-types feature).
// Lists the workspace types (shared by every project) and lets admins edit name, description, icon and color.
import { useState } from "react";
import { observer } from "mobx-react";
import useSWR from "swr";
// plane imports
import { Badge } from "@makeplane/propel/components/badge";
import { Button } from "@makeplane/propel/components/button";
import { Loader } from "@plane/blocks/skeleton";
import { EUserPermissions, EUserPermissionsLevel, JP_WORK_ITEM_TYPES_SWR_KEY } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import type { TWorkItemType } from "@plane/types";
// components
import { NotAuthorizedView } from "@/components/auth-screens/not-authorized-view";
// hooks
import { useWorkItemTypes } from "@/hooks/store/jira-parity/use-work-item-types";
import { useUserPermissions } from "@/hooks/store/user";
// local imports
import { WorkItemTypeIcon } from "./icons";
import { WorkItemTypeEditModal } from "./settings-edit-modal";

type TWorkItemTypesSettingsRootProps = {
  workspaceSlug: string;
};

type TWorkItemTypeRowProps = {
  workItemType: TWorkItemType;
  canEdit: boolean;
  onEdit: () => void;
};

const WorkItemTypeRow = observer(function WorkItemTypeRow(props: TWorkItemTypeRowProps) {
  const { workItemType, canEdit, onEdit } = props;
  // plane hooks
  const { t } = useTranslation();

  return (
    <div className="flex items-center gap-3 px-4 py-3" data-testid={`work-item-type-row-${workItemType.name}`}>
      <WorkItemTypeIcon workItemType={workItemType} className="size-6" />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="truncate text-body-sm-medium text-primary">{workItemType.name}</span>
          {workItemType.is_default && (
            <Badge variant="brand" size="xs" label={t("jp_work_item_types.settings.badges.default")} />
          )}
          {workItemType.is_epic && (
            <Badge variant="purple" size="xs" label={t("jp_work_item_types.settings.badges.epic")} />
          )}
          {workItemType.is_sub_task && (
            <Badge variant="info" size="xs" label={t("jp_work_item_types.settings.badges.sub_task")} />
          )}
          {!workItemType.is_active && (
            <Badge variant="neutral" size="xs" label={t("jp_work_item_types.settings.badges.inactive")} />
          )}
        </div>
        <p className="truncate text-body-xs-regular text-tertiary">
          {workItemType.description?.trim() || t("jp_work_item_types.settings.no_description")}
        </p>
      </div>
      {canEdit && (
        <Button
          variant="secondary"
          size="sm"
          stretch="auto"
          label={t("jp_work_item_types.settings.edit")}
          onClick={onEdit}
          data-testid={`work-item-type-edit-${workItemType.name}`}
        />
      )}
    </div>
  );
});

export const WorkItemTypesSettingsRoot = observer(function WorkItemTypesSettingsRoot(
  props: TWorkItemTypesSettingsRootProps
) {
  const { workspaceSlug } = props;
  // states
  const [editingTypeId, setEditingTypeId] = useState<string | null>(null);
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const { workItemTypes, fetchedWorkspaceSlug, fetchWorkItemTypes, getWorkItemTypeById } = useWorkItemTypes();
  const { workspaceUserInfo, allowPermissions } = useUserPermissions();
  // derived values
  const isAdmin = allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.WORKSPACE);
  // always refresh on open (the workspace bootstrap shares this key)
  const { error, isLoading } = useSWR(
    workspaceSlug ? JP_WORK_ITEM_TYPES_SWR_KEY(workspaceSlug) : null,
    workspaceSlug ? () => fetchWorkItemTypes(workspaceSlug) : null,
    { revalidateOnFocus: false, revalidateOnMount: true }
  );
  const isLoaded = fetchedWorkspaceSlug === workspaceSlug;

  if (workspaceUserInfo && !isAdmin) return <NotAuthorizedView section="settings" className="h-auto" />;

  if (!isLoaded && (isLoading || !error)) {
    return (
      <Loader className="flex flex-col gap-2">
        <Loader.Item height="56px" />
        <Loader.Item height="56px" />
        <Loader.Item height="56px" />
      </Loader>
    );
  }

  if (!isLoaded && error) {
    return <p className="text-body-sm-regular text-danger-primary">{t("jp_work_item_types.settings.load_failed")}</p>;
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-body-xs-regular text-tertiary">{t("jp_work_item_types.settings.shared_note")}</p>
      {workItemTypes.length === 0 ? (
        <p className="rounded-md border border-dashed border-subtle px-4 py-8 text-center text-body-sm-regular text-tertiary">
          {t("jp_work_item_types.settings.empty")}
        </p>
      ) : (
        <div className="divide-y divide-subtle rounded-lg border border-subtle" data-testid="work-item-types-list">
          {workItemTypes.map((workItemType) => (
            <WorkItemTypeRow
              key={workItemType.id}
              workItemType={workItemType}
              canEdit={isAdmin}
              onEdit={() => setEditingTypeId(workItemType.id)}
            />
          ))}
        </div>
      )}
      <WorkItemTypeEditModal
        workspaceSlug={workspaceSlug}
        workItemType={getWorkItemTypeById(editingTypeId)}
        isOpen={!!editingTypeId}
        onClose={() => setEditingTypeId(null)}
      />
    </div>
  );
});
