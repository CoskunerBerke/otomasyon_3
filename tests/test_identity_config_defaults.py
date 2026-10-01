"""
The code must not ship anyone's Telegram or Instagram identifiers as defaults.
With the variables unset, Telegram approvals and the Instagram target fail closed,
and the Railway preflight checks the configured account instead of a hardcoded one.
All values below are fictional; nothing here talks to Telegram or Meta.
"""
from unittest.mock import MagicMock

import pytest

from automation.cloud.approval_service import ApprovalService
from automation.cloud.config import CloudConfig
from automation.cloud.database import Database
from automation.cloud.models import TelegramApproval, TelegramApprovalStatus
from automation.cloud.railway_production_preflight import run_railway_preflight
from automation.cloud.telegram_bot import TelegramBotClient
from automation.publishing.instagram_api import InstagramAPIClient
from automation.publishing.instagram_live_test import EXIT_ACCOUNT_MISMATCH, InstagramLiveTestRunner
from automation.publishing.instagram_models import InstagramConfig
from automation.publishing.instagram_preflight import InstagramPreflightRunner

IDENTITY_ENV_KEYS = (
    "TELEGRAM_ALLOWED_USER_ID",
    "TELEGRAM_CHAT_ID",
    "INSTAGRAM_ACCOUNT_ID",
    "INSTAGRAM_EXPECTED_USERNAME",
)
DEMO_TELEGRAM_ID = 424242
DEMO_IG_ACCOUNT_ID = "17841400000000099"
DEMO_IG_USERNAME = "demo_reels_studio"


@pytest.fixture(autouse=True)
def no_identity_env(monkeypatch):
    # tmp_path is passed as base_dir everywhere, so no .env file can re-inject these.
    for key in IDENTITY_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    return monkeypatch


def test_unset_identity_variables_have_no_builtin_defaults(tmp_path):
    cfg = CloudConfig(tmp_path)
    assert cfg.telegram_allowed_user_id is None
    assert cfg.telegram_chat_id is None
    assert cfg.instagram_account_id == ""
    assert cfg.instagram_expected_username == ""

    cfg.telegram_bot_token = "123456:demo-token"
    assert cfg.is_telegram_configured is False
    assert InstagramConfig().expected_username == ""
    assert InstagramConfig().account_id == ""


def test_identity_variables_are_read_from_the_environment(tmp_path, no_identity_env):
    no_identity_env.setenv("TELEGRAM_ALLOWED_USER_ID", str(DEMO_TELEGRAM_ID))
    no_identity_env.setenv("TELEGRAM_CHAT_ID", "-100424242")
    no_identity_env.setenv("INSTAGRAM_ACCOUNT_ID", DEMO_IG_ACCOUNT_ID)
    no_identity_env.setenv("INSTAGRAM_EXPECTED_USERNAME", DEMO_IG_USERNAME)

    cfg = CloudConfig(tmp_path)
    assert cfg.telegram_allowed_user_id == DEMO_TELEGRAM_ID
    assert cfg.telegram_chat_id == -100424242
    assert cfg.instagram_account_id == DEMO_IG_ACCOUNT_ID
    assert cfg.instagram_expected_username == DEMO_IG_USERNAME


def test_approval_is_not_sent_and_callbacks_are_refused_without_telegram_ids(tmp_path):
    cfg = CloudConfig(tmp_path)
    cfg.database_url = f"sqlite:///{tmp_path / 'cloud.db'}"
    db = Database(cfg.database_url)
    bot = MagicMock(spec=TelegramBotClient)
    approval_svc = ApprovalService(cfg, db, bot)

    ok, approval_id = approval_svc.create_and_send_approval("2099-W01", "2099-W02")
    assert (ok, approval_id) == (False, None)
    bot.send_message.assert_not_called()

    db.save_approval(TelegramApproval(
        approval_id="APPR-DEMO",
        week_id="2099-W01",
        next_week_id="2099-W02",
        status=TelegramApprovalStatus.PENDING,
        telegram_message_id=1,
        telegram_chat_id=DEMO_TELEGRAM_ID,
    ))
    res = approval_svc.handle_callback_query({
        "id": "cb_demo",
        "from": {"id": DEMO_TELEGRAM_ID},
        "message": {"chat": {"id": DEMO_TELEGRAM_ID}, "message_id": 1},
        "data": "weekly_approve:APPR-DEMO",
    })
    assert res["status"] == "UNAUTHORIZED"
    assert db.get_approval("APPR-DEMO").status == TelegramApprovalStatus.PENDING
    assert db.get_next_pending_command() is None


def _check_8_errors(tmp_path, monkeypatch, **env):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    _, _, messages = run_railway_preflight(tmp_path)
    return [m for m in messages if "8/17" in m]


def test_railway_preflight_fails_when_instagram_target_is_unset(tmp_path, no_identity_env):
    errors = _check_8_errors(tmp_path, no_identity_env)
    assert len(errors) == 1
    assert "INSTAGRAM_ACCOUNT_ID" in errors[0]


def test_railway_preflight_fails_on_template_placeholders(tmp_path, no_identity_env):
    errors = _check_8_errors(
        tmp_path, no_identity_env,
        INSTAGRAM_ACCOUNT_ID="your-instagram-business-account-id",
        INSTAGRAM_EXPECTED_USERNAME="your-instagram-username",
    )
    assert len(errors) == 1

    errors = _check_8_errors(
        tmp_path, no_identity_env,
        INSTAGRAM_ACCOUNT_ID=DEMO_IG_ACCOUNT_ID,
        INSTAGRAM_EXPECTED_USERNAME="your-instagram-username",
    )
    assert len(errors) == 1
    assert "INSTAGRAM_EXPECTED_USERNAME" in errors[0]


def test_railway_preflight_accepts_any_configured_instagram_target(tmp_path, no_identity_env):
    # Before, check 8 passed only for one hardcoded account, so every other deployer failed it.
    errors = _check_8_errors(
        tmp_path, no_identity_env,
        INSTAGRAM_ACCOUNT_ID=DEMO_IG_ACCOUNT_ID,
        INSTAGRAM_EXPECTED_USERNAME=DEMO_IG_USERNAME,
    )
    assert errors == []


def test_instagram_preflight_requires_expected_username():
    cfg = InstagramConfig(access_token="EAABvalidtoken123", account_id=DEMO_IG_ACCOUNT_ID, expected_username="")
    client = MagicMock(spec=InstagramAPIClient)
    client.config = cfg

    success, status, diag = InstagramPreflightRunner(cfg, client=client).run_preflight()
    assert success is False
    assert status == "NEEDS_USER_META_SETUP"
    assert any("MISSING_INSTAGRAM_EXPECTED_USERNAME" in err for err in diag["errors"])
    client.get_me.assert_not_called()


def test_instagram_live_runner_refuses_to_start_without_a_configured_account(tmp_path):
    runner = InstagramLiveTestRunner(tmp_path, state_file=tmp_path / "state.json")
    runner.config.access_token = "EAABvalidtoken123"
    client = MagicMock(spec=InstagramAPIClient)
    client.config = runner.config
    runner.client = client

    ok, result, exit_code = runner.run()
    assert ok is False
    assert exit_code == EXIT_ACCOUNT_MISMATCH
    assert result.error_code == "ACCOUNT_NOT_CONFIGURED"
    client.get_account_info.assert_not_called()
    client.publish_media.assert_not_called()
