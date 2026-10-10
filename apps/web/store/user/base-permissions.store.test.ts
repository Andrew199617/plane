/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import { runInAction } from "mobx";
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
import type { IWorkspaceMemberMe } from "@plane/types";
import type { RootStore } from "@/store/root.store";
import { BaseUserPermissionStore } from "./base-permissions.store";

test("Guest-compatible actions exclude agents, while read gates and explicit agent actions allow them", () => {
  const store = new BaseUserPermissionStore({ router: { workspaceSlug: "a", projectId: "p" } } as RootStore);
  runInAction(() => {
    store.workspaceUserInfo.a = { role: EUserPermissions.AGENT } as IWorkspaceMemberMe;
    store.workspaceProjectsPermissions.a = { p: EUserPermissions.AGENT };
  });
  const guestRoles = [EUserPermissions.ADMIN, EUserPermissions.MEMBER, EUserPermissions.GUEST];
  for (const level of [EUserPermissionsLevel.WORKSPACE, EUserPermissionsLevel.PROJECT]) {
    assert.equal(store.allowPermissions(guestRoles, level), false);
    assert.equal(store.allowReadPermissions(guestRoles, level), true);
    assert.equal(store.allowReadPermissions([EUserPermissions.ADMIN, EUserPermissions.MEMBER], level), false);
    assert.equal(store.allowPermissions([EUserPermissions.AGENT], level), true);
    assert.equal(
      store.allowReadPermissions(guestRoles, level, undefined, undefined, () => false),
      false
    );
  }
  runInAction(() => {
    store.workspaceUserInfo.a.role = EUserPermissions.GUEST;
    store.workspaceProjectsPermissions.a.p = EUserPermissions.GUEST;
  });
  assert.equal(store.allowPermissions(guestRoles, EUserPermissionsLevel.PROJECT), true);
  assert.equal(store.allowReadPermissions(guestRoles, EUserPermissionsLevel.PROJECT), true);
});
