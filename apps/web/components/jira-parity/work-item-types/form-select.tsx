/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: work item type picker in the create/edit work item modal (owned by the work-item-types feature).
// - defaults to the workspace default type (Task) and suggests Sub-task when created under a Task/Story/Bug
// - picking Sub-task without a parent opens the parent picker; submitting a Sub-task without a parent (or
//   under a Sub-task) is blocked through a react-hook-form `validate` rule on `type_id`
import { useEffect, useRef, useState } from "react";
import { observer } from "mobx-react";
import { Controller, useFormContext } from "react-hook-form";
// plane imports
import { ParentOutline } from "@makeplane/propel/icons";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import type { ISearchIssueResponse, TIssue, TWorkItemTypeHierarchyError } from "@plane/types";
// components
import { ParentIssuesListModal } from "@/components/issues/parent-issues-list-modal";
// hooks
import { useIssueModal } from "@/hooks/context/use-issue-modal";
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
import { useWorkItemTypes } from "@/hooks/store/jira-parity/use-work-item-types";
// local imports
import { getSuggestedWorkItemTypeForParent, getWorkItemTypeHierarchyError } from "./rules";
import { WorkItemTypeSelect } from "./type-select";

const HIERARCHY_ERROR_I18N_KEYS: Record<TWorkItemTypeHierarchyError, string> = {
  sub_task_requires_parent: "jp_work_item_types.errors.sub_task_requires_parent",
  parent_is_sub_task: "jp_work_item_types.errors.parent_is_sub_task",
  sub_task_cannot_have_children: "jp_work_item_types.errors.sub_task_cannot_have_children",
};

type TWorkItemTypeFormSelectProps = {
  /** Id of the work item being edited (undefined while creating). */
  workItemId?: string;
  /** Whether the modal saves a workspace draft (the parent rule is enforced when the draft is moved). */
  isDraft?: boolean;
  disabled?: boolean;
  handleFormChange: () => void;
  tabIndex?: number;
};

