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

Huy owns data validation/A3 and shared execution safeguards. An Nguyen owns A2 and supplies assessed-order lists, dates, ETA, and delay evidence. Truc owns A1, all UI, and HTTP APIs.

The release dataset supports initial development. Tiny lacks promised dates and ops telemetry; it cannot validate the full workflow. A2 and an illustrative UI prototype are present; A3/A1, the API server, the executor, and the full pipeline remain to be implemented.
