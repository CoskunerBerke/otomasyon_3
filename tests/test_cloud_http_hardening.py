"""
Regression tests for the cloud control plane HTTP layer (automation/cloud/app.py).

Runs the real CloudHTTPRequestHandler on a loopback port with a SQLite database and local
media storage. No Telegram token is configured, so nothing leaves the machine.
"""
import hashlib
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


def _multipart_upload_body(boundary, fields, video):
    parts = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode()
        for name, value in fields.items()
    ]
    parts.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"reel.mp4\"\r\n"
        f"Content-Type: video/mp4\r\n\r\n".encode() + video + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts)


def test_authenticated_multipart_upload_still_works_and_leaves_no_temp_file(server):
    httpd, _, tmp_path = server
    video = b"\x00\x00\x00\x18ftypmp42 fictional demo bytes" * 100
    sha = hashlib.sha256(video).hexdigest()
    boundary = "TESTBOUNDARY"
    body = _multipart_upload_body(boundary, {
        "week_id": "2099-W01", "reel_id": "REEL-2099-0001", "media_sha256": sha,
    }, video)
    code, resp = _request(httpd, "POST", "/worker/media/upload", body, {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "X-Worker-Api-Key": WORKER_KEY,
    })
    assert code == 200, resp
    assert resp["status"] == "MEDIA_READY"
    assert resp["media_sha256"] == sha
    stream_dir = tmp_path / "cloud_media_stream"
    assert not any(stream_dir.iterdir())


@pytest.mark.parametrize("configured_key, sent_headers, expected_error", [
    (WORKER_KEY, {}, "UNAUTHORIZED_WORKER_KEY"),
    (WORKER_KEY, {"X-Worker-Api-Key": "wrong"}, "UNAUTHORIZED_WORKER_KEY"),
    ("", {}, "WORKER_API_DISABLED"),
])
def test_json_body_cannot_make_the_server_delete_a_file(server, configured_key, sent_headers,
                                                         expected_error):
    # A client-written JSON body used to reach the "delete the streamed temp file" cleanup
    # with any path it liked, so an anonymous request could delete files the server can write.
    httpd, handler, tmp_path = server
    handler.app.config.local_worker_api_key = configured_key
    victim = tmp_path / "victim_important.db"
    victim.write_bytes(b"precious")

    code, resp = _request(httpd, "POST", "/worker/media/upload",
                          json.dumps({"__stream_file_path__": str(victim)}).encode(),
                          {"Content-Type": "application/json", **sent_headers})
    assert code == 401
    assert resp["error"] == expected_error
    assert victim.read_bytes() == b"precious"


def test_key_holder_cannot_upload_or_delete_an_arbitrary_local_file(server):
    # Even with a valid key, forged stream metadata must not read a local file into
    # media storage (and then delete it).
    httpd, _, tmp_path = server
    secret = tmp_path / "secret_config.txt"
    secret.write_bytes(b"not a video")
    sha = hashlib.sha256(secret.read_bytes()).hexdigest()
    forged = {
        "__stream_file_path__": str(secret),
        "__filename__": "x.mp4",
        "__file_size__": secret.stat().st_size,
        "__calculated_sha256__": sha,
        "__fields__": {"week_id": "2099-W01", "reel_id": "REEL-2099-0001", "media_sha256": sha},
        "week_id": "2099-W01", "reel_id": "REEL-2099-0001", "media_sha256": sha,
    }
    code, resp = _request(httpd, "POST", "/worker/media/upload", json.dumps(forged).encode(),
                          {"Content-Type": "application/json", "X-Worker-Api-Key": WORKER_KEY})
    assert code == 400
    assert resp["error"] == "MEDIA_EMPTY"
    assert secret.read_bytes() == b"not a video"
    storage_dir = tmp_path / "workspace" / "cloud_media_storage"
    assert not storage_dir.exists() or not any(p.is_file() for p in storage_dir.rglob("*"))


def test_media_upload_handler_never_touches_a_payload_path_on_auth_failure(tmp_path):
    cfg = CloudConfig(tmp_path)
    cfg.local_worker_api_key = WORKER_KEY
    db = Database(f"sqlite:///{tmp_path / 'test.db'}")
    victim = tmp_path / "victim.db"
    victim.write_bytes(b"x" * 1000)

    code, _ = handle_media_upload({"X-Worker-Api-Key": "wrong"}, {"__stream_file_path__": str(victim)}, cfg, db)
    assert code == 401
    assert victim.exists()


def test_media_upload_handler_rejects_stream_path_outside_stream_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "tmp"))
    (tmp_path / "tmp").mkdir()
    cfg = CloudConfig(tmp_path)
    cfg.local_worker_api_key = WORKER_KEY
    db = Database(f"sqlite:///{tmp_path / 'test.db'}")
    outside = tmp_path / "stream_0123456789ab.mp4"
    outside.write_bytes(b"x" * 1000)
    traversal = tmp_path / "tmp" / "cloud_media_stream" / ".." / ".." / outside.name

    for candidate in (outside, traversal):
        payload = {"__stream_file_path__": str(candidate), "__fields__": {}, "__file_size__": 1000}
        code, resp = handle_media_upload({"X-Worker-Api-Key": WORKER_KEY}, payload, cfg, db)
        assert code == 400
        assert resp["error"] == "INVALID_STREAM_PATH"
        assert outside.exists()


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


