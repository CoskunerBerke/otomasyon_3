"""
Unit tests for YouTube Studio Web UI CDP automation, selectors, observer, and publisher.
"""
from pathlib import Path
from unittest.mock import MagicMock

from automation.publishing.models import Platform, PlatformPublicationStatus, PublishRecord
from automation.publishing.config import PublishingConfig
from automation.publishing.youtube_studio_selectors import YouTubeStudioSelectors
from automation.publishing.youtube_studio_browser import YouTubeStudioBrowserManager
from automation.publishing.youtube_studio_ui_observer import YouTubeStudioUIObserver
from automation.publishing.youtube_studio_publisher import YouTubeStudioPublisher, MockYouTubeStudioPublisher

def test_youtube_studio_selectors_multilingual_defined():
    assert len(YouTubeStudioSelectors.CREATE_BUTTONS) >= 2
    assert any("Create" in s or "Oluştur" in s for s in YouTubeStudioSelectors.CREATE_BUTTONS)
    assert any("Upload" in s or "yükle" in s for s in YouTubeStudioSelectors.UPLOAD_MENU_ITEMS)
    assert any("Schedule" in s or "Planla" in s for s in YouTubeStudioSelectors.SCHEDULE_RADIO_BUTTONS)
    assert any("Done" in s or "Schedule" in s or "Planla" in s or "done" in s for s in YouTubeStudioSelectors.SUBMIT_SCHEDULE_BUTTONS)

def test_youtube_studio_browser_manager_profile_and_port():
    mgr = YouTubeStudioBrowserManager(debug_port=9224)
    assert mgr.debug_port == 9224
    assert "youtube-studio-profile" in str(mgr.profile_dir)

def test_youtube_studio_ui_observer_channel_verification_pass_and_mismatch():
    mock_page = MagicMock()
    mock_page.url = "https://studio.youtube.com/channel/UCahsmsqzTCtwTDDtvCurtBA"
    
    # 1. URL match
    observer = YouTubeStudioUIObserver(mock_page)
    is_match, info, msg = observer.verify_logged_in_channel(
        expected_handle="@BuiIdVerse",
        expected_channel_id="UCahsmsqzTCtwTDDtvCurtBA"
    )
    assert is_match is True
    assert "Verified" in msg

    # 2. Text header match
    mock_page.url = "https://studio.youtube.com/"
    mock_locator = MagicMock()
    mock_locator.first.is_visible.return_value = True
    mock_locator.first.inner_text.return_value = "BuildVerse Official"
    mock_page.locator.return_value = mock_locator

    is_match_txt, info_txt, msg_txt = observer.verify_logged_in_channel(
        expected_handle="@BuiIdVerse",
        expected_channel_id="UCahsmsqzTCtwTDDtvCurtBA"
    )
    assert is_match_txt is True
    assert "Verified" in msg_txt

    # 3. Account mismatch
    mock_locator.first.inner_text.return_value = "Random Gaming Hub"
    is_match_bad, info_bad, msg_bad = observer.verify_logged_in_channel(
        expected_handle="@BuiIdVerse",
        expected_channel_id="UCahsmsqzTCtwTDDtvCurtBA"
    )
    assert is_match_bad is False
    assert "ACCOUNT_MISMATCH" in msg_bad

def test_mock_youtube_studio_publisher_success_and_mismatch(tmp_path: Path):
    dummy_video = tmp_path / "test_video.mp4"
    dummy_video.write_bytes(b"mock video data" * 50)

    record = PublishRecord(
        publish_id="PUB-REEL-2026-0020-YOUTUBE",
        batch_id="PUB-BATCH-01",
        reel_id="REEL-2026-0020",
        platform=Platform.YOUTUBE,
        account_handle="@BuiIdVerse",
        video_file=dummy_video,
        video_sha256="hash123",
        title="Modern Villa Build in 30 Seconds",
        description="Step by step villa construction.",
        hashtags=["#Shorts", "#Architecture"],
        scheduled_at_local="2026-08-16T19:30:00+03:00",
        scheduled_at_utc="2026-08-16T16:30:00Z"
    )

    # Success case
    pub = MockYouTubeStudioPublisher(simulate_mismatch=False, expected_handle="@BuiIdVerse")
    res = pub.upload_and_schedule(record)
    assert res.status == PlatformPublicationStatus.SCHEDULED
    assert "studio.youtube.com" in res.remote_url

    # Mismatch case
    record.status = PlatformPublicationStatus.METADATA_READY
    pub_bad = MockYouTubeStudioPublisher(simulate_mismatch=True, expected_handle="@BuiIdVerse")
    res_bad = pub_bad.upload_and_schedule(record)
    assert res_bad.status == PlatformPublicationStatus.ACCOUNT_MISMATCH
    assert "ACCOUNT_MISMATCH" in res_bad.last_error

def test_youtube_studio_planlayin_and_schedule_accordion_detection():
    # Verify Turkish 'Planlayın' and English 'Schedule' card selectors
    headers = YouTubeStudioSelectors.SCHEDULE_ACCORDION_HEADERS
    assert any("Planlayın" in h for h in headers)
    assert any("Schedule" in h for h in headers)

    mock_page = MagicMock()
    mock_header = MagicMock()
    mock_header.is_visible.return_value = True
    
    mock_date_hidden = MagicMock()
    mock_date_hidden.is_visible.return_value = False
    mock_date_hidden.wait_for.side_effect = TimeoutError("not visible")

    # Mock tabs so detect_current_wizard_step returns VISIBILITY
    visibility_tab = MagicMock()
    visibility_tab.get_attribute.return_value = "true"
    visibility_tab.inner_text.return_value = "Görünürlük"
    tabs_locator = MagicMock()
    tabs_locator.count.return_value = 1
    tabs_locator.nth = lambda i: visibility_tab

    # detect_current_wizard_step() scopes its queries to the resolved active
    # ytcp-uploads-dialog, so that locator must also route through this same
    # selector logic (not just mock_page.locator) for the VISIBILITY tab to
    # be found.
    mock_dialog = MagicMock()
    mock_dialog.is_visible.return_value = True
    mock_dialog.count.return_value = 1
    mock_dialog.first = mock_dialog
    mock_dialog.nth.return_value = mock_dialog
    mock_dialog.get_attribute.return_value = ""

    def locator_side_effect(sel):
        if "ytcp-uploads-dialog" in sel:
            return mock_dialog
        if sel == "tp-yt-paper-tab":
            return tabs_locator
        res = MagicMock()
        if sel in YouTubeStudioSelectors.SCHEDULE_ACCORDION_HEADERS:
            res.first = mock_header
        else:
            res.first = mock_date_hidden
        return res

    mock_page.locator.side_effect = locator_side_effect
    mock_dialog.locator.side_effect = locator_side_effect

    observer = YouTubeStudioUIObserver(mock_page)
    expanded = observer.find_and_expand_schedule_card()
    assert expanded is True
    mock_header.click.assert_called()

def test_youtube_studio_date_and_time_picker_interaction():
    date_inputs = YouTubeStudioSelectors.DATE_PICKER_INPUTS
    time_inputs = YouTubeStudioSelectors.TIME_PICKER_INPUTS
    assert any("Tarih" in d or "date" in d.lower() for d in date_inputs)
    assert any("Saat" in t or "time" in t.lower() for t in time_inputs)

    mock_page = MagicMock()
    
    mock_header = MagicMock()
    mock_header.is_visible.return_value = True
    mock_header.inner_text.return_value = "AĞU 2026"

    mock_day = MagicMock()
    mock_day.inner_text.return_value = "16"
    mock_days = MagicMock()
    mock_days.count.return_value = 1
    mock_days.nth.return_value = mock_day

    mock_hidden = MagicMock()
    mock_hidden.is_visible.return_value = False
    mock_hidden.wait_for.side_effect = TimeoutError("not visible")

    def locator_side_effect(sel):
        res = MagicMock()
        if any(err_tok in sel for err_tok in ("Geçersiz", "Invalid", "invalid", "error", "Gelecekte", "future", "dialog", "calendar")):
            res.first = mock_hidden
        elif any(h in sel for h in ("month-header", "month-title", "h2")):
            res.first = mock_header
        elif "16" in sel:
            return mock_days
        else:
            loc = MagicMock()
            loc.is_visible.return_value = True
            loc.input_value.return_value = "19:30"
            loc.inner_text.return_value = "16 Ağu 2026"
            res.first = loc
        return res

    mock_page.locator.side_effect = locator_side_effect

    observer = YouTubeStudioUIObserver(mock_page)
    res = observer.set_schedule_datetime("2026-08-16T19:30:00+03:00")
    assert res is True

def test_youtube_studio_existing_draft_detection_and_resume():
    mock_page = MagicMock()
    mock_page.url = "https://studio.youtube.com/channel/UCahsmsqzTCtwTDDtvCurtBA/videos/upload"

    # Simulate finding video in draft row
    mock_row = MagicMock()
    mock_row.inner_text.return_value = "How Desert Oasis Palace Comes to Life in 30 Seconds - Taslak"
    mock_edit_btn = MagicMock()
    mock_edit_btn.count.return_value = 1
    mock_row.locator.return_value.first = mock_edit_btn

    mock_rows = MagicMock()
    mock_rows.count.return_value = 1
    mock_rows.nth.return_value = mock_row
    mock_page.locator.return_value = mock_rows

    observer = YouTubeStudioUIObserver(mock_page)
    found = observer.find_and_open_existing_draft(
        target_title="How Desert Oasis Palace Comes to Life in 30 Seconds",
        reel_id="REEL-2026-0003"
    )
    assert found is True
    mock_edit_btn.click.assert_called_once()

def test_youtube_studio_hard_upload_guard_in_resume_state(tmp_path: Path):
    from automation.publishing.config import load_publishing_config
    dummy_video = tmp_path / "vid.mp4"
    dummy_video.write_bytes(b"mock mp4")

    # Record in SCHEDULE_RESUME_REQUIRED mode
    record = PublishRecord(
        publish_id="PUB-REEL-2026-0003-YOUTUBE",
        batch_id="PUB-BATCH-01",
        reel_id="REEL-2026-0003",
        platform=Platform.YOUTUBE,
        account_handle="@BuiIdVerse",
        video_file=dummy_video,
        video_sha256="hash123",
        title="Desert Oasis Palace",
        description="Desert Oasis Palace description",
        hashtags=["#Shorts"],
        scheduled_at_local="2026-08-16T19:30:00+03:00",
        scheduled_at_utc="2026-08-16T16:30:00Z",
        status=PlatformPublicationStatus.SCHEDULE_RESUME_REQUIRED
    )

    cfg = load_publishing_config(base_dir=tmp_path)
    pub = YouTubeStudioPublisher(config=cfg)

    # Mock browser connection & observer
    mock_page = MagicMock()
    mock_observer = MagicMock()
    mock_observer.is_logged_in.return_value = True
    mock_observer.verify_logged_in_channel.return_value = (True, "@BuiIdVerse", "OK")
    # Draft is not found
    mock_observer.find_and_open_existing_draft.return_value = False

    pub.browser_mgr = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.pages = [mock_page]
    pub.browser_mgr.connect.return_value.__enter__.return_value = (MagicMock(), mock_ctx)

    # Call upload_and_schedule with mock observer
    import automation.publishing.youtube_studio_publisher as ysp
    orig_observer_cls = ysp.YouTubeStudioUIObserver
    ysp.YouTubeStudioUIObserver = lambda p: mock_observer
    try:
        res = pub.upload_and_schedule(record)
        # Verify that upload_file was NEVER called
        assert mock_observer.upload_file.call_count == 0
        assert res.status == PlatformPublicationStatus.SCHEDULE_RESUME_REQUIRED
        assert "HARD UPLOAD GUARD" in res.last_error
    finally:
        ysp.YouTubeStudioUIObserver = orig_observer_cls

