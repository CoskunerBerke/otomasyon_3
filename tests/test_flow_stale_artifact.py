"""
Regression: a failed Flow generation must never yield a segment.

2026-09-03, CBM-REEL-2026-0032: segments 1 and 2 came back byte-identical. Flow's
generation had failed ("Bu üretme işlemi için kredi kullanmadınız"), the previous
artifact stayed on screen with its download button enabled, and the decision engine
reached DOWNLOAD_MEDIA through its MEDIA_GENERATING branch -- with no new artifact.
Nothing downstream compared the file to the one before it.
"""
import pytest

from automation.flow.page import FlowPage
from automation.flow.generator import _segment_digest
from automation.flow.state_machine import GenerationSession, FlowDecisionAction
from automation.flow.selectors import GenerationTimeoutError


class _Snapshot:
    """Minimal stand-in exposing only what the download branch reads."""
    def __init__(self, fingerprint):
        self.new_artifact_fingerprint = fingerprint


def _make_page(fingerprint, downloads):
    """A FlowPage whose UI always offers an enabled download button."""
    page = FlowPage.__new__(FlowPage)

    class _Observer:
        def take_snapshot(self):
            return _Snapshot(fingerprint)

    class _Engine:
        class _State:
            value = "media_ready"
        state = _State()

        def decide_next_action(self, snapshot, session=None):
            return FlowDecisionAction.RECOVER_DOWNLOAD_UI

    class _Downloader:
        def trigger_and_save_download(self, **kwargs):
            downloads.append(kwargs.get("target_filename"))
            return "downloaded.mp4"

    page.observer = _Observer()
    page.decision_engine = _Engine()
    page.downloader = _Downloader()
    page.page = type("P", (), {"url": "https://labs.google/fx"})()
    page.check_auth_and_security = lambda: None
    page.check_credit_warnings = lambda: None
    page.recover_and_open_video_detail = lambda: None
    page.resolve_enabled_download_button = lambda timeout_ms=1000: object()
    page.capture_error_snapshot = lambda name: None
    return page


def _session():
    s = GenerationSession(reel_id="CBM-REEL-2026-0032-S2", flow_project_url="u", prompt_hash="h")
    s.baseline_artifact_fingerprints = {"artifact-from-segment-1"}
    s.submit_attempted = True
    return s


def test_stale_baseline_artifact_is_not_downloaded():
    """The artifact left on screen by segment 1 must not become segment 2."""
    downloads = []
    page = _make_page("artifact-from-segment-1", downloads)
    with pytest.raises(GenerationTimeoutError):
        page.wait_for_completion_and_download(
            target_filename="segment_02.mp4", timeout_minutes=0.05, session=_session()
        )
    assert downloads == [], "baseline artifact indirilmemeliydi"


def test_missing_fingerprint_is_not_downloaded():
    """No new artifact at all is also not a result."""
    downloads = []
    page = _make_page(None, downloads)
    with pytest.raises(GenerationTimeoutError):
        page.wait_for_completion_and_download(
            target_filename="segment_02.mp4", timeout_minutes=0.05, session=_session()
        )
    assert downloads == []


def test_genuinely_new_artifact_still_downloads():
    """The normal case must keep working."""
    downloads = []
    page = _make_page("artifact-from-segment-2", downloads)
    result = page.wait_for_completion_and_download(
        target_filename="segment_02.mp4", timeout_minutes=0.05, session=_session()
    )
    assert result == "downloaded.mp4"
    assert downloads == ["segment_02.mp4"]


def test_segment_digest_distinguishes_content(tmp_path):
    a = tmp_path / "segment_01.mp4"
    b = tmp_path / "segment_02.mp4"
    c = tmp_path / "segment_03.mp4"
    a.write_bytes(b"first video payload")
    b.write_bytes(b"first video payload")   # the duplicate case
    c.write_bytes(b"a genuinely different video")
    assert _segment_digest(a) == _segment_digest(b)
    assert _segment_digest(a) != _segment_digest(c)
