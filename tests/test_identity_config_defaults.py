"""
The code must not ship anyone's Telegram or Instagram identifiers as defaults.
With the variables unset, Telegram approvals and the Instagram target fail closed,
and the Railway preflight checks the configured account instead of a hardcoded one.
All values below are fictional; nothing here talks to Telegram or Meta.
"""
from unittest.mock import MagicMock

import pytest

from automation.cloud.approval_service import ApprovalService
from automation.cloud.cloud_preflight import run_cloud_preflight
from automation.cloud.config import CloudConfig
from automation.cloud.database import Database
from automation.cloud.models import TelegramApproval, TelegramApprovalStatus
from automation.cloud.railway_production_preflight import run_railway_preflight
from automation.cloud.security import verify_telegram_chat, verify_telegram_user
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


def test_telegram_allow_lists_fail_closed_when_unconfigured(caplog):
    # An unset TELEGRAM_CHAT_ID used to mean "accept every chat".
    with caplog.at_level("WARNING", logger="ReelsAIFactory.Security"):
        assert verify_telegram_chat(DEMO_TELEGRAM_ID, None) is False
        assert verify_telegram_chat(None, None) is False
        assert verify_telegram_user(DEMO_TELEGRAM_ID, None) is False
    assert "TELEGRAM_CHAT_ID is not set" in caplog.text
    assert "TELEGRAM_ALLOWED_USER_ID is not set" in caplog.text


def test_configured_telegram_allow_lists_behave_as_before():
    assert verify_telegram_user(DEMO_TELEGRAM_ID, DEMO_TELEGRAM_ID) is True
    assert verify_telegram_user(DEMO_TELEGRAM_ID + 1, DEMO_TELEGRAM_ID) is False
    assert verify_telegram_user(None, DEMO_TELEGRAM_ID) is False
    assert verify_telegram_chat(-100424242, -100424242) is True
    assert verify_telegram_chat(-100424243, -100424242) is False
    # An update without a chat (inline message) is still left to the user check.
    assert verify_telegram_chat(None, -100424242) is True


def test_allowed_user_cannot_approve_while_telegram_chat_id_is_unset(tmp_path, no_identity_env):
    no_identity_env.setenv("TELEGRAM_ALLOWED_USER_ID", str(DEMO_TELEGRAM_ID))
    cfg = CloudConfig(tmp_path)
    cfg.database_url = f"sqlite:///{tmp_path / 'cloud.db'}"
    assert cfg.telegram_chat_id is None
    db = Database(cfg.database_url)
    bot = MagicMock(spec=TelegramBotClient)
    approval_svc = ApprovalService(cfg, db, bot)

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
        "message": {"chat": {"id": 777000}, "message_id": 1},
        "data": "weekly_approve:APPR-DEMO",
    })
    assert res == {"status": "UNAUTHORIZED", "message": "Unauthorized chat ID"}
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


def _cloud_preflight(tmp_path, monkeypatch, capsys, **env):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'cloud.db'}")
    monkeypatch.setenv("MEDIA_STORAGE_BACKEND", "local")
    monkeypatch.setenv("META_ACCESS_TOKEN", "EAABvalidtoken123")
    monkeypatch.setenv("INSTAGRAM_ACCOUNT_ID", DEMO_IG_ACCOUNT_ID)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    ok, errors = run_cloud_preflight(tmp_path)
    return ok, errors, capsys.readouterr().out


@pytest.mark.parametrize("worker_key", ["", "change-me", "reels_ai_local_worker_key_dev"])
def test_cloud_preflight_fails_when_the_server_would_disable_the_worker_api(
        tmp_path, no_identity_env, capsys, worker_key):
    ok, errors, out = _cloud_preflight(tmp_path, no_identity_env, capsys,
                                       LOCAL_WORKER_API_KEY=worker_key,
                                       INSTAGRAM_EXPECTED_USERNAME=DEMO_IG_USERNAME)
    assert ok is False
    assert [e for e in errors if "5/5" in e] == [
        "[FAIL 5/5] LOCAL_WORKER_API_KEY is empty or still a template value (change-me)."]
    assert "[PASS 5/5]" not in out


def test_cloud_preflight_names_the_target_or_says_it_is_not_set(tmp_path, no_identity_env, capsys):
    ok, errors, out = _cloud_preflight(tmp_path, no_identity_env, capsys,
                                       LOCAL_WORKER_API_KEY="demo-worker-key-0123456789")
    assert (ok, errors) == (True, [])
    assert "[PASS 4/5] Meta credentials configured (INSTAGRAM_EXPECTED_USERNAME not set)." in out
    assert "for @." not in out

    no_identity_env.setenv("INSTAGRAM_EXPECTED_USERNAME", f"@{DEMO_IG_USERNAME}")
    ok, _, out = _cloud_preflight(tmp_path, no_identity_env, capsys,
                                  LOCAL_WORKER_API_KEY="demo-worker-key-0123456789")
    assert ok is True
    assert f"[PASS 4/5] Meta credentials configured (@{DEMO_IG_USERNAME})." in out


def test_instagram_preflight_requires_expected_username():
    cfg = InstagramConfig(access_token="EAABvalidtoken123", account_id=DEMO_IG_ACCOUNT_ID, expected_username="")
    client = MagicMock(spec=InstagramAPIClient)
    client.config = cfg

    success, status, diag = InstagramPreflightRunner(cfg, client=client).run_preflight()
    assert success is False
    assert status == "NEEDS_USER_META_SETUP"
    assert any("MISSING_INSTAGRAM_EXPECTED_USERNAME" in err for err in diag["errors"])
    client.get_me.assert_not_called()


@pytest.mark.parametrize("account_id, username, expected_error", [
    (DEMO_IG_ACCOUNT_ID, "your-instagram-username", "MISSING_INSTAGRAM_EXPECTED_USERNAME"),
    (DEMO_IG_ACCOUNT_ID, "@your-instagram-username", "MISSING_INSTAGRAM_EXPECTED_USERNAME"),
    ("your-instagram-business-account-id", DEMO_IG_USERNAME, "INVALID_INSTAGRAM_ACCOUNT_ID"),
])
def test_instagram_preflight_rejects_template_values_before_any_api_call(account_id, username,
                                                                         expected_error):
    # The template values used to pass the config step, so the preflight queried the
    # Graph API for an account called "your-instagram-business-account-id".
    cfg = InstagramConfig(access_token="EAABvalidtoken123", account_id=account_id, expected_username=username)
    client = MagicMock(spec=InstagramAPIClient)
    client.config = cfg

    success, status, diag = InstagramPreflightRunner(cfg, client=client).run_preflight()
    assert (success, status) == (False, "NEEDS_USER_META_SETUP")
    assert len(diag["errors"]) == 1
    assert diag["errors"][0].startswith(expected_error)
    client.get_me.assert_not_called()
    client.get_account_info.assert_not_called()


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
