/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useContext } from "react";
// mobx store
import { StoreContext } from "@/lib/store-context";
import type { IJiraParityRootStore } from "@/store/jira-parity/root.store";

export const useJiraParity = (): IJiraParityRootStore => {
  const context = useContext(StoreContext);
  if (context === undefined) throw new Error("useJiraParity must be used within StoreProvider");
  return context.jiraParity;
};
