/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useContext } from "react";
// mobx store
import { StoreContext } from "@/lib/store-context";
import type { IProjectCategoriesStore } from "@/store/jira-parity/project-categories.store";

export const useProjectCategories = (): IProjectCategoriesStore => {
  const context = useContext(StoreContext);
  if (context === undefined) throw new Error("useProjectCategories must be used within StoreProvider");
  return context.jiraParity.projectCategories;
};
