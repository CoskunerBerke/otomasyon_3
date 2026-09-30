"""
Regression tests for the cloud control plane HTTP layer (automation/cloud/app.py).

Runs the real CloudHTTPRequestHandler on a loopback port with a SQLite database and local
media storage. No Telegram token is configured, so nothing leaves the machine.
"""
import http.client
import json
import socket
import tempfile
import threading
import time
from http.server import HTTPServer

import pytest

from automation.cloud.app import CloudApp, CloudHTTPRequestHandler
from automation.cloud.config import CloudConfig
from automation.cloud.local_worker_api import handle_media_upload
from automation.cloud.database import Database

WORKER_KEY = "test-worker-key-123"
WEBHOOK_SECRET = "test-webhook-secret"


@pytest.fixture
def server(tmp_path, monkeypatch):
    # Streamed uploads go to tempfile.gettempdir(); keep them inside tmp_path.
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.chdir(tmp_path)

    cfg = CloudConfig(tmp_path)
    cfg.app_env = "development"
    cfg.database_url = f"sqlite:///{tmp_path / 'cloud.db'}"
    cfg.telegram_bot_token = ""
    cfg.telegram_webhook_secret = WEBHOOK_SECRET
    cfg.local_worker_api_key = WORKER_KEY
    cfg.media_storage_backend = "local"
    cfg.enable_weekly_scheduler = False
    cfg.enable_instagram_worker = False

    handler = type("Handler", (CloudHTTPRequestHandler,), {"app": CloudApp(cfg)})
    httpd = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd, handler, tmp_path
    httpd.shutdown()
    httpd.server_close()


def _request(httpd, method, path, body=b"", headers=None, timeout=10):
    conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=timeout)
    try:
        conn.request(method, path, body=body, headers=headers or {})
        resp = conn.getresponse()
        return resp.status, json.loads(resp.read() or b"{}")
    finally:
        conn.close()


def _worker_headers():
    return {"X-Worker-Api-Key": WORKER_KEY, "Content-Type": "application/json"}


def test_webhook_message_with_null_text_is_answered(server):
    httpd, _, _ = server
    headers = {"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET, "Content-Type": "application/json"}
    code, resp = _request(httpd, "POST", "/telegram/webhook",
                          json.dumps({"message": {"text": None, "chat": {"id": 1}}}).encode(), headers)
    assert code == 200
    assert resp["action"] == "IGNORED_UPDATE"

    code, resp = _request(httpd, "POST", "/telegram/webhook",
                          json.dumps({"message": {"text": "/start", "from": {"id": 1}}}).encode(), headers)
    assert (code, resp["action"]) == (200, "START_ACK")


@pytest.mark.parametrize("path", ["/worker/heartbeat", "/worker/commands/CMD-1/complete",
                                  "/worker/media/diagnostic-cleanup", "/telegram/webhook"])
def test_non_object_json_body_is_rejected_not_crashing(server, path):
    httpd, _, _ = server
    headers = dict(_worker_headers(), **{"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET})
    code, resp = _request(httpd, "POST", path, b"[1, 2, 3]", headers)
    assert code == 400
    assert resp["error"] == "INVALID_JSON_BODY"


def test_invalid_content_length_is_rejected(server):
    httpd, _, _ = server
    headers = dict(_worker_headers(), **{"Content-Length": "abc"})
    code, resp = _request(httpd, "POST", "/worker/heartbeat", b"", headers)
    assert code == 400
    assert resp["error"] == "INVALID_CONTENT_LENGTH"


def test_unexpected_handler_error_returns_generic_500(server, monkeypatch):
    httpd, handler, _ = server

    def boom(*_args, **_kwargs):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(handler.app, "route_request", boom)
    code, resp = _request(httpd, "GET", "/health")
    assert code == 500
    assert resp == {"ok": False, "error": "INTERNAL_ERROR"}


def test_unauthenticated_multipart_upload_writes_nothing_to_disk(server):
    httpd, _, tmp_path = server
    boundary = "TESTBOUNDARY"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"x.mp4\"\r\n"
            f"Content-Type: video/mp4\r\n\r\n").encode() + b"\0" * 50_000 + f"\r\n--{boundary}--\r\n".encode()
    code, resp = _request(httpd, "POST", "/worker/media/upload", body,
                          {"Content-Type": f"multipart/form-data; boundary={boundary}"})
    assert code == 401
    assert resp["error"] == "UNAUTHORIZED_WORKER_KEY"
    stream_dir = tmp_path / "cloud_media_stream"
    assert not stream_dir.exists() or not any(stream_dir.iterdir())


def test_media_upload_handler_deletes_streamed_file_on_auth_failure(tmp_path):
    cfg = CloudConfig(tmp_path)
    cfg.local_worker_api_key = WORKER_KEY
    db = Database(f"sqlite:///{tmp_path / 'test.db'}")
    streamed = tmp_path / "stream_abc.mp4"
    streamed.write_bytes(b"x" * 1000)

    code, _ = handle_media_upload({"X-Worker-Api-Key": "wrong"}, {"__stream_file_path__": str(streamed)}, cfg, db)
    assert code == 401
    assert not streamed.exists()


def test_stalled_client_does_not_block_the_server(server, monkeypatch):
    # The server is single-threaded: without a socket timeout one idle connection
    # would block every later request, /health included.
    assert CloudHTTPRequestHandler.timeout is not None
    assert 0 < CloudHTTPRequestHandler.timeout <= 120

    httpd, handler, _ = server
    monkeypatch.setattr(handler, "timeout", 1)  # keep the test fast

    stalled = socket.create_connection(("127.0.0.1", httpd.server_address[1]))
    try:
        stalled.sendall(b"POST /worker/heartbeat HTTP/1.1\r\n")  # never finishes the request
        time.sleep(0.2)
        start = time.monotonic()
        code, resp = _request(httpd, "GET", "/health", timeout=10)
        assert code == 200
        assert time.monotonic() - start < 5
    finally:
        stalled.close()
