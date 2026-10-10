/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import type { TMyStateTransitions } from "@plane/types";
import type { CoreRootStore } from "@/store/root.store";
import { WorkflowsStore } from "./workflows.store";

const rules = (extra: Record<string, string[]> = {}): TMyStateTransitions => ({
  restricted: true,
  role: 10,
  epic_locked: true,
  transitions: { todo: ["doing"], doing: [], ...extra },
});
const makeStore = () =>
  new WorkflowsStore({
    router: { workspaceSlug: "a" },
    user: { permission: { isAgentInProject: () => true } },
  } as unknown as CoreRootStore);
const deferred = () => {
  let resolve!: (value: TMyStateTransitions) => void;
  const promise = new Promise<TMyStateTransitions>((done) => {
    resolve = done;
  });
  return { resolve, promise };
};

test("concurrent callers share the pending refresh instead of receiving the stale snapshot", async () => {
  const store = makeStore();
  store.service.getMyTransitions = async () => rules();
  await store.fetchMyTransitions("a", "project");
  const request = deferred();
  let calls = 0;
  store.service.getMyTransitions = () => {
    calls++;
    return request.promise;
  };
  const first = store.ensureMyTransitions("a", "project", "new-state");
  const second = store.ensureMyTransitions("a", "project", "new-state");
  assert.equal(first, second);
  assert.equal(calls, 1);
  request.resolve(rules({ "new-state": ["doing"] }));
  await Promise.all([first, second]);
  assert.equal(store.canTransition("project", "new-state", "doing"), true);
  assert.equal(store.canTransition("project", "new-state", "doing", true), false);
});

test("a failed unknown-state refresh can retry, while a successful omission does not loop", async () => {
  const store = makeStore();
  store.service.getMyTransitions = async () => rules();
  await store.fetchMyTransitions("a", "project");
  let calls = 0;
  store.service.getMyTransitions = async () => {
    calls++;
    throw new Error("offline");
  };
  assert.equal(await store.ensureMyTransitions("a", "project", "new-state"), undefined);
  store.service.getMyTransitions = async () => {
    calls++;
    return rules();
  };
  await store.ensureMyTransitions("a", "project", "new-state");
  await store.ensureMyTransitions("a", "project", "new-state");
  assert.equal(calls, 2);
  // A later project snapshot may introduce the previously missing state.
  store.service.getMyTransitions = async () => rules({ "new-state": ["doing"] });
  await store.fetchMyTransitions("a", "project");
  assert.equal(store.canTransition("project", "new-state", "doing"), true);
});

test("a slow request cannot overwrite newer workflow rules", async () => {
  const store = makeStore();
  const old = deferred();
  const latest = deferred();
  let calls = 0;
  store.service.getMyTransitions = () => (calls++ === 0 ? old.promise : latest.promise);
  const first = store.fetchMyTransitions("a", "project");
  const second = store.fetchMyTransitions("a", "project");
  latest.resolve(rules({ todo: ["done"] }));
  await second;
  old.resolve(rules());
  await first;
  assert.equal(store.canTransition("project", "todo", "done"), true);
  assert.equal(store.canTransition("project", "todo", "doing"), false);
});

test("lazy board transitions expire after a minute, including changes to existing states", async () => {
  const store = makeStore();
  const originalNow = Date.now;
  let now = 100_000;
  Date.now = () => now;
  try {
    let calls = 0;
    store.service.getMyTransitions = async () => {
      calls++;
      return calls === 1 ? rules() : rules({ todo: ["done"] });
    };
    await store.ensureMyTransitions("a", "project", "todo");
    await store.ensureMyTransitions("a", "project", "todo");
    assert.equal(calls, 1);
    now += 60_000;
    await store.ensureMyTransitions("a", "project", "todo");
    assert.equal(calls, 2);
    assert.equal(store.canTransition("project", "todo", "done"), true);
  } finally {
    Date.now = originalNow;
  }
});
