/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity placeholder (scaffold-owned)
import { useTranslation } from "@plane/i18n";
import { cn } from "@plane/utils";

type TJiraParityComingSoonProps = {
  className?: string;
};

export function JiraParityComingSoon(props: TJiraParityComingSoonProps) {
  const { className } = props;
  const { t } = useTranslation();

  return (
    <div
      className={cn(
        "flex w-full flex-col items-center justify-center gap-1 rounded-md border border-dashed border-subtle px-4 py-10 text-center",
        className
      )}
    >
      <p className="text-13 font-medium text-primary">{t("jp_common.coming_soon")}</p>
      <p className="text-12 text-tertiary">{t("jp_common.coming_soon_description")}</p>
    </div>
  );
}
