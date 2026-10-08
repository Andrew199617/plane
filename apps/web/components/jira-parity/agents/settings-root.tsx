/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: workspace settings > Agents (owned by the agents feature). Workspace admins only:
// list agent accounts, create one (its API token is shown once), issue / rotate / revoke tokens,
// rename and deactivate.
import { useState } from "react";
import { observer } from "mobx-react";
import useSWR from "swr";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { Icon } from "@makeplane/propel/components/icon";
import { AddOutline, AgentOutline } from "@makeplane/propel/icons";
import { ConfirmDialog } from "@plane/blocks/dialog";
import { Loader } from "@plane/blocks/skeleton";
import { setToast } from "@plane/blocks/toast";
import { EUserPermissions, EUserPermissionsLevel, JP_AGENTS_SWR_KEY } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import type { TWorkspaceAgent, TWorkspaceAgentCreateResponse, TWorkspaceAgentToken } from "@plane/types";
// components
import { NotAuthorizedView } from "@/components/auth-screens/not-authorized-view";
// hooks
import { useAgents } from "@/hooks/store/jira-parity/use-agents";
import { useUserPermissions } from "@/hooks/store/user";
// local imports
import { AgentListItem } from "./agent-list-item";
import { CreateAgentModal } from "./create-agent-modal";
import { getAgentApiErrorMessage } from "./helpers";
import { RenameAgentModal } from "./rename-agent-modal";
import type { TRevealedAgentToken } from "./token-reveal-modal";
import { AgentTokenRevealModal } from "./token-reveal-modal";

type TAgentsSettingsRootProps = {
  workspaceSlug: string;
};

type TPendingAgentAction =
  | { kind: "deactivate"; agent: TWorkspaceAgent }
  | { kind: "revoke"; agent: TWorkspaceAgent; token: TWorkspaceAgentToken }
  | { kind: "rotate"; agent: TWorkspaceAgent; token: TWorkspaceAgentToken };