def test_youtube_studio_multiple_matching_drafts_diagnostic():
    mock_page = MagicMock()
    mock_page.url = "https://studio.youtube.com/channel/UCahsmsqzTCtwTDDtvCurtBA/videos/upload"

    row1 = MagicMock()
    row1.inner_text.return_value = "How Desert Oasis Palace Comes to Life in 30 Seconds - Draft 1"
    row1.locator.return_value.first.count.return_value = 1
    row1.locator.return_value.first.get_attribute.return_value = "/video/id_001/edit"

    row2 = MagicMock()
    row2.inner_text.return_value = "How Desert Oasis Palace Comes to Life in 30 Seconds - Draft 2"
    row2.locator.return_value.first.count.return_value = 1
    row2.locator.return_value.first.get_attribute.return_value = "/video/id_002/edit"

    mock_rows = MagicMock()
    mock_rows.count.return_value = 2
    mock_rows.nth.side_effect = lambda i: row1 if i == 0 else row2
    mock_page.locator.return_value = mock_rows

    observer = YouTubeStudioUIObserver(mock_page)
    matches = observer.find_matching_drafts(
        target_title="How Desert Oasis Palace Comes to Life in 30 Seconds",
        reel_id="REEL-2026-0003"
    )
    assert len(matches) == 2
    assert matches[0]["video_id"] == "id_001"
    assert matches[1]["video_id"] == "id_002"

def test_youtube_studio_calendar_august_2026_navigation_and_day_16():
    mock_page = MagicMock()
    
    # Simulate calendar header showing 'TEM 2026' (July), then clicking next to 'AĞU 2026' (August)
    headers = ["TEM 2026", "AĞU 2026"]
    header_idx = {"val": 0}

    mock_header_loc = MagicMock()
    mock_header_loc.is_visible.return_value = True
    def header_text():
        txt = headers[min(header_idx["val"], len(headers)-1)]
        return txt
    mock_header_loc.inner_text.side_effect = header_text

    mock_next_btn = MagicMock()
    mock_next_btn.is_visible.return_value = True
    def on_next_click():
        header_idx["val"] += 1
    mock_next_btn.click.side_effect = on_next_click

    mock_day_16 = MagicMock()
    mock_day_16.inner_text.return_value = "16"

    mock_days = MagicMock()
    mock_days.count.return_value = 1
    mock_days.nth.return_value = mock_day_16

    def locator_side_effect(sel):
        res = MagicMock()
        if any(h in sel for h in ("month-header", "month-title", "h2")):
            res.first = mock_header_loc
        elif "next-month" in sel or "Sonraki" in sel or "Next" in sel:
            res.first = mock_next_btn
        elif "16" in sel:
            return mock_days
        else:
            loc = MagicMock()
            loc.is_visible.return_value = True
            res.first = loc
        return res

    mock_page.locator.side_effect = locator_side_effect

    observer = YouTubeStudioUIObserver(mock_page)
    success = observer.select_calendar_date(target_year=2026, target_month=8, target_day=16)
    assert success is True
    mock_next_btn.click.assert_called()
    mock_day_16.click.assert_called()

def test_youtube_studio_invalid_date_error_blocks_schedule_click():
    mock_page = MagicMock()

    # Simulate 'Geçersiz Tarih' error visible on page
    mock_err_loc = MagicMock()
    mock_err_loc.is_visible.return_value = True
    mock_err_loc.inner_text.return_value = "Geçersiz Tarih"

    mock_submit_btn = MagicMock()
    mock_submit_btn.is_visible.return_value = True
    mock_submit_btn.is_enabled.return_value = True

    def locator_side_effect(sel):
        res = MagicMock()
        if "Geçersiz Tarih" in sel or "Invalid date" in sel or "invalid" in sel:
            res.first = mock_err_loc
        elif "done-button" in sel or "Planla" in sel or "Schedule" in sel:
            res.first = mock_submit_btn
        else:
            loc = MagicMock()
            loc.is_visible.return_value = False
            loc.wait_for.side_effect = TimeoutError("not visible")
            res.first = loc
        return res

    mock_page.locator.side_effect = locator_side_effect

    observer = YouTubeStudioUIObserver(mock_page)
    # Check validate date input returns False
    is_valid, msg = observer.validate_date_input()
    assert is_valid is False
    assert "Geçersiz Tarih" in msg

    # Click schedule should abort and NEVER click submit button
    sched_success, sched_msg = observer.click_schedule_and_verify()
    assert sched_success is False
    assert "Date is invalid" in sched_msg
    mock_submit_btn.click.assert_not_called()

def test_weekday_labels_never_detected_as_month_header():
    mock_page = MagicMock()
    observer = YouTubeStudioUIObserver(mock_page)

    # Weekday row in Turkish
    y, m = observer.parse_calendar_month_year("P\nS\nÇ\nP\nC\nC\nP")
    assert y == 0 and m == 0

    # Weekday row in English
    y_en, m_en = observer.parse_calendar_month_year("M T W T F S S")
    assert y_en == 0 and m_en == 0

    # Valid Turkish month header
    y_tr, m_tr = observer.parse_calendar_month_year("AĞU 2026")
    assert y_tr == 2026 and m_tr == 8

    # Valid English month header
    y_aug, m_aug = observer.parse_calendar_month_year("August 2026")
    assert y_aug == 2026 and m_aug == 8

def test_remote_video_id_captured_from_link_at_upload():
    mock_page = MagicMock()
    mock_page.url = "https://studio.youtube.com/channel/UCahsmsqzTCtwTDDtvCurtBA/videos/upload"

    mock_link = MagicMock()
    mock_link.is_visible.return_value = True
    mock_link.get_attribute.return_value = "https://youtu.be/dQw4w9WgXcQ"

    mock_page.locator.return_value.first = mock_link

    observer = YouTubeStudioUIObserver(mock_page)
    v_id, v_url = observer.capture_video_id_and_url()

    assert v_id == "dQw4w9WgXcQ"
    assert "youtu.be" in v_url

def test_exact_remote_video_resume_bypasses_upload(tmp_path: Path):
    from automation.publishing.config import load_publishing_config
    dummy_video = tmp_path / "v3_vid.mp4"
    dummy_video.write_bytes(b"mock mp4 30s")

    record = PublishRecord(
        publish_id="PUB-REEL-2026-0010-YOUTUBE",
        batch_id="PUB-BATCH-01",
        reel_id="REEL-2026-0010",
        platform=Platform.YOUTUBE,
        account_handle="@BuiIdVerse",
        video_file=dummy_video,
        video_sha256="hash123",
        title="Japanese Zen Temple",
        description="Zen temple description",
        hashtags=["#Shorts"],
        scheduled_at_local="2026-08-16T19:30:00+03:00",
        scheduled_at_utc="2026-08-16T16:30:00Z",
        remote_id="dQw4w9WgXcQ",
        remote_url="https://youtube.com/shorts/dQw4w9WgXcQ",
        status=PlatformPublicationStatus.UPLOADED_DRAFT
    )

    cfg = load_publishing_config(base_dir=tmp_path)
    pub = YouTubeStudioPublisher(config=cfg)

    mock_page = MagicMock()
    mock_observer = MagicMock()
    mock_observer.is_logged_in.return_value = True
    mock_observer.verify_logged_in_channel.return_value = (True, "@BuiIdVerse", "OK")
    mock_observer.open_exact_remote_video.return_value = True
    mock_observer.enter_existing_draft_wizard.return_value = True
    mock_observer.set_audience.return_value = (True, "AUDIENCE_VERIFIED")
    mock_observer.advance_wizard_to_visibility.return_value = (True, "VISIBILITY_READY")
    mock_observer.find_and_expand_schedule_card.return_value = True
    mock_observer.set_schedule_datetime.return_value = True
    mock_observer.click_schedule_and_verify.return_value = (True, "confirmed")
    mock_observer.verify_remote_scheduled_status.return_value = (True, "SCHEDULED")

    pub.browser_mgr = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.pages = [mock_page]
    pub.browser_mgr.connect.return_value.__enter__.return_value = (MagicMock(), mock_ctx)

    import automation.publishing.youtube_studio_publisher as ysp
    orig_observer_cls = ysp.YouTubeStudioUIObserver
    ysp.YouTubeStudioUIObserver = lambda p: mock_observer
    try:
        res = pub.upload_and_schedule(record)
        # Verify that upload_file was NEVER called
        assert mock_observer.upload_file.call_count == 0
        # Verify that open_exact_remote_video was called with dQw4w9WgXcQ
        mock_observer.open_exact_remote_video.assert_called_once_with("dQw4w9WgXcQ")
        assert res.status == PlatformPublicationStatus.SCHEDULED
    finally:
        ysp.YouTubeStudioUIObserver = orig_observer_cls

