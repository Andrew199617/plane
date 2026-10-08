/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: one agent row on the agents settings page, with its API tokens. Owned by the agents feature.
import { useState } from "react";
import { observer } from "mobx-react";
// plane imports
import { Badge } from "@makeplane/propel/components/badge";
import { Button } from "@makeplane/propel/components/button";
import { Icon } from "@makeplane/propel/components/icon";
import { IconButton } from "@makeplane/propel/components/icon-button";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@makeplane/propel/components/menu";
import {
  ChevronDownOutline,
  ChevronRightOutline,
  DeactivatedUserOutline,
  EditOutline,
  KeyOutline,
  MoreHorizontalOutline,
  RefreshOutline,
} from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
import type { TWorkspaceAgent, TWorkspaceAgentToken } from "@plane/types";
import { calculateTimeAgo, cn, getFileURL, renderFormattedDate } from "@plane/utils";
// local imports
import { getActiveAgentTokens, getAgentInitial, isAgentTokenUsable, sortAgentTokens } from "./helpers";

export type TAgentListItemProps = {
  agent: TWorkspaceAgent;
  isGeneratingToken: boolean;
  onGenerateToken: (agent: TWorkspaceAgent) => void;
  onRename: (agent: TWorkspaceAgent) => void;
  onDeactivate: (agent: TWorkspaceAgent) => void;
  onRevokeToken: (agent: TWorkspaceAgent, token: TWorkspaceAgentToken) => void;
  onRotateToken: (agent: TWorkspaceAgent, token: TWorkspaceAgentToken) => void;
};

type TAgentTokenRowProps = {
  token: TWorkspaceAgentToken;
  onRevoke: () => void;
  onRotate: () => void;
};

function AgentTokenRow(props: TAgentTokenRowProps) {
  const { token, onRevoke, onRotate } = props;
  // plane hooks
  const { t } = useTranslation();
  // derived values
  const isUsable = isAgentTokenUsable(token);

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2" data-testid="agent-token-row">
      <Icon icon={KeyOutline} />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="truncate text-body-xs-medium text-primary">
            {token.label?.trim() || t("jp_agents.token.default_label")}
          </span>
          <Badge
            variant={isUsable ? "success" : "neutral"}
            size="xs"
            label={isUsable ? t("jp_agents.token.active") : t("jp_agents.token.inactive")}
          />
        </div>
        <span className="text-caption-sm-regular text-tertiary">
          {[
            t("jp_agents.token.created", { date: renderFormattedDate(token.created_at) ?? "" }),
            token.last_used
              ? t("jp_agents.token.last_used", { time: calculateTimeAgo(token.last_used) })
              : t("jp_agents.token.never_used"),
            token.expired_at
              ? t("jp_agents.token.expires", { date: renderFormattedDate(token.expired_at) ?? "" })
              : t("jp_agents.token.never_expires"),
          ].join(" · ")}
        </span>
      </div>
      {isUsable && (
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            stretch="auto"
            icon={<Icon icon={RefreshOutline} />}
            label={t("jp_agents.token.rotate.action")}
            onClick={onRotate}
          />
          <Button
            variant="danger-outline"
            size="sm"
            stretch="auto"
            label={t("jp_agents.token.revoke.action")}
            onClick={onRevoke}
          />
        </div>
      )}
    </div>
  );
}

