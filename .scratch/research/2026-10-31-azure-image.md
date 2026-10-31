# Azure image preparation — 2026-10-31

Scope: deployment packaging only. The approved local release pair totals
97,103,872 bytes (core 67,608,576; ops 29,495,296). No source database changes,
Git mutations, cloud actions, or secrets access are part of this worker task.

[Docker build context documentation](https://docs.docker.com/build/concepts/context/)
states that the last matching ignore rule determines inclusion and that `**`
matches any number of directories. Keep the existing application allowlist,
deny nested secrets/runtime/data, then reopen only the two exact release paths.
Explicit parent-content exclusions prevent opening their siblings.
The same exclusions are necessary under source directories: a plain directory
reinclusion otherwise inherits to unlisted children in Azure's archiver.

[Microsoft's Azure CLI archive implementation](https://raw.githubusercontent.com/Azure/azure-cli/dev/src/azure-cli/azure/cli/command_modules/acr/_archive_utils.py)
loads .dockerignore, with a Dockerfile-specific ignore file taking precedence
when present. It does not load .gitignore patterns for local contexts; it
excludes common version-control metadata separately. Therefore the local
release pair need not be Git tracked to be uploaded for the build. No
Dockerfile-specific ignore file is part of this change.

[Microsoft ACR CLI reference](https://learn.microsoft.com/en-us/cli/azure/acr?view=azure-cli-latest#az-acr-build)
documents local source context, Dockerfile paths relative to its root, image
tags, and push by default. Use `az acr build --registry <ACR> --resource-group
<RG> --image sea-demo:<TAG> --file deploy/Dockerfile .` from the repository root.
[ACR quickstart](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-quickstart-task-cli)
confirms cloud builds need no local Docker installation. Do not pass secrets
as build arguments; the existing launcher consumes runtime settings.

Implementation: copy the exact SQLite pair with app ownership into the existing
SEA_RELEASE_DIR, chmod both 0444, retain the same startup command. Existing
ensure_release validates local inputs read-only, uses HF only for an absent
directory, and rejects invalid/partial existing releases. Runtime remains
separate. Frontend, Care, A2, contracts and fetch_data are unchanged.

Validation boundary: new tests enforce the literal build allowlist, exact COPY
sources/destination, ownership/read-only configuration, and exclusion ordering.
These are static configuration guards, not proof of a successful Docker/ACR
build. Existing real SQLite deployment tests check offline validation and
fallback. Cloud build and live HTTP validation belong to the controller.
The unchanged legacy lunch metadata test requires HF README YAML and conflicts
with the user's explicitly requested five-line Azure README. Final combined
result: 21 passed, 1 failed (that metadata assertion). New Azure checks alone:
5 passed. Initial RED and final outputs are in .scratch/runs/azure-image.

Local archive verification also passed using the four unmodified local packing
functions from Microsoft's official CLI source downloaded on 2026-10-31. Source
SHA256: 0ec54c63444569de359ce53664d1a03173d371df181d846b99c31db6edc10180.
The controlled context admitted exactly 15 approved files and excluded all 32
denied sentinel files, including nested secrets/runtime/truth/heldout and extra
data files. The real SQLite pair was copied into this temporary context and
archived byte-for-byte, verified by size and SHA256 against the original pair.
No actual secrets were used. The helper selects only local archive definitions
via AST; no cloud upload or authentication functions are executed. It verifies
current official source, not the controller's eventual installed CLI version.
Reproduction helper: .scratch/runs/azure-image/check_acr_archive.py; evidence:
actual-archive-verified.txt. ACR cloud build and live HTTP validation remain
controller-owned and have not been performed by this worker.
