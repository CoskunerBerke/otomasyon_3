"""
End-to-end integration test with MockVideoProvider (0 credit usage).
"""
import json
import pytest
from pathlib import Path
from automation.run import run_pipeline

def test_full_pipeline_mock_run(tmp_path: Path):
    vault_dir = tmp_path / "Mock_Vault"
    output_dir = tmp_path / "Mock_Output"

    # Set up mock vault structure
    for folder in ["00_SYSTEM", "01_TOPICS", "02_IDEAS", "03_SCRIPTS", "04_PRODUCTION", "05_READY", "06_PUBLISHED", "07_REJECTED", "09_TEMPLATES"]:
        (vault_dir / folder).mkdir(parents=True, exist_ok=True)

    # Write config file for test
    test_config = tmp_path / "test_config.json"
    config_data = {
        "vault_path": str(vault_dir),
        "output_path": str(output_dir),
        "videos_per_run": 2,
        "video_duration": 5,
        "video_ratio": "9:16",
        "audio_enabled": False,
        "generation_timeout_minutes": 5,
        "max_retries_per_video": 1,
        "browser_headless": True,
        "reject_wrong_ratio": True
    }
    test_config.write_text(json.dumps(config_data), encoding="utf-8")

    # Run pipeline with mock flow and mock notification provider
    from automation.notifications.windows import MockNotificationProvider
    mock_notif = MockNotificationProvider()

    exit_code = run_pipeline(
        count=2,
        dry_run=False,
        config_path=str(test_config),
        mock_flow=True,
        notification_provider=mock_notif
    )

    assert exit_code == 0
    assert len(mock_notif.sent_notifications) == 1
    assert mock_notif.sent_notifications[0]["count"] == 2
    assert "2 yeni Reel hazır" in mock_notif.sent_notifications[0]["message"]

    # Verify vault notes moved to 05_READY
    ready_notes = list((vault_dir / "05_READY").glob("*.md"))
    assert len(ready_notes) == 2

    # Verify notes contain READY status
    for note in ready_notes:
        content = note.read_text(encoding="utf-8")
        assert "status: READY" in content
        assert "Teknik QC (FFprobe):** PASS" in content

    # Verify desktop output files
    today_folders = list(output_dir.glob("20*"))
    assert len(today_folders) == 1
    today_folder = today_folders[0]

    mp4_files = list(today_folder.glob("*.mp4"))
    json_files = list(today_folder.glob("*.json"))

    assert len(mp4_files) == 2
    assert len(json_files) == 2

    # Verify metadata JSON
    sample_json = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert sample_json["status"] == "READY"
    assert sample_json["provider"] == "google_flow"
    assert sample_json["qc_summary"]["technical_pass"] is True
