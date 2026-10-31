# sea-openai

Late-delivery hackathon scaffold for Huy, An Nguyen, and Truc.

- [Team ownership, seven-hour schedule, APIs, and cross-tests](docs/team_plan.md)
- [Confirmed D1-D5 decisions](docs/decisions.md)
- [Release and tiny data audit](docs/data_audit.md)
- [Contributor rules](AGENTS.md)

Use a standalone Python 3.11+ installation (not a Python bundled with FreeCAD
or another application). From this directory on Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -c "import contracts"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m platform_huy.serve_ui
```

Open http://127.0.0.1:8765/?variant=A for the static UI prototype; press Ctrl+C
to stop. Use `--port 8766` if port 8765 is occupied. The launcher avoids reverse
hostname lookup, including the Windows `UnicodeDecodeError` seen with
`python -m http.server`.

On macOS/Linux, use `.venv/bin/python` instead of `.\.venv\Scripts\python.exe`.
See [environment setup and troubleshooting](requirements/README.md) if `python`
selects FreeCAD or an existing `.venv` was created from it. Requirements install
Python packages; they do not install or replace the Python interpreter.

Place source files under `data/release_main/` and `data/tiny/`; data is gitignored and must be shared separately. Open source databases read-only. Runtime state belongs in `runs/`.

Huy owns data validation/A3 and shared execution safeguards. An Nguyen owns A2 and supplies assessed-order lists, dates, ETA, and delay evidence. Truc owns A1, all UI, and HTTP APIs.

The release dataset supports initial development. Tiny lacks promised dates and ops telemetry; it cannot validate the full workflow. A2 logic and a static UI prototype are available; the integrated agents, API server, and action executor are not implemented yet. See the [prototype limitations](platform_huy/ui_prototype/README.md).
