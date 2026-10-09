/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback, useEffect, useState } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import { Controller, useForm } from "react-hook-form";
import {
  AddOutline,
  ChevronRightOutline,
  InfoOutline,
  MembersOutline,
  UserAltOutline,
  WorkItemsOutline,
} from "@makeplane/propel/icons";
import { Collapsible } from "@makeplane/propel/components/collapsible";
import { MODULE_STATUS, EUserPermissions, EUserPermissionsLevel, EEstimateSystem } from "@plane/constants";
// plane types
import { useTranslation } from "@plane/i18n";
import { ModuleStatusIcon } from "@plane/blocks/icons";
import { setToast } from "@plane/blocks/toast";
import type { ILinkDetails, IModule, ModuleLink } from "@plane/types";
// plane ui
import { Select } from "@plane/blocks/select";
import { Loader } from "@plane/blocks/skeleton";
import { TextArea } from "@makeplane/propel/components/text-area";
// components
// helpers
import { MemberSelect } from "@/components/dropdowns/member/member-select";
import { ReleaseOverdueLozenge, ReleaseSidebarDates, ReleaseStatusLozenge } from "@/components/jira-parity/releases";
import { CreateUpdateModuleLinkModal, ModuleAnalyticsProgress, ModuleLinksList } from "@/components/modules";
// hooks
import { useProjectEstimates } from "@/hooks/store/estimates";
import { useModule } from "@/hooks/store/use-module";
import { useUserPermissions } from "@/hooks/store/user";
// plane web constants
type ModuleStatusOption = (typeof MODULE_STATUS)[number];

const defaultValues: Partial<IModule> = {
  lead_id: "",
  member_ids: [],
  start_date: null,
  target_date: null,
  status: "unreleased",
};

type TModuleLinksCollapsibleProps = {
  moduleDetails: IModule;
  moduleId: string;
  isEditingAllowed: boolean;
  isArchived: boolean;
  handleEditLink: (link: ILinkDetails) => void;
  handleDeleteLink: (linkId: string) => Promise<void>;
  setModuleLinkModal: (value: boolean) => void;
};

// Its own observer so the open state initialises from the loaded links and MobX tracks the list.
const ModuleLinksCollapsible = observer(function ModuleLinksCollapsible(props: TModuleLinksCollapsibleProps) {
  const {
    moduleDetails,
    moduleId,
    isEditingAllowed,
    isArchived,
    handleEditLink,
    handleDeleteLink,
    setModuleLinkModal,
  } = props;
  // states
  const [isOpen, setIsOpen] = useState(!!moduleDetails?.link_module?.length);
  // plane hooks
  const { t } = useTranslation();

  return (
    <div className="relative flex h-full w-full flex-col">
      <Collapsible
        open={isOpen}
        onOpenChange={setIsOpen}
        trigger={<span className="text-13 font-medium text-secondary">{t("common.links")}</span>}
      >
        <div className="mt-2 flex min-h-72 w-full flex-col space-y-3 overflow-y-auto">
          {isEditingAllowed && moduleDetails.link_module && moduleDetails.link_module.length > 0 ? (
            <>
              {isEditingAllowed && !isArchived && (
                <div className="flex w-full items-center justify-end">
                  <button
                    type="button"
                    className="flex items-center gap-1.5 text-13 font-medium text-accent-primary"
                    onClick={() => setModuleLinkModal(true)}
                  >
                    <AddOutline className="h-3 w-3" />
                    {t("add_link")}
                  </button>
                </div>
              )}

              {moduleId && (
                <ModuleLinksList
                  moduleId={moduleId}
                  handleEditLink={handleEditLink}
                  handleDeleteLink={handleDeleteLink}
                  disabled={!isEditingAllowed || isArchived}
                />
              )}
            </>
          ) : (
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <InfoOutline className="h-3.5 w-3.5 stroke-[1.5] text-tertiary" />
                <span className="p-0.5 text-11 text-tertiary">{t("common.no_links_added_yet")}</span>
              </div>
              {isEditingAllowed && !isArchived && (
                <button
                  type="button"
                  className="flex items-center gap-1.5 text-13 font-medium text-accent-primary"
                  onClick={() => setModuleLinkModal(true)}
                >
                  <AddOutline className="h-3 w-3" />
                  {t("add_link")}
                </button>
              )}
            </div>
          )}
        </div>
      </Collapsible>
    </div>
  );
});

