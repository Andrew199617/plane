/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useContext } from "react";
// mobx store
import { StoreContext } from "@/lib/store-context";
import type { IWorkflowsStore } from "@/store/jira-parity/workflows.store";

export const useWorkflows = (): IWorkflowsStore => {
  const context = useContext(StoreContext);
  if (context === undefined) throw new Error("useWorkflows must be used within StoreProvider");
  return context.jiraParity.workflows;
};
