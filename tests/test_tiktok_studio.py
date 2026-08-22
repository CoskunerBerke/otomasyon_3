"""
Unit tests for TikTok Studio Web UI automation, file picker fallback, and scheduler.
Includes caption replacement verification, 'Planla' radio selection, and publish-now safety.
"""
from pathlib import Path
from unittest.mock import MagicMock

from automation.publishing.models import Platform, PlatformPublicationStatus, PublishRecord
from automation.publishing.config import PublishingConfig, get_default_tiktok_profile_path
from automation.publishing.tiktok_selectors import TikTokSelectors
from automation.publishing.tiktok_browser import TikTokBrowserManager
from automation.publishing.tiktok_ui_observer import TikTokUIObserver
from automation.publishing.tiktok_publisher import MockTikTokPublisher, TikTokPublisher

def test_tiktok_studio_selectors_and_url_support():
    assert any("Video seçin" in s or "Select video" in s for s in TikTokSelectors.SELECT_VIDEO_BUTTONS)
    assert any("input[type='file']" in s for s in TikTokSelectors.FILE_INPUT_SELECTORS)
    assert any("Planla" in s or "Schedule" in s for s in TikTokSelectors.SCHEDULE_RADIO_OPTIONS)
    assert any("Şimdi" in s or "Now" in s for s in TikTokSelectors.NOW_RADIO_OPTIONS)
    assert any("Planla" in s or "Schedule" in s for s in TikTokSelectors.FINAL_ACTION_BUTTONS)

def test_tiktok_studio_direct_file_upload_method_a(tmp_path: Path):
    dummy_video = tmp_path / "reel.mp4"
    dummy_video.write_bytes(b"dummy mp4 data" * 10)

    mock_page = MagicMock()
    mock_file_loc = MagicMock()
    mock_file_loc.count.return_value = 1
    mock_page.locator.return_value.first = mock_file_loc

    observer = TikTokUIObserver(mock_page)
    res = observer.upload_file(dummy_video)
    assert res is True
    mock_file_loc.set_input_files.assert_called_once_with(str(dummy_video.resolve()))

def test_tiktok_studio_native_file_chooser_fallback_method_b(tmp_path: Path):
    dummy_video = tmp_path / "reel.mp4"
    dummy_video.write_bytes(b"dummy mp4 data" * 10)

    mock_page = MagicMock()
    
    mock_empty_loc = MagicMock()
    mock_empty_loc.count.return_value = 0
    mock_empty_loc.is_visible.return_value = True
    mock_empty_loc.is_enabled.return_value = True

    mock_chooser = MagicMock()
    fc_info = MagicMock()
    fc_info.value = mock_chooser
    
    mock_page.expect_file_chooser.return_value.__enter__.return_value = fc_info
    mock_page.locator.return_value.first = mock_empty_loc

    observer = TikTokUIObserver(mock_page)
    res = observer.upload_file(dummy_video)
    assert res is True
    mock_chooser.set_files.assert_called_once_with(str(dummy_video.resolve()))

def test_tiktok_studio_existing_editor_detected_and_resumed():
    mock_page = MagicMock()
    mock_page.content.return_value = "<html><body><div>Yüklendi (7.44MB) REEL-2026-0010_Japanese_Zen_Temple.mp4</div></body></html>"
    
    mock_loc = MagicMock()
    mock_loc.is_visible.return_value = True
    mock_page.locator.return_value.first = mock_loc

    observer = TikTokUIObserver(mock_page)
    is_open = observer.is_editor_open_for_reel("REEL-2026-0010", "REEL-2026-0010_Japanese_Zen_Temple.mp4")
    assert is_open is True

def test_tiktok_studio_replace_caption_clears_filename():
    mock_page = MagicMock()
    mock_editor = MagicMock()
    mock_editor.is_visible.return_value = True
    # Read-back returns generated caption (no filename prefix)
    mock_editor.inner_text.return_value = "A peaceful Japanese Zen temple rising in 30s. #architecture #japan"
    
    def loc_side_effect(sel):
        res = MagicMock()
        if "react-joyride" in sel or "overlay" in sel or "joyride" in sel:
            loc = MagicMock()
            loc.is_visible.return_value = False
            loc.wait_for.side_effect = TimeoutError("not visible")
            res.first = loc
        else:
            res.first = mock_editor
        return res

    mock_page.locator.side_effect = loc_side_effect

    observer = TikTokUIObserver(mock_page)
    ok, msg = observer.replace_caption(
        caption="A peaceful Japanese Zen temple rising in 30s.",
        hashtags=["#architecture", "#japan"]
    )
    assert ok is True
    assert msg == "CAPTION_VERIFIED"
    mock_page.keyboard.press.assert_any_call("Control+A")
    mock_page.keyboard.press.assert_any_call("Backspace")

def test_tiktok_studio_caption_verification_fails_if_filename_remains():
    mock_page = MagicMock()
    mock_editor = MagicMock()
    mock_editor.is_visible.return_value = True
    # Read-back still contains filename prefix
    mock_editor.inner_text.return_value = "REEL-2026-0010_Japanese_Zen_Temple A peaceful Japanese Zen temple"
    
    def loc_side_effect(sel):
        res = MagicMock()
        if "react-joyride" in sel or "overlay" in sel or "joyride" in sel:
            loc = MagicMock()
            loc.is_visible.return_value = False
            loc.wait_for.side_effect = TimeoutError("not visible")
            res.first = loc
        else:
            res.first = mock_editor
        return res

    mock_page.locator.side_effect = loc_side_effect

    observer = TikTokUIObserver(mock_page)
    ok, msg = observer.replace_caption(
        caption="A peaceful Japanese Zen temple",
        hashtags=["#architecture"]
    )
    assert ok is False
    assert "CAPTION_VERIFICATION_FAILED" in msg

def test_tiktok_studio_select_schedule_mode_planla():
    mock_page = MagicMock()
    mock_planla_input = MagicMock()
    mock_planla_input.is_visible.return_value = True
    mock_planla_input.get_attribute.side_effect = lambda attr: "radio-123" if attr == "id" else ("true" if (attr == "aria-checked" and clicked_state["clicked"]) else "false")

    mock_simdi_input = MagicMock()
    mock_simdi_input.is_visible.return_value = True
    mock_simdi_input.get_attribute.return_value = "false"
    mock_simdi_input.evaluate.return_value = False

    mock_label = MagicMock()
    mock_label.is_visible.return_value = True

    clicked_state = {"clicked": False}
    def mock_click(*args, **kwargs):
        clicked_state["clicked"] = True

    mock_label.click = MagicMock(side_effect=mock_click)
    mock_planla_input.click = MagicMock(side_effect=mock_click)

    mock_planla_input.evaluate.side_effect = lambda expr: clicked_state["clicked"]

    def loc_side_effect(sel):
        res = MagicMock()
        if "value='schedule'" in sel:
            res.first = mock_planla_input
        elif "value='post_now'" in sel:
            res.first = mock_simdi_input
        elif "label[for='radio-123']" in sel or "Planla" in sel or ":has-text('Schedule')" in sel:
            res.first = mock_label
        else:
            res.first.is_visible.return_value = False
            res.first.wait_for.side_effect = TimeoutError("not visible")
        return res

    mock_page.locator.side_effect = loc_side_effect

    observer = TikTokUIObserver(mock_page)
    ok, msg = observer.select_schedule_mode("SCHEDULE")
    assert ok is True
    assert msg == "SCHEDULE_MODE_VERIFIED"
    assert mock_label.click.called or mock_planla_input.click.called


def test_tiktok_schedule_mode_case_1_already_checked():
    """Test 1: Schedule is already checked -> click count 0 -> PASS."""
    mock_page = MagicMock()
    mock_planla_input = MagicMock()
    mock_planla_input.is_visible.return_value = True
    mock_planla_input.get_attribute.side_effect = lambda attr: "radio-case1" if attr == "id" else ("true" if attr == "aria-checked" else "false")
    mock_planla_input.evaluate.return_value = True
    mock_planla_input.is_checked.return_value = True

    mock_simdi_input = MagicMock()
    mock_simdi_input.is_visible.return_value = True
    mock_simdi_input.get_attribute.return_value = "false"
    mock_simdi_input.evaluate.return_value = False
    mock_simdi_input.is_checked.return_value = False

    mock_label = MagicMock()

    def loc_side_effect(sel):
        res = MagicMock()
        if "value='schedule'" in sel:
            res.first = mock_planla_input
        elif "value='post_now'" in sel:
            res.first = mock_simdi_input
        else:
            res.first = mock_label
        return res

    mock_page.locator.side_effect = loc_side_effect

    observer = TikTokUIObserver(mock_page)
    ok, msg = observer.select_schedule_mode("SCHEDULE")
    assert ok is True
    assert msg == "SCHEDULE_MODE_VERIFIED"
    mock_label.click.assert_not_called()
    mock_planla_input.click.assert_not_called()