def test_remote_id_rR_uNcTLZuM_prevents_upload(tmp_path: Path):
    from automation.publishing.config import load_publishing_config
    dummy_video = tmp_path / "v3_vid.mp4"
    dummy_video.write_bytes(b"mock mp4 30s")

    record = PublishRecord(
        publish_id="PUB-REEL-2026-0010-YOUTUBE",
        batch_id="PUB-BATCH-01",
        reel_id="REEL-2026-0010",
        platform=Platform.YOUTUBE,
        account_handle="@BuiIdVerse",
        video_file=dummy_video,
        video_sha256="hash123",
        title="Japanese Zen Temple",
        description="Zen temple description",
        hashtags=["#Shorts"],
        scheduled_at_local="2026-08-16T19:30:00+03:00",
        scheduled_at_utc="2026-08-16T16:30:00Z",
        remote_id="rR_uNcTLZuM",
        remote_url="https://youtube.com/shorts/rR_uNcTLZuM",
        status=PlatformPublicationStatus.SCHEDULE_RESUME_REQUIRED
    )

    cfg = load_publishing_config(base_dir=tmp_path)
    pub = YouTubeStudioPublisher(config=cfg)

    mock_page = MagicMock()
    mock_observer = MagicMock()
    mock_observer.is_logged_in.return_value = True
    mock_observer.verify_logged_in_channel.return_value = (True, "@BuiIdVerse", "OK")
    mock_observer.open_exact_remote_video.return_value = True
    mock_observer.enter_existing_draft_wizard.return_value = True
    mock_observer.set_audience.return_value = (True, "AUDIENCE_VERIFIED")
    mock_observer.advance_wizard_to_visibility.return_value = (True, "VISIBILITY_READY")
    mock_observer.find_and_expand_schedule_card.return_value = True
    mock_observer.set_schedule_datetime.return_value = True
    mock_observer.click_schedule_and_verify.return_value = (True, "confirmed")
    mock_observer.verify_remote_scheduled_status.return_value = (True, "SCHEDULED")

    pub.browser_mgr = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.pages = [mock_page]
    pub.browser_mgr.connect.return_value.__enter__.return_value = (MagicMock(), mock_ctx)

    import automation.publishing.youtube_studio_publisher as ysp
    orig_observer_cls = ysp.YouTubeStudioUIObserver
    ysp.YouTubeStudioUIObserver = lambda p: mock_observer
    try:
        res = pub.upload_and_schedule(record)
        # Verify that upload_file was NEVER called
        assert mock_observer.upload_file.call_count == 0
        # Verify that open_exact_remote_video was called with rR_uNcTLZuM
        mock_observer.open_exact_remote_video.assert_called_once_with("rR_uNcTLZuM")
        assert res.status == PlatformPublicationStatus.SCHEDULED
    finally:
        ysp.YouTubeStudioUIObserver = orig_observer_cls

def test_time_field_00_00_causes_time_mismatch():
    mock_page = MagicMock()
    mock_loc = MagicMock()
    mock_loc.is_visible.return_value = True
    # Simulate UI remaining 00:00
    mock_loc.input_value.return_value = "00:00"
    mock_page.locator.return_value.first = mock_loc

    observer = YouTubeStudioUIObserver(mock_page)
    ok, msg = observer.set_schedule_time_exact("19:30")
    assert ok is False
    assert "TIME_MISMATCH" in msg

def test_exact_19_30_time_setter_and_readback():
    mock_page = MagicMock()
    mock_loc = MagicMock()
    mock_loc.is_visible.return_value = True
    # Simulate UI successfully changing to 19:30
    mock_loc.input_value.return_value = "19:30"
    mock_page.locator.return_value.first = mock_loc

    observer = YouTubeStudioUIObserver(mock_page)
    ok, msg = observer.set_schedule_time_exact("19:30")
    assert ok is True
    assert msg == "TIME_MATCH"
    mock_page.keyboard.type.assert_called_with("19:30")

def test_disabled_planla_button_prevents_click_and_fails_safely():
    mock_page = MagicMock()

    # Valid date and time inputs
    mock_valid_loc = MagicMock()
    mock_valid_loc.is_visible.return_value = False
    mock_valid_loc.wait_for.side_effect = TimeoutError("not visible")

    # Disabled Planla button
    mock_disabled_btn = MagicMock()
    mock_disabled_btn.is_visible.return_value = True
    mock_disabled_btn.is_enabled.return_value = False

    def locator_side_effect(sel):
        res = MagicMock()
        if "Geçersiz" in sel or "Invalid" in sel:
            res.first = mock_valid_loc
        elif "done-button" in sel or "Planla" in sel or "Schedule" in sel:
            res.first = mock_disabled_btn
        else:
            loc = MagicMock()
            loc.is_visible.return_value = False
            loc.wait_for.side_effect = TimeoutError("not visible")
            res.first = loc
        return res

    mock_page.locator.side_effect = locator_side_effect

    observer = YouTubeStudioUIObserver(mock_page)
    success, msg = observer.click_schedule_and_verify(timeout_seconds=2, wait_processing_seconds=1)
    assert success is False
    assert "FINAL_SCHEDULE_BUTTON_DISABLED" in msg
    mock_disabled_btn.click.assert_not_called()

def test_true_remote_scheduled_verification():
    mock_page = MagicMock()
    mock_page.url = "https://studio.youtube.com/channel/UCahsmsqzTCtwTDDtvCurtBA/videos/upload"

    # Row 1: Shows Planlandı with 16 Ağu 2026 and 19:30
    mock_row = MagicMock()
    mock_row.inner_text.return_value = "Japanese Zen Temple Transformation - rR_uNcTLZuM - Planlandı - 16 Ağu 2026, 19:30"
    
    mock_rows = MagicMock()
    mock_rows.count.return_value = 1
    mock_rows.nth.return_value = mock_row
    mock_page.locator.return_value = mock_rows

    observer = YouTubeStudioUIObserver(mock_page)
    is_ok, msg = observer.verify_remote_scheduled_status(
        remote_id="rR_uNcTLZuM",
        target_title="Japanese Zen Temple",
        expected_date_str="16.08.2026",
        expected_time_str="19:30"
    )
    assert is_ok is True
    assert msg == "SCHEDULED"

def test_resolve_paper_input_by_aria_labelledby_dynamic():
    mock_page = MagicMock()
    
    mock_input = MagicMock()
    mock_input.get_attribute.return_value = "paper-input-label-99"
    mock_inputs = MagicMock()
    mock_inputs.count.return_value = 1
    mock_inputs.nth.return_value = mock_input

    mock_label = MagicMock()
    mock_label.count.return_value = 1
    mock_label.inner_text.return_value = "Saat"
    mock_label.text_content.return_value = "Saat"

    def loc_side_effect(sel):
        if "paper-input-label-99" in sel:
            res = MagicMock()
            res.first = mock_label
            return res
        elif "tp-yt-paper-input" in sel or "aria-labelledby" in sel or sel.startswith("input"):
            return mock_inputs
        return MagicMock()

    mock_page.locator.side_effect = loc_side_effect

    observer = YouTubeStudioUIObserver(mock_page)
    resolved = observer.resolve_paper_input_by_label(["Saat", "Time"])
    assert resolved == mock_input

def test_resolve_time_input_via_schedule_card_pattern():
    mock_page = MagicMock()
    mock_empty_inputs = MagicMock()
    mock_empty_inputs.count.return_value = 0

    mock_container = MagicMock()
    mock_container.is_visible.return_value = True

    mock_time_cand = MagicMock()
    mock_time_cand.input_value.return_value = "00:00"

    mock_cand_inputs = MagicMock()
    mock_cand_inputs.count.return_value = 1
    mock_cand_inputs.nth.return_value = mock_time_cand

    mock_container.locator.return_value = mock_cand_inputs

    def loc_side_effect(sel):
        if "aria-labelledby" in sel:
            return mock_empty_inputs
        elif "#schedule-section" in sel or "#schedule-card" in sel:
            res = MagicMock()
            res.first = mock_container
            return res
        return MagicMock()

    mock_page.locator.side_effect = loc_side_effect

    observer = YouTubeStudioUIObserver(mock_page)
    resolved = observer.resolve_paper_input_by_label(["Saat", "Time"])
    assert resolved == mock_time_cand

def test_audience_set_not_made_for_kids_strict_verification():
    mock_page = MagicMock()
    mock_no_radio = MagicMock()
    mock_no_radio.is_visible.return_value = True
    mock_no_radio.get_attribute.side_effect = lambda attr: "true" if attr == "aria-checked" else None

    mock_yes_radio = MagicMock()
    mock_yes_radio.is_visible.return_value = True
    mock_yes_radio.get_attribute.side_effect = lambda attr: "false" if attr == "aria-checked" else None

    def loc_side_effect(sel):
        res = MagicMock()
        if "NOT_MFK" in sel or "Hayır" in sel or "No" in sel:
            res.first = mock_no_radio
        elif "MFK" in sel or "Evet" in sel or "Yes" in sel:
            res.first = mock_yes_radio
        else:
            loc = MagicMock()
            loc.is_visible.return_value = False
            loc.wait_for.side_effect = TimeoutError("not visible")
            res.first = loc
        return res

    mock_page.locator.side_effect = loc_side_effect

    observer = YouTubeStudioUIObserver(mock_page)
    ok, msg = observer.set_audience(made_for_kids=False)
    assert ok is True
    assert msg == "AUDIENCE_VERIFIED"
    mock_no_radio.click.assert_called_once()

def test_audience_mismatch_fails_when_yes_checked():
    mock_page = MagicMock()
    mock_no_radio = MagicMock()
    mock_no_radio.is_visible.return_value = True
    mock_no_radio.get_attribute.side_effect = lambda attr: "false" if attr == "aria-checked" else None

    mock_yes_radio = MagicMock()
    mock_yes_radio.is_visible.return_value = True
    mock_yes_radio.get_attribute.side_effect = lambda attr: "true" if attr == "aria-checked" else None

    def loc_side_effect(sel):
        res = MagicMock()
        if "NOT_MFK" in sel or "Hayır" in sel or "No" in sel:
            res.first = mock_no_radio
        elif "MFK" in sel or "Evet" in sel or "Yes" in sel:
            res.first = mock_yes_radio
        else:
            loc = MagicMock()
            loc.is_visible.return_value = False
            loc.wait_for.side_effect = TimeoutError("not visible")
            res.first = loc
        return res

    mock_page.locator.side_effect = loc_side_effect

    observer = YouTubeStudioUIObserver(mock_page)
    ok, msg = observer.set_audience(made_for_kids=False)
    assert ok is False
    assert "AUDIENCE_MISMATCH" in msg

def test_repository_merge_with_existing_preserves_remote_evidence(tmp_path: Path):
    from automation.publishing.repository import PublishingRepository
    repo = PublishingRepository(vault_path=tmp_path)

    # 1. Existing record on disk
    dummy_video = tmp_path / "vid.mp4"
    dummy_video.write_bytes(b"dummy")

    disk_rec = PublishRecord(
        publish_id="PUB-REEL-2026-0010-YOUTUBE",
        batch_id="PUB-BATCH-01",
        reel_id="REEL-2026-0010",
        platform=Platform.YOUTUBE,
        account_handle="@BuiIdVerse",
        video_file=dummy_video,
        video_sha256="hash123",
        title="Japanese Zen Temple",
        description="Desc",
        hashtags=["#Shorts"],
        scheduled_at_local="2026-08-16T19:30:00+03:00",
        scheduled_at_utc="2026-08-16T16:30:00Z",
        remote_id="Sq1nDGQPpOc",
        remote_url="https://youtube.com/shorts/Sq1nDGQPpOc",
        upload_started=True,
        remote_draft_exists=True,
        status=PlatformPublicationStatus.SCHEDULE_RESUME_REQUIRED
    )
    repo.save_publish_record(disk_rec)

    # 2. Newly created blank record from batch planning
    new_blank_rec = PublishRecord(
        publish_id="PUB-REEL-2026-0010-YOUTUBE",
        batch_id="PUB-BATCH-02",
        reel_id="REEL-2026-0010",
        platform=Platform.YOUTUBE,
        account_handle="@BuiIdVerse",
        video_file=dummy_video,
        video_sha256="hash123",
        title="Japanese Zen Temple",
        description="Desc",
        hashtags=["#Shorts"],
        scheduled_at_local="2026-08-16T19:30:00+03:00",
        scheduled_at_utc="2026-08-16T16:30:00Z",
        status=PlatformPublicationStatus.PENDING
    )

    merged = repo.merge_with_existing(new_blank_rec)
    assert merged.remote_id == "Sq1nDGQPpOc"
    assert merged.remote_url == "https://youtube.com/shorts/Sq1nDGQPpOc"
    assert merged.upload_started is True
    assert merged.remote_draft_exists is True
    assert merged.status == PlatformPublicationStatus.SCHEDULE_RESUME_REQUIRED

