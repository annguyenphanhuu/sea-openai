# MongoDB setup plan

1. `how` over the affected subsystem.
   Complete. The repository has SQLite source contracts and no MongoDB adapter.
2. `architect` for parallel design exploration.
   skip: parent supplied the interface and forbade child delegation.
   Compare direct client use with a settings record and managed connection.
   Choose the latter for isolated configuration and cleanup.
3. Write the throughput checkpoint as four todo items.
   - Blocking first steps. Read repository rules and preserve SQLite inputs.
   - Independent workstreams. One worker owns code, docs, and isolated tests.
     Parent owns dependency installation, live ping, and complete tests.
   - Shared mutable state. Implementation uses the isolated worktree.
     The worker does not edit `.env` or the primary checkout.
   - Smallest safe decomposition. One worker keeps configuration and usage aligned.
4. Delegate code-writing to a subagent using your configured feature model.
   Complete. The parent delegated this bounded setup to this worker.
5. Verify on the matching surface.
   Run isolated pytest tests. Parent runs the real CLI and full suite.
6. Rebase into small, ordered commits. Stack follow-ups.
   Parent owns Git operations after review.
7. If the design is contested, `interrogate` before shipping.
   skip: no contested design.
8. Run **Opening a PR**.
   Parent owns delivery.

## Implementation

- Add `MongoSettings`, `load_mongo_settings`, and `mongo_database` in one module.
- Add the read-only ping CLI with safe failure output.
- Pin PyMongo and python-dotenv. Extend the environment example and usage docs.
- Test environment precedence, root-relative `.env`, safe failures, raw credentials,
  timeouts, and guaranteed connection cleanup.
