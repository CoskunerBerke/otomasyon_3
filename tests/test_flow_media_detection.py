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


def _menu_page(items, visible=None):
    """
    A quality menu whose entries are the labels Flow actually renders.

    Each entry is one [role=menuitem] whose text is the two visible lines joined, e.g.
    "720p Orijinal boyut". has-text() is a case-insensitive substring match, so that is
    what the fake locator does.
    """
    page = MagicMock()
    page.wait_for_selector.return_value = None
    clicked = []
    vis = [True] * len(items) if visible is None else visible

    def _item(label, is_visible):
        it = MagicMock()
        it.is_visible.return_value = is_visible
        it.inner_text.return_value = label
        it.click.side_effect = lambda timeout=None: clicked.append(label)
        return it

    def locator(sel):
        loc = MagicMock()
        want = re.search(r"has-text\('([^']+)'\)", sel)
        if want is None:
            # The diagnostics read of the menu container; inert here.
            loc.first.inner_text.side_effect = Exception("not modelled")
            loc.count.return_value = 0
            return loc
        needle = want.group(1).casefold()
        hits = [(lbl, v) for lbl, v in zip(items, vis) if needle in lbl.casefold()]
        loc.count.return_value = len(hits)
        loc.nth.side_effect = lambda i: _item(*hits[i])
        return loc

    page.locator.side_effect = locator
    return page, clicked


def test_original_size_is_chosen_from_the_quality_menu():
    """
    The entries below are the live menu of 2026-09-17, copied as it renders.

    The code looked for "Orjinal", which is a substring of none of them -- Turkish spells
    it "Orijinal". So the match failed on a menu that was perfectly recognisable, and the
    run stopped at DOWNLOAD_QUALITY_MENU_UNRECOGNISED with the video already generated
    and its Flow credit already spent (CBM-REEL-2026-0058).
    """
    page, clicked = _menu_page(["270p Hareketli GIF", "720p Orijinal boyut",
                                "1080p Yükseltilmiş", "4K Yükseltilmiş · 50 kredi"])
    _choose_original_quality(page)
    assert clicked == ["720p Orijinal boyut"]


def test_the_english_menu_is_matched_too():
    page, clicked = _menu_page(["270p Animated GIF", "720p Original size",
                                "1080p Upscaled", "4K Upscaled · 50 credits"])
    _choose_original_quality(page)
    assert clicked == ["720p Original size"]


def test_unrecognised_menu_refuses_rather_than_picking_a_paid_entry():
    """No original entry means stop -- never fall through onto an upscale that bills."""
    page, clicked = _menu_page(["1080p Yükseltilmiş", "4K Yükseltilmiş · 50 kredi"])
    with pytest.raises(RuntimeError, match="DOWNLOAD_QUALITY_MENU_UNRECOGNISED"):
        _choose_original_quality(page)
    assert clicked == []


def test_an_upscale_that_calls_itself_original_is_still_refused():
    """
    Matching on the word alone is not enough to protect the credits.

    If Flow ever labels an upscale "Orijinal boyut - yükseltilmiş", the text match hits
    it; the credit marker in the label is what stops the click.
    """
    page, clicked = _menu_page(["4K Orijinal boyut · Yükseltilmiş · 50 kredi"])
    with pytest.raises(RuntimeError, match="DOWNLOAD_QUALITY_MENU_PAID_ONLY"):
        _choose_original_quality(page)
    assert clicked == []


def test_a_panel_left_in_the_dom_does_not_swallow_the_click():
    """Angular Material keeps closed panels around; the visible entry is the real one."""
    page, clicked = _menu_page(["720p Orijinal boyut", "720p Orijinal boyut"],
                               visible=[False, True])
    _choose_original_quality(page)
    assert clicked == ["720p Orijinal boyut"]


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
