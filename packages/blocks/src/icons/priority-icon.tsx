/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import * as React from "react";
import type { TIssuePriorities as TIssuePrioritiesBase } from "@plane/types";
import { cn } from "@plane/utils";
import { PriorityNone } from "@makeplane/propel/icons";

// Jira-parity priorities: highest / high / medium / low / lowest (the union lives in @plane/types).
export type IssuePriority = TIssuePrioritiesBase;

/** @deprecated Use IssuePriority instead. */
export type TIssuePriorities = IssuePriority;

export type PriorityIconProps = {
  className?: string;
  priority: IssuePriority | undefined | null;
};

/** @deprecated Use PriorityIconProps instead. */
export type IPriorityIcon = PriorityIconProps;

type TPriorityGlyphProps = React.SVGProps<SVGSVGElement>;

/** Shared frame for the Jira-style glyphs: 16x16, stroked with the current text color. */
function PriorityGlyph({ children, ...props }: TPriorityGlyphProps) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 16 16"
      width="1em"
      height="1em"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {children}
    </svg>
  );
}

/** Highest: double chevron up. */
export function PriorityHighestIcon(props: TPriorityGlyphProps) {
  return (
    <PriorityGlyph data-priority="highest" {...props}>
      <polyline points="3.5,8 8,3.5 12.5,8" />
      <polyline points="3.5,12.5 8,8 12.5,12.5" />
    </PriorityGlyph>
  );
}

/** High: chevron up. */
export function PriorityHighIcon(props: TPriorityGlyphProps) {
  return (
    <PriorityGlyph data-priority="high" {...props}>
      <polyline points="3.5,10.25 8,5.75 12.5,10.25" />
    </PriorityGlyph>
  );
}

/** Medium: equals sign. */
export function PriorityMediumIcon(props: TPriorityGlyphProps) {
  return (
    <PriorityGlyph data-priority="medium" {...props}>
      <line x1="3" y1="6" x2="13" y2="6" />
      <line x1="3" y1="10" x2="13" y2="10" />
    </PriorityGlyph>
  );
}

/** Low: chevron down. */
export function PriorityLowIcon(props: TPriorityGlyphProps) {
  return (
    <PriorityGlyph data-priority="low" {...props}>
      <polyline points="3.5,5.75 8,10.25 12.5,5.75" />
    </PriorityGlyph>
  );
}

/** Lowest: double chevron down. */
export function PriorityLowestIcon(props: TPriorityGlyphProps) {
  return (
    <PriorityGlyph data-priority="lowest" {...props}>
      <polyline points="3.5,3.5 8,8 12.5,3.5" />
      <polyline points="3.5,8 8,12.5 12.5,8" />
    </PriorityGlyph>
  );
}

const PRIORITY_ICONS: Record<IssuePriority, (props: TPriorityGlyphProps) => React.ReactElement> = {
  highest: PriorityHighestIcon,
  high: PriorityHighIcon,
  medium: PriorityMediumIcon,
  low: PriorityLowIcon,
  lowest: PriorityLowestIcon,
};

// Full class literals so Tailwind generates them (tokens defined in @plane/tailwind-config).
const PRIORITY_ICON_CLASSES: Record<IssuePriority, string> = {
  highest: "text-priority-highest",
  high: "text-priority-high",
  medium: "text-priority-medium",
  low: "text-priority-low",
  lowest: "text-priority-lowest",
};

export function PriorityIcon(props: PriorityIconProps) {
  const { priority, className = "size-3.5" } = props;

  // No value yet (e.g. an empty picker): neutral placeholder glyph.
  if (!priority) return <PriorityNone className={cn("shrink-0 text-priority-none", className)} />;

  // Unknown (e.g. a stale legacy key): render nothing rather than a misleading icon.
  if (!Object.hasOwn(PRIORITY_ICONS, priority)) return null;
  const Icon = PRIORITY_ICONS[priority];

  return <Icon className={cn("shrink-0", PRIORITY_ICON_CLASSES[priority], className)} />;
}
