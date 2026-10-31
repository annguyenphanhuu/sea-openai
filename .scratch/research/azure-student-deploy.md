# Azure student deployment decision — 2026-10-31

Observed at 14:09 Asia/Ho_Chi_Minh. Estimates are engineering estimates, not service guarantees.

| Priority / route | Student availability and observed evidence | Estimate | Main risk | Primary source |
|---|---|---|---|---|
| 1. Linux Python 3.11 App Service B1, source ZIP | **Verified:** `sea-openai-b1` in East Asia created successfully, status Ready. B1 consumes credit; it is not claimed free. | 5–10 minutes after provisioning | Source upload/Oryx dependency installation | https://learn.microsoft.com/en-us/azure/app-service/quickstart-python |
| 2. GitHub Actions → GHCR → Container Apps | Student offer includes Container Apps; actual regional quota still needs validation. Repo push permission verified, no admin permission. | 10–20 minutes | GHCR publication permissions/package visibility and environment quota | https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images ; https://learn.microsoft.com/en-us/azure/container-apps/get-started |
| 3. Local Docker → ACR | Registry exists. Docker executable exists but daemon is unavailable on this machine. | 8–15 minutes if daemon starts; 25–60+ otherwise | WSL/engine startup or reboot | https://learn.microsoft.com/en-us/azure/container-registry/container-registry-get-started-docker-cli |
| 4. GHCR → Container Instances | Credit-backed service candidate; subscription quota and region are not yet verified. | 5–10 minutes once image exists | Capacity and HTTPS setup | https://learn.microsoft.com/en-us/azure/container-instances/container-instances-quickstart |
| 5. B1s VM → Python/nginx | Student offer advertises eligible VM allowance; actual B1s availability is not established. | 20–40 minutes | VM quota plus manual service/TLS setup | https://azure.microsoft.com/en-us/free/students/ ; https://learn.microsoft.com/en-us/azure/virtual-machines/linux/quick-create-portal |

Decision: choose route 1 because the actual B1 plan is Ready, avoiding Docker and ACR Tasks. Use a clean source ZIP with only approved application files and the two immutable SQLite files; no secrets, truth, frontend, node_modules or Git metadata. Startup must use PORT (default 8000); enable Always On and presenter authentication. Credentials are sent only to Azure configuration from process memory. Final code is gated on the user's requested merge/tests before deployment.

ACR build attempt 3 uploaded its context successfully but failed before building with TasksOperationsNotAllowed. Microsoft documents temporary ACR Tasks restrictions for Azure free-credit accounts: https://learn.microsoft.com/en-us/azure/container-registry/container-registry-tasks-overview . Repeating tags cannot repair that permission failure.

Independent researcher: azure_paths_research reviewed routes 2–5. No resource was deleted. If route 1 fails for over five minutes, proceed to route 2 rather than repeatedly retrying it.
