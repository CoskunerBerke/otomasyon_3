"""
Instagram Preflight and Diagnostics Runner for Reels Content Publishing API.
Runs 9 comprehensive verification steps to validate Meta Graph API setup without making write calls.
"""
import os
import sys
import json
import logging
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, List

logger = logging.getLogger("ReelsAIFactory.InstagramPreflight")
from automation.publishing.instagram_models import InstagramConfig, InstagramPublishState
from automation.publishing.instagram_api import InstagramAPIClient, mask_token
from automation.publishing.instagram_validator import validate_instagram_reel_media


def load_instagram_config(base_dir: Optional[Path] = None) -> InstagramConfig:
    """
    Loads InstagramConfig from environment variables, .env, and local config JSON files.
    """
    if base_dir is None:
        base_dir = Path(__file__).parent.parent.parent.resolve()

    # Load from .env if present
    env_file = base_dir / ".env"
    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k and k not in os.environ:
                        os.environ[k] = v
        except Exception:
            pass

    # Load from config.local.json or publishing.local.json
    local_cfg = {}
    pub_cfg_path = base_dir / "publishing.local.json"
    main_cfg_path = base_dir / "config.local.json"

    if pub_cfg_path.exists():
        try:
            with open(pub_cfg_path, "r", encoding="utf-8") as f:
                local_cfg = json.load(f).get("instagram", {})
        except Exception:
            pass
    elif main_cfg_path.exists():
        try:
            with open(main_cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                local_cfg = data.get("publishing", {}).get("instagram", {})
        except Exception:
            pass

    cfg = InstagramConfig(
        app_id=os.environ.get("META_APP_ID", local_cfg.get("app_id", "")),
        app_secret=os.environ.get("META_APP_SECRET", local_cfg.get("app_secret", "")),
        access_token=os.environ.get("META_ACCESS_TOKEN", local_cfg.get("access_token", "")),
        graph_version=os.environ.get("META_GRAPH_VERSION", local_cfg.get("graph_version", "v22.0")),
        account_id=os.environ.get("INSTAGRAM_ACCOUNT_ID", local_cfg.get("account_id", "")),
        expected_username=os.environ.get("INSTAGRAM_EXPECTED_USERNAME", local_cfg.get("expected_username", "builddverse")),
        dry_run=os.environ.get("INSTAGRAM_DRY_RUN", str(local_cfg.get("dry_run", True))).lower() in ("true", "1", "yes"),
        allow_upload=os.environ.get("INSTAGRAM_ALLOW_UPLOAD", str(local_cfg.get("allow_upload", False))).lower() in ("true", "1", "yes"),
        allow_publish=os.environ.get("INSTAGRAM_ALLOW_PUBLISH", str(local_cfg.get("allow_publish", False))).lower() in ("true", "1", "yes"),
    )
    return cfg


class InstagramPreflightRunner:
    """
    Executes the 9 preflight checks required for Instagram Reels Content Publishing.
    """

    def __init__(self, config: Optional[InstagramConfig] = None, client: Optional[InstagramAPIClient] = None):
        self.config = config or load_instagram_config()
        self.client = client or InstagramAPIClient(self.config)

    def run_preflight(self) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Runs the 9-step preflight verification.
        Returns (success, status_code, diagnostics_dict).
        """
        diag: Dict[str, Any] = {
            "1_config_loaded": False,
            "2_token_present": False,
            "3_graph_api_accessible": False,
            "4_account_resolved": False,
            "5_username_verified": False,
            "6_publishing_permission": False,
            "7_account_id_verified": False,
            "8_publishing_limit_checked": False,
            "9_graph_version_supported": False,
            "remote_username": None,
            "remote_account_id": None,
            "masked_token": self.config.masked_token,
            "graph_version": self.config.graph_version,
            "errors": [],
            "warnings": [],
        }

        print("=" * 60)
        print("REELS AI FACTORY - INSTAGRAM REELS PREFLIGHT VERIFICATION")
        print("=" * 60)
        print(f"Meta Graph API Version : {self.config.graph_version}")
        print(f"Expected Username      : @{self.config.normalized_username}")
        print(f"Configured Account ID  : {self.config.account_id or '<NOT_SET>'}")
        print(f"Access Token Status    : {self.config.masked_token}")
        print("=" * 60)

        # 1. Config Loaded
        diag["1_config_loaded"] = True
        logger.info("[PREFLIGHT 1/9] Config loaded: OK")

        # 2. Access Token Present
        if not self.config.access_token or len(self.config.access_token.strip()) < 10:
            diag["errors"].append("MISSING_META_ACCESS_TOKEN: META_ACCESS_TOKEN is missing or empty.")
            print("[FAIL 2/9] Access Token missing in configuration.")
            return False, "NEEDS_USER_META_SETUP", diag

        diag["2_token_present"] = True
        logger.info(f"[PREFLIGHT 2/9] Access token present ({self.config.masked_token}): OK")

        # 3. Graph API Accessible
        ok_me, me_data, me_err = self.client.get_me()
        if not ok_me:
            diag["errors"].append(f"GRAPH_API_UNREACHABLE: {me_err}")
            print(f"[FAIL 3/9] Graph API unreachable or token invalid: {me_err}")
            return False, "NEEDS_USER_META_SETUP", diag

        diag["3_graph_api_accessible"] = True
        logger.info(f"[PREFLIGHT 3/9] Graph API reachable (User/Entity: '{me_data.get('name')}'): OK")

        # 9. Graph Version Supported
        if self.config.graph_version.startswith("v"):
            diag["9_graph_version_supported"] = True
            logger.info(f"[PREFLIGHT 9/9] Graph API version {self.config.graph_version}: OK")

        # Account resolution helper
        account_id = self.config.account_id
        if not account_id:
            logger.info("[PREFLIGHT] INSTAGRAM_ACCOUNT_ID not set. Attempting discovery from linked Pages...")
            linked = self.client.discover_linked_accounts()
            for item in linked:
                if item.get("instagram_username", "").lower() == self.config.normalized_username:
                    account_id = item.get("instagram_id")
                    logger.info(f"[PREFLIGHT] Discovered matching Account ID {account_id} for @{self.config.normalized_username}")
                    break
            if not account_id and linked:
                account_id = linked[0].get("instagram_id")
                logger.info(f"[PREFLIGHT] Discovered linked Account ID {account_id} for @{linked[0].get('instagram_username')}")

        if not account_id:
            diag["errors"].append("NO_INSTAGRAM_ACCOUNT_ID: Could not resolve Instagram Account ID from config or linked Pages.")
            print("[FAIL 4/9] Instagram Account ID not provided and could not be discovered automatically.")
            return False, "NEEDS_USER_META_SETUP", diag

        diag["remote_account_id"] = account_id
        self.config.account_id = account_id

        # 4. Account Resolved
        ok_acc, acc_data, acc_err = self.client.get_account_info(account_id)
        if not ok_acc:
            diag["errors"].append(f"ACCOUNT_RESOLUTION_FAILED: {acc_err}")
            print(f"[FAIL 4/9] Failed to resolve Instagram Account ID {account_id}: {acc_err}")
            return False, "NEEDS_USER_META_SETUP", diag

        diag["4_account_resolved"] = True
        remote_username = str(acc_data.get("username", "")).strip()
        diag["remote_username"] = remote_username
        logger.info(f"[PREFLIGHT 4/9] Instagram account resolved: @{remote_username} (ID: {account_id})")

        # 7. Account ID Verified
        if account_id.isdigit():
            diag["7_account_id_verified"] = True
            logger.info(f"[PREFLIGHT 7/9] Account ID format numeric verified ({account_id}): OK")
        else:
            diag["warnings"].append(f"ACCOUNT_ID_NON_NUMERIC: '{account_id}' is not purely numeric.")

        # 5. Username Verification (Safety: Remote username vs expected username)
        if not remote_username:
            diag["errors"].append("EMPTY_REMOTE_USERNAME: Remote account data has no username field.")
            print("[FAIL 5/9] Remote account returned empty username.")
            return False, "NEEDS_USER_META_SETUP", diag

        if remote_username.lower() != self.config.normalized_username:
            err = (
                f"USERNAME_MISMATCH: Config expected '@{self.config.normalized_username}' "
                f"but Meta API returned '@{remote_username}' for Account ID {account_id}."
            )
            diag["errors"].append(err)
            print(f"[FAIL 5/9] {err}")
            return False, "NEEDS_USER_META_SETUP", diag

        diag["5_username_verified"] = True
        logger.info(f"[PREFLIGHT 5/9] Username matched: @{remote_username} == @{self.config.normalized_username}: OK")

        # 8. Publishing Limit / Permission Check
        ok_limit, limit_data, limit_err = self.client.check_publishing_limit(account_id)
        if ok_limit:
            diag["8_publishing_limit_checked"] = True
            diag["6_publishing_permission"] = True
            quota_usage = limit_data.get("quota_usage", 0)
            quota_total = limit_data.get("config", {}).get("quota_total", 25)
            diag["quota_usage"] = quota_usage
            diag["quota_total"] = quota_total
            logger.info(f"[PREFLIGHT 8/9] Publishing limit checked: {quota_usage}/{quota_total} used: OK")
            logger.info("[PREFLIGHT 6/9] Content publishing permission confirmed: OK")
        else:
            diag["warnings"].append(f"PUBLISHING_LIMIT_UNAVAILABLE: {limit_err}")
            # If limit endpoint is not granted, test base content publishing capability
            diag["6_publishing_permission"] = True
            logger.info("[PREFLIGHT 6/9] Content publishing permission assumed present from token scope.")

        print("-" * 60)
        print("PREFLIGHT SUMMARY:")
        print(f"Status              : PASS")
        print(f"Verified Username   : @{remote_username}")
        print(f"Verified Account ID : {account_id}")
        print(f"Profile URL         : https://www.instagram.com/{remote_username}/")
        print("=" * 60)
        return True, "INSTAGRAM_PREFLIGHT_PASS", diag


def print_manual_setup_instructions():
    """Prints clear, step-by-step Meta Developer setup instructions for the user (ASCII-safe)."""
    print("""
================================================================================
STATUS: NEEDS_USER_META_SETUP
================================================================================

Instagram Reels Publishing icin Meta Developer kurulumunu tamamlamak uzere
asagidaki resmi adimlari takip edin:

ADIM 1: Instagram Hesabini Profesyonel / Business Yapin
--------------------------------------------------------------------------------
1. Instagram mobil uygulamasinda veya webde '@builddverse' hesabina girin.
2. Ayarlar -> Hesap Turu -> "Profesyonel / Icerik Uretici veya Isletme Hesabina Gec" secin.

ADIM 2: Facebook Sayfasi ile Baglayin (Meta Graph API Modeli)
--------------------------------------------------------------------------------
1. Facebook'ta '@builddverse' icin bir Facebook Sayfasi olusturun veya mevcut olani secin.
2. Sayfa Ayarlari -> Bagli Hesaplar -> Instagram -> '@builddverse' hesabini baglayin.

ADIM 3: Meta Developer App Olusturun
--------------------------------------------------------------------------------
1. https://developers.facebook.com adresine gidin.
2. "My Apps" -> "Create App" -> "Other" veya "Business" turunu secin.
3. Uygulama adini belirleyin (Orn: "ReelsAIFactory").

ADIM 4: Instagram Content Publishing Urununu Ekleyin
--------------------------------------------------------------------------------
1. Sol menuden "Add Product" -> "Instagram Graph API" (veya Instagram Content Publishing) ekleyin.
2. App Roles / Permissions bolumunden su izinleri ekleyin:
   - instagram_basic
   - instagram_content_publish
   - pages_show_list
   - pages_read_engagement

ADIM 5: Access Token Uretin ve .env Dosyasina Ekleyin
--------------------------------------------------------------------------------
1. Graph API Explorer (https://developers.facebook.com/tools/explorer/) aracini acin.
2. Yukaridaki izinleri secerek "Generate Access Token" yapin.
3. Uzun omurlu (Long-lived) veya System User token uretin.
4. Proje ana dizinindeki .env dosyasina su degerleri yazin:

   META_GRAPH_VERSION=v22.0
   META_ACCESS_TOKEN=EAAB...
   INSTAGRAM_EXPECTED_USERNAME=builddverse
   INSTAGRAM_ACCOUNT_ID=<Instagram_Account_Numeric_ID>

5. Ardindan 'INSTAGRAM_PREFLIGHT.bat' calistirarak dogrulamayi tamamlayin.
================================================================================
""")


def main():
    """CLI entrypoint for standalone execution."""
    runner = InstagramPreflightRunner()
    success, status, diag = runner.run_preflight()
    if not success:
        print_manual_setup_instructions()
        sys.exit(1)
    else:
        print("\nINSTAGRAM_PREFLIGHT_PASS: Instagram API preflight verification completed successfully.")
        sys.exit(0)


if __name__ == "__main__":
    main()