export const WorkItemTypeFormSelect = observer(function WorkItemTypeFormSelect(props: TWorkItemTypeFormSelectProps) {
  const { workItemId, isDraft = false, disabled = false, handleFormChange, tabIndex } = props;
  // states
  const [isParentModalOpen, setIsParentModalOpen] = useState(false);
  // refs
  const hasUserPickedTypeRef = useRef(false);
  const autoSetTypeIdRef = useRef<string | null>(null);
  // plane hooks
  const { t } = useTranslation();
  // form
  const { control, watch, setValue, getValues, trigger, formState } = useFormContext<TIssue>();
  // store hooks
  const { selectedParentIssue, setSelectedParentIssue } = useIssueModal();
  const { activeWorkItemTypes, defaultWorkItemType, getWorkItemTypeById } = useWorkItemTypes();
  const {
    issue: { getIssueById },
  } = useIssueDetail();
  // derived values
  const typeId = watch("type_id");
  const parentId = watch("parent_id");
  const projectId = watch("project_id");
  const isEditing = !!workItemId;
  const selectedType = getWorkItemTypeById(typeId);
  const parentTypeId = parentId
    ? selectedParentIssue?.id === parentId
      ? selectedParentIssue.type_id
      : getIssueById(parentId)?.type_id
    : undefined;
  const parentType = getWorkItemTypeById(parentTypeId);
  const hasChildren = isEditing && (getIssueById(workItemId)?.sub_issues_count ?? 0) > 0;
  const hierarchyError = getWorkItemTypeHierarchyError(selectedType, {
    hasParent: !!parentId,
    parentType,
    hasChildren,
  });
  const typeFieldError = formState.errors.type_id;

  // latest validator for the `type_id` rule (rules are registered once, so read through a ref)
  const validateRef = useRef<() => true | string>(() => true);
  validateRef.current = () => (hierarchyError ? t(HIERARCHY_ERROR_I18N_KEYS[hierarchyError]) : true);

  // default to the workspace default type once types are loaded
  useEffect(() => {
    if (typeId || !defaultWorkItemType) return;
    autoSetTypeIdRef.current = defaultWorkItemType.id;
    setValue("type_id", defaultWorkItemType.id);
  }, [typeId, defaultWorkItemType, setValue]);

  // while creating, follow the parent: Sub-task under a Task/Story/Bug, default type otherwise. Only
  // types picked automatically are replaced (never a user pick or a preloaded non-default type).
  // `typeId` is a dependency because IssueFormRoot resets the form (type_id -> default) after mount.
  useEffect(() => {
    if (isEditing || hasUserPickedTypeRef.current) return;
    if (parentId && !parentType) return; // parent type unknown yet
    const currentTypeId = getValues("type_id");
    const isAutomaticType =
      !currentTypeId || currentTypeId === autoSetTypeIdRef.current || currentTypeId === defaultWorkItemType?.id;
    if (!isAutomaticType) return;
    const suggestedType = getSuggestedWorkItemTypeForParent(activeWorkItemTypes, parentId ? parentType : undefined);
    if (!suggestedType || suggestedType.id === currentTypeId) return;
    autoSetTypeIdRef.current = suggestedType.id;
    setValue("type_id", suggestedType.id);
  }, [isEditing, typeId, parentId, parentType, activeWorkItemTypes, defaultWorkItemType, getValues, setValue]);

  // re-check a failed submit once the parent changes
  useEffect(() => {
    if (formState.errors.type_id) void trigger("type_id");
    // oxlint-disable-next-line eslint-plugin-react-hooks/exhaustive-deps
  }, [parentId, parentTypeId]);

  // explain a blocked submit
  useEffect(() => {
    if (!typeFieldError?.message || formState.submitCount === 0) return;
    setToast({
      type: "error",
      title: t("jp_work_item_types.errors.title"),
      message: typeFieldError.message,
    });
    // oxlint-disable-next-line eslint-plugin-react-hooks/exhaustive-deps
  }, [formState.submitCount]);

  const handleParentSelect = (parentIssue: ISearchIssueResponse) => {
    if (getWorkItemTypeById(parentIssue.type_id)?.is_sub_task) {
      setToast({
        type: "error",
        title: t("jp_work_item_types.errors.title"),
        message: t("jp_work_item_types.errors.parent_is_sub_task"),
      });
      return;
    }
    setValue("parent_id", parentIssue.id, { shouldDirty: true });
    setSelectedParentIssue(parentIssue);
    handleFormChange();
  };

  const visibleError =
    typeFieldError?.message ??
    (hierarchyError && hierarchyError !== "sub_task_requires_parent"
      ? t(HIERARCHY_ERROR_I18N_KEYS[hierarchyError])
      : undefined);

  return (
    <>
      <Controller
        control={control}
        name="type_id"
        rules={{ validate: () => (isDraft ? true : validateRef.current()) }}
        render={({ field: { value, onChange } }) => (
          <WorkItemTypeSelect
            testId="work-item-modal-type-select"
            value={value}
            onChange={(workItemTypeId) => {
              hasUserPickedTypeRef.current = true;
              onChange(workItemTypeId);
              handleFormChange();
              if (getWorkItemTypeById(workItemTypeId)?.is_sub_task && !getValues("parent_id")) {
                setIsParentModalOpen(true);
              }
            }}
            getOptionDisabledReason={(workItemType) =>
              workItemType.is_sub_task && hasChildren ? t("jp_work_item_types.select.has_children") : undefined
            }
            disabled={disabled}
            variant="pill-md"
            tabIndex={tabIndex}
          />
        )}
      />
      {hierarchyError === "sub_task_requires_parent" && (
        <button
          type="button"
          className="inline-flex h-6 shrink-0 items-center gap-1 rounded-md border border-danger-strong/20 bg-danger-subtle px-1.5 text-caption-md-regular text-danger-primary"
          onClick={() => setIsParentModalOpen(true)}
          data-testid="work-item-modal-type-select-parent"
        >
          <ParentOutline className="size-3.5 shrink-0" />
          {t("jp_work_item_types.select.select_parent")}
        </button>
      )}
      {visibleError && (
        <span className="truncate text-caption-sm-regular text-danger-primary" role="alert">
          {visibleError}
        </span>
      )}
      <ParentIssuesListModal
        isOpen={isParentModalOpen}
        handleClose={() => setIsParentModalOpen(false)}
        onChange={handleParentSelect}
        projectId={projectId ?? undefined}
        issueId={isEditing && !isDraft ? workItemId : undefined}
      />
    </>
  );
});