# ---------------------------------------------------------------------------
# enter_existing_draft_wizard -- strict wizard-proof contract.
#
# The real upload wizard is proven ONLY by a visible ytcp-uploads-dialog that also
# contains a stepper. A plain /video/<id>/edit page has its own title input and must
# never be mistaken for the wizard (that false positive was the production bug).
# ---------------------------------------------------------------------------

class _DraftLoc:
    """Minimal Playwright-locator stand-in that supports scoped .locator() lookups."""

    def __init__(self, page, kind, visible=True, enabled=True):
        self._page = page
        self._kind = kind
        self._visible = visible
        self._enabled = enabled
        self.click_count = 0

    @property
    def first(self):
        return self

    def is_visible(self, timeout=None):
        return self._visible() if callable(self._visible) else self._visible

    def wait_for(self, state="visible", timeout=None):
        visible = self._visible() if callable(self._visible) else self._visible
        if state == "visible" and not visible:
            raise TimeoutError(f"{self._kind} not visible")
        return None

    def is_enabled(self, timeout=None):
        return self._enabled

    def scroll_into_view_if_needed(self, timeout=None):
        return None

    def click(self, timeout=None):
        self.click_count += 1
        self._page.on_edit_click()

    def locator(self, selector):
        # Scoped lookup inside this element (used for stepper-inside-dialog).
        kind = self._page.classify(selector)
        if self._kind == "dialog" and kind == "stepper":
            return _DraftLoc(self._page, "stepper", visible=self._page.stepper_visible)
        return _DraftLoc(self._page, "missing", visible=False)


class _DraftPage:
    """Fake /video/<id>/edit page. Models exactly which elements exist."""

    def __init__(self, has_edit_button=True, has_title_input=True,
                 dialog_after_click=True, stepper_in_dialog=True,
                 dialog_present_initially=False):
        self.has_edit_button = has_edit_button
        self.has_title_input = has_title_input
        self.dialog_after_click = dialog_after_click
        self.stepper_in_dialog = stepper_in_dialog
        self._dialog_open = dialog_present_initially
        self.edit_clicks = 0
        self.snapshots = []

    # -- helpers -------------------------------------------------------
    def classify(self, selector):
        s = selector.lower()
        if "ytcp-uploads-dialog" in s:
            return "dialog"
        if "taslağı düzenle" in s or "edit draft" in s:
            return "edit_button"
        if "stepper" in s or "tablist" in s or "paper-tab" in s:
            return "stepper"
        if "title" in s or "başlık" in s:
            return "title_input"
        return "other"

    def dialog_visible(self):
        return self._dialog_open

    def stepper_visible(self):
        return self._dialog_open and self.stepper_in_dialog

    def on_edit_click(self):
        self.edit_clicks += 1
        if self.dialog_after_click:
            self._dialog_open = True

    # -- playwright surface --------------------------------------------
    def locator(self, selector):
        kind = self.classify(selector)
        if kind == "dialog":
            return _DraftLoc(self, "dialog", visible=self.dialog_visible)
        if kind == "edit_button":
            return _DraftLoc(self, "edit_button", visible=self.has_edit_button)
        if kind == "stepper":
            return _DraftLoc(self, "stepper", visible=self.stepper_visible)
        if kind == "title_input":
            return _DraftLoc(self, "title_input", visible=self.has_title_input)
        return _DraftLoc(self, "missing", visible=False)

    def screenshot(self, path=None, full_page=None):
        self.snapshots.append(path)
        Path(path).write_bytes(b"")

    def content(self):
        return "<html></html>"


def _observer_for(page):
    obs = YouTubeStudioUIObserver(page)
    obs.capture_error_snapshot = MagicMock()
    return obs


def test_draft_wizard_rejects_plain_edit_page_with_title_input():
    """Edit page + title input + NO uploads-dialog => must be FALSE.
    This is the exact production false positive being fixed."""
    page = _DraftPage(has_edit_button=False, has_title_input=True, dialog_after_click=False)
    observer = _observer_for(page)

    assert observer.enter_existing_draft_wizard(timeout_seconds=1) is False
    assert page.edit_clicks == 0
    observer.capture_error_snapshot.assert_called_once()


def test_draft_wizard_success_requires_real_dialog_and_stepper():
    """'Taslağı düzenle' click that mounts a real ytcp-uploads-dialog + stepper => TRUE."""
    page = _DraftPage(has_edit_button=True, dialog_after_click=True, stepper_in_dialog=True)
    observer = _observer_for(page)

    assert observer.enter_existing_draft_wizard(timeout_seconds=3) is True
    assert page.edit_clicks == 1
    observer.capture_error_snapshot.assert_not_called()


def test_draft_wizard_button_found_but_wizard_never_opens_fails_safely():
    """Button exists and is clicked, but no real wizard mounts => safe failure + snapshot."""
    page = _DraftPage(has_edit_button=True, dialog_after_click=False, has_title_input=True)
    observer = _observer_for(page)

    assert observer.enter_existing_draft_wizard(timeout_seconds=2) is False
    assert page.edit_clicks == 1
    observer.capture_error_snapshot.assert_called_once()


def test_draft_wizard_dialog_without_stepper_is_not_proof():
    """A dialog alone (no stepper inside it) must not count as wizard proof."""
    page = _DraftPage(has_edit_button=True, dialog_after_click=True, stepper_in_dialog=False)
    observer = _observer_for(page)

    assert observer.enter_existing_draft_wizard(timeout_seconds=2) is False
    observer.capture_error_snapshot.assert_called_once()


def test_draft_wizard_already_open_is_idempotent_and_does_not_click():
    """Already inside the real wizard => TRUE without clicking anything again."""
    page = _DraftPage(has_edit_button=True, dialog_present_initially=True, stepper_in_dialog=True)
    observer = _observer_for(page)

    assert observer.enter_existing_draft_wizard(timeout_seconds=2) is True
    assert page.edit_clicks == 0


def test_draft_wizard_uses_at_most_two_button_strategies():
    """Kural 31: the Edit-draft action must expose exactly 2 semantic strategies."""
    from automation.publishing.youtube_studio_selectors import YouTubeStudioSelectors
    assert len(YouTubeStudioSelectors.EDIT_DRAFT_BUTTON_STRATEGIES) == 2
    assert len(YouTubeStudioSelectors.WIZARD_STEPPER_IN_DIALOG) == 2


def test_draft_wizard_failure_blocks_upload_no_duplicate(tmp_path):
    """Existing remote_id + wizard failure => publisher must STOP, never upload a duplicate."""
    from automation.publishing.config import load_publishing_config

    dummy_video = tmp_path / "REEL-2026-0011.mp4"
    dummy_video.write_bytes(b"x" * 2048)

    record = PublishRecord(
        publish_id="PUB-REEL-2026-0011-YOUTUBE",
        batch_id="2026-08-17",
        reel_id="REEL-2026-0011",
        platform=Platform.YOUTUBE,
        account_handle="@BuiIdVerse",
        video_file=dummy_video,
        video_sha256="hash123",
        title="Real Title",
        description="Real caption",
        hashtags=["#Shorts"],
        scheduled_at_local="2026-08-17T19:30:00+03:00",
        scheduled_at_utc="2026-08-17T16:30:00Z",
        remote_id="a9RnSvejU2Q",
        remote_url="https://youtube.com/shorts/a9RnSvejU2Q",
        status=PlatformPublicationStatus.UPLOADED_DRAFT,
    )

    cfg = load_publishing_config(base_dir=tmp_path)
    pub = YouTubeStudioPublisher(config=cfg)

    mock_observer = MagicMock()
    mock_observer.is_logged_in.return_value = True
    mock_observer.verify_logged_in_channel.return_value = (True, "@BuiIdVerse", "OK")
    mock_observer.open_exact_remote_video.return_value = True
    mock_observer.enter_existing_draft_wizard.return_value = False  # wizard never opens

    pub.browser_mgr = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.pages = [MagicMock()]
    pub.browser_mgr.connect.return_value.__enter__.return_value = (MagicMock(), mock_ctx)

    import automation.publishing.youtube_studio_publisher as ysp
    orig = ysp.YouTubeStudioUIObserver
    ysp.YouTubeStudioUIObserver = lambda p: mock_observer
    try:
        res = pub.upload_and_schedule(record)
        assert mock_observer.upload_file.call_count == 0
        assert res.status == PlatformPublicationStatus.SCHEDULE_RESUME_REQUIRED
    finally:
        ysp.YouTubeStudioUIObserver = orig

def test_youtube_studio_real_dom_fixture_resolution():
    fixture_path = Path(__file__).resolve().parent / "fixtures" / "youtube_live_controls.html"
    assert fixture_path.exists()
    html_content = fixture_path.read_text(encoding="utf-8")

    assert "VIDEO_MADE_FOR_KIDS_NOT_MFK" in html_content
    assert "VIDEO_MADE_FOR_KIDS_MFK" in html_content
    assert "Taslağı düzenle" in html_content
    assert "paper-input-label-1" in html_content
    assert "Planla" in html_content


# =============================================================================
# WIZARD STATE MACHINE REGRESSION TESTS
# =============================================================================

from automation.publishing.youtube_studio_ui_observer import WizardStep


