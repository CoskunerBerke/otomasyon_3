"""
High level video generation coordinator with retry protection and provider interfaces.
Connects to real Google Chrome via Chrome DevTools Protocol (CDP).
Supports V3 30-Second 3-Segment Step-by-Step Reels with visual continuity,
one-project-per-reel execution, per-segment session tracking, and seamless concatenation.
"""
from abc import ABC, abstractmethod
import time
import hashlib
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List

from .browser import CDPBrowserManager
from .page import FlowPage
from .selectors import (
    FlowError,
    FlowUIChangedError,
    UserActionRequiredError,
    InsufficientCreditsError,
    GenerationTimeoutError,
    RealGenerationDisabled
)
from .state_machine import GenerationSession, FlowDecisionAction
from ..config import AppConfig
from ..content.prompt_engine import ReelConceptPlan
from ..quality.frame_extractor import FrameExtractor
from ..quality.concatenator import VideoConcatenator

class VideoProvider(ABC):
    """Abstract video generation provider."""

    @abstractmethod
    def generate_single_video(
        self,
        plan: ReelConceptPlan,
        reel_id: str,
        target_filename: str,
        flow_project_url: Optional[str] = None,
        resume_from: Optional[str] = None
    ) -> Path:
        pass

class GoogleFlowWebProvider(VideoProvider):
    """Generates 30-second 3-segment videos using Google Flow web interface via CDP."""

    def __init__(self, config: AppConfig, agent_manager: Optional[Any] = None):
        self.config = config
        self.agent_manager = agent_manager
        self.browser_mgr = CDPBrowserManager(config=self.config)
        self.frame_extractor = FrameExtractor(output_dir=self.config.workspace_frames_dir)
        self.concatenator = VideoConcatenator(workspace_dir=self.config.workspace_segments_dir)

    def generate_single_video(
        self,
        plan: ReelConceptPlan,
        reel_id: str,
        target_filename: str,
        flow_project_url: Optional[str] = None,
        resume_from: Optional[str] = None
    ) -> Path:
        """
        Execute 30-second 3-segment generation in a single dedicated Flow project.
        Skips already completed segments, takes baseline snapshots before each generation,
        downloads each segment, extracts end-frames, and concatenates into a final 30s MP4.
        """
        segments = plan.segments if plan.segments else []
        reel_segments_dir = self.config.workspace_segments_dir / reel_id
        reel_segments_dir.mkdir(parents=True, exist_ok=True)

        is_download_only = (resume_from == "DOWNLOAD")

        with self.browser_mgr.connect() as (browser, context):
            page = self.browser_mgr.find_or_open_flow_page(context, self.config.flow_url)
            flow_page = FlowPage(
                page=page,
                screenshots_dir=self.config.screenshots_dir,
                downloads_dir=self.config.workspace_downloads_dir
            )

            # 1. Verify auth and ensure dedicated project for this Reel
            flow_page.check_auth_and_security()
            project_url = flow_page.ensure_project_for_reel(reel_id, flow_project_url=flow_project_url)

            # -------------------------------------------------------------
            # CASE A: RESUME DIRECTLY FROM DOWNLOAD (NO GENERATION / 0 CREDIT)
            # -------------------------------------------------------------
            if is_download_only:
                print(f"[{reel_id}] [SAFE RESUME] Video zaten üretilmiş durumda. Prompt/Generate atlanıyor, doğrudan DOWNLOAD aşamasına geçiliyor...")
                session = GenerationSession(
                    reel_id=reel_id,
                    flow_project_url=project_url,
                    prompt_hash=hashlib.sha256(plan.prompt.strip().encode("utf-8")).hexdigest()[:16]
                )
                session.submit_attempted = True

                flow_page.recover_and_open_video_detail()
                time.sleep(1.0)
                dl_btn = flow_page.resolve_enabled_download_button(timeout_ms=1500)
                if dl_btn:
                    return flow_page.downloader.trigger_and_save_download(
                        page=flow_page.page,
                        download_button_locator=dl_btn,
                        target_filename=target_filename,
                        timeout_seconds=60
                    )
                else:
                    return flow_page.wait_for_completion_and_download(
                        target_filename=target_filename,
                        timeout_minutes=2,
                        target_duration=self.config.video_duration,
                        session=session
                    )

            # -------------------------------------------------------------
            # CASE B: V3 MULTI-SEGMENT GENERATION (3 x 10s = 30s)
            # -------------------------------------------------------------
            if segments:
                completed_segment_paths: List[Path] = []

                # Configure Settings once for the project
                flow_page.configure_agent_settings(
                    approval_mode=self.config.approval_before_generation,
                    video_ratio=self.config.video_ratio,
                    video_outputs=self.config.video_outputs,
                    video_model=self.config.video_model,
                    image_ratio=self.config.image_ratio,
                    image_outputs=self.config.image_outputs,
                    image_model=self.config.image_model,
                    target_duration=self.config.segment_duration_seconds
                )

                for seg in segments:
                    seg_idx = seg.index
                    seg_target_name = f"segment_{seg_idx:02d}.mp4"
                    seg_target_file = reel_segments_dir / seg_target_name

                    # Check if segment already completed on disk
                    if seg.status == "READY" and seg_target_file.exists() and seg_target_file.stat().st_size > 10000:
                        print(f"[{reel_id}] Segment {seg_idx}/3 daha önce tamamlanmış: {seg_target_name} (Atlanıyor)")
                        completed_segment_paths.append(seg_target_file)
                        continue

                    print(f"\n[{reel_id}] >>> SEGMENT {seg_idx}/3 ÜRETİLİYOR ({seg.stage_name} — {seg.duration_seconds}s)")

                    seg_session = GenerationSession(
                        reel_id=f"{reel_id}-S{seg_idx}",
                        flow_project_url=project_url,
                        prompt_hash=seg.prompt_hash
                    )

                    # Reset submit flag for this segment
                    flow_page._submit_attempted = False

                    # Enter segment prompt
                    flow_page.enter_prompt(seg.prompt, target_duration=seg.duration_seconds)

                    if not self.config.allow_real_generation:
                        print(f"[{reel_id}] [SEGMENT {seg_idx}] Prompt doğrulandı (allow_real_generation=False).")
                        if not seg_target_file.exists():
                            seg_target_file.write_bytes(b"TEST_SEGMENT_PLACEHOLDER")
                        completed_segment_paths.append(seg_target_file)
                        continue

                    # Trigger generation with baseline snapshot
                    if self.agent_manager:
                        self.agent_manager.record_flow_generation_start(reel_id, seg_idx, len(segments))

                    flow_page.trigger_generation(allow_real_generation=True, session=seg_session)

                    # Wait and download segment video
                    downloaded_seg = flow_page.wait_for_completion_and_download(
                        target_filename=seg_target_name,
                        timeout_minutes=self.config.generation_timeout_minutes,
                        target_duration=seg.duration_seconds,
                        session=seg_session
                    )

                    # Move/copy to segments folder if needed
                    final_seg_path = reel_segments_dir / seg_target_name
                    if downloaded_seg != final_seg_path:
                        import shutil
                        shutil.copy2(str(downloaded_seg), str(final_seg_path))

                    if self.agent_manager:
                        self.agent_manager.record_flow_segment_downloaded(reel_id, seg_idx)

                    # Extract end-frame for continuity reference
                    end_frame_path = self.frame_extractor.extract_end_frame(
                        video_path=final_seg_path,
                        output_filename=f"segment_{seg_idx:02d}_end.jpg",
                        reel_id=reel_id
                    )
                    seg.local_file = final_seg_path
                    seg.end_frame_file = end_frame_path
                    seg.status = "READY"

                    if self.agent_manager:
                        self.agent_manager.record_segment_qc_pass(reel_id, seg_idx)

                    print(f"[{reel_id}] Segment {seg_idx}/3 tamamlandı: {final_seg_path.name}")
                    print(f"[{reel_id}] Segment {seg_idx}/3 son kare çıkarıldı: {end_frame_path.name}")

                    completed_segment_paths.append(final_seg_path)

                # Concatenate 3 segments into final 30s MP4
                print(f"\n[{reel_id}] 3 Segment birleştiriliyor (FFmpeg 30s Final Concat)...")
                if self.agent_manager:
                    self.agent_manager.record_final_concat_start(reel_id)

                final_concat_path = reel_segments_dir / target_filename
                self.concatenator.concatenate_segments(
                    segment_paths=completed_segment_paths,
                    output_path=final_concat_path,
                    reel_id=reel_id
                )
                if self.agent_manager:
                    self.agent_manager.record_final_qc_pass(reel_id, duration=30.0)

                print(f"[{reel_id}] 30 Saniyelik Final Video oluşturuldu: {final_concat_path.name}")
                return final_concat_path

            # -------------------------------------------------------------
            # CASE C: LEGACY SINGLE SEGMENT FALLBACK
            # -------------------------------------------------------------
            flow_page.configure_agent_settings(
                approval_mode=self.config.approval_before_generation,
                video_ratio=self.config.video_ratio,
                video_outputs=self.config.video_outputs,
                video_model=self.config.video_model,
                image_ratio=self.config.image_ratio,
                image_outputs=self.config.image_outputs,
                image_model=self.config.image_model,
                target_duration=self.config.video_duration
            )

            flow_page.enter_prompt(plan.prompt, target_duration=self.config.video_duration)

            if not self.config.allow_real_generation:
                dummy_test_path = self.config.workspace_downloads_dir / target_filename
                if not dummy_test_path.exists():
                    dummy_test_path.write_bytes(b"TEST_VIDEO_PLACEHOLDER")
                return dummy_test_path

            session = GenerationSession(
                reel_id=reel_id,
                flow_project_url=project_url,
                prompt_hash=hashlib.sha256(plan.prompt.strip().encode("utf-8")).hexdigest()[:16]
            )
            flow_page.trigger_generation(allow_real_generation=True, session=session)

            return flow_page.wait_for_completion_and_download(
                target_filename=target_filename,
                timeout_minutes=self.config.generation_timeout_minutes,
                target_duration=self.config.video_duration,
                session=session
            )