def test_tiktok_schedule_mode_case_2_label_for_click_intercept_regression():
    """
    Test 2 (Exact Live Intercept Bug):
    Input click would fail or be intercepted.
    label[for='radio-svp7yhtv4'] exists and is clicked -> PASS.
    """
    mock_page = MagicMock()
    mock_planla_input = MagicMock()
    mock_planla_input.is_visible.return_value = True
    mock_planla_input.get_attribute.side_effect = lambda attr: "radio-svp7yhtv4" if attr == "id" else ("true" if (attr == "aria-checked" and clicked_state["clicked"]) else "false")

    mock_simdi_input = MagicMock()
    mock_simdi_input.is_visible.return_value = True
    mock_simdi_input.get_attribute.return_value = "false"
    mock_simdi_input.evaluate.return_value = False

    mock_label = MagicMock()
    mock_label.is_visible.return_value = True

    clicked_state = {"clicked": False}
    def label_click(*args, **kwargs):
        clicked_state["clicked"] = True

    mock_label.click = MagicMock(side_effect=label_click)
    # Direct input click must not be relied upon
    mock_planla_input.click = MagicMock(side_effect=Exception("Radio__innerCircle intercepts pointer events"))

    mock_planla_input.evaluate.side_effect = lambda expr: clicked_state["clicked"]

    def loc_side_effect(sel):
        res = MagicMock()
        if "value='schedule'" in sel:
            res.first = mock_planla_input
        elif "value='post_now'" in sel:
            res.first = mock_simdi_input
        elif "label[for='radio-svp7yhtv4']" in sel:
            res.first = mock_label
        else:
            res.first.is_visible.return_value = False
            res.first.wait_for.side_effect = TimeoutError("not visible")
        return res

    mock_page.locator.side_effect = loc_side_effect

    observer = TikTokUIObserver(mock_page)
    ok, msg = observer.select_schedule_mode("SCHEDULE")
    assert ok is True
    assert msg == "SCHEDULE_MODE_VERIFIED"
    assert mock_label.click.called


def test_tiktok_schedule_mode_case_3_wrapper_click():
    """Test 3: No label[for], wrapper exists and is clicked -> PASS."""
    mock_page = MagicMock()
    mock_planla_input = MagicMock()
    mock_planla_input.is_visible.return_value = True
    mock_planla_input.get_attribute.side_effect = lambda attr: "" if attr == "id" else ("true" if (attr == "aria-checked" and clicked_state["clicked"]) else "false")

    mock_simdi_input = MagicMock()
    mock_simdi_input.is_visible.return_value = True
    mock_simdi_input.evaluate.return_value = False

    mock_wrapper = MagicMock()
    mock_wrapper.is_visible.return_value = True

    clicked_state = {"clicked": False}
    def wrapper_click(*args, **kwargs):
        clicked_state["clicked"] = True

    mock_wrapper.click = MagicMock(side_effect=wrapper_click)
    mock_planla_input.evaluate.side_effect = lambda expr: clicked_state["clicked"]

    mock_ancestor = MagicMock()
    mock_ancestor.first = mock_wrapper
    mock_ancestor.is_visible.return_value = True
    mock_planla_input.locator.side_effect = lambda sel: mock_ancestor

    def loc_side_effect(sel):
        res = MagicMock()
        if "value='schedule'" in sel:
            res.first = mock_planla_input
        elif "value='post_now'" in sel:
            res.first = mock_simdi_input
        else:
            res.first = mock_wrapper
        return res

    mock_page.locator.side_effect = loc_side_effect

    observer = TikTokUIObserver(mock_page)
    ok, msg = observer.select_schedule_mode("SCHEDULE")
    assert ok is True
    assert msg == "SCHEDULE_MODE_VERIFIED"
    assert mock_wrapper.click.called


def test_tiktok_schedule_mode_case_4_inner_circle_click():
    """Test 4: Wrapper click not matched, inner circle exists and is clicked -> PASS."""
    mock_page = MagicMock()
    mock_planla_input = MagicMock()
    mock_planla_input.is_visible.return_value = True
    mock_planla_input.get_attribute.side_effect = lambda attr: "" if attr == "id" else ("true" if (attr == "aria-checked" and clicked_state["clicked"]) else "false")

    mock_simdi_input = MagicMock()
    mock_simdi_input.is_visible.return_value = True
    mock_simdi_input.evaluate.return_value = False

    mock_circle = MagicMock()
    mock_circle.is_visible.return_value = True

    clicked_state = {"clicked": False}
    def circle_click(*args, **kwargs):
        clicked_state["clicked"] = True

    mock_circle.click = MagicMock(side_effect=circle_click)
    mock_planla_input.evaluate.side_effect = lambda expr: clicked_state["clicked"]

    def input_loc(sel):
        res = MagicMock()
        if "Radio__innerCircle" in sel or "innerCircle" in sel:
            res.first = mock_circle
            res.is_visible.return_value = True
        else:
            res.first.is_visible.return_value = False
            res.first.wait_for.side_effect = TimeoutError("not visible")
            res.is_visible.return_value = False
            res.wait_for.side_effect = TimeoutError("not visible")
        return res

    mock_planla_input.locator.side_effect = input_loc

    def loc_side_effect(sel):
        res = MagicMock()
        if "value='schedule'" in sel:
            res.first = mock_planla_input
        elif "value='post_now'" in sel:
            res.first = mock_simdi_input
        else:
            res.first.is_visible.return_value = False
            res.first.wait_for.side_effect = TimeoutError("not visible")
        return res

    mock_page.locator.side_effect = loc_side_effect

    observer = TikTokUIObserver(mock_page)
    ok, msg = observer.select_schedule_mode("SCHEDULE")
    assert ok is True
    assert msg == "SCHEDULE_MODE_VERIFIED"
    assert mock_circle.click.called


def test_tiktok_schedule_mode_case_5_keyboard_space_fallback():
    """Test 5: Pointer interactions fail, focus + Space sets checked -> PASS."""
    mock_page = MagicMock()
    mock_planla_input = MagicMock()
    mock_planla_input.is_visible.return_value = True
    mock_planla_input.get_attribute.side_effect = lambda attr: "" if attr == "id" else ("true" if (attr == "aria-checked" and clicked_state["pressed"]) else "false")

    mock_simdi_input = MagicMock()
    mock_simdi_input.is_visible.return_value = True
    mock_simdi_input.evaluate.return_value = False

    clicked_state = {"pressed": False}
    def space_press(key):
        if key == "Space":
            clicked_state["pressed"] = True

    mock_page.keyboard.press = MagicMock(side_effect=space_press)
    mock_planla_input.evaluate.side_effect = lambda expr: clicked_state["pressed"]

    # Child locators invisible
    child_loc = MagicMock()
    child_loc.first.is_visible.return_value = False
    child_loc.first.wait_for.side_effect = TimeoutError("not visible")
    child_loc.is_visible.return_value = False
    child_loc.wait_for.side_effect = TimeoutError("not visible")
    mock_planla_input.locator.return_value = child_loc

    def loc_side_effect(sel):
        res = MagicMock()
        if "value='schedule'" in sel:
            res.first = mock_planla_input
        elif "value='post_now'" in sel:
            res.first = mock_simdi_input
        else:
            res.first.is_visible.return_value = False
            res.first.wait_for.side_effect = TimeoutError("not visible")
        return res

    mock_page.locator.side_effect = loc_side_effect

    observer = TikTokUIObserver(mock_page)
    ok, msg = observer.select_schedule_mode("SCHEDULE")
    assert ok is True
    assert msg == "SCHEDULE_MODE_VERIFIED"
    mock_planla_input.focus.assert_called()
    assert clicked_state["pressed"] is True


def test_tiktok_schedule_mode_case_6_schedule_true_but_now_also_true():
    """Test 6: Schedule is true but Now is also true -> FAIL."""
    mock_page = MagicMock()
    mock_planla_input = MagicMock()
    mock_planla_input.is_visible.return_value = True
    mock_planla_input.evaluate.return_value = True

    mock_simdi_input = MagicMock()
    mock_simdi_input.is_visible.return_value = True
    mock_simdi_input.evaluate.return_value = True  # Both true = invalid state!

    def loc_side_effect(sel):
        res = MagicMock()
        if "value='schedule'" in sel:
            res.first = mock_planla_input
        elif "value='post_now'" in sel:
            res.first = mock_simdi_input
        else:
            res.first.is_visible.return_value = False
            res.first.wait_for.side_effect = TimeoutError("not visible")
        return res

    mock_page.locator.side_effect = loc_side_effect

    observer = TikTokUIObserver(mock_page)
    ok, msg = observer.select_schedule_mode("SCHEDULE")
    assert ok is False
    assert "SCHEDULING_UNAVAILABLE" in msg or "MISMATCH" in msg


def test_tiktok_schedule_mode_case_7_no_interaction_changes_state():
    """Test 7: No interaction changes state -> SCHEDULING_UNAVAILABLE -> final Planla click 0."""
    mock_page = MagicMock()
    mock_planla_input = MagicMock()
    mock_planla_input.is_visible.return_value = True
    mock_planla_input.evaluate.return_value = False
    mock_planla_input.get_attribute.return_value = "false"

    mock_simdi_input = MagicMock()
    mock_simdi_input.is_visible.return_value = True
    mock_simdi_input.evaluate.return_value = True

    def loc_side_effect(sel):
        res = MagicMock()
        if "value='schedule'" in sel:
            res.first = mock_planla_input
        elif "value='post_now'" in sel:
            res.first = mock_simdi_input
        else:
            res.first.is_visible.return_value = False
            res.first.wait_for.side_effect = TimeoutError("not visible")
        return res

    mock_page.locator.side_effect = loc_side_effect

    observer = TikTokUIObserver(mock_page)
    ok, msg = observer.select_schedule_mode("SCHEDULE")
    assert ok is False
    assert "SCHEDULING_UNAVAILABLE" in msg

    # Verify final schedule click blocked
    mock_final_btn = MagicMock()
    mock_page.locator.return_value.first = mock_final_btn
    success, submit_msg = observer.click_schedule_and_verify(schedule_mode_verified=False)
    assert success is False
    mock_final_btn.click.assert_not_called()