def _make_mock_page_with_tabs(active_tab_text="Ayrıntılar", tab_count=4):
    """Create a mock page with a resolved active ytcp-uploads-dialog whose
    tp-yt-paper-tab stepper reflects the given active tab.

    detect_current_wizard_step() scopes all of its DOM queries to the
    active-dialog locator returned by get_active_upload_dialog(), so the
    stepper tabs must be reachable via THAT locator's .locator(...), not
    just mock_page.locator(...). Selector matching uses exact string
    equality (never bare "in" substring checks) so that :not(tp-yt-paper-tab)
    exclusion clauses used by other detection heuristics don't get
    misidentified as the stepper-tab selector itself.
    """
    mock_page = MagicMock()
    tab_texts = ["Ayrıntılar", "Video öğeleri", "İlk kontrol", "Görünürlük"]

    tabs_locator = MagicMock()
    tabs_locator.count.return_value = tab_count

    tab_elements = []
    for txt in tab_texts[:tab_count]:
        tab = MagicMock()
        tab.is_visible.return_value = True
        tab.get_attribute.side_effect = lambda attr, t=txt: "true" if (attr == "aria-selected" and t == active_tab_text) else ""
        tab.inner_text.return_value = txt
        tab_elements.append(tab)

    tabs_locator.nth = lambda i: tab_elements[i]

    def _not_found():
        m = MagicMock()
        m.first = MagicMock()
        m.first.is_visible.return_value = False
        m.first.is_enabled.return_value = False
        m.first.wait_for.side_effect = TimeoutError("not visible")
        m.count.return_value = 0
        return m

    def dialog_locator_side_effect(sel):
        if sel == "tp-yt-paper-tab":
            return tabs_locator
        return _not_found()

    mock_dialog = MagicMock()
    mock_dialog.is_visible.return_value = True
    mock_dialog.count.return_value = 1
    mock_dialog.first = mock_dialog
    mock_dialog.nth.return_value = mock_dialog
    mock_dialog.get_attribute.return_value = ""
    mock_dialog.locator = MagicMock(side_effect=dialog_locator_side_effect)

    def locator_side_effect(sel):
        if "ytcp-uploads-dialog" in sel:
            return mock_dialog
        return dialog_locator_side_effect(sel)

    mock_page.locator = MagicMock(side_effect=locator_side_effect)
    return mock_page


def test_wizard_step_detection_details():
    """Test wizard step detection returns DETAILS when Ayrıntılar tab is active."""
    mock_page = _make_mock_page_with_tabs(active_tab_text="Ayrıntılar")
    observer = YouTubeStudioUIObserver(mock_page)
    assert observer.detect_current_wizard_step() == WizardStep.DETAILS


def test_wizard_step_detection_video_elements():
    """Test wizard step detection returns VIDEO_ELEMENTS when Video öğeleri tab is active."""
    mock_page = _make_mock_page_with_tabs(active_tab_text="Video öğeleri")
    observer = YouTubeStudioUIObserver(mock_page)
    assert observer.detect_current_wizard_step() == WizardStep.VIDEO_ELEMENTS


def test_wizard_step_detection_checks():
    """Test wizard step detection returns CHECKS when İlk kontrol tab is active."""
    mock_page = _make_mock_page_with_tabs(active_tab_text="İlk kontrol")
    observer = YouTubeStudioUIObserver(mock_page)
    assert observer.detect_current_wizard_step() == WizardStep.CHECKS


def test_wizard_step_detection_visibility():
    """Test wizard step detection returns VISIBILITY when Görünürlük tab is active."""
    mock_page = _make_mock_page_with_tabs(active_tab_text="Görünürlük")
    observer = YouTubeStudioUIObserver(mock_page)
    assert observer.detect_current_wizard_step() == WizardStep.VISIBILITY


def test_exact_live_bug_regression_stale_details_with_video_elements_content():
    """
    CRITICAL REGRESSION TEST (Exact live bug):
    Active wizard dialog has stale workflow-step="DETAILS",
    but visible heading is "Video öğeleri", visible cards are "İlgili video" & "Altyazılar",
    and stepper has "Video öğeleri" active.
    Verify that detect_current_wizard_step() returns VIDEO_ELEMENTS and NOT DETAILS!
    """
    mock_page = MagicMock()
    mock_dialog = MagicMock()
    mock_dialog.is_visible.return_value = True
    mock_dialog.count.return_value = 1
    mock_dialog.first = mock_dialog
    mock_dialog.nth.return_value = mock_dialog
    # Stale attribute:
    mock_dialog.get_attribute.side_effect = lambda attr: "DETAILS" if attr == "workflow-step" else "Sq1nDGQPpOc"

    # Stepper has "Video öğeleri" active
    mock_tab = MagicMock()
    mock_tab.is_visible.return_value = True
    mock_tab.inner_text.return_value = "Video öğeleri"
    mock_tab.get_attribute.side_effect = lambda attr: "true" if attr == "aria-selected" else ""

    # Heading has "Video öğeleri"
    mock_heading = MagicMock()
    mock_heading.is_visible.return_value = True
    mock_heading.inner_text.return_value = "Video öğeleri"

    # Related video and subtitles cards
    mock_cards = MagicMock()
    mock_cards.count.return_value = 2
    mock_cards.is_visible.return_value = True

    # Stale background details radio (should be ignored by consensus)
    mock_stale_radio = MagicMock()
    mock_stale_radio.is_visible.return_value = False
    mock_stale_radio.wait_for.side_effect = TimeoutError("not visible")

    def dialog_loc(sel):
        res = MagicMock()
        # Match on the actual heading text only: a bare "h1"/"h2" tag check
        # would also match unrelated heading selectors (e.g. the Görünürlük
        # heading query), since every step's heading selector uses h1/h2 tags.
        if "Video öğeleri" in sel:
            res.first = mock_heading
            res.is_visible.return_value = True
        elif "İlgili video" in sel or "Altyazılar" in sel:
            return mock_cards
        elif ("tp-yt-paper-tab" in sel or "ytcp-stepper" in sel) and ":not(" not in sel:
            # Real CSS :not(tp-yt-paper-tab) exclusion clauses (used by other
            # detection heuristics to exclude stepper elements) must NOT be
            # treated as a query FOR the stepper tab itself.
            res.first = mock_tab
            res.count.return_value = 1
            res.nth.return_value = mock_tab
            res.is_visible.return_value = True
        elif "VIDEO_MADE_FOR_KIDS" in sel:
            res.first = mock_stale_radio
            res.is_visible.return_value = False
        else:
            res.first.is_visible.return_value = False
            res.first.wait_for.side_effect = TimeoutError("not visible")
            res.count.return_value = 0
        return res

    mock_dialog.locator.side_effect = dialog_loc

    def page_loc(sel):
        if "ytcp-uploads-dialog" in sel:
            return mock_dialog
        return dialog_loc(sel)

    mock_page.locator.side_effect = page_loc

    observer = YouTubeStudioUIObserver(mock_page)
    observer.current_remote_id = "Sq1nDGQPpOc"

    step = observer.detect_current_wizard_step()
    assert step == WizardStep.VIDEO_ELEMENTS, f"Expected VIDEO_ELEMENTS, got {step}"


def test_wizard_step_detection_all_four_steps_with_stale_previous_clones():
    """
    Verify that all 4 steps (DETAILS, VIDEO_ELEMENTS, CHECKS, VISIBILITY)
    are accurately resolved even when stale previous-step DOM elements exist.
    """
    for expected_step, heading_text, stepper_text in [
        (WizardStep.DETAILS, "Ayrıntılar", "Ayrıntılar"),
        (WizardStep.VIDEO_ELEMENTS, "Video öğeleri", "Video öğeleri"),
        (WizardStep.CHECKS, "İlk kontrol", "İlk kontrol"),
        (WizardStep.VISIBILITY, "Görünürlük", "Görünürlük"),
    ]:
        mock_page = MagicMock()
        mock_dialog = MagicMock()
        mock_dialog.is_visible.return_value = True
        mock_dialog.count.return_value = 1
        mock_dialog.first = mock_dialog
        mock_dialog.nth.return_value = mock_dialog
        mock_dialog.get_attribute.side_effect = lambda attr: expected_step if attr == "workflow-step" else "Sq1nDGQPpOc"

        mock_heading = MagicMock()
        mock_heading.is_visible.return_value = True
        mock_heading.inner_text.return_value = heading_text

        mock_tab = MagicMock()
        mock_tab.is_visible.return_value = True
        mock_tab.inner_text.return_value = stepper_text
        mock_tab.get_attribute.side_effect = lambda attr: "true" if attr == "aria-selected" else ""

        def dialog_loc(sel):
            res = MagicMock()
            # Match on the actual heading text only: a bare "h1"/"h2" tag
            # check would match EVERY step's heading selector (they all use
            # h1/h2 tags), falsely marking a different step's heading visible.
            if heading_text in sel:
                res.first = mock_heading
                res.is_visible.return_value = True
            elif ("tp-yt-paper-tab" in sel or "ytcp-stepper" in sel) and ":not(" not in sel:
                # Real CSS :not(tp-yt-paper-tab) exclusion clauses (used by other
                # detection heuristics to exclude stepper elements) must NOT be
                # treated as a query FOR the stepper tab itself.
                res.first = mock_tab
                res.count.return_value = 1
                res.nth.return_value = mock_tab
                res.is_visible.return_value = True
            elif expected_step == WizardStep.CHECKS and "Kontroller tamamlandı" in sel:
                res.first = mock_heading
                res.is_visible.return_value = True
            elif expected_step == WizardStep.VISIBILITY and ("Planlayın" in sel or "#schedule" in sel):
                res.first = mock_heading
                res.is_visible.return_value = True
            elif expected_step == WizardStep.DETAILS and "VIDEO_MADE_FOR_KIDS_NOT_MFK" in sel:
                aud = MagicMock()
                aud.is_visible.return_value = True
                aud.bounding_box.return_value = {"width": 20, "height": 20}
                res.first = aud
            else:
                res.first.is_visible.return_value = False
                res.first.wait_for.side_effect = TimeoutError("not visible")
                res.count.return_value = 0
            return res

        mock_dialog.locator.side_effect = dialog_loc

        def page_loc(sel):
            if "ytcp-uploads-dialog" in sel:
                return mock_dialog
            return dialog_loc(sel)

        mock_page.locator.side_effect = page_loc
        observer = YouTubeStudioUIObserver(mock_page)
        detected = observer.detect_current_wizard_step()
        assert detected == expected_step, f"For {expected_step}, got {detected}"