class MockVideoProvider(VideoProvider):
    """Test video provider creating valid vertical 9:16 MP4s (3x10s segments = 30s final)."""

    def __init__(self, output_dir: Path, agent_manager: Optional[Any] = None):
        self.output_dir = Path(output_dir).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.agent_manager = agent_manager
        self.concatenator = VideoConcatenator(workspace_dir=self.output_dir)
        self.frame_extractor = FrameExtractor(output_dir=self.output_dir / "frames")

    def generate_single_video(
        self,
        plan: ReelConceptPlan,
        reel_id: str,
        target_filename: str,
        flow_project_url: Optional[str] = None,
        resume_from: Optional[str] = None
    ) -> Path:
        """Create 3x10s mock segments with synthetic motion and concatenate into a 30s MP4."""
        segments_dir = self.output_dir / reel_id
        segments_dir.mkdir(parents=True, exist_ok=True)

        if plan.segments:
            seg_paths = []
            for seg in plan.segments:
                if self.agent_manager:
                    self.agent_manager.record_flow_generation_start(reel_id, seg.index, len(plan.segments))

                seg_file = segments_dir / f"segment_{seg.index:02d}.mp4"
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-f", "lavfi",
                    "-i", f"testsrc=size=540x960:rate=30",
                    "-t", "10",
                    "-c:v", "libx264",
                    "-pix_fmt", "yuv420p",
                    str(seg_file)
                ]
                try:
                    subprocess.run(cmd, capture_output=True, check=True)
                except Exception:
                    fallback_cmd = [
                        "ffmpeg",
                        "-y",
                        "-f", "lavfi",
                        "-i", f"color=c=blue:s=540x960:d=10",
                        "-c:v", "libx264",
                        str(seg_file)
                    ]
                    try:
                        subprocess.run(fallback_cmd, capture_output=True, check=True)
                    except Exception:
                        seg_file.write_bytes(b"MOCK_MP4_SEGMENT_BYTES" * 500)

                if self.agent_manager:
                    self.agent_manager.record_flow_segment_downloaded(reel_id, seg.index)

                # Extract frame
                self.frame_extractor.extract_end_frame(seg_file, f"segment_{seg.index:02d}_end.jpg", reel_id)
                seg.local_file = seg_file
                seg.status = "READY"

                if self.agent_manager:
                    self.agent_manager.record_segment_qc_pass(reel_id, seg.index)

                seg_paths.append(seg_file)

            if self.agent_manager:
                self.agent_manager.record_final_concat_start(reel_id)

            final_file = self.output_dir / target_filename
            res = self.concatenator.concatenate_segments(seg_paths, final_file, reel_id)

            if self.agent_manager:
                self.agent_manager.record_final_qc_pass(reel_id, duration=30.0)

            return res
        else:
            # Single video fallback
            target_path = self.output_dir / target_filename
            cmd = [
                "ffmpeg",
                "-y",
                "-f", "lavfi",
                "-i", "testsrc=size=540x960:rate=30",
                "-t", "10",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                str(target_path)
            ]
            try:
                subprocess.run(cmd, capture_output=True, check=True)
            except Exception:
                target_path.write_bytes(b"MOCK_MP4_BYTES" * 500)
            return target_path
