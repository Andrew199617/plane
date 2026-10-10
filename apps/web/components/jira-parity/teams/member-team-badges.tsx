/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: the teams a workspace member belongs to, as small badges (member rows).
// Owned by the teams feature. Teams are loaded by useTeamsWorkspaceBootstrap.
import { observer } from "mobx-react";
// plane imports
import { Badge } from "@makeplane/propel/components/badge";
import { Tooltip } from "@makeplane/propel/components/tooltip";
import { JP_TEAM_BADGES_MAX_VISIBLE } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import { cn } from "@plane/utils";
// hooks
import { useTeams } from "@/hooks/store/jira-parity/use-teams";

type TMemberTeamBadgesProps = {
  userId: string;
  /** Only teams linked to this project. */
  projectId?: string;
  className?: string;
};

export const MemberTeamBadges = observer(function MemberTeamBadges(props: TMemberTeamBadgesProps) {
  const { userId, projectId, className } = props;
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const { getTeamsByMemberId } = useTeams();
  // derived values
  const teams = getTeamsByMemberId(userId).filter((team) => !projectId || team.project_ids.includes(projectId));
  if (teams.length === 0) return null;
  const visible = teams.slice(0, JP_TEAM_BADGES_MAX_VISIBLE);
  const hidden = teams.slice(JP_TEAM_BADGES_MAX_VISIBLE);

  return (
    <div className={cn("flex flex-wrap items-center gap-1", className)} data-testid={`member-team-badges-${userId}`}>
      {visible.map((team) => (
        <Badge key={team.id} variant="neutral" size="sm" label={team.name} />
      ))}
      {hidden.length > 0 && (
        <Tooltip label={hidden.map((team) => team.name).join(", ")}>
          <span>
            <Badge variant="neutral" size="sm" label={t("jp_teams.badges.more", { count: hidden.length })} />
          </span>
        </Tooltip>
      )}
    </div>
  );
});