def test_advance_wizard_to_visibility_full_progression():
    """Test that advance_wizard_to_visibility() drives from DETAILS through all steps to VISIBILITY."""
    mock_page = MagicMock()

    # Track which step we're on (mutable state)
    state = {"step_index": 0}
    tab_texts = ["Ayrıntılar", "Video öğeleri", "İlk kontrol", "Görünürlük"]

    def locator_side_effect(sel):
        m = MagicMock()
        m.first = MagicMock()

        if sel == "tp-yt-paper-tab":
            tabs_loc = MagicMock()
            tabs_loc.count.return_value = 4

            def make_tab(i):
                tab = MagicMock()
                active_text = tab_texts[state["step_index"]]
                tab.get_attribute.return_value = "true" if tab_texts[i] == active_text else "false"
                tab.inner_text.return_value = tab_texts[i]
                return tab

            tabs_loc.nth = make_tab
            return tabs_loc

        # Audience NOT_MFK radio: visible and clickable on DETAILS step
        if "VIDEO_MADE_FOR_KIDS_NOT_MFK" in sel:
            m.first.is_visible.return_value = (state["step_index"] == 0)
            if state["step_index"] != 0:
                m.first.wait_for.side_effect = TimeoutError("not visible")
            m.first.bounding_box.return_value = {"x": 100, "y": 200, "width": 30, "height": 30}
            m.first.get_attribute.return_value = "true" if state["step_index"] == 0 else "false"
            m.first.scroll_into_view_if_needed = MagicMock()
            m.first.click = MagicMock()
            m.count.return_value = 1 if state["step_index"] == 0 else 0
            m.nth.return_value = m.first
            return m

        if "VIDEO_MADE_FOR_KIDS_MFK" in sel:
            m.first.is_visible.return_value = (state["step_index"] == 0)
            if state["step_index"] != 0:
                m.first.wait_for.side_effect = TimeoutError("not visible")
            m.first.get_attribute.return_value = "false"
            m.count.return_value = 1 if state["step_index"] == 0 else 0
            m.nth.return_value = m.first
            return m

        # Next button
        if "#next-button" in sel or "next" in sel.lower():
            m.first.is_visible.return_value = True
            m.first.is_enabled.return_value = True
            def click_next(*args, **kwargs):
                if state["step_index"] < 3:
                    state["step_index"] += 1
            m.first.click = MagicMock(side_effect=click_next)
            return m

        # Show More button
        if "toggle-button" in sel or "Show more" in sel or "Daha fazla" in sel:
            m.first.is_visible.return_value = (state["step_index"] == 0)
            if state["step_index"] != 0:
                m.first.wait_for.side_effect = TimeoutError("not visible")
            return m

        # AI disclosure radio
        if "ALTERED_CONTENT_YES" in sel or "SYNTHETIC_CONTENT_YES" in sel:
            m.first.is_visible.return_value = (state["step_index"] == 0)
            if state["step_index"] != 0:
                m.first.wait_for.side_effect = TimeoutError("not visible")
            return m

        # Checks completion - dialog text
        if "ytcp-uploads-dialog" in sel:
            m = MagicMock()
            m.is_visible.return_value = True
            m.count.return_value = 1
            m.nth.return_value = m
            m.first = m
            m.locator.side_effect = locator_side_effect
            return m

        m.first.is_visible.return_value = False
        m.first.is_enabled.return_value = False
        m.first.wait_for.side_effect = TimeoutError("not visible")
        m.count.return_value = 0
        return m

    mock_page.locator = MagicMock(side_effect=locator_side_effect)
    mock_page.inner_text = MagicMock(return_value="Kontroller tamamlandı")

    observer = YouTubeStudioUIObserver(mock_page)
    ok, msg = observer.advance_wizard_to_visibility(made_for_kids=False, ai_disclosure=True)

    assert ok, f"advance_wizard_to_visibility() failed: {msg}"
    assert msg == "VISIBILITY_READY"
    assert state["step_index"] == 3  # Should be on VISIBILITY (index 3)


def test_advance_wizard_ai_disclosure_fail_does_not_stop_wizard():
    """Verify that if AI disclosure is unavailable or fails, wizard progression continues cleanly to VISIBILITY."""
    mock_page = MagicMock()
    observer = YouTubeStudioUIObserver(mock_page)

    steps = [WizardStep.DETAILS, WizardStep.VIDEO_ELEMENTS, WizardStep.CHECKS, WizardStep.VISIBILITY]
    current_idx = {"idx": 0}

    observer.detect_current_wizard_step = MagicMock(side_effect=lambda: steps[current_idx["idx"]])
    observer.set_audience = MagicMock(return_value=(True, "AUDIENCE_VERIFIED"))
    # AI disclosure FAILS / unavailable
    observer.set_ai_disclosure = MagicMock(return_value=(False, "AI_DISCLOSURE_CONTROL_NOT_FOUND"))
    
    def advance_step():
        if current_idx["idx"] < len(steps) - 1:
            current_idx["idx"] += 1
        return True

    observer._resolve_active_next_button = MagicMock(return_value=MagicMock())
    observer._click_next_button = MagicMock(side_effect=advance_step)
    observer._wait_for_wizard_step = MagicMock(side_effect=lambda target, timeout_seconds=10: True)
    observer._wait_for_checks_complete = MagicMock(return_value=True)

    ok, msg = observer.advance_wizard_to_visibility(made_for_kids=False, ai_disclosure=True)
    assert ok is True
    assert msg == "VISIBILITY_READY"
    # Audience was checked, AI was attempted (but did not block), Next was clicked
    observer.set_audience.assert_called_once()
    assert observer._click_next_button.call_count >= 3


def test_advance_wizard_audience_fail_stops_wizard():
    """Verify that if Audience selection fails, wizard progression immediately stops with error."""
    mock_page = MagicMock()
    observer = YouTubeStudioUIObserver(mock_page)

    observer.detect_current_wizard_step = MagicMock(return_value=WizardStep.DETAILS)
    observer.set_audience = MagicMock(return_value=(False, "AUDIENCE_SELECTION_FAILED"))
    observer._click_next_button = MagicMock()

    ok, msg = observer.advance_wizard_to_visibility(made_for_kids=False, ai_disclosure=True)
    assert ok is False
    assert "AUDIENCE_FAILED" in msg
    # Next button should NEVER be clicked if audience fails
    observer._click_next_button.assert_not_called()


def test_details_step_does_not_search_schedule():
    """Verify that find_and_expand_schedule_card() fails when on DETAILS step."""
    mock_page = _make_mock_page_with_tabs(active_tab_text="Ayrıntılar")
    observer = YouTubeStudioUIObserver(mock_page)
    result = observer.find_and_expand_schedule_card()
    assert result is False, "Schedule card should NOT be found when on DETAILS step"


def test_video_elements_step_does_not_search_schedule():
    """Verify that find_and_expand_schedule_card() fails when on VIDEO_ELEMENTS step."""
    mock_page = _make_mock_page_with_tabs(active_tab_text="Video öğeleri")
    observer = YouTubeStudioUIObserver(mock_page)
    result = observer.find_and_expand_schedule_card()
    assert result is False, "Schedule card should NOT be found when on VIDEO_ELEMENTS step"


def test_checks_step_does_not_search_schedule():
    """Verify that find_and_expand_schedule_card() fails when on CHECKS step."""
    mock_page = _make_mock_page_with_tabs(active_tab_text="İlk kontrol")
    observer = YouTubeStudioUIObserver(mock_page)
    result = observer.find_and_expand_schedule_card()
    assert result is False, "Schedule card should NOT be found when on CHECKS step"


def test_only_visibility_step_searches_schedule():
    """Verify that find_and_expand_schedule_card() proceeds when on VISIBILITY step."""
    mock_page = _make_mock_page_with_tabs(active_tab_text="Görünürlük")

    # Override the locator to provide a schedule accordion header on VISIBILITY
    original_locator = mock_page.locator

    def patched_locator(sel):
        # If we're checking schedule headers after step verification, simulate found
        for sched_sel in ["#schedule-section", "#schedule-card",
                          "tp-yt-paper-radio-button[name='SCHEDULE']"]:
            if sel == sched_sel:
                m = MagicMock()
                m.first = MagicMock()
                m.first.is_visible.return_value = True
                m.first.click = MagicMock()
                return m

        return original_locator(sel)

    mock_page.locator = MagicMock(side_effect=patched_locator)
    observer = YouTubeStudioUIObserver(mock_page)
    result = observer.find_and_expand_schedule_card()
    assert result is True, "Schedule card should be found when on VISIBILITY step"


def test_audience_bounding_box_required():
    """Verify that set_audience() fails when bounding_box returns None (hidden element)."""
    mock_page = MagicMock()

    def locator_side_effect(sel):
        m = MagicMock()
        m.first = MagicMock()
        if "VIDEO_MADE_FOR_KIDS_NOT_MFK" in sel:
            m.first.is_visible.return_value = True
            m.first.bounding_box.return_value = None  # Hidden/template clone
            m.first.scroll_into_view_if_needed = MagicMock()
            m.first.click = MagicMock()
            return m
        m.first.is_visible.return_value = False
        m.first.wait_for.side_effect = TimeoutError("not visible")
        return m

    mock_page.locator = MagicMock(side_effect=locator_side_effect)
    observer = YouTubeStudioUIObserver(mock_page)
    ok, msg = observer.set_audience(made_for_kids=False)
    assert ok is False, "Audience should fail when bounding_box is None"
    assert "not found or not clickable" in msg


def test_old_bug_regression_details_to_schedule_fails():
    """
    Exact reproduction of the old bug: being on DETAILS step and trying to
    find_and_expand_schedule_card(). This MUST fail now.
    """
    mock_page = _make_mock_page_with_tabs(active_tab_text="Ayrıntılar")
    observer = YouTubeStudioUIObserver(mock_page)

    # This is the exact old code path that caused SCHEDULING_UNAVAILABLE
    step = observer.detect_current_wizard_step()
    assert step == WizardStep.DETAILS

    result = observer.find_and_expand_schedule_card()
    assert result is False, "OLD BUG REGRESSION: Schedule card search from DETAILS step must fail"


def test_scheduled_without_verification_normalizes_to_resume():
    """
    SCHEDULED status on disk without schedule_verified=True must be
    normalized to SCHEDULE_RESUME_REQUIRED during merge.
    """
    import tempfile
    from automation.publishing.repository import PublishingRepository

    with tempfile.TemporaryDirectory() as tmp:
        repo = PublishingRepository(Path(tmp))

        # Create a record with SCHEDULED but no verification
        existing = PublishRecord(
            publish_id="PUB-REEL-TEST-YT",
            batch_id="BATCH-TEST",
            reel_id="REEL-TEST",
            platform=Platform.YOUTUBE,
            video_file=Path("test.mp4"),
            video_sha256="abc123",
            title="Test",
            description="Test desc",
            hashtags=[],
            scheduled_at_local="2026-08-16T19:30:00",
            scheduled_at_utc="2026-08-16T16:30:00",
            status=PlatformPublicationStatus.SCHEDULED,
            remote_id="test_vid_id",
            schedule_verified=False  # No verification evidence!
        )
        repo.save_publish_record(existing)

        # Create a new PENDING record for the same reel
        new_rec = PublishRecord(
            publish_id="PUB-REEL-TEST-YT",
            batch_id="BATCH-TEST",
            reel_id="REEL-TEST",
            platform=Platform.YOUTUBE,
            video_file=Path("test.mp4"),
            video_sha256="abc123",
            title="Test",
            description="Test desc",
            hashtags=[],
            scheduled_at_local="2026-08-16T19:30:00",
            scheduled_at_utc="2026-08-16T16:30:00",
            status=PlatformPublicationStatus.PENDING
        )

        merged = repo.merge_with_existing(new_rec)
        assert merged.status == PlatformPublicationStatus.SCHEDULE_RESUME_REQUIRED, \
            f"Expected SCHEDULE_RESUME_REQUIRED, got {merged.status.value}"