type Props = {
  moduleId: string;
  handleClose: () => void;
  isArchived?: boolean;
};

// TODO: refactor this component
export const ModuleAnalyticsSidebar = observer(function ModuleAnalyticsSidebar(props: Props) {
  const { moduleId, handleClose, isArchived } = props;
  // states
  const [moduleLinkModal, setModuleLinkModal] = useState(false);
  const [selectedLinkToUpdate, setSelectedLinkToUpdate] = useState<ILinkDetails | null>(null);
  // router
  const { workspaceSlug, projectId } = useParams();

  // store hooks
  const { t } = useTranslation();
  const { allowPermissions } = useUserPermissions();

  const { getModuleById, updateModuleDetails, createModuleLink, updateModuleLink, deleteModuleLink } = useModule();
  const { areEstimateEnabledByProjectId, currentActiveEstimateId, estimateById } = useProjectEstimates();

  // derived values
  const moduleDetails = getModuleById(moduleId);
  const areEstimateEnabled = projectId && areEstimateEnabledByProjectId(projectId.toString());
  const estimateType = areEstimateEnabled && currentActiveEstimateId && estimateById(currentActiveEstimateId);
  const isEstimatePointValid = !!estimateType && estimateType?.type == EEstimateSystem.POINTS;

  const { reset, control } = useForm({
    defaultValues,
  });

  const submitChanges = async (data: Partial<IModule>) => {
    if (!workspaceSlug || !projectId || !moduleId) return;
    await updateModuleDetails(workspaceSlug.toString(), projectId.toString(), moduleId.toString(), data);
  };

  const handleCreateLink = async (formData: ModuleLink) => {
    if (!workspaceSlug || !projectId || !moduleId) return;
    const payload = { metadata: {}, ...formData };
    await createModuleLink(workspaceSlug.toString(), projectId.toString(), moduleId.toString(), payload);
  };

  const handleUpdateLink = async (formData: ModuleLink, linkId: string) => {
    if (!workspaceSlug || !projectId) return;
    const payload = { metadata: {}, ...formData };
    await updateModuleLink(workspaceSlug.toString(), projectId.toString(), moduleId.toString(), linkId, payload);
  };

  const handleDeleteLink = useCallback(
    async (linkId: string) => {
      if (!workspaceSlug || !projectId) return;
      try {
        await deleteModuleLink(workspaceSlug.toString(), projectId.toString(), moduleId.toString(), linkId);
        setToast({
          type: "success",
          title: "Success!",
          message: "Release link deleted successfully.",
        });
      } catch (_error) {
        setToast({
          type: "error",
          title: "Error!",
          message: "Some error occurred",
        });
      }
    },
    [workspaceSlug, projectId, moduleId, deleteModuleLink]
  );

  const handleDateChange = async (payload: Partial<Pick<IModule, "start_date" | "target_date">>) => {
    try {
      await submitChanges(payload);
      setToast({
        type: "success",
        title: "Success!",
        message: "Release updated successfully.",
      });
    } catch {
      setToast({
        type: "error",
        title: "Error!",
        message: "Release could not be updated. Please try again.",
      });
    }
  };

  useEffect(() => {
    if (moduleDetails)
      reset({
        ...moduleDetails,
      });
  }, [moduleDetails, reset]);

  const handleEditLink = useCallback((link: ILinkDetails) => {
    setSelectedLinkToUpdate(link);
    setModuleLinkModal(true);
  }, []);

  if (!moduleDetails)
    return (
      <Loader>
        <div className="space-y-2">
          <Loader.Item height="15px" width="50%" />
          <Loader.Item height="15px" width="30%" />
        </div>
        <div className="mt-8 space-y-3">
          <Loader.Item height="30px" />
          <Loader.Item height="30px" />
          <Loader.Item height="30px" />
        </div>
      </Loader>
    );

  const moduleStatus = MODULE_STATUS.find((status) => status.value === moduleDetails.status);

  const issueCount =
    moduleDetails.total_issues === 0
      ? "0 work items"
      : `${moduleDetails.completed_issues}/${moduleDetails.total_issues}`;

  const issueEstimatePointCount =
    moduleDetails.total_estimate_points === 0
      ? "0 work items"
      : `${moduleDetails.completed_estimate_points}/${moduleDetails.total_estimate_points}`;

  const isEditingAllowed = allowPermissions(
    [EUserPermissions.ADMIN, EUserPermissions.MEMBER],
    EUserPermissionsLevel.PROJECT
  );

  return (
    <div className="relative">
      <CreateUpdateModuleLinkModal
        isOpen={moduleLinkModal}
        handleClose={() => {
          setModuleLinkModal(false);
          setTimeout(() => {
            setSelectedLinkToUpdate(null);
          }, 500);
        }}
        data={selectedLinkToUpdate}
        createLink={handleCreateLink}
        updateLink={handleUpdateLink}
      />
      <>
        <div className={`sticky top-0 z-10 flex items-center justify-between bg-surface-1 pt-5 pb-5`}>
          <div>
            <button
              className="flex h-5 w-5 items-center justify-center rounded-full bg-layer-3"
              onClick={() => handleClose()}
            >
              <ChevronRightOutline className="h-3 w-3 text-on-color" />
            </button>
          </div>
        </div>

        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-5 pt-2">
            <Controller
              control={control}
              name="status"
              render={({ field: { value } }) => (
                <Select<ModuleStatusOption>
                  getValues={() => MODULE_STATUS}
                  value={MODULE_STATUS.find((status) => status.value === value) ?? null}
                  onChange={(val) => {
                    void submitChanges({ status: val as IModule["status"] });
                  }}
                  getOptionValue={(status) => status.value}
                  getOptionLabel={(status) => t(status.i18n_label)}
                  getOptionIcon={(status) => <ModuleStatusIcon status={status.value} />}
                  disabled={!isEditingAllowed || isArchived}
                  showSearch={false}
                  pinSelected={false}
                >
                  {/* The chip carries the status colour (a runtime hex), so the trigger chrome is
                      neutralised and the coloured surface stays on the inner span. */}
                  <Select.Trigger
                    variant="pill-md"
                    className={`h-6 border-none bg-transparent p-0 hover:bg-transparent active:bg-transparent ${
                      isEditingAllowed && !isArchived ? "cursor-pointer" : "cursor-not-allowed"
                    }`}
                  >
                    <span
                      className="flex h-6 w-20 items-center justify-center rounded-xs text-center text-11"
                      style={{
                        color: moduleStatus ? moduleStatus.color : "#a3a3a2",
                        backgroundColor: moduleStatus ? `${moduleStatus.color}20` : "#a3a3a220",
                      }}
                    >
                      {(moduleStatus && t(moduleStatus?.i18n_label)) ?? t("project_modules.status.unreleased")}
                    </span>
                  </Select.Trigger>
                </Select>
              )}
            />
            {/* Jira-parity: ARCHIVED / OVERDUE lozenges next to the status */}
            {moduleDetails.archived_at && <ReleaseStatusLozenge release={moduleDetails} />}
            <ReleaseOverdueLozenge release={moduleDetails} />
          </div>
          <h4 className="w-full text-18 font-semibold wrap-break-word text-primary">{moduleDetails.name}</h4>
          {moduleDetails.description && (
            <TextArea size="lg" surface="inline" autoResize value={moduleDetails.description} disabled />
          )}
        </div>

        <div className="flex flex-col gap-5 pt-2.5 pb-6">
          {/* Jira-parity: separate "Start date" / "Release date" (= target_date) rows */}
          <ReleaseSidebarDates
            release={moduleDetails}
            disabled={!isEditingAllowed || !!isArchived}
            onChange={(payload) => void handleDateChange(payload)}
          />
          <div className="flex items-center justify-start gap-1">
            <div className="flex w-2/5 items-center justify-start gap-2 text-tertiary">
              <UserAltOutline className="h-4 w-4" />
              <span className="text-14">{t("lead")}</span>
            </div>
            <Controller
              control={control}
              name="lead_id"
              render={({ field: { value } }) => (
                <div className="h-7 w-3/5">
                  <MemberSelect
                    value={value ?? null}
                    onChange={(val) => {
                      void submitChanges({ lead_id: val });
                    }}
                    projectId={projectId?.toString() ?? ""}
                    multiple={false}
                    placeholder={t("lead")}
                    disabled={!isEditingAllowed || isArchived}
                    variant="select-ghost-md"
                  />
                </div>
              )}
            />
          </div>
          <div className="flex items-center justify-start gap-1">
            <div className="flex w-2/5 items-center justify-start gap-2 text-tertiary">
              <MembersOutline className="h-4 w-4" />
              <span className="text-14">{t("members")}</span>
            </div>
            <Controller
              control={control}
              name="member_ids"
              render={({ field: { value } }) => (
                <div className="h-7 w-3/5">
                  <MemberSelect
                    value={value ?? []}
                    onChange={(val: string[]) => {
                      void submitChanges({ member_ids: val });
                    }}
                    multiple
                    projectId={projectId?.toString() ?? ""}
                    placeholder={t("members")}
                    disabled={!isEditingAllowed || isArchived}
                    variant="select-ghost-md"
                    showLabel={(value ?? []).length <= 1}
                  />
                </div>
              )}
            />
          </div>
          <div className="flex items-center justify-start gap-1">
            <div className="flex w-2/5 items-center justify-start gap-2 text-tertiary">
              <WorkItemsOutline className="h-4 w-4" />
              <span className="text-14">{t("issues")}</span>
            </div>
            <div className="flex h-7 w-3/5 items-center">
              <span className="px-1.5 text-13 text-tertiary">{issueCount}</span>
            </div>
          </div>

          {/**
           * NOTE: Render this section when estimate points of he projects is enabled and the estimate system is points
           */}
          {isEstimatePointValid && (
            <div className="flex items-center justify-start gap-1">
              <div className="flex w-2/5 items-center justify-start gap-2 text-tertiary">
                <WorkItemsOutline className="h-4 w-4" />
                <span className="text-14">{t("points")}</span>
              </div>
              <div className="flex h-7 w-3/5 items-center">
                <span className="px-1.5 text-13 text-tertiary">{issueEstimatePointCount}</span>
              </div>
            </div>
          )}
        </div>

        {workspaceSlug && projectId && moduleDetails?.id && (
          <ModuleAnalyticsProgress
            workspaceSlug={workspaceSlug.toString()}
            projectId={projectId.toString()}
            moduleId={moduleDetails?.id}
          />
        )}

        <div className="flex flex-col">
          <div className="flex w-full flex-col items-center justify-start gap-2 border-t border-subtle px-1.5 py-5">
            <ModuleLinksCollapsible
              moduleDetails={moduleDetails}
              moduleId={moduleId}
              isEditingAllowed={isEditingAllowed}
              isArchived={!!isArchived}
              handleEditLink={handleEditLink}
              handleDeleteLink={handleDeleteLink}
              setModuleLinkModal={setModuleLinkModal}
            />
          </div>
        </div>
      </>
    </div>
  );
});