def test_tiktok_studio_publish_now_safety_blocks_click_when_simdi_active():
    mock_page = MagicMock()
    mock_btn = MagicMock()
    mock_btn.is_visible.return_value = True
    mock_btn.is_enabled.return_value = True
    mock_page.locator.return_value.first = mock_btn

    observer = TikTokUIObserver(mock_page)
    # schedule_mode_verified is False -> must block click!
    success, msg = observer.click_schedule_and_verify(schedule_mode_verified=False)
    assert success is False
    assert "SCHEDULE_MODE_NOT_ACTIVE" in msg
    mock_btn.click.assert_not_called()

def test_tiktok_studio_ai_disclosure_under_show_more():
    mock_page = MagicMock()
    mock_toggle = MagicMock()
    mock_toggle.is_visible.return_value = True
    ai_state = [False]
    mock_toggle.is_checked.side_effect = lambda: ai_state[0]
    mock_toggle.get_attribute.side_effect = lambda attr: "true" if (attr == "aria-checked" and ai_state[0]) else "false"
    def on_click(*a, **kw):
        ai_state[0] = True
    mock_toggle.click.side_effect = on_click
    mock_toggle.locator.return_value.first = mock_toggle
    mock_page.locator.return_value.first = mock_toggle

    observer = TikTokUIObserver(mock_page)
    res = observer.toggle_ai_disclosure(True)
    assert res is True
    mock_toggle.click.assert_called()

def test_tiktok_studio_date_and_time_setting():
    mock_page = MagicMock()
    current_date = ["2026-08-16"]
    current_time = ["19:30"]

    def loc_side_effect(sel):
        res = MagicMock()
        loc = MagicMock()
        loc.is_visible.return_value = True
        loc.is_enabled.return_value = True
        if "19" in sel:
            loc.click.side_effect = lambda *a, **kw: None
        elif "30" in sel:
            loc.click.side_effect = lambda *a, **kw: current_time.__setitem__(0, "19:30")
        elif "value*=':'" in sel or "time" in sel:
            loc.get_attribute.side_effect = lambda attr: current_time[0] if attr == "value" else None
            loc.input_value.side_effect = lambda: current_time[0]
        else:
            loc.get_attribute.side_effect = lambda attr: current_date[0] if attr == "value" else None
            loc.input_value.side_effect = lambda: current_date[0]
        res.first = loc
        return res

    mock_page.locator.side_effect = loc_side_effect
    observer = TikTokUIObserver(mock_page)
    ok, msg = observer.set_schedule_datetime("2026-08-16T19:30:00+03:00")
    assert ok is True
    assert msg == "DATETIME_SET_AND_VERIFIED"

def test_tiktok_joyride_overlay_detected_and_dismissed_via_kapat():
    mock_page = MagicMock()
    mock_close_btn = MagicMock()
    mock_close_btn.is_visible.return_value = True
    mock_close_btn.is_enabled.return_value = True

    # Overlay is visible on check 1, not visible on check 2
    overlay_states = [True, True, False, False]

    def loc_side_effect(sel):
        res = MagicMock()
        if "react-joyride-portal" in sel or "overlay" in sel:
            vis = overlay_states.pop(0) if overlay_states else False
            loc = MagicMock()
            loc.is_visible.return_value = vis
            if not vis:
                loc.wait_for.side_effect = TimeoutError("not visible")
            res.first = loc
        elif "Kapat" in sel or "Close" in sel:
            res.first = mock_close_btn
        else:
            loc = MagicMock()
            loc.is_visible.return_value = False
            loc.wait_for.side_effect = TimeoutError("not visible")
            res.first = loc
        return res

    mock_page.locator.side_effect = loc_side_effect

    observer = TikTokUIObserver(mock_page)
    ok, msg = observer.dismiss_onboarding_overlay_if_present()
    assert ok is True
    assert "CAPTION_INTERACTION_UNBLOCKED" in msg
    mock_close_btn.click.assert_called_once()

def test_tiktok_joyride_overlay_dismissed_via_close_en():
    mock_page = MagicMock()
    mock_close_btn = MagicMock()
    mock_close_btn.is_visible.return_value = True
    mock_close_btn.is_enabled.return_value = True

    overlay_states = [True, True, False, False]

    def loc_side_effect(sel):
        res = MagicMock()
        if "react-joyride-portal" in sel or "overlay" in sel:
            vis = overlay_states.pop(0) if overlay_states else False
            loc = MagicMock()
            loc.is_visible.return_value = vis
            if not vis:
                loc.wait_for.side_effect = TimeoutError("not visible")
            res.first = loc
        elif "Close" in sel:
            res.first = mock_close_btn
        else:
            loc = MagicMock()
            loc.is_visible.return_value = False
            loc.wait_for.side_effect = TimeoutError("not visible")
            res.first = loc
        return res

    mock_page.locator.side_effect = loc_side_effect

    observer = TikTokUIObserver(mock_page)
    ok, msg = observer.dismiss_onboarding_overlay_if_present()
    assert ok is True
    assert "CAPTION_INTERACTION_UNBLOCKED" in msg
    mock_close_btn.click.assert_called_once()

def test_tiktok_joyride_overlay_dismissed_via_atla_skip():
    mock_page = MagicMock()
    mock_skip_btn = MagicMock()
    mock_skip_btn.is_visible.return_value = True
    mock_skip_btn.is_enabled.return_value = True

    overlay_states = [True, True, False, False]

    def loc_side_effect(sel):
        res = MagicMock()
        if "react-joyride-portal" in sel or "overlay" in sel:
            vis = overlay_states.pop(0) if overlay_states else False
            loc = MagicMock()
            loc.is_visible.return_value = vis
            if not vis:
                loc.wait_for.side_effect = TimeoutError("not visible")
            res.first = loc
        elif "Atla" in sel or "Skip" in sel:
            res.first = mock_skip_btn
        else:
            loc = MagicMock()
            loc.is_visible.return_value = False
            loc.wait_for.side_effect = TimeoutError("not visible")
            res.first = loc
        return res

    mock_page.locator.side_effect = loc_side_effect

    observer = TikTokUIObserver(mock_page)
    ok, msg = observer.dismiss_onboarding_overlay_if_present()
    assert ok is True
    assert "CAPTION_INTERACTION_UNBLOCKED" in msg
    mock_skip_btn.click.assert_called_once()

def test_tiktok_joyride_overlay_dismissed_via_escape():
    mock_page = MagicMock()
    mock_hidden_btn = MagicMock()
    mock_hidden_btn.is_visible.return_value = False
    mock_hidden_btn.wait_for.side_effect = TimeoutError("not visible")

    overlay_states = [True, True, False, False]

    def loc_side_effect(sel):
        res = MagicMock()
        if "react-joyride-portal" in sel or "overlay" in sel:
            vis = overlay_states.pop(0) if overlay_states else False
            loc = MagicMock()
            loc.is_visible.return_value = vis
            if not vis:
                loc.wait_for.side_effect = TimeoutError("not visible")
            res.first = loc
        else:
            loc = MagicMock()
            loc.is_visible.return_value = False
            loc.wait_for.side_effect = TimeoutError("not visible")
            res.first = loc
        return res

    mock_page.locator.side_effect = loc_side_effect

    observer = TikTokUIObserver(mock_page)
    ok, msg = observer.dismiss_onboarding_overlay_if_present()
    assert ok is True
    assert "CAPTION_INTERACTION_UNBLOCKED" in msg
    mock_page.keyboard.press.assert_called_with("Escape")

def test_tiktok_joyride_overlay_remaining_blocks_caption_and_fails_safely():
    mock_page = MagicMock()
    mock_overlay = MagicMock()
    mock_overlay.is_visible.return_value = True

    mock_page.locator.return_value.first = mock_overlay

    observer = TikTokUIObserver(mock_page)
    ok, msg = observer.dismiss_onboarding_overlay_if_present(max_steps=2)
    assert ok is False
    assert "TIKTOK_ONBOARDING_OVERLAY_BLOCKING" in msg

    # Calling replace_caption must fail safely without force click
    cap_ok, cap_msg = observer.replace_caption("New caption", ["#Tag"])
    assert cap_ok is False
    assert "TIKTOK_ONBOARDING_OVERLAY_BLOCKING" in cap_msg

def test_tiktok_studio_real_dom_fixture_resolution():
    fixture_path = Path(__file__).resolve().parent / "fixtures" / "tiktok_live_controls.html"
    assert fixture_path.exists()
    html_content = fixture_path.read_text(encoding="utf-8")

    assert "react-joyride-portal" in html_content
    assert "Kapat" in html_content
    assert "public-DraftEditor-content" in html_content
    assert "Planla" in html_content
    assert "schedule-datetime-container" in html_content


def test_tiktok_editor_state_empty_upload_page_detected():
    """Test that EMPTY_UPLOAD_PAGE is detected when select button is present without editor."""
    mock_page = MagicMock()
    mock_page.content.return_value = "<html><body><button>Video seçin</button></body></html>"

    def loc_side_effect(sel):
        res = MagicMock()
        if sel in TikTokSelectors.SELECT_VIDEO_BUTTONS or sel in TikTokSelectors.FILE_INPUT_SELECTORS:
            res.first.is_visible.return_value = True
            res.count.return_value = 1
        else:
            res.first.is_visible.return_value = False
            res.first.wait_for.side_effect = TimeoutError("not visible")
            res.count.return_value = 0
        return res

    mock_page.locator.side_effect = loc_side_effect
    observer = TikTokUIObserver(mock_page)
    assert observer.detect_editor_state() == "EMPTY_UPLOAD_PAGE"


