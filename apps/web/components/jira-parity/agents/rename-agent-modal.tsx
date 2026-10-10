/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: rename an agent account (workspace admin). Owned by the agents feature.
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
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import type { TWorkspaceAgent } from "@plane/types";
// hooks
import { useAgents } from "@/hooks/store/jira-parity/use-agents";
// local imports
import { getAgentApiErrorMessage } from "./helpers";

type TRenameAgentFormValues = { displayName: string };

type TRenameAgentModalProps = {
  workspaceSlug: string;
  agent: TWorkspaceAgent | undefined;
  onClose: () => void;
};

export const RenameAgentModal = observer(function RenameAgentModal(props: TRenameAgentModalProps) {
  const { workspaceSlug, agent, onClose } = props;
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const { updateAgent } = useAgents();
  // form
  const {
    control,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<TRenameAgentFormValues>({ defaultValues: { displayName: agent?.member.display_name ?? "" } });

  useEffect(() => {
    if (agent) reset({ displayName: agent.member.display_name ?? "" });
    // oxlint-disable-next-line eslint-plugin-react-hooks/exhaustive-deps
  }, [agent?.member.id, reset]);

  const onSubmit = async (formData: TRenameAgentFormValues) => {
    if (!agent) return;
    try {
      await updateAgent(workspaceSlug, agent.member.id, { display_name: formData.displayName.trim() });
      setToast({ type: "success", title: t("jp_agents.rename.success") });
      onClose();
    } catch (error) {
      setToast({
        type: "error",
        title: t("jp_agents.rename.error"),
        message: getAgentApiErrorMessage(error, "") || undefined,
      });
    }
  };

  return (
    <Dialog
      open={!!agent}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent size="sm">
        <form onSubmit={handleSubmit(onSubmit)} className="flex min-h-0 flex-1 flex-col">
          <DialogMain>
            <DialogHeader>
              <DialogHeading>
                <DialogTitle>{t("jp_agents.rename.title")}</DialogTitle>
              </DialogHeading>
            </DialogHeader>
            <DialogBody>
              <Controller
                control={control}
                name="displayName"
                rules={{ validate: (value) => value.trim().length > 0 || t("jp_agents.create.display_name_required") }}
                render={({ field: { value, onChange, ref } }) => (
                  <InputField
                    id="agent-rename-display-name"
                    name="display_name"
                    ref={ref}
                    value={value}
                    onChange={onChange}
                    size="lg"
                    orientation="vertical"
                    label={t("jp_agents.create.display_name")}
                    required
                    error={errors.displayName?.message}
                    autoComplete="off"
                  />
                )}
              />
            </DialogBody>
          </DialogMain>
          <DialogActions>
            <Button
              variant="secondary"
              size="md"
              stretch="auto"
              label={t("jp_agents.create.cancel")}
              onClick={onClose}
            />
            <Button
              variant="primary"
              size="md"
              stretch="auto"
              type="submit"
              loading={isSubmitting}
              disabled={isSubmitting}
              label={isSubmitting ? t("jp_agents.rename.submitting") : t("jp_agents.rename.submit")}
            />
          </DialogActions>
        </form>
      </DialogContent>
    </Dialog>
  );
});