export const AgentListItem = observer(function AgentListItem(props: TAgentListItemProps) {
  const { agent, isGeneratingToken, onGenerateToken, onRename, onDeactivate, onRevokeToken, onRotateToken } = props;
  // states
  const [showTokens, setShowTokens] = useState(false);
  // plane hooks
  const { t } = useTranslation();
  // derived values
  const { member } = agent;
  const activeTokenCount = getActiveAgentTokens(agent).length;
  const tokens = sortAgentTokens(agent.tokens ?? []);
  const fullName = [member.first_name, member.last_name].filter(Boolean).join(" ").trim();

  return (
    <div className="flex flex-col" data-testid="agent-row">
      <div className="flex flex-wrap items-center gap-3 px-4 py-3">
        {member.avatar_url ? (
          <img
            src={getFileURL(member.avatar_url)}
            alt={member.display_name}
            className="size-8 shrink-0 rounded-full object-cover"
          />
        ) : (
          <span className="grid size-8 shrink-0 place-items-center rounded-full bg-layer-3 text-body-xs-medium text-secondary">
            {getAgentInitial(agent)}
          </span>
        )}
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="truncate text-body-sm-medium text-primary" data-testid="agent-name">
              {member.display_name}
            </span>
            <Badge variant="purple" size="xs" label={t("jp_agents.badge")} />
            {fullName && fullName !== member.display_name && (
              <span className="truncate text-body-xs-regular text-tertiary">{fullName}</span>
            )}
          </div>
          <span className="truncate text-body-xs-regular text-tertiary">{member.email}</span>
        </div>
        <span className="shrink-0 text-body-xs-regular text-secondary">
          {t("jp_agents.list.project_count", { count: agent.project_count ?? 0 })}
        </span>
        <button
          type="button"
          className={cn(
            "flex shrink-0 items-center gap-1 rounded-sm px-1.5 py-1 text-body-xs-regular text-secondary outline-none",
            "hover:bg-layer-1-hover focus-visible:ring-2 focus-visible:ring-accent-strong"
          )}
          aria-expanded={showTokens}
          aria-label={showTokens ? t("jp_agents.actions.hide_tokens") : t("jp_agents.actions.show_tokens")}
          onClick={() => setShowTokens((value) => !value)}
          data-testid="agent-tokens-toggle"
        >
          <Icon icon={showTokens ? ChevronDownOutline : ChevronRightOutline} />
          {t("jp_agents.list.token_count", { count: activeTokenCount })}
        </button>
        <Menu>
          <MenuTrigger
            render={
              <IconButton
                variant="ghost"
                size="sm"
                aria-label={t("jp_agents.actions.options")}
                icon={<Icon icon={MoreHorizontalOutline} />}
              />
            }
          />
          <MenuContent side="bottom" align="end">
            <MenuItem
              icon={<Icon icon={KeyOutline} />}
              label={t("jp_agents.actions.generate_token")}
              disabled={isGeneratingToken}
              onClick={() => onGenerateToken(agent)}
            />
            <MenuItem
              icon={<Icon icon={EditOutline} />}
              label={t("jp_agents.actions.rename")}
              onClick={() => onRename(agent)}
            />
            <MenuItem
              variant="danger"
              icon={<Icon icon={DeactivatedUserOutline} />}
              label={t("jp_agents.actions.deactivate")}
              onClick={() => onDeactivate(agent)}
            />
          </MenuContent>
        </Menu>
      </div>
      {showTokens && (
        <div className="mx-4 mb-3 rounded-md border border-subtle bg-layer-1 px-3" data-testid="agent-token-list">
          {tokens.length === 0 ? (
            <p className="py-3 text-body-xs-regular text-tertiary">{t("jp_agents.token.empty")}</p>
          ) : (
            <div className="divide-y divide-subtle">
              {tokens.map((token) => (
                <AgentTokenRow
                  key={token.id}
                  token={token}
                  onRevoke={() => onRevokeToken(agent, token)}
                  onRotate={() => onRotateToken(agent, token)}
                />
              ))}
            </div>
          )}
          <div className="border-t border-subtle py-2">
            <Button
              variant="ghost"
              size="sm"
              stretch="auto"
              icon={<Icon icon={KeyOutline} />}
              label={t("jp_agents.actions.generate_token")}
              loading={isGeneratingToken}
              onClick={() => onGenerateToken(agent)}
              data-testid="agent-generate-token"
            />
          </div>
        </div>
      )}
    </div>
  );
});
