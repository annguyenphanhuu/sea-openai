# sea-openai

Late-delivery hackathon scaffold for Huy, An Nguyen, and Truc.

- [Team ownership, seven-hour schedule, APIs, and cross-tests](docs/team_plan.md)
- [Confirmed D1-D5 decisions](docs/decisions.md)
- [Release and tiny data audit](docs/data_audit.md)
- [Contributor rules](AGENTS.md)

Use Python 3.11+ from this directory:

```powershell
python -m pip install -r requirements/dev.txt
python -c "import contracts"
pytest -q
```

Place source files under `data/release_main/` and `data/tiny/`; data is gitignored and must be shared separately. Open source databases read-only. Runtime state belongs in `runs/`.

The release dataset supports initial development. Tiny lacks promised dates and ops telemetry; it cannot validate the full workflow. Agents, the API server, UI, and the action executor are not implemented yet.
