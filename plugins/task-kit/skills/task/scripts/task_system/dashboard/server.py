"""The dashboard's local HTTP server.

One detached process per machine, bound to ``127.0.0.1`` on an OS-chosen port,
serving a JSON API and the static UI. The security posture is fixed by
construction, not configuration:

- loopback only; any ``Host`` other than ``127.0.0.1:<port>`` or
  ``localhost:<port>`` is refused (DNS rebinding), and no CORS header is ever
  emitted;
- the per-instance token travels in the URL FRAGMENT (never sent to a server,
  so never logged) and in the ``X-Task-Kit-Token`` header on every API call;
- a mutation additionally needs a same-origin ``Origin``, a JSON content type
  and a body of at most 64 KiB;
- every response is ``Cache-Control: no-store`` and carries a restrictive CSP.

Health is the one unauthenticated endpoint and reveals only the instance
nonce, the code hash, the port and the busy-job count.
"""

from __future__ import annotations

import hmac
import json
import os
import secrets
import signal
import sys
import threading
import traceback
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, unquote, urlsplit

from . import redact, snapshot
from .codehash import DASHBOARD_PACKAGE, code_hash
from .inventory import Inventory
from .state import (
    LOCK_FILE,
    LOG_FILE,
    SCHEMA,
    LockHeldError,
    ServerLock,
    ServerState,
    remove_state_if_owned,
    runtime_root,
    write_state,
)

LOOPBACK = "127.0.0.1"
TOKEN_HEADER = "X-Task-Kit-Token"
MAX_BODY_BYTES = 64 * 1024
EXIT_LOCK_HELD = 75  # EX_TEMPFAIL: another server already runs; use that one.

CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
    "img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'; "
    "object-src 'none'"
)

_STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}


def load_static(scripts_dir: Path) -> dict[str, tuple[bytes, str]]:
    """Read the UI assets into memory once.

    A plugin update can delete the directory this server started from while it
    keeps running; serving from memory means that never breaks the page.
    """
    static_dir = Path(scripts_dir).joinpath(*DASHBOARD_PACKAGE, "static")
    assets: dict[str, tuple[bytes, str]] = {}
    for path in sorted(static_dir.iterdir()):
        content_type = _STATIC_TYPES.get(path.suffix)
        if path.is_file() and content_type:
            assets[path.name] = (path.read_bytes(), content_type)
    if "index.html" not in assets:
        raise FileNotFoundError(f"dashboard UI missing: {static_dir / 'index.html'}")
    return assets


