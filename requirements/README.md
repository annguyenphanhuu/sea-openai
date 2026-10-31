# Dependencies and environment setup

Owner: Huy; only Huy maintains dependency lists.

- Python 3.11+ is required. Use a standalone Python installation.
- `runtime.txt`: no external runtime packages are currently needed.
- `dev.txt`: runtime requirements plus the pinned pytest version.
- Root `requirements.txt`: includes `dev.txt` for the shared team setup.
- The static UI needs no npm installation, API key, or source database.

## Conda

From the repository root, create the project environment once and install the
shared requirements into that environment:

```powershell
conda create --name sea-openai python=3.11 pip --yes
conda env config vars set --name sea-openai PYTHONNOUSERSITE=1
conda run --name sea-openai python -s -m pip install -r requirements.txt
conda run --name sea-openai python -m pip check
conda run --name sea-openai python -m pytest -q
```

If Python 3.11 and its dependencies are already cached and the Conda server is
unreachable, add `--offline` to the create command. This only works with a
complete local package cache; pip requirements still need a reachable index or
cached distributions.

The environment variable prevents Python from loading packages from the shared
user site. Reactivate the environment if it was already active when setting it.
Use `conda activate sea-openai` in a Conda-enabled terminal, or keep using
`conda run` without changing shell configuration. To start the prototype:

```powershell
conda run --no-capture-output --name sea-openai python -m platform_huy.serve_ui
```

Use the environment's `python.exe` as the IDE interpreter, with
`PYTHONNOUSERSITE=1` in the IDE run environment if Conda activation is skipped.
The environment is
local to the machine and is not committed. Refresh dependencies with the pip
install command above whenever the shared requirements change.

## Windows (PowerShell)

Check which interpreter will create the environment:

```powershell
Get-Command python
python -c "import sys; print(sys.executable); print(sys.version)"
```

If it points to FreeCAD, install standalone Python 3.11+ from
https://www.python.org/downloads/ and open a new terminal. Use its full executable
path if `python` still resolves to FreeCAD:

```powershell
& 'C:\path\to\standalone\python.exe' -m venv .venv
```

For a new checkout with the correct `python` on PATH:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m platform_huy.serve_ui
```

No environment activation or PowerShell execution-policy change is needed.
If `.venv` already uses FreeCAD, preserve it and create a separate environment
named `venv` using the standalone interpreter; substitute `venv` for `.venv` in
the commands above. Both names are gitignored.

## macOS / Linux

With Python 3.11+ available as `python3`:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest -q
.venv/bin/python -m platform_huy.serve_ui
```

If the operating system does not include `venv`, install its Python venv package
using the system package manager first.

## UI startup

Open http://127.0.0.1:8765/?variant=A. Stop with Ctrl+C.
The launcher binds only to localhost and serves only `platform_huy/ui_prototype`.
Pass `--port 8766` to select another port.

Installing requirements alone cannot fix hostname decoding in Python's default
HTTP server. Use `python -m platform_huy.serve_ui` with your environment's Python;
it avoids reverse hostname lookup without changing Python or system settings.
