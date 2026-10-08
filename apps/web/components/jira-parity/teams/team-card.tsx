/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: one team on the Teams settings page — default project role, auto-join, members and
// the projects the team applies to. Admins edit inline; members see it read-only.
// Owned by the teams feature.
import { useRef, useState } from "react";
import type { ReactNode } from "react";
import { observer } from "mobx-react";
// plane imports
import { Badge } from "@makeplane/propel/components/badge";
import { Icon } from "@makeplane/propel/components/icon";
import { IconButton } from "@makeplane/propel/components/icon-button";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@makeplane/propel/components/menu";
import { Switch } from "@makeplane/propel/components/switch";
import { DeleteOutline, EditOutline, MoreHorizontalOutline, TeamspacesOutline } from "@makeplane/propel/icons";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import type { TTeam, TTeamPayload } from "@plane/types";
// components
import { MemberSelect } from "@/components/dropdowns/member/member-select";
import { ProjectSelect } from "@/components/dropdowns/project/project-select";
// hooks
import { useTeams } from "@/hooks/store/jira-parity/use-teams";
// local imports
import { getTeamErrorMessage, isSameIdSet } from "./helpers";
import { TeamRoleSelect } from "./team-role-select";

type TTeamCardRowProps = {
  label: string;
  hint?: string;
  children: ReactNode;
};

function TeamCardRow(props: TTeamCardRowProps) {
  const { label, hint, children } = props;
  return (
    <div className="grid grid-cols-1 items-start gap-1.5 py-2.5 sm:grid-cols-[200px_minmax(0,1fr)] sm:gap-4">
      <div className="flex flex-col gap-0.5 pt-1.5">
        <span className="text-body-xs-medium text-secondary">{label}</span>
        {hint && <span className="text-caption-md-regular text-tertiary">{hint}</span>}
      </div>
      <div className="flex min-w-0 flex-col gap-1">{children}</div>
    </div>
  );
}

type TTeamCardProps = {
  workspaceSlug: string;
  team: TTeam;
  isAdmin: boolean;
  onEdit: () => void;
  onDelete: () => void;
};

type TSavingField = "role" | "auto_join" | "members" | "projects";

