/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: edit a workspace work item type (name, description, icon, color). Admin only.
// Owned by the work-item-types feature.
import { useEffect } from "react";
import { observer } from "mobx-react";
import { Controller, useForm } from "react-hook-form";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import {
  Dialog,
  DialogActions,
  DialogBody,
  DialogContent,
  DialogHeader,
  DialogHeading,
  DialogMain,
  DialogTitle,
} from "@makeplane/propel/components/dialog";
import { InputField } from "@makeplane/propel/components/input-field";
import { TextAreaField } from "@makeplane/propel/components/text-area-field";
import { ColorSwatchPicker } from "@plane/blocks/common";
import { setToast } from "@plane/blocks/toast";
import { JP_WORK_ITEM_TYPE_COLOR_PRESETS, JP_WORK_ITEM_TYPE_ICON_KEYS } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import type { TWorkItemType, TWorkItemTypeIconKey } from "@plane/types";
import { cn } from "@plane/utils";
// hooks
import { useWorkItemTypes } from "@/hooks/store/jira-parity/use-work-item-types";
// local imports
import { WorkItemTypeGlyphIcon } from "./icons";
import { buildWorkItemTypeLogoProps, getWorkItemTypeColor, getWorkItemTypeIconKey } from "./rules";
import { getWorkItemTypeUpdateErrorMessage } from "./use-work-item-type-guard";

const NAME_MAX_LENGTH = 255;

type TWorkItemTypeFormValues = {
  name: string;
  description: string;
  iconKey: TWorkItemTypeIconKey;
  color: string;
};

const getFormValues = (workItemType: TWorkItemType | undefined): TWorkItemTypeFormValues => ({
  name: workItemType?.name ?? "",
  description: workItemType?.description ?? "",
  iconKey: getWorkItemTypeIconKey(workItemType),
  color: getWorkItemTypeColor(workItemType),
});

type TWorkItemTypeEditModalProps = {
  workspaceSlug: string;
  workItemType: TWorkItemType | undefined;
  isOpen: boolean;
  onClose: () => void;
};

