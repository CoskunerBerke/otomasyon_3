"""
Narration and output quality, added 2026-10-06.

BuildVerse wanted a plain narrator over its Reels and sharper uploads: the finals were
720x1280 at about 2.5 Mbps, straight from Flow's free 720p download. These pin the
narration scripts to real concepts and to the length a segment can hold, the mixer's
behaviour on real FFmpeg output (speech is faked -- no network), the 1080x1920 encode,
and the rule that only a real Flow render is ever narrated.
"""
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from automation.audio.voiceover import VoiceoverError, VoiceoverMixer
from automation.brands import BUILDVERSE, CRAFTSBYMAN
from automation.content.cutaway_concepts import CUTAWAY_CONCEPTS
from automation.content.hidden_build_concepts import HIDDEN_BUILD_CONCEPTS
from automation.content.narration_lines import BEATS, MAX_WORDS_PER_LINE, NARRATION_LINES
from automation.content.story_concepts import STORY_CONCEPTS
from automation.flow.generator import GoogleFlowWebProvider, MockVideoProvider
from automation.quality.concatenator import OUTPUT_HEIGHT, OUTPUT_WIDTH, VideoConcatenator
from automation.simple_weekly_pipeline import SimpleWeeklyPipeline

needs_ffmpeg = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg not on PATH"
)


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], check=True)


