// oxlint-disable promise/always-return
/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { SyntheticEvent } from "react";
import React, { useRef } from "react";
import { observer } from "mobx-react";
import Link from "next/link";
import { useParams, usePathname, useSearchParams } from "next/navigation";
import { CalendarOutline, InfoOutline, UserAltOutline, WorkItemsOutline } from "@makeplane/propel/icons";
// plane package imports
import { EUserPermissions, EUserPermissionsLevel, IS_FAVORITE_MENU_OPEN } from "@plane/constants";
import { useLocalStorage } from "@plane/hooks";
import { useTranslation } from "@plane/i18n";
import { setPromiseToast, setToast } from "@plane/blocks/toast";
import { Tooltip } from "@makeplane/propel/components/tooltip";
import type { IModule } from "@plane/types";
import { Card } from "@plane/blocks/card";
import { FavoriteStar } from "@plane/blocks/common";
import { DateRangeSelect } from "@plane/blocks/property-select";
import { getDate, renderFormattedPayloadDate, generateQueryParams } from "@plane/utils";
// components
import { handleTriggerKeyDown } from "@/components/common/trigger-guard";
import { ButtonAvatars } from "@/components/dropdowns/member/avatar";
import {
  formatReleaseDateRangeLabel,
  ReleaseActionButton,
  ReleaseLozenges,
  ReleaseProgressBar,
} from "@/components/jira-parity/releases";
import { ModuleQuickActions } from "@/components/modules";
// hooks
import { useMember } from "@/hooks/store/use-member";
import { useModule } from "@/hooks/store/use-module";
import { useUserPermissions, useUserProfile } from "@/hooks/store/user";
import { useAppRouter } from "@/hooks/use-app-router";
import { usePlatformOS } from "@/hooks/use-platform-os";

type Props = {
  moduleId: string;
};

const handleEventPropagation = (e: SyntheticEvent<HTMLDivElement>) => {
  e.stopPropagation();
  e.preventDefault();
};

