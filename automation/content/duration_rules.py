"""
Model duration compatibility rules and prompt duration sanitization for Google Flow.
Ensures prompts strictly adhere to Omni Flash allowed durations (4, 6, 8, 10s) with 8s default.
"""
import re
from typing import Set, Dict

MODEL_DURATION_RULES: Dict[str, Set[int]] = {
    "Omni Flash": {4, 6, 8, 10}
}

DEFAULT_VIDEO_DURATION = 10
DEFAULT_SEGMENT_DURATION = 10
DEFAULT_FINAL_DURATION = 30

def sanitize_video_duration(prompt: str, model_name: str = "Omni Flash", target_duration: int = DEFAULT_VIDEO_DURATION) -> str:
    """
    Sanitize and enforce compatible duration in prompt text for the selected Flow model.
    Replaces 5-second, 5 seconds, 15 seconds, etc. with valid target_duration (default 8s).
    """
    allowed_durations = MODEL_DURATION_RULES.get(model_name, {4, 6, 8, 10})
    if target_duration not in allowed_durations:
        target_duration = DEFAULT_VIDEO_DURATION

    # Replace variations like '5-second', '5 second', '15-second' in introductory sentences
    sanitized = re.sub(
        r'\b(?:[1-9]\d?)\s*-\s*second\b',
        f"{target_duration}-second",
        prompt,
        flags=re.IGNORECASE
    )

    # Replace 'Duration: X seconds' or 'Duration: X second'
    sanitized = re.sub(
        r'Duration\s*:\s*\d+\s*seconds?',
        f"Duration: {target_duration} seconds",
        sanitized,
        flags=re.IGNORECASE
    )

    # Replace 'X seconds' in generic duration specifications if present
    sanitized = re.sub(
        r'\b5\s*seconds\b',
        f"{target_duration} seconds",
        sanitized,
        flags=re.IGNORECASE
    )

    # If neither 'X-second' nor 'Duration:' was present, append clean duration spec
    if f"{target_duration}-second" not in sanitized and f"Duration: {target_duration} seconds" not in sanitized:
        sanitized += f"\n\nAspect ratio: 9:16 vertical. Duration: {target_duration} seconds. Optimized for Instagram Reels, TikTok and YouTube Shorts."

    return sanitized