export const WorkItemTypeEditModal = observer(function WorkItemTypeEditModal(props: TWorkItemTypeEditModalProps) {
  const { workspaceSlug, workItemType, isOpen, onClose } = props;
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const { updateWorkItemType } = useWorkItemTypes();
  // form
  const {
    control,
    handleSubmit,
    reset,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<TWorkItemTypeFormValues>({ defaultValues: getFormValues(workItemType) });
  // derived values
  const previewIconKey = watch("iconKey");
  const previewColor = watch("color");
  const previewName = watch("name");

  // re-seed the form when the modal opens for a type (not on every store refresh of that type)
  useEffect(() => {
    if (isOpen) reset(getFormValues(workItemType));
    // oxlint-disable-next-line eslint-plugin-react-hooks/exhaustive-deps
  }, [isOpen, workItemType?.id, reset]);

  const handleClose = () => {
    onClose();
  };

  const onSubmit = async (formData: TWorkItemTypeFormValues) => {
    if (!workItemType) return;
    try {
      await updateWorkItemType(workspaceSlug, workItemType.id, {
        name: formData.name.trim(),
        description: formData.description.trim(),
        logo_props: buildWorkItemTypeLogoProps(formData.iconKey, formData.color),
      });
      setToast({
        type: "success",
        title: t("jp_work_item_types.settings.toast.updated.title"),
        message: t("jp_work_item_types.settings.toast.updated.message", { type: formData.name.trim() }),
      });
      handleClose();
    } catch (error) {
      setToast({
        type: "error",
        title: t("jp_work_item_types.settings.toast.update_failed.title"),
        message: getWorkItemTypeUpdateErrorMessage(error, t("jp_work_item_types.settings.toast.update_failed.message")),
      });
    }
  };

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) handleClose();
      }}
    >
      <DialogContent size="md">
        <form onSubmit={handleSubmit(onSubmit)} className="flex min-h-0 flex-1 flex-col">
          <DialogMain>
            <DialogHeader>
              <DialogHeading>
                <DialogTitle>{t("jp_work_item_types.settings.edit_modal.title")}</DialogTitle>
              </DialogHeading>
            </DialogHeader>
            <DialogBody>
              <div className="flex flex-col gap-5">
                {/* preview */}
                <div className="flex items-center gap-2 rounded-md border border-subtle bg-layer-1 px-3 py-2">
                  <WorkItemTypeGlyphIcon iconKey={previewIconKey} color={previewColor} className="size-5" />
                  <span className="truncate text-body-sm-medium text-primary">
                    {previewName.trim() || t("jp_work_item_types.settings.edit_modal.name_placeholder")}
                  </span>
                </div>
                <Controller
                  control={control}
                  name="name"
                  rules={{
                    validate: (value) =>
                      value.trim().length > 0 || t("jp_work_item_types.settings.edit_modal.name_required"),
                    maxLength: {
                      value: NAME_MAX_LENGTH,
                      message: t("jp_work_item_types.settings.edit_modal.name_too_long"),
                    },
                  }}
                  render={({ field: { value, onChange, ref } }) => (
                    <InputField
                      id="work-item-type-name"
                      name="name"
                      ref={ref}
                      value={value}
                      onChange={onChange}
                      size="lg"
                      orientation="vertical"
                      label={t("jp_work_item_types.settings.edit_modal.name_label")}
                      placeholder={t("jp_work_item_types.settings.edit_modal.name_placeholder")}
                      required
                      error={errors.name?.message}
                    />
                  )}
                />
                <Controller
                  control={control}
                  name="description"
                  render={({ field: { value, onChange } }) => (
                    <TextAreaField
                      id="work-item-type-description"
                      name="description"
                      value={value}
                      onChange={onChange}
                      size="lg"
                      label={t("jp_work_item_types.settings.edit_modal.description_label")}
                      placeholder={t("jp_work_item_types.settings.edit_modal.description_placeholder")}
                      autoResize
                      maxRows={6}
                    />
                  )}
                />
                <Controller
                  control={control}
                  name="iconKey"
                  render={({ field: { value, onChange } }) => (
                    <fieldset className="flex flex-col gap-2">
                      <legend className="mb-2 text-body-xs-medium text-secondary">
                        {t("jp_work_item_types.settings.edit_modal.icon_label")}
                      </legend>
                      <div className="flex flex-wrap gap-2">
                        {JP_WORK_ITEM_TYPE_ICON_KEYS.map((iconKey) => {
                          const isSelected = iconKey === value;
                          const iconName = t(`jp_work_item_types.settings.glyphs.${iconKey}`);
                          return (
                            <button
                              key={iconKey}
                              type="button"
                              aria-pressed={isSelected}
                              aria-label={iconName}
                              title={iconName}
                              onClick={() => onChange(iconKey)}
                              className={cn(
                                "grid size-9 place-items-center rounded-md border border-subtle transition-colors outline-none hover:bg-layer-1-hover focus-visible:ring-2 focus-visible:ring-accent-strong",
                                isSelected && "border-accent-strong bg-layer-1"
                              )}
                            >
                              <WorkItemTypeGlyphIcon iconKey={iconKey} color={previewColor} className="size-5" />
                            </button>
                          );
                        })}
                      </div>
                    </fieldset>
                  )}
                />
                <Controller
                  control={control}
                  name="color"
                  render={({ field: { value, onChange } }) => (
                    <fieldset className="flex flex-col gap-2">
                      <legend className="mb-2 text-body-xs-medium text-secondary">
                        {t("jp_work_item_types.settings.edit_modal.color_label")}
                      </legend>
                      <ColorSwatchPicker colors={JP_WORK_ITEM_TYPE_COLOR_PRESETS} value={value} onChange={onChange} />
                    </fieldset>
                  )}
                />
              </div>
            </DialogBody>
          </DialogMain>
          <DialogActions>
            <Button
              variant="secondary"
              size="md"
              stretch="auto"
              label={t("jp_work_item_types.settings.edit_modal.cancel")}
              onClick={handleClose}
            />
            <Button
              variant="primary"
              size="md"
              stretch="auto"
              type="submit"
              loading={isSubmitting}
              disabled={isSubmitting || !workItemType}
              label={
                isSubmitting
                  ? t("jp_work_item_types.settings.edit_modal.saving")
                  : t("jp_work_item_types.settings.edit_modal.save")
              }
            />
          </DialogActions>
        </form>
      </DialogContent>
    </Dialog>
  );
});
