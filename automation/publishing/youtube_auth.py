"""
YouTube OAuth 2.0 authentication manager.
Secures tokens in secrets/youtube/ and provisions authenticated YouTube Data API v3 clients.
"""
import os
import json
import logging
from pathlib import Path
from typing import Optional, Any

logger = logging.getLogger("ReelsAIFactory.YouTubeAuth")

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]

class YouTubeAuthError(Exception):
    pass

class AuthRequiredError(YouTubeAuthError):
    pass

class ReauthRequiredError(YouTubeAuthError):
    pass

class YouTubeAuthManager:
    """Manages YouTube OAuth2 credentials and token lifecycle."""

    @staticmethod
    def get_authenticated_service(
        client_secret_path: Path,
        token_path: Path,
        interactive: bool = False
    ) -> Any:
        """
        Authenticate and return a Google API client for YouTube Data API v3.
        If token is missing or expired and interactive=False, raises AuthRequiredError.
        """
        try:
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build
        except ImportError as e:
            raise YouTubeAuthError(f"Google API client libraries missing: {e}")

        client_secret_path = Path(client_secret_path).resolve()
        token_path = Path(token_path).resolve()

        creds = None

        if token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
                # Verify that existing token has all required scopes
                if creds and hasattr(creds, "has_scopes") and not creds.has_scopes(SCOPES):
                    logger.warning("Existing YouTube token is missing required scopes (e.g. youtube.readonly). Re-authorization required.")
                    creds = None
            except Exception as e:
                logger.warning(f"Failed to load existing token from {token_path.name}: {e}")
                creds = None

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    logger.info("Refreshing expired YouTube OAuth token...")
                    creds.refresh(Request())
                    # Check scopes again after refresh
                    if creds and hasattr(creds, "has_scopes") and not creds.has_scopes(SCOPES):
                        logger.warning("Refreshed token is missing required scopes.")
                        creds = None
                    else:
                        token_path.parent.mkdir(parents=True, exist_ok=True)
                        token_path.write_text(creds.to_json(), encoding="utf-8")
                except Exception as e:
                    logger.warning(f"Failed to refresh token: {e}")
                    creds = None

            if not creds:
                if not client_secret_path.exists():
                    raise AuthRequiredError(
                        f"YouTube OAuth client_secret file not found at: {client_secret_path}\n"
                        "Lütfen Google Cloud Console'dan indirdiğiniz client_secret.json dosyasını 'secrets/youtube/' içine yerleştirin."
                    )

                if interactive:
                    print("\n[YOUTUBE OAUTH] Tarayıcı açılarak Google hesabı yetkilendirmesi başlatılıyor...")
                    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), SCOPES)
                    creds = flow.run_local_server(port=0)
                    token_path.parent.mkdir(parents=True, exist_ok=True)
                    token_path.write_text(creds.to_json(), encoding="utf-8")
                    print("[YOUTUBE OAUTH] Yetkilendirme başarılı! Token kaydedildi.\n")
                else:
                    raise AuthRequiredError(
                        "YouTube OAuth token bulunamadı, süresi doldu veya gerekli yetkiler (youtube.readonly) eksik.\n"
                        "Lütfen önce 'YOUTUBE_LOGIN.bat' dosyasını çalıştırarak giriş yapın."
                    )

        return build("youtube", "v3", credentials=creds, cache_discovery=False)

    @staticmethod
    def verify_authenticated_channel(
        youtube_client: Any,
        expected_handle: str = "@BuiIdVerse",
        expected_channel_id: Optional[str] = None
    ) -> tuple[bool, str, dict]:
        """
        Verify that the authenticated YouTube account matches the expected channel.
        Returns: (is_match: bool, message: str, channel_info_dict: dict)
        """
        try:
            res = youtube_client.channels().list(mine=True, part="snippet,id").execute()
            items = res.get("items", [])
            if not items:
                return False, "No YouTube channel found associated with this Google account.", {"error_type": "NO_CHANNEL"}

            channel = items[0]
            channel_id = channel.get("id", "")
            snippet = channel.get("snippet", {})
            title = snippet.get("title", "")
            custom_url = snippet.get("customUrl", "")

            # Normalize handles for comparison (e.g. "@BuiIdVerse" vs "@buiidverse" vs "buiidverse")
            exp_norm = expected_handle.strip().lstrip("@").lower()
            act_norm = custom_url.strip().lstrip("@").lower() if custom_url else ""

            is_match = False
            if expected_channel_id and channel_id == expected_channel_id:
                is_match = True
            elif act_norm and act_norm == exp_norm:
                is_match = True
            elif exp_norm and exp_norm in title.lower():
                is_match = True

            info = {
                "channel_id": channel_id,
                "title": title,
                "custom_url": custom_url,
                "handle": f"@{act_norm}" if act_norm else (custom_url or "None"),
                "is_match": is_match
            }

            if is_match:
                return True, f"YouTube Channel Verified: {title} ({custom_url or channel_id})", info
            else:
                info["error_type"] = "ACCOUNT_MISMATCH"
                return False, f"ACCOUNT_MISMATCH: Expected '{expected_handle}', authenticated as '{custom_url or title}' ({channel_id})", info

        except Exception as e:
            err_str = str(e)
            if "insufficient" in err_str.lower() or "403" in err_str or "forbidden" in err_str.lower() or "permission" in err_str.lower():
                return False, (
                    "REAUTH_REQUIRED: YouTube OAuth token lacks required readonly permissions (403 insufficientPermissions). "
                    "Lütfen 'YOUTUBE_LOGIN.bat' dosyasını çalıştırarak yetkilendirmeyi yenileyin."
                ), {"error_type": "REAUTH_REQUIRED", "raw_error": err_str}

            return False, f"Channel verification request failed: {e}", {"error_type": "API_ERROR", "raw_error": err_str}

