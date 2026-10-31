---
title: SEA synthetic logistics demo
sdk: docker
app_port: 7860
---

# Docker Space setup

This is a synthetic simulation using immutable release SQLite inputs. It does
not credit a real Shopee wallet or call a financial provider. NEXT runs the real
local A3, A2 and A1 modules; messages and effects use a SQLite-backed web inbox.
This demonstrates prepared synthetic data, not live marketplace orders.

Prepare a Space repository from the application source allowlist below. Copy
this README to its root `README.md`, and `deploy/Dockerfile` to its root
`Dockerfile`. Keep `deploy/` itself too. HF reads Docker metadata from the root
README. Use the same source tree as the tested application; do not upload local
data, truth labels, .env files, runs, Git metadata or scratch evidence.

Required source directories/files: `contracts/*.py`, `contracts/*.sql`,
`logistics_an_nguyen/*.py`, `care_truc/*.py`, `care_truc/schema.sql`,
`platform_huy/*.py`, `platform_huy/migrations/*.sql`,
`platform_huy/ui_prototype/`, `deploy/*.py`, `deploy/requirements.txt`,
`deploy/Dockerfile`, `.dockerignore`.

In the Space Settings, configure:

| Setting | Kind | Value |
| --- | --- | --- |
| `SEA_DATASET_REPO` | Variable | Actual private dataset repo ID (`owner/name`); no default ID exists |
| `HF_TOKEN` | Secret | Read access to that private dataset; runtime only |
| `LIVE_PRESENTER_KEY` | Secret | Required presenter password for the integrated HTTP API; enter it on the page |
| `OPENAI_API_KEY` | Secret | Optional provider credential; the deterministic demo path does not need an LLM |
| `SEA_INTEGRATED` | Variable | `1` runs the complete A3/A2/A1 demonstration |
| `SEA_DATASET_REVISION` | Optional variable | Dataset revision/tag/commit; defaults to `main`; pin a commit for repeatable demos |
| `SEA_RELEASE_DIR` | Optional variable | Defaults in Docker to `/home/app/app/data/release_main` |
| `SEA_STATE_PATH` | Optional variable | Defaults in Docker to `/home/app/app/runs/integrated-demo/state.sqlite` |

The dataset must contain `release_main/core_14d.sqlite` and
`release_main/ops_14d.sqlite`; `release_main/manifest.sha256` is optional. Only
these exact paths are fetched with `snapshot_download`. If a manifest exists,
it must contain SHA256 entries for both SQLite files using their basenames.
Other manifest entries are ignored because their files are outside this demo's
download scope. Never place the token in Docker build arguments, Dockerfile,
source files or the image.

Startup command: `python -m deploy.start_space`. It validates both inputs before
launching `python -m platform_huy.serve_ui --integrated --host 0.0.0.0 --port 7860`. A valid
existing local release works offline without HF configuration. An invalid or
partial existing release fails startup; explicitly repair it or select a fresh
directory. Downloads use a temporary sibling directory and publish the complete
validated release with one directory rename. Optional manifest hashes and real
SQLite quick checks run before serving.

SQLite runtime state lives separately on the Space's local disk. Returning to
the baseline after a Space restart is acceptable. Transactions and retry
protection still apply within a run; the launcher does not reset a surviving
runtime file. There is no MongoDB backend. NEXT advances simulation time by
exactly 30 minutes; host wall time does not advance business time.

Keep the Space private. The homepage loads before presenter authentication;
every integrated API request requires `X-Presenter-Key`. Enter the dedicated
key into the page's presenter control. It stays in page memory and is cleared
when the page reloads. It is never embedded in URLs, HTML, logs or source files.
For private Space API checks, use both the HF authorization header and the
presenter header; do not place either secret in command-line arguments.

The initial NEXT selects a real release COD order and opens eligible chats.
Huy must complete the evidence-based staff review on the page before granting
coins. Customer text is stored from the actual A1 session. Cancellation only
queues a request requiring approval. The Next.js frontend is not part of this
deployment's source allowlist.

Startup rejects runtime paths inside the release directory or aliases of either
source database, including hardlinks outside that directory.

Local image build from the application repository root:

```sh
docker build -f deploy/Dockerfile -t sea-demo .
```

Configure runtime variables/secrets in the hosting environment. Deployment and
live HTTP evidence are recorded separately in `.scratch/runs/deploy/hf.log`.
The local UI retains its default loopback bind and port 8765 via
`python -m platform_huy.serve_ui`.

References: [Docker Spaces](https://huggingface.co/docs/hub/en/spaces-sdks-docker),
[Space YAML](https://huggingface.co/docs/hub/en/spaces-config-reference),
[Hub downloads](https://huggingface.co/docs/huggingface_hub/en/guides/download).
