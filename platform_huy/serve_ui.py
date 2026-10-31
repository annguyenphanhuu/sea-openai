"""Serve the A3 prototype or integrated A3/A2/A1 local operator demo."""

import argparse
from datetime import datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie, CookieError
import hmac
import json
import os
from pathlib import Path
from socketserver import TCPServer
import sqlite3
import secrets
from urllib.parse import parse_qs, urlsplit

from .a3_demo import A3Demo, project_root, release_dir


class LocalHTTPServer(ThreadingHTTPServer):
    """Avoid Windows hostname decoding errors during HTTP server startup."""

    # Windows SO_REUSEADDR can let two servers bind the same port.
    allow_reuse_address = os.name != "nt"

    def server_bind(self) -> None:
        TCPServer.server_bind(self)
        self.server_name = "localhost"
        self.server_port = self.server_address[1]

    def server_close(self) -> None:
        try:
            super().server_close()
        finally:
            coordinator = getattr(self, 'coordinator', None)
            if coordinator is not None:
                coordinator.close()


def create_server(*, core_path: Path, state_path: Path,
                  start_at: datetime | None = None, port: int = 8765,
                  host: str = "127.0.0.1", integrated: bool = False,
                  ops_path: Path | None = None, selector=None) -> LocalHTTPServer:
    """Create an actual HTTP server; tests and CLI share the same request path."""
    from .presenter_auth import PresenterAuth
    presenter = PresenterAuth(host) if integrated else None
    if integrated:
        from .demo_flow import DemoFlow
        demo = DemoFlow(core_path, state_path, start_at=start_at, ops_path=ops_path, selector=selector)
    else:
        demo = A3Demo(core_path, state_path, start_at)
    directory = Path(__file__).resolve().parent / "ui_prototype"
    orders_directory = directory.parent.parent / 'logistics_an_nguyen' / 'ui'
    orders_token = secrets.token_urlsafe(32)

    class Handler(SimpleHTTPRequestHandler):
        extensions_map = {**SimpleHTTPRequestHandler.extensions_map, '.mjs': 'text/javascript'}

        def _orders_cookie_authorized(self) -> bool:
            try:
                cookie = SimpleCookie(self.headers.get('Cookie', ''))
                token = cookie.get('orders_presenter')
                return token is not None and hmac.compare_digest(token.value, orders_token)
            except (CookieError, TypeError):
                return False

        def _json(self, code: int, result: dict) -> None:
            payload = json.dumps(result, default=lambda value: value.isoformat(),
                                 ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            if presenter is not None and presenter.required and presenter.authorized(self.headers):
                # Nguyen's unchanged API client sends same-origin credentials.
                # This process-local capability permits only the orders read API.
                secure = '; Secure' if host not in ('127.0.0.1', 'localhost', '::1') else ''
                self.send_header('Set-Cookie', f'orders_presenter={orders_token}; '
                                 f'Path=/api/orders; HttpOnly; SameSite=Strict{secure}')
            self.end_headers()
            self.wfile.write(payload)

        def _api(self, action: str, payload: dict | None = None) -> None:
            if action == 'reset' and (presenter is None or not presenter.required
                                      or not presenter.authorized(self.headers)):
                self._json(401, {'error': 'Presenter key required'})
                return
            if (presenter is not None and not presenter.authorized(self.headers)
                    and not (action == 'orders' and self._orders_cookie_authorized())):
                self._json(401, {'error': 'Presenter key required'})
                return
            try:
                result = demo.request(action, payload, reject_overlapping_next=True) if integrated else demo.request(action)
                self._json(200, result)
            except (OSError, ValueError, TypeError, KeyError, sqlite3.Error):
                # Failure responses cannot authorize even a stale browser client.
                self._json(503, {"error": "A3 demo unavailable; proactive drafting is blocked",
                                 "guard_alive": False, "proactive_allowed": False,
                                 "actions": []})
            except Exception as error:
                # Domain exceptions expose only stable codes, never source data.
                from care_truc.runtime_types import CareError
                from .dto import PlatformError
                if isinstance(error, CareError):
                    self._json(error.status, {'error': error.code})
                elif isinstance(error, PlatformError):
                    self._json(409, {'error': error.code})
                else:
                    self._json(503, {'error': 'Demo operation unavailable'})

        def _body(self) -> dict | None:
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 <= length <= 16384:
                    self._json(413, {'error': 'Request body too large'})
                    return None
                value = json.loads(self.rfile.read(length).decode('utf-8')) if length else {}
                if not isinstance(value, dict):
                    raise ValueError('Object required')
                return value
            except (ValueError, UnicodeError):
                self._json(400, {'error': 'Invalid JSON object'})
                return None

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            query = {key: values[-1] for key, values in parse_qs(urlsplit(self.path).query).items()}
            if path == "/api/a3/status" or (integrated and path == '/api/demo/state'):
                self._api("status", query)
            elif integrated and path == '/api/records':
                self._api('records', query)
            elif integrated and path == '/api/orders':
                self._api('orders', query)
            elif path.startswith("/api/"):
                self._json(404, {"error": "Unknown API route", "proactive_allowed": False})
            elif integrated and path in ('/orders', '/orders/', '/orders/index.html'):
                if path == '/orders' or query.get('source') != 'api':
                    self.send_response(302)
                    self.send_header('Location', '/orders/?source=api')
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                    return
                self.directory = str(orders_directory)
                self.path = '/index.html'
                super().do_GET()
            elif integrated and path.startswith('/orders/'):
                name = path.removeprefix('/orders/')
                if name not in ('styles.css', 'app.js', 'data.mjs'):
                    self.send_error(404, 'Not found')
                    return
                self.directory = str(orders_directory)
                self.path = '/' + name
                super().do_GET()
            else:
                if integrated and path in ('/', '/overview', '/contacts', '/chat', '/money'):
                    self.path = '/live.html'
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
            if integrated:
                routes.update({'/api/chat/open': 'chat-open', '/api/chat/say': 'chat-say',
                               '/api/orders/verify': 'verify-order', '/api/reset': 'reset'})
            action = routes.get(urlsplit(self.path).path)
            if action is None:
                self._json(404, {"error": "Unknown API route", "proactive_allowed": False})
                return
            payload = self._body()
            if payload is not None:
                self._api(action, payload)

    try:
        server = LocalHTTPServer((host, port), partial(Handler, directory=str(directory)))
    except BaseException:
        if integrated:
            demo.close()
        raise
    if integrated:
        server.coordinator = demo
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument('--integrated', action='store_true', help='Run the real A3/A2/A1 web-chat demo')
    parser.add_argument('--llm', action='store_true', help='Enable OpenAI approved-phrase selection in A1')
    parser.add_argument('--ops-path', type=Path)
    parser.add_argument("--core-path", type=Path,
                        default=release_dir() / "core_14d.sqlite")
    parser.add_argument("--state-path", type=Path,
                        default=None)
    parser.add_argument("--start-at", type=datetime.fromisoformat,
                        help="Aware replay timestamp; integrated demo starts at 2026-10-24T14:00+07:00")
    args = parser.parse_args()
    selector = None
    if args.llm:
        if not args.integrated:
            parser.error('--llm requires --integrated')
        env_path = project_root() / '.env'
        if env_path.is_file():
            for line in env_path.read_text(encoding='utf-8-sig').splitlines():
                key, separator, value = line.partition('=')
                if separator and key.strip() in ('OPENAI_API_KEY', 'OPENAI_MODEL'):
                    os.environ.setdefault(key.strip(), value.strip().strip('\"\''))
        from care_truc.openai_selector import selector_from_env
        selector = selector_from_env()
        if selector is None:
            parser.error('OPENAI_API_KEY is required for --llm')
    if args.state_path is None:
        folder = 'integrated-demo' if args.integrated else 'a3-demo'
        args.state_path = project_root() / 'runs' / folder / 'state.sqlite'
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")

    directory = Path(__file__).resolve().parent / "ui_prototype"
    if not (directory / "index.html").is_file():
        parser.error(f"UI prototype not found: {directory / 'index.html'}")

    try:
        with create_server(core_path=args.core_path, state_path=args.state_path,
                           start_at=args.start_at, port=args.port, host=args.host,
                           integrated=args.integrated, ops_path=args.ops_path, selector=selector) as server:
            label = 'Integrated A3/A2/A1 demo' if args.integrated else 'A3 demo'
            print(f"{label}: http://{args.host}:{server.server_port}/", flush=True)
            print(f"Runtime: {args.state_path.resolve()}; NEXT advances exactly 30 minutes.", flush=True)
            print("Press Ctrl+C to stop.", flush=True)
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    except (OSError, ValueError, sqlite3.Error) as error:
        parser.exit(1, f"Cannot start UI server: {error}\n")


if __name__ == "__main__":
    main()