def test_scheduled_with_verification_preserved():
    """
    SCHEDULED status on disk WITH schedule_verified=True must be preserved.
    """
    import tempfile
    from automation.publishing.repository import PublishingRepository

    with tempfile.TemporaryDirectory() as tmp:
        repo = PublishingRepository(Path(tmp))

        existing = PublishRecord(
            publish_id="PUB-REEL-TEST-YT",
            batch_id="BATCH-TEST",
            reel_id="REEL-TEST",
            platform=Platform.YOUTUBE,
            video_file=Path("test.mp4"),
            video_sha256="abc123",
            title="Test",
            description="Test desc",
            hashtags=[],
            scheduled_at_local="2026-08-16T19:30:00",
            scheduled_at_utc="2026-08-16T16:30:00",
            remote_id="test_vid_id",
        )
        # Use mark_scheduled to properly set verification
        existing.mark_scheduled(remote_id="test_vid_id", verified_date="2026-08-16", verified_time="19:30")
        repo.save_publish_record(existing)

        new_rec = PublishRecord(
            publish_id="PUB-REEL-TEST-YT",
            batch_id="BATCH-TEST",
            reel_id="REEL-TEST",
            platform=Platform.YOUTUBE,
            video_file=Path("test.mp4"),
            video_sha256="abc123",
            title="Test",
            description="Test desc",
            hashtags=[],
            scheduled_at_local="2026-08-16T19:30:00",
            scheduled_at_utc="2026-08-16T16:30:00",
            status=PlatformPublicationStatus.PENDING
        )

        merged = repo.merge_with_existing(new_rec)
        assert merged.status == PlatformPublicationStatus.SCHEDULED, \
            f"Expected SCHEDULED, got {merged.status.value}"
        assert merged.schedule_verified is True


def test_audience_scoped_to_active_kitle_container_ignores_clones():
    """
    Test that set_audience() finds and uses the active Kitle container
    which contains all 4 anchor texts, eliminating clone radio pairs.
    """
    mock_page = MagicMock()

    # Container mock with the 4 anchor markers
    mock_container = MagicMock()
    mock_container.is_visible.return_value = True
    mock_container.inner_text.return_value = "Kitle. Evet, çocuklara özel. Hayır, çocuklara özel değil. Yaş kısıtlaması."

    # Within this container, exact 1 YES and 1 NO radio
    mock_no_radio = MagicMock()
    mock_no_radio.is_visible.return_value = True
    mock_no_radio.bounding_box.return_value = {"x": 50, "y": 50, "width": 20, "height": 20}
    mock_no_radio.get_attribute.return_value = "true"

    mock_yes_radio = MagicMock()
    mock_yes_radio.is_visible.return_value = True
    mock_yes_radio.bounding_box.return_value = {"x": 50, "y": 80, "width": 20, "height": 20}
    mock_yes_radio.get_attribute.return_value = "false"

    def container_locator(sel):
        res = MagicMock()
        if "NOT_MFK" in sel:
            res.count.return_value = 1
            res.nth.return_value = mock_no_radio
        elif "MFK" in sel:
            res.count.return_value = 1
            res.nth.return_value = mock_yes_radio
        else:
            res.count.return_value = 0
        return res

    mock_container.locator.side_effect = container_locator

    def page_locator(sel):
        res = MagicMock()
        if "#scrollable-content" in sel or "DETAILS" in sel or "ytcp-uploads-dialog" in sel:
            res.count.return_value = 1
            res.nth.return_value = mock_container
            res.first = mock_container
        else:
            res.count.return_value = 0
            res.first.is_visible.return_value = False
            res.first.wait_for.side_effect = TimeoutError("not visible")
        return res

    mock_page.locator.side_effect = page_locator

    observer = YouTubeStudioUIObserver(mock_page)
    ok, msg = observer.set_audience(made_for_kids=False)
    assert ok is True
    assert msg == "AUDIENCE_VERIFIED"
    mock_no_radio.click.assert_called()


def test_audience_ambiguous_pairs_in_container_fails():
    """
    Test that set_audience() returns AMBIGUOUS_ACTIVE_AUDIENCE_SECTION
    if more than 1 visible NOT_MADE_FOR_KIDS radio is found in the container.
    """
    mock_page = MagicMock()

    mock_container = MagicMock()
    mock_container.is_visible.return_value = True
    mock_container.inner_text.return_value = "Kitle. Evet, çocuklara özel. Hayır, çocuklara özel değil. Yaş kısıtlaması."

    r1 = MagicMock()
    r1.is_visible.return_value = True
    r1.bounding_box.return_value = {"x": 10, "y": 10, "width": 20, "height": 20}

    r2 = MagicMock()
    r2.is_visible.return_value = True
    r2.bounding_box.return_value = {"x": 10, "y": 50, "width": 20, "height": 20}

    def container_locator(sel):
        res = MagicMock()
        if "NOT_MFK" in sel:
            res.count.return_value = 2
            res.nth.side_effect = lambda i: [r1, r2][i]
        else:
            res.count.return_value = 0
        return res

    mock_container.locator.side_effect = container_locator

    def page_locator(sel):
        res = MagicMock()
        if "#scrollable-content" in sel or "DETAILS" in sel or "ytcp-uploads-dialog" in sel:
            res.count.return_value = 1
            res.nth.return_value = mock_container
            res.first = mock_container
        else:
            res.count.return_value = 0
            res.first.is_visible.return_value = False
            res.first.wait_for.side_effect = TimeoutError("not visible")
        return res

    mock_page.locator.side_effect = page_locator

    observer = YouTubeStudioUIObserver(mock_page)
    ok, msg = observer.set_audience(made_for_kids=False)
    assert ok is False
    assert "AMBIGUOUS_ACTIVE_AUDIENCE_SECTION" in msg


def test_single_visible_hh_mm_paper_input_fallback_resolves_time():
    """
    Test that when label text is empty, exactly 1 visible paper input
    matching ^\\d{1,2}:\\d{2}$ is correctly accepted as the time input.
    """
    mock_page = MagicMock()

    mock_time_inp = MagicMock()
    mock_time_inp.is_visible.return_value = True
    # Initial value 00:00, after typing 19:30
    values = ["00:00", "19:30", "19:30"]
    mock_time_inp.input_value.side_effect = lambda: values.pop(0) if values else "19:30"
    mock_time_inp.get_attribute.return_value = "paper-input-label-1"

    # Label text is empty (reproducing live probe condition)
    mock_lbl = MagicMock()
    mock_lbl.inner_text.return_value = ""
    mock_lbl.text_content.return_value = ""

    def loc_side_effect(sel):
        res = MagicMock()
        if "tp-yt-paper-input" in sel:
            res.count.return_value = 1
            res.nth.return_value = mock_time_inp
            res.first = mock_time_inp
        elif "paper-input-label-1" in sel:
            res.first = mock_lbl
            res.count.return_value = 1
        else:
            res.count.return_value = 0
            res.first.is_visible.return_value = False
            res.first.wait_for.side_effect = TimeoutError("not visible")
        return res

    mock_page.locator.side_effect = loc_side_effect

    observer = YouTubeStudioUIObserver(mock_page)
    ok, msg = observer.set_schedule_time_exact("19:30")
    assert ok is True
    assert msg == "TIME_MATCH"
    mock_page.keyboard.type.assert_called_with("19:30")


def test_youtube_preflight_never_clicks_final_planla_and_returns_ready(tmp_path):
    """
    Test prepare_youtube_schedule_preflight:
    Executes all setup steps up to final Planla button verification,
    does NOT click Planla, and returns YOUTUBE_FINAL_SCHEDULE_READY.
    """
    mock_page = MagicMock()
    observer = YouTubeStudioUIObserver(mock_page)

    observer.is_logged_in = MagicMock(return_value=True)
    observer.verify_logged_in_channel = MagicMock(return_value=(True, "@BuiIdVerse", "OK"))
    observer.open_exact_remote_video = MagicMock(return_value=True)
    observer.enter_existing_draft_wizard = MagicMock(return_value=True)
    observer.advance_wizard_to_visibility = MagicMock(return_value=(True, "VISIBILITY_READY"))
    observer.find_and_expand_schedule_card = MagicMock(return_value=True)
    observer.set_schedule_datetime = MagicMock(return_value=True)

    # Final button visible & enabled
    mock_btn = MagicMock()
    mock_btn.is_visible.return_value = True
    mock_btn.is_enabled.return_value = True
    mock_btn.inner_text.return_value = "Planla"
    mock_page.locator.return_value.first = mock_btn

    ok, msg = observer.prepare_youtube_schedule_preflight(
        target_remote_id="Sq1nDGQPpOc",
        scheduled_at_local="2026-08-16T19:30:00"
    )

    assert ok is True
    assert msg == "YOUTUBE_FINAL_SCHEDULE_READY"
    # Final button must NEVER have been clicked during preflight
    mock_btn.click.assert_not_called()


def test_ai_disclosure_control_not_found():
    """Verify that set_ai_disclosure() fails cleanly if AI disclosure radio is not found."""
    mock_page = MagicMock()
    mock_dialog = MagicMock()
    mock_dialog.is_visible.return_value = True
    mock_dialog.count.return_value = 1
    mock_dialog.first = mock_dialog
    mock_dialog.nth.return_value = mock_dialog

    mock_loc = MagicMock()
    mock_loc.first.is_visible.return_value = False
    mock_loc.first.wait_for.side_effect = TimeoutError("not visible")
    mock_loc.count.return_value = 0
    mock_dialog.locator.return_value = mock_loc

    def loc_side_effect(sel):
        if "ytcp-uploads-dialog" in sel:
            return mock_dialog
        return mock_loc

    mock_page.locator.side_effect = loc_side_effect
    observer = YouTubeStudioUIObserver(mock_page)
    ok, msg = observer.set_ai_disclosure(enabled=True)
    assert ok is False
    assert "ADVANCED_SETTINGS_CONTROL_NOT_FOUND_IN_ACTIVE_DIALOG" in msg or "AI_DISCLOSURE_CONTROL_NOT_FOUND" in msg


