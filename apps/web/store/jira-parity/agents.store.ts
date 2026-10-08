/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: agents store (owned by the agents feature)
import { action, computed, makeObservable, observable, runInAction } from "mobx";
import { computedFn } from "mobx-utils";
// plane imports
import type {
  TWorkspaceAgent,
  TWorkspaceAgentCreatePayload,
  TWorkspaceAgentCreateResponse,
  TWorkspaceAgentTokenCreatePayload,
  TWorkspaceAgentTokenCreateResponse,
  TWorkspaceAgentUpdatePayload,
} from "@plane/types";
// services
import { AgentsService } from "@/services/jira-parity/agents.service";
// store
import type { CoreRootStore } from "@/store/root.store";

export interface IAgentsStore {
  // observables (keyed by agent user id = member.id)
  agentMap: Record<string, TWorkspaceAgent>;
  /** Workspace whose agents are loaded in `agentMap` (null until the first fetch). */
  fetchedWorkspaceSlug: string | null;
  // computed
  /** Agents sorted by display name. */
  sortedAgents: TWorkspaceAgent[];
  // computed actions
  getAgentByUserId: (userId: string | null | undefined) => TWorkspaceAgent | undefined;
  // fetch actions
  fetchAgents: (workspaceSlug: string) => Promise<TWorkspaceAgent[]>;
  // actions (workspace admin only; the server enforces it)
  /** Creates an agent account; the response carries the API token once when one was generated. */
  createAgent: (workspaceSlug: string, data: TWorkspaceAgentCreatePayload) => Promise<TWorkspaceAgentCreateResponse>;
  updateAgent: (workspaceSlug: string, userId: string, data: TWorkspaceAgentUpdatePayload) => Promise<void>;
  /** Deactivates the agent (workspace + project memberships) and revokes its tokens. */
  deactivateAgent: (workspaceSlug: string, userId: string) => Promise<void>;
  /** Issues a new API token for the agent; the token value is only returned here. */
  createToken: (
    workspaceSlug: string,
    userId: string,
    data?: TWorkspaceAgentTokenCreatePayload
  ) => Promise<TWorkspaceAgentTokenCreateResponse>;
  revokeToken: (workspaceSlug: string, userId: string, tokenId: string) => Promise<void>;
  /** Issues a replacement token (same label), then revokes the old one. */
  rotateToken: (workspaceSlug: string, userId: string, tokenId: string) => Promise<TWorkspaceAgentTokenCreateResponse>;
}

export class AgentsStore implements IAgentsStore {
  // observables
  agentMap: Record<string, TWorkspaceAgent> = {};
  fetchedWorkspaceSlug: string | null = null;
  // root store
  rootStore: CoreRootStore;
  // services
  service: AgentsService;

  constructor(rootStore: CoreRootStore) {
    makeObservable(this, {
      agentMap: observable,
      fetchedWorkspaceSlug: observable.ref,
      sortedAgents: computed,
      fetchAgents: action,
      createAgent: action,
      updateAgent: action,
      deactivateAgent: action,
      createToken: action,
      revokeToken: action,
      rotateToken: action,
    });
    this.rootStore = rootStore;
    this.service = new AgentsService();
  }

  get sortedAgents() {
    // oxlint-disable-next-line unicorn/no-array-sort -- Object.values returns a fresh array; web targets ES2022
    return Object.values(this.agentMap).sort((a, b) =>
      (a.member.display_name ?? "").localeCompare(b.member.display_name ?? "", undefined, { sensitivity: "base" })
    );
  }

  getAgentByUserId = computedFn((userId: string | null | undefined) => (userId ? this.agentMap[userId] : undefined));

  fetchAgents = async (workspaceSlug: string) => {
    const agents = await this.service.list(workspaceSlug);
    runInAction(() => {
      this.agentMap = Object.fromEntries((agents ?? []).map((agent) => [agent.member.id, agent]));
      this.fetchedWorkspaceSlug = workspaceSlug;
    });
    return agents;
  };

  /** Re-reads the list (token rows and project counts are computed by the server). */
  private refresh = async (workspaceSlug: string) => {
    await this.fetchAgents(workspaceSlug).catch(() => undefined);
  };

  createAgent = async (workspaceSlug: string, data: TWorkspaceAgentCreatePayload) => {
    const response = await this.service.create(workspaceSlug, data);
    runInAction(() => {
      if (response?.member?.id) {
        const { token: _token, ...agent } = response;
        this.agentMap[response.member.id] = agent;
      }
    });
    void this.refresh(workspaceSlug);
    return response;
  };

  updateAgent = async (workspaceSlug: string, userId: string, data: TWorkspaceAgentUpdatePayload) => {
    const response = await this.service.update(workspaceSlug, userId, data);
    runInAction(() => {
      const current = this.agentMap[userId];
      if (response?.member?.id) this.agentMap[userId] = response;
      else if (current) this.agentMap[userId] = { ...current, member: { ...current.member, ...data } };
    });
  };

  deactivateAgent = async (workspaceSlug: string, userId: string) => {
    await this.service.destroy(workspaceSlug, userId);
    runInAction(() => {
      delete this.agentMap[userId];
    });
    void this.refresh(workspaceSlug);
  };

  createToken = async (workspaceSlug: string, userId: string, data: TWorkspaceAgentTokenCreatePayload = {}) => {
    const response = await this.service.createToken(workspaceSlug, userId, data);
    await this.refresh(workspaceSlug);
    return response;
  };

  revokeToken = async (workspaceSlug: string, userId: string, tokenId: string) => {
    await this.service.revokeToken(workspaceSlug, userId, tokenId);
    runInAction(() => {
      const revokedToken = this.agentMap[userId]?.tokens?.find((token) => token.id === tokenId);
      if (revokedToken) revokedToken.is_active = false;
    });
    void this.refresh(workspaceSlug);
  };

  rotateToken = async (workspaceSlug: string, userId: string, tokenId: string) => {
    const previousToken = this.agentMap[userId]?.tokens?.find((token) => token.id === tokenId);
    // issue the replacement first so a failure never leaves the agent without a working token
    const response = await this.service.createToken(
      workspaceSlug,
      userId,
      previousToken?.label ? { label: previousToken.label } : {}
    );
    await this.service.revokeToken(workspaceSlug, userId, tokenId);
    await this.refresh(workspaceSlug);
    return response;
  };
}