@pytest.mark.parametrize("placeholder", ["change-me", "reels_ai_local_worker_key_dev"])
def test_template_worker_key_keeps_worker_api_closed(tmp_path, placeholder):
    from automation.cloud.local_worker_api import handle_worker_heartbeat

    cfg = CloudConfig(tmp_path)
    cfg.local_worker_api_key = placeholder
    db = Database(f"sqlite:///{tmp_path / 'test.db'}")
    assert cfg.is_worker_api_enabled is False
    code, resp = handle_worker_heartbeat({"X-Worker-Api-Key": placeholder}, {}, cfg, db)
    assert code == 401
    assert resp["error"] == "WORKER_API_DISABLED"
    assert db.get_latest_heartbeat() is None


def test_disabled_telegram_webhook_is_closed(server):
    httpd, handler, _ = server
    handler.app.config.enable_telegram_webhook = False
    headers = {"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET, "Content-Type": "application/json"}
    body = json.dumps({"callback_query": {"id": "1", "from": {"id": 1}, "data": "weekly_approve:APPR-1"}}).encode()
    code, resp = _request(httpd, "POST", "/telegram/webhook", body, headers)
    assert code == 503
    assert resp["error"] == "TELEGRAM_WEBHOOK_DISABLED"

    code, _ = _request(httpd, "GET", "/health")
    assert code == 200


def _post_without_sending_the_body(httpd, path, headers, declared_length=5 * 1024 * 1024):
    """Declares a large body, sends only a few bytes of it and waits for the answer.
    A server that reads the body before checking the headers never answers in time."""
    sock = socket.create_connection(("127.0.0.1", httpd.server_address[1]), timeout=5)
    resp = http.client.HTTPResponse(sock)
    try:
        lines = [f"POST {path} HTTP/1.1", "Host: 127.0.0.1", "Content-Type: application/json",
                 f"Content-Length: {declared_length}"]
        lines += [f"{name}: {value}" for name, value in headers.items()]
        sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode() + b'{"worker_id": ')
        resp.begin()
        return resp.status, json.loads(resp.read() or b"{}")
    finally:
        resp.close()  # the response holds its own reference to the socket
        sock.close()


@pytest.mark.parametrize("path, headers, config_changes, expected", [
    ("/worker/heartbeat", {}, {}, (401, "UNAUTHORIZED_WORKER_KEY")),
    ("/worker/heartbeat", {"X-Worker-Api-Key": "wrong"}, {}, (401, "UNAUTHORIZED_WORKER_KEY")),
    ("/worker/commands/CMD-1/complete", {}, {}, (401, "UNAUTHORIZED_WORKER_KEY")),
    ("/worker/media/diagnostic-cleanup", {}, {}, (401, "UNAUTHORIZED_WORKER_KEY")),
    ("/worker/media/upload", {}, {}, (401, "UNAUTHORIZED_WORKER_KEY")),
    ("/worker/heartbeat", {"X-Worker-Api-Key": "change-me"},
     {"local_worker_api_key": "change-me"}, (401, "WORKER_API_DISABLED")),
    ("/telegram/webhook", {}, {}, (403, "FORBIDDEN_INVALID_WEBHOOK_SECRET")),
    ("/telegram/webhook", {"X-Telegram-Bot-Api-Secret-Token": "wrong"}, {},
     (403, "FORBIDDEN_INVALID_WEBHOOK_SECRET")),
    ("/telegram/webhook", {}, {"app_env": "production", "telegram_webhook_secret": ""},
     (403, "TELEGRAM_WEBHOOK_SECRET_MISSING")),
    ("/telegram/webhook", {"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET},
     {"enable_telegram_webhook": False}, (503, "TELEGRAM_WEBHOOK_DISABLED")),
    ("/not-a-route", {}, {}, (404, "NOT_FOUND")),
])
def test_rejected_post_is_answered_before_its_body_is_read(server, path, headers, config_changes,
                                                           expected):
    # Before, the server read up to 10 MB of body before any route checked a credential.
    httpd, handler, _ = server
    for name, value in config_changes.items():
        setattr(handler.app.config, name, value)

    code, resp = _post_without_sending_the_body(httpd, path, headers)
    assert (code, resp["error"]) == expected

    code, _ = _request(httpd, "GET", "/health")
    assert code == 200


def test_authenticated_json_post_still_reads_the_body(server):
    httpd, handler, _ = server
    body = json.dumps({"worker_id": "demo_worker", "version": "9.9.9"}).encode()
    code, resp = _request(httpd, "POST", "/worker/heartbeat", body, _worker_headers())
    assert code == 200
    assert resp["status"] == "HEARTBEAT_ACKNOWLEDGED"
    heartbeat = handler.app.db.get_latest_heartbeat()
    assert heartbeat.worker_id == "demo_worker"
    assert heartbeat.version == "9.9.9"
