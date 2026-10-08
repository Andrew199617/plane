/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: workspace settings > Teams (owned by the teams feature).
// Lists the workspace teams; admins create / edit / delete teams and change members, projects,
// default project role and auto-join inline. Workspace members see the page read-only.
import { useMemo, useState } from "react";
import { observer } from "mobx-react";
import useSWR from "swr";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { SearchOutline } from "@makeplane/propel/icons";
import { EmptyStateDetailed } from "@plane/blocks/empty-state";
import { Loader } from "@plane/blocks/skeleton";
import { EUserPermissions, EUserPermissionsLevel, JP_TEAMS_SWR_KEY } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
// components
import { NotAuthorizedView } from "@/components/auth-screens/not-authorized-view";
// hooks
import { useTeams } from "@/hooks/store/jira-parity/use-teams";
import { useUserPermissions } from "@/hooks/store/user";
// local imports
import { DeleteTeamModal } from "./delete-team-modal";
import { teamMatchesQuery } from "./helpers";
import { TeamCard } from "./team-card";
import { TeamFormModal } from "./team-form-modal";

type TTeamsSettingsRootProps = {
  workspaceSlug: string;
};

type TTeamModalState = { type: "create" } | { type: "edit"; teamId: string } | { type: "delete"; teamId: string };

export const TeamsSettingsRoot = observer(function TeamsSettingsRoot(props: TTeamsSettingsRootProps) {
  const { workspaceSlug } = props;
  // states
  const [searchQuery, setSearchQuery] = useState("");
  const [modal, setModal] = useState<TTeamModalState | null>(null);
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const { sortedTeams, fetchedWorkspaceSlug, fetchTeams, getTeamById } = useTeams();
  const { workspaceUserInfo, allowPermissions } = useUserPermissions();
  // derived values
  const isAdmin = allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.WORKSPACE);
  const canView = allowPermissions([EUserPermissions.ADMIN, EUserPermissions.MEMBER], EUserPermissionsLevel.WORKSPACE);
  // always refresh on open (the workspace bootstrap shares this key)
  const { error, isLoading } = useSWR(
    workspaceSlug ? JP_TEAMS_SWR_KEY(workspaceSlug) : null,
    workspaceSlug ? () => fetchTeams(workspaceSlug) : null,
    { revalidateOnFocus: false, revalidateOnMount: true }
  );
  const isLoaded = fetchedWorkspaceSlug === workspaceSlug;
  const filteredTeams = useMemo(
    () => sortedTeams.filter((team) => teamMatchesQuery(team, searchQuery)),
    [sortedTeams, searchQuery]
  );
  const modalTeam = modal && modal.type !== "create" ? getTeamById(modal.teamId) : undefined;

  if (workspaceUserInfo && !canView) return <NotAuthorizedView section="settings" className="h-auto" />;

  const renderBody = () => {
    if (!isLoaded && (isLoading || !error)) {
      return (
        <Loader className="flex flex-col gap-3">
          <Loader.Item height="180px" />
          <Loader.Item height="180px" />
        </Loader>
      );
    }
    if (!isLoaded && error) {
      return <p className="text-body-sm-regular text-danger-primary">{t("jp_teams.toasts.error")}</p>;
    }
    if (sortedTeams.length === 0) {
      return (
        <EmptyStateDetailed
          assetKey="teamspace"
          title={t("jp_teams.empty_state.title")}
          description={t("jp_teams.empty_state.description")}
          actions={
            isAdmin
              ? [
                  {
                    label: t("jp_teams.toolbar.add_team"),
                    variant: "primary",
                    onClick: () => setModal({ type: "create" }),
                  },
                ]
              : undefined
          }
        />
      );
    }
    if (filteredTeams.length === 0) {
      return (
        <p className="rounded-md border border-dashed border-subtle px-4 py-8 text-center text-body-sm-regular text-tertiary">
          {t("jp_teams.empty_state.title")}
        </p>
      );
    }
    return (
      <div className="flex flex-col gap-4" data-testid="teams-list">
        {filteredTeams.map((team) => (
          <TeamCard
            key={team.id}
            workspaceSlug={workspaceSlug}
            team={team}
            isAdmin={isAdmin}
            onEdit={() => setModal({ type: "edit", teamId: team.id })}
            onDelete={() => setModal({ type: "delete", teamId: team.id })}
          />
        ))}
      </div>
    );
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-1.5 rounded-md border border-subtle bg-surface-1 px-2.5 py-1.5">
          <SearchOutline className="h-3.5 w-3.5 text-placeholder" />
          <input
            className="w-full max-w-[234px] border-none bg-transparent text-body-xs-regular outline-none placeholder:text-placeholder"
            placeholder={t("jp_teams.toolbar.search_placeholder")}
            aria-label={t("jp_teams.toolbar.search_placeholder")}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
        {isAdmin ? (
          <Button
            variant="primary"
            size="md"
            stretch="auto"
            label={t("jp_teams.toolbar.add_team")}
            onClick={() => setModal({ type: "create" })}
            data-testid="teams-add-team"
          />
        ) : (
          <span className="text-body-xs-regular text-tertiary">{t("jp_teams.toolbar.read_only")}</span>
        )}
      </div>
      {renderBody()}
      <TeamFormModal
        workspaceSlug={workspaceSlug}
        team={modal?.type === "edit" ? modalTeam : undefined}
        isOpen={modal?.type === "create" || (modal?.type === "edit" && !!modalTeam)}
        onClose={() => setModal(null)}
      />
      <DeleteTeamModal
        workspaceSlug={workspaceSlug}
        team={modal?.type === "delete" ? modalTeam : undefined}
        isOpen={modal?.type === "delete" && !!modalTeam}
        onClose={() => setModal(null)}
      />
    </div>
  );
});
