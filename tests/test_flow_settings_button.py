"""
Regression: Flow's view-options button must never be mistaken for generation settings.

2026-09-09, with no change on our side, every craftsbyman run died at
FLOW_SETTINGS_SAVE_FAILED. Flow had added a second settings button to the top bar --
aria-label "Kutu izgarasi ayarlari", tooltip "Ayarlari goster" -- which opens grid/batch
view options. Those apply immediately, so the panel has no Save button. A substring match
on "Ayarlar" selected it, and it sits higher in the DOM than the real one.

Both button shapes below are copied from the captured DOM in screenshots/errors/.
"""
from unittest.mock import MagicMock

from automation.flow.page import FlowPage
from automation.flow.selectors import FlowSelectors


def _button(icon_name, visible=True):
    btn = MagicMock()
    btn.is_visible.return_value = visible
    icon = MagicMock()
    icon.count.return_value = 1
    icon.text_content.return_value = icon_name
    btn.locator.return_value.first = icon
    btn._icon = icon_name
    return btn


def _page_with(buttons):
    page = FlowPage.__new__(FlowPage)
    mock_page = MagicMock()
    mock_page.locator.return_value.all.return_value = buttons
    page.page = mock_page
    page.find_first_visible = lambda selectors, timeout_ms=1000: "FELL_BACK"
    return page


def test_view_options_button_is_not_taken_for_settings():
    """The top-bar view-options button comes first in the DOM and must lose."""
    view_options = _button("settings_2")   # aria-label "Kutu izgarasi ayarlari"
    real_settings = _button("tune")        # aria-label "Ayarlar"
    page = _page_with([view_options, real_settings])
    assert page.resolve_settings_button()._icon == "tune"


def test_tune_button_is_found_when_it_is_the_only_one():
    page = _page_with([_button("tune")])
    assert page.resolve_settings_button()._icon == "tune"


def test_no_tune_button_falls_back_rather_than_guessing():
    """With no tune icon, resolution defers to the exact-match selector list."""
    page = _page_with([_button("settings_2"), _button("home")])
    assert page.resolve_settings_button() == "FELL_BACK"


def test_settings_selectors_are_exact_not_substring():
    """A substring aria-label match is what selected the wrong button."""
    joined = " ".join(FlowSelectors.SETTINGS_BUTTON_SELECTORS)
    assert "aria-label*=" not in joined, "gevsek aria-label eslesmesi geri gelmis"
    assert "has-text('Ayarlar')" not in joined, "gevsek metin eslesmesi geri gelmis"
    assert "button[aria-label='Ayarlar']" in joined
    assert "tune" in joined


# ---------------------------------------------------------------------------
# Flow's 2026-09-09 interface change. Every assertion below was read off the live
# DOM (screenshots/errors/ + a live probe), not guessed.
# ---------------------------------------------------------------------------

def test_icon_selectors_target_mat_icon():
    """
    Icons moved from <i class="google-symbols"> to <mat-icon class="... google-symbols">.

    Verified live: i.google-symbols count=0, mat-icon count=22. Every icon-based
    selector in the codebase silently matched nothing, which is why the settings
    button, the submit button and the download button all stopped resolving.
    """
    joined = " ".join(FlowSelectors.SETTINGS_BUTTON_SELECTORS)
    assert "mat-icon:text-is('tune')" in joined


def test_prompt_selectors_target_prosemirror():
    """Flow replaced the Slate.js editor with ProseMirror; the old attribute is gone."""
    sels = FlowSelectors.PROMPT_INPUT_SELECTORS
    assert any("ProseMirror" in s for s in sels), "ProseMirror secicisi yok"
    assert sels[0].startswith("div.ProseMirror"), "ProseMirror once denenmeli"


def test_approval_selectors_target_material_radio():
    """
    Approval is a mat-radio-button group now.

    The other settings in that panel are still segmented button[role='radio'] -- fifteen
    of them -- so matching on the role alone selects an aspect-ratio button instead of
    the approval mode. Verified live: mat-radio-button count=2, and the old
    button[role='radio'] approval selectors count=0.
    """
    assert FlowSelectors.APPROVAL_NEVER_SELECTORS[0] == "mat-radio-button:has-text('Hiçbir zaman')"
    assert FlowSelectors.APPROVAL_ALWAYS_SELECTORS[0] == "mat-radio-button:has-text('Her zaman')"
