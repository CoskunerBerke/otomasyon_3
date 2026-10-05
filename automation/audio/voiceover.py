"""
Mixes a spoken narration over a finished Reel.

Each Reel is three segments of equal length, and each beat's line is placed at the start
of its own segment, so the voice tracks the picture without any timing data from Flow.
The Reel's own ambient sound stays underneath and is ducked while the voice speaks. The
picture is copied untouched -- this step changes audio only.

Every failure raises. A Reel that should carry narration and silently goes out without it
is the same class of bug as the concatenator that once pasted segment bytes together
when FFmpeg was missing; the segments stay on disk, so a rerun costs no Flow credits.
"""
import asyncio
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Dict, Optional

from automation.content.narration_lines import BEATS

# Slightly slower than the voice's default reads as calm narration rather than an advert.
DEFAULT_RATE = "-4%"

# Where each line starts inside its segment, and how much of the segment end it must clear.
LEAD_IN_SECONDS = 0.5
TAIL_SECONDS = 0.3

# Shorts and TikTok play at about -14 LUFS; ducking alone left the mix near -19.
LOUDNESS_FILTER = "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000"

# A line slightly too long is sped up to fit; one far too long is a script problem.
MAX_TEMPO = 1.25

# (text, voice, output path) -> writes an audio file at output path.
Synthesizer = Callable[[str, str, Path], None]


class VoiceoverError(RuntimeError):
    pass


def edge_tts_synthesize(text: str, voice: str, out_path: Path) -> None:
    try:
        import edge_tts
    except ImportError as e:
        raise VoiceoverError("VOICEOVER_TTS_MISSING: edge-tts is not installed (pip install edge-tts)") from e

    async def _run() -> None:
        await edge_tts.Communicate(text, voice, rate=DEFAULT_RATE).save(str(out_path))

    try:
        asyncio.run(_run())
    except Exception as e:
        raise VoiceoverError(f"VOICEOVER_TTS_FAILED: {e}") from e
    if not out_path.exists() or out_path.stat().st_size < 1000:
        raise VoiceoverError(f"VOICEOVER_TTS_FAILED: no audio written for '{text[:40]}'")


class VoiceoverMixer:
    def __init__(
        self,
        voice: str,
        synthesize: Synthesizer = edge_tts_synthesize,
        ffmpeg_bin: Optional[str] = None,
        ffprobe_bin: Optional[str] = None,
    ):
        if not voice:
            raise VoiceoverError("VOICEOVER_NO_VOICE: the brand has no narration voice")
        self.voice = voice
        self.synthesize = synthesize
        self.ffmpeg_bin = ffmpeg_bin or shutil.which("ffmpeg")
        self.ffprobe_bin = ffprobe_bin or shutil.which("ffprobe")

    def _probe(self, path: Path, entries: str) -> str:
        res = subprocess.run(
            [self.ffprobe_bin, "-v", "error", *entries.split(), "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=60,
        )
        return res.stdout.strip()

    def _duration(self, path: Path) -> float:
        try:
            return float(self._probe(path, "-show_entries format=duration"))
        except ValueError as e:
            raise VoiceoverError(f"VOICEOVER_PROBE_FAILED: cannot read duration of {path.name}") from e

    def _has_audio(self, path: Path) -> bool:
        return bool(self._probe(path, "-select_streams a -show_entries stream=index"))

    def apply(self, video_in: Path, lines: Dict[str, str], video_out: Path) -> Path:
        if not self.ffmpeg_bin or not self.ffprobe_bin:
            raise VoiceoverError("VOICEOVER_FFMPEG_MISSING: ffmpeg/ffprobe not on PATH")
        if set(lines) != set(BEATS) or not all(lines.values()):
            raise VoiceoverError(f"VOICEOVER_BAD_SCRIPT: expected lines for {BEATS}, got {sorted(lines)}")

        video_in, video_out = Path(video_in), Path(video_out)
        video_out.parent.mkdir(parents=True, exist_ok=True)
        duration = self._duration(video_in)
        slot = duration / len(BEATS)
        room = slot - LEAD_IN_SECONDS - TAIL_SECONDS

        with tempfile.TemporaryDirectory(prefix="voiceover_") as tmp:
            clips, chains = [], []
            for i, beat in enumerate(BEATS):
                clip = Path(tmp) / f"{i}_{beat}.mp3"
                self.synthesize(lines[beat], self.voice, clip)
                spoken = self._duration(clip)
                tempo = max(1.0, spoken / room)
                if tempo > MAX_TEMPO:
                    raise VoiceoverError(
                        f"VOICEOVER_LINE_TOO_LONG: '{beat}' runs {spoken:.1f}s, segment allows {room:.1f}s"
                    )
                delay_ms = int((i * slot + LEAD_IN_SECONDS) * 1000)
                clips.append(clip)
                chains.append(
                    f"[{i + 1}:a]aresample=48000,atempo={tempo:.3f},adelay=delays={delay_ms}:all=1[v{i}]"
                )

            voice = "".join(f"[v{i}]" for i in range(len(BEATS)))
            graph = chains + [f"{voice}amix=inputs={len(BEATS)}:normalize=0,asplit=2[vkey][vmix]"]
            if self._has_audio(video_in):
                graph += [
                    "[0:a]aresample=48000[amb]",
                    "[amb][vkey]sidechaincompress=threshold=0.02:ratio=6:attack=20:release=400[duck]",
                    f"[duck][vmix]amix=inputs=2:normalize=0:duration=first,{LOUDNESS_FILTER}[aout]",
                ]
            else:
                graph += [
                    "[vkey]anullsink",
                    f"[vmix]apad,atrim=0:{duration:.3f},{LOUDNESS_FILTER}[aout]",
                ]

            cmd = [self.ffmpeg_bin, "-y", "-i", str(video_in)]
            for clip in clips:
                cmd += ["-i", str(clip)]
            cmd += [
                "-filter_complex", ";".join(graph),
                "-map", "0:v", "-map", "[aout]",
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                "-movflags", "+faststart",
                str(video_out),
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if res.returncode != 0 or not video_out.exists() or video_out.stat().st_size < 10000:
            raise VoiceoverError(f"VOICEOVER_MIX_FAILED: {res.stderr.strip()[-300:]}")
        return video_out
