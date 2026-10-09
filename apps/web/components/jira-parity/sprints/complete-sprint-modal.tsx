/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: "Complete sprint" dialog (done / open summary + where the open work items go). Owned by the sprints
// feature.
import { useEffect, useMemo, useState } from "react";
import { observer } from "mobx-react";
import { mutate } from "swr";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import {
  Dialog,
  DialogActions,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogHeading,
  DialogMain,
  DialogTitle,
} from "@makeplane/propel/components/dialog";
import { Select } from "@plane/blocks/select";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import type { ICycle, TSprintMoveTarget } from "@plane/types";
// hooks
import { useCycle } from "@/hooks/store/use-cycle";
// local imports
import {
  getDefaultMoveTarget,
  getSprintErrorMessage,
  getSprintIssueSummary,
  isFutureSprint,
  sortFutureSprints,
} from "./helpers";

type TMoveTargetOption = { key: TSprintMoveTarget; label: string };

type TCompleteSprintModalProps = {
  workspaceSlug: string;
  projectId: string;
  cycle: ICycle;
  isOpen: boolean;
  onClose: () => void;
};

export const CompleteSprintModal = observer(function CompleteSprintModal(props: TCompleteSprintModalProps) {
  const { workspaceSlug, projectId, cycle, isOpen, onClose } = props;
  // states
  const [moveTo, setMoveTo] = useState<TSprintMoveTarget | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const { completeCycle, fetchActiveCycleProgress, getProjectCycleDetails } = useCycle();
  // derived values
  const { done, open } = getSprintIssueSummary(cycle);
  const futureSprints = sortFutureSprints(
    (getProjectCycleDetails(projectId) ?? []).filter((sprint) => sprint.id !== cycle.id && isFutureSprint(sprint))
  );
  const futureSprintIds = futureSprints.map((sprint) => sprint.id);
  const defaultMoveTarget = getDefaultMoveTarget(futureSprintIds);
  const options = useMemo<TMoveTargetOption[]>(
    () => [
      ...futureSprints.map((sprint) => ({ key: sprint.id, label: sprint.name })),
      { key: "new", label: t("jp_sprints.complete_modal.new_sprint") },
      { key: "backlog", label: t("jp_sprints.complete_modal.backlog") },
    ],
    // oxlint-disable-next-line eslint-plugin-react-hooks/exhaustive-deps
    [futureSprintIds.join(","), t]
  );
  const resolvedMoveTo = moveTo && options.some((option) => option.key === moveTo) ? moveTo : defaultMoveTarget;
  const selectedOption = options.find((option) => option.key === resolvedMoveTo) ?? null;

  // fresh counts + default target whenever the dialog opens
  useEffect(() => {
    if (!isOpen) return;
    setMoveTo(null);
    setServerError(null);
    // the progress endpoint returns every state-group count from one query
    void fetchActiveCycleProgress(workspaceSlug, projectId, cycle.id).catch(() => undefined);
    // oxlint-disable-next-line eslint-plugin-react-hooks/exhaustive-deps
  }, [isOpen, cycle.id]);

  const handleComplete = async () => {
    setIsSubmitting(true);
    setServerError(null);
    try {
      // nothing to move: "backlog" is a no-op target (never create an empty "new" sprint)
      const response = await completeCycle(workspaceSlug, projectId, cycle.id, open > 0 ? resolvedMoveTo : "backlog");
      void mutate(`PROJECT_ACTIVE_CYCLE_${projectId}`);
      const name = response?.cycle?.name ?? cycle.name;
      const moved = response?.moved_issues ?? 0;
      setToast({
        type: "success",
        title: t("jp_sprints.toasts.completed_title"),
        message:
          moved > 0
            ? response?.moved_to?.name
              ? t("jp_sprints.toasts.completed_moved", { name, count: moved, target: response.moved_to.name })
              : t("jp_sprints.toasts.completed_moved_backlog", { name, count: moved })
            : t("jp_sprints.toasts.completed", { name }),
      });
      onClose();
    } catch (error) {
      setServerError(getSprintErrorMessage(error, t("jp_sprints.toasts.complete_error")));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(nextOpen) => {
        if (!nextOpen && !isSubmitting) onClose();
      }}
    >
      <DialogContent size="sm">
        <DialogMain>
          <DialogHeader>
            <DialogHeading>
              <DialogTitle>{t("jp_sprints.complete_modal.title", { name: cycle.name })}</DialogTitle>
              <DialogDescription>{t("jp_sprints.complete_modal.summary", { done, open })}</DialogDescription>
            </DialogHeading>
          </DialogHeader>
          <DialogBody>
            <div className="flex flex-col gap-4" data-testid="complete-sprint-body">
              {open > 0 ? (
                <div className="flex flex-col gap-1.5" data-testid="complete-sprint-move-to">
                  <span className="text-body-xs-medium text-secondary">{t("jp_sprints.complete_modal.move_to")}</span>
                  <Select<TMoveTargetOption>
                    value={selectedOption}
                    onChange={(key) => {
                      if (key) setMoveTo(key);
                    }}
                    getValues={() => options}
                    getOptionValue={(option) => option.key}
                    getOptionLabel={(option) => option.label}
                    showSearch={options.length > 8}
                    pinSelected={false}
                    disabled={isSubmitting}
                  >
                    <Select.Trigger<TMoveTargetOption> variant="select-lg">
                      <span className="min-w-0 flex-1 truncate text-left">{selectedOption?.label ?? ""}</span>
                    </Select.Trigger>
                  </Select>
                  <span className="text-body-xs-regular text-tertiary">
                    {t("jp_sprints.complete_modal.move_to_hint")}
                  </span>
                </div>
              ) : (
                <p className="text-body-sm-regular text-secondary">{t("jp_sprints.complete_modal.all_done")}</p>
              )}
              {serverError && (
                <p
                  className="text-body-sm-regular text-danger-primary"
                  role="alert"
                  data-testid="complete-sprint-error"
                >
                  {serverError}
                </p>
              )}
            </div>
          </DialogBody>
        </DialogMain>
        <DialogActions>
          <Button
            variant="secondary"
            size="md"
            stretch="auto"
            label={t("jp_sprints.complete_modal.cancel")}
            onClick={onClose}
            disabled={isSubmitting}
          />
          <Button
            variant="primary"
            size="md"
            stretch="auto"
            loading={isSubmitting}
            disabled={isSubmitting}
            data-testid="complete-sprint-submit"
            label={isSubmitting ? t("jp_sprints.complete_modal.submitting") : t("jp_sprints.complete_modal.submit")}
            onClick={() => void handleComplete()}
          />
        </DialogActions>
      </DialogContent>
    </Dialog>
  );
});
