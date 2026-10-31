# Integrated local operations console

The default Next.js page reads A2 assessments and A3 gates from the Python pipeline. NEXT runs A3, A2 and A1. Chat messages, cancellation confirmations and staff handoffs use the real local runtime. Ledger records are local, not external wallet payments. Web voice is not implemented.

Start the backend from the repository root. Keep runtime state outside any ancestor folder named data because the current platform path validator rejects those paths.

```powershell
.\.venv\Scripts\python.exe -m platform_huy.serve_ui --integrated --port 8765 --state-path "$env:LOCALAPPDATA/Temp/sea-console/state.sqlite"
```

In a second terminal, start Next.js.

```powershell
cd frontend
$env:PIPELINE_URL = 'http://127.0.0.1:8765'
npm run build
npm run start -- --hostname 127.0.0.1
```

Open http://127.0.0.1:3000. NEXT advances replay by 30 minutes and can create eligible local contacts. The list is the backend's priority queue of up to 30 orders plus the selected order. It is not the full assessment list. A3 controls are available under Giám sát dữ liệu. Cancellation requires a second confirmation and remains a review request.

To enable actual OpenAI calls, install the shared development requirements and add `--llm` to the Python command. The launcher reads `OPENAI_API_KEY` and optional `OPENAI_MODEL` from the repository `.env`, preserving values already set in the environment. The default model is `gpt-4o-mini`. The UI shows whether LLM is enabled and whether the latest returned turn used it. A1 calls OpenAI for explanation and clarification turns to select an approved phrase ID. Application code renders all dates, amounts and facts. Other intents use rules. Timeout or invalid output falls back to templates. A2 and A3 do not call the model. Do not add API credentials to frontend environment variables.

`PIPELINE_URL` and optional `LIVE_PRESENTER_KEY` are server environment variables. They are never sent to the browser. This console is for localhost presenter use. The proxy rejects public Host headers and forwarded-host requests. Start Next on loopback and do not expose it through a tunnel or reverse proxy. This is not customer authentication.

On an uncertain chat response, retry the same text. The page reuses its request key until success. NEXT and other commands are never automatically retried. Reload runtime state before deciding whether to advance again.

```powershell
npm run typecheck
npm run lint
npm run build
npm run test:e2e
```

The browser tests require an isolated, running release-fed backend. They mutate that runtime through chat, handoff and A3 controls. Use a fresh state path for each run. Set `PIPELINE_URL` in the test shell and `PLAYWRIGHT_CHANNEL=chrome` if Chromium is unavailable.
