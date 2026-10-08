/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: create / edit a team (name, description, default project role, auto-join, members,
// projects). Workspace admins only. Owned by the teams feature.
import { useEffect } from "react";
import { observer } from "mobx-react";
import { Controller, useForm } from "react-hook-form";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import {
  Dialog,
  DialogActions,
  DialogBody,
  DialogContent,
  DialogHeader,
  DialogHeading,
  DialogMain,
  DialogTitle,
} from "@makeplane/propel/components/dialog";
import { InputField } from "@makeplane/propel/components/input-field";
import { SwitchField } from "@makeplane/propel/components/switch-field";
import { TextAreaField } from "@makeplane/propel/components/text-area-field";
import { setToast } from "@plane/blocks/toast";
import { JP_TEAM_DEFAULT_PROJECT_ROLE } from "@plane/constants";
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

const NAME_MAX_LENGTH = 255;

type TTeamFormValues = {
  name: string;
  description: string;
  default_project_role: number;
  auto_join: boolean;
  member_ids: string[];
  project_ids: string[];
};

const getFormValues = (team: TTeam | undefined): TTeamFormValues => ({
  name: team?.name ?? "",
  description: team?.description ?? "",
  default_project_role: team?.default_project_role ?? JP_TEAM_DEFAULT_PROJECT_ROLE,
  auto_join: team?.auto_join ?? false,
  member_ids: team?.member_ids ?? [],
  project_ids: team?.project_ids ?? [],
});

/** Only the fields that changed (create: everything that is set). */
const buildPayload = (values: TTeamFormValues, team: TTeam | undefined): TTeamPayload => {
  const name = values.name.trim();
  const description = values.description.trim();
  if (!team) {
    return {
      name,
      description,
      default_project_role: values.default_project_role,
      auto_join: values.auto_join,
      member_ids: values.member_ids,
      ...(values.auto_join ? {} : { project_ids: values.project_ids }),
    };
  }
  const payload: TTeamPayload = {};
  if (name !== team.name) payload.name = name;
  if (description !== (team.description ?? "")) payload.description = description;
  if (values.default_project_role !== team.default_project_role)
    payload.default_project_role = values.default_project_role;
  if (values.auto_join !== team.auto_join) payload.auto_join = values.auto_join;
  if (!isSameIdSet(values.member_ids, team.member_ids)) payload.member_ids = values.member_ids;
  if (!values.auto_join && !isSameIdSet(values.project_ids, team.project_ids)) payload.project_ids = values.project_ids;
  return payload;
};

type TTeamFormModalProps = {
  workspaceSlug: string;
  /** undefined = create a new team */
  team: TTeam | undefined;
  isOpen: boolean;
  onClose: () => void;
};

export const TeamFormModal = observer(function TeamFormModal(props: TTeamFormModalProps) {
  const { workspaceSlug, team, isOpen, onClose } = props;
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const { createTeam, updateTeam } = useTeams();
  // form
  const {
    control,
    handleSubmit,
    reset,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<TTeamFormValues>({ defaultValues: getFormValues(team) });
  // derived values
  const isEditing = !!team;
  const autoJoin = watch("auto_join");

  // re-seed the form whenever the modal opens (not on every store refresh of the team)
  useEffect(() => {
    if (isOpen) reset(getFormValues(team));
    // oxlint-disable-next-line eslint-plugin-react-hooks/exhaustive-deps
  }, [isOpen, team?.id, reset]);

  const onSubmit = async (values: TTeamFormValues) => {
    try {
      if (team) {
        const payload = buildPayload(values, team);
        if (Object.keys(payload).length > 0) await updateTeam(workspaceSlug, team.id, payload);
      } else {
        await createTeam(workspaceSlug, buildPayload(values, undefined));
      }
      setToast({
        type: "success",
        title: t("jp_teams.toasts.success_title"),
        message: isEditing ? t("jp_teams.toasts.updated") : t("jp_teams.toasts.created"),
      });
      onClose();
    } catch (error) {
      setToast({
        type: "error",
        title: t("jp_teams.toasts.error_title"),
        message: getTeamErrorMessage(error, t("jp_teams.toasts.error")),
      });
    }
  };

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent size="md">
        <form onSubmit={handleSubmit(onSubmit)} className="flex min-h-0 flex-1 flex-col" data-testid="team-form">
          <DialogMain>
            <DialogHeader>
              <DialogHeading>
                <DialogTitle>{isEditing ? t("jp_teams.form.edit_title") : t("jp_teams.form.create_title")}</DialogTitle>
              </DialogHeading>
            </DialogHeader>
            <DialogBody>
              <div className="flex flex-col gap-5">
                <Controller
                  control={control}
                  name="name"
                  rules={{
                    validate: (value) => value.trim().length > 0 || t("jp_teams.form.name_required"),
                    maxLength: { value: NAME_MAX_LENGTH, message: t("jp_teams.form.name_max_length") },
                  }}
                  render={({ field: { value, onChange, ref } }) => (
                    <InputField
                      id="team-name"
                      name="name"
                      ref={ref}
                      value={value}
                      onChange={onChange}
                      size="lg"
                      orientation="vertical"
                      label={t("jp_teams.form.name")}
                      placeholder={t("jp_teams.form.name_placeholder")}
                      required
                      error={errors.name?.message}
                    />
                  )}
                />
                <Controller
                  control={control}
                  name="description"
                  render={({ field: { value, onChange } }) => (
                    <TextAreaField
                      id="team-description"
                      name="description"
                      value={value}
                      onChange={onChange}
                      size="lg"
                      label={t("jp_teams.form.description")}
                      placeholder={t("jp_teams.form.description_placeholder")}
                      autoResize
                      maxRows={4}
                    />
                  )}
                />
                <Controller
                  control={control}
                  name="default_project_role"
                  render={({ field: { value, onChange } }) => (
                    <div className="flex flex-col gap-1.5">
                      <span className="text-body-xs-medium text-secondary">{t("jp_teams.form.default_role")}</span>
                      <TeamRoleSelect value={value} onChange={onChange} testId="team-form-role" />
                      <span className="text-body-xs-regular text-tertiary">{t("jp_teams.form.default_role_help")}</span>
                    </div>
                  )}
                />
                <Controller
                  control={control}
                  name="auto_join"
                  render={({ field: { value, onChange } }) => (
                    <SwitchField
                      name="auto_join"
                      size="lg"
                      switchSize="sm"
                      label={t("jp_teams.form.auto_join")}
                      description={t("jp_teams.form.auto_join_help")}
                      checked={value}
                      onCheckedChange={(checked) => onChange(checked)}
                    />
                  )}
                />
                <Controller
                  control={control}
                  name="member_ids"
                  render={({ field: { value, onChange } }) => (
                    <div className="flex flex-col gap-1.5">
                      <span className="text-body-xs-medium text-secondary">{t("jp_teams.form.members")}</span>
                      <MemberSelect
                        testId="team-form-members"
                        multiple
                        value={value}
                        onChange={onChange}
                        variant="select-lg"
                        placeholder={t("jp_teams.form.members_placeholder")}
                        className="w-full"
                      />
                    </div>
                  )}
                />
                {!autoJoin && (
                  <Controller
                    control={control}
                    name="project_ids"
                    render={({ field: { value, onChange } }) => (
                      <div className="flex flex-col gap-1.5">
                        <span className="text-body-xs-medium text-secondary">{t("jp_teams.form.projects")}</span>
                        <ProjectSelect
                          multiple
                          projectList="all"
                          value={value}
                          onChange={onChange}
                          variant="select-lg"
                          placeholder={t("jp_teams.form.projects_placeholder")}
                          className="w-full"
                        />
                      </div>
                    )}
                  />
                )}
              </div>
            </DialogBody>
          </DialogMain>
          <DialogActions>
            <Button variant="secondary" size="md" stretch="auto" label={t("jp_teams.form.cancel")} onClick={onClose} />
            <Button
              variant="primary"
              size="md"
              stretch="auto"
              type="submit"
              loading={isSubmitting}
              disabled={isSubmitting}
              data-testid="team-form-submit"
              label={
                isEditing
                  ? isSubmitting
                    ? t("jp_teams.form.saving")
                    : t("jp_teams.form.save")
                  : isSubmitting
                    ? t("jp_teams.form.creating")
                    : t("jp_teams.form.create")
              }
            />
          </DialogActions>
        </form>
      </DialogContent>
    </Dialog>
  );
});
