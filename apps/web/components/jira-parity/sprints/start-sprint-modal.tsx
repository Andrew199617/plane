/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: "Start sprint" dialog (name, duration, start / end date, sprint goal). Owned by the sprints feature.
import { useEffect, useMemo, useState } from "react";
import { observer } from "mobx-react";
import { Controller, useForm } from "react-hook-form";
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
import { InputField } from "@makeplane/propel/components/input-field";
import { TextAreaField } from "@makeplane/propel/components/text-area-field";
import { CalendarOutline } from "@makeplane/propel/icons";
import { DateSelect } from "@plane/blocks/property-select";
import { Select } from "@plane/blocks/select";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import type { ICycle } from "@plane/types";
// hooks
import { useCycle } from "@/hooks/store/use-cycle";
import { useUserProfile } from "@/hooks/store/user";
// local imports
import type { TSprintDuration, TStartSprintFormValues } from "./helpers";
import {
  getSprintEndDate,
  getSprintErrorMessage,
  getStartSprintDefaults,
  isValidSprintRange,
  parseDateKey,
  SPRINT_DURATION_I18N,
  SPRINT_DURATIONS,
  toDateKey,
} from "./helpers";

const NAME_MAX_LENGTH = 255;

type TDurationOption = { key: TSprintDuration; label: string };

type TStartSprintModalProps = {
  workspaceSlug: string;
  projectId: string;
  cycle: ICycle;
  isOpen: boolean;
  onClose: () => void;
};

