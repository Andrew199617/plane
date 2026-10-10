/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Run with tsx --test --tsconfig apps/web/tsconfig.json <this file> from the repo root.
import assert from "node:assert/strict";
import { test } from "node:test";
import { observable, runInAction } from "mobx";
import type { TProjectCategory, TTeam, TWorkItemType } from "@plane/types";
import type { CoreRootStore } from "@/store/root.store";
import { ProjectCategoriesStore } from "./project-categories.store";
import { TeamsStore } from "./teams.store";
import { WorkItemTypesStore } from "./work-item-types.store";

const deferred = <T>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
};

const makeRoot = () => ({ router: observable({ workspaceSlug: "a" }) }) as unknown as CoreRootStore;
const type = (id: string) => ({ id, name: id, is_active: true, is_default: true }) as TWorkItemType;
const team = (id: string) => ({ id, name: id, member_ids: [], project_ids: [] }) as unknown as TTeam;
const category = (id: string): TProjectCategory => ({
  id,
  name: id,
  description: "",
  sort_order: 1,
  logo_props: { in_use: "icon" },
  project_ids: [],
});

const cases = [
  {
    name: "work item types",
    make: (root: CoreRootStore) => {
      const store = new WorkItemTypesStore(root);
      return {
        list: store.fetchWorkItemTypes,
        update: store.updateWorkItemType,
        service: store.service,
        item: type,
        visible: () => store.workItemTypes.map((item) => item.id),
        lookup: (id: string) => store.getWorkItemTypeById(id)?.id,
      };
    },
  },
  {
    name: "teams",
    make: (root: CoreRootStore) => {
      const store = new TeamsStore(root);
      return {
        list: store.fetchTeams,
        update: store.updateTeam,
        service: store.service,
        item: team,
        visible: () => store.sortedTeams.map((item) => item.id),
        lookup: (id: string) => store.getTeamById(id)?.id,
      };
    },
  },
  {
    name: "categories",
    make: (root: CoreRootStore) => {
      const store = new ProjectCategoriesStore(root);
      return {
        list: store.fetchProjectCategories,
        update: store.updateCategory,
        service: store.service,
        item: category,
        visible: () => store.sortedCategories.map((item) => item.id),
        lookup: (id: string) => store.getCategoryById(id)?.id,
      };
    },
  },
];

for (const entry of cases) {
  test(`${entry.name}: a late settings update cannot insert another workspace's data`, async () => {
    const root = makeRoot();
    const store = entry.make(root);
    store.service.list = (async (slug: string) => [store.item(slug)]) as typeof store.service.list;
    await store.list("a");
    const lateUpdate = deferred<unknown>();
    store.service.update = (() => lateUpdate.promise) as typeof store.service.update;
    const update = store.update("a", "a", { name: "changed" });
    runInAction(() => {
      root.router.workspaceSlug = "b";
    });
    await store.list("b");
    lateUpdate.resolve(store.item("a-updated"));
    await update;
    assert.deepEqual(store.visible(), ["b"]);
    assert.equal(store.lookup("a-updated"), undefined);
  });

  test(`${entry.name}: A -> B -> A hydrates the active workspace and rejects late A/B responses`, async () => {
    const root = makeRoot();
    const store = entry.make(root);
    // Each response is controlled independently to reproduce request completion out of order.
    const pending: ReturnType<typeof deferred<unknown[]>>[] = [];
    store.service.list = (() => {
      const request = deferred<unknown[]>();
      pending.push(request);
      return request.promise;
    }) as typeof store.service.list;

    const a1 = store.list("a");
    runInAction(() => {
      root.router.workspaceSlug = "b";
    });
    const b = store.list("b");
    runInAction(() => {
      root.router.workspaceSlug = "a";
    });
    const a2 = store.list("a");
    pending[2].resolve([store.item("a-new")]);
    await a2;
    assert.deepEqual(store.visible(), ["a-new"]);
    pending[1].resolve([store.item("b")]);
    await b;
    pending[0].resolve([store.item("a-old")]);
    await a1;
    assert.deepEqual(store.visible(), ["a-new"]);
    assert.equal(store.lookup("b"), undefined);
    assert.equal(store.lookup("a-old"), undefined);
  });

  test(`${entry.name}: old workspace data is hidden before the next fetch and background fetches cannot clear it`, async () => {
    const root = makeRoot();
    const store = entry.make(root);
    store.service.list = (async (slug: string) => [store.item(slug)]) as typeof store.service.list;
    await store.list("a");
    runInAction(() => {
      root.router.workspaceSlug = "b";
    });
    assert.deepEqual(store.visible(), []);
    assert.equal(store.lookup("a"), undefined);
    await store.list("b");
    const lateA = deferred<unknown[]>();
    store.service.list = (() => lateA.promise) as typeof store.service.list;
    const background = store.list("a");
    assert.deepEqual(store.visible(), ["b"]);
    lateA.resolve([store.item("a")]);
    await background;
    assert.deepEqual(store.visible(), ["b"]);
  });
}
