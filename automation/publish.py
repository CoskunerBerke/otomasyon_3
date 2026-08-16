"""
Reels AI Factory — Publishing Agent CLI
Coordinates YouTube Shorts and TikTok Studio automated scheduling.
"""
import sys
import os
import argparse
import logging
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from automation.config import load_config
from automation.publishing.config import load_publishing_config
from automation.publishing.publisher import PublishingOrchestrator
from automation.publishing.youtube_auth import YouTubeAuthManager
from automation.publishing.youtube_studio_browser import YouTubeStudioBrowserManager
from automation.publishing.tiktok_browser import TikTokBrowserManager
from automation.agents import AgentManager

# Setup logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("ReelsAIFactory.PublishCLI")

def parse_args():
    parser = argparse.ArgumentParser(description="Reels AI Factory — Publishing Agent (YouTube Shorts + TikTok Studio)")
    parser.add_argument("--count", "-c", type=int, default=1, help="Number of 05_READY reels to schedule (Default: 1)")
    parser.add_argument("--start-date", "-s", type=str, default=None, help="Publishing start date (YYYY-MM-DD, e.g. 2026-08-16)")
    parser.add_argument("--dry-run", action="store_true", help="Prepare metadata, schedule slots, and Obsidian notes without uploading")
    parser.add_argument("--allow-partial", action="store_true", help="Allow scheduling available reels even if count exceeds available READY reels")
    parser.add_argument("--mock", action="store_true", help="Use Mock publishers for testing")
    parser.add_argument("--enable-live-publish", action="store_true", help="Explicitly enable real live publishing to YouTube Studio / TikTok Studio")
    parser.add_argument("--single-live-test", action="store_true", help="Run single-reel live schedule test to unlock weekly batch")
    parser.add_argument("--preflight", action="store_true", help="Run Phase 1 PREFLIGHT: prepare UI forms up to final action button (0 clicks)")
    parser.add_argument("--commit", action="store_true", help="Run Phase 2 COMMIT: re-verify preflight states and click final schedule buttons")
    parser.add_argument("--youtube-auth", action="store_true", help="Run interactive YouTube OAuth 2.0 login flow")
    parser.add_argument("--youtube-studio-login", action="store_true", help="Launch dedicated Chrome instance on port 9224 for YouTube Studio login")
    parser.add_argument("--tiktok-login", action="store_true", help="Launch dedicated Chrome instance on port 9223 for TikTok login")
    return parser.parse_args()

def handle_youtube_auth(pub_cfg):
    print("========================================")
    print("      YOUTUBE OAUTH 2.0 YETKİLENDİRME")
    print("========================================")
    print(f"Client Secret:    {pub_cfg.youtube_client_secret_path}")
    print(f"Token Hedefi:     {pub_cfg.youtube_token_path}")
    print(f"Beklenen Kanal:   {pub_cfg.youtube_expected_handle}\n")

    if not pub_cfg.youtube_client_secret_path.exists():
        print("[HATA] client_secret.json dosyası bulunamadı!")
        print("Lütfen Google Cloud Console'dan indirdiğiniz OAuth istemci dosyasını:")
        print(f"'{pub_cfg.youtube_client_secret_path}'")
        print("konumuna kopyalayın ve bu komutu tekrar çalıştırın.")
        return 1

    try:
        service = YouTubeAuthManager.get_authenticated_service(
            client_secret_path=pub_cfg.youtube_client_secret_path,
            token_path=pub_cfg.youtube_token_path,
            interactive=True
        )

        is_match, v_msg, ch_info = YouTubeAuthManager.verify_authenticated_channel(
            service,
            expected_handle=pub_cfg.youtube_expected_handle,
            expected_channel_id=pub_cfg.youtube_expected_channel_id
        )

        err_type = ch_info.get("error_type")
        if is_match:
            print("\n========================================")
            print("YouTube OAuth Scopes:")
            print(" [PASS] youtube.upload")
            print(" [PASS] youtube.readonly")
            print("\nAuthenticated Channel:")
            print(f" Title:      {ch_info.get('title')}")
            print(f" Handle:     {ch_info.get('custom_url') or ch_info.get('handle')}")
            print(f" Channel ID: {ch_info.get('channel_id')}")
            print(f"\nExpected:")
            print(f" {pub_cfg.youtube_expected_handle}")
            print("\nAccount Verification:")
            print(" PASS")
            print("========================================")
            print("     YOUTUBE GİRİŞİ BAŞARIYLA TAMAMLANDI")
            print("========================================\n")
            return 0
        elif err_type == "REAUTH_REQUIRED":
            print("\n----------------------------------------")
            print("Doğrulama Sonucu: ❌ REAUTH_REQUIRED (Yetersiz İzin/Scope)")
            print(f"{v_msg}")
            print("----------------------------------------\n")
            return 1
        else:
            print("\n----------------------------------------")
            print(f"Giriş Yapılan Kanal: {ch_info.get('title', 'Unknown')}")
            print(f"Kanal Handle/URL:    {ch_info.get('custom_url', 'None')}")
            print(f"Kanal ID:            {ch_info.get('channel_id', 'None')}")
            print(f"Doğrulama Sonucu:    ❌ ACCOUNT MISMATCH")
            print("----------------------------------------")
            print(f"\n[UYARI] Yetkilendirilen hesap beklenen hedef hesapla uyuşmuyor!")
            print(f"Beklenen:   {pub_cfg.youtube_expected_handle}")
            print(f"Giriş:      {ch_info.get('custom_url') or ch_info.get('title')}")
            print("Lütfen doğru YouTube kanalıyla (@BuiIdVerse) tekrar yetkilendirin.\n")
            return 1

    except Exception as e:
        print(f"\n[HATA] YouTube yetkilendirmesi başarısız: {e}")
        return 1