export const StartSprintModal = observer(function StartSprintModal(props: TStartSprintModalProps) {
  const { workspaceSlug, projectId, cycle, isOpen, onClose } = props;
  // states
  const [serverError, setServerError] = useState<string | null>(null);
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const { startCycle } = useCycle();
  const { data: userProfile } = useUserProfile();
  // form
  const {
    control,
    handleSubmit,
    reset,
    watch,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<TStartSprintFormValues>({ defaultValues: getStartSprintDefaults(cycle, toDateKey(new Date())) });
  // derived values
  const duration = watch("duration");
  const startDate = watch("start_date");
  const endDate = watch("end_date");
  const durationOptions = useMemo<TDurationOption[]>(
    () => SPRINT_DURATIONS.map((key) => ({ key, label: t(SPRINT_DURATION_I18N[key]) })),
    [t]
  );
  const selectedDuration = durationOptions.find((option) => option.key === duration) ?? null;

  // re-seed the form whenever the dialog opens (not on every store refresh of the sprint)
  useEffect(() => {
    if (!isOpen) return;
    reset(getStartSprintDefaults(cycle, toDateKey(new Date())));
    setServerError(null);
    // oxlint-disable-next-line eslint-plugin-react-hooks/exhaustive-deps
  }, [isOpen, cycle.id, reset]);

  const handleDurationChange = (next: TSprintDuration) => {
    setValue("duration", next);
    if (next === "custom") return;
    setValue("end_date", getSprintEndDate(startDate, next), { shouldValidate: !!errors.end_date });
  };

  const handleStartDateChange = (date: Date | null) => {
    if (!date) return;
    const key = toDateKey(date);
    setValue("start_date", key, { shouldValidate: true });
    if (duration !== "custom") setValue("end_date", getSprintEndDate(key, duration), { shouldValidate: true });
  };

  const handleEndDateChange = (date: Date | null) => {
    if (!date) return;
    // picking an end date by hand means a custom duration
    setValue("duration", "custom");
    setValue("end_date", toDateKey(date), { shouldValidate: true });
  };

  const onSubmit = async (values: TStartSprintFormValues) => {
    if (!values.end_date) return;
    setServerError(null);
    try {
      const started = await startCycle(workspaceSlug, projectId, cycle.id, {
        name: values.name.trim(),
        description: values.description.trim(),
        start_date: values.start_date,
        end_date: values.end_date,
      });
      void mutate(`PROJECT_ACTIVE_CYCLE_${projectId}`);
      setToast({
        type: "success",
        title: t("jp_sprints.toasts.started_title"),
        message: t("jp_sprints.toasts.started", { name: started?.name ?? values.name.trim() }),
      });
      onClose();
    } catch (error) {
      setServerError(getSprintErrorMessage(error, t("jp_sprints.toasts.start_error")));
    }
  };

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent size="md">
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex min-h-0 flex-1 flex-col"
          data-testid="start-sprint-form"
        >
          <DialogMain>
            <DialogHeader>
              <DialogHeading>
                <DialogTitle>{t("jp_sprints.start_modal.title")}</DialogTitle>
                <DialogDescription>
                  {t("jp_sprints.start_modal.work_item_count", { count: cycle.total_issues ?? 0 })}
                </DialogDescription>
              </DialogHeading>
            </DialogHeader>
            <DialogBody>
              <div className="flex flex-col gap-5">
                <Controller
                  control={control}
                  name="name"
                  rules={{
                    validate: (value) => value.trim().length > 0 || t("jp_sprints.start_modal.name_required"),
                    maxLength: { value: NAME_MAX_LENGTH, message: t("jp_sprints.start_modal.name_max_length") },
                  }}
                  render={({ field: { value, onChange, ref } }) => (
                    <InputField
                      id="start-sprint-name"
                      name="name"
                      ref={ref}
                      value={value}
                      onChange={onChange}
                      size="lg"
                      orientation="vertical"
                      label={t("jp_sprints.start_modal.name")}
                      placeholder={t("jp_sprints.start_modal.name")}
                      required
                      error={errors.name?.message}
                      autoComplete="off"
                    />
                  )}
                />
                <div className="flex flex-col gap-1.5" data-testid="start-sprint-duration">
                  <span className="text-body-xs-medium text-secondary">{t("jp_sprints.start_modal.duration")}</span>
                  <Select<TDurationOption>
                    value={selectedDuration}
                    onChange={(key) => {
                      const next = SPRINT_DURATIONS.find((option) => option === key);
                      if (next && next !== duration) handleDurationChange(next);
                    }}
                    getValues={() => durationOptions}
                    getOptionValue={(option) => option.key}
                    getOptionLabel={(option) => option.label}
                    showSearch={false}
                    pinSelected={false}
                  >
                    <Select.Trigger<TDurationOption> variant="select-lg">
                      <span className="min-w-0 flex-1 truncate text-left">{selectedDuration?.label ?? ""}</span>
                    </Select.Trigger>
                  </Select>
                </div>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <Controller
                    control={control}
                    name="start_date"
                    rules={{ validate: (value) => !!value || t("jp_sprints.start_modal.dates_required") }}
                    render={({ field: { value } }) => (
                      <div className="flex flex-col gap-1.5" data-testid="start-sprint-start-date">
                        <span className="text-body-xs-medium text-secondary">
                          {t("jp_sprints.start_modal.start_date")}
                        </span>
                        <DateSelect
                          variant="select-lg"
                          value={parseDateKey(value)}
                          onChange={handleStartDateChange}
                          icon={<CalendarOutline />}
                          placeholder={t("jp_sprints.start_modal.select_date")}
                          weekStartsOn={userProfile?.start_of_the_week}
                        />
                        {errors.start_date?.message && (
                          <span className="text-body-xs-regular text-danger-primary">{errors.start_date.message}</span>
                        )}
                      </div>
                    )}
                  />
                  <Controller
                    control={control}
                    name="end_date"
                    rules={{
                      validate: (value) => {
                        if (!value) return t("jp_sprints.start_modal.dates_required");
                        return isValidSprintRange(startDate, value) || t("jp_sprints.start_modal.end_before_start");
                      },
                    }}
                    render={({ field: { value } }) => (
                      <div className="flex flex-col gap-1.5" data-testid="start-sprint-end-date">
                        <span className="text-body-xs-medium text-secondary">
                          {t("jp_sprints.start_modal.end_date")}
                        </span>
                        <DateSelect
                          variant="select-lg"
                          value={parseDateKey(value)}
                          onChange={handleEndDateChange}
                          icon={<CalendarOutline />}
                          placeholder={t("jp_sprints.start_modal.select_date")}
                          minDate={parseDateKey(startDate) ?? undefined}
                          weekStartsOn={userProfile?.start_of_the_week}
                        />
                        {errors.end_date?.message ? (
                          <span className="text-body-xs-regular text-danger-primary">{errors.end_date.message}</span>
                        ) : (
                          duration !== "custom" && (
                            <span className="text-body-xs-regular text-tertiary">
                              {t("jp_sprints.start_modal.end_date_hint")}
                            </span>
                          )
                        )}
                      </div>
                    )}
                  />
                </div>
                <Controller
                  control={control}
                  name="description"
                  render={({ field: { value, onChange } }) => (
                    <TextAreaField
                      id="start-sprint-goal"
                      name="description"
                      value={value}
                      onChange={onChange}
                      size="lg"
                      label={t("jp_sprints.goal.label")}
                      placeholder={t("jp_sprints.start_modal.goal_placeholder")}
                      autoResize
                      maxRows={6}
                    />
                  )}
                />
                {serverError && (
                  <p className="text-body-sm-regular text-danger-primary" role="alert" data-testid="start-sprint-error">
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
              label={t("jp_sprints.start_modal.cancel")}
              onClick={onClose}
            />
            <Button
              variant="primary"
              size="md"
              stretch="auto"
              type="submit"
              loading={isSubmitting}
              disabled={isSubmitting || !endDate}
              data-testid="start-sprint-submit"
              label={isSubmitting ? t("jp_sprints.start_modal.submitting") : t("jp_sprints.start_modal.submit")}
            />
          </DialogActions>
        </form>
      </DialogContent>
    </Dialog>
  );
});
