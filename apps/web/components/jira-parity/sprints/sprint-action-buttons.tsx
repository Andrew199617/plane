/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: "Start sprint" (future sprint) / "Complete sprint" (active sprint) button with its dialog, for the sprint
// list rows and the sprint detail header. Admin / Member only. Owned by the sprints feature.
import { observer } from "mobx-react";
import { Button } from "@makeplane/propel/components/button";
import { Tooltip } from "@makeplane/propel/components/tooltip";
import { useTranslation } from "@plane/i18n";
// local imports
import { useSprintActions } from "./use-sprint-actions";

type TSprintActionButtonsProps = {
  workspaceSlug: string;
  projectId: string;
  cycleId: string;
  /** Button emphasis: the detail header uses the primary style, list rows the secondary one. */
  variant?: "primary" | "secondary";
  className?: string;
};

export const SprintActionButtons = observer(function SprintActionButtons(props: TSprintActionButtonsProps) {
  const { workspaceSlug, projectId, cycleId, variant = "secondary", className } = props;
  // plane hooks
  const { t } = useTranslation();
  // sprint actions
  const { canStart, canComplete, startBlockedReason, openStart, openComplete, modals } = useSprintActions({
    workspaceSlug,
    projectId,
    cycleId,
  });

  if (!canStart && !canComplete) return <>{modals}</>;

  return (
    <>
      {modals}
      {/* the row / header around the button must not navigate or toggle when it is pressed */}
      {/* oxlint-disable-next-line jsx_a11y/click-events-have-key-events, jsx_a11y/no-static-element-interactions */}
      <span
        className={className}
        onClick={(e) => {
          e.stopPropagation();
        }}
      >
        {canStart && (
          <Tooltip label={startBlockedReason} layout="stacked" disabled={!startBlockedReason}>
            {/* a disabled button swallows pointer events, so the tooltip anchors on a focusable wrapper */}
            <span className="inline-flex" tabIndex={startBlockedReason ? 0 : -1} data-testid="sprint-start-button">
              <Button
                variant={variant}
                size="md"
                stretch="auto"
                label={t("jp_sprints.actions.start")}
                disabled={!!startBlockedReason}
                onClick={openStart}
              />
            </span>
          </Tooltip>
        )}
        {canComplete && (
          <span className="inline-flex" data-testid="sprint-complete-button">
            <Button
              variant={variant}
              size="md"
              stretch="auto"
              label={t("jp_sprints.actions.complete")}
              onClick={openComplete}
            />
          </span>
        )}
      </span>
    </>
  );
});
