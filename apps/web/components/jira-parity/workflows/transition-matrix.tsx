/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: from-state x to-state checkbox matrix for one role (owned by the workflows feature).
import { observer } from "mobx-react";
// plane imports
import { Checkbox } from "@makeplane/propel/components/checkbox";
import { StateGroupIcon } from "@plane/blocks/icons";
import { useTranslation } from "@plane/i18n";
import type { IState } from "@plane/types";
import { cn } from "@plane/utils";
// local imports
import type { TWorkflowRoleDraft } from "./helpers";
import { getWorkflowCellKey } from "./helpers";

type TWorkflowTransitionMatrixProps = {
  roleLabel: string;
  states: IState[];
  /** The role's draft cells (`from::to` -> exclude_epics). */
  cells: TWorkflowRoleDraft;
  disabled: boolean;
  onToggleCell: (fromStateId: string | null, toStateId: string) => void;
};

function StateLabel(props: { state: IState }) {
  const { state } = props;
  return (
    <span className="flex items-center gap-1.5 whitespace-nowrap">
      <StateGroupIcon stateGroup={state.group} color={state.color} className="shrink-0" />
      <span className="truncate">{state.name}</span>
    </span>
  );
}

export const WorkflowTransitionMatrix = observer(function WorkflowTransitionMatrix(
  props: TWorkflowTransitionMatrixProps
) {
  const { roleLabel, states, cells, disabled, onToggleCell } = props;
  // plane hooks
  const { t } = useTranslation();
  // derived values
  const fromRows: (IState | null)[] = [null, ...states];
  const anyStateLabel = t("jp_workflows.matrix.any_state");

  return (
    <div className="overflow-x-auto rounded-lg border border-subtle" data-testid="workflow-matrix">
      <table className="w-full border-collapse text-body-xs-regular">
        <caption className="sr-only">{t("jp_workflows.matrix.caption", { role: roleLabel })}</caption>
        <thead>
          <tr className="border-b border-subtle bg-layer-1">
            <th
              scope="col"
              className="sticky left-0 z-[1] min-w-36 bg-layer-1 px-3 py-2 text-left text-body-xs-medium text-secondary"
            >
              {t("jp_workflows.matrix.from_to")}
            </th>
            {states.map((state) => (
              <th scope="col" key={state.id} className="px-3 py-2 text-center text-body-xs-medium text-secondary">
                <span className="flex justify-center">
                  <StateLabel state={state} />
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {fromRows.map((fromState) => {
            const fromStateId = fromState?.id ?? null;
            const fromLabel = fromState?.name ?? anyStateLabel;
            return (
              <tr key={fromStateId ?? "any"} className="border-b border-subtle last:border-b-0">
                <th
                  scope="row"
                  className={cn("font-normal sticky left-0 z-[1] px-3 py-2 text-left text-primary", {
                    "bg-surface-1": fromStateId !== null,
                    "bg-layer-1": fromStateId === null,
                  })}
                >
                  {fromState ? <StateLabel state={fromState} /> : <span className="italic">{anyStateLabel}</span>}
                </th>
                {states.map((toState) => {
                  const isSameState = fromStateId === toState.id;
                  if (isSameState) {
                    return (
                      <td key={toState.id} className="px-3 py-2 text-center text-placeholder">
                        <span
                          title={t("jp_workflows.matrix.same_state")}
                          aria-label={t("jp_workflows.matrix.same_state")}
                        >
                          —
                        </span>
                      </td>
                    );
                  }
                  const isAllowedFromAny = fromStateId !== null && getWorkflowCellKey(null, toState.id) in cells;
                  const isChecked = getWorkflowCellKey(fromStateId, toState.id) in cells;
                  const toggleLabel = t("jp_workflows.matrix.toggle", { from: fromLabel, to: toState.name });
                  return (
                    <td key={toState.id} className="px-3 py-2 text-center">
                      <span
                        className="inline-flex"
                        title={isAllowedFromAny ? t("jp_workflows.matrix.allowed_from_any") : toggleLabel}
                      >
                        <Checkbox
                          aria-label={toggleLabel}
                          checked={isChecked || isAllowedFromAny}
                          disabled={disabled || isAllowedFromAny}
                          onCheckedChange={() => onToggleCell(fromStateId, toState.id)}
                          data-testid={`workflow-cell-${fromStateId ?? "any"}-${toState.id}`}
                        />
                      </span>
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
});