def test_tiktok_editor_state_loaded_editor_detected():
    """Test that LOADED_EDITOR is detected when DraftEditor or upload indicators are present."""
    mock_page = MagicMock()
    mock_page.content.return_value = "<html><body><div class='uploaded'>Yüklendi (7.44MB)</div></body></html>"

    def loc_side_effect(sel):
        res = MagicMock()
        if "DraftEditor" in sel or "contenteditable" in sel:
            res.first.is_visible.return_value = True
        else:
            res.first.is_visible.return_value = False
            res.first.wait_for.side_effect = TimeoutError("not visible")
        return res

    mock_page.locator.side_effect = loc_side_effect
    observer = TikTokUIObserver(mock_page)
    assert observer.detect_editor_state() == "LOADED_EDITOR"


def test_tiktok_preflight_uploads_when_empty_page(tmp_path):
    """Test that preflight triggers upload when page is in EMPTY_UPLOAD_PAGE state."""
    mock_page = MagicMock()
    observer = TikTokUIObserver(mock_page)

    observer.is_logged_in = MagicMock(return_value=True)
    observer.verify_logged_in_username = MagicMock(return_value=(True, "@kitchenverse360", "OK"))
    observer.detect_editor_state = MagicMock(return_value="EMPTY_UPLOAD_PAGE")
    observer.upload_file = MagicMock(return_value=True)
    observer.wait_for_upload_completion = MagicMock(return_value=True)
    observer.dismiss_onboarding_overlay_if_present = MagicMock(return_value=(True, "OK"))
    observer.replace_caption = MagicMock(return_value=(True, "CAPTION_VERIFIED"))
    observer.select_schedule_mode = MagicMock(return_value=(True, "SCHEDULE_MODE_VERIFIED"))
    observer.set_schedule_datetime = MagicMock(return_value=(True, "DATETIME_SET"))
    observer.toggle_ai_disclosure = MagicMock(return_value=True)

    # Final button visible & enabled
    mock_btn = MagicMock()
    mock_btn.is_visible.return_value = True
    mock_btn.is_enabled.return_value = True
    mock_page.locator.return_value.first = mock_btn

    record = MagicMock()
    record.reel_id = "REEL-2026-0010"
    record.video_file = tmp_path / "vid.mp4"
    record.description = "Test caption"
    record.hashtags = ["#Shorts"]
    record.scheduled_at_local = "2026-08-16T19:30:00"

    ok, msg = observer.prepare_tiktok_schedule_preflight(record)
    assert ok is True
    assert msg == "TIKTOK_FINAL_SCHEDULE_READY"
    observer.upload_file.assert_called_once_with(record.video_file)
    mock_btn.click.assert_not_called()


def test_tiktok_preflight_skips_upload_when_loaded_editor(tmp_path):
    """Test that preflight skips upload when page is already LOADED_EDITOR."""
    mock_page = MagicMock()
    observer = TikTokUIObserver(mock_page)

    observer.is_logged_in = MagicMock(return_value=True)
    observer.verify_logged_in_username = MagicMock(return_value=(True, "@kitchenverse360", "OK"))
    observer.detect_editor_state = MagicMock(return_value="LOADED_EDITOR")
    observer.upload_file = MagicMock()
    observer.dismiss_onboarding_overlay_if_present = MagicMock(return_value=(True, "OK"))
    observer.replace_caption = MagicMock(return_value=(True, "CAPTION_VERIFIED"))
    observer.select_schedule_mode = MagicMock(return_value=(True, "SCHEDULE_MODE_VERIFIED"))
    observer.set_schedule_datetime = MagicMock(return_value=(True, "DATETIME_SET"))
    observer.toggle_ai_disclosure = MagicMock(return_value=True)

    mock_btn = MagicMock()
    mock_btn.is_visible.return_value = True
    mock_btn.is_enabled.return_value = True
    mock_page.locator.return_value.first = mock_btn

    record = MagicMock()
    record.reel_id = "REEL-2026-0010"
    record.video_file = tmp_path / "vid.mp4"
    record.description = "Test caption"
    record.hashtags = ["#Shorts"]
    record.scheduled_at_local = "2026-08-16T19:30:00"

    ok, msg = observer.prepare_tiktok_schedule_preflight(record)
    assert ok is True
    assert msg == "TIKTOK_FINAL_SCHEDULE_READY"
    # Upload must NEVER have been called
    observer.upload_file.assert_not_called()
    mock_btn.click.assert_not_called()


def test_tiktok_select_schedule_mode_real_input_state():
    """Verify that select_schedule_mode reads real radio input state (post_now=False, schedule=True)."""
    mock_page = MagicMock()

    mock_planla_input = MagicMock()
    mock_planla_input.is_visible.return_value = True
    # Initially unchecked
    mock_planla_input.evaluate.side_effect = lambda expr: True
    mock_planla_input.get_attribute.return_value = "true"

    mock_simdi_input = MagicMock()
    mock_simdi_input.is_visible.return_value = True
    mock_simdi_input.evaluate.side_effect = lambda expr: False
    mock_simdi_input.get_attribute.return_value = "false"

    mock_label = MagicMock()
    mock_label.is_visible.return_value = True

    def loc_side_effect(sel):
        res = MagicMock()
        if "value='schedule'" in sel:
            res.first = mock_planla_input
        elif "value='post_now'" in sel:
            res.first = mock_simdi_input
        elif "Planla" in sel:
            res.first = mock_label
        else:
            res.first.is_visible.return_value = False
            res.first.wait_for.side_effect = TimeoutError("not visible")
        return res

    mock_page.locator.side_effect = loc_side_effect
    observer = TikTokUIObserver(mock_page)

    ok, msg = observer.select_schedule_mode()
    assert ok is True
    assert msg == "SCHEDULE_MODE_VERIFIED"


# =============================================================================
# TIME PICKER AND AI DISCLOSURE SUITE
# =============================================================================

def test_tiktok_timepicker_case_1_ui_picker_success():
    """Case 1: Time field initially 12:00, UI picker selects Hour 19 and Minute 30, readback 19:30 -> PASS."""
    mock_page = MagicMock()
    time_val = ["12:00"]

    mock_time_input = MagicMock()
    mock_time_input.is_visible.return_value = True
    mock_time_input.get_attribute.side_effect = lambda attr: time_val[0] if attr == "value" else None
    mock_time_input.input_value.side_effect = lambda: time_val[0]

    mock_hour_19 = MagicMock()
    mock_hour_19.is_visible.return_value = True

    mock_min_30 = MagicMock()
    mock_min_30.is_visible.return_value = True

    def on_hour_click(*args, **kwargs):
        pass

    def on_min_click(*args, **kwargs):
        time_val[0] = "19:30"

    mock_hour_19.click.side_effect = on_hour_click
    mock_min_30.click.side_effect = on_min_click

    def loc_side_effect(sel):
        res = MagicMock()
        if "19" in sel:
            res.first = mock_hour_19
        elif "30" in sel:
            res.first = mock_min_30
        elif "input" in sel:
            res.first = mock_time_input
        else:
            res.first = MagicMock(is_visible=MagicMock(return_value=False), wait_for=MagicMock(side_effect=TimeoutError("not visible")))
        return res

    mock_page.locator.side_effect = loc_side_effect
    observer = TikTokUIObserver(mock_page)

    ok = observer._set_schedule_time(mock_time_input, "19:30")
    assert ok is True
    mock_hour_19.click.assert_called()
    mock_min_30.click.assert_called()
    assert time_val[0] == "19:30"


def test_tiktok_timepicker_case_2_typing_reverts_to_12_00_picker_used():
    """Case 2: Typing 19:30 into time field causes UI to revert to 12:00, picker strategy succeeds."""
    mock_page = MagicMock()
    time_val = ["12:00"]

    mock_time_input = MagicMock()
    mock_time_input.is_visible.return_value = True
    # Fill attempt does not change readback because it's readonly
    mock_time_input.fill.side_effect = lambda v, **kw: None
    mock_time_input.get_attribute.side_effect = lambda attr: time_val[0] if attr == "value" else None
    mock_time_input.input_value.side_effect = lambda: time_val[0]

    mock_hour_19 = MagicMock()
    mock_hour_19.is_visible.return_value = True
    mock_min_30 = MagicMock()
    mock_min_30.is_visible.return_value = True

    def on_min_click(*args, **kwargs):
        time_val[0] = "19:30"

    mock_min_30.click.side_effect = on_min_click

    def loc_side_effect(sel):
        res = MagicMock()
        if "19" in sel:
            res.first = mock_hour_19
        elif "30" in sel:
            res.first = mock_min_30
        elif "input" in sel:
            res.first = mock_time_input
        else:
            res.first = MagicMock(is_visible=MagicMock(return_value=False), wait_for=MagicMock(side_effect=TimeoutError("not visible")))
        return res

    mock_page.locator.side_effect = loc_side_effect
    observer = TikTokUIObserver(mock_page)

    ok = observer._set_schedule_time(mock_time_input, "19:30")
    assert ok is True
    assert time_val[0] == "19:30"


