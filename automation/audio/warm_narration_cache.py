"""
Fetch every narration line into the cache before a run, so the run never has to reach
the speech service. Lines already cached are skipped; a refused line is retried with
longer pauses, and whatever is still missing at the end is listed.

    python -m automation.audio.warm_narration_cache [--brand craftsbyman] [--slugs a,b]
"""
import argparse
import sys
import time

from automation.audio.voiceover import VoiceoverError, cached_synthesize, narration_cache_path
from automation.brands import get_brand
from automation.content.cutaway_concepts import CUTAWAY_CONCEPTS
from automation.content.hidden_build_concepts import HIDDEN_BUILD_CONCEPTS
from automation.content.narration_lines import NARRATION_LINES
from automation.content.story_concepts import STORY_CONCEPTS

BRAND_LIBRARIES = {
    "buildverse": list(STORY_CONCEPTS) + list(CUTAWAY_CONCEPTS),
    "craftsbyman": list(HIDDEN_BUILD_CONCEPTS),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", default=None)
    ap.add_argument("--slugs", default="")
    ap.add_argument("--rounds", type=int, default=6)
    args = ap.parse_args()

    brands = [args.brand] if args.brand else list(BRAND_LIBRARIES)
    wanted = {s for s in args.slugs.split(",") if s}
    todo = []
    for b in brands:
        voice = get_brand(b).narration_voice
        for c in BRAND_LIBRARIES[b]:
            if wanted and c.id_slug not in wanted:
                continue
            for text in NARRATION_LINES.get(c.id_slug, {}).values():
                todo.append((text, voice))

    for round_no in range(1, args.rounds + 1):
        missing = [(t, v) for t, v in todo if not narration_cache_path(t, v).exists()]
        print(f"round {round_no}: {len(todo) - len(missing)}/{len(todo)} cached", flush=True)
        if not missing:
            return 0
        for text, voice in missing:
            try:
                cached_synthesize(text, voice, narration_cache_path(text, voice).with_suffix(".probe.mp3"))
                narration_cache_path(text, voice).with_suffix(".probe.mp3").unlink(missing_ok=True)
            except VoiceoverError as e:
                print(f"  refused: {str(e)[:90]}", flush=True)
                break
        time.sleep(60 * round_no)
    missing = [(t, v) for t, v in todo if not narration_cache_path(t, v).exists()]
    print(f"done: {len(todo) - len(missing)}/{len(todo)} cached", flush=True)
    return 0 if not missing else 1


if __name__ == "__main__":
    sys.exit(main())
