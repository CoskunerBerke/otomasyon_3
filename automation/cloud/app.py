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
    handle_worker_heartbeat,
    handle_get_next_command,
    handle_complete_command,
    handle_sync_cloud_state,
    handle_storage_self_test
)


class CloudApp:
    """Central Cloud Application Server."""

    def __init__(self, config: Optional[CloudConfig] = None):
        self.config = config or CloudConfig()
        self.db = Database(self.config.database_url, is_production=self.config.is_production)
        self.bot = TelegramBotClient(self.config.telegram_bot_token)
        self.approval_service = ApprovalService(self.config, self.db, self.bot)
        self.storage = get_media_storage(self.config)
        self.instagram_worker = InstagramCloudWorker(self.config, self.db, self.storage)
        self.scheduler = CloudScheduler(self.config, self.db, self.approval_service, self.instagram_worker)
        self._scheduler_running = False
        self._scheduler_thread: Optional[threading.Thread] = None

    def route_request(self, method: str, path: str, headers: Dict[str, str], body_json: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        """Unified internal router for HTTP / ASGI / WSGI."""
        clean_path = path.rstrip("/")

        if method == "GET" and (clean_path == "/health" or clean_path == ""):
            return 200, get_health_status(self.config, self.db)

        if method == "POST" and clean_path == "/telegram/webhook":
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

    def _send_json(self, status_code: int, data: Dict[str, Any]) -> None:
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        headers_dict = {k: v for k, v in self.headers.items()}
        code, resp = self.app.route_request("GET", self.path, headers_dict, {})
        self._send_json(code, resp)

    def do_POST(self):
        headers_dict = {k: v for k, v in self.headers.items()}
        content_len = int(self.headers.get("Content-Length", 0))
        body_data = {}
        if content_len > 0:
            raw_body = self.rfile.read(content_len)
            try:
                body_data = json.loads(raw_body.decode("utf-8"))
            except Exception:
                body_data = {}
        code, resp = self.app.route_request("POST", self.path, headers_dict, body_data)
        self._send_json(code, resp)

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
