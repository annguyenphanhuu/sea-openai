"""Serve the static order list on loopback without Windows hostname lookup."""

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
from socketserver import TCPServer
from urllib.parse import urlsplit


class PreviewServer(ThreadingHTTPServer):
    allow_reuse_address = os.name != "nt"

    def server_bind(self) -> None:
        TCPServer.server_bind(self)
        self.server_name = "localhost"
        self.server_port = self.server_address[1]


class PreviewHandler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".mjs": "text/javascript"}
    allowed_paths = frozenset({
        "/ui/", "/ui/index.html", "/ui/styles.css", "/ui/app.js",
        "/ui/data.mjs", "/sample_orders.json",
    })

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self) -> None:
        if urlsplit(self.path).path not in self.allowed_paths:
            self.send_error(404, "Not found")
            return
        super().do_GET()

    def do_HEAD(self) -> None:
        if urlsplit(self.path).path not in self.allowed_paths:
            self.send_error(404, "Not found")
            return
        super().do_HEAD()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    directory = Path(__file__).resolve().parent.parent
    handler = partial(PreviewHandler, directory=str(directory))
    with PreviewServer(("127.0.0.1", args.port), handler) as server:
        print(f"Order list: http://127.0.0.1:{server.server_port}/ui/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
