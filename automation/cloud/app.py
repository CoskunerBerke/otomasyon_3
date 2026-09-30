"""
Cloud Control Plane Application Server (FastAPI / WSGI / HTTP compatible).
Serves Telegram webhooks, worker command queues, health check, and background scheduler.
Binds dynamically to Railway $PORT on 0.0.0.0.
"""
import os
import sys
import json
import time
import logging
import threading
import argparse
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any, Tuple, Optional

logger = logging.getLogger("ReelsAIFactory.CloudApp")

from .config import CloudConfig
from .database import Database
from .telegram_bot import TelegramBotClient
from .approval_service import ApprovalService
from .media_storage import get_media_storage
from .instagram_worker import InstagramCloudWorker
from .scheduler import CloudScheduler
from .health import get_health_status
from .telegram_webhook import handle_webhook_request
from .local_worker_api import (
    _authenticate_worker,
    handle_worker_heartbeat,
    handle_get_next_command,
    handle_complete_command,
    handle_sync_cloud_state,
    handle_storage_self_test,
    handle_media_upload,
    handle_diagnostic_cleanup,
    stream_multipart_request
)


class CloudApp:
    """Central Cloud Application Server."""

    def __init__(self, config: Optional[CloudConfig] = None):
        self.config = config or CloudConfig()
        self.db = Database(self.config.database_url, is_production=self.config.is_production)
        self.telegram_bot = TelegramBotClient(self.config.telegram_bot_token)
        self.approval_service = ApprovalService(self.config, self.db, self.telegram_bot)
        self.storage = get_media_storage(self.config)
        self.instagram_worker = InstagramCloudWorker(self.config, self.db, self.storage)
        self.scheduler = CloudScheduler(self.config, self.db, self.approval_service, self.instagram_worker)

        self._scheduler_running = False
        self._scheduler_thread: Optional[threading.Thread] = None

    def route_request(
        self,
        method: str,
        path: str,
        headers: Dict[str, str],
        body_json: Dict[str, Any]
    ) -> Tuple[int, Dict[str, Any]]:
        """Main routing dispatch for HTTP requests."""
        clean_path = path.split("?")[0].rstrip("/")
        if not clean_path:
            clean_path = "/"

        if method == "GET" and clean_path in ("/", "/health"):
            return 200, get_health_status(self.config, self.db)

        if method == "POST" and clean_path == "/telegram/webhook":
            # ENABLE_TELEGRAM_WEBHOOK=false must really switch the endpoint off.
            if not self.config.enable_telegram_webhook:
                return 503, {"ok": False, "error": "TELEGRAM_WEBHOOK_DISABLED"}
            return handle_webhook_request(headers, body_json, self.config, self.approval_service)

        if method == "POST" and clean_path == "/worker/heartbeat":
            return handle_worker_heartbeat(headers, body_json, self.config, self.db)

        if method == "GET" and clean_path == "/worker/commands/next":
            worker_id = headers.get("X-Worker-Id", "local_win_worker")
            return handle_get_next_command(headers, worker_id, self.config, self.db)

        if method == "POST" and clean_path.startswith("/worker/commands/") and clean_path.endswith("/complete"):
            parts = clean_path.split("/")
            if len(parts) >= 4:
                command_id = parts[3]
                return handle_complete_command(headers, command_id, body_json, self.config, self.db)

        if method == "GET" and clean_path == "/worker/state/sync":
            return handle_sync_cloud_state(headers, self.config, self.db)

        if method == "POST" and clean_path == "/worker/storage/self-test":
            return handle_storage_self_test(headers, self.config, self.storage)

        if method == "POST" and clean_path == "/worker/media/upload":
            return handle_media_upload(headers, body_json, self.config, self.db, self.storage)

        if method == "POST" and clean_path == "/worker/media/diagnostic-cleanup":
            return handle_diagnostic_cleanup(headers, body_json, self.config, self.db, self.storage)

        return 404, {"ok": False, "error": "NOT_FOUND"}

    def _scheduler_loop(self) -> None:
        """Background loop executing scheduler iterations."""
        logger.info("[SCHEDULER] Cloud background scheduler started.")
        while self._scheduler_running:
            try:
                if self.config.enable_weekly_scheduler or self.config.enable_instagram_worker:
                    self.scheduler.run_iteration()
            except Exception as e:
                logger.error(f"[SCHEDULER] Error in scheduler loop: {e}")
            time.sleep(30)

    def start_scheduler(self) -> None:
        """Starts background scheduler thread if enabled."""
        if not self._scheduler_running:
            self._scheduler_running = True
            self._scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
            self._scheduler_thread.start()

    def stop_scheduler(self) -> None:
        """Stops background scheduler thread gracefully."""
        self._scheduler_running = False
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            self._scheduler_thread.join(timeout=2)


