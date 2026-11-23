"""
Local web interface (standard library only - no Flask needed).

    python3 run_app.py web            ->  http://127.0.0.1:5000

The server is a thin JSON API over the same engine / workflows used by the
terminal front-ends. Security model (it can move files, so it is strict):
  * listens on 127.0.0.1 only;
  * Host header must match (blocks DNS-rebinding);
  * every /api request needs a per-run secret token (blocks CSRF from other sites);
  * request bodies are size-limited, responses carry no-store / CSP headers;
  * all paths go through the same validation (protected system folders refused).
"""

import hmac
import json
import logging
import secrets
import threading
import webbrowser
from collections import Counter
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import __version__, ui
from .analytics import AnalyticsEngine
from .config import ConfigError
from .core_engine import FileOrganizerEngine
from .duplicates import wasted_bytes
from .models import STATUS_SUCCESS
from .persistence import PersistenceManager
from .strategies import get_strategy
from .validator import validate_directory
from .web_page import render_index
from .workflows import perform_organize, perform_quarantine, perform_undo, plan_duplicates

logger = logging.getLogger(__name__)

MAX_BODY_BYTES = 64 * 1024
MAX_PREVIEW_ROWS = 200
MAX_DUPLICATE_GROUPS = 50
HOST = "127.0.0.1"


class ApiError(Exception):
    """A problem the caller should see (HTTP status + message)."""

    def __init__(self, message: str, status: int = HTTPStatus.BAD_REQUEST):
        super().__init__(message)
        self.status = int(status)


