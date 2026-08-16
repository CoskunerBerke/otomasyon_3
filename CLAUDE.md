# Reels AI Factory — Permanent Repository Rules

These rules are durable and apply to every future Claude Code session in this repository,
not just the repair that introduced this file. They exist because violating them has
already caused a real production incident (2026-08-16: a MockVideoProvider test video was
scanned as live inventory and uploaded to YouTube as REEL-2026-0001).

## Non-negotiable safety rules

1. **V3 only.** Any Reel entering live publishing must have `pipeline_version == 3` and
   `content_mode == "silent_global_step_by_step"`. No legacy V1/V2 media in live paths.
2. **REEL-2026-0010 is permanently excluded** from all live inventory/publishing. It is the
   dedicated diagnostic/smoke-test Reel ID. Never reuse it, never treat it as production
   inventory, regardless of what any state file claims.
3. **Filename pattern is never proof of production provenance.** A file matching
   `clean_REEL-*.mp4` is not eligible for live inventory on that basis alone. Eligibility
   requires a persisted `ReelState` with `source == "flow_live_generation"` — see
   `automation/publishing/eligibility.py:is_live_production_eligible`. Absence of state
   means ineligible, not eligible-by-default.
4. **No phantom COMPLETE reels.** A slot may only be marked `generation_status=COMPLETE` /
   `qc_status=PASS` when a real QC-passed final MP4 actually exists and has been validated.
   Never fabricate these fields unconditionally.
5. **Reel ID invariant.** Before any live upload: `slot.reel_id == ReelState.reel_id ==
   PublishRecord.reel_id == resolved video filename's reel ID`. If they disagree, block
   with `REEL_ID_MEDIA_MISMATCH` before upload. Never "best guess" the file.
6. **Metadata must come from the real content plan**, via `PublishingMetadataBuilder` /
   `ReelConceptPlan`, never a generic fallback string. Generic titles like
   `"Architectural Marvel REEL-..."` are explicitly rejected by the pre-publish gate
   (`automation/publishing/preflight_gate.py:is_placeholder_metadata`) — do not
   reintroduce a fallback that looks like that.
7. **Hashtags are appended exactly once.** The UI observer layer that actually writes to
   the platform (`YouTubeStudioUIObserver.fill_details`,
   `TikTokUIObserver.replace_caption`) is the single authoritative place hashtags get
   joined onto the caption/description. Do not also embed them into
   `PublishRecord.description` upstream — that produces duplicated hashtag blocks.
8. **`PublishRecord` uses `last_error`, not `error_message`.** `error_message` is not a
   field on `PublishRecord` (it exists on `QCResult` and Instagram's `PublishResult` —
   those are fine). Referencing `PublishRecord.error_message` is always a bug.

## Kural 31 (Rule 31) — browser automation

- **Maximum 2 safe semantic selector strategies per single UI action.**
- **Never** use `force=True`, JavaScript `click()`/`dispatchEvent`, pointer-events hacks,
  overlay removal, manual aria/checked attribute mutation, or dynamic hash-based CSS class
  hardcoding.
- If the real DOM is genuinely required and cannot be safely inferred from existing
  evidence (logs, captured HTML/screenshots in `screenshots/errors/`), the correct
  response is `NEEDS_USER_HTML` with the exact element(s) needed — never guess.
- Never click an immediate-publish control ("Hemen paylaş" / "Post now" / "Şimdi paylaş").
  Schedule mode must be verified active before any final submit click.

## Production safety

- Do not auto-delete or auto-modify remote platform content (YouTube/TikTok/Instagram)
  under any circumstance. If a bad remote draft/upload is found, quarantine it locally
  (mark the local `ReelState`/`PublishRecord`) and report
  `MANUAL_REMOTE_CLEANUP_RECOMMENDED` — never delete it automatically.
- Real platform operations (live Flow generation, live YouTube/TikTok/Instagram
  publishing, Telegram sends) require explicit user instruction for that specific run.
  Do not run `HAFTALIK_14_REEL_URET_VE_PLANLA.bat` or any `--live` invocation as part of
  a repair/analysis task unless the user explicitly asks for a live run.
- Resume/idempotency first: never re-spend Flow credits or re-upload when local/remote
  state already shows the work is done. Preserve existing completed segments/final videos.
- Never print `.env` contents, API keys, tokens, `DATABASE_URL`, S3 secrets, Meta tokens,
  Telegram bot tokens, or `LOCAL_WORKER_API_KEY`. Read secret-bearing config only through
  existing safe config loaders.
- Preserve working production modules; prefer the smallest fix that removes the root
  cause over broad rewrites.

## Testing policy for repair/hardening tasks

- Maximum **one pytest process at a time**.
- Hard maximum of **2 pytest invocations** per repair task. If the second invocation
  fails, stop — do not run a third.
- Do not run the full existing test suite unless explicitly requested; prefer one
  focused, consolidated regression test file per repair.
- No real browser, no real Flow generation, no real YouTube/TikTok/Instagram/Telegram
  calls in tests — mocks/fakes only.
