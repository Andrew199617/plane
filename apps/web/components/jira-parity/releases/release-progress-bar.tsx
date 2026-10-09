/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: a release's segmented progress bar — done (completed + cancelled, green), in progress
// (started, blue), to do (unstarted + backlog, gray) — with the counts in a tooltip.
import { observer } from "mobx-react";
// plane imports
import { Tooltip } from "@makeplane/propel/components/tooltip";
import { useTranslation } from "@plane/i18n";
import type { IModule } from "@plane/types";
import { cn } from "@plane/utils";
// local imports
import { getReleaseProgress } from "./helpers";

type TReleaseProgressBarProps = {
  release: Pick<
    IModule,
    "total_issues" | "completed_issues" | "cancelled_issues" | "started_issues" | "unstarted_issues" | "backlog_issues"
  >;
  className?: string;
  isMobile?: boolean;
};

export const ReleaseProgressBar = observer(function ReleaseProgressBar(props: TReleaseProgressBarProps) {
  const { release, className, isMobile = false } = props;
  // plane hooks
  const { t } = useTranslation();
  // derived values
  const progress = getReleaseProgress(release);
  const summary =
    progress.total > 0
      ? t("jp_releases.progress.summary", {
          done: progress.done,
          in_progress: progress.inProgress,
          to_do: progress.toDo,
        })
      : t("jp_releases.progress.empty");
  const donePercent = Math.round(progress.donePercent);

  return (
    <Tooltip label={summary} layout="stacked" disabled={isMobile}>
      <div
        role="progressbar"
        aria-label={t("jp_releases.progress.aria_label")}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={donePercent}
        aria-valuetext={summary}
        className={cn("flex h-1.5 w-24 flex-shrink-0 overflow-hidden rounded-full bg-layer-3", className)}
        data-testid="release-progress-bar"
      >
        {progress.donePercent > 0 && (
          <span className="h-full bg-success-primary" style={{ width: `${progress.donePercent}%` }} />
        )}
        {progress.inProgressPercent > 0 && (
          <span className="h-full bg-accent-primary" style={{ width: `${progress.inProgressPercent}%` }} />
        )}
      </div>
    </Tooltip>
  );
});
