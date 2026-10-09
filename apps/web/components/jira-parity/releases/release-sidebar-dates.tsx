/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: the release sidebar's "Start date" and "Release date" (= target_date) rows.
import { observer } from "mobx-react";
// plane imports
import { DueDateOutline, StartDateOutline } from "@makeplane/propel/icons";
import { DateSelect } from "@plane/blocks/property-select";
import { useTranslation } from "@plane/i18n";
import type { IModule } from "@plane/types";
import { getDate, renderFormattedPayloadDate } from "@plane/utils";
// hooks
import { useUserProfile } from "@/hooks/store/user";

type TReleaseDatesPayload = Partial<Pick<IModule, "start_date" | "target_date">>;

type TReleaseSidebarDatesProps = {
  release: Pick<IModule, "start_date" | "target_date">;
  disabled: boolean;
  onChange: (payload: TReleaseDatesPayload) => void;
};

export const ReleaseSidebarDates = observer(function ReleaseSidebarDates(props: TReleaseSidebarDatesProps) {
  const { release, disabled, onChange } = props;
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const { data: userProfile } = useUserProfile();
  // derived values
  const startDate = getDate(release.start_date) ?? null;
  const releaseDate = getDate(release.target_date) ?? null;

  return (
    <>
      <div className="flex items-center justify-start gap-1">
        <div className="flex w-2/5 items-center justify-start gap-2 text-tertiary">
          <StartDateOutline className="h-4 w-4" />
          <span className="text-14">{t("start_date")}</span>
        </div>
        <div className="h-7 w-3/5">
          <DateSelect
            variant="select-ghost-md"
            value={startDate}
            onChange={(date) => onChange({ start_date: (date && renderFormattedPayloadDate(date)) || null })}
            maxDate={releaseDate ?? undefined}
            placeholder={t("start_date")}
            weekStartsOn={userProfile?.start_of_the_week}
            disabled={disabled}
            clearable
            clearLabel={t("common.clear")}
            className="w-full"
            testId="release-sidebar-start-date"
          />
        </div>
      </div>
      <div className="flex items-center justify-start gap-1">
        <div className="flex w-2/5 items-center justify-start gap-2 text-tertiary">
          <DueDateOutline className="h-4 w-4" />
          <span className="text-14">{t("jp_releases.release_date")}</span>
        </div>
        <div className="h-7 w-3/5">
          <DateSelect
            variant="select-ghost-md"
            value={releaseDate}
            onChange={(date) => onChange({ target_date: (date && renderFormattedPayloadDate(date)) || null })}
            minDate={startDate ?? undefined}
            placeholder={t("jp_releases.release_date")}
            weekStartsOn={userProfile?.start_of_the_week}
            disabled={disabled}
            clearable
            clearLabel={t("common.clear")}
            className="w-full"
            testId="release-sidebar-release-date"
          />
        </div>
      </div>
    </>
  );
});
