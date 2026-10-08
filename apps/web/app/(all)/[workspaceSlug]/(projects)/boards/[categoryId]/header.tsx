/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: master board header (owned by the project-categories feature)
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
// components
import { CategoryBoardHeaderRoot } from "@/components/jira-parity/project-categories/board-header";

export const CategoryBoardHeader = observer(function CategoryBoardHeader() {
  // router
  const { workspaceSlug, categoryId } = useParams();

  if (!workspaceSlug || !categoryId) return null;
  return <CategoryBoardHeaderRoot workspaceSlug={workspaceSlug.toString()} categoryId={categoryId.toString()} />;
});
