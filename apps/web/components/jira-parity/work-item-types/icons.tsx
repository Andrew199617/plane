/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Jira-parity: Jira-like work item type icons (owned by the work-item-types feature).
// Each icon is a single 16x16 SVG: a colored rounded square with a white glyph. Size it with `className`
// (e.g. "size-4"); select triggers inject their own size class through cloneElement.
import type { TWorkItemType, TWorkItemTypeIconKey } from "@plane/types";
import { cn } from "@plane/utils";
// local imports
import { getWorkItemTypeColor, getWorkItemTypeIconKey } from "./rules";

const GLYPH_COLOR = "#FFFFFF";

type TGlyphProps = { color: string };

function TaskGlyph() {
  return (
    <path
      d="M4.4 8.3l2.4 2.4 4.8-5.1"
      fill="none"
      stroke={GLYPH_COLOR}
      strokeWidth={1.9}
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  );
}

function SubTaskGlyph() {
  return (
    <>
      <rect x="3.4" y="3.4" width="5.6" height="5.6" rx="1" fill="none" stroke={GLYPH_COLOR} strokeWidth={1.4} />
      <rect x="7" y="7" width="5.6" height="5.6" rx="1" fill={GLYPH_COLOR} />
    </>
  );
}

function StoryGlyph() {
  return (
    <>
      <path d="M8 3.6v5.4" fill="none" stroke={GLYPH_COLOR} strokeWidth={2.1} strokeLinecap="round" />
      <circle cx="8" cy="11.9" r="1.25" fill={GLYPH_COLOR} />
    </>
  );
}

function BugGlyph(props: TGlyphProps) {
  const { color } = props;
  return (
    <>
      <path
        d="M3.3 6.9l1.9.9M12.7 6.9l-1.9.9M3 9.9h2.1M13 9.9h-2.1M3.5 12.9l1.9-1M12.5 12.9l-1.9-1"
        fill="none"
        stroke={GLYPH_COLOR}
        strokeWidth={1.1}
        strokeLinecap="round"
      />
      <circle cx="8" cy="4.8" r="1.6" fill={GLYPH_COLOR} />
      <ellipse cx="8" cy="9.6" rx="3.1" ry="3.5" fill={GLYPH_COLOR} />
      <path d="M8 6.9v5.6" fill="none" stroke={color} strokeWidth={0.9} />
    </>
  );
}

function EpicGlyph() {
  return <path d="M9.3 2.6L4.6 9h3.1l-1 4.4L11.4 7H8.3l1-4.4z" fill={GLYPH_COLOR} strokeLinejoin="round" />;
}

const renderGlyph = (iconKey: TWorkItemTypeIconKey, color: string) => {
  switch (iconKey) {
    case "sub_task":
      return <SubTaskGlyph />;
    case "story":
      return <StoryGlyph />;
    case "bug":
      return <BugGlyph color={color} />;
    case "epic":
      return <EpicGlyph />;
    case "task":
    default:
      return <TaskGlyph />;
  }
};

export type TWorkItemTypeGlyphIconProps = {
  iconKey: TWorkItemTypeIconKey;
  color: string;
  className?: string;
  /** Accessible name; the icon is decorative (aria-hidden) when omitted. */
  title?: string;
};

/** Jira glyph on a colored rounded square. */
export function WorkItemTypeGlyphIcon(props: TWorkItemTypeGlyphIconProps) {
  const { iconKey, color, className, title } = props;

  return (
    <svg
      viewBox="0 0 16 16"
      className={cn("size-4 shrink-0", className)}
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
    >
      <rect width="16" height="16" rx="3" fill={color} />
      {renderGlyph(iconKey, color)}
    </svg>
  );
}

export type TWorkItemTypeIconProps = {
  workItemType: TWorkItemType | undefined | null;
  className?: string;
  /** Adds the type name as the accessible name. */
  withTitle?: boolean;
};

/** Icon of a work item type (glyph + color resolved from its logo, flags and name). */
export function WorkItemTypeIcon(props: TWorkItemTypeIconProps) {
  const { workItemType, className, withTitle = false } = props;

  return (
    <WorkItemTypeGlyphIcon
      iconKey={getWorkItemTypeIconKey(workItemType)}
      color={getWorkItemTypeColor(workItemType)}
      className={className}
      title={withTitle ? workItemType?.name : undefined}
    />
  );
}
