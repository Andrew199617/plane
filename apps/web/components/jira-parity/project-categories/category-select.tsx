/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: project category picker used by the project create modal and the project settings form.
import { observer } from "mobx-react";
import { ProjectsOutline } from "@makeplane/propel/icons";
// plane imports
import { useTranslation } from "@plane/i18n";
import { Logo } from "@plane/blocks/emoji-icon-picker";
import { Select } from "@plane/blocks/select";
import type { SelectVariant } from "@plane/blocks/select";
import type { TProjectCategory } from "@plane/types";
// hooks
import { useProjectCategories } from "@/hooks/store/jira-parity/use-project-categories";

const NO_CATEGORY = "__none__";

type TCategoryOption = Pick<TProjectCategory, "id" | "name" | "logo_props">;

type TProjectCategorySelectProps = {
  value: string | null | undefined;
  onChange: (categoryId: string | null) => void;
  variant?: SelectVariant;
  disabled?: boolean;
  tabIndex?: number;
  className?: string;
  /** Render nothing while the workspace has no categories (e.g. the project create modal). */
  hideWhenEmpty?: boolean;
};

export function ProjectCategoryIcon(props: {
  category?: Pick<TProjectCategory, "logo_props"> | null;
  className?: string;
}) {
  const { category, className = "size-3.5 shrink-0" } = props;
  if (category?.logo_props?.in_use) return <Logo logo={category.logo_props} size={14} />;
  return <ProjectsOutline className={className} />;
}

export const ProjectCategorySelect = observer(function ProjectCategorySelect(props: TProjectCategorySelectProps) {
  const { value, onChange, variant = "pill-md", disabled = false, tabIndex, className, hideWhenEmpty = false } = props;
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const { sortedCategories, getCategoryById } = useProjectCategories();
  // derived values
  const noCategoryOption: TCategoryOption = {
    id: NO_CATEGORY,
    name: t("jp_categories.select.none"),
    logo_props: {} as TProjectCategory["logo_props"],
  };
  const selectedCategory = getCategoryById(value ?? undefined);

  if (hideWhenEmpty && sortedCategories.length === 0 && !selectedCategory) return null;

  return (
    <Select<TCategoryOption>
      getValues={() => [noCategoryOption, ...sortedCategories]}
      value={selectedCategory ?? null}
      onChange={(categoryId) => onChange(!categoryId || categoryId === NO_CATEGORY ? null : categoryId)}
      getOptionValue={(category) => category.id}
      getOptionLabel={(category) => category.name}
      getOptionIcon={(category) => <ProjectCategoryIcon category={category} />}
      placeholder={t("jp_categories.select.placeholder")}
      emptyMessage={t("jp_categories.select.empty")}
      pinSelected={false}
      disabled={disabled}
    >
      <Select.Trigger<TCategoryOption>
        variant={variant}
        tabIndex={tabIndex}
        className={className}
        disabled={disabled}
        prependIcon={() => <ProjectCategoryIcon category={selectedCategory} />}
      >
        {() => (
          <span className="min-w-0 grow truncate text-left">
            {selectedCategory?.name ?? t("jp_categories.select.placeholder")}
          </span>
        )}
      </Select.Trigger>
    </Select>
  );
});