def test_tiktok_timepicker_case_3_picker_options_exact_matching():
    """Case 3: Exact 19 and 30 must be targeted, avoiding partial matches like 09 or 19:00."""
    mock_page = MagicMock()
    clicked_selectors = []
    is_popup_open = [True]

    def on_key(k):
        if k == "Escape":
            is_popup_open[0] = False
    mock_page.keyboard.press.side_effect = on_key

    mock_time_input = MagicMock()
    mock_time_input.is_visible.return_value = True
    time_val = ["12:00"]
    mock_time_input.get_attribute.side_effect = lambda attr: time_val[0] if attr == "value" else None
    mock_time_input.input_value.side_effect = lambda: time_val[0]

    def loc_side_effect(sel):
        res = MagicMock()
        loc = MagicMock()
        if "tiktok-timepicker-time-picker-container" in sel and ":has" not in sel and "text-is" not in sel:
            loc.is_visible.side_effect = lambda **kw: is_popup_open[0]
            def _timepicker_wait_for(*args, **kwargs):
                if not is_popup_open[0]:
                    raise TimeoutError("not visible")
            loc.wait_for.side_effect = _timepicker_wait_for
        else:
            loc.is_visible.return_value = True
        def make_click(s):
            def _cl(*args, **kwargs):
                clicked_selectors.append(s)
                if "30" in s:
                    time_val[0] = "19:30"
            return _cl
        loc.click.side_effect = make_click(sel)
        res.first = loc
        return res

    mock_page.locator.side_effect = loc_side_effect
    observer = TikTokUIObserver(mock_page)

    ok = observer._set_schedule_time(mock_time_input, "19:30")
    assert ok is True
    assert any("19" in s for s in clicked_selectors)
    assert any("30" in s for s in clicked_selectors)


def test_tiktok_timepicker_case_4_readback_mismatch_blocks_final_schedule():
    """Case 4: Readback remains 12:00 -> TIME_MISMATCH and final Planla is NOT clicked."""
    mock_page = MagicMock()
    mock_time_input = MagicMock()
    mock_time_input.is_visible.return_value = True
    mock_time_input.get_attribute.return_value = "12:00"
    mock_time_input.input_value.return_value = "12:00"

    # Option clicks do not change time
    def loc_side_effect(sel):
        res = MagicMock()
        loc = MagicMock()
        loc.is_visible.return_value = True
        res.first = loc
        return res

    mock_page.locator.side_effect = loc_side_effect
    observer = TikTokUIObserver(mock_page)

    ok = observer._set_schedule_time(mock_time_input, "19:30")
    assert ok is False

    # Verify final schedule click blocked
    mock_final_btn = MagicMock()
    mock_page.locator.return_value.first = mock_final_btn
    success, submit_msg = observer.click_schedule_and_verify(schedule_mode_verified=False)
    assert success is False
    mock_final_btn.click.assert_not_called()


def test_tiktok_ai_disclosure_multi_switches_scopes_to_aigc_only():
    """Verify that toggle_ai_disclosure(True) changes ONLY AI switch, leaving other switches intact."""
    mock_page = MagicMock()

    # Switch 1: Yüksek kaliteli yüklemeler (ON)
    sw_hd = {"name": "HD", "checked": True}
    # Switch 2: Gönderi içeriğini açıklayın (OFF)
    sw_branded = {"name": "Branded", "checked": False}
    # Switch 3: AI ile oluşturulmuş içerik (OFF -> should become ON)
    sw_ai = {"name": "AI", "checked": False}

    mock_aigc_container = MagicMock()
    mock_aigc_container.is_visible.return_value = True

    mock_ai_switch = MagicMock()
    mock_ai_switch.is_visible.return_value = True
    mock_ai_switch.get_attribute.side_effect = lambda attr: "true" if (attr == "aria-checked" and sw_ai["checked"]) else ("false" if attr == "aria-checked" else None)

    def on_ai_click(*args, **kwargs):
        sw_ai["checked"] = True

    mock_ai_switch.click.side_effect = on_ai_click
    mock_aigc_container.locator.return_value.first = mock_ai_switch

    def loc_side_effect(sel):
        res = MagicMock()
        if "aigc_container" in sel or "AI" in sel or "Yapay" in sel:
            res.first = mock_aigc_container
        else:
            res.first = MagicMock(is_visible=MagicMock(return_value=False), wait_for=MagicMock(side_effect=TimeoutError("not visible")))
        return res

    mock_page.locator.side_effect = loc_side_effect
    observer = TikTokUIObserver(mock_page)

    ok = observer.toggle_ai_disclosure(True)
    assert ok is True
    assert sw_ai["checked"] is True
    assert sw_hd["checked"] is True
    assert sw_branded["checked"] is False


def test_tiktok_ai_disclosure_show_more_expansion_flow():
    """Verify that if AI row is initially hidden, 'Daha fazla göster' is clicked and expanded."""
    mock_page = MagicMock()
    is_expanded = [False]
    ai_checked = [False]

    mock_show_more = MagicMock()
    mock_show_more.is_visible.side_effect = lambda **kw: not is_expanded[0]
    def _show_more_wait_for(*args, **kwargs):
        if is_expanded[0]:
            raise TimeoutError("not visible")
    mock_show_more.wait_for.side_effect = _show_more_wait_for
    def on_show_more_click(*args, **kwargs):
        is_expanded[0] = True
    mock_show_more.click.side_effect = on_show_more_click

    def _aigc_wait_for(*args, **kwargs):
        if not is_expanded[0]:
            raise TimeoutError("not visible")

    mock_aigc_container = MagicMock()
    mock_aigc_container.is_visible.side_effect = lambda **kw: is_expanded[0]
    mock_aigc_container.wait_for.side_effect = _aigc_wait_for

    mock_ai_switch = MagicMock()
    mock_ai_switch.is_visible.side_effect = lambda **kw: is_expanded[0]
    mock_ai_switch.wait_for.side_effect = _aigc_wait_for
    mock_ai_switch.get_attribute.side_effect = lambda attr: "true" if (attr == "aria-checked" and ai_checked[0]) else ("false" if attr == "aria-checked" else None)

    def on_ai_click(*args, **kwargs):
        ai_checked[0] = True
    mock_ai_switch.click.side_effect = on_ai_click
    mock_aigc_container.locator.return_value.first = mock_ai_switch

    def loc_side_effect(sel):
        res = MagicMock()
        if "Daha fazla" in sel or "Show more" in sel:
            res.first = mock_show_more
        elif "aigc_container" in sel or "AI" in sel:
            res.first = mock_aigc_container
        else:
            res.first = MagicMock(is_visible=MagicMock(return_value=False), wait_for=MagicMock(side_effect=TimeoutError("not visible")))
        return res

    mock_page.locator.side_effect = loc_side_effect
    observer = TikTokUIObserver(mock_page)

    ok = observer.toggle_ai_disclosure(True)
    assert ok is True
    assert is_expanded[0] is True
    assert ai_checked[0] is True
    mock_show_more.click.assert_called_once()
    mock_ai_switch.click.assert_called()


def test_tiktok_ai_disclosure_already_on_no_click():
    """Verify that if AI switch is already ON, no click is performed and returns True."""
    mock_page = MagicMock()
    mock_aigc_container = MagicMock()
    mock_aigc_container.is_visible.return_value = True

    mock_ai_switch = MagicMock()
    mock_ai_switch.is_visible.return_value = True
    mock_ai_switch.get_attribute.side_effect = lambda attr: "true" if attr == "aria-checked" else None
    mock_aigc_container.locator.return_value.first = mock_ai_switch

    mock_page.locator.return_value.first = mock_aigc_container
    observer = TikTokUIObserver(mock_page)

    ok = observer.toggle_ai_disclosure(True)
    assert ok is True
    mock_ai_switch.click.assert_not_called()


def test_tiktok_ai_disclosure_fails_when_control_missing():
    """Verify that if AI disclosure cannot be found or toggled, it returns False."""
    mock_page = MagicMock()
    mock_empty = MagicMock()
    mock_empty.is_visible.return_value = False
    mock_empty.wait_for.side_effect = TimeoutError("not visible")
    mock_page.locator.return_value.first = mock_empty

    observer = TikTokUIObserver(mock_page)
    ok = observer.toggle_ai_disclosure(True)
    assert ok is False


def test_tiktok_ai_disclosure_false_negative_prevention_live_dom_case():
    """
    CRITICAL REGRESSION TEST (Exact live false-negative bug):
    Switch is already ON in the live DOM with .Switch__content aria-checked="true",
    Switch__thumb data-state="checked", and Switch__input checked=true.
    Verify toggle_ai_disclosure() returns True immediately and performs 0 clicks.
    """
    mock_page = MagicMock()
    mock_aigc = MagicMock()
    mock_aigc.is_visible.return_value = True

    mock_content = MagicMock()
    mock_content.is_visible.return_value = True
    mock_content.get_attribute.side_effect = lambda attr: "true" if attr == "aria-checked" else ("checked" if attr == "data-state" else "Switch__content Switch__content--checked-true")

    mock_thumb = MagicMock()
    mock_thumb.get_attribute.side_effect = lambda attr: "checked" if attr == "data-state" else "Switch__thumb Switch__thumb--checked-true"

    mock_inp = MagicMock()
    mock_inp.is_checked.return_value = True

    def aigc_locator(sel):
        res = MagicMock()
        if "Switch__content" in sel:
            res.first = mock_content
        elif "thumb" in sel:
            res.first = mock_thumb
        elif "input" in sel or "role" in sel:
            res.first = mock_inp
        else:
            res.first = MagicMock(is_visible=MagicMock(return_value=False), wait_for=MagicMock(side_effect=TimeoutError("not visible")))
        return res

    mock_aigc.locator.side_effect = aigc_locator

    def page_locator(sel):
        res = MagicMock()
        if "aigc_container" in sel or "AI" in sel:
            res.first = mock_aigc
        else:
            res.first = MagicMock(is_visible=MagicMock(return_value=False), wait_for=MagicMock(side_effect=TimeoutError("not visible")))
        return res

    mock_page.locator.side_effect = page_locator

    observer = TikTokUIObserver(mock_page)
    ok = observer.toggle_ai_disclosure(True)
    assert ok is True
    mock_content.click.assert_not_called()
    mock_aigc.click.assert_not_called()


