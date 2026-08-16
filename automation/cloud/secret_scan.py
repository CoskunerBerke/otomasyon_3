"""
Repository Secret Leak Scanner.
Scans project files for potential credentials and secrets before git commits and deployment.
Strictly masks all discovered matches in reports.
"""
import os
import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

logger = logging.getLogger("ReelsAIFactory.SecretScan")

from .config import mask_secret

# High-entropy / known token patterns
PATTERNS = {
    "TELEGRAM_BOT_TOKEN": re.compile(r"\b\d{8,11}:[A-Za-z0-9_-]{35}\b"),
    "META_ACCESS_TOKEN": re.compile(r"\bEAA[a-zA-Z0-9]{40,}\b"),
    "POSTGRES_PASSWORD_URL": re.compile(r"postgres(?:ql)?:\/\/[a-zA-Z0-9_\-\.]+:[a-zA-Z0-9_\-\.]+@[a-zA-Z0-9_\-\.]+"),
    "S3_SECRET_KEY": re.compile(r"(?:S3_SECRET_ACCESS_KEY|aws_secret_access_key)\s*=\s*['\"]?([A-Za-z0-9\/+=]{30,})['\"]?", re.IGNORECASE)
}

EXCLUDED_DIRS = {
    ".git", ".venv", "workspace", "screenshots", "logs", "__pycache__",
    ".pytest_cache", "AI_Reels", "node_modules", "tests"
}

EXCLUDED_FILES = {
    ".env", ".env.example", ".env.railway.example"
}

MOCK_KEYWORDS = ("EXAMPLE", "PLACEHOLDER", "<", "MOCK", "FAKE", "SECRETPASS", "TEST_KEY", "ABCDEFGH")


def scan_file_for_secrets(file_path: Path) -> List[Dict[str, Any]]:
    """Scans an individual text file for secret patterns."""
    findings = []
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []

    for name, pattern in PATTERNS.items():
        for match in pattern.finditer(content):
            matched_str = match.group(0)
            # Check if it's a dummy or template placeholder
            if any(k in matched_str.upper() for k in MOCK_KEYWORDS):
                continue
            
            line_num = content[:match.start()].count("\n") + 1
            findings.append({
                "file": str(file_path),
                "line": line_num,
                "secret_type": name,
                "masked_value": mask_secret(matched_str, 3, 3)
            })
    return findings


def scan_repository(root_dir: Optional[Path] = None) -> Tuple[bool, List[Dict[str, Any]]]:
    """Scans all non-excluded project files for credentials."""
    root = (root_dir or Path(".").resolve())
    all_findings = []

    for path in root.rglob("*"):
        if path.is_file():
            # Check exclusions
            parts = path.parts
            if any(exc in parts for exc in EXCLUDED_DIRS):
                continue
            if path.name in EXCLUDED_FILES:
                continue
            if path.suffix in (".pyc", ".mp4", ".png", ".jpg", ".zip", ".tar", ".gz", ".db"):
                continue

            findings = scan_file_for_secrets(path)
            all_findings.extend(findings)

    is_clean = len(all_findings) == 0
    return is_clean, all_findings


def main():
    print("=" * 60)
    print("REELS AI FACTORY - REPOSITORY SECRET SCANNER")
    print("=" * 60)
    is_clean, findings = scan_repository()

    if is_clean:
        print("[PASS] No tracked credentials or leaked tokens detected.")
        print("Status: SECRET_SCAN_PASS\n")
    else:
        print(f"[FAIL] Found {len(findings)} potential secret leak(s):")
        for f in findings:
            print(f"- {f['file']}:{f['line']} [{f['secret_type']}] -> {f['masked_value']}")
        print("\nStatus: SECRET_LEAK_RISK\n")


if __name__ == "__main__":
    main()
