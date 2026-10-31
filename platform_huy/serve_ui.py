"""Serve the A3 demo and illustrative order UI; loopback by default."""

import argparse
from datetime import datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from socketserver import TCPServer
import sqlite3
from urllib.parse import urlsplit

from .a3_demo import A3Demo, project_root, release_dir


class LocalHTTPServer(ThreadingHTTPServer):
    """Avoid Windows hostname decoding errors during HTTP server startup."""

    # Windows SO_REUSEADDR can let two servers bind the same port.
    allow_reuse_address = os.name != "nt"

    def server_bind(self) -> None:
        TCPServer.server_bind(self)
        self.server_name = "localhost"
        self.server_port = self.server_address[1]


def create_server(*, core_path: Path, state_path: Path,
                  start_at: datetime | None = None, port: int = 8765,
                  host: str = "127.0.0.1") -> LocalHTTPServer:
    """Create an actual HTTP server; tests and CLI share the same request path."""
    demo = A3Demo(core_path, state_path, start_at)
    directory = Path(__file__).resolve().parent / "ui_prototype"

    class Handler(SimpleHTTPRequestHandler):
        def _json(self, code: int, result: dict) -> None:
            payload = json.dumps(result, default=lambda value: value.isoformat(),
                                 ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def _api(self, action: str) -> None:
            try:
                self._json(200, demo.request(action))
            except (OSError, ValueError, TypeError, KeyError, sqlite3.Error):
                # Failure responses cannot authorize even a stale browser client.
                self._json(503, {"error": "A3 demo unavailable; proactive drafting is blocked",
                                 "guard_alive": False, "proactive_allowed": False,
                                 "actions": []})

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path == "/api/a3/status":
                self._api("status")
            elif path.startswith("/api/"):
                self._json(404, {"error": "Unknown API route", "proactive_allowed": False})
            else:
                super().do_GET()

        def do_POST(self) -> None:
            origin = self.headers.get("Origin")
            host_header = self.headers.get("Host", "")
            # The Space proxy terminates HTTPS before forwarding to this server.
            if origin is not None and origin not in (
                "http://" + host_header, "https://" + host_header
            ):
                self._json(403, {"error": "Local origin required", "proactive_allowed": False})
                return
            routes = {"/api/a3/kill": "kill", "/api/a3/revive": "revive",
                      "/api/next": "next", "/api/a3/proactive-check": "proactive-check"}
            action = routes.get(urlsplit(self.path).path)
            if action is None:
                self._json(404, {"error": "Unknown API route", "proactive_allowed": False})
                return
            self._api(action)

    return LocalHTTPServer((host, port), partial(Handler, directory=str(directory)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--core-path", type=Path,
                        default=release_dir() / "core_14d.sqlite")
    parser.add_argument("--state-path", type=Path,
                        default=project_root() / "runs/a3-demo/state.sqlite")
    parser.add_argument("--start-at", type=datetime.fromisoformat,
                        help="Aware simulation timestamp; defaults to source sim_clock on first launch")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")

    directory = Path(__file__).resolve().parent / "ui_prototype"
    if not (directory / "index.html").is_file():
        parser.error(f"UI prototype not found: {directory / 'index.html'}")

    try:
        with create_server(core_path=args.core_path, state_path=args.state_path,
                           start_at=args.start_at, port=args.port, host=args.host) as server:
            print(f"A3 demo: http://{args.host}:{server.server_port}/?variant=A", flush=True)
            print(f"Runtime: {args.state_path.resolve()}; NEXT advances exactly 30 minutes.", flush=True)
            print("Press Ctrl+C to stop.", flush=True)
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    except (OSError, ValueError, sqlite3.Error) as error:
        parser.exit(1, f"Cannot start UI server: {error}\n")


if __name__ == "__main__":
    main()