class CloudHTTPRequestHandler(BaseHTTPRequestHandler):
    """Standard HTTP request handler delegating to CloudApp router."""
    app: CloudApp = None  # Injected on server startup

    # The server handles one request at a time, so a client that opens a connection and
    # then stalls would otherwise block every other request (including /health) forever.
    # This bounds each socket read/write, not the total transfer time of an upload.
    timeout = 60

    def _send_json(self, status_code: int, data: Dict[str, Any]) -> None:
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _dispatch(self, method: str, headers_dict: Dict[str, str], body: Dict[str, Any]) -> None:
        """
        Routes the request and always answers. An unexpected exception becomes a generic
        500 (details go to the server log only) instead of a dropped connection, which
        Telegram would keep retrying for the same update.
        """
        try:
            code, resp = self.app.route_request(method, self.path, headers_dict, body)
        except Exception:
            logger.exception(f"[HTTP] Unhandled error while serving {method} {self.path.split('?')[0]}")
            code, resp = 500, {"ok": False, "error": "INTERNAL_ERROR"}
        self._send_json(code, resp)

    def do_GET(self):
        headers_dict = {k: v for k, v in self.headers.items()}
        self._dispatch("GET", headers_dict, {})

    def do_POST(self):
        headers_dict = {k: v for k, v in self.headers.items()}
        try:
            content_len = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            content_len = -1
        if content_len < 0:
            self._send_json(400, {"ok": False, "error": "INVALID_CONTENT_LENGTH"})
            return
        content_type = self.headers.get("Content-Type", "")

        clean_path = self.path.split("?")[0].rstrip("/")
        if not clean_path:
            clean_path = "/"

        # Bounded streaming multipart upload for /worker/media/upload
        if clean_path == "/worker/media/upload" and "multipart/form-data" in content_type:
            # Authenticate before a single byte of the body is written to disk; otherwise
            # anyone could leave up to 100 MB of temp files behind per request.
            auth_ok, auth_err = _authenticate_worker(headers_dict, self.app.config)
            if not auth_ok:
                self._send_json(401, {"ok": False, "error": auth_err})
                return

            fields, temp_path, filename, file_size, calculated_sha, err = stream_multipart_request(
                self.rfile, content_len, content_type
            )
            if err:
                code = 413 if err == "MEDIA_TOO_LARGE" else 400
                self._send_json(code, {"ok": False, "error": err})
                return

            body_data = {
                "__stream_file_path__": str(temp_path) if temp_path else "",
                "__fields__": fields,
                "__filename__": filename or "video.mp4",
                "__file_size__": file_size,
                "__calculated_sha256__": calculated_sha
            }
            try:
                self._dispatch("POST", headers_dict, body_data)
            finally:
                # The handler deletes the file on every path it knows about; this also
                # covers an exception inside it.
                if temp_path and Path(temp_path).exists():
                    try:
                        Path(temp_path).unlink()
                    except OSError:
                        pass
            return

        if content_len > 10 * 1024 * 1024:
            self._send_json(413, {"ok": False, "error": "PAYLOAD_TOO_LARGE"})
            return

        body_data = {}
        if content_len > 0:
            raw_body = self.rfile.read(content_len)
            try:
                body_data = json.loads(raw_body.decode("utf-8"))
            except Exception:
                body_data = {"__raw_body__": raw_body}

        # Every route expects a JSON object; a list, string or number would otherwise
        # reach payload.get(...) and crash the handler.
        if not isinstance(body_data, dict):
            self._send_json(400, {"ok": False, "error": "INVALID_JSON_BODY"})
            return

        self._dispatch("POST", headers_dict, body_data)

    def log_message(self, format, *args):
        # Suppress noisy standard request logs
        return


def run_production_server(port: Optional[int] = None, host: str = "0.0.0.0") -> None:
    """Runs production HTTP server binding to host and Railway PORT."""
    config = CloudConfig()
    target_port = port or config.port

    app = CloudApp(config)
    if config.enable_weekly_scheduler or config.enable_instagram_worker:
        app.start_scheduler()

    CloudHTTPRequestHandler.app = app
    server_address = (host, target_port)
    httpd = HTTPServer(server_address, CloudHTTPRequestHandler)

    print(f"[REELS AI CLOUD] Server listening on {host}:{target_port} (Env: {config.app_env.upper()})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[REELS AI CLOUD] Shutting down...")
    finally:
        app.stop_scheduler()
        httpd.server_close()


def create_app() -> CloudApp:
    """Factory helper for CloudApp."""
    return CloudApp()


def main():
    parser = argparse.ArgumentParser(description="Reels AI Factory Cloud Control Plane")
    parser.add_argument("--port", type=int, default=None, help="Port to listen on (default from PORT env or 8000)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host address (default 0.0.0.0)")
    args = parser.parse_args()

    run_production_server(port=args.port, host=args.host)


if __name__ == "__main__":
    main()
