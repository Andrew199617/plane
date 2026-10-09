/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: create an agent account (workspace admin). Owned by the agents feature.
import { useEffect } from "react";
import { observer } from "mobx-react";
import { Controller, useForm } from "react-hook-form";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { CheckboxField } from "@makeplane/propel/components/checkbox-field";
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
import { InputField } from "@makeplane/propel/components/input-field";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import type { TWorkspaceAgentCreateResponse } from "@plane/types";
// hooks
import { useAgents } from "@/hooks/store/jira-parity/use-agents";
// local imports
import { buildAgentCreatePayload, getAgentApiErrorMessage, getAgentEmailDomain } from "./helpers";

const NAME_MAX_LENGTH = 255;

type TCreateAgentFormValues = {
  displayName: string;
  generateToken: boolean;
  tokenLabel: string;
};

const DEFAULT_VALUES: TCreateAgentFormValues = {
  displayName: "",
  generateToken: true,
  tokenLabel: "",
};

type TCreateAgentModalProps = {
  workspaceSlug: string;
  isOpen: boolean;
  onClose: () => void;
  /** Called with the created agent (and its one-time token when one was generated). */
  onCreated: (agent: TWorkspaceAgentCreateResponse) => void;
};

export const CreateAgentModal = observer(function CreateAgentModal(props: TCreateAgentModalProps) {
  const { workspaceSlug, isOpen, onClose, onCreated } = props;
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const { createAgent } = useAgents();
  // form
  const {
    control,
    handleSubmit,
    reset,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<TCreateAgentFormValues>({ defaultValues: DEFAULT_VALUES });
  const generateToken = watch("generateToken");

  useEffect(() => {
    if (isOpen) reset(DEFAULT_VALUES);
  }, [isOpen, reset]);

  const onSubmit = async (formData: TCreateAgentFormValues) => {
    try {
      const agent = await createAgent(workspaceSlug, buildAgentCreatePayload(formData));
      setToast({
        type: "success",
        title: t("jp_agents.create.success_title"),
        message: t("jp_agents.create.success_message", {
          name: agent?.member?.display_name ?? formData.displayName.trim(),
        }),
      });
      onClose();
      onCreated(agent);
    } catch (error) {
      setToast({
        type: "error",
        title: t("jp_agents.create.error"),
        message: getAgentApiErrorMessage(error, "") || undefined,
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
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex min-h-0 flex-1 flex-col"
          data-testid="create-agent-form"
        >
          <DialogMain>
            <DialogHeader>
              <DialogHeading>
                <DialogTitle>{t("jp_agents.create.title")}</DialogTitle>
                <DialogDescription>{t("jp_agents.create.description")}</DialogDescription>
              </DialogHeading>
            </DialogHeader>
            <DialogBody>
              <div className="flex flex-col gap-5">
                <Controller
                  control={control}
                  name="displayName"
                  rules={{
                    validate: (value) => value.trim().length > 0 || t("jp_agents.create.display_name_required"),
                    maxLength: { value: NAME_MAX_LENGTH, message: t("jp_agents.create.display_name_required") },
                  }}
                  render={({ field: { value, onChange, ref } }) => (
                    <InputField
                      id="agent-display-name"
                      name="display_name"
                      ref={ref}
                      value={value}
                      onChange={onChange}
                      size="lg"
                      orientation="vertical"
                      label={t("jp_agents.create.display_name")}
                      placeholder={t("jp_agents.create.display_name_placeholder")}
                      required
                      error={errors.displayName?.message}
                      hint={t("jp_agents.create.email_hint", { domain: getAgentEmailDomain(workspaceSlug) })}
                      autoComplete="off"
                    />
                  )}
                />
                <Controller
                  control={control}
                  name="generateToken"
                  render={({ field: { value, onChange } }) => (
                    <CheckboxField
                      name="generate_token"
                      label={t("jp_agents.create.generate_token")}
                      size="lg"
                      stretch="full"
                      checked={value}
                      onCheckedChange={(checked) => onChange(checked === true)}
                    />
                  )}
                />
                {generateToken && (
                  <Controller
                    control={control}
                    name="tokenLabel"
                    render={({ field: { value, onChange } }) => (
                      <InputField
                        id="agent-token-label"
                        name="token_label"
                        value={value}
                        onChange={onChange}
                        size="lg"
                        orientation="vertical"
                        label={t("jp_agents.create.token_label")}
                        placeholder={t("jp_agents.create.token_label_placeholder")}
                        autoComplete="off"
                      />
                    )}
                  />
                )}
              </div>
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
              label={isSubmitting ? t("jp_agents.create.submitting") : t("jp_agents.create.submit")}
              data-testid="create-agent-submit"
            />
          </DialogActions>
        </form>
      </DialogContent>
    </Dialog>
  );
});
