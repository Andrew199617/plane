/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: project settings > Workflows (owned by the workflows feature). Project admins only (the
// page checks it): enable/disable the workflow and edit the allowed state transitions per role.
import { useEffect, useMemo, useState } from "react";
import { observer } from "mobx-react";
import useSWR from "swr";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { Switch } from "@makeplane/propel/components/switch";
import { Tab, Tabs, TabsList, TabsPanel } from "@makeplane/propel/components/tabs";
import { Loader } from "@plane/blocks/skeleton";
import { setToast } from "@plane/blocks/toast";
import { JP_PROJECT_STATE_TRANSITIONS_SWR_KEY, JP_ROLES } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
// components
import { getAgentApiErrorMessage } from "@/components/jira-parity/agents/helpers";
import { SettingsControlItem } from "@/components/settings/control-item";
// hooks
import { useWorkflows } from "@/hooks/store/jira-parity/use-workflows";
import { useProject } from "@/hooks/store/use-project";
import { useProjectState } from "@/hooks/store/use-project-state";
// local imports
import type { TWorkflowDraft } from "./helpers";
import {
  getRoleEpicScope,
  getRulesSignature,
  rulesToWorkflowDraft,
  setRoleExcludeEpics,
  toggleWorkflowCell,
  WORKFLOW_AGENT_ROLE,
  WORKFLOW_EDITABLE_ROLES,
  workflowDraftToRules,
} from "./helpers";
import { WorkflowTransitionMatrix } from "./transition-matrix";

type TWorkflowsSettingsRootProps = {
  workspaceSlug: string;
  projectId: string;
};

type TWorkflowRoleKey = "member" | "agent" | "guest";

const ROLE_KEYS: Record<number, TWorkflowRoleKey> = {
  [JP_ROLES.MEMBER]: "member",
  [JP_ROLES.AGENT]: "agent",
  [JP_ROLES.GUEST]: "guest",
};

export const WorkflowsSettingsRoot = observer(function WorkflowsSettingsRoot(props: TWorkflowsSettingsRootProps) {
  const { workspaceSlug, projectId } = props;
  // states
  const [activeRole, setActiveRole] = useState<number>(WORKFLOW_AGENT_ROLE);
  const [draft, setDraft] = useState<TWorkflowDraft | null>(null);
  // a role without rules has no cells to carry its epic scope, so remember the switch per role
  const [emptyRoleAppliesToEpics, setEmptyRoleAppliesToEpics] = useState<Record<number, boolean>>({});
  const [isSaving, setIsSaving] = useState(false);
  const [isToggling, setIsToggling] = useState(false);
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const { fetchTransitionRules, getTransitionRules, replaceTransitionRules, setWorkflowEnabled } = useWorkflows();
  const { fetchProjectStates, getProjectStates } = useProjectState();
  const { getProjectById } = useProject();
  // fetching
  const { error: rulesError } = useSWR(
    workspaceSlug && projectId ? JP_PROJECT_STATE_TRANSITIONS_SWR_KEY(projectId) : null,
    workspaceSlug && projectId ? () => fetchTransitionRules(workspaceSlug, projectId) : null,
    { revalidateOnFocus: false, revalidateOnMount: true, shouldRetryOnError: false }
  );
  useSWR(
    workspaceSlug && projectId ? `JP_WORKFLOW_PROJECT_STATES_${projectId}` : null,
    workspaceSlug && projectId ? () => fetchProjectStates(workspaceSlug, projectId) : null,
    { revalidateOnFocus: false }
  );
  // derived values
  const rules = getTransitionRules(projectId);
  const projectStates = getProjectStates(projectId);
  const states = useMemo(
    () => (projectStates ?? []).filter((state) => (state.group as string) !== "triage"),
    [projectStates]
  );
  const isWorkflowEnabled = !!getProjectById(projectId)?.is_workflow_enabled;
  const rulesSignature = rules ? getRulesSignature(rules) : null;
  const draftSignature = draft && rules ? getRulesSignature(workflowDraftToRules(draft, rules)) : null;
  const isDirty = !!draftSignature && draftSignature !== rulesSignature;

  // (re)seed the draft from the server rules whenever they change (first load, after a save)
  useEffect(() => {
    if (rules) setDraft(rulesToWorkflowDraft(rules));
    // oxlint-disable-next-line eslint-plugin-react-hooks/exhaustive-deps
  }, [rulesSignature]);

  const roleLabel = (role: number) => t(`jp_workflows.roles.${ROLE_KEYS[role]}`);

  const updateRoleCells = (role: number, updater: (cells: TWorkflowDraft[number]) => TWorkflowDraft[number]) =>
    setDraft((current) => (current ? { ...current, [role]: updater(current[role] ?? {}) } : current));

  const roleAppliesToEpics = (role: number): boolean => {
    if (role === WORKFLOW_AGENT_ROLE) return false;
    const scope = getRoleEpicScope(draft?.[role]);
    if (scope === "empty") return emptyRoleAppliesToEpics[role] ?? true;
    return scope !== "exclude";
  };

  const handleToggleCell = (role: number, fromStateId: string | null, toStateId: string) =>
    updateRoleCells(role, (cells) => toggleWorkflowCell(cells, fromStateId, toStateId, !roleAppliesToEpics(role)));

  const handleEpicScopeChange = (role: number, appliesToEpics: boolean) => {
    setEmptyRoleAppliesToEpics((current) => ({ ...current, [role]: appliesToEpics }));
    updateRoleCells(role, (cells) => setRoleExcludeEpics(cells, !appliesToEpics));
  };

  const handleSave = async () => {
    if (!draft || !rules) return;
    setIsSaving(true);
    try {
      await replaceTransitionRules(workspaceSlug, projectId, workflowDraftToRules(draft, rules));
      setToast({
        type: "success",
        title: t("jp_workflows.toast.saved_title"),
        message: t("jp_workflows.toast.saved_message"),
      });
    } catch (error) {
      setToast({
        type: "error",
        title: t("jp_workflows.toast.save_error"),
        message: getAgentApiErrorMessage(error, "") || undefined,
      });
    } finally {
      setIsSaving(false);
    }
  };

  const handleDiscard = () => {
    if (rules) setDraft(rulesToWorkflowDraft(rules));
  };

  const handleToggleWorkflow = async (isEnabled: boolean) => {
    setIsToggling(true);
    try {
      await setWorkflowEnabled(workspaceSlug, projectId, isEnabled);
      setToast({
        type: "success",
        title: isEnabled ? t("jp_workflows.enable.enabled") : t("jp_workflows.enable.disabled"),
      });
    } catch (error) {
      setToast({
        type: "error",
        title: t("jp_workflows.enable.error"),
        message: getAgentApiErrorMessage(error, "") || undefined,
      });
    } finally {
      setIsToggling(false);
    }
  };

  if (!rules && rulesError) {
    return <p className="text-body-sm-regular text-danger-primary">{t("jp_workflows.load_error")}</p>;
  }

  if (!rules || !draft || !projectStates) {
    return (
      <Loader className="flex flex-col gap-3">
        <Loader.Item height="56px" />
        <Loader.Item height="240px" />
      </Loader>
    );
  }

  return (
    <div className="flex flex-col gap-6" data-testid="workflows-settings">
      <div className="flex flex-col gap-2 border-b border-subtle pb-2">
        <SettingsControlItem
          title={t("jp_workflows.enable.title")}
          description={t("jp_workflows.enable.description")}
          control={
            <Switch
              size="sm"
              checked={isWorkflowEnabled}
              disabled={isToggling}
              onCheckedChange={(checked) => void handleToggleWorkflow(checked)}
              aria-label={t("jp_workflows.enable.title")}
              data-testid="workflow-enabled-switch"
            />
          }
        />
        {!isWorkflowEnabled && (
          <p className="text-body-xs-regular text-tertiary">{t("jp_workflows.enable.off_notice")}</p>
        )}
        <p className="text-body-xs-regular text-tertiary">{t("jp_workflows.admin_note")}</p>
      </div>

      {states.length === 0 ? (
        <p className="text-body-sm-regular text-tertiary">{t("jp_workflows.no_states")}</p>
      ) : (
        <Tabs
          variant="underline"
          value={String(activeRole)}
          onValueChange={(value: string) => setActiveRole(Number(value))}
        >
          <TabsList>
            {WORKFLOW_EDITABLE_ROLES.map((role) => (
              <Tab key={role} value={String(role)} label={roleLabel(role)} />
            ))}
          </TabsList>
          {WORKFLOW_EDITABLE_ROLES.map((role) => {
            const cells = draft[role] ?? {};
            const cellCount = Object.keys(cells).length;
            const isAgentRole = role === WORKFLOW_AGENT_ROLE;
            const epicScope = getRoleEpicScope(cells);
            return (
              <TabsPanel key={role} value={String(role)}>
                <div className="flex flex-col gap-4 pt-4" data-testid={`workflow-role-${role}`}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-body-xs-regular text-secondary">
                      {cellCount > 0
                        ? t("jp_workflows.matrix.count", { count: cellCount })
                        : t(`jp_workflows.no_rules.${ROLE_KEYS[role]}`)}
                    </p>
                    {cellCount > 0 && (
                      <Button
                        variant="ghost"
                        size="sm"
                        stretch="auto"
                        label={t("jp_workflows.actions.clear")}
                        disabled={isSaving}
                        onClick={() => updateRoleCells(role, () => ({}))}
                      />
                    )}
                  </div>
                  <WorkflowTransitionMatrix
                    roleLabel={roleLabel(role)}
                    states={states}
                    cells={cells}
                    disabled={isSaving}
                    onToggleCell={(fromStateId, toStateId) => handleToggleCell(role, fromStateId, toStateId)}
                  />
                  <SettingsControlItem
                    title={t("jp_workflows.epics.title")}
                    description={
                      isAgentRole
                        ? t("jp_workflows.epics.agent_locked")
                        : epicScope === "mixed"
                          ? t("jp_workflows.epics.mixed")
                          : t("jp_workflows.epics.description")
                    }
                    control={
                      <Switch
                        size="sm"
                        checked={roleAppliesToEpics(role)}
                        disabled={isAgentRole || isSaving}
                        onCheckedChange={(checked) => handleEpicScopeChange(role, checked)}
                        aria-label={t("jp_workflows.epics.title")}
                      />
                    }
                  />
                </div>
              </TabsPanel>
            );
          })}
        </Tabs>
      )}

      <div className="flex flex-wrap items-center justify-end gap-2 border-t border-subtle pt-4">
        <Button
          variant="secondary"
          size="md"
          stretch="auto"
          label={t("jp_workflows.actions.discard")}
          disabled={!isDirty || isSaving}
          onClick={handleDiscard}
        />
        <Button
          variant="primary"
          size="md"
          stretch="auto"
          label={isSaving ? t("jp_workflows.actions.saving") : t("jp_workflows.actions.save")}
          loading={isSaving}
          disabled={!isDirty || isSaving}
          onClick={() => void handleSave()}
          data-testid="workflow-save"
        />
      </div>
    </div>
  );
});
