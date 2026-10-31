# Remote storage preflight — 2026-10-31

## Decision and gate

Task 1a provides a runnable compatibility probe and offline protocol tests. Task
1b (live Turso compatibility) is **BLOCKED**: the user confirmed there is no Turso
configuration yet. No credentials were requested from logs, printed, or used;
no service was provisioned and no real database was contacted. Ownership and
persistence approval conflicts were explicitly deferred by the user for this
implementation. That authorization is not a live-engine compatibility result.

Use Python 3.11+ and HTTPX 0.28.1 (development/test dependency). The runtime
driver is deliberately not pinned as proven. Existing runtime requirements stay
unchanged. No remote business adapter or local fallback was introduced.

## Official sources checked on execution date

- [Turso HTTP reference](https://docs.turso.tech/sdk/http/reference): SQL over
  HTTPS is an explicit supported interface, rather than a sqlite3 connection swap.
- [Hrana 3 protocol](https://github.com/tursodatabase/libsql/blob/main/docs/HRANA_3_SPEC.md):
  a stream represents a SQL connection. HTTP `/v3/pipeline` opens a stream with
  null baton and returns the next baton, which must be used serially. Ordered
  pipeline requests all execute even after individual SQL errors. Consequently
  this probe checks each transaction statement separately before issuing COMMIT.
- [Turso Python quickstart](https://docs.turso.tech/sdk/python/quickstart): reviewed
  alongside the wire protocol; no assumption that a synchronous SDK is async.
- [HTTPX async client](https://www.python-httpx.org/async/) and
  [package metadata](https://pypi.org/project/httpx/0.28.1/): AsyncClient supplies
  awaited network operations with Python 3.11 support. The installed/tested
  version is 0.28.1, pinned only for development probe/test tooling.
- [HF disk storage](https://huggingface.co/docs/hub/main/spaces-storage): the
  Space filesystem is ephemeral across stop/restart, so it cannot be the commit
  authority for runtime state.
- [FastAPI concurrency](https://fastapi.tiangolo.com/async/): async routes need
  awaited I/O; directly called synchronous utilities are not automatically moved
  to a thread. The probe's HTTP I/O uses AsyncClient rather than blocking calls.

## Probe interface and safety

`probe(database_url: str, token: str) -> dict` is a synchronous standalone entry
point around an async runner. It must be called outside an already-running event
loop. `python -m scripts.probe_remote_storage` reads only:

- `TURSO_TEST_DATABASE_URL` — dedicated disposable test database origin;
- `TURSO_TEST_AUTH_TOKEN` — test DB credential;
- `TURSO_PROBE_ALLOW_WRITES=isolated-test-database` — explicit operator attestation.

No automatic `.env` loading occurs. Missing opt-in/credentials returns BLOCKED
and CLI exit 2 before network access. HTTPS or libsql origins are accepted;
libsql is converted to HTTPS. Embedded userinfo, query secrets, fragments, paths,
and HTTP are rejected. HTTP redirects are disabled. Changed server routing
origins fail closed instead of forwarding credentials. Error reports suppress
remote text/URLs and never include the token.

Every run uses random `probe_<uuid>_parent` and `_child` tables. Only these tables
are dropped, in dependency order, via a new cleanup stream. Failed cleanup returns
FAIL and the generated namespace for manual inspection. No source DB is opened.
This still requires an isolated test DB: the probe intentionally writes and DDL
can contend with other database users.

## Checks and evidence

Initial RED: `pytest -q acceptance_huy/test_service_storage.py` reported **8
failed in 0.17s**, with `remote storage compatibility probe is not implemented`;
this did not depend on credentials. GREEN after implementation and additional
negative cases: **13 passed in 0.30s**. The harness uses real in-memory SQLite
connections behind HTTPX MockTransport and rotating Hrana batons; it is not a
live Turso substitute or evidence of the remote engine's semantics.

The runnable checks exercise migration twice while preserving rows; FK, CHECK,
and UNIQUE rejection with constraint-specific error codes; explicit transaction
rollback with no row leakage; concurrent independent-stream duplicate inserts
with one winner and one persisted row; CAS expected_version with one affected
row; and COMMIT response loss followed by receipt lookup on a new HTTP client
and stream. COMMIT and close share a pipeline to avoid leaking the successful
fault stream. Writes and COMMIT are never retried. A pre-COMMIT disconnect must
fail reconciliation; arbitrary SQL errors cannot masquerade as constraint proof.

Malformed protocol, unsafe routing, falsely accepted constraints, network error
redaction, missing opt-in, and unsafe URL cases are covered. A delayed async
transport test proves the event loop continues to run heartbeat work while an
HTTP operation waits; it is a responsiveness assertion, not a throughput claim.

Actual CLI execution without test configuration returned:

```json
{"reason": "Set TURSO_PROBE_ALLOW_WRITES=isolated-test-database only for a dedicated test DB.", "status": "BLOCKED"}
```

No live capability is recorded as PASS. All nine live checks are NOT RUN; actual
libSQL/SQLite engine version is UNVERIFIED until the first remote response.

## Limitations and next gate

Transactions are server-side BEGIN IMMEDIATE/COMMIT/ROLLBACK on one serial Hrana
stream, with a 10-second HTTP timeout per request and no write retries. Each
transaction owns its stream. The wire format is an intentionally small probe
client, not a general-purpose production driver. PRAGMA foreign_keys is enabled
and verified on the constraint-test stream. Production adapters must enable it
for every business connection and handle authorization, migrations, leases,
transaction expiry, and ambiguous outcomes independently.

A lost response before COMMIT can leave an open remote transaction until the
server expires it; cleanup may then fail and the report exposes the isolated
namespace. A new client reconnect check proves state survives closing a client;
it does **not** prove a hosted server or HF process restart. The new client and
stream are actually instantiated, not simulated by rereading a cached result.

Before remote integration: configure a dedicated Turso test DB, run the CLI,
record engine version and PASS/FAIL for each capability and cleanup, verify
server routing behavior, and perform a real restart/persistence smoke check on
the deployed runtime. If any engine invariant fails, stop remote integration;
do not fall back to local SQLite. HF account/DB account readiness and hosted
restart evidence remain unverified. Tasks 2–3 may develop independent local
ports, but remote business integration remains gated.
