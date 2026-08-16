"""
Central CLI orchestrator for Reels AI Factory.
Executes the full 8-step automated pipeline with clean console UX, dry-run support,
incomplete Reel resumption, and safety limit enforcement.
"""
import argparse
import datetime
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

# Ensure project root is in sys.path for direct script execution
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from automation.config import load_config, AppConfig, MAX_VIDEOS_PER_RUN_LIMIT
from automation.lock import ProcessLock, LockAcquisitionError
from automation.logger import setup_logger, print_banner, print_step
from automation.obsidian.reel_repository import ObsidianReelRepository
from automation.content.engine import ContentEngine
from automation.content.concepts import ConceptDefinition, CATEGORIES
from automation.content.prompt_engine import ReelConceptPlan
from automation.flow.generator import GoogleFlowWebProvider, MockVideoProvider, VideoProvider
from automation.flow.selectors import (
    UserActionRequiredError,
    InsufficientCreditsError,
    FlowUIChangedError,
    RealGenerationDisabled
)
from automation.agents import AgentManager
from automation.quality.validator import VideoValidator
from automation.output.manager import DesktopOutputManager, sanitize_filename
from automation.notifications.windows import (
    NotificationProvider,
    get_default_notification_provider,
    MockNotificationProvider,
    WindowsNotificationProvider,
    notify_success,
    notify_action_required,
    notify_failure
)

from automation.content.segment_planner import SegmentPlanner, ContinuityContext

def reconstruct_plan_from_meta(meta: dict) -> ReelConceptPlan:
    """Reconstruct a ReelConceptPlan with 3 staged segments from existing Obsidian note metadata."""
    title = meta.get("title") or "Satisfying Transformation Build"
    topic = meta.get("topic") or "Pristine environment transforming into architectural build"
    topic_key = meta.get("topic_key") or "satisfying-transformation"
    prompt = meta.get("prompt") or ""
    category = meta.get("category") or "Satisfying Transformation"

    # Find matching concept definition
    matched_concept = next((c for c in CATEGORIES if c.id_slug in topic_key), CATEGORIES[0])

    env = meta.get("environment") or (matched_concept.environments[0] if matched_concept.environments else "pristine landscape")
    arch = meta.get("architecture") or (matched_concept.architectures[0] if matched_concept.architectures else "modern architecture")
    trans = meta.get("transformation") or (matched_concept.transformations[0] if matched_concept.transformations else "seamless construction progression")
    cam = meta.get("camera_style") or (matched_concept.camera_styles[0] if matched_concept.camera_styles else "cinematic aerial view")
    light = meta.get("lighting") or (matched_concept.lighting_schemes[0] if matched_concept.lighting_schemes else "golden hour")
    mats = meta.get("materials") or (matched_concept.materials[0] if matched_concept.materials else "premium realistic materials")
    rev = meta.get("reveal") or (matched_concept.reveals[0] if matched_concept.reveals else "completed architectural masterpiece")

    continuity, segments = SegmentPlanner.plan_segments(
        concept=matched_concept,
        env=env,
        arch=arch,
        transformation=trans,
        camera=cam,
        lighting=light,
        materials=mats,
        reveal=rev,
        duration_per_segment=10
    )

    # If note had specific segment prompts, preserve them
    seg_prompts = meta.get("segment_prompts", {})
    for seg in segments:
        if seg.index in seg_prompts:
            seg.prompt = seg_prompts[seg.index]

    return ReelConceptPlan(
        concept_def=matched_concept,
        title=title,
        topic_description=topic,
        topic_key=topic_key,
        category=category,
        environment=env,
        architecture=arch,
        transformation=trans,
        camera_style=cam,
        lighting=light,
        materials=mats,
        reveal=rev,
        prompt=segments[0].prompt if segments else prompt,
        diversity_score=float(meta.get("diversity_score", 0.85)),
        pipeline_version=3,
        content_mode="silent_global_step_by_step",
        final_duration_seconds=30,
        segment_count=len(segments),
        segment_duration_seconds=10,
        continuity=continuity,
        segments=segments
    )

