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
