"""
A control that is still moving is not a broken control.

Five separate failures in one week, on four different surfaces, were the same mistake:
Playwright refuses to click an element that is not yet "visible, enabled and stable", the
call site allowed a couple of seconds for that to become true, and a page mid-animation
was therefore reported as a page that could not be driven.

    2026-08-22  TikTok's file input -- stopped a week at its twelfth Reel
    2026-08-22  TikTok's Planla button -- video uploaded, caption written, slot set
    2026-08-22  YouTube's file input -- the same shape, not yet unlucky
    2026-08-27  Instagram's İleri -- stopped a live phase at its third Reel
    2026-08-27  Flow's download button -- the Reel was generated, the credit spent,
                and the file never came down

The costs differ but the reading does not: absence of readiness treated as absence of the
control. This file pins the timeouts that were raised, so a later edit cannot quietly
return them to a value that only works on a page that happens to be still.

The numbers are not magic. What matters is that they are long enough for an animation and
short enough that a genuinely missing control still fails the run rather than hanging it.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPO = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "module,constant,floor,what",
    [
        pytest.param(
            "automation.flow.downloader", "DOWNLOAD_CLICK_TIMEOUT_MS", 10000,
            "Flow's download button, after the video is already generated",
            id="flow-download",
        ),
        pytest.param(
            "automation.publishing.instagram_web_observer", "CLICK_TIMEOUT_MS", 5000,
            "Instagram's composer navigation",
            id="instagram-click",
        ),
        pytest.param(
            "automation.publishing.tiktok_ui_observer", "SCHEDULE_CLICK_TIMEOUT_MS", 5000,
            "TikTok's final Schedule button",
            id="tiktok-schedule-click",
        ),
        pytest.param(
            "automation.publishing.tiktok_ui_observer", "SCHEDULE_BUTTON_SETTLE_MS", 8000,
            "TikTok's Schedule button, scrolling to it while the page reflows",
            id="tiktok-schedule-settle",
        ),
        pytest.param(
            "automation.publishing.tiktok_ui_observer", "FILE_INPUT_WAIT_SECONDS", 15,
            "TikTok's upload area, built after the page loads",
            id="tiktok-file-input",
        ),
        pytest.param(
            "automation.publishing.youtube_studio_ui_observer", "FILE_INPUT_WAIT_SECONDS", 15,
            "YouTube's upload dialog, building its file input",
            id="youtube-file-input",
        ),
    ],
)
def test_a_moving_control_is_given_time_to_settle(module, constant, floor, what):
    import importlib

    value = getattr(importlib.import_module(module), constant)
    assert value >= floor, (
        f"{constant} is {value}, too short for {what}. An animation would read as a "
        f"missing control -- which is what this whole file is about."
    )


def test_the_download_click_no_longer_guards_a_case_already_ruled_out():
    """
    The old 2000ms was justified as avoiding a 30s wait on a DISABLED button. But the
    disabled case is rejected by an explicit pre-check above the click, so the short
    timeout could only ever catch an enabled button that had not finished moving.
    """
    source = (REPO / "automation" / "flow" / "downloader.py").read_text(encoding="utf-8")

    pre_check = source.index("DOWNLOAD_BUTTON_DISABLED")
    click = source.index("download_button_locator.click(")
    assert pre_check < click, "the disabled pre-check must still run before the click"
    assert "click(timeout=2000)" not in source


def test_a_genuinely_missing_control_still_fails():
    """
    Patience must not become an infinite wait: a control that never appears has to end
    the run with an error, not hang it. Every timeout here is bounded.
    """
    import importlib

    bounded = [
        ("automation.flow.downloader", "DOWNLOAD_CLICK_TIMEOUT_MS", 60000),
        ("automation.publishing.instagram_web_observer", "CLICK_TIMEOUT_MS", 60000),
        ("automation.publishing.instagram_web_observer", "CLICK_RETRY_SECONDS", 120),
        ("automation.publishing.tiktok_ui_observer", "SCHEDULE_CLICK_TIMEOUT_MS", 60000),
        ("automation.publishing.tiktok_ui_observer", "FILE_INPUT_WAIT_SECONDS", 120),
        ("automation.publishing.youtube_studio_ui_observer", "FILE_INPUT_WAIT_SECONDS", 120),
    ]
    for module, constant, ceiling in bounded:
        value = getattr(importlib.import_module(module), constant)
        assert 0 < value <= ceiling, f"{constant} must stay bounded, got {value}"
