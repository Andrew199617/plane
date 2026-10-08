/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: delete a team. Optionally also removes members from the projects they joined only
// through this team (never workspace admins, agents, project leads or default assignees).
// Owned by the teams feature.
import { useEffect, useState } from "react";
import { observer } from "mobx-react";
// plane imports
import { Checkbox } from "@makeplane/propel/components/checkbox";
import { ConfirmDialog } from "@plane/blocks/dialog";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import type { TTeam } from "@plane/types";
// hooks
import { useTeams } from "@/hooks/store/jira-parity/use-teams";
// local imports
import { getTeamErrorMessage } from "./helpers";

type TDeleteTeamModalProps = {
  workspaceSlug: string;
  team: TTeam | undefined;
  isOpen: boolean;
  onClose: () => void;
};

export const DeleteTeamModal = observer(function DeleteTeamModal(props: TDeleteTeamModalProps) {
  const { workspaceSlug, team, isOpen, onClose } = props;
  // states
  const [isDeleting, setIsDeleting] = useState(false);
  const [removeFromProjects, setRemoveFromProjects] = useState(true);
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const { deleteTeam } = useTeams();

  useEffect(() => {
    if (isOpen) setRemoveFromProjects(true);
  }, [isOpen]);

  const handleDelete = async () => {
    if (!team) return;
    setIsDeleting(true);
    try {
      await deleteTeam(workspaceSlug, team.id, removeFromProjects);
      setToast({ type: "success", title: t("jp_teams.toasts.success_title"), message: t("jp_teams.toasts.deleted") });
      onClose();
    } catch (error) {
      setToast({
        type: "error",
        title: t("jp_teams.toasts.error_title"),
        message: getTeamErrorMessage(error, t("jp_teams.toasts.error")),
      });
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <ConfirmDialog
      isOpen={isOpen}
      handleClose={onClose}
      handleSubmit={handleDelete}
      isSubmitting={isDeleting}
      isDisabled={!team}
      variant="danger"
      title={t("jp_teams.delete.title")}
      primaryButtonText={{ loading: t("jp_teams.delete.deleting"), default: t("jp_teams.delete.confirm") }}
      content={
        <div className="flex flex-col gap-3">
          <span>{t("jp_teams.delete.content", { name: team?.name ?? "" })}</span>
          <div className="flex flex-col gap-1">
            <Checkbox
              label={t("jp_teams.delete.remove_from_projects")}
              stretch="auto"
              checked={removeFromProjects}
              onCheckedChange={(checked) => setRemoveFromProjects(checked === true)}
            />
            <span className="pl-6 text-body-xs-regular text-tertiary">
              {t("jp_teams.delete.remove_from_projects_help")}
            </span>
          </div>
        </div>
      }
    />
  );
});
