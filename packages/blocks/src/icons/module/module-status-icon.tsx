/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import * as React from "react";

import { ModuleCompletedIcon } from "./completed";
import { ModulePlannedIcon } from "./planned";

// Jira-parity: releases (modules) are only Unreleased / Released.
export type ModuleStatus = "unreleased" | "released";

/** @deprecated Use ModuleStatus instead. */
export type TModuleStatus = ModuleStatus;

export type ModuleStatusIconProps = {
  status: ModuleStatus;
  className?: string;
  height?: string;
  width?: string;
};

/** Released = green check; Unreleased (and any unknown/legacy value) = the open, dashed "planned" ring. */
export function ModuleStatusIcon({ status, className, height = "12px", width = "12px" }: ModuleStatusIconProps) {
  if (status === "released") return <ModuleCompletedIcon className={className} height={height} width={width} />;
  return <ModulePlannedIcon className={className} height={height} width={width} />;
}