export const ModuleCardItem = observer(function ModuleCardItem(props: Props) {
  const { moduleId } = props;
  // refs
  const parentRef = useRef(null);
  // router
  const router = useAppRouter();
  const { workspaceSlug, projectId } = useParams();
  const searchParams = useSearchParams();
  const pathname = usePathname();
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const { allowPermissions } = useUserPermissions();
  const { getModuleById, addModuleToFavorites, removeModuleFromFavorites, updateModuleDetails } = useModule();
  const { getUserDetails } = useMember();
  const { data: userProfile } = useUserProfile();
  // local storage
  const { setValue: toggleFavoriteMenu, storedValue } = useLocalStorage<boolean>(IS_FAVORITE_MENU_OPEN, false);
  // derived values
  const moduleDetails = getModuleById(moduleId);
  const isEditingAllowed = allowPermissions(
    [EUserPermissions.ADMIN, EUserPermissions.MEMBER],
    EUserPermissionsLevel.PROJECT
  );
  const isDisabled = !isEditingAllowed || !!moduleDetails?.archived_at;
  const renderIcon = Boolean(moduleDetails?.start_date) || Boolean(moduleDetails?.target_date);

  const { isMobile } = usePlatformOS();
  const handleAddToFavorites = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    e.preventDefault();
    if (!workspaceSlug || !projectId) return;

    const addToFavoritePromise = addModuleToFavorites(workspaceSlug.toString(), projectId.toString(), moduleId).then(
      () => {
        if (!storedValue) toggleFavoriteMenu(true);
      }
    );

    setPromiseToast(addToFavoritePromise, {
      loading: "Adding release to favorites...",
      success: {
        title: "Success!",
        message: () => "Release added to favorites.",
      },
      error: {
        title: "Error!",
        message: () => "Couldn't add the release to favorites. Please try again.",
      },
    });
  };

  const handleRemoveFromFavorites = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    e.preventDefault();
    if (!workspaceSlug || !projectId) return;

    const removeFromFavoritePromise = removeModuleFromFavorites(
      workspaceSlug.toString(),
      projectId.toString(),
      moduleId
    );

    setPromiseToast(removeFromFavoritePromise, {
      loading: "Removing release from favorites...",
      success: {
        title: "Success!",
        message: () => "Release removed from favorites.",
      },
      error: {
        title: "Error!",
        message: () => "Couldn't remove the release from favorites. Please try again.",
      },
    });
  };

  const handleModuleDetailsChange = async (payload: Partial<IModule>) => {
    if (!workspaceSlug || !projectId) return;

    await updateModuleDetails(workspaceSlug.toString(), projectId.toString(), moduleId, payload)
      .then(() => {
        setToast({
          type: "success",
          title: "Success!",
          message: "Release updated successfully.",
        });
      })
      .catch((err) => {
        setToast({
          type: "error",
          title: "Error!",
          message: err?.detail ?? "Release could not be updated. Please try again.",
        });
      });
  };

  const openModuleOverview = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    e.preventDefault();

    const query = generateQueryParams(searchParams, ["peekModule"]);
    if (searchParams.has("peekModule") && searchParams.get("peekModule") === moduleId) {
      router.push(`${pathname}?${query}`);
    } else {
      router.push(`${pathname}?${query && `${query}&`}peekModule=${moduleId}`);
    }
  };

  if (!moduleDetails) return null;

  const moduleTotalIssues =
    moduleDetails.backlog_issues +
    moduleDetails.unstarted_issues +
    moduleDetails.started_issues +
    moduleDetails.completed_issues +
    moduleDetails.cancelled_issues;

  const moduleCompletedIssues = moduleDetails.completed_issues;

  // const areYearsEqual = startDate.getFullYear() === endDate.getFullYear();

  const issueCount = moduleDetails
    ? !moduleTotalIssues || moduleTotalIssues === 0
      ? `0 work items`
      : moduleTotalIssues === moduleCompletedIssues
        ? `${moduleTotalIssues} Work item${moduleTotalIssues > 1 ? `s` : ``}`
        : `${moduleCompletedIssues}/${moduleTotalIssues} Work items`
    : `0 work items`;

  const moduleLeadDetails = moduleDetails.lead_id ? getUserDetails(moduleDetails.lead_id) : undefined;

  return (
    <div className="relative" data-prevent-progress>
      <Link ref={parentRef} href={`/${workspaceSlug}/projects/${moduleDetails.project_id}/modules/${moduleDetails.id}`}>
        <Card>
          <div>
            <div className="flex items-center justify-between gap-2">
              <Tooltip label={moduleDetails.name} layout="stacked" disabled={isMobile}>
                <span className="truncate text-14 font-medium">{moduleDetails.name}</span>
              </Tooltip>
              {/* Ruling 38: guard both halves — the card root is a `Link`. */}
              <div
                className="flex items-center gap-2"
                role="presentation"
                onClick={handleEventPropagation}
                onKeyDown={handleTriggerKeyDown}
              >
                {/* Jira-parity: status lozenges (the Release button sits outside the card link, below) */}
                <ReleaseLozenges release={moduleDetails} />
                <button onClick={openModuleOverview}>
                  <InfoOutline className="h-4 w-4 text-placeholder" />
                </button>
              </div>
            </div>
          </div>
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 text-secondary">
                <WorkItemsOutline className="h-4 w-4 text-tertiary" />
                <span className="text-11 text-tertiary">{issueCount ?? "0 Work item"}</span>
              </div>
              {moduleLeadDetails ? (
                <span className="cursor-default">
                  <ButtonAvatars showTooltip={false} userIds={moduleLeadDetails?.id} />
                </span>
              ) : (
                <Tooltip label="No lead">
                  <UserAltOutline className="mx-1 h-4 w-4 text-tertiary" />
                </Tooltip>
              )}
            </div>
            <ReleaseProgressBar release={moduleDetails} isMobile={isMobile} className="w-full" />
            {/* Ruling 38: the whole card is a `Link`, so the trigger's click and keyboard
                activation must not reach it. */}
            <div
              className="flex items-center justify-between py-0.5"
              role="presentation"
              onClick={handleEventPropagation}
              onKeyDown={handleTriggerKeyDown}
            >
              <DateRangeSelect
                variant="select-ghost-md"
                className={`h-6 w-full gap-1.5 rounded-sm border-[0.5px] border-strong text-11 text-tertiary ${
                  isDisabled ? "cursor-not-allowed" : "cursor-pointer"
                }`}
                value={{
                  from: getDate(moduleDetails.start_date) ?? null,
                  to: getDate(moduleDetails.target_date) ?? null,
                }}
                onChange={(range) => {
                  void handleModuleDetailsChange({
                    start_date: range.from ? renderFormattedPayloadDate(range.from) : null,
                    target_date: range.to ? renderFormattedPayloadDate(range.to) : null,
                  });
                }}
                formatLabel={
                  moduleDetails.start_date && moduleDetails.target_date
                    ? undefined
                    : (_range, formatted) => formatReleaseDateRangeLabel(formatted)
                }
                showTooltip
                tooltipHeading={t("jp_releases.date_range")}
                tooltipEmptyContent={t("common.none")}
                placeholder={t("jp_releases.date_range")}
                weekStartsOn={userProfile?.start_of_the_week}
                disabled={isDisabled}
                icon={renderIcon ? undefined : <CalendarOutline aria-hidden="true" />}
              />
            </div>
          </div>
        </Card>
      </Link>
      <div className="absolute right-4 bottom-[18px] flex items-center gap-1.5">
        {workspaceSlug && (
          <ReleaseActionButton
            workspaceSlug={workspaceSlug.toString()}
            projectId={moduleDetails.project_id}
            moduleId={moduleId}
          />
        )}
        {isEditingAllowed && (
          <FavoriteStar
            onClick={(e) => {
              if (moduleDetails.is_favorite) handleRemoveFromFavorites(e);
              else handleAddToFavorites(e);
            }}
            selected={!!moduleDetails.is_favorite}
          />
        )}
        {workspaceSlug && projectId && (
          <ModuleQuickActions
            parentRef={parentRef}
            moduleId={moduleId}
            projectId={projectId.toString()}
            workspaceSlug={workspaceSlug.toString()}
          />
        )}
      </div>
    </div>
  );
});