class WebApp:
    """Application logic behind the HTTP routes (kept separate so it is easy to test)."""

    def __init__(self, persistence: PersistenceManager):
        self.persistence = persistence
        self.token = secrets.token_urlsafe(24)
        self.lock = threading.Lock()  # one file-changing operation at a time

    # ----------------------------------------------------------------- helpers
    def _engine(self, strategy: str = "type") -> FileOrganizerEngine:
        try:
            chosen = get_strategy(strategy)
        except ValueError as exc:
            raise ApiError(str(exc)) from exc
        return FileOrganizerEngine(strategy=chosen, exclude_paths=self.persistence.state_files())

    @staticmethod
    def _target(data: Dict[str, Any]) -> str:
        try:
            return str(validate_directory(str(data.get("path", ""))))
        except ValueError as exc:
            raise ApiError(str(exc)) from exc

    @staticmethod
    def _flag(data: Dict[str, Any], key: str) -> bool:
        return data.get(key) is True

    # --------------------------------------------------------------- endpoints
    def preview(self, data: Dict[str, Any]) -> Dict[str, Any]:
        target = self._target(data)
        recursive = self._flag(data, "recursive")
        engine = self._engine(str(data.get("strategy", "type")))
        simulation = engine.execute_organization(target, engine.iter_scan(target, recursive), dry_run=True)

        records = simulation["moved_files"]
        by_category = Counter(r["category"] for r in records)
        rows = [
            {
                "filename": r["filename"],
                "category": r["category"],
                "size_bytes": r["size_bytes"],
                "destination": str(Path(r["target_path"]).relative_to(target)),
                "renamed": Path(r["target_path"]).name != r["filename"],
            }
            for r in records[:MAX_PREVIEW_ROWS]
        ]
        return {
            "target": target,
            "total_files": len(records),
            "total_bytes": sum(r["size_bytes"] for r in records),
            "by_category": dict(by_category),
            "rows": rows,
            "truncated": len(records) > MAX_PREVIEW_ROWS,
            "pending_recovery": engine.has_pending_journal(target),
        }

    def organize(self, data: Dict[str, Any]) -> Dict[str, Any]:
        target = self._target(data)
        engine = self._engine(str(data.get("strategy", "type")))
        with self.lock:
            summary = perform_organize(
                engine, self.persistence, target,
                atomic=self._flag(data, "atomic"), recursive=self._flag(data, "recursive"),
            )
        return {
            "operation_id": summary["operation_id"],
            "total": summary["total_files_processed"],
            "successful": summary["successful_moves"],
            "failed": summary["failed_moves"],
            "aborted": summary["aborted"],
            "errors": summary["errors"][:10],
        }

    def undo(self, data: Dict[str, Any]) -> Dict[str, Any]:
        operation = self.persistence.find_operation(str(data.get("operation_id", "")))
        if operation is None:
            raise ApiError("Operation not found.", HTTPStatus.NOT_FOUND)
        if operation.get("rolled_back"):
            raise ApiError("This operation was already rolled back.")
        with self.lock:
            restored, failed, errors = perform_undo(
                FileOrganizerEngine(exclude_paths=self.persistence.state_files()), self.persistence, operation
            )
        return {"restored": restored, "failed": failed, "errors": errors[:10]}

    def recover(self, data: Dict[str, Any]) -> Dict[str, Any]:
        target = self._target(data)
        with self.lock:
            restored, failed, errors = self._engine().recover_pending(target)
        return {"restored": restored, "failed": failed, "errors": errors[:10]}

    def operations(self) -> Dict[str, Any]:
        items: List[Dict[str, Any]] = []
        for op in reversed(self.persistence.load_history()[-20:]):
            records = op.get("moved_files", [])
            outstanding = sum(1 for r in records if r.get("status") == STATUS_SUCCESS)
            items.append({
                "operation_id": op.get("operation_id"),
                "timestamp": op.get("timestamp"),
                "target_directory": op.get("target_directory"),
                "strategy": op.get("strategy", "type"),
                "files": op.get("successful_moves", outstanding),
                "failed": op.get("failed_moves", 0),
                "rolled_back": bool(op.get("rolled_back")),
                "can_undo": outstanding > 0 and not op.get("rolled_back"),
            })
        return {"operations": items}

    def stats(self) -> Dict[str, Any]:
        return AnalyticsEngine(self.persistence.load_history()).compute_metrics()

    def report(self) -> str:
        return AnalyticsEngine(self.persistence.load_history()).build_markdown_report()

    def duplicates_scan(self, data: Dict[str, Any]) -> Dict[str, Any]:
        target = self._target(data)
        groups, plan = plan_duplicates(
            target, recursive=self._flag(data, "recursive"), exclude=self.persistence.state_files()
        )
        return {
            "target": target,
            "total_groups": len(groups),
            "total_extra_copies": len(plan),
            "wasted_bytes": wasted_bytes(groups),
            "groups": [
                {"keep": str(g[0]), "extras": [str(p) for p in g[1:]]} for g in groups[:MAX_DUPLICATE_GROUPS]
            ],
        }

    def duplicates_quarantine(self, data: Dict[str, Any]) -> Dict[str, Any]:
        target = self._target(data)
        _groups, plan = plan_duplicates(
            target, recursive=self._flag(data, "recursive"), exclude=self.persistence.state_files()
        )
        if not plan:
            return {"operation_id": None, "total": 0, "successful": 0, "failed": 0, "aborted": False, "errors": []}
        with self.lock:
            summary = perform_quarantine(self._engine(), self.persistence, target, plan)
        return {
            "operation_id": summary["operation_id"],
            "total": summary["total_files_processed"],
            "successful": summary["successful_moves"],
            "failed": summary["failed_moves"],
            "aborted": summary["aborted"],
            "errors": summary["errors"][:10],
        }


