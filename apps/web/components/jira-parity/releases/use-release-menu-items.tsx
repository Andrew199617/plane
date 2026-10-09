/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: "Release" (unreleased) / "Unrelease" (released) quick-action items of a release (module),
// plus the Release modal they open. Merged into the module quick actions menu.
import { useState } from "react";
import type { JSX } from "react";
// plane imports
import { RocketOutline, UndoOutline } from "@makeplane/propel/icons";
import type { TContextMenuItem } from "@plane/blocks/context-menu";
import { setPromiseToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import type { IModule } from "@plane/types";
// hooks
import { useModule } from "@/hooks/store/use-module";
// local imports
import { getReleaseErrorMessage, isReleaseReleased } from "./helpers";
import { ReleaseModal } from "./release-modal";

type TUseReleaseMenuItemsProps = {
  moduleDetails: IModule | null | undefined;
  workspaceSlug: string;
  projectId: string;
  moduleId: string;
  isEditingAllowed: boolean;
};

export const useReleaseMenuItems = (
  props: TUseReleaseMenuItemsProps
): { items: TContextMenuItem[]; modals: JSX.Element | null } => {
  const { moduleDetails, workspaceSlug, projectId, moduleId, isEditingAllowed } = props;
  // states
  const [isReleaseModalOpen, setIsReleaseModalOpen] = useState(false);
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const { unreleaseModule } = useModule();
  // derived values
  const isArchived = !!moduleDetails?.archived_at;
  const isReleased = isReleaseReleased(moduleDetails);
  const canAct = !!moduleDetails && isEditingAllowed && !isArchived;

  const handleUnrelease = () => {
    if (!moduleDetails) return;
    const name = moduleDetails.name;
    const promise = unreleaseModule(workspaceSlug, projectId, moduleId);
    setPromiseToast(promise, {
      loading: t("jp_releases.toasts.unreleasing", { name }),
      success: {
        title: t("toast.success"),
        message: () => t("jp_releases.toasts.unreleased", { name }),
      },
      error: {
        title: t("toast.error"),
        message: (error) => getReleaseErrorMessage(error, t, t("jp_releases.toasts.unrelease_error", { name })),
      },
    });
  };

  const items: TContextMenuItem[] = [
    {
      key: "release",
      title: t("jp_releases.actions.release"),
      icon: RocketOutline,
      action: () => setIsReleaseModalOpen(true),
      shouldRender: canAct && !isReleased,
    },
    {
      key: "unrelease",
      title: t("jp_releases.actions.unrelease"),
      icon: UndoOutline,
      action: handleUnrelease,
      shouldRender: canAct && isReleased,
    },
  ].filter((item) => item.shouldRender !== false);

  const modals = moduleDetails ? (
    <ReleaseModal
      workspaceSlug={workspaceSlug}
      projectId={projectId}
      moduleId={moduleId}
      isOpen={isReleaseModalOpen}
      onClose={() => setIsReleaseModalOpen(false)}
    />
  ) : null;

  return { items, modals };
};
