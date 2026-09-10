"""
Regression: seeing generated media, and downloading it without spending credits.

2026-09-10. Flow finished a video, showed it on the canvas, and the run sat in WAIT until
it timed out. Two causes, both from the same redesign:

  * generated media is an <img> thumbnail inside flow-video-tile now. The <video>
    elements and /edit/ links the observer looked for do not exist, so every poll saw an
    empty set and concluded nothing new had appeared.
  * the download button opens a quality menu instead of downloading. Clicking it and
    waiting for a download event waits forever -- and one menu entry, 4K upscaled, costs
    50 credits.
"""
import re
from unittest.mock import MagicMock

import pytest

from automation.flow.ui_observer import FlowUIObserver
from automation.flow.downloader import _choose_original_quality


def _img(src, visible=True):
    m = MagicMock()
    m.is_visible.return_value = visible
    m.get_attribute.side_effect = lambda a: src if a == "src" else None
    return m


def _observer(imgs):
    page = MagicMock()

    def locator(sel):
        loc = MagicMock()
        loc.all.return_value = imgs if "flow-content.google" in sel else []
        return loc

    page.locator.side_effect = locator
    return FlowUIObserver(page)


REAL = "https://flow-content.google/image/af8ef86b-860b-4ffa-925f-481c3b2f6f27?Expires=1789041934&KeyName=la"


def test_thumbnail_is_recognised_as_an_artifact():
    fps = _observer([_img(REAL)]).get_visible_artifact_fingerprints()
    assert fps == {"media:af8ef86b-860b-4ffa-925f-481c3b2f6f27"}


def test_fingerprint_survives_the_expiring_url():
    """
    The signed src carries an Expires= that changes between polls.

    Keying on the whole URL would make the same video look new on every single poll,
    which is how a stale artifact gets downloaded as if it were this segment's.
    """
    later = REAL.replace("Expires=1789041934", "Expires=1789099999")
    a = _observer([_img(REAL)]).get_visible_artifact_fingerprints()
    b = _observer([_img(later)]).get_visible_artifact_fingerprints()
    assert a == b


def test_hidden_thumbnails_are_ignored():
    assert _observer([_img(REAL, visible=False)]).get_visible_artifact_fingerprints() == set()


def _menu_page(items):
    page = MagicMock()
    page.wait_for_selector.return_value = None
    clicked = []

    def locator(sel):
        loc = MagicMock()
        label = re.search(r"has-text\('([^']+)'\)", sel)
        want = label.group(1) if label else None
        hit = want is not None and any(want in it for it in items)
        loc.first.count.return_value = 1 if hit else 0
        loc.first.is_visible.return_value = hit
        loc.first.click.side_effect = lambda timeout=None: clicked.append(want)
        return loc

    page.locator.side_effect = locator
    return page, clicked


def test_original_size_is_chosen_from_the_quality_menu():
    page, clicked = _menu_page(["270p Hareketli GIF", "720p Orjinal boyut",
                                "1080p Yükseltilmiş", "4K Yükseltilmiş · 50 kredi"])
    _choose_original_quality(page)
    assert clicked == ["Orjinal"]


def test_unrecognised_menu_refuses_rather_than_picking_a_paid_entry():
    """No original entry means stop -- never fall through onto an upscale that bills."""
    page, clicked = _menu_page(["1080p Yükseltilmiş", "4K Yükseltilmiş · 50 kredi"])
    with pytest.raises(RuntimeError, match="DOWNLOAD_QUALITY_MENU_UNRECOGNISED"):
        _choose_original_quality(page)
    assert clicked == []


def test_no_menu_means_the_click_already_downloaded():
    page = MagicMock()
    page.wait_for_selector.side_effect = Exception("no menu")
    _choose_original_quality(page)  # returns quietly


def test_detail_view_opens_by_clicking_the_tile():
    """
    The download control only exists inside the detail view, and the tile is what opens it.

    recover_and_open_video_detail() tried an /edit/ link, a <video> element and a
    play_circle button -- all removed in the redesign -- so it returned False on every
    attempt while the finished video sat on the canvas, and the download loop ran out its
    twenty minutes. Verified live: before the click the download button is not visible,
    after it aria-label="Medyayı indir" is.
    """
    from automation.flow.page import FlowPage

    clicked = []
    page = MagicMock()

    def locator(sel):
        loc = MagicMock()
        hit = sel == "flow-video-tile"
        loc.first.count.return_value = 1 if hit else 0
        loc.first.is_visible.return_value = hit
        loc.first.click.side_effect = lambda: clicked.append(sel)
        return loc

    page.locator.side_effect = locator
    fp = FlowPage.__new__(FlowPage)
    fp.page = page

    assert fp.recover_and_open_video_detail() is True
    assert clicked == ["flow-video-tile"]
