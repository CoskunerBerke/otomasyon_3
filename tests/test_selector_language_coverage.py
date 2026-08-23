"""
Every UI action must be reachable on a Studio that is not in Turkish.

This system was built against three Turkish-language accounts, so selectors naturally
grew Turkish wording. That is fine for the two channels it runs today and fatal for the
third one, or for anyone else's: a customer's YouTube Studio, TikTok Studio and Instagram
are whatever language their account is in, and a selector with only Turkish text has
nothing to match there.

The rule this file pins is deliberately loose about HOW a list stays reachable. A list
qualifies if it resolves structurally -- by id, data-e2e, class or attribute, none of
which translate -- or if it carries a non-Turkish wording alongside the Turkish one.
Most lists here already did both; two TikTok modal lists did neither and were the whole
remaining gap on 2026-08-22.

The blocklists get a stricter rule of their own. FORBIDDEN_IMMEDIATE_PUBLISH_LABELS and
its Instagram twin are what stand between a scheduled week and fourteen videos published
at once, and they are matched against button text. A blocklist that only knows the
Turkish label would wave the English button straight through, so those must name both.
"""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPO = Path(__file__).resolve().parents[1]
SELECTOR_FILES = (
    "youtube_studio_selectors",
    "tiktok_selectors",
    "instagram_web_selectors",
)

TURKISH_CHARS = "çğıöşüÇĞİÖŞÜ"

# Lists whose Turkish text is a value being searched for rather than a UI control to
# find, and which therefore have nothing to translate.
EXEMPT = {
    # Istanbul's own offset, checked to confirm the picker is in the expected zone. This
    # is a timezone question, not a language one -- it belongs to per-customer config.
    "TIMEZONE_INDICATORS",
    # Turkish month names, used to type a locale-formatted date. The English path types
    # a numeric format instead.
    "MONTH_MAP",
}

LIST_PATTERN = re.compile(
    r"^\s{4}([A-Z_][A-Z0-9_]*)\s*:\s*(?:List\[str\]|Dict\[str, int\]|str)\s*=\s*"
    r"(\[.*?\n\s{4}\]|\{.*?\n\s{4}\}|\".*?\")",
    re.S | re.M,
)
TEXT_PATTERN = re.compile(
    r"has-text\('([^']*)'\)|aria-label\*?='([^']*)'|has-text\(\"([^\"]*)\"\)"
)
STRUCTURAL_PATTERN = re.compile(
    r'"[^"]*#[\w-]+|"\s*\[[\w-]+|data-e2e=|input\[|div\[class|\[name=|\[type='
)


def _is_turkish(text: str) -> bool:
    return any(character in TURKISH_CHARS for character in text)


def _selector_lists():
    for module in SELECTOR_FILES:
        source = (REPO / "automation" / "publishing" / f"{module}.py").read_text(encoding="utf-8")
        for match in LIST_PATTERN.finditer(source):
            name, body = match.group(1), match.group(2)
            if name in EXEMPT:
                continue
            texts = [t for group in TEXT_PATTERN.findall(body) for t in group if t]
            yield module, name, body, texts


def test_no_ui_action_is_reachable_only_in_turkish():
    """
    A list may lean on Turkish wording, but never as its only way in. Either it also
    resolves structurally, or it names the same control in another language.
    """
    stranded = []
    for module, name, body, texts in _selector_lists():
        if not texts:
            continue
        turkish = [t for t in texts if _is_turkish(t)]
        latin = [t for t in texts if not _is_turkish(t)]
        if turkish and not latin and not STRUCTURAL_PATTERN.search(body):
            stranded.append(f"{module}.{name} (only: {turkish[:2]})")

    assert not stranded, (
        "these lists can only be resolved on a Turkish-language account:\n  "
        + "\n  ".join(stranded)
    )


@pytest.mark.parametrize(
    "blocklist,must_include",
    [
        pytest.param(
            "tiktok", ("hemen paylaş", "post now"), id="tiktok-publish-now"
        ),
        pytest.param(
            "instagram", ("paylaş", "share"), id="instagram-share-now"
        ),
    ],
)
def test_the_publish_now_blocklists_know_both_languages(blocklist, must_include):
    """
    These are matched against a button's own text before it is clicked. A blocklist that
    only knows the Turkish label would pass the English button through -- and that button
    publishes the whole week immediately instead of on its schedule.

    Read off the class rather than the source: a name also appears in the comments above
    it, and matching source text found the wrong list entirely.
    """
    if blocklist == "tiktok":
        from automation.publishing.tiktok_selectors import TikTokSelectors

        labels = TikTokSelectors.FORBIDDEN_IMMEDIATE_PUBLISH_LABELS
    else:
        from automation.publishing.instagram_web_selectors import InstagramWebSelectors

        labels = InstagramWebSelectors.FORBIDDEN_IMMEDIATE_SHARE_LABELS

    joined = " | ".join(label.lower() for label in labels)
    for label in must_include:
        assert label in joined, f"{blocklist} blocklist must still refuse {label!r}"


def test_the_tiktok_content_check_modal_is_answerable_in_english():
    """
    The modal offers exactly two buttons: Cancel, and one that publishes immediately.
    Not finding Cancel does not make the run click the other one, but it does strand the
    Reel -- so both wordings live in the selector list, not at one call site.
    """
    from automation.publishing.tiktok_selectors import TikTokSelectors

    cancel = " ".join(TikTokSelectors.CONTENT_CHECK_MODAL_CANCEL_BUTTONS).lower()
    assert "i̇ptal" in cancel or "iptal" in cancel
    assert "cancel" in cancel

    modal = " ".join(TikTokSelectors.CONTENT_CHECK_CONFIRM_MODAL).lower()
    assert "paylaşmaya devam" in modal
    assert "continue posting" in modal
