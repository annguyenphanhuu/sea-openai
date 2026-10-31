# HF Docker Space deployment research — 2026-10-31

Read before implementation, in the lunch-deploy private worktree. No HF remote,
credentials or external deployment were accessed.

- [Docker Spaces](https://huggingface.co/docs/hub/en/spaces-sdks-docker): Docker SDK exposes an HTTP app on port 7860 by default; runtime variables and secrets are environment variables. Container UID is 1000. Use a matching non-root user and owned working directory. Disk can be lost on restart.
- [Space configuration](https://huggingface.co/docs/hub/en/spaces-config-reference): root README YAML selects `sdk: docker` and `app_port: 7860`.
- [Hub downloads](https://huggingface.co/docs/huggingface_hub/en/guides/download) and [snapshot API](https://huggingface.co/docs/huggingface_hub/package_reference/file_download): `snapshot_download` supports `repo_type="dataset"`, `token`, `revision`, `local_dir` and exact `allow_patterns`. A local directory mirrors remote paths. Restrict downloads to `release_main/core_14d.sqlite`, `release_main/ops_14d.sqlite`, and optional `release_main/manifest.sha256`.
- [Maintainer package metadata](https://pypi.org/project/huggingface-hub/1.16.4/): version 1.16.4 exists, requires Python >=3.10, and supplies a universal Python wheel. Pin only the deployment requirement; the existing application uses the standard library. Downloader import stays lazy so common acceptance collection needs no Hub package.

Implementation decision: Python 3.11 Docker image; explicit COPY allowlist; module launcher validates existing offline release first, otherwise downloads into a sibling staging directory and publishes the validated release directory atomically. Read-only SQLite quick checks plus both hashes when a manifest exists. Missing/partial/corrupt existing releases fail closed. Runtime SQLite remains separate under runs on ephemeral local disk. No MongoDB. Missing dataset ID is a required configuration error, never an invented ID. HF_TOKEN is runtime-only, never a build argument or file in the image.

Observed local verification limits: installed Python is 3.13.2; installed Hub client is 0.36.2. Docker CLI 26.1.1 exists but daemon pipe is unavailable. Image build and actual private dataset download cannot be claimed as verified. No dataset repo ID/token was provided.

Controller approved a minimal HTTPS Origin compatibility change: HF proxy
termination means browser Origin can be HTTPS while this app receives HTTP.
Permit either scheme for the exact Host header; retain rejection of other hosts.
Real HTTP tests cover successful same-host HTTPS NEXT and denied other-host NEXT.

Independent review reproduced an unsafe custom runtime path aliasing the ops
database in a temporary synthetic release. The controller added four failing
regressions, then startup validation requiring runtime outside the release and
not samefile with either source, including hardlinks. A3Demo also rejects direct
ops aliases. Both source DBs remained unchanged in the subsequent real-release
executor smoke. This supplements the worker's initial deployment verification.