def test_ai_disclosure_already_enabled():
    """Verify that set_ai_disclosure() detects already enabled synthetic content radio."""
    mock_page = MagicMock()
    mock_dialog = MagicMock()
    mock_dialog.is_visible.return_value = True
    mock_dialog.count.return_value = 1
    mock_dialog.first = mock_dialog
    mock_dialog.nth.return_value = mock_dialog

    mock_radio = MagicMock()
    mock_radio.is_visible.return_value = True
    mock_radio.get_attribute.return_value = "true"

    def d_loc_side_effect(sel):
        res = MagicMock()
        if "ALTERED_CONTENT_YES" in sel or "SYNTHETIC_CONTENT_YES" in sel:
            res.first = mock_radio
            res.is_visible.return_value = True
        else:
            res.first.is_visible.return_value = False
            res.first.wait_for.side_effect = TimeoutError("not visible")
        return res

    mock_dialog.locator.side_effect = d_loc_side_effect

    def loc_side_effect(sel):
        if "ytcp-uploads-dialog" in sel:
            return mock_dialog
        res = MagicMock()
        res.first.is_visible.return_value = False
        res.first.wait_for.side_effect = TimeoutError("not visible")
        return res

    mock_page.locator.side_effect = loc_side_effect
    observer = YouTubeStudioUIObserver(mock_page)
    ok, msg = observer.set_ai_disclosure(enabled=True)
    assert ok is True
    assert msg == "AI_DISCLOSURE_ALREADY_ENABLED"
    mock_radio.click.assert_not_called()


def test_ai_disclosure_enable_success():
    """Verify that set_ai_disclosure() clicks YES radio and enables synthetic content."""
    mock_page = MagicMock()
    mock_dialog = MagicMock()
    mock_dialog.is_visible.return_value = True
    mock_dialog.count.return_value = 1
    mock_dialog.first = mock_dialog
    mock_dialog.nth.return_value = mock_dialog

    mock_radio = MagicMock()
    mock_radio.is_visible.return_value = True
    mock_radio.get_attribute.side_effect = lambda attr: "ALTERED_CONTENT_YES" if attr == "name" else "false"

    mock_aud_no = MagicMock()
    mock_aud_no.is_visible.return_value = True
    mock_aud_no.get_attribute.return_value = "true"

    mock_aud_yes = MagicMock()
    mock_aud_yes.is_visible.return_value = True
    mock_aud_yes.get_attribute.return_value = "false"

    def d_loc_side_effect(sel):
        res = MagicMock()
        if "ALTERED_CONTENT_YES" in sel or "SYNTHETIC_CONTENT_YES" in sel:
            res.first = mock_radio
            res.is_visible.return_value = True
        elif "VIDEO_MADE_FOR_KIDS_NOT_MFK" in sel:
            res.first = mock_aud_no
        elif "VIDEO_MADE_FOR_KIDS_MFK" in sel:
            res.first = mock_aud_yes
        else:
            res.first.is_visible.return_value = False
            res.first.wait_for.side_effect = TimeoutError("not visible")
        return res

    mock_dialog.locator.side_effect = d_loc_side_effect

    def loc_side_effect(sel):
        if "ytcp-uploads-dialog" in sel:
            return mock_dialog
        res = MagicMock()
        res.first.is_visible.return_value = False
        res.first.wait_for.side_effect = TimeoutError("not visible")
        return res

    mock_page.locator.side_effect = loc_side_effect
    observer = YouTubeStudioUIObserver(mock_page)
    ok, msg = observer.set_ai_disclosure(enabled=True)
    assert ok is True
    assert msg == "AI_DISCLOSURE_ENABLED"
    mock_radio.click.assert_called_once()


def test_ai_disclosure_dual_metadata_editors_scopes_strictly_to_active_dialog():
    """
    CRITICAL REGRESSION TEST:
    DOM contains two metadata editors:
    1. Background page editor (with backdrop blocking it)
    2. Active ytcp-uploads-dialog editor
    Both have #toggle-button.
    Verify that set_ai_disclosure() ONLY clicks the active dialog toggle button,
    and never touches the background editor button.
    """
    mock_page = MagicMock()

    # 1. Background Editor and Toggle
    mock_bg_toggle = MagicMock()
    mock_bg_toggle.is_visible.return_value = True
    mock_bg_toggle.click = MagicMock(side_effect=Exception("Backdrop pointer interception!"))

    mock_bg_editor = MagicMock()
    mock_bg_editor.is_visible.return_value = True
    mock_bg_editor.locator.return_value.first = mock_bg_toggle

    # 2. Dialog Editor and Toggle
    expanded_state = {"open": False}
    def dialog_toggle_click(*args, **kwargs):
        expanded_state["open"] = True

    mock_dialog_toggle = MagicMock()
    mock_dialog_toggle.is_visible.return_value = True
    mock_dialog_toggle.get_attribute.side_effect = lambda attr: "Gelişmiş ayarları göster" if attr == "aria-label" else ""
    mock_dialog_toggle.inner_text.return_value = "Daha fazla göster"
    mock_dialog_toggle.evaluate.return_value = "BUTTON"
    mock_dialog_toggle.click = MagicMock(side_effect=dialog_toggle_click)

    mock_dialog_editor = MagicMock()
    mock_dialog_editor.is_visible.return_value = True

    mock_ai_radio = MagicMock()
    mock_ai_radio.is_visible.side_effect = lambda *args, **kwargs: expanded_state["open"]

    def _ai_radio_wait_for_side_effect(*args, **kwargs):
        if not expanded_state["open"]:
            raise TimeoutError("not visible")

    mock_ai_radio.wait_for.side_effect = _ai_radio_wait_for_side_effect
    mock_ai_radio.get_attribute.side_effect = lambda attr: "ALTERED_CONTENT_YES" if attr == "name" else "false"

    mock_aud_no = MagicMock()
    mock_aud_no.is_visible.return_value = True
    mock_aud_no.get_attribute.return_value = "true"

    mock_aud_yes = MagicMock()
    mock_aud_yes.is_visible.return_value = True
    mock_aud_yes.get_attribute.return_value = "false"

    def dialog_editor_loc(sel):
        res = MagicMock()
        if "toggle-button" in sel or "Show more" in sel or "Daha fazla" in sel:
            res.first = mock_dialog_toggle
            res.is_visible.return_value = True
        elif "ALTERED_CONTENT_YES" in sel:
            res.first = mock_ai_radio
            res.is_visible = mock_ai_radio.is_visible
            res.wait_for = mock_ai_radio.wait_for
        else:
            res.first.is_visible.return_value = False
            res.first.wait_for.side_effect = TimeoutError("not visible")
        return res

    mock_dialog_editor.locator.side_effect = dialog_editor_loc

    # 3. Active Upload Dialog
    mock_dialog = MagicMock()
    mock_dialog.is_visible.return_value = True
    mock_dialog.count.return_value = 1
    mock_dialog.first = mock_dialog
    mock_dialog.nth.return_value = mock_dialog
    mock_dialog.get_attribute.side_effect = lambda attr: "Sq1nDGQPpOc" if attr == "video-id" else "DETAILS"

    def dialog_loc(sel):
        res = MagicMock()
        if "ytcp-video-metadata-editor" in sel:
            res.first = mock_dialog_editor
            res.count.return_value = 1
            res.is_visible.return_value = True
        elif "toggle-button" in sel or "Show more" in sel or "Daha fazla" in sel:
            res.first = mock_dialog_toggle
            res.is_visible.return_value = True
        elif "ALTERED_CONTENT_YES" in sel:
            res.first = mock_ai_radio
            res.is_visible.return_value = True
        elif "VIDEO_MADE_FOR_KIDS_NOT_MFK" in sel:
            res.first = mock_aud_no
            res.is_visible.return_value = True
        elif "VIDEO_MADE_FOR_KIDS_MFK" in sel:
            res.first = mock_aud_yes
            res.is_visible.return_value = True
        else:
            res.first.is_visible.return_value = False
            res.first.wait_for.side_effect = TimeoutError("not visible")
        return res

    mock_dialog.locator.side_effect = dialog_loc

    # 4. Page Locators
    def page_loc(sel):
        res = MagicMock()
        if "ytcp-uploads-dialog" in sel:
            return mock_dialog
        elif "ytcp-video-metadata-editor" in sel:
            res.first = mock_bg_editor
            res.count.return_value = 2  # 1 in background, 1 in dialog
            return res
        elif "toggle-button" in sel:
            res.count.return_value = 2
            res.first = mock_bg_toggle
            return res
        else:
            res.first.is_visible.return_value = False
            res.first.wait_for.side_effect = TimeoutError("not visible")
            return res

    mock_page.locator.side_effect = page_loc

    observer = YouTubeStudioUIObserver(mock_page)
    ok, msg = observer.set_ai_disclosure(enabled=True, remote_id="Sq1nDGQPpOc")

    assert ok is True
    assert msg == "AI_DISCLOSURE_ENABLED"

    # CRITICAL ASSERTIONS:
    # 1. Background toggle was NEVER clicked
    mock_bg_toggle.click.assert_not_called()
    # 2. Active dialog toggle was clicked exactly once
    mock_dialog_toggle.click.assert_called_once()
    # 3. AI radio was clicked
    mock_ai_radio.click.assert_called_once()
    # 4. Audience state is preserved
    mock_aud_no.get_attribute.assert_called_with("aria-checked")


def test_ai_disclosure_corrupted_audience_fails_safely():
    """Verify that if Audience NO is corrupted during AI disclosure, it fails safely with AUDIENCE_CORRUPTED_BY_AI_DISCLOSURE."""
    mock_page = MagicMock()
    mock_dialog = MagicMock()
    mock_dialog.is_visible.return_value = True
    mock_dialog.count.return_value = 1
    mock_dialog.first = mock_dialog
    mock_dialog.nth.return_value = mock_dialog

    mock_ai_yes = MagicMock()
    mock_ai_yes.is_visible.return_value = True
    mock_ai_yes.get_attribute.side_effect = lambda attr: "ALTERED_CONTENT_YES" if attr == "name" else "true"

    mock_aud_no = MagicMock()
    mock_aud_no.is_visible.return_value = True
    # Corrupted: NO is false
    mock_aud_no.get_attribute.return_value = "false"

    mock_aud_yes = MagicMock()
    mock_aud_yes.is_visible.return_value = True
    mock_aud_yes.get_attribute.return_value = "true"

    def d_loc_side_effect(sel):
        res = MagicMock()
        if "ALTERED_CONTENT_YES" in sel:
            res.first = mock_ai_yes
            res.is_visible.return_value = True
        elif "VIDEO_MADE_FOR_KIDS_NOT_MFK" in sel:
            res.first = mock_aud_no
            res.is_visible.return_value = True
        elif "VIDEO_MADE_FOR_KIDS_MFK" in sel:
            res.first = mock_aud_yes
            res.is_visible.return_value = True
        else:
            res.first.is_visible.return_value = False
            res.first.wait_for.side_effect = TimeoutError("not visible")
        return res

    mock_dialog.locator.side_effect = d_loc_side_effect

    def loc_side_effect(sel):
        if "ytcp-uploads-dialog" in sel:
            return mock_dialog
        return d_loc_side_effect(sel)

    mock_page.locator.side_effect = loc_side_effect
    observer = YouTubeStudioUIObserver(mock_page)
    ok, msg = observer.set_ai_disclosure(enabled=True)

    assert ok is False
    assert "AUDIENCE_CORRUPTED_BY_AI_DISCLOSURE" in msg