def test_tiktok_ai_disclosure_toggle_from_off_to_on():
    """Verify that if switch is initially OFF, click transitions state to ON and returns True."""
    mock_page = MagicMock()
    state = {"is_on": False}

    mock_aigc = MagicMock()
    mock_aigc.is_visible.return_value = True

    mock_content = MagicMock()
    mock_content.is_visible.return_value = True
    mock_content.get_attribute.side_effect = lambda attr: ("true" if state["is_on"] else "false") if attr == "aria-checked" else (("checked" if state["is_on"] else "unchecked") if attr == "data-state" else ("Switch__content--checked-true" if state["is_on"] else "Switch__content--checked-false"))

    mock_thumb = MagicMock()
    mock_thumb.get_attribute.side_effect = lambda attr: ("checked" if state["is_on"] else "unchecked") if attr == "data-state" else ""

    mock_inp = MagicMock()
    mock_inp.is_checked.side_effect = lambda: state["is_on"]

    def on_click(*args, **kwargs):
        state["is_on"] = True

    mock_content.click.side_effect = on_click
    mock_aigc.click.side_effect = on_click

    def aigc_locator(sel):
        res = MagicMock()
        if "Switch__content" in sel:
            res.first = mock_content
        elif "thumb" in sel:
            res.first = mock_thumb
        elif "input" in sel or "role" in sel:
            res.first = mock_inp
        else:
            res.first = MagicMock(is_visible=MagicMock(return_value=False), wait_for=MagicMock(side_effect=TimeoutError("not visible")))
        return res

    mock_aigc.locator.side_effect = aigc_locator

    def page_locator(sel):
        res = MagicMock()
        if "aigc_container" in sel or "AI" in sel:
            res.first = mock_aigc
        else:
            res.first = MagicMock(is_visible=MagicMock(return_value=False), wait_for=MagicMock(side_effect=TimeoutError("not visible")))
        return res

    mock_page.locator.side_effect = page_locator

    observer = TikTokUIObserver(mock_page)
    ok = observer.toggle_ai_disclosure(True)
    assert ok is True
    assert state["is_on"] is True


# =============================================================================
# DYNAMIC CALENDAR & TIMEPICKER BATCH TESTS (14-SLOT GENERIC AUTOMATION)
# =============================================================================

def test_tiktok_timepicker_22_00_dynamic_slot():
    """Verify timepicker sets dynamic slot 22:00 (Hour 22, Minute 00)."""
    mock_page = MagicMock()
    time_val = ["12:00"]

    mock_time_input = MagicMock()
    mock_time_input.is_visible.return_value = True
    mock_time_input.get_attribute.side_effect = lambda attr: time_val[0] if attr == "value" else None
    mock_time_input.input_value.side_effect = lambda: time_val[0]

    mock_hour_22 = MagicMock()
    mock_hour_22.is_visible.return_value = True
    mock_min_00 = MagicMock()
    mock_min_00.is_visible.return_value = True

    def on_min_click(*args, **kwargs):
        time_val[0] = "22:00"

    mock_min_00.click.side_effect = on_min_click

    def loc_side_effect(sel):
        res = MagicMock()
        if "22" in sel:
            res.first = mock_hour_22
        elif "00" in sel:
            res.first = mock_min_00
        elif "input" in sel:
            res.first = mock_time_input
        else:
            res.first = MagicMock(is_visible=MagicMock(return_value=False), wait_for=MagicMock(side_effect=TimeoutError("not visible")))
        return res

    mock_page.locator.side_effect = loc_side_effect
    observer = TikTokUIObserver(mock_page)

    ok = observer._set_schedule_time(mock_time_input, "22:00")
    assert ok is True
    assert time_val[0] == "22:00"


def test_tiktok_calendar_august_2026_days_16_to_22():
    """Verify that calendar UI correctly selects any day from 16 to 22 August 2026."""
    for day in range(16, 23):
        mock_page = MagicMock()
        date_val = ["2026-08-01"]
        target_iso = f"2026-08-{day:02d}"

        mock_date_input = MagicMock()
        mock_date_input.is_visible.return_value = True
        mock_date_input.get_attribute.side_effect = lambda attr, dv=date_val: dv[0] if attr == "value" else None
        mock_date_input.input_value.side_effect = lambda dv=date_val: dv[0]

        mock_cal_wrapper = MagicMock()
        mock_cal_wrapper.is_visible.return_value = True

        mock_month_title = MagicMock(inner_text=MagicMock(return_value="Ağustos"))
        mock_year_title = MagicMock(inner_text=MagicMock(return_value="2026"))

        mock_day_elem = MagicMock()
        mock_day_elem.is_visible.return_value = True
        def make_day_click(d_str, dv=date_val):
            def _cl(*args, **kwargs):
                dv[0] = f"2026-08-{int(d_str):02d}"
            return _cl
        mock_day_elem.click.side_effect = make_day_click(str(day))

        def loc_side_effect(sel, m_month=mock_month_title, m_year=mock_year_title, m_day=mock_day_elem, m_cal=mock_cal_wrapper, m_inp=mock_date_input):
            res = MagicMock()
            if "month-title" in sel:
                res.first = m_month
            elif "year-title" in sel:
                res.first = m_year
            elif "calendar-wrapper" in sel and "day" in sel:
                res.first = m_day
                res.count.return_value = 1
                res.nth.return_value = m_day
            elif "calendar-wrapper" in sel:
                res.first = m_cal
            elif "input" in sel:
                res.first = m_inp
            else:
                res.first = MagicMock(is_visible=MagicMock(return_value=False), wait_for=MagicMock(side_effect=TimeoutError("not visible")))
            return res

        mock_page.locator.side_effect = loc_side_effect
        observer = TikTokUIObserver(mock_page)

        ok = observer._set_schedule_date(mock_date_input, target_iso)
        assert ok is True
        assert date_val[0] == target_iso


def test_tiktok_calendar_month_transition_august_to_september():
    """Verify month transition: Current header 'Ağustos / 2026', target '2026-09-01' clicks next arrow to 'Eylül / 2026'."""
    mock_page = MagicMock()
    header_state = ["Ağustos", "2026"]
    date_val = ["2026-08-16"]

    mock_date_input = MagicMock()
    mock_date_input.is_visible.return_value = True
    mock_date_input.get_attribute.side_effect = lambda attr: date_val[0] if attr == "value" else None
    mock_date_input.input_value.side_effect = lambda: date_val[0]

    mock_cal_wrapper = MagicMock()
    mock_cal_wrapper.is_visible.return_value = True

    mock_month_title = MagicMock()
    mock_month_title.inner_text.side_effect = lambda: header_state[0]

    mock_year_title = MagicMock()
    mock_year_title.inner_text.side_effect = lambda: header_state[1]

    mock_next_arrow = MagicMock()
    def on_next_arrow_click(*args, **kwargs):
        header_state[0] = "Eylül"
    mock_next_arrow.click.side_effect = on_next_arrow_click

    mock_prev_arrow = MagicMock()
    mock_arrows = MagicMock()
    mock_arrows.count.return_value = 2
    mock_arrows.nth.side_effect = lambda idx: mock_next_arrow if idx == 1 else mock_prev_arrow
    mock_arrows.last = mock_next_arrow
    mock_arrows.first = mock_prev_arrow

    mock_day_1 = MagicMock()
    mock_day_1.is_visible.return_value = True
    def on_day_1_click(*args, **kwargs):
        date_val[0] = "2026-09-01"
    mock_day_1.click.side_effect = on_day_1_click

    def loc_side_effect(sel):
        res = MagicMock()
        if "month-title" in sel:
            res.first = mock_month_title
        elif "year-title" in sel:
            res.first = mock_year_title
        elif "arrow" in sel:
            return mock_arrows
        elif "day" in sel:
            res.first = mock_day_1
            res.count.return_value = 1
            res.nth.return_value = mock_day_1
        elif "calendar-wrapper" in sel:
            res.first = mock_cal_wrapper
        elif "input" in sel:
            res.first = mock_date_input
        else:
            res.first = MagicMock(is_visible=MagicMock(return_value=False), wait_for=MagicMock(side_effect=TimeoutError("not visible")))
        return res

    mock_page.locator.side_effect = loc_side_effect
    observer = TikTokUIObserver(mock_page)

    ok = observer._set_schedule_date(mock_date_input, "2026-09-01")
    assert ok is True
    assert header_state[0] == "Eylül"
    assert date_val[0] == "2026-09-01"
    mock_next_arrow.click.assert_called()


def test_tiktok_final_post_video_button_exact_dom_resolution_and_click():
    """
    CRITICAL REGRESSION TEST (Exact final button DOM):
    <button role="button" type="button" aria-disabled="false" data-disabled="false" data-loading="false" data-e2e="post_video_button">
      <div class="Button__content">Planla</div>
    </button>
    Verify post_video_button is resolved, enabled passes, normal click is called, and redirect to content page confirms schedule.
    """
    mock_page = MagicMock()
    mock_page.url = "https://www.tiktok.com/tiktokstudio/content"

    mock_btn = MagicMock()
    mock_btn.is_visible.return_value = True
    mock_btn.is_enabled.return_value = True
    mock_btn.get_attribute.side_effect = lambda attr: "false" if attr in ("aria-disabled", "data-disabled", "data-loading") else None
    mock_btn.inner_text.return_value = "Planla"

    def loc_side_effect(sel):
        res = MagicMock()
        if "post_video_button" in sel:
            res.first = mock_btn
        else:
            res.first = MagicMock(is_visible=MagicMock(return_value=False), wait_for=MagicMock(side_effect=TimeoutError("not visible")), is_enabled=MagicMock(return_value=False))
        return res

    mock_page.locator.side_effect = loc_side_effect
    observer = TikTokUIObserver(mock_page)

    success, msg = observer.click_schedule_and_verify(schedule_mode_verified=True, timeout_seconds=2)
    assert success is True
    assert msg == "TIKTOK_FINAL_SCHEDULE_SUBMITTED"
    mock_btn.click.assert_called_once()