class DashboardServer:
    """Binds, records ownership, serves, and cleans up."""

    def __init__(
        self,
        *,
        data_dir: Path,
        scripts_dir: Path,
        inventory: Inventory,
        busy: Callable[[], int] = lambda: 0,
        log=None,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.scripts_dir = Path(scripts_dir)
        self.root = runtime_root(self.data_dir)
        self.inventory = inventory
        self._busy = busy
        self.log_stream = log if log is not None else sys.stderr
        self.code_hash = code_hash(self.scripts_dir)
        self.assets = load_static(self.scripts_dir)
        self.token = secrets.token_urlsafe(32)
        self.nonce = secrets.token_hex(16)
        redact.register_secret(self.token)
        self._httpd: ThreadingHTTPServer | None = None
        self._lock = ServerLock(self.root / LOCK_FILE)
        self.state: ServerState | None = None
        self._stopping = threading.Event()

    # -- lifecycle ---------------------------------------------------------

    @property
    def port(self) -> int:
        if self._httpd is None:
            raise RuntimeError("server is not bound")
        return self._httpd.server_address[1]

    def busy_count(self) -> int:
        return int(self._busy())

    def start(self) -> ServerState:
        """Take the lock, bind port 0, and publish ownership. Raises LockHeldError."""
        import psutil

        self.root.mkdir(parents=True, exist_ok=True)
        self._lock.acquire()
        try:
            httpd = ThreadingHTTPServer((LOOPBACK, 0), _Handler)
            httpd.daemon_threads = True
            httpd.dashboard = self  # type: ignore[attr-defined]
            self._httpd = httpd
            self.state = ServerState(
                schema=SCHEMA,
                pid=os.getpid(),
                pid_create_time=psutil.Process(os.getpid()).create_time(),
                nonce=self.nonce,
                port=httpd.server_address[1],
                token=self.token,
                code_hash=self.code_hash,
                started_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                log_path=str(self.root / LOG_FILE),
            )
            write_state(self.root, self.state)
        except BaseException:
            self._lock.release()
            raise
        self.log(f"serving on {LOOPBACK}:{self.port} (code {self.code_hash[:12]})")
        return self.state

    def serve_forever(self) -> None:
        assert self._httpd is not None, "start() first"
        try:
            self._httpd.serve_forever(poll_interval=0.2)
        finally:
            self.close()

    def request_shutdown(self) -> None:
        """Stop serving; safe to call from a handler thread."""
        if self._httpd is not None and not self._stopping.is_set():
            self._stopping.set()
            threading.Thread(target=self._httpd.shutdown, daemon=True).start()

    def close(self) -> None:
        if self._httpd is not None:
            self._httpd.server_close()
            self._httpd = None
        remove_state_if_owned(self.root, self.nonce)
        self._lock.release()
        redact.clear_secrets()

    def log(self, message: str) -> None:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.log_stream.write(f"{stamp} {redact.redact(message)}\n")
        self.log_stream.flush()

    # -- facts the handler serves -----------------------------------------

    def health(self) -> dict:
        return {
            "schema": SCHEMA,
            "instance": self.nonce,
            "code_hash": self.code_hash,
            "port": self.port,
            "busy": self.busy_count(),
        }

    def server_info(self) -> dict:
        return {"instance": self.nonce, "code_hash": self.code_hash[:12]}

    def allowed_hosts(self) -> set[str]:
        return {f"{LOOPBACK}:{self.port}", f"localhost:{self.port}"}

    def allowed_origins(self) -> set[str]:
        return {f"http://{LOOPBACK}:{self.port}", f"http://localhost:{self.port}"}


class _Handler(BaseHTTPRequestHandler):
    server_version = "task-kit-dashboard"
    sys_version = ""

    def version_string(self) -> str:
        return self.server_version

    @property
    def app(self) -> DashboardServer:
        return self.server.dashboard  # type: ignore[attr-defined]

    # -- logging -----------------------------------------------------------

    def log_message(self, format: str, *args) -> None:  # noqa: A002 -- stdlib name
        # Method, path and status only: never headers, never the query string.
        path = urlsplit(self.path).path
        self.app.log(f"{self.command} {path} -> {args[1] if len(args) > 1 else '?'}")

    def log_error(self, format: str, *args) -> None:  # noqa: A002
        self.app.log(f"error {format % args}")

    # -- verbs -------------------------------------------------------------

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_PUT(self) -> None:
        self._dispatch("PUT")

    def do_PATCH(self) -> None:
        self._dispatch("PATCH")

    def do_DELETE(self) -> None:
        self._dispatch("DELETE")

    def do_OPTIONS(self) -> None:
        # No CORS: a preflight gets the same refusal as any unsupported verb.
        self._dispatch("OPTIONS")

    def do_HEAD(self) -> None:
        self._dispatch("HEAD")

    # -- responses ---------------------------------------------------------

    def _headers(self, content_type: str, length: int) -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self._headers(content_type, len(body))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        self._send(status, body, "application/json")

    def _error(self, status: int, code: str, message: str) -> None:
        self._json(status, {"error": {"code": code, "message": message}})

    # -- security gates ----------------------------------------------------

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").strip().lower()
        return host in self.app.allowed_hosts()

    def _token_ok(self) -> bool:
        supplied = self.headers.get(TOKEN_HEADER) or ""
        return hmac.compare_digest(supplied.encode("utf-8"), self.app.token.encode("utf-8"))

    def _read_json_body(self) -> dict | None:
        """Validate a mutation's origin, type and size; return the JSON body.

        Sends the error response itself and returns None when any gate fails.
        """
        origin = self.headers.get("Origin")
        if origin is None or origin.lower() not in self.app.allowed_origins():
            self._error(403, "bad_origin", "A mutation needs a same-origin Origin header.")
            return None
        content_type = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if content_type != "application/json":
            self._error(415, "bad_content_type", "A mutation body must be application/json.")
            return None
        length_header = self.headers.get("Content-Length")
        if length_header is None or not length_header.isdigit():
            self._error(411, "length_required", "A mutation needs a Content-Length.")
            return None
        length = int(length_header)
        if length > MAX_BODY_BYTES:
            self._error(413, "body_too_large", f"A mutation body is limited to {MAX_BODY_BYTES} bytes.")
            return None
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, ValueError):
            self._error(400, "bad_json", "The body is not valid JSON.")
            return None
        if not isinstance(body, dict):
            self._error(400, "bad_json", "The body must be a JSON object.")
            return None
        return body

    # -- routing -----------------------------------------------------------

    def _dispatch(self, method: str) -> None:
        try:
            if not self._host_ok():
                self._error(403, "forbidden_host", "Only 127.0.0.1 and localhost are served.")
                return
            parts = urlsplit(self.path)
            segments = [unquote(s) for s in parts.path.split("/")[1:]]
            query = parse_qs(parts.query)
            if method in ("GET", "HEAD") and not (segments and segments[0] == "api"):
                self._static(segments)
                return
            if segments[:2] != ["api", "v1"]:
                self._error(404, "not_found", "No such endpoint.")
                return
            route = segments[2:]
            if route == ["health"]:
                if method not in ("GET", "HEAD"):
                    self._error(405, "method_not_allowed", "Use GET.")
                    return
                self._json(200, self.app.health())
                return
            if not self._token_ok():
                self._error(401, "unauthorized", "Missing or wrong token; reopen the dashboard with `task-kit`.")
                return
            self._api(method, route, query)
        except ConnectionError as exc:
            # The browser closed the connection mid-response: nothing to answer.
            self.app.log(f"client went away: {type(exc).__name__}")
        except Exception as exc:  # noqa: BLE001 -- a handler must answer, then log loudly
            self.app.log("unhandled error:\n" + traceback.format_exc())
            self._error(500, "internal", f"{type(exc).__name__}: {exc}")

    def _static(self, segments: list[str]) -> None:
        if segments in ([""], ["index.html"]):
            name = "index.html"
        elif len(segments) == 2 and segments[0] == "static":
            name = segments[1]
        else:
            self._error(404, "not_found", "No such page.")
            return
        asset = self.app.assets.get(name)
        if asset is None:
            self._error(404, "not_found", "No such asset.")
            return
        self._send(200, asset[0], asset[1])

    def _api(self, method: str, route: list[str], query: dict) -> None:
        if route == ["dashboard"]:
            if method not in ("GET", "HEAD"):
                self._error(405, "method_not_allowed", "Use GET.")
                return
            force = query.get("refresh", [""])[0] == "1"
            inventory = self.app.inventory.snapshot(force=force)
            payload = snapshot.dashboard_payload(
                inventory,
                project=query.get("project", [""])[0] or None,
                query=query.get("q", [""])[0],
                needs_only=query.get("needs", [""])[0] in ("1", "true"),
                server=self.app.server_info(),
            )
            self._json(200, payload)
            return
        if route[:1] == ["items"] and len(route) in (4, 5):
            if method not in ("GET", "HEAD"):
                self._error(405, "method_not_allowed", "Use GET.")
                return
            project, task_id, item_id = route[1], route[2], route[3]
            task = self.app.inventory.snapshot().find_task(project, task_id)
            if task is None:
                self._error(404, "unknown_task", "No such task in any configured project.")
                return
            detail = snapshot.item_detail(task, item_id)
            if detail is None:
                self._error(404, "unknown_item", "No such item in that task.")
                return
            if len(route) == 5:
                if route[4] != "handoff":
                    self._error(404, "not_found", "No such endpoint.")
                    return
                self._json(200, detail["handoff"])
                return
            self._json(200, detail)
            return
        if route == ["shutdown"]:
            if method != "POST":
                self._error(405, "method_not_allowed", "Use POST.")
                return
            body = self._read_json_body()
            if body is None:
                return
            busy = self.app.busy_count()
            if busy and not body.get("force"):
                self._error(409, "busy", f"{busy} job(s) are running; stop is refused without force.")
                return
            self._json(200, {"ok": True})
            self.app.request_shutdown()
            return
        self._error(404, "not_found", "No such endpoint.")


def run(data_dir: Path, scripts_dir: Path, *, log=None) -> int:
    """Run a dashboard server in the foreground until it is asked to stop."""
    server = DashboardServer(
        data_dir=data_dir,
        scripts_dir=scripts_dir,
        inventory=Inventory(),
        log=log,
    )
    try:
        server.start()
    except LockHeldError as exc:
        server.log(str(exc))
        print(f"task-kit dashboard: {exc}", file=sys.stderr)
        return EXIT_LOCK_HELD

    # Read every task folder once now, so the first page load does not wait for it.
    threading.Thread(target=server.inventory.snapshot, name="inventory-warmup", daemon=True).start()

    def _stop(_signum, _frame) -> None:
        server.request_shutdown()

    for name in ("SIGTERM", "SIGINT", "SIGBREAK"):
        number = getattr(signal, name, None)
        if number is not None:
            signal.signal(number, _stop)
    server.serve_forever()
    server.log("stopped")
    return 0