export const AgentsSettingsRoot = observer(function AgentsSettingsRoot(props: TAgentsSettingsRootProps) {
  const { workspaceSlug } = props;
  // states
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [renamingAgentId, setRenamingAgentId] = useState<string | null>(null);
  const [revealedToken, setRevealedToken] = useState<TRevealedAgentToken | null>(null);
  const [pendingAction, setPendingAction] = useState<TPendingAgentAction | null>(null);
  const [isConfirming, setIsConfirming] = useState(false);
  const [generatingTokenFor, setGeneratingTokenFor] = useState<string | null>(null);
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const {
    sortedAgents,
    fetchedWorkspaceSlug,
    fetchAgents,
    getAgentByUserId,
    deactivateAgent,
    createToken,
    revokeToken,
    rotateToken,
  } = useAgents();
  const { workspaceUserInfo, allowPermissions } = useUserPermissions();
  // derived values
  const isAdmin = allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.WORKSPACE);
  const { error, isLoading } = useSWR(
    workspaceSlug && isAdmin ? JP_AGENTS_SWR_KEY(workspaceSlug) : null,
    workspaceSlug && isAdmin ? () => fetchAgents(workspaceSlug) : null,
    { revalidateOnFocus: false, revalidateOnMount: true, shouldRetryOnError: false }
  );
  const isLoaded = fetchedWorkspaceSlug === workspaceSlug;

  if (workspaceUserInfo && !isAdmin) return <NotAuthorizedView section="settings" className="h-auto" />;

  const handleCreated = (agent: TWorkspaceAgentCreateResponse) => {
    if (agent?.token) setRevealedToken({ agentName: agent.member?.display_name ?? "", token: agent.token });
  };

  const handleGenerateToken = async (agent: TWorkspaceAgent) => {
    setGeneratingTokenFor(agent.member.id);
    try {
      const response = await createToken(workspaceSlug, agent.member.id, {});
      if (response?.token) setRevealedToken({ agentName: agent.member.display_name, token: response.token });
    } catch (err) {
      setToast({
        type: "error",
        title: t("jp_agents.token.generate_error"),
        message: getAgentApiErrorMessage(err, "") || undefined,
      });
    } finally {
      setGeneratingTokenFor(null);
    }
  };

  const handleConfirm = async () => {
    if (!pendingAction) return;
    const { agent } = pendingAction;
    setIsConfirming(true);
    try {
      if (pendingAction.kind === "deactivate") {
        await deactivateAgent(workspaceSlug, agent.member.id);
        setToast({ type: "success", title: t("jp_agents.deactivate.success") });
      } else if (pendingAction.kind === "revoke") {
        await revokeToken(workspaceSlug, agent.member.id, pendingAction.token.id);
        setToast({ type: "success", title: t("jp_agents.token.revoke.success") });
      } else {
        const response = await rotateToken(workspaceSlug, agent.member.id, pendingAction.token.id);
        if (response?.token) setRevealedToken({ agentName: agent.member.display_name, token: response.token });
      }
      setPendingAction(null);
    } catch (err) {
      const fallback =
        pendingAction.kind === "deactivate"
          ? t("jp_agents.deactivate.error")
          : pendingAction.kind === "revoke"
            ? t("jp_agents.token.revoke.error")
            : t("jp_agents.token.rotate.error");
      setToast({ type: "error", title: fallback, message: getAgentApiErrorMessage(err, "") || undefined });
    } finally {
      setIsConfirming(false);
    }
  };

  const confirmCopy = (() => {
    if (!pendingAction) return null;
    if (pendingAction.kind === "deactivate")
      return {
        title: t("jp_agents.deactivate.title", { name: pendingAction.agent.member.display_name }),
        content: t("jp_agents.deactivate.description"),
        loading: t("jp_agents.deactivate.confirming"),
        default: t("jp_agents.deactivate.confirm"),
        variant: "danger" as const,
      };
    if (pendingAction.kind === "revoke")
      return {
        title: t("jp_agents.token.revoke.title"),
        content: t("jp_agents.token.revoke.description"),
        loading: t("jp_agents.token.revoke.confirming"),
        default: t("jp_agents.token.revoke.confirm"),
        variant: "danger" as const,
      };
    return {
      title: t("jp_agents.token.rotate.title"),
      content: t("jp_agents.token.rotate.description"),
      loading: t("jp_agents.token.rotate.confirming"),
      default: t("jp_agents.token.rotate.confirm"),
      variant: "warning" as const,
    };
  })();

  const renderList = () => {
    if (!isLoaded && (isLoading || !error)) {
      return (
        <Loader className="flex flex-col gap-2">
          <Loader.Item height="56px" />
          <Loader.Item height="56px" />
        </Loader>
      );
    }
    if (!isLoaded && error) {
      return <p className="text-body-sm-regular text-danger-primary">{t("jp_agents.load_error")}</p>;
    }
    if (sortedAgents.length === 0) {
      return (
        <div
          className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-subtle px-6 py-10 text-center"
          data-testid="agents-empty-state"
        >
          <Icon icon={AgentOutline} />
          <p className="text-body-sm-medium text-primary">{t("jp_agents.list.empty_title")}</p>
          <p className="max-w-md text-body-xs-regular text-tertiary">{t("jp_agents.list.empty_description")}</p>
        </div>
      );
    }
    return (
      <div className="divide-y divide-subtle rounded-lg border border-subtle" data-testid="agents-list">
        {sortedAgents.map((agent) => (
          <AgentListItem
            key={agent.member.id}
            agent={agent}
            isGeneratingToken={generatingTokenFor === agent.member.id}
            onGenerateToken={(item) => void handleGenerateToken(item)}
            onRename={(item) => setRenamingAgentId(item.member.id)}
            onDeactivate={(item) => setPendingAction({ kind: "deactivate", agent: item })}
            onRevokeToken={(item, token) => setPendingAction({ kind: "revoke", agent: item, token })}
            onRotateToken={(item, token) => setPendingAction({ kind: "rotate", agent: item, token })}
          />
        ))}
      </div>
    );
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="max-w-2xl text-body-xs-regular text-tertiary">{t("jp_agents.permissions_note")}</p>
        <Button
          variant="primary"
          size="md"
          stretch="auto"
          icon={<Icon icon={AddOutline} />}
          label={t("jp_agents.list.add_agent")}
          onClick={() => setIsCreateModalOpen(true)}
          data-testid="add-agent-button"
        />
      </div>
      {renderList()}
      <CreateAgentModal
        workspaceSlug={workspaceSlug}
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        onCreated={handleCreated}
      />
      <RenameAgentModal
        workspaceSlug={workspaceSlug}
        agent={getAgentByUserId(renamingAgentId)}
        onClose={() => setRenamingAgentId(null)}
      />
      <AgentTokenRevealModal revealedToken={revealedToken} onClose={() => setRevealedToken(null)} />
      {confirmCopy && (
        <ConfirmDialog
          isOpen={!!pendingAction}
          handleClose={() => {
            if (!isConfirming) setPendingAction(null);
          }}
          handleSubmit={handleConfirm}
          isSubmitting={isConfirming}
          title={confirmCopy.title}
          content={confirmCopy.content}
          variant={confirmCopy.variant}
          primaryButtonText={{ loading: confirmCopy.loading, default: confirmCopy.default }}
          secondaryButtonText={t("jp_agents.create.cancel")}
        />
      )}
    </div>
  );
});
