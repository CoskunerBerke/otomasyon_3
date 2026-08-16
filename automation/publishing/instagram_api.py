"""
Meta Instagram Content Publishing / Reels Publishing API Client.
Official Graph API client supporting resumable local video upload, rate limit checks,
async processing polling, and safe preflight verification.
"""
import os
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
import requests

logger = logging.getLogger("ReelsAIFactory.InstagramAPI")
from automation.publishing.instagram_models import (
    InstagramConfig,
    InstagramPublishRequest,
    InstagramPublishResult,
    InstagramPublishState,
)


def mask_token(token: Optional[str]) -> str:
    """Masks an access token for safe logging (e.g. EAAB...x92)."""
    if not token:
        return "<EMPTY_TOKEN>"
    tok = token.strip()
    if len(tok) <= 8:
        return "***"
    return f"{tok[:4]}...{tok[-4:]}"


class InstagramAPIClient:
    """
    Official Meta Instagram Graph API Client for Reels Content Publishing.
    Follows Meta's official resumable upload and publishing lifecycle.
    """

    def __init__(self, config: Optional[InstagramConfig] = None):
        self.config = config or InstagramConfig()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "ReelsAIFactory/3.0 (Meta Instagram Reels Publisher)"
        })
        self.base_url = f"https://graph.facebook.com/{self.config.graph_version}"

    def _sanitize_error_message(self, msg: str) -> str:
        """Removes full access token strings from any error message."""
        if self.config.access_token and self.config.access_token in msg:
            return msg.replace(self.config.access_token, self.config.masked_token)
        return msg

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
        json_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, Any]] = None,
        is_absolute_url: bool = False,
        retry_transient: bool = True
    ) -> requests.Response:
        """
        Executes an HTTP request against Meta Graph API with retry on 429/5xx and timeouts.
        Never retries on fatal 4xx (400, 401, 403) authentication/permission errors.
        """
        url = endpoint if is_absolute_url else f"{self.base_url}/{endpoint.lstrip('/')}"
        req_params = dict(params or {})

        # Automatically append access_token if not already in URL or headers
        if not is_absolute_url and "access_token" not in req_params:
            if self.config.access_token:
                req_params["access_token"] = self.config.access_token

        req_headers = dict(headers or {})
        timeout = (10, self.config.timeout_seconds)  # (connect_timeout, read_timeout)

        attempt = 0
        max_attempts = self.config.max_retries if retry_transient else 1

        while attempt < max_attempts:
            attempt += 1
            try:
                resp = self.session.request(
                    method=method,
                    url=url,
                    params=req_params,
                    data=data,
                    json=json_data,
                    headers=req_headers,
                    timeout=timeout
                )

                # Successful response or fatal client error
                if resp.status_code < 400:
                    return resp

                # Check for rate limit (429) or server error (5xx)
                if resp.status_code == 429 or resp.status_code >= 500:
                    if attempt < max_attempts:
                        backoff = 2 ** attempt
                        logger.warning(
                            f"[INSTAGRAM API] Transient error HTTP {resp.status_code}. "
                            f"Retrying attempt {attempt + 1}/{max_attempts} after {backoff}s..."
                        )
                        time.sleep(backoff)
                        continue

                # Fatal client error or exhausted retries
                return resp

            except (requests.exceptions.ConnectTimeout, requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError) as e:
                if attempt < max_attempts and retry_transient:
                    backoff = 2 ** attempt
                    logger.warning(
                        f"[INSTAGRAM API] Network error: {e.__class__.__name__}. "
                        f"Retrying attempt {attempt + 1}/{max_attempts} after {backoff}s..."
                    )
                    time.sleep(backoff)
                else:
                    raise

        return resp

    # =========================================================================
    # 1. ACCOUNT VERIFICATION & DISCOVERY
    # =========================================================================

    def get_me(self) -> Tuple[bool, Dict[str, Any], Optional[str]]:
        """Verifies access token by requesting /me."""
        try:
            resp = self._request("GET", "/me", params={"fields": "id,name"})
            data = resp.json()
            if resp.status_code == 200:
                logger.info(f"[INSTAGRAM API] Token verified for Meta entity: {data.get('name')} (ID: {data.get('id')})")
                return True, data, None
            err_msg = self._sanitize_error_message(data.get("error", {}).get("message", resp.text))
            return False, data, f"HTTP_{resp.status_code}: {err_msg}"
        except Exception as e:
            return False, {}, self._sanitize_error_message(str(e))

    def get_account_info(self, account_id: Optional[str] = None) -> Tuple[bool, Dict[str, Any], Optional[str]]:
        """
        Fetches remote Instagram professional account details (id, username, name).
        """
        target_id = account_id or self.config.account_id
        if not target_id:
            return False, {}, "NO_ACCOUNT_ID_CONFIGURED"

        try:
            resp = self._request(
                "GET",
                f"/{target_id}",
                params={"fields": "id,username,name,profile_picture_url"}
            )
            data = resp.json()
            if resp.status_code == 200:
                username = data.get("username", "")
                logger.info(
                    f"[INSTAGRAM API] Resolved Instagram account: @{username} "
                    f"(ID: {data.get('id')}, Name: '{data.get('name')}')"
                )
                return True, data, None
            err_msg = self._sanitize_error_message(data.get("error", {}).get("message", resp.text))
            return False, data, f"HTTP_{resp.status_code}: {err_msg}"
        except Exception as e:
            return False, {}, self._sanitize_error_message(str(e))

    def discover_linked_accounts(self) -> List[Dict[str, Any]]:
        """
        Discovers Instagram Business/Creator accounts linked to the user's Facebook Pages.
        """
        discovered = []
        try:
            resp = self._request(
                "GET",
                "/me/accounts",
                params={"fields": "id,name,instagram_business_account{id,username,name}"}
            )
            if resp.status_code == 200:
                pages = resp.json().get("data", [])
                for p in pages:
                    ig_acc = p.get("instagram_business_account")
                    if ig_acc:
                        discovered.append({
                            "page_id": p.get("id"),
                            "page_name": p.get("name"),
                            "instagram_id": ig_acc.get("id"),
                            "instagram_username": ig_acc.get("username"),
                            "instagram_name": ig_acc.get("name"),
                        })
        except Exception as e:
            logger.debug(f"[INSTAGRAM API] Account discovery error: {e}")
        return discovered

    # =========================================================================
    # 2. CONTENT PUBLISHING LIMIT CHECK
    # =========================================================================

    def check_publishing_limit(self, account_id: Optional[str] = None) -> Tuple[bool, Dict[str, Any], Optional[str]]:
        """
        Checks the Instagram content publishing quota usage for the account.
        Standard limit is 25 posts/reels per 24 hours.
        """
        target_id = account_id or self.config.account_id
        if not target_id:
            return False, {}, "NO_ACCOUNT_ID_CONFIGURED"

        try:
            resp = self._request(
                "GET",
                f"/{target_id}/content_publishing_limit",
                params={"fields": "config,quota_usage"}
            )
            data = resp.json()
            if resp.status_code == 200:
                quota_data = data.get("data", [{}])[0] if data.get("data") else data
                usage = quota_data.get("quota_usage", 0)
                config_info = quota_data.get("config", {})
                total = config_info.get("quota_total", 25)
                logger.info(f"[INSTAGRAM API] Content publishing quota: {usage}/{total} reels used in last 24h.")
                return True, quota_data, None
            err_msg = self._sanitize_error_message(data.get("error", {}).get("message", resp.text))
            return False, data, f"HTTP_{resp.status_code}: {err_msg}"
        except Exception as e:
            return False, {}, self._sanitize_error_message(str(e))

    # =========================================================================
    # 3. CONTAINER CREATION (RESUMABLE UPLOAD SESSION)
    # =========================================================================

    def create_reels_container(
        self,
        request: InstagramPublishRequest
    ) -> Tuple[bool, str, Optional[str], Optional[str]]:
        """
        Initializes a Reels media container via POST /{account_id}/media with upload_type='resumable'.
        Returns (success, message, container_id, upload_uri).
        """
        target_id = self.config.account_id
        if not target_id:
            return False, "NO_ACCOUNT_ID_CONFIGURED", None, None

        if request.dry_run:
            logger.info(f"[INSTAGRAM DRY-RUN] Mock container created for Reel '{request.reel_id}'.")
            return True, "DRY_RUN_CONTAINER_CREATED", f"mock_container_{request.reel_id}", "https://rupload.facebook.com/mock-upload-uri"

        payload = {
            "media_type": "REELS",
            "upload_type": "resumable",
            "caption": request.full_caption(),
            "share_to_feed": request.share_to_feed,
        }
        if request.thumb_offset is not None:
            payload["thumb_offset"] = request.thumb_offset

        try:
            resp = self._request(
                "POST",
                f"/{target_id}/media",
                data=payload
            )
            data = resp.json()
            if resp.status_code == 200 and "id" in data:
                container_id = data.get("id")
                upload_uri = data.get("uri")
                logger.info(f"[INSTAGRAM API] Reels container created: ID={container_id}, URI={upload_uri}")
                return True, "CONTAINER_CREATED", container_id, upload_uri

            err_msg = self._sanitize_error_message(data.get("error", {}).get("message", resp.text))
            logger.error(f"[INSTAGRAM API] Container creation failed: HTTP {resp.status_code} - {err_msg}")
            return False, f"HTTP_{resp.status_code}: {err_msg}", None, None
        except Exception as e:
            err_msg = self._sanitize_error_message(str(e))
            return False, f"CONTAINER_EXCEPTION: {err_msg}", None, None

    # =========================================================================
    # 4. RESUMABLE LOCAL BINARY UPLOAD
    # =========================================================================

    def upload_video_resumable(
        self,
        upload_uri: str,
        video_path: Path,
        dry_run: bool = True,
        allow_upload: bool = False
    ) -> Tuple[bool, str]:
        """
        Streams binary video file to Meta's rupload URI with offset headers.
        Respects safety flags: only executes real byte transfer if allow_upload=True and dry_run=False.
        """
        if dry_run or not allow_upload:
            logger.info(
                f"[INSTAGRAM DRY-RUN] Local file upload simulated for '{video_path.name}' "
                f"(dry_run={dry_run}, allow_upload={allow_upload})."
            )
            return True, "DRY_RUN_UPLOAD_SKIPPED"

        if not video_path.exists():
            return False, f"FILE_NOT_FOUND: {video_path}"

        file_size = video_path.stat().st_size
        logger.info(f"[INSTAGRAM API] Starting binary upload of '{video_path.name}' ({file_size} bytes)...")

        headers = {
            "Authorization": f"OAuth {self.config.access_token}",
            "offset": "0",
            "file_size": str(file_size),
            "Content-Type": "application/octet-stream",
        }

        try:
            with open(video_path, "rb") as f:
                resp = self._request(
                    "POST",
                    upload_uri,
                    data=f,
                    headers=headers,
                    is_absolute_url=True,
                    retry_transient=True
                )
            if resp.status_code == 200:
                logger.info(f"[INSTAGRAM API] Binary upload completed successfully.")
                return True, "UPLOAD_SUCCESS"

            err_msg = self._sanitize_error_message(resp.text)
            logger.error(f"[INSTAGRAM API] Binary upload failed: HTTP {resp.status_code} - {err_msg}")
            return False, f"HTTP_{resp.status_code}: {err_msg}"
        except Exception as e:
            err_msg = self._sanitize_error_message(str(e))
            return False, f"UPLOAD_EXCEPTION: {err_msg}"

    # =========================================================================
    # 5. ASYNC PROCESSING POLLING
    # =========================================================================

    def poll_container_status(
        self,
        container_id: str,
        timeout_seconds: Optional[int] = None
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Polls GET /{container_id}?fields=status_code,status until FINISHED, ERROR, or EXPIRED.
        Normalizes status to FINISHED, IN_PROGRESS, ERROR.
        """
        if container_id.startswith("mock_container_"):
            logger.info(f"[INSTAGRAM DRY-RUN] Mock container status polled: FINISHED.")
            return True, "FINISHED", {"status_code": "FINISHED"}

        max_wait = timeout_seconds or self.config.max_poll_wait_seconds
        interval = self.config.poll_interval_seconds
        start_time = time.time()

        logger.info(f"[INSTAGRAM API] Polling processing status for container {container_id} (max {max_wait}s)...")

        while time.time() - start_time < max_wait:
            try:
                resp = self._request(
                    "GET",
                    f"/{container_id}",
                    params={"fields": "status_code,status"}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    status_code = data.get("status_code", "").upper()
                    logger.info(f"[INSTAGRAM API] Container {container_id} status: {status_code}")

                    if status_code == "FINISHED":
                        return True, "FINISHED", data
                    elif status_code in ("ERROR", "EXPIRED"):
                        err_msg = data.get("status", f"Processing status={status_code}")
                        logger.error(f"[INSTAGRAM API] Container processing failed: {err_msg}")
                        return False, status_code, data
                    elif status_code == "IN_PROGRESS":
                        time.sleep(interval)
                        continue
                else:
                    data = resp.json()
                    err_msg = self._sanitize_error_message(data.get("error", {}).get("message", resp.text))
                    logger.warning(f"[INSTAGRAM API] Poll status HTTP {resp.status_code}: {err_msg}")

            except Exception as e:
                logger.debug(f"[INSTAGRAM API] Status poll exception: {e}")

            time.sleep(interval)

        logger.error(f"[INSTAGRAM API] Processing poll timeout after {max_wait}s.")
        return False, "POLL_TIMEOUT", {"status_code": "TIMEOUT"}

    # =========================================================================
    # 6. PUBLISH MEDIA (EXPLICITLY GATED)
    # =========================================================================

    def publish_media(
        self,
        container_id: str,
        dry_run: bool = True,
        allow_publish: bool = False
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Publishes the media container via POST /{account_id}/media_publish?creation_id={container_id}.
        Hard-gated: only executes real publish if allow_publish=True and dry_run=False.
        """
        if dry_run or not allow_publish:
            logger.info(
                f"[INSTAGRAM DRY-RUN] Media publish skipped (dry_run={dry_run}, allow_publish={allow_publish}). "
                f"Container ID: {container_id}"
            )
            return True, "DRY_RUN_PUBLISH_SKIPPED", None

        target_id = self.config.account_id
        if not target_id:
            return False, "NO_ACCOUNT_ID_CONFIGURED", None

        try:
            resp = self._request(
                "POST",
                f"/{target_id}/media_publish",
                data={"creation_id": container_id}
            )
            data = resp.json()
            if resp.status_code == 200 and "id" in data:
                media_id = data.get("id")
                logger.info(f"[INSTAGRAM API] Media published successfully! Remote Media ID: {media_id}")
                return True, "PUBLISHED", media_id

            err_msg = self._sanitize_error_message(data.get("error", {}).get("message", resp.text))
            logger.error(f"[INSTAGRAM API] Media publish failed: HTTP {resp.status_code} - {err_msg}")
            return False, f"HTTP_{resp.status_code}: {err_msg}", None
        except Exception as e:
            err_msg = self._sanitize_error_message(str(e))
            return False, f"PUBLISH_EXCEPTION: {err_msg}", None

    # =========================================================================
    # 7. REMOTE MEDIA VERIFICATION
    # =========================================================================

    def get_media_object(self, media_id: str) -> Tuple[bool, Dict[str, Any], Optional[str]]:
        """
        Fetches full remote media object fields from Meta Graph API for verification.
        Fields: id,media_type,media_product_type,permalink,timestamp,username
        """
        if not media_id:
            return False, {}, "NO_MEDIA_ID_PROVIDED"

        if media_id.startswith("mock_"):
            return True, {
                "id": media_id,
                "media_type": "VIDEO",
                "media_product_type": "REELS",
                "permalink": f"https://www.instagram.com/reel/{media_id}/",
                "username": self.config.expected_username
            }, None

        try:
            resp = self._request(
                "GET",
                f"/{media_id}",
                params={"fields": "id,media_type,media_product_type,permalink,timestamp,username"}
            )
            data = resp.json()
            if resp.status_code == 200 and "id" in data:
                return True, data, None
            err_msg = self._sanitize_error_message(data.get("error", {}).get("message", resp.text))
            return False, data, f"HTTP_{resp.status_code}: {err_msg}"
        except Exception as e:
            err_msg = self._sanitize_error_message(str(e))
            return False, {}, f"GET_MEDIA_EXCEPTION: {err_msg}"

    def get_media_permalink(self, media_id: str) -> Optional[str]:
        """Fetches permalink for a published Instagram media item."""
        ok, data, _ = self.get_media_object(media_id)
        if ok and data.get("permalink"):
            return data.get("permalink")
        return None
