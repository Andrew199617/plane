/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: default project role picker of a team (Admin / Member / Agent / Guest).
// Owned by the teams feature.
import { useMemo } from "react";
import { Select } from "@plane/blocks/select";
import type { SelectVariant } from "@plane/blocks/select";
import { JP_TEAM_ROLE_OPTIONS } from "@plane/constants";
import { useTranslation } from "@plane/i18n";

type TTeamRoleOption = { key: number; label: string; description: string };

type TTeamRoleSelectProps = {
  value: number;
  onChange: (role: number) => void;
  disabled?: boolean;
  variant?: SelectVariant;
  className?: string;
  testId?: string;
};

/** i18n label of a team role value ("Member" fallback for unknown values). */
export const getTeamRoleI18nLabel = (role: number) =>
  JP_TEAM_ROLE_OPTIONS.find((option) => option.value === role)?.i18n_label ?? "jp_teams.roles.member";

export function TeamRoleSelect(props: TTeamRoleSelectProps) {
  const { value, onChange, disabled = false, variant = "select-md", className, testId } = props;
  // plane hooks
  const { t } = useTranslation();
  // derived values
  const options = useMemo<TTeamRoleOption[]>(
    () =>
      JP_TEAM_ROLE_OPTIONS.map((option) => ({
        key: option.value,
        label: t(option.i18n_label),
        description: t(option.i18n_description),
      })),
    [t]
  );
  const selected = options.find((option) => option.key === value) ?? null;

  return (
    <div className={className} data-testid={testId}>
      <Select<TTeamRoleOption>
        value={selected}
        onChange={(key) => {
          const role = Number(key);
          if (!Number.isNaN(role) && role !== value) onChange(role);
        }}
        getValues={() => options}
        getOptionValue={(option) => String(option.key)}
        getOptionLabel={(option) => option.label}
        getOptionDescription={(option) => option.description}
        disabled={disabled}
        showSearch={false}
        pinSelected={false}
      >
        <Select.Trigger<TTeamRoleOption> variant={variant}>
          <span className="min-w-0 flex-1 truncate text-left">{selected?.label ?? t(getTeamRoleI18nLabel(value))}</span>
        </Select.Trigger>
      </Select>
    </div>
  );
}
