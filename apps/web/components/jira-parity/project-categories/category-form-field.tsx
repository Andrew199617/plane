/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: "Category" field of project settings > General (components/project/form.tsx), owned by the
// project-categories feature. The value is submitted as `category_id` with the rest of the form.
import { observer } from "mobx-react";
import { Controller } from "react-hook-form";
import type { Control } from "react-hook-form";
// plane imports
import { useTranslation } from "@plane/i18n";
import type { IProject } from "@plane/types";
// local imports
import { ProjectCategorySelect } from "./category-select";

type TProjectCategoryFormFieldProps = {
  control: Control<IProject>;
  disabled?: boolean;
};

export const ProjectCategoryFormField = observer(function ProjectCategoryFormField(
  props: TProjectCategoryFormFieldProps
) {
  const { control, disabled = false } = props;
  const { t } = useTranslation();

  return (
    <div className="flex flex-col gap-1" data-testid="project-category-field">
      <h4 className="text-13">{t("jp_categories.select.label")}</h4>
      <Controller
        name="category_id"
        control={control}
        render={({ field: { value, onChange } }) => (
          <ProjectCategorySelect
            value={value ?? null}
            onChange={onChange}
            variant="select-lg"
            className="font-medium"
            disabled={disabled}
          />
        )}
      />
    </div>
  );
});