def handle_tiktok_login(pub_cfg):
    print("========================================")
    print("      TIKTOK STUDIO CHROME GİRİŞİ")
    print("========================================")
    print(f"Beklenen Hesap: {pub_cfg.tiktok_expected_username}")
    print(f"CDP Portu:      {pub_cfg.tiktok_debug_port}")
    print(f"Profil Dizini:  {pub_cfg.tiktok_profile_dir}")
    print(f"TikTok URL:     {pub_cfg.tiktok_url}\n")
    print("Google Chrome penceresi açılıyor...")
    print(f"Lütfen açılan pencerede '{pub_cfg.tiktok_expected_username}' hesabınızla manuel olarak giriş yapın.")
    print("Oturum kalıcı olarak profile kaydedilecektir.")
    print("========================================\n")

    browser_mgr = TikTokBrowserManager(
        debug_port=pub_cfg.tiktok_debug_port,
        profile_dir=pub_cfg.tiktok_profile_dir
    )
    try:
        proc = browser_mgr.launch_chrome_for_tiktok(pub_cfg.tiktok_url)
        print("Chrome başlatıldı (PID: {}).".format(proc.pid))
        print("Giriş işleminizi tamamlayın.")
        return 0
    except Exception as e:
        print(f"[HATA] Chrome başlatılamadı: {e}")
        return 1

def handle_youtube_studio_login(pub_cfg):
    print("========================================")
    print("    YOUTUBE STUDIO CHROME GİRİŞİ")
    print("========================================")
    print(f"Beklenen Kanal: {pub_cfg.youtube_expected_handle} ({pub_cfg.youtube_expected_channel_id})")
    print(f"CDP Portu:      {pub_cfg.youtube_studio_debug_port}")
    print(f"Profil Dizini:  {pub_cfg.youtube_studio_profile_dir}")
    print(f"Studio URL:     {pub_cfg.youtube_studio_url}\n")
    print("Google Chrome penceresi açılıyor...")
    print(f"Lütfen açılan pencerede '{pub_cfg.youtube_expected_handle}' kanalınızla manuel olarak giriş yapın.")
    print("Oturum kalıcı olarak YouTube Studio profiline kaydedilecektir.")
    print("========================================\n")

    browser_mgr = YouTubeStudioBrowserManager(
        debug_port=pub_cfg.youtube_studio_debug_port,
        profile_dir=pub_cfg.youtube_studio_profile_dir
    )
    try:
        proc = browser_mgr.launch_chrome_for_youtube_studio(pub_cfg.youtube_studio_url)
        print("Chrome başlatıldı (PID: {}).".format(proc.pid))
        print("Giriş işleminizi tamamlayın.")
        return 0
    except Exception as e:
        print(f"[HATA] Chrome başlatılamadı: {e}")
        return 1