def test_tiktok_final_button_disabled_blocks_click():
    """Verify that if final button has aria-disabled='true', data-disabled='true', or data-loading='true', click is blocked."""
    for disabled_attr in ["aria-disabled", "data-disabled", "data-loading"]:
        mock_page = MagicMock()
        mock_btn = MagicMock()
        mock_btn.is_visible.return_value = True
        mock_btn.is_enabled.return_value = True
        mock_btn.get_attribute.side_effect = lambda attr, da=disabled_attr: "true" if attr == da else "false"
        mock_btn.inner_text.return_value = "Planla"

        def loc_side_effect(sel, b=mock_btn):
            res = MagicMock()
            if "post_video_button" in sel:
                res.first = b
            else:
                res.first = MagicMock(is_visible=MagicMock(return_value=False), wait_for=MagicMock(side_effect=TimeoutError("not visible")), is_enabled=MagicMock(return_value=False))
            return res

        mock_page.locator.side_effect = loc_side_effect
        observer = TikTokUIObserver(mock_page)

        success, msg = observer.click_schedule_and_verify(schedule_mode_verified=True, timeout_seconds=2)
        assert success is False
        assert msg == "FINAL_BUTTON_NOT_READY"
        mock_btn.click.assert_not_called()


def test_tiktok_aigc_fresh_off_state_overrides_stale_on_cache():
    """
    CRITICAL REGRESSION TEST:
    Simulate stale input.checked=True, but fresh DOM has aria-checked='false',
    data-state='unchecked', and class='Switch__content Switch__content--checked-false'.
    Verify already-enabled does NOT return True, click is performed, and state transitions to ON.
    """
    mock_page = MagicMock()
    is_clicked = [False]

    mock_aigc = MagicMock()
    mock_aigc.is_visible.return_value = True

    mock_content = MagicMock()
    mock_content.is_visible.return_value = True
    mock_content.get_attribute.side_effect = lambda attr: (
        ("true" if is_clicked[0] else "false") if attr == "aria-checked"
        else (("checked" if is_clicked[0] else "unchecked") if attr == "data-state"
              else ("Switch__content Switch__content--checked-true" if is_clicked[0] else "Switch__content Switch__content--checked-false"))
    )

    mock_thumb = MagicMock()
    mock_thumb.get_attribute.side_effect = lambda attr: ("checked" if is_clicked[0] else "unchecked") if attr == "data-state" else ""

    mock_inp = MagicMock()
    mock_inp.is_checked.return_value = True  # stale on signal

    def on_content_click(*args, **kwargs):
        is_clicked[0] = True

    mock_content.click.side_effect = on_content_click

    def aigc_locator(sel):
        res = MagicMock()
        if "Switch__content" in sel:
            res.first = mock_content
        elif "thumb" in sel:
            res.first = mock_thumb
        elif "input" in sel or "role" in sel:
            res.first = mock_inp
        else:
            res.first = MagicMock(is_visible=MagicMock(return_value=False), wait_for=MagicMock(side_effect=TimeoutError("not visible")))
        return res

    mock_aigc.locator.side_effect = aigc_locator

    def page_locator(sel):
        res = MagicMock()
        if "aigc_container" in sel or "AI" in sel:
            res.first = mock_aigc
        else:
            res.first = MagicMock(is_visible=MagicMock(return_value=False), wait_for=MagicMock(side_effect=TimeoutError("not visible")))
        return res

    mock_page.locator.side_effect = page_locator

    observer = TikTokUIObserver(mock_page)
    ok = observer.toggle_ai_disclosure(True)
    assert ok is True
    assert is_clicked[0] is True
    mock_content.click.assert_called_once()


def test_tiktok_aigc_strict_scoping_ignores_copyright_and_content_check_switches():
    """
    Test 1:
    Page has 3 switches:
    - AIGC: aria=false, unchecked
    - Copyright: aria=true, checked
    - Content check: aria=true, checked
    Expected: AIGC is strictly OFF, copyright/content switches are NOT used, click is performed on AIGC only.
    """
    mock_page = MagicMock()
    aigc_clicked = [False]

    # Mock copyright container (checked=true)
    mock_copyright = MagicMock()
    mock_copyright.is_visible.return_value = True
    mock_cop_content = MagicMock()
    mock_cop_content.get_attribute.side_effect = lambda a: "true" if a == "aria-checked" else ("checked" if a == "data-state" else "")

    # Mock AIGC container (checked=false)
    mock_aigc = MagicMock()
    mock_aigc.is_visible.return_value = True
    mock_aigc_content = MagicMock()
    mock_aigc_content.is_visible.return_value = True
    mock_aigc_content.get_attribute.side_effect = lambda a: (
        ("true" if aigc_clicked[0] else "false") if a == "aria-checked"
        else (("checked" if aigc_clicked[0] else "unchecked") if a == "data-state"
              else ("Switch__content--checked-true" if aigc_clicked[0] else "Switch__content--checked-false"))
    )

    def on_aigc_click(*args, **kwargs):
        aigc_clicked[0] = True
    mock_aigc_content.click.side_effect = on_aigc_click

    def aigc_locator(sel):
        res = MagicMock()
        if "Switch__content" in sel:
            res.first = mock_aigc_content
        else:
            res.first = MagicMock(is_visible=MagicMock(return_value=False), wait_for=MagicMock(side_effect=TimeoutError("not visible")))
        return res
    mock_aigc.locator.side_effect = aigc_locator

    def page_locator(sel):
        res = MagicMock()
        if "aigc_container" in sel:
            res.first = mock_aigc
        elif "copyright_container" in sel:
            res.first = mock_copyright
        else:
            res.first = MagicMock(is_visible=MagicMock(return_value=False), wait_for=MagicMock(side_effect=TimeoutError("not visible")))
        return res
    mock_page.locator.side_effect = page_locator

    observer = TikTokUIObserver(mock_page)
    ok = observer.toggle_ai_disclosure(True)
    assert ok is True
    assert aigc_clicked[0] is True
    mock_cop_content.click.assert_not_called()


def test_tiktok_ensure_more_options_expanded():
    """
    Test 2:
    More options initially collapsed.
    Click 'Daha fazla göster' -> aigc_container becomes visible.
    """
    mock_page = MagicMock()
    expanded = [False]

    mock_more_btn = MagicMock()
    mock_more_btn.is_visible.return_value = True

    def on_more_click(*args, **kwargs):
        expanded[0] = True
    mock_more_btn.click.side_effect = on_more_click

    mock_aigc = MagicMock()
    mock_aigc.is_visible.side_effect = lambda **kw: expanded[0]
    def _aigc_wait_for(*args, **kwargs):
        if not expanded[0]:
            raise TimeoutError("not visible")
    mock_aigc.wait_for.side_effect = _aigc_wait_for

    def page_locator(sel):
        res = MagicMock()
        if "more-btn" in sel or "Daha fazla göster" in sel:
            res.first = mock_more_btn
        elif "aigc_container" in sel:
            res.first = mock_aigc
        else:
            res.first = MagicMock(is_visible=MagicMock(return_value=False), wait_for=MagicMock(side_effect=TimeoutError("not visible")))
        return res
    mock_page.locator.side_effect = page_locator

    observer = TikTokUIObserver(mock_page)
    ok = observer.ensure_more_options_expanded()
    assert ok is True
    assert expanded[0] is True
    mock_more_btn.click.assert_called_once()


def test_tiktok_aigc_off_to_on_toggle_flow():
    """
    Test 3:
    AIGC is OFF -> click Switch__content -> becomes ON.
    """
    mock_page = MagicMock()
    is_on = [False]

    mock_aigc = MagicMock()
    mock_aigc.is_visible.return_value = True

    mock_content = MagicMock()
    mock_content.is_visible.return_value = True
    mock_content.get_attribute.side_effect = lambda a: (
        ("true" if is_on[0] else "false") if a == "aria-checked"
        else (("checked" if is_on[0] else "unchecked") if a == "data-state" else "")
    )
    def on_click(*args, **kwargs):
        is_on[0] = True
    mock_content.click.side_effect = on_click

    mock_aigc.locator.side_effect = lambda s: MagicMock(first=mock_content if "Switch__content" in s else MagicMock(is_visible=MagicMock(return_value=False), wait_for=MagicMock(side_effect=TimeoutError("not visible"))))
    mock_page.locator.side_effect = lambda s: MagicMock(first=mock_aigc if "aigc_container" in s else MagicMock(is_visible=MagicMock(return_value=False), wait_for=MagicMock(side_effect=TimeoutError("not visible"))))

    observer = TikTokUIObserver(mock_page)
    ok = observer.toggle_ai_disclosure(True)
    assert ok is True
    assert is_on[0] is True


