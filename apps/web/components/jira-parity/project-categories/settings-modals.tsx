/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: create / edit / delete dialogs of workspace settings > Project categories (owned by the
// project-categories feature). Admin only (the settings route is gated by WORKSPACE_SETTINGS access).
import { useEffect, useState } from "react";
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
import { ConfirmDialog } from "@plane/blocks/dialog";
import { EmojiPicker } from "@plane/blocks/emoji-icon-picker";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import type { TLogoProps, TProjectCategory } from "@plane/types";
// hooks
import { useProjectCategories } from "@/hooks/store/jira-parity/use-project-categories";
// local imports
import { ProjectCategoryIcon } from "./category-select";
import { getProjectCategoryErrorMessage } from "./utils";

const NAME_MAX_LENGTH = 255;

type TProjectCategoryFormValues = {
  name: string;
  description: string;
  logo_props: TLogoProps;
};

const getFormValues = (category: TProjectCategory | undefined): TProjectCategoryFormValues => ({
  name: category?.name ?? "",
  description: category?.description ?? "",
  logo_props: category?.logo_props ?? ({} as TLogoProps),
});

/** EmojiPicker change payload -> TLogoProps (same mapping as the project settings form). */
const toLogoProps = (value: { type?: string; value?: unknown } | undefined): TLogoProps => {
  if (value?.type === "emoji") return { in_use: "emoji", emoji: { value: value.value as string } } as TLogoProps;
  if (value?.type === "icon") return { in_use: "icon", icon: value.value } as TLogoProps;
  return {} as TLogoProps;
};

type TProjectCategoryFormModalProps = {
  workspaceSlug: string;
  /** Category to edit; undefined creates a new one. */
  category?: TProjectCategory;
  isOpen: boolean;
  onClose: () => void;
};

export const ProjectCategoryFormModal = observer(function ProjectCategoryFormModal(
  props: TProjectCategoryFormModalProps
) {
  const { workspaceSlug, category, isOpen, onClose } = props;
  // states
  const [isLogoPickerOpen, setIsLogoPickerOpen] = useState(false);
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const { createCategory, updateCategory } = useProjectCategories();
  // form
  const {
    control,
    handleSubmit,
    reset,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<TProjectCategoryFormValues>({ defaultValues: getFormValues(category) });
  const isEditing = !!category;

  // re-seed the form whenever the modal opens (for a new category or another one)
  useEffect(() => {
    if (isOpen) reset(getFormValues(category));
    // oxlint-disable-next-line eslint-plugin-react-hooks/exhaustive-deps
  }, [isOpen, category?.id, reset]);

  const onSubmit = async (formData: TProjectCategoryFormValues) => {
    const payload = {
      name: formData.name.trim(),
      description: formData.description.trim(),
      logo_props: formData.logo_props,
    };
    try {
      if (category) await updateCategory(workspaceSlug, category.id, payload);
      else await createCategory(workspaceSlug, payload);
      setToast({
        type: "success",
        title: t(isEditing ? "jp_categories.settings.toast.updated" : "jp_categories.settings.toast.created"),
        message: payload.name,
      });
      onClose();
    } catch (error) {
      const message = getProjectCategoryErrorMessage(error, t("jp_categories.settings.toast.save_failed"));
      if (error && typeof error === "object" && "name" in error) setError("name", { message });
      setToast({ type: "error", title: t("jp_categories.settings.toast.error"), message });
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
        <form onSubmit={handleSubmit(onSubmit)} className="flex min-h-0 flex-1 flex-col">
          <DialogMain>
            <DialogHeader>
              <DialogHeading>
                <DialogTitle>
                  {t(isEditing ? "jp_categories.settings.edit_title" : "jp_categories.settings.create_title")}
                </DialogTitle>
              </DialogHeading>
            </DialogHeader>
            <DialogBody>
              <div className="flex flex-col gap-5">
                <div className="flex items-end gap-3">
                  <Controller
                    control={control}
                    name="logo_props"
                    render={({ field: { value, onChange } }) => (
                      <EmojiPicker
                        iconType="material"
                        closeOnSelect={false}
                        isOpen={isLogoPickerOpen}
                        handleToggle={(open: boolean) => setIsLogoPickerOpen(open)}
                        className="flex shrink-0 items-center justify-center"
                        buttonClassName="flex size-9 items-center justify-center rounded-md border border-subtle bg-layer-1 hover:bg-layer-1-hover"
                        label={<ProjectCategoryIcon category={{ logo_props: value }} className="size-4" />}
                        onChange={(selected: { type?: string; value?: unknown }) => {
                          onChange(toLogoProps(selected));
                          setIsLogoPickerOpen(false);
                        }}
                        defaultIconColor={value?.in_use === "icon" ? value?.icon?.color : undefined}
                        defaultOpen={value?.in_use === "emoji" ? "emoji" : "icon"}
                      />
                    )}
                  />
                  <div className="min-w-0 flex-1">
                    <Controller
                      control={control}
                      name="name"
                      rules={{
                        validate: (value) => value.trim().length > 0 || t("jp_categories.settings.name_required"),
                        maxLength: { value: NAME_MAX_LENGTH, message: t("jp_categories.settings.name_too_long") },
                      }}
                      render={({ field: { value, onChange, ref } }) => (
                        <InputField
                          id="project-category-name"
                          name="name"
                          ref={ref}
                          value={value}
                          onChange={onChange}
                          size="lg"
                          orientation="vertical"
                          label={t("jp_categories.settings.name_label")}
                          placeholder={t("jp_categories.settings.name_placeholder")}
                          required
                          error={errors.name?.message}
                        />
                      )}
                    />
                  </div>
                </div>
                <Controller
                  control={control}
                  name="description"
                  render={({ field: { value, onChange } }) => (
                    <TextAreaField
                      id="project-category-description"
                      name="description"
                      value={value}
                      onChange={onChange}
                      size="lg"
                      label={t("jp_categories.settings.description_label")}
                      placeholder={t("jp_categories.settings.description_placeholder")}
                      autoResize
                      maxRows={6}
                    />
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
              label={t("jp_categories.settings.cancel")}
              onClick={onClose}
            />
            <Button
              variant="primary"
              size="md"
              stretch="auto"
              type="submit"
              loading={isSubmitting}
              disabled={isSubmitting}
              label={
                isSubmitting
                  ? t("jp_categories.settings.saving")
                  : t(isEditing ? "jp_categories.settings.save" : "jp_categories.settings.create")
              }
            />
          </DialogActions>
        </form>
      </DialogContent>
    </Dialog>
  );
});

type TProjectCategoryDeleteModalProps = {
  workspaceSlug: string;
  category: TProjectCategory | undefined;
  isOpen: boolean;
  onClose: () => void;
};

export const ProjectCategoryDeleteModal = observer(function ProjectCategoryDeleteModal(
  props: TProjectCategoryDeleteModalProps
) {
  const { workspaceSlug, category, isOpen, onClose } = props;
  // states
  const [isDeleting, setIsDeleting] = useState(false);
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const { deleteCategory, getProjectIdsByCategoryId } = useProjectCategories();
  // derived values
  const projectCount = getProjectIdsByCategoryId(category?.id).length;

  const handleClose = () => {
    setIsDeleting(false);
    onClose();
  };

  const handleDelete = async () => {
    if (!category) return;
    setIsDeleting(true);
    try {
      await deleteCategory(workspaceSlug, category.id);
      setToast({ type: "success", title: t("jp_categories.settings.toast.deleted"), message: category.name });
      handleClose();
    } catch (error) {
      setIsDeleting(false);
      setToast({
        type: "error",
        title: t("jp_categories.settings.toast.error"),
        message: getProjectCategoryErrorMessage(error, t("jp_categories.settings.toast.delete_failed")),
      });
    }
  };

  return (
    <ConfirmDialog
      isOpen={isOpen}
      handleClose={handleClose}
      handleSubmit={handleDelete}
      isSubmitting={isDeleting}
      title={t("jp_categories.settings.delete_title")}
      primaryButtonText={{
        default: t("jp_categories.settings.delete"),
        loading: t("jp_categories.settings.deleting"),
      }}
      content={t("jp_categories.settings.delete_description", {
        name: category?.name ?? "",
        count: projectCount,
      })}
    />
  );
});
