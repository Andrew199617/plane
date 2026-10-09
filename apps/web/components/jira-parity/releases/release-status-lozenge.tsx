/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: release (module) lozenges — UNRELEASED / RELEASED / ARCHIVED, plus the red OVERDUE one.
import { observer } from "mobx-react";
// plane imports
import { Tooltip } from "@makeplane/propel/components/tooltip";
import { useTranslation } from "@plane/i18n";
import type { IModule } from "@plane/types";
import { cn } from "@plane/utils";
// local imports
import type { TReleaseLozengeStatus } from "./helpers";
import { getReleaseLozengeStatus, isReleaseOverdue } from "./helpers";

const LOZENGE_BASE =
  "inline-flex h-5 flex-shrink-0 items-center rounded-sm px-1.5 text-11 font-semibold tracking-wide whitespace-nowrap uppercase";

const STATUS_CLASSNAMES: Record<TReleaseLozengeStatus, string> = {
  unreleased: "bg-layer-3 text-secondary",
  released: "bg-success-subtle text-success-primary",
  archived: "bg-layer-1 text-tertiary",
};

type TReleaseLozengeProps = {
  release: Pick<IModule, "status" | "archived_at" | "target_date">;
  className?: string;
};

/** UNRELEASED / RELEASED / ARCHIVED (archived wins, like Jira). */
export const ReleaseStatusLozenge = observer(function ReleaseStatusLozenge(props: TReleaseLozengeProps) {
  const { release, className } = props;
  // plane hooks
  const { t } = useTranslation();
  // derived values
  const status = getReleaseLozengeStatus(release);

  return (
    <span className={cn(LOZENGE_BASE, STATUS_CLASSNAMES[status], className)} data-testid="release-status-lozenge">
      {t(`jp_releases.status.${status}`)}
    </span>
  );
});

/** Red OVERDUE lozenge; renders nothing unless the release is overdue (unreleased, release date passed). */
export const ReleaseOverdueLozenge = observer(function ReleaseOverdueLozenge(props: TReleaseLozengeProps) {
  const { release, className } = props;
  // plane hooks
  const { t } = useTranslation();

  if (!isReleaseOverdue(release)) return null;

  return (
    <Tooltip label={t("jp_releases.overdue_tooltip")} layout="stacked">
      <span
        className={cn(LOZENGE_BASE, "cursor-default bg-danger-subtle text-danger-primary", className)}
        data-testid="release-overdue-lozenge"
      >
        {t("jp_releases.status.overdue")}
      </span>
    </Tooltip>
  );
});

/** Status lozenge followed by the OVERDUE one when it applies. */
export const ReleaseLozenges = observer(function ReleaseLozenges(props: TReleaseLozengeProps) {
  const { release, className } = props;
  return (
    <span className={cn("flex flex-shrink-0 items-center gap-1.5", className)}>
      <ReleaseStatusLozenge release={release} />
      <ReleaseOverdueLozenge release={release} />
    </span>
  );
});
