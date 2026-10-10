# Jira parity migrations during upstream syncs

The fork's migrations keep `jp_` in their names. Migration numbers alone do not
identify dependencies: upstream can add another `0123_*` after our `0123_jp_agent_role`.
Keep both migrations and their dependency graphs when synchronizing upstream.

Before accepting an upstream sync:

1. Inspect `uv run python manage.py showmigrations db --plan` in an isolated
   development or test database. If Django reports conflicting leaf nodes,
   inspect the operations in both branches before generating a merge migration.
2. For independent operations, run `uv run python manage.py makemigrations db
--merge --name jp_upstream_merge`. Check that the generated migration depends
   on both leaf nodes. Do not delete or renumber migrations already shipped.
3. If both branches alter the same field (including role or priority choices),
   reconcile the intended final model and add explicit operations after the
   merge. An empty merge only joins dependencies; it does not resolve conflicting
   schema or data semantics.
4. Check `uv run python manage.py makemigrations --check --dry-run`, then test
   migration from each previously supported leaf as well as a fresh database.
   Run the Jira parity regression suite on the resulting schema.

Use new forward data migrations for corrections that existing installations
must receive. Editing an earlier `RunPython` operation only changes fresh
installations. In particular, legacy Viewer invites and human accounts that
previously held Agent roles require cleanup after the Agent account marker is
available. Do not infer account ownership or upgrade a human account into an
Agent from its historical numeric role.

Migration reversal must not reinterpret Agent role 10 as a legacy Viewer or
leave unsupported roles behind. Keep explicit downgrade handling with the role
choices migration, and test the reverse path using an isolated database.