def make_handler(app: WebApp, allowed_hosts: List[str]) -> type:
    """Builds the request-handler class bound to ``app``."""

    post_routes: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
        "/api/preview": app.preview,
        "/api/organize": app.organize,
        "/api/undo": app.undo,
        "/api/recover": app.recover,
        "/api/duplicates/scan": app.duplicates_scan,
        "/api/duplicates/quarantine": app.duplicates_quarantine,
    }
    get_routes: Dict[str, Callable[[], Dict[str, Any]]] = {
        "/api/operations": app.operations,
        "/api/stats": app.stats,
    }

    class Handler(BaseHTTPRequestHandler):
        server_version = f"FileOrganizer/{__version__}"

        def log_message(self, fmt: str, *args: Any) -> None:  # route access log to logging, not stderr
            logger.info("%s - %s", self.address_string(), fmt % args)

        # ------------------------------------------------------------ plumbing
        def _send(self, status: int, body: bytes, content_type: str, extra: Optional[Dict[str, str]] = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src data:",
            )
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, payload: Dict[str, Any]) -> None:
            self._send(status, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8")

        def _guard(self, api: bool) -> bool:
            """Host + token checks. Sends the error response and returns False when rejected."""
            if self.headers.get("Host", "") not in allowed_hosts:
                self._json(HTTPStatus.FORBIDDEN, {"error": "Forbidden host."})
                return False
            if api and not hmac.compare_digest(self.headers.get("X-Organizer-Token", ""), app.token):
                self._json(HTTPStatus.FORBIDDEN, {"error": "Missing or invalid session token. Reload the page."})
                return False
            return True

        def _read_json(self) -> Dict[str, Any]:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                raise ApiError("Invalid Content-Length.")
            if length > MAX_BODY_BYTES:
                raise ApiError("Request body too large.", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                data = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ApiError(f"Invalid JSON body: {exc}") from exc
            if not isinstance(data, dict):
                raise ApiError("JSON body must be an object.")
            return data

        def _run(self, func: Callable[[], Any]) -> None:
            try:
                result = func()
            except ApiError as exc:
                self._json(exc.status, {"error": str(exc)})
            except (ValueError, ConfigError) as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            except OSError as exc:
                logger.error("File system error handling %s: %s", self.path, exc)
                self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"File system problem: {exc}"})
            except Exception:  # noqa: BLE001 - last-resort boundary: log the traceback, never leak it to the client
                logger.exception("Unhandled error handling %s", self.path)
                self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Unexpected server error (see organizer.log)."})
            else:
                if isinstance(result, tuple):  # (bytes, content_type, extra headers)
                    self._send(HTTPStatus.OK, *result)
                else:
                    self._json(HTTPStatus.OK, result)

        # -------------------------------------------------------------- routes
        def do_GET(self) -> None:  # noqa: N802 - http.server naming
            path = self.path.split("?", 1)[0]
            if path == "/":
                if self._guard(api=False):
                    self._send(HTTPStatus.OK, render_index(app.token).encode("utf-8"), "text/html; charset=utf-8")
                return
            if path == "/api/report":
                if self._guard(api=True):
                    self._run(lambda: (
                        app.report().encode("utf-8"), "text/markdown; charset=utf-8",
                        {"Content-Disposition": 'attachment; filename="organizer_report.md"'},
                    ))
                return
            if path in get_routes:
                if self._guard(api=True):
                    self._run(get_routes[path])
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "Not found."})

        def do_POST(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path not in post_routes:
                self._json(HTTPStatus.NOT_FOUND, {"error": "Not found."})
                return
            if self._guard(api=True):
                self._run(lambda: post_routes[path](self._read_json()))

    return Handler


def create_server(persistence: PersistenceManager, port: int = 5000) -> Tuple[ThreadingHTTPServer, WebApp]:
    """Creates (but does not start) the server. ``port=0`` picks a free port (used by tests)."""
    app = WebApp(persistence)
    # Bind first so we know the real port, then tell the handler which Host headers are legitimate.
    allowed: List[str] = []
    handler = make_handler(app, allowed)
    server = ThreadingHTTPServer((HOST, port), handler)
    server.daemon_threads = True
    real_port = server.server_address[1]
    allowed.extend([f"127.0.0.1:{real_port}", f"localhost:{real_port}"])
    return server, app


def serve(persistence: PersistenceManager, port: int = 5000, open_browser: bool = True) -> int:
    """Runs the web app until Ctrl+C. Tries the next ports if ``port`` is busy."""
    server: Optional[ThreadingHTTPServer] = None
    for candidate in range(port, port + 10):
        try:
            server, _app = create_server(persistence, candidate)
            break
        except OSError as exc:
            logger.warning("Port %d unavailable: %s", candidate, exc)
    if server is None:
        ui.error(f"[Error] Could not open a port between {port} and {port + 9}. Close the other program or use --port.")
        return 1

    url = f"http://127.0.0.1:{server.server_address[1]}"
    ui.success(f"File Organizer web app is running at {url}")
    ui.info("Press Ctrl+C in this window to stop it.")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        ui.plain("\nStopping web app. Goodbye.")
    finally:
        server.server_close()
    return 0