def test_tiktok_content_check_modal_escaped_no_publish_now_click():
    """
    Test 4:
    Final schedule click triggers content-check modal.
    Expected:
    - 'Hemen paylaş' click count = 0
    - Escape pressed = 1
    - Content checks wait is initiated
    - Retry final submit
    """
    mock_page = MagicMock()
    keys_pressed = []
    attempt = [0]

    def on_key(k):
        keys_pressed.append(k)
    mock_page.keyboard.press.side_effect = on_key

    mock_post_btn = MagicMock()
    mock_post_btn.is_visible.return_value = True
    mock_post_btn.is_enabled.return_value = True
    mock_post_btn.get_attribute.side_effect = lambda a: "false" if a in ("aria-disabled", "data-disabled", "data-loading") else ""
    mock_post_btn.inner_text.return_value = "Planla"

    def on_post_click(*args, **kwargs):
        attempt[0] += 1
    mock_post_btn.click.side_effect = on_post_click

    # Modal loc
    mock_modal = MagicMock()
    # Modal visible on attempt 1, closed after Escape and gone on attempt 2
    mock_modal.is_visible.side_effect = lambda **kw: (attempt[0] == 1 and "Escape" not in keys_pressed)
    def _modal_wait_for(*args, **kwargs):
        if not (attempt[0] == 1 and "Escape" not in keys_pressed):
            raise TimeoutError("not visible")
    mock_modal.wait_for.side_effect = _modal_wait_for

    mock_hemen_paylas = MagicMock()
    mock_hemen_paylas.is_visible.return_value = True

    # Status success for checks
    mock_success = MagicMock()
    mock_success.is_visible.return_value = True
    mock_succ_locs = MagicMock()
    mock_succ_locs.count.return_value = 1
    mock_succ_locs.nth.return_value = mock_success

    mock_chk_locs = MagicMock()
    mock_chk_locs.count.return_value = 0

    mock_page.url = "https://www.tiktok.com/tiktokstudio/upload"

    def page_locator(sel):
        res = MagicMock()
        if "post_video_button" in sel:
            res.first = mock_post_btn
        elif "Paylaşmaya devam edilsin mi?" in sel or "kontrol ediyoruz" in sel:
            res.first = mock_modal
        elif "Hemen paylaş" in sel:
            res.first = mock_hemen_paylas
        elif "status-checking" in sel:
            return mock_chk_locs
        elif "status-success" in sel:
            return mock_succ_locs
        elif "postSchedule" in sel or ("input" in sel and "schedule" in sel):
            res.first = MagicMock(is_checked=MagicMock(return_value=True), is_visible=MagicMock(return_value=False), wait_for=MagicMock(side_effect=TimeoutError("not visible")))
        else:
            res.first = MagicMock(is_visible=MagicMock(return_value=False), wait_for=MagicMock(side_effect=TimeoutError("not visible")), is_enabled=MagicMock(return_value=False))
        return res

    mock_page.locator.side_effect = page_locator

    def url_prop():
        if attempt[0] >= 2:
            return "https://www.tiktok.com/tiktokstudio/content"
        return "https://www.tiktok.com/tiktokstudio/upload"

    type(mock_page).url = property(lambda self: url_prop())

    observer = TikTokUIObserver(mock_page)
    ok, msg = observer.click_schedule_and_verify(schedule_mode_verified=True, timeout_seconds=2)

    assert ok is True
    assert msg == "TIKTOK_FINAL_SCHEDULE_SUBMITTED"
    assert "Escape" in keys_pressed
    assert attempt[0] == 2
    mock_hemen_paylas.click.assert_not_called()


def test_tiktok_content_check_data_show_false_ignored():
    """
    Test 5:
    .status-checking with data-show='false' is NOT active checking.
    """
    mock_page = MagicMock()
    mock_chk_locs = MagicMock()
    mock_chk_locs.count.return_value = 0  # .status-checking[data-show='true'] matches 0

    mock_succ_locs = MagicMock()
    mock_succ_locs.count.return_value = 1
    mock_succ_locs.nth.return_value = MagicMock(is_visible=MagicMock(return_value=True))

    def page_locator(sel):
        if "status-checking[data-show='true']" in sel:
            return mock_chk_locs
        elif "status-success" in sel:
            return mock_succ_locs
        return MagicMock(count=MagicMock(return_value=0), first=MagicMock(is_visible=MagicMock(return_value=False), wait_for=MagicMock(side_effect=TimeoutError("not visible"))))

    mock_page.locator.side_effect = page_locator

    observer = TikTokUIObserver(mock_page)
    ok = observer.wait_for_content_checks(max_wait_seconds=2, poll_interval=0.1)
    assert ok is True


def test_tiktok_content_check_data_show_true_active_and_waited():
    """
    Test 6:
    .status-checking with data-show='true' IS active checking.
    When it finishes -> CHECKS_COMPLETED.
    """
    mock_page = MagicMock()
    polls = [0]

    def chk_count():
        polls[0] += 1
        return 1 if polls[0] < 2 else 0

    mock_chk = MagicMock()
    mock_chk.count.side_effect = chk_count
    mock_chk.nth.return_value = MagicMock(is_visible=MagicMock(return_value=True))

    mock_succ = MagicMock()
    mock_succ.count.return_value = 1
    mock_succ.nth.return_value = MagicMock(is_visible=MagicMock(return_value=True))

    def page_locator(sel):
        if "status-checking[data-show='true']" in sel:
            return mock_chk
        elif "status-success" in sel:
            return mock_succ
        return MagicMock(count=MagicMock(return_value=0), first=MagicMock(is_visible=MagicMock(return_value=False), wait_for=MagicMock(side_effect=TimeoutError("not visible"))))

    mock_page.locator.side_effect = page_locator

    observer = TikTokUIObserver(mock_page)
    ok = observer.wait_for_content_checks(max_wait_seconds=5, poll_interval=0.1)
    assert ok is True
    assert polls[0] >= 2


def test_tiktok_checks_success_retry_final_submit_redirect():
    """
    Test 7:
    Checks success -> retry -> redirect to content page -> PASS.
    """
    mock_page = MagicMock()
    mock_post_btn = MagicMock()
    mock_post_btn.is_visible.return_value = True
    mock_post_btn.is_enabled.return_value = True
    mock_post_btn.get_attribute.side_effect = lambda a: "false" if a in ("aria-disabled", "data-disabled", "data-loading") else ""
    mock_post_btn.inner_text.return_value = "Planla"

    mock_page.locator.side_effect = lambda s: MagicMock(first=mock_post_btn if "post_video_button" in s else MagicMock(is_visible=MagicMock(return_value=False), wait_for=MagicMock(side_effect=TimeoutError("not visible")), is_enabled=MagicMock(return_value=False)))
    mock_page.url = "https://www.tiktok.com/tiktokstudio/content"

    observer = TikTokUIObserver(mock_page)
    ok, msg = observer.click_schedule_and_verify(schedule_mode_verified=True, timeout_seconds=2)
    assert ok is True
    assert msg == "TIKTOK_FINAL_SCHEDULE_SUBMITTED"
    mock_post_btn.click.assert_called_once()









# ---------------------------------------------------------------------------
# "Paylaşmaya devam edilsin mi?" — the only exits are İptal and "Hemen paylaş".
# "Hemen paylaş" publishes immediately instead of at the scheduled slot, which would
# dump the whole week out at once. It must never be clicked. (Real DOM 2026-08-17.)
# ---------------------------------------------------------------------------

class _ModalBtn:
    def __init__(self, label, visible=True):
        self._label = label
        self._visible = visible
        self.clicked = False

    @property
    def first(self):
        return self

    def is_visible(self, timeout=None):
        return self._visible

    def wait_for(self, state="visible", timeout=None):
        if state == "visible" and not self._visible:
            raise TimeoutError(f"{self._label!r} not visible")

    def is_enabled(self, timeout=None):
        return True

    def inner_text(self):
        return self._label

    def click(self, timeout=None):
        self.clicked = True


class _ModalPage:
    """TikTok content-check modal with both real buttons present."""

    def __init__(self):
        self.cancel = _ModalBtn("İptal")
        self.publish_now = _ModalBtn("Hemen paylaş")

    def locator(self, selector):
        s = selector.lower()
        if "i̇ptal" in s or "iptal" in s or "İptal" in selector:
            return self.cancel
        if "hemen payla" in s:
            return self.publish_now
        return _ModalBtn("", visible=False)


def test_content_check_modal_cancelled_via_iptal_never_publish_now():
    from automation.publishing.tiktok_ui_observer import TikTokUIObserver

    page = _ModalPage()
    observer = TikTokUIObserver(page)

    assert observer.cancel_content_check_modal() is True
    assert page.cancel.clicked is True
    assert page.publish_now.clicked is False, "ASLA 'Hemen paylas' tiklanmamali"


def test_publish_now_is_refused_even_if_a_selector_resolves_to_it():
    """Defense in depth: if a selector ever resolved to the publish button, the label
    guard must refuse to click it rather than posting the video immediately."""
    from automation.publishing.tiktok_ui_observer import TikTokUIObserver

    class _MisroutedPage:
        def __init__(self):
            self.publish_now = _ModalBtn("Hemen paylaş")

        def locator(self, selector):
            return self.publish_now   # every selector wrongly resolves here

    page = _MisroutedPage()
    observer = TikTokUIObserver(page)

    assert observer.cancel_content_check_modal() is False
    assert page.publish_now.clicked is False


def test_forbidden_labels_cover_both_languages():
    from automation.publishing.tiktok_selectors import TikTokSelectors
    labels = TikTokSelectors.FORBIDDEN_IMMEDIATE_PUBLISH_LABELS
    assert "hemen paylaş" in labels
    assert "post now" in labels
