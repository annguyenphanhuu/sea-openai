---
title: SEA synthetic logistics demo
sdk: docker
app_port: 7860
---

# Docker Space setup

This is a synthetic simulation using immutable release SQLite inputs. It does
not credit a real Shopee wallet or call a financial provider. The existing UI
and A3 HTTP API are served; A1 draft UI is not a claim of live A1 transport.

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
| `SEA_DATASET_REVISION` | Optional variable | Dataset revision/tag/commit; defaults to `main`; pin a commit for repeatable demos |
| `SEA_RELEASE_DIR` | Optional variable | Defaults in Docker to `/home/app/app/data/release_main` |
| `SEA_STATE_PATH` | Optional variable | Defaults in Docker to `/home/app/app/runs/a3-demo/state.sqlite` |

The dataset must contain `release_main/core_14d.sqlite` and
`release_main/ops_14d.sqlite`; `release_main/manifest.sha256` is optional. Only
these exact paths are fetched with `snapshot_download`. If a manifest exists,
it must contain SHA256 entries for both SQLite files using their basenames.
Other manifest entries are ignored because their files are outside this demo's
download scope. Never place the token in Docker build arguments, Dockerfile,
source files or the image.

Startup command: `python -m deploy.start_space`. It validates both inputs before
launching `python -m platform_huy.serve_ui --host 0.0.0.0 --port 7860`. A valid
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

Startup rejects runtime paths inside the release directory or aliases of either
source database, including hardlinks outside that directory.

Local image build from the application repository root:

```sh
docker build -f deploy/Dockerfile -t sea-demo .
```

Configure runtime variables/secrets in the hosting environment. No real Space
deployment or private dataset download is implied by the local verification.
The local UI retains its default loopback bind and port 8765 via
`python -m platform_huy.serve_ui`.

References: [Docker Spaces](https://huggingface.co/docs/hub/en/spaces-sdks-docker),
[Space YAML](https://huggingface.co/docs/hub/en/spaces-config-reference),
[Hub downloads](https://huggingface.co/docs/huggingface_hub/en/guides/download).
