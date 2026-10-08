/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: shows a freshly issued agent API token exactly once (owned by the agents feature).
import { Button } from "@makeplane/propel/components/button";
import {
  Dialog,
  DialogActions,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogHeading,
  DialogMain,
  DialogTitle,
} from "@makeplane/propel/components/dialog";
import { Icon } from "@makeplane/propel/components/icon";
import { CopyOutline } from "@makeplane/propel/icons";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import { copyTextToClipboard } from "@plane/utils";

export type TRevealedAgentToken = {
  /** Display name of the agent the token belongs to. */
  agentName: string;
  /** The secret token value (only available right after it was issued). */
  token: string;
};

type TAgentTokenRevealModalProps = {
  revealedToken: TRevealedAgentToken | null;
  onClose: () => void;
};

export function AgentTokenRevealModal(props: TAgentTokenRevealModalProps) {
  const { revealedToken, onClose } = props;
  // plane hooks
  const { t } = useTranslation();

  const handleCopy = () => {
    if (!revealedToken) return;
    void copyTextToClipboard(revealedToken.token).then(() =>
      setToast({ type: "success", title: t("jp_agents.token.copied") })
    );
  };

  return (
    <Dialog
      open={!!revealedToken}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent size="md">
        <DialogMain>
          <DialogHeader>
            <DialogHeading>
              <DialogTitle>{t("jp_agents.token.created_title")}</DialogTitle>
              <DialogDescription>{t("jp_agents.token.created_description")}</DialogDescription>
            </DialogHeading>
          </DialogHeader>
          <DialogBody>
            {revealedToken && (
              <div className="flex flex-col gap-2">
                <span className="text-body-xs-medium text-secondary">
                  {t("jp_agents.token.for_agent", { name: revealedToken.agentName })}
                </span>
                <div className="flex items-center gap-2 rounded-md border border-subtle bg-layer-1 px-3 py-2">
                  <code
                    className="font-mono min-w-0 flex-1 text-body-xs-regular break-all text-primary select-all"
                    data-testid="agent-token-value"
                  >
                    {revealedToken.token}
                  </code>
                </div>
              </div>
            )}
          </DialogBody>
        </DialogMain>
        <DialogActions>
          <Button
            variant="secondary"
            size="md"
            stretch="auto"
            icon={<Icon icon={CopyOutline} />}
            label={t("jp_agents.token.copy")}
            onClick={handleCopy}
            data-testid="agent-token-copy"
          />
          <Button variant="primary" size="md" stretch="auto" label={t("jp_agents.token.done")} onClick={onClose} />
        </DialogActions>
      </DialogContent>
    </Dialog>
  );
}
