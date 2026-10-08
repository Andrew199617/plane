/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: master board page /:workspaceSlug/boards/:categoryId (owned by the project-categories feature)
import { observer } from "mobx-react";
// plane imports
import { useTranslation } from "@plane/i18n";
// components
import { PageHead } from "@/components/core/page-title";
import { CategoryBoardRoot } from "@/components/jira-parity/project-categories";
// hooks
import { useProjectCategories } from "@/hooks/store/jira-parity/use-project-categories";
// local imports
import type { Route } from "./+types/page";

function CategoryBoardPage({ params }: Route.ComponentProps) {
  const { workspaceSlug, categoryId } = params;
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const { getCategoryById } = useProjectCategories();
  // derived values
  const category = getCategoryById(categoryId);
  const pageTitle = category?.name
    ? `${category.name} - ${t("jp_categories.board.title")}`
    : t("jp_categories.board.title");

  return (
    <>
      <PageHead title={pageTitle} />
      <div className="relative h-full w-full overflow-hidden overflow-y-auto">
        <CategoryBoardRoot workspaceSlug={workspaceSlug} categoryId={categoryId} />
      </div>
    </>
  );
}

export default observer(CategoryBoardPage);
