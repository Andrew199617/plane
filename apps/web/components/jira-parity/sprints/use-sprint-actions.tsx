/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: Start / Complete sprint availability + dialogs for one sprint, shared by the list row buttons, the
// sprint detail header and the sprint quick-actions menu. Owned by the sprints feature.
import { useState } from "react";
import type { ReactNode } from "react";
import { CheckDoneOutline, PlayCircleOutline } from "@makeplane/propel/icons";
import type { TContextMenuItem } from "@plane/blocks/context-menu";
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import type { ICycle } from "@plane/types";
// hooks
import { useCycle } from "@/hooks/store/use-cycle";
import { useUserPermissions } from "@/hooks/store/user";
// local imports
import { CompleteSprintModal } from "./complete-sprint-modal";
import { isActiveSprint, isFutureSprint } from "./helpers";
import { StartSprintModal } from "./start-sprint-modal";

type TUseSprintActionsArgs = {
  workspaceSlug: string;
  projectId: string;
  cycleId: string;
};

export type TSprintActions = {
  cycle: ICycle | null;
  /** Future sprint + Admin / Member. */
  canStart: boolean;
  /** Active sprint + Admin / Member. */
  canComplete: boolean;
  /** Set when another sprint of the project is active (starting is blocked until it is completed). */
  startBlockedReason: string | undefined;
  openStart: () => void;
  openComplete: () => void;
  /** Start / Complete quick-action menu items (empty when neither applies). */
  menuItems: TContextMenuItem[];
  /** The dialogs; render them once next to whatever opens them. */
  modals: ReactNode;
};

/** Call from an observer component (reads the cycle store). */
export const useSprintActions = (args: TUseSprintActionsArgs): TSprintActions => {
  const { workspaceSlug, projectId, cycleId } = args;
  // states
  const [openModal, setOpenModal] = useState<"start" | "complete" | null>(null);
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const { getCycleById, getProjectCycleDetails } = useCycle();
  const { allowPermissions } = useUserPermissions();
  // derived values
  const cycle = cycleId ? getCycleById(cycleId) : null;
  const canManage = allowPermissions(
    [EUserPermissions.ADMIN, EUserPermissions.MEMBER],
    EUserPermissionsLevel.PROJECT,
    workspaceSlug,
    projectId
  );
  const canStart = canManage && isFutureSprint(cycle);
  const canComplete = canManage && isActiveSprint(cycle);
  const otherActiveSprint = canStart
    ? (getProjectCycleDetails(projectId) ?? []).find((sprint) => sprint.id !== cycleId && isActiveSprint(sprint))
    : undefined;
  const startBlockedReason = otherActiveSprint
    ? t("jp_sprints.actions.start_blocked", { name: otherActiveSprint.name })
    : undefined;

  const openStart = () => setOpenModal("start");
  const openComplete = () => setOpenModal("complete");
  const closeModal = () => setOpenModal(null);

  const menuItems: TContextMenuItem[] = [];
  if (canStart)
    menuItems.push({
      key: "start-sprint",
      title: t("jp_sprints.actions.start"),
      icon: PlayCircleOutline,
      action: openStart,
      disabled: !!startBlockedReason,
      description: startBlockedReason,
    });
  if (canComplete)
    menuItems.push({
      key: "complete-sprint",
      title: t("jp_sprints.actions.complete"),
      icon: CheckDoneOutline,
      action: openComplete,
    });

  const modals =
    cycle && (canStart || canComplete || openModal) ? (
      <>
        {(canStart || openModal === "start") && (
          <StartSprintModal
            workspaceSlug={workspaceSlug}
            projectId={projectId}
            cycle={cycle}
            isOpen={openModal === "start"}
            onClose={closeModal}
          />
        )}
        {(canComplete || openModal === "complete") && (
          <CompleteSprintModal
            workspaceSlug={workspaceSlug}
            projectId={projectId}
            cycle={cycle}
            isOpen={openModal === "complete"}
            onClose={closeModal}
          />
        )}
      </>
    ) : null;

  return { cycle, canStart, canComplete, startBlockedReason, openStart, openComplete, menuItems, modals };
};