def run_pipeline(
    count: int = 1,
    dry_run: bool = False,
    config_path: Optional[str] = None,
    mock_flow: bool = False,
    allow_real_generation: bool = False,
    notification_provider: Optional[NotificationProvider] = None
) -> int:
    """
    Main pipeline entry point. Returns exit code (0 for success, 1 for failure).
    """
    print_banner(reels_count=count)

    # Step 1: Load config & acquire single-instance process lock
    try:
        config = load_config(config_file=config_path, count_override=count)
        if allow_real_generation and not dry_run:
            config.allow_real_generation = True
        elif dry_run:
            config.allow_real_generation = False
    except Exception as e:
        print(f"[HATA] Yapılandırma yüklenemedi: {e}")
        return 1

    notif = notification_provider or get_default_notification_provider(enabled=config.notifications_enabled)

    logger = setup_logger(config.logs_dir)
    logger.info("Reels AI Factory başlatılıyor...")
    logger.info(f"Parametreler: count={config.videos_per_run}, dry_run={dry_run}, mock_flow={mock_flow}")

    lock = ProcessLock(config.chrome_profile_dir.parent / "automation.lock")
    try:
        lock.acquire()
    except LockAcquisitionError as e:
        print(f"[UYARI] {e}")
        logger.warning(f"Kilit alınamadı: {e}")
        return 1

    try:
        # Step 1: Check Obsidian Vault
        print_step(1, 8, "Obsidian kasası kontrol ediliyor...", f"Kasa: {config.vault_path}")
        if not config.vault_path.exists():
            raise FileNotFoundError(f"Obsidian kasası bulunamadı: {config.vault_path}")
        repo = ObsidianReelRepository(config.vault_path)
        print("      OK\n")

        # Initialize Agent Manager for multi-agent orchestration & Obsidian live knowledge graph
        agent_mgr = AgentManager(config.vault_path, config=config)

        # Step 2: Read past history and check for incomplete reels to resume
        print_step(2, 8, "Geçmiş içerikler okunuyor...")
        completed_reels = repo.get_completed_reels()
        incomplete_reels = repo.get_incomplete_reels()
        print(f"      {len(completed_reels)} tamamlanmış Reel kaydı bulundu.")
        if incomplete_reels:
            print(f"      {len(incomplete_reels)} tamamlanmamış Reel kaydı tespit edildi (Öncelikli devam ettirilecek).\n")
        else:
            print()

        # Step 3: Select novel concepts or resume existing unfulfilled ones
        print_step(3, 8, "Konseptler belirleniyor...")
        allocated_reels: List[Tuple[str, ReelConceptPlan, bool, Optional[str], Optional[str]]] = []  # (id, plan, is_resumed, flow_project_url, resume_from)

        # First priority: Resume incomplete reels
        for inc_meta in incomplete_reels:
            if len(allocated_reels) >= config.videos_per_run:
                break
            reel_id = inc_meta["id"]
            plan = reconstruct_plan_from_meta(inc_meta)
            f_url = inc_meta.get("flow_project_url")
            res_from = inc_meta.get("resume_from") or ("DOWNLOAD" if inc_meta.get("status") == "MEDIA_READY" else None)
            allocated_reels.append((reel_id, plan, True, f_url, res_from))
            print(f"      [DEVAM] {reel_id:<14} {plan.title} (Önceki yarım kalan Reel sürdürülüyor)")

        history_reels = repo.get_past_visual_history()

        # Second priority: Generate new concepts if more are requested
        remaining_needed = config.videos_per_run - len(allocated_reels)
        if remaining_needed > 0:
            content_engine = ContentEngine()
            new_plans = content_engine.generate_next_reels(
                count=remaining_needed,
                past_records=history_reels,
                duration_seconds=config.video_duration
            )

            first_id_str = repo.get_next_id()
            parts = first_id_str.split("-")
            current_year = int(parts[1])
            start_num = int(parts[2])

            for i, plan in enumerate(new_plans):
                reel_id = f"REEL-{current_year}-{start_num + i:04d}"
                allocated_reels.append((reel_id, plan, False, None, None))
                print(f"      [YENİ]  {reel_id:<14} {plan.title} (Diversity Score: {plan.diversity_score:.2f})")

        print()

        # Start Agent Run Context and record planning events
        req_ids = [r[0] for r in allocated_reels]
        run_ctx = agent_mgr.start_run(requested_reels=req_ids)
        agent_mgr.record_history_analysis(history_reels)

        for reel_id, plan, is_resumed, f_url, res_from in allocated_reels:
            if is_resumed:
                agent_mgr.record_resume_event(reel_id, res_from or "PROMPT")
            else:
                agent_mgr.record_concept_selection(reel_id, plan)
            agent_mgr.record_segment_planning(reel_id, plan)

        # Step 4: Write initial Markdown scripts into Obsidian
        print_step(4, 8, "Obsidian senaryo notları kontrol ediliyor...")
        for reel_id, plan, is_resumed, f_url, res_from in allocated_reels:
            if not is_resumed:
                script_path = repo.create_new_reel(reel_id, plan, run_id=run_ctx.run_id)
                logger.info(f"Oluşturuldu: {script_path.name} (status: PROMPT_READY)")
                print(f"      {reel_id} -> 03_SCRIPTS/{script_path.name}")
            else:
                if res_from == "DOWNLOAD":
                    repo.writer.update_status(reel_id, "MEDIA_READY", {"resume_from": "DOWNLOAD"})
                    print(f"      {reel_id} -> Mevcut not güncellendi (status: MEDIA_READY, resume_from: DOWNLOAD)")
                else:
                    repo.writer.update_status(reel_id, "PROMPT_READY")
                    print(f"      {reel_id} -> Mevcut not güncellendi (status: PROMPT_READY)")
        print()

        # Check for Dry Run mode
        if dry_run:
            agent_mgr.complete_run()
            print("========================================")
            print("         DRY RUN TAMAMLANDI")
            print("========================================")
            for reel_id, plan, is_resumed, f_url, res_from in allocated_reels:
                print(f"\n{reel_id}")
                print(f"Concept: {plan.title} ({plan.category})")
                print(f"Diversity Score: {plan.diversity_score:.2f}")
                if plan.segments:
                    for seg in plan.segments:
                        print(f"\nSEGMENT {seg.index}/3")
                        print(f"Duration: {seg.duration_seconds}s")
                        print(f"Goal: {seg.stage_name}")
                        print(f"Starting: {seg.starting_state}")
                        print(f"Action:   {seg.action_description}")
                        print(f"Ending:   {seg.ending_state}")
                print(f"\nFINAL:")
                print(f"{plan.final_duration_seconds} seconds")
                print(f"9:16 vertical")
                print(f"Silent (Audio: {config.audio_enabled})")
                print("----------------------------------------")
            print("\nObsidian senaryoları ve promptlar hazırlandı.")
            print("Google Flow açılmadı, kredi harcanmadı.")
            print(f"Kasa: {config.vault_path}")
            print("========================================\n")
            return 0

        # Step 5: Initialize Video Provider
        print_step(5, 8, "Video üretim servisi hazırlanıyor...")
        if mock_flow:
            video_provider: VideoProvider = MockVideoProvider(config.workspace_downloads_dir, agent_manager=agent_mgr)
            print("      [MOCK FLOW AKTİF] Test videosu üretilecek.\n")
        else:
            video_provider = GoogleFlowWebProvider(config, agent_manager=agent_mgr)
            print("      Google Chrome CDP bağlantısı hazır.\n")

        validator = VideoValidator(
            reject_wrong_ratio=config.reject_wrong_ratio,
            audio_enabled=config.audio_enabled
        )
        output_mgr = DesktopOutputManager(config.output_path)

        successful_reels = []
        daily_folder = output_mgr.get_today_folder()

        # Step 6 & 7: Generate & Validate each video sequentially
        for reel_id, plan, is_resumed, f_url, res_from in allocated_reels:
            print(f"\n>>> İŞLENİYOR: {reel_id} ({plan.title})")
            repo.mark_generating(reel_id)

            clean_title = sanitize_filename(plan.title)
            target_filename = f"{reel_id}_{clean_title}.mp4"

            started_at = datetime.datetime.now()
            print(f"[{reel_id}] Google Flow'a gönderiliyor...")

            try:
                # 5 & 6. Submit to Flow & Download
                downloaded_file = video_provider.generate_single_video(
                    plan=plan,
                    reel_id=reel_id,
                    target_filename=target_filename,
                    flow_project_url=f_url,
                    resume_from=res_from
                )

                if not config.allow_real_generation and not mock_flow:
                    print(f"[{reel_id}] [TEST BAŞARILI] Prompt Flow üzerinde doğrulandı (Kredi: 0).")
                    successful_reels.append((reel_id, downloaded_file))
                    continue

                print(f"[{reel_id}] Video başarıyla indirildi: {downloaded_file.name}")
                repo.mark_downloading(reel_id)

                # 7. Quality Control & Post-Processing
                print(f"[{reel_id}] Kalite kontrolü ve ses temizleme yapılıyor...")
                repo.mark_validating(reel_id)
                qc_result = validator.process_and_validate(
                    input_video=downloaded_file,
                    output_dir=config.workspace_downloads_dir
                )

                if not qc_result.is_passed:
                    print(f"[{reel_id}] [QC FAIL] {qc_result.error_message}")
                    repo.mark_rejected(reel_id, qc_result.error_message)
                    continue

                print(f"[{reel_id}] [QC PASS] 9:16 Doğrulandı, Ses Temizlendi.")

                # 8. Output to Desktop & Finalize Obsidian
                finished_at = datetime.datetime.now()
                final_mp4, final_json = output_mgr.save_final_reel(
                    reel_id=reel_id,
                    plan=plan,
                    processed_video_path=qc_result.processed_video_path,
                    qc_result=qc_result,
                    started_at=started_at,
                    finished_at=finished_at
                )

                repo.mark_ready(
                    reel_id=reel_id,
                    video_path=final_mp4,
                    metadata_path=final_json,
                    qc_details={
                        "technical_pass": qc_result.technical_pass,
                        "ratio_pass": qc_result.ratio_pass,
                        "audio_stripped": qc_result.audio_stripped,
                        "visual_pass": qc_result.visual_pass
                    }
                )

                agent_mgr.record_reel_completed(reel_id)
                successful_reels.append((reel_id, final_mp4))
                print(f"[{reel_id}] -> 05_READY ve Masaüstü AI_Reels klasörüne kaydedildi.")

            except RealGenerationDisabled as rgd:
                print(f"[{reel_id}] {rgd}")
                print(f"[{reel_id}] [TEST BAŞARILI] Prompt kontrolü tamamlandı, 0 kredi harcandı.")
                successful_reels.append((reel_id, Path("safe_test_ok")))
                agent_mgr.record_reel_completed(reel_id)
                break

            except UserActionRequiredError as uare:
                print(f"\n[USER_ACTION_REQUIRED] {uare}")
                notif.notify_action_required(str(uare))
                repo.mark_rejected(reel_id, f"USER_ACTION_REQUIRED: {uare}")
                agent_mgr.record_reel_failed(reel_id, str(uare))
                break

            except InsufficientCreditsError as ice:
                print(f"\n[INSUFFICIENT_CREDITS] {ice}")
                notif.notify_action_required(str(ice))
                repo.mark_rejected(reel_id, f"INSUFFICIENT_CREDITS: {ice}")
                agent_mgr.record_reel_failed(reel_id, str(ice))
                break

            except FlowUIChangedError as fuce:
                print(f"\n[{reel_id}] [PRE_SUBMIT UI HATASI] {fuce}")
                logger.error(f"{reel_id} pre-submit UI error: {fuce}")
                repo.mark_rejected(reel_id, f"PRE_SUBMIT_UI_ERROR: {fuce}")
                agent_mgr.record_reel_failed(reel_id, str(fuce))
                break

            except Exception as e:
                print(f"\n[{reel_id}] [HATA] Üretim başarısız: {e}")
                logger.exception(f"{reel_id} generation exception")
                repo.mark_rejected(reel_id, f"ERROR: {e}")
                agent_mgr.record_reel_failed(reel_id, str(e))

        agent_mgr.complete_run()

        # Final Summary
        ready_videos = [mp4 for (_, mp4) in successful_reels if mp4.exists() and mp4.suffix == ".mp4"]
        ready_count = len(ready_videos)

        print("\n========================================")
        if ready_count > 0:
            print(f"{ready_count} VIDEO İŞLEMİ TAMAMLANDI")
            print(f"{daily_folder}")
            notif.notify_success(ready_count, daily_folder)
        elif successful_reels and dry_run:
            print(f"{len(successful_reels)} SENARYO VE PROMPT HAZIRLANDI (DRY RUN)")
        else:
            print("HİÇBİR VİDEO TAMAMLANAMADI.")
            notif.notify_failure("Video üretimi durduruldu.")
        print("========================================\n")

        return 0 if len(successful_reels) == len(allocated_reels) else 1

    finally:
        lock.release()

def main():
    parser = argparse.ArgumentParser(description="Reels AI Factory - Obsidian + Google Flow Automation")
    parser.add_argument("--count", type=int, default=1, help="Üretilecek Reel sayısı (varsayılan: 1, maks: 5)")
    parser.add_argument("--dry-run", action="store_true", help="Kredi harcamadan senaryo ve prompt üretimi testi")
    parser.add_argument("--mock-flow", action="store_true", help="Gerçek Google Flow yerine yerel test videosu kullan")
    parser.add_argument("--allow-real-generation", action="store_true", help="Gerçek video üretimi için Flow Generate butonuna basılmasına izin ver")
    parser.add_argument("--config", type=str, default=None, help="Özel config dosyası yolu")

    args = parser.parse_args()
    count = min(args.count, MAX_VIDEOS_PER_RUN_LIMIT)

    exit_code = run_pipeline(
        count=count,
        dry_run=args.dry_run,
        config_path=args.config,
        mock_flow=args.mock_flow,
        allow_real_generation=args.allow_real_generation
    )
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
