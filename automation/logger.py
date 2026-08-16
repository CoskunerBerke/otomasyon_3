"""
Centralized logging for Reels AI Factory.
Ensures clean console output, detailed file logs, and strict secret masking.
"""
import logging
import re
import sys
import time
from pathlib import Path
from typing import Optional

# Sensitive patterns that must never appear in logs
SENSITIVE_PATTERNS = [
    re.compile(r'(cookie[s]?\s*[:=]\s*)[^\s;,\n]+', re.IGNORECASE),
    re.compile(r'(token[s]?\s*[:=]\s*)[^\s;,\n]+', re.IGNORECASE),
    re.compile(r'(password[s]?\s*[:=]\s*)[^\s;,\n]+', re.IGNORECASE),
    re.compile(r'(authorization\s*[:=]\s*Bearer\s+)[^\s;,\n]+', re.IGNORECASE),
    re.compile(r'(sessionid[s]?\s*[:=]\s*)[^\s;,\n]+', re.IGNORECASE),
]

class SanitizeFilter(logging.Filter):
    """Filters out any potential secrets from log messages."""
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            sanitized = record.msg
            for pattern in SENSITIVE_PATTERNS:
                sanitized = pattern.sub(r'\1[REDACTED]', sanitized)
            record.msg = sanitized
        return True

def setup_logger(logs_dir: Optional[Path] = None, run_name: Optional[str] = None) -> logging.Logger:
    """Initialize and configure global application logger."""
    logger = logging.getLogger("ReelsAIFactory")
    logger.setLevel(logging.DEBUG)

    # Avoid duplicate handlers if setup is called multiple times
    if logger.hasHandlers():
        logger.handlers.clear()

    # Sanitizer filter
    sanitizer = SanitizeFilter()

    # Formatter for log files
    file_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s:%(module)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Formatter for console output
    console_formatter = logging.Formatter(
        "%(message)s"
    )

    # Console Handler (INFO+)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)
    console_handler.addFilter(sanitizer)
    logger.addHandler(console_handler)

    # File Handler (DEBUG+)
    if logs_dir is None:
        base_dir = Path(__file__).parent.parent.resolve()
        logs_dir = base_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    if not run_name:
        run_name = f"run-{time.strftime('%Y-%m-%d-%H%M%S')}"

    log_file_path = logs_dir / f"{run_name}.log"
    file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)
    file_handler.addFilter(sanitizer)
    logger.addHandler(file_handler)

    return logger

def print_banner(reels_count: int = 1) -> None:
    flow_gens = reels_count * 3
    print("========================================")
    print("        REELS AI FACTORY V3")
    print("========================================")
    print(f"Format: 1 Reel = 3 Segment × 10s = 30s Final MP4")
    print(f"Kredi Modeli: {reels_count} Reel = {flow_gens} Flow video üretimi")
    print("========================================")
    print()

def print_step(step_num: int, total_steps: int, title: str, detail: Optional[str] = None) -> None:
    print(f"[{step_num}/{total_steps}] {title}")
    if detail:
        print(f"      {detail}")
    print()
