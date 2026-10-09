/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: the "Release" button of an unreleased, non-archived release (Admin/Member only). Opens the
// Release modal. Render it outside any row/card link — the modal portal still bubbles React events.
import { useState } from "react";
import { observer } from "mobx-react";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
// hooks
import { useModule } from "@/hooks/store/use-module";
import { useUserPermissions } from "@/hooks/store/user";
// local imports
import { isReleaseReleased } from "./helpers";
import { ReleaseModal } from "./release-modal";

type TReleaseActionButtonProps = {
  workspaceSlug: string;
  projectId: string;
  moduleId: string;
  size?: "sm" | "md";
  className?: string;
};

export const ReleaseActionButton = observer(function ReleaseActionButton(props: TReleaseActionButtonProps) {
  const { workspaceSlug, projectId, moduleId, size = "sm", className } = props;
  // states
  const [isModalOpen, setIsModalOpen] = useState(false);
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const { getModuleById } = useModule();
  const { allowPermissions } = useUserPermissions();
  // derived values
  const release = getModuleById(moduleId);
  const canRelease =
    !!release &&
    !release.archived_at &&
    !isReleaseReleased(release) &&
    allowPermissions(
      [EUserPermissions.ADMIN, EUserPermissions.MEMBER],
      EUserPermissionsLevel.PROJECT,
      workspaceSlug,
      projectId
    );

  if (!canRelease && !isModalOpen) return null;

  return (
    <>
      {canRelease && (
        <span className={className}>
          <Button
            variant="secondary"
            size={size}
            stretch="auto"
            label={t("jp_releases.actions.release")}
            data-testid="release-action-button"
            onClick={(event) => {
              event.stopPropagation();
              event.preventDefault();
              setIsModalOpen(true);
            }}
          />
        </span>
      )}
      <ReleaseModal
        workspaceSlug={workspaceSlug}
        projectId={projectId}
        moduleId={moduleId}
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
      />
    </>
  );
});
