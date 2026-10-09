/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: "Release <name>" — pick the release date and, when the release still has unresolved work
// items, either move them to another unreleased release or ignore them and release anyway.
import { useEffect, useState } from "react";
import { observer } from "mobx-react";
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
import { CalendarOutline } from "@makeplane/propel/icons";
import { RadioGroupField, RadioGroupFieldOption } from "@makeplane/propel/components/radio-group-field";
import { ModuleStatusIcon } from "@plane/blocks/icons";
import { DateSelect } from "@plane/blocks/property-select";
import { Select } from "@plane/blocks/select";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import type { IModule } from "@plane/types";
// hooks
import { useModule } from "@/hooks/store/use-module";
import { useUserProfile } from "@/hooks/store/user";
// local imports
import {
  getDefaultReleaseDate,
  getMoveTargetReleases,
  getReleaseErrorMessage,
  getUnresolvedCount,
  parsePayloadDate,
  toPayloadDate,
} from "./helpers";

type TUnresolvedMode = "move" | "ignore";

type TReleaseModalProps = {
  workspaceSlug: string;
  projectId: string;
  moduleId: string;
  isOpen: boolean;
  onClose: () => void;
};

export const ReleaseModal = observer(function ReleaseModal(props: TReleaseModalProps) {
  const { workspaceSlug, projectId, moduleId, isOpen, onClose } = props;
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const { getModuleById, getProjectModuleDetails, fetchModules, releaseModule } = useModule();
  const { data: userProfile } = useUserProfile();
  // states
  const [releaseDate, setReleaseDate] = useState<Date | null>(null);
  // null = not chosen yet → defaults below (they follow the move targets once the project's releases load)
  const [mode, setMode] = useState<TUnresolvedMode | null>(null);
  const [targetId, setTargetId] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showTargetError, setShowTargetError] = useState(false);
  // derived values
  const release = getModuleById(moduleId);
  const projectReleases = getProjectModuleDetails(projectId);
  const unresolvedCount = getUnresolvedCount(release);
  const moveTargets: IModule[] = release ? getMoveTargetReleases(projectReleases ?? [], release) : [];
  const resolvedMode: TUnresolvedMode = mode ?? (moveTargets.length > 0 ? "move" : "ignore");
  const selectedTarget = moveTargets.find((target) => target.id === targetId) ?? moveTargets[0] ?? null;
  const willMove = unresolvedCount > 0 && resolvedMode === "move";

  // re-seed whenever the modal opens
  useEffect(() => {
    if (!isOpen) return;
    setReleaseDate(parsePayloadDate(getDefaultReleaseDate(getModuleById(moduleId))));
    setMode(null);
    setTargetId(null);
    setShowTargetError(false);
    setIsSubmitting(false);
    // oxlint-disable-next-line eslint-plugin-react-hooks/exhaustive-deps
  }, [isOpen, moduleId]);

  // the move targets come from the project's release list — load it when this opens elsewhere (e.g. a deep link)
  useEffect(() => {
    if (!isOpen || !workspaceSlug || !projectId || projectReleases) return;
    void fetchModules(workspaceSlug, projectId);
  }, [isOpen, workspaceSlug, projectId, projectReleases, fetchModules]);

  if (!release) return null;

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    event.stopPropagation();
    if (isSubmitting) return;
    if (willMove && !selectedTarget) {
      setShowTargetError(true);
      return;
    }
    setIsSubmitting(true);
    try {
      const moveTo = willMove ? (selectedTarget?.id ?? null) : null;
      const response = await releaseModule(workspaceSlug, projectId, release.id, {
        release_date: releaseDate ? toPayloadDate(releaseDate) : null,
        move_to: moveTo,
      });
      const movedCount = response?.moved_issues ?? 0;
      setToast({
        type: "success",
        title: t("toast.success"),
        message:
          moveTo && movedCount > 0
            ? t("jp_releases.toasts.released_moved", {
                name: release.name,
                count: movedCount,
                target: selectedTarget?.name ?? "",
              })
            : t("jp_releases.toasts.released", { name: release.name }),
      });
      onClose();
    } catch (error) {
      setToast({
        type: "error",
        title: t("toast.error"),
        message: getReleaseErrorMessage(error, t, t("jp_releases.toasts.release_error", { name: release.name })),
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => {
        if (!open && !isSubmitting) onClose();
      }}
    >
      <DialogContent size="md">
        <form onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col" data-testid="release-form">
          <DialogMain>
            <DialogHeader>
              <DialogHeading>
                <DialogTitle>{t("jp_releases.release_modal.title", { name: release.name })}</DialogTitle>
                <DialogDescription>{t("jp_releases.release_modal.description")}</DialogDescription>
              </DialogHeading>
            </DialogHeader>
            <DialogBody>
              <div className="flex flex-col gap-5">
                <div className="flex flex-col gap-1.5">
                  <span className="text-body-xs-medium text-secondary">
                    {t("jp_releases.release_modal.release_date")}
                  </span>
                  <DateSelect
                    value={releaseDate}
                    onChange={(date) => setReleaseDate(date)}
                    icon={<CalendarOutline />}
                    placeholder={t("jp_releases.release_modal.release_date_placeholder")}
                    weekStartsOn={userProfile?.start_of_the_week}
                    variant="select-lg"
                    className="w-full"
                    testId="release-form-date"
                  />
                </div>

                {unresolvedCount > 0 ? (
                  <div className="flex flex-col gap-3">
                    <RadioGroupField<TUnresolvedMode>
                      name="release_unresolved"
                      label={t("jp_releases.release_modal.unresolved_label")}
                      description={t("jp_releases.release_modal.unresolved_summary", { count: unresolvedCount })}
                      size="md"
                      density="comfortable"
                      value={resolvedMode}
                      onValueChange={(value) => {
                        setMode(value);
                        setShowTargetError(false);
                      }}
                    >
                      <RadioGroupFieldOption
                        value="move"
                        label={t("jp_releases.release_modal.move_option", { count: unresolvedCount })}
                        description={moveTargets.length === 0 ? t("jp_releases.release_modal.no_targets") : undefined}
                        disabled={moveTargets.length === 0}
                      />
                      <RadioGroupFieldOption
                        value="ignore"
                        label={t("jp_releases.release_modal.ignore_option")}
                        description={t("jp_releases.release_modal.ignore_description")}
                      />
                    </RadioGroupField>
                    {willMove && (
                      <div className="flex flex-col gap-1.5" data-testid="release-form-target">
                        <span className="text-body-xs-medium text-secondary">
                          {t("jp_releases.release_modal.move_to")}
                        </span>
                        <Select<IModule>
                          value={selectedTarget}
                          onChange={(id) => {
                            setTargetId(id || null);
                            setShowTargetError(false);
                          }}
                          getValues={() => moveTargets}
                          getOptionValue={(option) => option.id}
                          getOptionLabel={(option) => option.name}
                          getOptionIcon={() => <ModuleStatusIcon status="unreleased" />}
                          showSearch={moveTargets.length > 7}
                          pinSelected={false}
                        >
                          <Select.Trigger<IModule> variant="select-lg" className="w-full">
                            <span className="min-w-0 flex-1 truncate text-left">
                              {selectedTarget?.name ?? t("jp_releases.release_modal.select_target")}
                            </span>
                          </Select.Trigger>
                        </Select>
                        {showTargetError && (
                          <span className="text-body-xs-regular text-danger-primary">
                            {t("jp_releases.release_modal.target_required")}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                ) : (
                  <span className="text-body-xs-regular text-tertiary">
                    {t("jp_releases.release_modal.all_resolved")}
                  </span>
                )}
              </div>
            </DialogBody>
          </DialogMain>
          <DialogActions>
            <Button
              variant="secondary"
              size="md"
              stretch="auto"
              label={t("jp_releases.release_modal.cancel")}
              onClick={onClose}
              disabled={isSubmitting}
            />
            <Button
              variant="primary"
              size="md"
              stretch="auto"
              type="submit"
              loading={isSubmitting}
              disabled={isSubmitting}
              data-testid="release-form-submit"
              label={isSubmitting ? t("jp_releases.release_modal.submitting") : t("jp_releases.release_modal.submit")}
            />
          </DialogActions>
        </form>
      </DialogContent>
    </Dialog>
  );
});
