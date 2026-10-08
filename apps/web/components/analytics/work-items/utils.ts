/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// plane package imports
import { JP_PRIORITY_COLORS, JP_PRIORITY_FALLBACK_COLOR } from "@plane/constants";
import type { ChartYAxisMetric, IState, TIssuePriorities } from "@plane/types";
import { ChartXAxisProperty } from "@plane/types";

interface ParamsProps {
  x_axis: ChartXAxisProperty;
  y_axis: ChartYAxisMetric;
  group_by?: ChartXAxisProperty;
}

export const generateBarColor = (
  value: string | null | undefined,
  params: ParamsProps,
  baseColors: string[],
  workspaceStates?: IState[]
): string => {
  if (!value) return baseColors[0];
  let color = baseColors[0];
  // Priority
  if (params.x_axis === ChartXAxisProperty.PRIORITY) {
    // Jira-parity priorities (highest/high/medium/low/lowest)
    color = Object.hasOwn(JP_PRIORITY_COLORS, value)
      ? JP_PRIORITY_COLORS[value as TIssuePriorities]
      : JP_PRIORITY_FALLBACK_COLOR;
  }

  // State
  if (params.x_axis === ChartXAxisProperty.STATES) {
    if (workspaceStates && workspaceStates.length > 0) {
      const state = workspaceStates.find((s) => s.id === value);
      if (state) {
        color = state.color;
      } else {
        const index = Math.abs(value.split("").reduce((acc, char) => acc + char.charCodeAt(0), 0)) % baseColors.length;
        color = baseColors[index];
      }
    }
  }

  return color;
};