export const TeamCard = observer(function TeamCard(props: TTeamCardProps) {
  const { workspaceSlug, team, isAdmin, onEdit, onDelete } = props;
  // states
  const [saving, setSaving] = useState<TSavingField | null>(null);
  // multi-select drafts: edited while the dropdown is open, committed in one request on close
  const [memberDraft, setMemberDraft] = useState<string[] | null>(null);
  const [projectDraft, setProjectDraft] = useState<string[] | null>(null);
  const memberDraftRef = useRef<string[] | null>(null);
  const projectDraftRef = useRef<string[] | null>(null);
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const { updateTeam } = useTeams();
  // derived values
  const isBusy = saving !== null;
  const canEdit = isAdmin && !isBusy;

  const save = async (field: TSavingField, payload: TTeamPayload, successMessage: string) => {
    setSaving(field);
    try {
      await updateTeam(workspaceSlug, team.id, payload);
      setToast({ type: "success", title: t("jp_teams.toasts.success_title"), message: successMessage });
    } catch (error) {
      setToast({
        type: "error",
        title: t("jp_teams.toasts.error_title"),
        message: getTeamErrorMessage(error, t("jp_teams.toasts.error")),
      });
    } finally {
      setSaving(null);
    }
  };

  const updateMemberDraft = (ids: string[]) => {
    memberDraftRef.current = ids;
    setMemberDraft(ids);
  };

  const updateProjectDraft = (ids: string[]) => {
    projectDraftRef.current = ids;
    setProjectDraft(ids);
  };

  const commitMembers = async () => {
    const draft = memberDraftRef.current;
    if (draft && !isSameIdSet(draft, team.member_ids)) {
      await save("members", { member_ids: draft }, t("jp_teams.toasts.members_updated"));
    }
    memberDraftRef.current = null;
    setMemberDraft(null);
  };

  const commitProjects = async () => {
    const draft = projectDraftRef.current;
    if (draft && !isSameIdSet(draft, team.project_ids)) {
      await save("projects", { project_ids: draft }, t("jp_teams.toasts.projects_updated"));
    }
    projectDraftRef.current = null;
    setProjectDraft(null);
  };

  return (
    <div className="rounded-lg border border-subtle bg-surface-1" data-testid={`team-card-${team.name}`}>
      {/* header */}
      <div className="flex items-start gap-3 border-b border-subtle px-4 py-3">
        <span className="grid size-8 shrink-0 place-items-center rounded-md bg-layer-1">
          <TeamspacesOutline className="size-4 text-secondary" />
        </span>
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="truncate text-body-sm-medium text-primary">{team.name}</span>
            <Badge variant="neutral" size="xs" label={t("jp_teams.card.member_count", { count: team.member_count })} />
            <Badge
              variant="neutral"
              size="xs"
              label={t("jp_teams.card.project_count", { count: team.project_ids.length })}
            />
            {team.auto_join && <Badge variant="brand" size="xs" label={t("jp_teams.card.auto_join")} />}
          </div>
          {team.description && <p className="text-body-xs-regular text-tertiary">{team.description}</p>}
        </div>
        {isAdmin && (
          <Menu>
            <MenuTrigger
              render={
                <IconButton
                  icon={<Icon icon={MoreHorizontalOutline} />}
                  aria-label={t("jp_teams.card.more_actions")}
                  variant="ghost"
                  size="sm"
                  data-testid={`team-actions-${team.name}`}
                />
              }
            />
            <MenuContent side="bottom" align="end">
              <MenuItem label={t("jp_teams.card.edit")} icon={<Icon icon={EditOutline} />} onClick={onEdit} />
              <MenuItem
                label={t("jp_teams.card.delete")}
                variant="danger"
                icon={<Icon icon={DeleteOutline} />}
                onClick={onDelete}
              />
            </MenuContent>
          </Menu>
        )}
      </div>
      {/* settings */}
      <div className="divide-y divide-subtle px-4">
        <TeamCardRow label={t("jp_teams.card.default_role")}>
          <TeamRoleSelect
            value={team.default_project_role}
            onChange={(role) => void save("role", { default_project_role: role }, t("jp_teams.toasts.updated"))}
            disabled={!canEdit}
            variant="select-ghost-md"
            className="w-48 max-w-full"
            testId={`team-role-${team.name}`}
          />
        </TeamCardRow>
        <TeamCardRow label={t("jp_teams.card.auto_join")} hint={t("jp_teams.form.auto_join_help")}>
          <div className="pt-1.5">
            <Switch
              size="sm"
              checked={team.auto_join}
              disabled={!canEdit}
              aria-label={t("jp_teams.card.auto_join")}
              onCheckedChange={(checked) =>
                void save("auto_join", { auto_join: checked }, t("jp_teams.toasts.updated"))
              }
            />
          </div>
        </TeamCardRow>
        <TeamCardRow label={t("jp_teams.card.members")}>
          {team.member_ids.length === 0 && !isAdmin ? (
            <span className="pt-1.5 text-body-xs-regular text-tertiary">{t("jp_teams.card.no_members")}</span>
          ) : (
            <MemberSelect
              testId={`team-members-${team.name}`}
              multiple
              value={memberDraft ?? team.member_ids}
              onChange={updateMemberDraft}
              onClose={() => void commitMembers()}
              variant={(memberDraft ?? team.member_ids).length > 0 ? "avatar-group-md" : "pill-md"}
              placeholder={t("jp_teams.card.add_members")}
              disabled={!canEdit}
            />
          )}
        </TeamCardRow>
        <TeamCardRow
          label={t("jp_teams.card.projects")}
          hint={team.auto_join ? t("jp_teams.card.all_projects") : undefined}
        >
          {team.project_ids.length === 0 && (!isAdmin || team.auto_join) ? (
            <span className="pt-1.5 text-body-xs-regular text-tertiary">{t("jp_teams.card.no_projects")}</span>
          ) : (
            <ProjectSelect
              multiple
              projectList="all"
              value={projectDraft ?? team.project_ids}
              onChange={updateProjectDraft}
              onClose={() => void commitProjects()}
              // `select` chrome lists the project names (the ghost/pill variants only show a count)
              variant="select-md"
              placeholder={t("jp_teams.card.add_projects")}
              disabled={!canEdit || team.auto_join}
              className="w-full"
            />
          )}
        </TeamCardRow>
      </div>
    </div>
  );
});
