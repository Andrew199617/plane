/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity (project lead / default assignee): the create-work-item modal pre-fills the assignee
// with the project's default assignee until the user picks assignees themselves. Owned by the
// lead-estimates feature; used by components/issues/issue-modal/components/default-properties.tsx.
import { useCallback, useEffect, useRef } from "react";
import { useFormContext, useFormState, useWatch } from "react-hook-form";
// plane imports
import type { TIssue } from "@plane/types";
// hooks
import { useMember } from "@/hooks/store/use-member";
import { useProject } from "@/hooks/store/use-project";
// local imports
import { getPrefillAssigneeId } from "./utils";

type TUseDefaultAssigneePrefillArgs = {
  /** Id of the work item being edited; nothing is pre-filled when editing. */
  workItemId: string | undefined;
  projectId: string | null;
};

/**
 * Pre-fills `assignee_ids` with the project's default assignee while the user hasn't chosen assignees.
 * - only when creating (no `workItemId`) and the field is empty (assignees passed in by the caller,
 *   e.g. "create in this assignee group", are kept);
 * - follows project changes while the value is still the pre-filled one;
 * - stops once the user changes the assignees (call `markAssigneesTouched` from the picker), until the
 *   project changes or the form is submitted ("create more");
 * - the pre-fill does not mark the form dirty.
 * Must be used inside the issue form's <FormProvider>.
 */
export const useDefaultAssigneePrefill = ({ workItemId, projectId }: TUseDefaultAssigneePrefillArgs) => {
  // form
  const { control, setValue } = useFormContext<TIssue>();
  const assigneeIds = useWatch({ control, name: "assignee_ids" });
  const { submitCount } = useFormState({ control });
  // store hooks
  const { getProjectById } = useProject();
  const {
    project: { getProjectMemberIds },
  } = useMember();
  // refs
  const isTouchedRef = useRef(false);
  const prefilledIdRef = useRef<string | null>(null);
  // derived values
  const prefillId = projectId
    ? getPrefillAssigneeId(getProjectById(projectId)?.default_assignee, getProjectMemberIds(projectId, false))
    : null;

  // a new project or a new work item ("create more") starts untouched again
  useEffect(() => {
    isTouchedRef.current = false;
  }, [projectId, submitCount]);

  useEffect(() => {
    if (workItemId || isTouchedRef.current) return;

    const currentIds = assigneeIds ?? [];
    const prefilledId = prefilledIdRef.current;
    const isPrefilledValue = prefilledId !== null && currentIds.length === 1 && currentIds[0] === prefilledId;
    // assignees that came from the caller (or a template) are never replaced
    if (currentIds.length > 0 && !isPrefilledValue) return;

    if (prefillId) {
      if (isPrefilledValue && prefilledId === prefillId) return;
      prefilledIdRef.current = prefillId;
      setValue("assignee_ids", [prefillId], { shouldDirty: false });
    } else if (isPrefilledValue) {
      // the new project has no default assignee: drop the previous project's pre-fill
      prefilledIdRef.current = null;
      setValue("assignee_ids", [], { shouldDirty: false });
    }
  }, [workItemId, projectId, prefillId, assigneeIds, submitCount, setValue]);

  const markAssigneesTouched = useCallback(() => {
    isTouchedRef.current = true;
  }, []);

  return { markAssigneesTouched };
};