def _probe(path: Path, entries: str) -> str:
    return subprocess.run(
        ["ffprobe", "-v", "error", *entries.split(), "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def _clip(path: Path, seconds: float, size: str = "720x1280", audio: bool = True) -> Path:
    args = ["-f", "lavfi", "-i", f"testsrc=size={size}:rate=30:duration={seconds}"]
    if audio:
        args += ["-f", "lavfi", "-i", f"anoisesrc=d={seconds}:a=0.05", "-c:a", "aac", "-shortest"]
    _ffmpeg(*args, "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path))
    return path


def _tone_synth(seconds: float):
    def synth(text, voice, out_path):
        _ffmpeg("-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", str(out_path.with_suffix(".mp3")))
        if out_path.suffix != ".mp3":
            out_path.with_suffix(".mp3").rename(out_path)
    return synth


# ---------------------------------------------------------------- scripts


def test_every_buildverse_concept_has_a_full_script():
    for concept in list(STORY_CONCEPTS) + list(CUTAWAY_CONCEPTS):
        lines = NARRATION_LINES.get(concept.id_slug)
        assert lines, f"{concept.id_slug} has no narration"
        assert tuple(lines) == BEATS, concept.id_slug


def test_every_script_belongs_to_a_real_concept_and_fits_its_segment():
    known = {c.id_slug for c in list(STORY_CONCEPTS) + list(CUTAWAY_CONCEPTS) + list(HIDDEN_BUILD_CONCEPTS)}
    for slug, lines in NARRATION_LINES.items():
        assert slug in known, f"narration for unknown concept '{slug}'"
        for beat, text in lines.items():
            assert text.strip(), (slug, beat)
            assert len(text.split()) <= MAX_WORDS_PER_LINE, (slug, beat, text)


def test_slugs_do_not_collide_across_libraries():
    """Narration is keyed by slug alone, so a slug shared by two libraries would mix scripts."""
    slugs = [c.id_slug for c in list(STORY_CONCEPTS) + list(CUTAWAY_CONCEPTS) + list(HIDDEN_BUILD_CONCEPTS)]
    assert len(slugs) == len(set(slugs))


def test_both_brands_have_a_voice():
    assert BUILDVERSE.narration_voice
    assert CRAFTSBYMAN.narration_voice
    assert BUILDVERSE.narration_voice != CRAFTSBYMAN.narration_voice


# ---------------------------------------------------------------- mixer


@needs_ffmpeg
def test_mixer_adds_narration_and_leaves_the_picture_alone(tmp_path):
    video = _clip(tmp_path / "in.mp4", 9)
    out = VoiceoverMixer("test-voice", synthesize=_tone_synth(1.0)).apply(
        video, {"before": "a", "turn": "b", "after": "c"}, tmp_path / "narrated" / "in.mp4"
    )
    assert out.exists()
    assert _probe(out, "-select_streams a -show_entries stream=codec_name") == "aac"
    assert _probe(out, "-select_streams v -show_entries stream=width,height") == "720,1280"
    assert abs(float(_probe(out, "-show_entries format=duration")) - 9.0) < 0.3


@needs_ffmpeg
def test_mixer_works_on_a_silent_video(tmp_path):
    video = _clip(tmp_path / "in.mp4", 9, audio=False)
    out = VoiceoverMixer("test-voice", synthesize=_tone_synth(1.0)).apply(
        video, {"before": "a", "turn": "b", "after": "c"}, tmp_path / "out.mp4"
    )
    assert _probe(out, "-select_streams a -show_entries stream=codec_name") == "aac"


@needs_ffmpeg
def test_a_line_too_long_for_its_segment_fails_loudly(tmp_path):
    video = _clip(tmp_path / "in.mp4", 9)
    with pytest.raises(VoiceoverError, match="VOICEOVER_LINE_TOO_LONG"):
        VoiceoverMixer("test-voice", synthesize=_tone_synth(6.0)).apply(
            video, {"before": "a", "turn": "b", "after": "c"}, tmp_path / "out.mp4"
        )


def test_an_incomplete_script_is_refused(tmp_path):
    with pytest.raises(VoiceoverError, match="VOICEOVER_BAD_SCRIPT"):
        VoiceoverMixer("test-voice", ffmpeg_bin="ffmpeg", ffprobe_bin="ffprobe").apply(
            tmp_path / "in.mp4", {"before": "a", "after": "c"}, tmp_path / "out.mp4"
        )


def test_missing_ffmpeg_never_passes_silently(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(VoiceoverError, match="VOICEOVER_FFMPEG_MISSING"):
        VoiceoverMixer("test-voice").apply(
            tmp_path / "in.mp4", {"before": "a", "turn": "b", "after": "c"}, tmp_path / "out.mp4"
        )


# ---------------------------------------------------------------- quality


@needs_ffmpeg
def test_final_concat_is_1080x1920(tmp_path):
    segs = [_clip(tmp_path / f"s{i}.mp4", 1) for i in range(3)]
    out = VideoConcatenator(workspace_dir=tmp_path).concatenate_segments(
        segs, tmp_path / "final.mp4", "REEL-TEST", preserve_audio=True
    )
    assert _probe(out, "-select_streams v -show_entries stream=width,height") == f"{OUTPUT_WIDTH},{OUTPUT_HEIGHT}"
    assert _probe(out, "-select_streams a -show_entries stream=codec_name") == "aac"


# ---------------------------------------------------------------- pipeline gate


def _fake_pipeline(provider, voice="test-voice"):
    return SimpleNamespace(brand=SimpleNamespace(narration_voice=voice), flow_provider=provider)


def _plan(slug):
    return SimpleNamespace(concept_def=SimpleNamespace(id_slug=slug))


@pytest.mark.parametrize("provider", [MagicMock(), MockVideoProvider.__new__(MockVideoProvider)])
def test_only_a_real_flow_render_is_narrated(tmp_path, monkeypatch, provider):
    mixer = MagicMock()
    monkeypatch.setattr("automation.simple_weekly_pipeline.VoiceoverMixer", mixer)
    video = tmp_path / "clean_REEL-2026-0001_pompeii-story.mp4"
    assert SimpleWeeklyPipeline._narrate(_fake_pipeline(provider), _plan("pompeii"), video) == video
    mixer.assert_not_called()


def test_real_render_is_narrated_under_the_same_file_name(tmp_path, monkeypatch):
    mixer = MagicMock()
    mixer.return_value.apply.side_effect = lambda src, lines, dst: dst
    monkeypatch.setattr("automation.simple_weekly_pipeline.VoiceoverMixer", mixer)
    real = GoogleFlowWebProvider.__new__(GoogleFlowWebProvider)
    video = tmp_path / "clean_REEL-2026-0001_pompeii-story.mp4"

    out = SimpleWeeklyPipeline._narrate(_fake_pipeline(real), _plan("pompeii"), video)

    assert out.name == video.name and out.parent.name == "narrated"
    mixer.assert_called_once_with("test-voice")
    assert mixer.return_value.apply.call_args.args[1] == NARRATION_LINES["pompeii"]


def test_concept_without_script_or_brand_without_voice_is_left_alone(tmp_path, monkeypatch):
    mixer = MagicMock()
    monkeypatch.setattr("automation.simple_weekly_pipeline.VoiceoverMixer", mixer)
    real = GoogleFlowWebProvider.__new__(GoogleFlowWebProvider)
    video = tmp_path / "v.mp4"
    assert SimpleWeeklyPipeline._narrate(_fake_pipeline(real), _plan("locomotive-sauna"), video) == video
    assert SimpleWeeklyPipeline._narrate(_fake_pipeline(real, voice=""), _plan("pompeii"), video) == video
    mixer.assert_not_called()
