/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: app sidebar "Boards" section: one master board per project category (owned by the
// project-categories feature). Rendered by app/(all)/[workspaceSlug]/(projects)/sidebar.tsx.
import { useState } from "react";
import { observer } from "mobx-react";
import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import { Collapsible } from "@makeplane/propel/components/collapsible";
import { Icon } from "@makeplane/propel/components/icon";
import { IconButton } from "@makeplane/propel/components/icon-button";
import { Tooltip } from "@makeplane/propel/components/tooltip";
import { BoardOutline, SettingsOutline } from "@makeplane/propel/icons";
// plane imports
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import { Logo } from "@plane/blocks/emoji-icon-picker";
// components
import { SidebarNavItem } from "@/components/sidebar/sidebar-navigation";
// hooks
import { useProjectCategories } from "@/hooks/store/jira-parity/use-project-categories";
import { useAppTheme } from "@/hooks/store/use-app-theme";
import { useUserPermissions } from "@/hooks/store/user";

const OPEN_STATE_STORAGE_KEY = "jp_sidebar_boards_open";

const readOpenState = (): boolean => {
  try {
    return window.localStorage.getItem(OPEN_STATE_STORAGE_KEY) !== "false";
  } catch {
    return true;
  }
};

const writeOpenState = (isOpen: boolean) => {
  try {
    window.localStorage.setItem(OPEN_STATE_STORAGE_KEY, String(isOpen));
  } catch {
    // storage unavailable: the section state is kept in memory only
  }
};

export const SidebarCategoryBoardsList = observer(function SidebarCategoryBoardsList() {
  // states
  const [isOpen, setIsOpen] = useState<boolean>(readOpenState);
  // router
  const { workspaceSlug: routerWorkspaceSlug } = useParams();
  const workspaceSlug = routerWorkspaceSlug?.toString();
  const pathname = usePathname();
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const { sortedCategories, getProjectIdsByCategoryId } = useProjectCategories();
  const { allowPermissions } = useUserPermissions();
  const { toggleSidebar, isExtendedSidebarOpened, toggleExtendedSidebar } = useAppTheme();
  // derived values
  const isAdmin = allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.WORKSPACE);

  if (!workspaceSlug || sortedCategories.length === 0) return null;

  const handleToggle = (open: boolean) => {
    setIsOpen(open);
    writeOpenState(open);
  };

  const handleLinkClick = () => {
    if (window.innerWidth < 768) toggleSidebar();
    if (isExtendedSidebarOpened) toggleExtendedSidebar(false);
  };

  return (
    <Collapsible
      placement="sidebar"
      render={<div className="group/boards-section" data-testid="sidebar-category-boards" />}
      open={isOpen}
      onOpenChange={handleToggle}
      trigger={
        <span className="text-13 font-semibold whitespace-nowrap text-placeholder">
          {t("jp_categories.sidebar.boards")}
        </span>
      }
      trailing={
        isAdmin ? (
          <span className="hidden text-placeholder group-focus-within/boards-section:inline-flex group-hover/boards-section:inline-flex">
            <Tooltip label={t("jp_categories.sidebar.manage")}>
              <IconButton
                variant="ghost"
                size="xs"
                nativeButton={false}
                render={<Link href={`/${workspaceSlug}/settings/project-categories`} />}
                icon={<Icon icon={SettingsOutline} />}
                aria-label={t("jp_categories.sidebar.manage")}
              />
            </Tooltip>
          </span>
        ) : null
      }
    >
      <div className="flex flex-col gap-0.5">
        {sortedCategories.map((category) => {
          const href = `/${workspaceSlug}/boards/${category.id}`;
          const projectCount = getProjectIdsByCategoryId(category.id).length;
          return (
            <Link key={category.id} href={href} onClick={handleLinkClick}>
              <SidebarNavItem isActive={pathname.startsWith(href)}>
                <div className="flex min-w-0 items-center gap-1.5 py-[1px]">
                  <span className="grid size-4 shrink-0 place-items-center">
                    {category.logo_props?.in_use ? (
                      <Logo logo={category.logo_props} size={14} />
                    ) : (
                      <BoardOutline className="size-4" />
                    )}
                  </span>
                  <p className="truncate text-13 leading-5 font-medium">{category.name}</p>
                </div>
                <Tooltip label={t("jp_categories.sidebar.projects_count", { count: projectCount })}>
                  <span className="shrink-0 text-11 text-placeholder tabular-nums">{projectCount}</span>
                </Tooltip>
              </SidebarNavItem>
            </Link>
          );
        })}
      </div>
    </Collapsible>
  );
});
