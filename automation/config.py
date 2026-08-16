"""
Configuration manager for Reels AI Factory.
Implements Windows Known Folder Desktop detection, LocalAppData Chrome profile isolation,
Chrome DevTools Protocol (CDP) settings, and strict credit & safety constraints.
"""
from dataclasses import dataclass, field
import json
import os
import sys
from pathlib import Path
from typing import Optional

MAX_VIDEOS_PER_RUN_LIMIT = 14
MAX_RETRIES_PER_VIDEO_LIMIT = 1

def get_default_chrome_profile_path() -> Path:
    """
    Get the default dedicated Chrome profile directory outside of OneDrive.
    Defaults to %LOCALAPPDATA%\\ReelsAIFactory\\chrome-profile.
    """
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        base_dir = Path(local_app_data)
    else:
        base_dir = Path.home() / "AppData" / "Local"

    profile_dir = (base_dir / "ReelsAIFactory" / "chrome-profile").resolve()
    return profile_dir

# Backward compatibility alias
get_default_browser_profile_path = get_default_chrome_profile_path

def get_real_windows_desktop() -> Path:
    """
    Safely resolve the real Windows Desktop directory, even if redirected to OneDrive.
    Queries Windows Registry (User Shell Folders) and Shell API with sensible fallbacks.
    """
    # 1. Try Windows Registry (User Shell Folders)
    if sys.platform == "win32":
        try:
            import winreg
            reg_key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
            )
            val, _ = winreg.QueryValueEx(reg_key, "Desktop")
            winreg.CloseKey(reg_key)
            if val:
                expanded = os.path.expandvars(val)
                p = Path(expanded).resolve()
                if p.exists():
                    return p
        except Exception:
            pass

        # 2. Try Windows Shell API (SHGetFolderPathW CSIDL_DESKTOPDIRECTORY = 0x0010)
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(260)
            ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, buf)
            if buf.value:
                p = Path(buf.value).resolve()
                if p.exists():
                    return p
        except Exception:
            pass

    # 3. Check common OneDrive / Windows Desktop locations
    user_profile = os.getenv("USERPROFILE")
    if user_profile:
        candidates = [
            Path(user_profile) / "OneDrive" / "Masaüstü",
            Path(user_profile) / "OneDrive" / "Desktop",
            Path(user_profile) / "Desktop",
            Path(user_profile) / "Masaüstü",
        ]
        for c in candidates:
            if c.exists():
                return c.resolve()

    home_desktop = Path.home() / "Desktop"
    if home_desktop.exists():
        return home_desktop.resolve()

    return (Path.home() / "Desktop").resolve()

@dataclass
class AppConfig:
    vault_path: Path
    output_path: Path
    videos_per_run: int = 1
    video_duration: int = 10
    final_duration_seconds: int = 30
    segment_count: int = 3
    segment_duration_seconds: int = 10
    pipeline_version: int = 3
    content_mode: str = "silent_global_step_by_step"
    video_ratio: str = "9:16"
    video_outputs: int = 1
    video_model: str = "Omni Flash"
    image_ratio: str = "9:16"
    image_outputs: int = 2
    image_model: str = "Nano Banana 2"
    approval_before_generation: str = "never"
    notifications_enabled: bool = True
    audio_enabled: bool = False
    generation_timeout_minutes: int = 20
    max_retries_per_video: int = 1
    browser_headless: bool = False
    reject_wrong_ratio: bool = True
    flow_url: str = "https://labs.google/fx/tools/flow"
    chrome_debug_port: int = 9222
    chrome_profile_dir: Path = field(default_factory=get_default_chrome_profile_path)
    keep_chrome_open: bool = True
    allow_real_generation: bool = True
    workspace_downloads_dir: Path = field(default_factory=lambda: Path("workspace/downloads").resolve())
    workspace_segments_dir: Path = field(default_factory=lambda: Path("workspace/segments").resolve())
    workspace_frames_dir: Path = field(default_factory=lambda: Path("workspace/frames").resolve())
    screenshots_dir: Path = field(default_factory=lambda: Path("screenshots/errors").resolve())
    logs_dir: Path = field(default_factory=lambda: Path("logs").resolve())
    agent_observability_enabled: bool = True
    agent_message_logging: bool = True
    agent_control_center_enabled: bool = True
    agent_graph_nodes_enabled: bool = True
    agent_poll_write_enabled: bool = False
    meaningful_message_nodes_enabled: bool = True

    @property
    def browser_profile_dir(self) -> Path:
        return self.chrome_profile_dir

    def validate(self) -> None:
        """Validate safety bounds and paths."""
        if self.videos_per_run > MAX_VIDEOS_PER_RUN_LIMIT:
            raise ValueError(f"videos_per_run exceeds hard safety limit of {MAX_VIDEOS_PER_RUN_LIMIT}")
        if self.videos_per_run < 1:
            raise ValueError("videos_per_run must be at least 1")
        if self.max_retries_per_video > MAX_RETRIES_PER_VIDEO_LIMIT:
            raise ValueError(f"max_retries_per_video exceeds safety limit of {MAX_RETRIES_PER_VIDEO_LIMIT}")
        if not self.vault_path.exists():
            raise FileNotFoundError(f"Obsidian vault path does not exist: {self.vault_path}")

