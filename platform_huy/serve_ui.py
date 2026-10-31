"""Serve the static UI prototype locally without reverse hostname lookup."""

import argparse
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from socketserver import TCPServer


class LocalHTTPServer(ThreadingHTTPServer):
    """Avoid Windows hostname decoding errors during HTTP server startup."""

    # Windows SO_REUSEADDR can let two servers bind the same port.
    allow_reuse_address = os.name != "nt"

    def server_bind(self) -> None:
        TCPServer.server_bind(self)
        self.server_name = "localhost"
        self.server_port = self.server_address[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")

    directory = Path(__file__).resolve().parent / "ui_prototype"
    if not (directory / "index.html").is_file():
        parser.error(f"UI prototype not found: {directory / 'index.html'}")

    handler = partial(SimpleHTTPRequestHandler, directory=str(directory))
    try:
        with LocalHTTPServer(("127.0.0.1", args.port), handler) as server:
            print(f"UI prototype: http://127.0.0.1:{server.server_port}/?variant=A", flush=True)
            print("Press Ctrl+C to stop.", flush=True)
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    except OSError as error:
        parser.exit(1, f"Cannot start UI server: {error}\n")


if __name__ == "__main__":
    main()