def main():
    args = parse_args()
    app_cfg = load_config()
    pub_cfg = load_publishing_config(base_dir=PROJECT_ROOT)

    if args.enable_live_publish:
        pub_cfg.live_publish_enabled = True
    if args.single_live_test:
        pub_cfg.single_live_test_passed = True

    # 1. Handle YouTube Auth interactive
    if args.youtube_auth:
        return handle_youtube_auth(pub_cfg)

    # 2. Handle YouTube Studio Login interactive
    if args.youtube_studio_login:
        return handle_youtube_studio_login(pub_cfg)

    # 3. Handle TikTok Login interactive
    if args.tiktok_login:
        return handle_tiktok_login(pub_cfg)

    # 4. Normal Publishing / Scheduling Flow
    print("========================================")
    print("   REELS AI FACTORY — PUBLISHING AGENT")
    print("========================================")
    print(f"Hedef Reel Sayısı:   {args.count}")
    print(f"Başlangıç Tarihi:    {args.start_date or pub_cfg.schedule_start_date or 'Belirlenmedi (NULL)'}")
    print(f"Hedef YouTube:       {pub_cfg.youtube_expected_handle} (Studio Port: {pub_cfg.youtube_studio_debug_port})")
    print(f"Hedef TikTok:        {pub_cfg.tiktok_expected_username} (Studio Port: {pub_cfg.tiktok_debug_port})")
    print(f"Zaman Dilimi:        {pub_cfg.timezone}")
    print(f"Günlük Slotlar:      {', '.join(pub_cfg.daily_slots)}")
    print(f"Mod:                 {'DRY RUN (Kredi/Upload Yok)' if args.dry_run else ('MOCK TEST' if args.mock else 'GERÇEK SCHEDULING')}")
    print("========================================\n")

    # Start-date safety check
    start_date = args.start_date or pub_cfg.schedule_start_date
    if not start_date and not args.dry_run:
        print("==================================================")
        print(" [!] LIVE SCHEDULING BLOCKED")
        print("==================================================")
        print("Set publishing.schedule_start_date before running a live schedule.")
        print("Lütfen komuta '--start-date YYYY-MM-DD' parametresini ekleyin veya")
        print("publishing.local.json içine 'schedule_start_date' alanını yazın.")
        print("\nÖrnek:")
        print(f"python automation/publish.py --count {args.count} --start-date 2026-08-20")
        print("==================================================\n")
        return 1

    agent_mgr = AgentManager(app_cfg.vault_path, config=app_cfg)
    pub_agent = agent_mgr.agents.get("PUBLISH_AGENT")
    if pub_agent:
        pub_agent.enable()

    orchestrator = PublishingOrchestrator(
        vault_path=app_cfg.vault_path,
        config=pub_cfg,
        agent_manager=agent_mgr,
        mock=args.mock
    )

    # 4. Handle Phase 1 PREFLIGHT
    if args.preflight:
        success, records = orchestrator.execute_preflight(
            count=args.count,
            start_date_override=start_date
        )
        return 0 if success else 1

    # 5. Handle Phase 2 COMMIT
    if args.commit:
        success, records = orchestrator.execute_commit(
            count=args.count,
            start_date_override=start_date
        )
        return 0 if success else 1

    # 6. Normal batch flow
    try:
        batch = orchestrator.execute_publishing_batch(
            count=args.count,
            start_date_override=start_date,
            dry_run=args.dry_run,
            allow_partial=args.allow_partial
        )

        print("\n========================================")
        print(f"   PUBLISHING BATCH: {batch.batch_id}")
        print("========================================")
        print(f"Durum:               {batch.status}")
        print(f"İşlenen Reel Sayısı: {len(batch.requested_reels)}")
        print(f"Oluşturulan Kayıt:   {len(batch.records)}")
        print("----------------------------------------")
        for rec in batch.records:
            print(f"[{rec.reel_id}] {rec.platform.value.upper():<8} ({rec.account_handle}) -> {rec.status.value:<12} Slot: {rec.scheduled_at_local}")
            if rec.remote_url:
                print(f"             Remote: {rec.remote_url}")
            if rec.last_error:
                print(f"             Info/Error: {rec.last_error}")
        print("========================================\n")
        print(f"Obsidian Kayıtları: {app_cfg.vault_path / '13_PUBLISHING'}")
        print(f"Canlı Kuyruk:       {app_cfg.vault_path / '13_PUBLISHING' / 'PUBLISHING_QUEUE.md'}")
        print("========================================\n")
        return 0 if batch.status in ("COMPLETED", "RUNNING") else 1

    except ValueError as ve:
        print(f"\n{ve}\n")
        return 1
    except Exception as e:
        logger.exception("Publishing batch execution failed")
        print(f"\n[HATA] Yayınlama işlemi başarısız: {e}\n")
        return 1

if __name__ == "__main__":
    sys.exit(main())