def resolve_path(path_str: str) -> Path:
    """Expand environment variables and resolve absolute path."""
    expanded = os.path.expandvars(path_str)
    return Path(expanded).resolve()

def auto_detect_vault() -> Optional[Path]:
    """
    Safely look for Reels_AI_Studio vault without full-disk scans:
    1. Check obsidian.json
    2. Check common user directories
    """
    appdata = os.getenv("APPDATA")
    if appdata:
        obsidian_json = Path(appdata) / "obsidian" / "obsidian.json"
        if obsidian_json.exists():
            try:
                with open(obsidian_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    vaults = data.get("vaults", {})
                    for v in vaults.values():
                        v_path = v.get("path")
                        if v_path and "Reels_AI_Studio" in v_path:
                            candidate = Path(v_path)
                            if candidate.exists():
                                return candidate
            except Exception:
                pass

    user_profile = os.getenv("USERPROFILE")
    if user_profile:
        candidates = [
            Path(user_profile) / "obsidian" / "Reels_AI_Studio",
            Path(user_profile) / "Documents" / "Reels_AI_Studio",
            Path(user_profile) / "OneDrive" / "Masaüstü" / "Reels_AI_Studio",
            Path(user_profile) / "Desktop" / "Reels_AI_Studio",
        ]
        for c in candidates:
            if c.exists():
                return c

    return None

def load_config(config_file: Optional[str] = None, count_override: Optional[int] = None) -> AppConfig:
    """
    Load configuration from JSON file or create with sensible defaults.
    """
    base_dir = Path(__file__).parent.parent.resolve()

    config_path = None
    if config_file:
        config_path = Path(config_file).resolve()
    else:
        local_candidate = base_dir / "config.local.json"
        example_candidate = base_dir / "config.example.json"
        if local_candidate.exists():
            config_path = local_candidate
        elif example_candidate.exists():
            config_path = example_candidate

    data = {}
    if config_path and config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

    # Vault path resolution
    vault_str = data.get("vault_path", "").strip()
    if vault_str:
        vault_path = resolve_path(vault_str)
    else:
        detected = auto_detect_vault()
        if detected:
            vault_path = detected
        else:
            raise FileNotFoundError(
                "Obsidian kasası ('Reels_AI_Studio') otomatik bulunamadı. "
                "Lütfen config.local.json dosyasındaki 'vault_path' alanını doldurun."
            )

    # Output path resolution (Real Windows Desktop / AI_Reels by default)
    output_str = data.get("output_path", "").strip()
    if output_str:
        output_path = resolve_path(output_str)
    else:
        output_path = (get_real_windows_desktop() / "AI_Reels").resolve()

    # Chrome Profile path resolution (%LOCALAPPDATA%\ReelsAIFactory\chrome-profile by default)
    profile_str = (
        data.get("chrome_profile_path")
        or data.get("chrome_profile_dir")
        or data.get("browser_profile_path")
        or data.get("browser_profile_dir", "")
    ).strip()

    if profile_str:
        chrome_profile_dir = resolve_path(profile_str)
    else:
        chrome_profile_dir = get_default_chrome_profile_path()

    videos_per_run = data.get("videos_per_run", 1)
    if count_override is not None:
        videos_per_run = count_override

    # Hard cap safety
    if videos_per_run > MAX_VIDEOS_PER_RUN_LIMIT:
        videos_per_run = MAX_VIDEOS_PER_RUN_LIMIT

    cfg = AppConfig(
        vault_path=vault_path,
        output_path=output_path,
        videos_per_run=videos_per_run,
        video_duration=data.get("video_duration", 10),
        final_duration_seconds=data.get("final_duration_seconds", 30),
        segment_count=data.get("segment_count", 3),
        segment_duration_seconds=data.get("segment_duration_seconds", 10),
        pipeline_version=data.get("pipeline_version", 3),
        content_mode=data.get("content_mode", "silent_global_step_by_step"),
        video_ratio=data.get("video_ratio", "9:16"),
        video_outputs=data.get("video_outputs", 1),
        video_model=data.get("video_model", "Omni Flash"),
        image_ratio=data.get("image_ratio", "9:16"),
        image_outputs=data.get("image_outputs", 2),
        image_model=data.get("image_model", "Nano Banana 2"),
        approval_before_generation=data.get("approval_before_generation", "never"),
        notifications_enabled=data.get("notifications_enabled", True),
        audio_enabled=data.get("audio_enabled", False),
        generation_timeout_minutes=data.get("generation_timeout_minutes", 20),
        max_retries_per_video=min(data.get("max_retries_per_video", 1), MAX_RETRIES_PER_VIDEO_LIMIT),
        browser_headless=data.get("browser_headless", False),
        reject_wrong_ratio=data.get("reject_wrong_ratio", True),
        flow_url=data.get("flow_url", "https://labs.google/fx/tools/flow"),
        chrome_debug_port=int(data.get("chrome_debug_port", 9222)),
        chrome_profile_dir=chrome_profile_dir,
        keep_chrome_open=data.get("keep_chrome_open", True),
        allow_real_generation=data.get("allow_real_generation", True),
        workspace_downloads_dir=(base_dir / "workspace" / "downloads").resolve(),
        workspace_segments_dir=(base_dir / "workspace" / "segments").resolve(),
        workspace_frames_dir=(base_dir / "workspace" / "frames").resolve(),
        screenshots_dir=(base_dir / "screenshots" / "errors").resolve(),
        logs_dir=(base_dir / "logs").resolve(),
        agent_observability_enabled=data.get("agent_observability_enabled", True),
        agent_message_logging=data.get("agent_message_logging", True),
        agent_control_center_enabled=data.get("agent_control_center_enabled", True),
        agent_graph_nodes_enabled=data.get("agent_graph_nodes_enabled", True),
        agent_poll_write_enabled=data.get("agent_poll_write_enabled", False),
        meaningful_message_nodes_enabled=data.get("meaningful_message_nodes_enabled", True),
    )

    # Ensure required runtime folders exist
    cfg.chrome_profile_dir.mkdir(parents=True, exist_ok=True)
    cfg.workspace_downloads_dir.mkdir(parents=True, exist_ok=True)
    cfg.workspace_segments_dir.mkdir(parents=True, exist_ok=True)
    cfg.workspace_frames_dir.mkdir(parents=True, exist_ok=True)
    cfg.screenshots_dir.mkdir(parents=True, exist_ok=True)
    cfg.logs_dir.mkdir(parents=True, exist_ok=True)
    cfg.output_path.mkdir(parents=True, exist_ok=True)

    cfg.validate()
    return cfg
