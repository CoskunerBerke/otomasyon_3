# How Reels AI Factory works

This document explains the engineering behind the repository: what each part does, how a week of Reels moves through the system, which rules decide what gets generated and published, and why the code is shaped the way it is. It is written for an engineer who has never seen the project. Every number below comes from the code or from a test run on this commit; file and symbol names are given so each claim can be checked.

**Contents:** [1. Scope](#1-what-it-is-and-what-it-is-not) · [2. Architecture](#2-architecture) · [3. Runtime flows](#3-runtime-flows) · [4. Data model](#4-data-model) · [5. Core logic](#5-core-logic-in-depth) · [6. Design decisions](#6-design-decisions-and-trade-offs) · [7. Testing](#7-testing-strategy) · [8. Operator runbook](#8-operator-runbook-blocked-and-terminal-states) · [9. Limitations](#9-limitations-known-gaps-and-next-steps) · [10. Code tour](#10-code-tour) · [11. Glossary](#11-glossary) · [Türkçe özet](#türkçe-özet)

## 1. What it is and what it is not

**What it is.** A Python automation that produces a weekly series of 14 vertical 30-second videos per channel (7 days × 2 slots, 19:30 and 22:00 Europe/Istanbul) and schedules them on YouTube, TikTok and Instagram. It runs for two channels that belong to the owner, BuildVerse and Crafts By Man, each with its own accounts, browser profiles, ID prefix and content format ([`brands.py`](../automation/brands.py)).

One weekly run does five things in a fixed order:

1. **Plan** 14 concepts from curated concept libraries, using the channel's own history so a concept rests before it returns.
2. **Generate** each video in Google Flow (Google's web app for video generation) by driving a real Chrome session with Playwright: three 10-second segments per Reel, joined with FFmpeg.
3. **Check** every file (stream, aspect ratio, black/empty/frozen frames, audio policy) and lock the week's plan once all 14 pass.
4. **Schedule** each Reel through the platform's own scheduler (YouTube Studio or the YouTube Data API, TikTok Studio, the instagram.com composer), so nothing has to be online at publish time.
5. **Report** the outcome on the console, in an Obsidian vault mirror and on Telegram.

**What it is not.**

- Not a generative model. The prompts are assembled deterministically from hand-written concept libraries and templates ([`content/`](../automation/content)); the "agents" in [`agents/`](../automation/agents) are deterministic bookkeeping classes, not language models. Video generation happens inside Google Flow.
- Not a hosted or multi-tenant product. Brand accounts are hard-coded in [`brands.py`](../automation/brands.py), and generation needs the owner's Windows PC with signed-in Chrome profiles.
- Not an official API integration for TikTok or the Instagram composer. Those two (and YouTube in its default `studio` mode) are driven through their web UIs, which is why a large part of the code is UI observation and defensive checks.
- The cloud control plane ([`cloud/`](../automation/cloud)) is packaged with a `Dockerfile` and is ready for Railway ([`railway.toml`](../railway.toml)), but it is optional and is not currently deployed. Everything in the weekly pipeline works without it except the optional cloud Instagram route and Telegram approvals.

**Honest status of the entry points.** The repository contains three generations of orchestration:

| Entry point | Role today |
|---|---|
| [`simple_weekly_pipeline.py`](../automation/simple_weekly_pipeline.py) | The live weekly entry point, called by the weekly `.bat` launchers and by the cloud worker command. Most of this document is about it. |
| [`run.py`](../automation/run.py) and [`publish.py`](../automation/publish.py) | The older Obsidian-centric CLIs: generate N Reels as vault notes (`03_SCRIPTS → 05_READY`), then schedule `05_READY` notes. Still in the repository and covered by tests; the README's sample output comes from `run.py --dry-run`. |
| [`weekly_orchestrator.py`](../automation/weekly_orchestrator.py) | Marked legacy in its own docstring; kept for its tests, not used by any launcher. |

## 2. Architecture

```mermaid
flowchart TB
    subgraph PC["Owner's Windows PC"]
        BAT[".bat launchers"]
        LW["local_worker.py --run-once"]
        PIPE["SimpleWeeklyPipeline<br/>(phase runner)"]
        CONTENT["Content engine<br/>concepts, rotation, prompts"]
        FLOW["Flow automation<br/>Playwright over CDP"]
        QC["QC: ffprobe,<br/>frame checks, ffmpeg"]
        GATE["Eligibility +<br/>pre-publish gate"]
        PUB["Publishers"]
        STATE[("workspace/<br/>manifest, progress, ReelState")]
        BAT --> PIPE
        LW --> PIPE
        PIPE --> CONTENT
        PIPE --> FLOW
        FLOW --> QC
        PIPE --> GATE
        GATE --> PUB
        PIPE <--> STATE
    end

    subgraph EXT["External services"]
        GFLOW["Google Flow"]
        PLAT["YouTube Studio or Data API,<br/>TikTok Studio, instagram.com"]
        TG["Telegram Bot API"]
        META["Meta Graph API"]
    end

    VAULT[("Obsidian vault")]

    subgraph CLOUD["Cloud control plane: Docker image, ready for Railway"]
        API["HTTP app"]
        SCHED["Scheduler thread"]
        IGW["Instagram worker"]
        DB[("PostgreSQL<br/>(SQLite in dev)")]
        S3[("S3-compatible bucket")]
        API --> DB
        API --> S3
        SCHED --> DB
        IGW --> DB
        IGW --> S3
    end

    FLOW --> GFLOW
    PUB --> PLAT
    PIPE -.->|"mirror notes"| VAULT
    PIPE -.->|"run summary"| TG
    LW -->|"X-Worker-Api-Key"| API
    PIPE -->|"cloud mode: MP4 + SHA-256"| API
    TG -->|"webhook + secret header"| API
    SCHED -->|"day-6 approval"| TG
    IGW --> META
```

| Component | Responsibility | Main code |
|---|---|---|
| Launchers | One-click Windows entry points: first-time install, Flow login, per-brand logins, the weekly run per brand, single-platform catch-up runs | [`*.bat`](../BUILDVERSE_HAFTALIK_14_REEL.bat) in the repo root |
| Brand registry | Per-channel identity: content mode, ID prefix, expected account handles, Chrome profiles and CDP ports, enabled platforms; refuses to publish for an unconfigured brand | [`brands.py`](../automation/brands.py) `Brand`, `ensure_publishable` |
| Weekly pipeline | Plans the week, runs the phases in order, persists every step, resumes where it stopped | [`simple_weekly_pipeline.py`](../automation/simple_weekly_pipeline.py) `SimpleWeeklyPipeline` |
| Content engine | Concept libraries, diversity scoring, per-mode providers, three-segment prompt construction | [`content/engine.py`](../automation/content/engine.py), [`content/prompt_engine.py`](../automation/content/prompt_engine.py), [`content/segment_planner.py`](../automation/content/segment_planner.py), [`content/story_planner.py`](../automation/content/story_planner.py), [`content/hidden_build_planner.py`](../automation/content/hidden_build_planner.py) |
| Content-mode registry | Single source of truth for each mode's audio policy and live eligibility | [`content/content_modes.py`](../automation/content/content_modes.py) |
| Flow automation | Connects to Chrome over CDP, one Flow project per Reel, a polling state machine per segment, safe download, concatenation | [`flow/generator.py`](../automation/flow/generator.py), [`flow/page.py`](../automation/flow/page.py), [`flow/state_machine.py`](../automation/flow/state_machine.py), [`flow/downloader.py`](../automation/flow/downloader.py) |
| Quality control | ffprobe inspection, frame sampling, audio policy, faststart remux, segment concatenation | [`quality/validator.py`](../automation/quality/validator.py), [`quality/frames.py`](../automation/quality/frames.py), [`quality/concatenator.py`](../automation/quality/concatenator.py) |
| Gates | Production provenance, Reel ID invariant, placeholder metadata, slot match, file hash | [`publishing/eligibility.py`](../automation/publishing/eligibility.py), [`publishing/preflight_gate.py`](../automation/publishing/preflight_gate.py) |
| Publishers | One per platform route, each reporting a platform status that the pipeline records | [`youtube_studio_publisher.py`](../automation/publishing/youtube_studio_publisher.py), [`youtube_publisher.py`](../automation/publishing/youtube_publisher.py), [`tiktok_publisher.py`](../automation/publishing/tiktok_publisher.py), [`instagram_web_publisher.py`](../automation/publishing/instagram_web_publisher.py) |
| Local state | Week manifest and progress files, per-Reel state, publish records | [`orchestration/batch_manifest.py`](../automation/orchestration/batch_manifest.py), [`orchestration/state_repository.py`](../automation/orchestration/state_repository.py), [`publishing/repository.py`](../automation/publishing/repository.py) |
| Obsidian | Mirror notes for the weekly pipeline; the vault is the primary store for the older `run.py` / `publish.py` path | [`orchestration/obsidian_mirror.py`](../automation/orchestration/obsidian_mirror.py), [`obsidian/reader.py`](../automation/obsidian/reader.py), [`obsidian/writer.py`](../automation/obsidian/writer.py) |
| Cloud control plane | Standard-library HTTP server: health, Telegram webhook, worker command queue, media upload; background scheduler for the day-6 approval and the Instagram worker | [`cloud/app.py`](../automation/cloud/app.py) and the rest of [`cloud/`](../automation/cloud) |
| Local worker | Heartbeat, claim one cloud command, run the weekly pipeline, report completion, mirror cloud state into the vault | [`local_worker.py`](../automation/local_worker.py), [`local_worker_cloud_client.py`](../automation/local_worker_cloud_client.py), [`media_handoff.py`](../automation/media_handoff.py) |

**The launchers.** The weekly `.bat` files call the pipeline module directly and pass `--live`:

| Launcher | What it runs |
|---|---|
| `INSTALL_FIRST_TIME.bat` | Creates `.venv`, installs `requirements.txt` and Playwright Chromium, copies `config.example.json` to `config.local.json` |
| `FLOW_LOGIN.bat` | Starts Chrome with a dedicated profile and remote debugging on port 9222 ([`flow/chrome_launcher.py`](../automation/flow/chrome_launcher.py)) for a manual Google sign-in |
| `YOUTUBE_LOGIN.bat` | Interactive OAuth for the YouTube Data API mode (`publish.py --youtube-auth`) |
| `BUILDVERSE_GIRIS.bat`, `CRAFTSBYMAN_GIRIS.bat` | Open the brand's own Chrome profiles on the brand's ports for a manual sign-in ([`publishing/brand_login.py`](../automation/publishing/brand_login.py)) |
| `BUILDVERSE_HAFTALIK_14_REEL.bat` | Weekly run for BuildVerse; options `--sessiz` (silent mode), `--ig-cloud` (cloud Instagram route) and `--dry-run` (broken, see below) |
| `CRAFTSBYMAN_HAFTALIK_14_REEL.bat` | Weekly run for Crafts By Man; options `--start-date` and `--dry-run` (broken, see below) |
| `*_SADECE_YOUTUBE/TIKTOK/INSTAGRAM.bat` | One platform phase only (`--phase`), which skips the 30-minute hold; the BuildVerse ones work on the most recent unfinished week (with none left, PLAN creates a new DRAFT week, which the phase then refuses as not locked); the Crafts By Man ones are pinned to `--week-id CBM-2026-W34` |
| `BASLAT.bat` | Older generic weekly launcher for the default brand |

The `--dry-run` option of the three weekly launchers (including `BASLAT.bat`) replaces `--live` with `--dry-run`, but the module's argument parser has no such flag ([`main`](../automation/simple_weekly_pipeline.py)), so Python exits with code 2 before anything runs. A rehearsal is the module started without `--live`, and what it actually exercises is described in [3.5](#35-what-a-rehearsal-dry-run-exercises).

There is no launcher for `local_worker.py`; it is started by hand (`python -m automation.local_worker --run-once`), and without `--run-once` it only sends one heartbeat.

## 3. Runtime flows

### 3.1 One weekly run

```mermaid
sequenceDiagram
    autonumber
    actor Op as Operator
    participant P as SimpleWeeklyPipeline
    participant C as ContentEngine
    participant F as GoogleFlowWebProvider
    participant V as VideoValidator
    participant R as BatchRepository
    participant Pub as Platform publisher
    Op->>P: weekly .bat (--live)
    P->>R: find unfinished week of this brand
    alt no unfinished week
        P->>C: rank concepts, apply rotation rules
        C-->>P: 14 ReelConceptPlans
        P->>R: save manifest.json (DRAFT) and progress.json
    end
    loop each Reel not COMPLETE
        P->>F: generate_single_video(plan)
        F-->>P: 30 s MP4 (3 x 10 s concat)
        P->>V: process_and_validate
        V-->>P: QCResult
        P->>R: save manifest, ReelState (flow_live_generation)
    end
    P->>P: validate 14 Reels, set LOCKED
    loop YouTube, then TikTok, then Instagram (skipped when all_platform_done)
        loop each Reel not yet done
            alt YouTube or TikTok
                P->>P: full pre-publish gate
                P->>R: record UPLOAD_ATTEMPTED
                P->>Pub: upload_and_schedule
            else Instagram (web or cloud route)
                P->>P: eligibility and Reel ID check only
                P->>Pub: schedule_reel or cloud handoff
            end
            Pub-->>P: status (and remote id)
            P->>R: record status in progress.json
        end
        opt platform not 14/14
            P->>P: Telegram alert, hold up to 30 min, retry every 5 min
        end
    end
    P->>Op: summary on console and Telegram
```

`SimpleWeeklyPipeline.run` ([source](../automation/simple_weekly_pipeline.py)) is a cascade: GENERATE runs only if some Reel is not `COMPLETE`, VALIDATE+LOCK only if the manifest is not `LOCKED`, and each platform only if it is enabled for the brand and not already 14/14 (`all_platform_done`). Every phase reads its own progress from disk, so re-running the same `.bat` after any failure continues where the previous run stopped and never regenerates a finished video or re-uploads a scheduled one. The one exception is a week that a rehearsal has written into: the 14/14 test does not look at the rehearsal stamp ([5.7](#57-platform-phases)). A `--phase` run executes one handler once and returns.

### 3.2 Generating one Reel in Google Flow

```mermaid
sequenceDiagram
    autonumber
    participant G as GoogleFlowWebProvider
    participant Pg as FlowPage
    participant E as FlowDecisionEngine
    participant UI as Google Flow tab
    G->>Pg: check_auth_and_security, ensure_project_for_reel
    G->>Pg: configure_agent_settings (approval Never, 9:16, output counts)
    loop segment 1..3 (skip if a valid file is on disk)
        G->>Pg: enter_prompt(segment prompt)
        Pg->>UI: read visible artifacts (baseline)
        Pg->>UI: click Generate once
        loop every 3 s, up to generation_timeout_minutes
            Pg->>UI: take_snapshot
            Pg->>E: decide_next_action(snapshot, session)
            alt new artifact, not in baseline
                E-->>Pg: DOWNLOAD_MEDIA or RECOVER_DOWNLOAD_UI
                Pg->>UI: open video, pick original-size entry
            else agent failed, retry offered (max 2)
                E-->>Pg: RETRY_AGENT_GENERATION
            else credit question (max 1)
                E-->>Pg: APPROVE_GENERATION_ONCE
            else generating
                E-->>Pg: WAIT
            end
        end
        G->>G: SHA-256 differs from earlier segments, extract end frame
    end
    G->>G: ffmpeg concat 3 segments, 30 fps H.264
```

The provider ([`flow/generator.py`](../automation/flow/generator.py) `GoogleFlowWebProvider.generate_single_video`) connects over the DevTools protocol to the installed Chrome listening on `chrome_debug_port`, not to a browser Playwright launches, so the Google session is the owner's own. If nothing listens on that port, [`CDPBrowserManager.ensure_chrome`](../automation/flow/browser.py) starts Chrome with the configured profile and `flow_url` and waits up to 15 seconds for it. A sign-in page, a CAPTCHA pattern or Flow's logged-out landing page raises `UserActionRequiredError` ([`flow/page.py`](../automation/flow/page.py) `FlowPage.check_auth_and_security`); the code never tries to get past them. The decision logic is described in [5.4](#54-the-flow-generation-state-machine).

### 3.3 Optional cloud start: Telegram approval to worker command

```mermaid
sequenceDiagram
    autonumber
    participant S as CloudScheduler
    participant A as ApprovalService
    participant T as Telegram
    participant H as HTTP app
    participant D as Database
    participant W as local_worker.py --run-once
    S->>D: list_active_weeks
    S->>A: day 6 reached and time >= WEEKLY_APPROVAL_LOCAL_TIME
    A->>T: sendMessage with EVET / HAYIR buttons
    A->>D: save approval (PENDING, expires in 48 h)
    T->>H: POST /telegram/webhook
    H->>H: secret header check before the body is read
    H->>A: handle_callback_query
    A->>A: allowed user and chat, not expired, still PENDING
    A->>D: approval APPROVED, insert GENERATE_WEEK (deduplicated)
    W->>H: GET /worker/commands/next (X-Worker-Api-Key)
    H->>D: claim oldest PENDING command
    H-->>W: GENERATE_WEEK for the approved week
    W->>W: SimpleWeeklyPipeline.run()
    W->>H: POST /worker/commands/{id}/complete
```

The scheduler thread wakes every 30 seconds ([`cloud/app.py`](../automation/cloud/app.py) `CloudApp._scheduler_loop`) and only does work when `ENABLE_WEEKLY_SCHEDULER` or `ENABLE_INSTAGRAM_WORKER` is true; both default to false. "Day 6" is `start_date + 5 days` of a week row in `cloud_weeks` ([`cloud/scheduler.py`](../automation/cloud/scheduler.py) `CloudScheduler.check_day6_approvals`). The worker reports `COMPLETE` when the pipeline returns success and `FAILED_RETRYABLE` with the last phase message otherwise ([`local_worker.py`](../automation/local_worker.py) `LocalWorker.process_next_command`).

**How the command's week ID meets the local pipeline.** The two sides count weeks differently. The cloud asks about `next_week_id`, the ISO week of the cloud row's `start_date + 7 days`; the local pipeline starts a week the day after the brand's last slot that reached a platform. `LocalWorker` builds one `SimpleWeeklyPipeline` for the default brand (BuildVerse), live, with the default 30-minute hold, and sets `pipeline.week_id` to the command's ID before `run()`. In `_get_or_create_manifest` that has three effects:

1. The search for an unfinished week is skipped, so a half-done older week is not resumed by this run.
2. If a manifest with that ID exists, it is loaded as it is.
3. Otherwise a new manifest is created under the command's ID, but its `start_date` still comes from local history (`_resolve_start_date`). Nothing compares the two, so the ID and the dates can disagree. In an experiment on this commit, a `2026-W52` command produced a manifest named `2026-W52` that starts on 2026-12-09, a day in ISO week 50.

### 3.4 Optional cloud Instagram route

With `--instagram-delivery cloud` (`--ig-cloud` on the BuildVerse launcher), the Instagram phase does not open instagram.com. For each Reel it uploads the MP4 as a multipart form, with its SHA-256 as a field, to `POST /worker/media/upload` ([`media_handoff.py`](../automation/media_handoff.py) `handoff_reel_to_cloud`); the server verifies the hash, stores the file under `media/<week_id>/<reel_id>/<sha256>.mp4` and records an Instagram job as `MEDIA_READY` ([`cloud/local_worker_api.py`](../automation/cloud/local_worker_api.py) `handle_media_upload`). The local side records `MEDIA_READY` and moves on. The cloud Instagram worker later publishes the job through the Meta Graph API:

```mermaid
stateDiagram-v2
    [*] --> MEDIA_READY: POST /worker/media/upload
    MEDIA_READY --> PREPARING: claimed, slot within 15 min
    PREPARING --> FAILED_FATAL: no object key, SHA-256 mismatch
    PREPARING --> FAILED_RETRYABLE: media download or daily quota
    PREPARING --> UPLOADING_TO_META: quota ok
    UPLOADING_TO_META --> FAILED_RETRYABLE: container or upload error
    UPLOADING_TO_META --> PUBLISHED: dry run or uploads disabled
    UPLOADING_TO_META --> PROCESSING: video bytes uploaded
    PROCESSING --> FAILED_RETRYABLE: not FINISHED within 300 s
    PROCESSING --> READY_TO_PUBLISH: container FINISHED
    READY_TO_PUBLISH --> PUBLISHING: publishing allowed
    READY_TO_PUBLISH --> PREPARING: re-claimed once publishing is allowed
    PUBLISHING --> FAILED_RETRYABLE: publish call failed
    PUBLISHING --> REMOTE_VERIFIED: media object read back
    PUBLISHING --> PUBLISHED: read-back inconclusive
```

The worker ([`cloud/instagram_worker.py`](../automation/cloud/instagram_worker.py) `InstagramCloudWorker.execute_job`) re-downloads the object, re-checks its SHA-256, checks the 24-hour publishing quota, creates a Reels container with `is_ai_generated`, uploads the bytes with the resumable upload, polls the container for up to 300 seconds, publishes and reads the media object back. Any unexpected exception ends in `FAILED_FATAL`. Because the Graph API has no scheduled-publish parameter, the post goes live when the job runs, not through a platform scheduler; see [9](#9-limitations-known-gaps-and-next-steps) for what that means for timing.

**Read this before setting `ENABLE_INSTAGRAM_WORKER=true`.** With an `INSTAGRAM_ACCOUNT_ID` set and the default `INSTAGRAM_DRY_RUN=true`, or with `INSTAGRAM_DRY_RUN=false` but `INSTAGRAM_ALLOW_UPLOAD=false`, a claimed job that passes the download, hash and quota steps ends as `PUBLISHED` with `remote_media_id = "MOCK_DRY_RUN_ID"` and no video bytes reach Meta. (With `INSTAGRAM_DRY_RUN=false` the container is still created by a real Graph API call, and the 24-hour quota read is a real call whenever an account ID is set.) That `PUBLISHED` is final:

- the claim query only picks `MEDIA_READY`, `READY_TO_PUBLISH` and lease-expired `PREPARING` jobs;
- a new upload for the same job ID gets 409 `JOB_ALREADY_ADVANCED`;
- the local side recorded `MEDIA_READY` at hand-off, which both Instagram routes treat as delivered.

So every job processed while the flags simulate is lost for real publishing. No endpoint resets a job; the row has to be changed in the database by hand. Without an account ID, the container step fails instead and the job ends as `FAILED_RETRYABLE`, which is not retried either.

### 3.5 What a rehearsal (dry run) exercises

`dry_run=True` is the default of both `SimpleWeeklyPipeline` and the command line (no `--live`). It swaps in `MockVideoProvider` for Flow, `MockYouTubeStudioPublisher` (or `MockYouTubePublisher` in API mode), `MockTikTokPublisher` and `MockInstagramWebPublisher`, and builds no cloud client. Everything else is real: planning reads the brand's history and writes a manifest, `progress.json` and `ReelState` files under `workspace/`; QC runs on the mock media; LOCK runs with only the placeholder check; the gates, the Obsidian mirror and Telegram all run.

GENERATE records the `ReelState` of `MockVideoProvider` output with `source = mock_test_provider`, and the gates exist to refuse exactly that. A fresh rehearsal on this commit (default brand, start date 2026-10-05, hold disabled) ended with GENERATE 14/14 and LOCK done, and then every platform stopped on its first Reel: YouTube and TikTok with `FAILED_FATAL` `PRE_PUBLISH_GATE_FAILED: Provenance is 'mock_test_provider' ...`, Instagram web with `FAILED_FATAL` and the same eligibility reason. So a rehearsal of a new week never reaches the mock publishers. Its other effects:

- `main()` keeps the 30-minute hold, so each enabled platform is held for 30 minutes and retried every 5 minutes before the run exits with code 1.
- `_send_telegram` does not look at `dry_run`. With a bot token and chat ID in the environment or `.env`, the hold alerts and the summary are real Telegram messages.
- The rehearsal week stays unfinished, so the next live run without `--week-id` resumes it (in the experiment, the live probe picked the rehearsal's `2026-W41`). Its videos are mock media, so every platform then stops at the same gate. The rehearsal also used up 14 Reel IDs, and its planned concepts count as aired for rotation (`_concept_last_aired` reads every manifest).
- The mock publishers run only when the media has live provenance, which means a week that was generated live is being rehearsed. They then return `SCHEDULED` with `mock_` remote IDs (the Instagram mock returns no ID), stamped `dry_run: true`. [5.7](#57-platform-phases) explains what a later live run does with those records, and [8](#8-operator-runbook-blocked-and-terminal-states) how to clean up.

## 4. Data model

All local state is JSON or Markdown under the working directory, written atomically (temporary file, then `replace`). Nothing in `workspace/`, `13_PUBLISHING/` or `secrets/` is committed (`.gitignore`).

**Week manifest** — `workspace/batches/<week_id>/manifest.json`, [`BatchManifest`](../automation/orchestration/batch_manifest.py) and `BatchReel`. The content plan; immutable once `status` is `LOCKED`.

| Field | Meaning |
|---|---|
| `week_id` | ISO week of the start date with the brand prefix, e.g. `2026-W40` or `CBM-2026-W40` |
| `start_date`, `timezone`, `target_reels` | First day, `Europe/Istanbul`, 14 |
| `status` | `DRAFT` or `LOCKED`; publishing phases refuse anything but `LOCKED` |
| `content_mode` | Mode the week was planned in; a resumed week keeps it even if another `--content-mode` is passed |
| `reels[].reel_id`, `index`, `scheduled_at_local`, `scheduled_at_utc` | One Reel per slot |
| `reels[].title`, `caption`, `hashtags` | Publishing metadata decided at plan time |
| `reels[].concept_id_slug`, `environment`, `architecture`, `transformation`, `camera_style`, `lighting`, `materials`, `reveal`, `diversity_score` | The raw selector fields, stored so the exact same prompt can be rebuilt in a later process (`_rebuild_concept_plan`) |
| `reels[].generation_status`, `generation_error`, `video_path`, `video_sha256` | GENERATE outcome per Reel |

**Week progress** — `workspace/batches/<week_id>/progress.json`, mutable and separate from the manifest so a platform failure can never touch the content plan. Per Reel and platform: `status`, `remote_id` (YouTube/TikTok; the Instagram web route records none) or `remote_media_id` (the cloud route's object key), `url`, `error`, and a `dry_run` stamp written by `_record_platform_status`. Which readers honour that stamp is listed in [5.7](#57-platform-phases). `update_platform_status` changes only the fields it is given, so a later write keeps an earlier `remote_id`. The manifest itself has no rehearsal flag.

**Reel state** — `workspace/state/reels/<reel_id>.json`, [`ReelState`](../automation/orchestration/models.py). The provenance record the gates trust: `source` (only `flow_live_generation` is live-eligible; `mock_test_provider`, `diagnostic_test`, `legacy_unverified`, `quarantined` are not), `pipeline_version`, `content_mode`, `generation_status`, `qc_status`, `video_path`, `video_sha256`, `quarantine_reason`, plus metadata and schedule. The weekly pipeline writes it once, when a Reel passes QC.

**Publish record** — `13_PUBLISHING/PUB-<reel_id>-<PLATFORM>.md` in the working directory, [`PublishRecord`](../automation/publishing/models.py) via [`PublishingRepository`](../automation/publishing/repository.py). Written only by the YouTube Studio publisher, as resume evidence: `status`, `remote_id`, `remote_url`, `upload_started`, `remote_draft_exists`, `last_error`, the verified schedule date and time. `merge_with_existing` lets existing remote evidence win over a fresh record.

**Brand** — [`Brand`](../automation/brands.py): `brand_id`, `content_mode`, `alternate_content_mode`, `id_prefix`, expected YouTube handle and channel id, expected TikTok username, CDP ports, profile suffix, `instagram_delivery`, `platforms`.

**Cloud database** — six tables created by [`Database.init_db`](../automation/cloud/database.py) (PostgreSQL in production, SQLite in development; `?` placeholders are translated to `%s` for PostgreSQL):

| Table | Key fields |
|---|---|
| `cloud_weeks` | `week_id`, `start_date`, `end_date`, `status`, `approval_status`, `approval_sent_at`, `approved_at`, `rejected_at` |
| `telegram_approvals` | `approval_id`, `week_id`, `next_week_id`, `status` (PENDING, APPROVED, REJECTED, EXPIRED), `telegram_message_id`, `expires_at` |
| `local_worker_commands` | `command_id`, `type` (e.g. `GENERATE_WEEK`), `week_id`, `status`, `claimed_by`, `claimed_at`, `completed_at`, `last_error` |
| `instagram_scheduled_jobs` | `job_id`, `week_id`, `reel_id`, `scheduled_at_local`, `media_object_key`, `media_sha256`, `caption`, `status`, `lease_expires_at`, `container_id`, `remote_media_id`, `permalink` |
| `worker_heartbeats` | `worker_id`, `hostname_hash`, `version`, `capabilities_json`, `last_seen_at` |
| `notification_logs` | `notification_id`, `notification_type`, `recipient`, `payload_hash`, `sent_at` |

**Media objects** — files in the cloud's storage backend ([5.9](#59-the-cloud-control-plane)), keyed `media/<week_id>/<reel_id>/<sha256>.mp4`; the storage self-test writes and deletes `diagnostics/storage-smoke/<random>.bin`.

## 5. Core logic in depth

### 5.1 Calendar, week IDs and Reel IDs

- **Slots.** `DAILY_SLOT_TIMES = ("19:30", "22:00")`; [`generate_14_slot_week_plan`](../automation/orchestration/slot_generator.py) produces 7 days × 2 slots in Europe/Istanbul and stores each slot in local and UTC form, so month and year boundaries need no special case.
- **Start date** ([`SimpleWeeklyPipeline._resolve_start_date`](../automation/simple_weekly_pipeline.py)). The new week starts the day after the latest slot that reached a platform, but never earlier than the earliest usable day. "Reached" is read from `progress.json` across all of the brand's weeks (`find_last_scheduled_date`): a YouTube or TikTok success status, or any Instagram terminal status (`MEDIA_READY` and `SUBMITTED_UNVERIFIED` included). A rehearsal's records count too. Today is usable only if its first slot is at least `SAME_DAY_START_LEAD_HOURS = 6` hours away; otherwise the week starts tomorrow. A brand that has never published starts at the earliest usable day. `--start-date` overrides all of this.
- **Resume first.** With no `--week-id`, `_find_unfinished_week_id` picks the most recent week of this brand that is not finished (not locked, not fully generated, or some enabled platform below 14/14). This is what makes "run the same `.bat` again" safe: it never opens a new week (and spends new Flow credits) while an old one is in flight.
- **Week ID.** `brand.week_id(ISO week of start date)`, e.g. `CBM-2026-W40`, unless `--week-id` or a cloud command supplies one ([3.3](#33-optional-cloud-start-telegram-approval-to-worker-command)). An existing manifest with that ID is loaded whatever its start date: the `WEEK_ID_COLLISION` check in `_get_or_create_manifest` tests `self.week_id is None` right after assigning it, so it never fires. Brands are isolated by prefix: `Brand.owns_week_id` makes the default (unprefixed) brand reject every week that carries another brand's prefix.
- **Reel IDs** ([`_allocate_reel_ids`](../automation/simple_weekly_pipeline.py)). Monotonic and never reused: every ID found in any manifest, any `ReelState` file or any `*REEL-*.mp4` in `workspace/downloads` is taken, as are `HARD_EXCLUDED_REEL_IDS` (`REEL-2026-0010`, the diagnostic Reel, and `REEL-2026-0001`, a test video that once reached YouTube). The default brand starts its search at 11, a prefixed brand at 1.

### 5.2 Choosing 14 concepts

Concepts live in four hand-curated libraries, one per content mode. Pool sizes at this commit: 40 construction concepts in 10 groups ([`concepts.py`](../automation/content/concepts.py)), 33 real-history places in 7 groups ([`story_concepts.py`](../automation/content/story_concepts.py)), 28 buried-object builds in 3 groups ([`hidden_build_concepts.py`](../automation/content/hidden_build_concepts.py)) and 16 cross-section subjects in 3 groups ([`cutaway_concepts.py`](../automation/content/cutaway_concepts.py)).

**Diversity score** ([`diversity.py`](../automation/content/diversity.py) `calculate_diversity_score`). For each candidate (a concept with one of its first two environments and first two architectures):

```
novelty   = 1 − max similarity to any past record
            similarity = Jaccard overlap of normalised word sets
            (lower-case, words ≤ 2 letters and a small stop-word list removed);
            a past topic_key equal to the concept slug, or contained in / containing
            the candidate key, counts as 0.95
penalty   = max over the 5 most recent categories that match this concept
            of 0.5 / (position + 1)
score     = 0.50 × novelty + 0.30 × 0.92 − 0.35 × penalty
```

Candidates with `novelty < 0.40` are dropped, the rest sorted by score, and one plan per concept slug is kept ([`TemplateContentProvider.generate_plans`](../automation/content/engine.py)). The story, hidden-build and cutaway providers then round-robin across category groups (`StoryContentProvider._interleave_by_group`), because selection order is publishing order and the libraries are grouped by theme. With an empty history the score is `0.5 + 0.276 = 0.776`, which is the 0.78 printed in the README's sample dry run.

**Rotation rule** ([`SimpleWeeklyPipeline._fresh_plans`](../automation/simple_weekly_pipeline.py)). The engine's score turned out to be a weak signal for the weekly pipeline (its comments record a week that repeated eleven of the fourteen concepts from two weeks earlier), so the order is driven by the channel's own history instead:

1. `last_aired` maps each concept slug to its latest planned slot date in any manifest the brand owns (`_concept_last_aired`). It reads the plan, not the outcome, so a slot that never reached a platform, or a rehearsal week, counts as aired.
2. Candidates (`max(count × 4, 40)` ranked plans) are sorted by days rested, longest first; a never-aired concept counts as 10,000 days. The engine's ranking is only the tie-break. The sorted candidates are then interleaved across category groups, so putting never-aired concepts first cannot open a week with several concepts of one group in a row.
3. The required rest adapts to the pool: `quarantine = min(21, (pool // per_week − 1) × 7)` days (`_quarantine_days`, ceiling `CONCEPT_QUARANTINE_DAYS = 21`). For BuildVerse's 7 story + 7 cutaway slots that is 21 days for stories (33 // 7 = 4 weeks) and 7 days for cutaways (16 // 7 = 2); for Crafts By Man's 14 hidden-build slots it is 7 days (28 // 14 = 2).
4. If not enough concepts have rested that long, the longest-rested of the rest fill the week and a warning names the shortest gap.
5. Finally `_refuse_a_repeat_within_days` raises `CONCEPT_POOL_EXHAUSTED` before anything is saved if any chosen concept aired less than `CONCEPT_MIN_GAP_DAYS = 7` days before the week starts.

**Two formats in one week** (`_plan_concepts`). A brand with an `alternate_content_mode` gets 7 plans from each library, interleaved so the 19:30 slot carries the primary mode and the 22:00 slot the alternate. BuildVerse uses `narrative_ambient_story` at 19:30 and `cutaway_reveal_story` at 22:00; Crafts By Man is single-format (`hidden_build_story`).

### 5.3 From concept to prompts

Every mode produces the same `ReelConceptPlan` shape ([`prompt_engine.py`](../automation/content/prompt_engine.py)): three `SegmentPlan`s of 10 seconds each, so the generator, concatenator and manifest need no per-mode branches.

- **Continuity contract.** Flow renders each segment separately and would otherwise drift, so each planner builds one `ContinuityContext` per Reel (environment, terrain, architecture style, structure identity, materials, scale, camera direction and height, lighting, time of day, palette; [`segment_planner.py`](../automation/content/segment_planner.py)) and repeats its fields in all three prompts. Each format writes the shared fields in its own words:
  - Construction (`silent_global_step_by_step`, [`SegmentPlanner.plan_segments`](../automation/content/segment_planner.py)): the whole context as one sentence from `ContinuityContext.to_prompt_clause`, labelled "Visual identity: …" in segment 1 and "Preserve exactly: …" in segments 2 and 3.
  - History stories and cutaways ([`StoryPlanner._build_beat_prompt`](../automation/content/story_planner.py)): labelled lines, `PLACE (identical in every beat): …`, `SETTING:`, `ARCHITECTURE:`, `MATERIALS:`, `CAMERA:`, `LIGHT:` and `COLOUR:`. The environment appears inside `SETTING`; the `scale` field is not used.
  - Hidden builds ([`HiddenBuildPlanner._build_beat_prompt`](../automation/content/hidden_build_planner.py)): "The location is the same in every beat: …", "The object is the same in every beat: …", plus materials, light and colour. Beats 1 and 2 get the same static camera sentence; beat 3 gets a different camera instruction (down the stairs and along the interior), because the payoff is underground.
- **Three beats.** Construction Reels use `FOUNDATION → MAIN_CONSTRUCTION → DETAILS_AND_REVEAL`, with explicit "do not restart from empty land / do not jump to the finished result" lines and a final segment that spends roughly 6–7 seconds on details and the last 3 on the reveal. History stories use `BEFORE → THE_TURN → WHAT_REMAINS`. Cutaways are labelled `PLAIN_SURFACE → THE_CUT → THE_WORKING_INTERIOR`, because Flow reads beat names and "what remains" would push it towards decay ([`story_planner.py`](../automation/content/story_planner.py) `CUTAWAY_BEATS`). Only the labels change, though: `build_cutaway_plan` reuses `StoryPlanner.get_story_beats`, so a cutaway's beat 2 still ends "no longer in use" and its beat 3 still asks for "time passing over the abandoned site: weather, growth and decay settling in" (checked by rendering a cutaway plan; listed in [9](#9-limitations-known-gaps-and-next-steps)). Hidden-build Reels keep the story beat names as stage names (their prompts say only "Beat N of 3"), have their own beat texts (`HiddenBuildPlanner.get_beats`) and repeat one fixed description of the recurring craftsman in every beat so his face stays consistent ([`hidden_build_planner.py`](../automation/content/hidden_build_planner.py) `HiddenBuildPlanner.CRAFTSMAN`).
- **Negative exclusions.** Each planner appends its own exclusion list. All of them ban captions, written text, logos and watermarks; the story-type lists also ban narration, dialogue and intelligible speech and ask for diegetic ambience only (`StoryPlanner.AUDIO_DIRECTION`), so audio modes still have no voiceover.
- **Duration sanitiser.** `sanitize_video_duration` ([`duration_rules.py`](../automation/content/duration_rules.py)) rewrites "N-second" phrases and "Duration: N seconds" to the segment length and appends a 9:16 and duration line if neither is present. The length must be in the allowed set `{4, 6, 8, 10}` from `MODEL_DURATION_RULES`, otherwise 10 is used; the set is looked up under the function's default model name, not the `video_model` from the configuration. It runs when construction prompts are built and again on every prompt typed into Flow (`FlowPage.enter_prompt`), so story and hidden-build prompts pass through it too.
- Each segment prompt carries `prompt_hash` (first 16 hex characters of its SHA-256), used to tie a Flow session to the prompt that produced it.

### 5.4 The Flow generation state machine

Generation costs Flow credits, so the browser layer is built around not paying twice and not downloading the wrong file.

- **One Flow project per Reel** (`FlowPage.ensure_project_for_reel`), configured once per Reel by `FlowPage.configure_agent_settings`: open the agent settings, click the "Never" option for approval before generation when `approval_before_generation` is `never` (if the option is missing, it warns, saves a snapshot and continues with whatever Flow has saved), click every visible `9:16` button, click the first `x2` and the second `x1` button (image x2, video x1 per the code comment), and save (a missing Save button raises `FLOW_SETTINGS_SAVE_FAILED`). The configured `video_model`, `video_ratio`, output counts and duration are printed but not used to choose anything in the UI; nothing in the code selects a model.
- **Resume from disk.** A segment file over 10,000 bytes already in `workspace/segments/<reel_id>/` is reused, unless its SHA-256 equals an earlier segment's, in which case it is deleted and regenerated ([`GoogleFlowWebProvider.generate_single_video`](../automation/flow/generator.py)).
- **Baseline fingerprints.** Before clicking Generate, `FlowPage.trigger_generation` records the fingerprints of every artifact already on screen. A second click in the same session raises `GenerationStateUncertain` (double-click guard).
- **Decision table** ([`flow/state_machine.py`](../automation/flow/state_machine.py) `FlowDecisionEngine.decide_next_action`), evaluated every 3 seconds until `generation_timeout_minutes` (20 by default), in priority order:

| Condition on the snapshot | Action |
|---|---|
| Prompt not yet submitted in this session | `START_MEDIA_GENERATION` (never download a stale artifact) |
| Download button visible and a new artifact (or already generating) | `DOWNLOAD_MEDIA` |
| New artifact and no stop button | `RECOVER_DOWNLOAD_UI` (open the video detail view) |
| Agent says media is ready, no stop button | `RECOVER_DOWNLOAD_UI` |
| Agent failed and Flow offers a retry | `RETRY_AGENT_GENERATION`, at most `MAX_AGENT_RETRIES_PER_SEGMENT = 2`, then `USER_ACTION_REQUIRED` |
| Flow asks to approve this generation's credits | `APPROVE_GENERATION_ONCE`, at most `MAX_GENERATION_APPROVALS_PER_SEGMENT = 1`; only the single-shot "Onayla" is clicked, never "Her zaman onayla" |
| Stop button visible or a progress message | `WAIT` |
| Agent asks about duration | Answer once with the segment length, then only wait |
| Agent error | `USER_ACTION_REQUIRED` |

- **Download guard.** Even with an enabled download button, the file is fetched only if the artifact's fingerprint is new for this session ([`FlowPage.wait_for_completion_and_download`](../automation/flow/page.py)). Flow's download control opens a quality menu; [`_choose_original_quality`](../automation/flow/downloader.py) clicks only the original-size entry and refuses any label matching the paid pattern (`yükseltilmiş`, `upscal`, or `N kredi/credit`), because the upscaled entries spend extra credits. An unrecognised menu is dumped to `screenshots/errors/` and the Reel fails with `DOWNLOAD_QUALITY_MENU_UNRECOGNISED` instead of guessing.
- **Duplicate guard.** After download, a segment whose SHA-256 matches an earlier segment raises `SEGMENT_DUPLICATE`; an end frame is extracted for reference; the three segments are concatenated.

### 5.5 Quality gates

QC runs once per Reel on the concatenated file ([`VideoValidator.process_and_validate`](../automation/quality/validator.py)). Each check rejects with a reason that is stored as `generation_error`:

| Check | Rule | Rejects |
|---|---|---|
| File | exists and is not empty | missing or 0-byte downloads |
| Stream ([`ffprobe.py`](../automation/quality/ffprobe.py) `inspect_video`) | a video stream and duration > 0.5 s | audio-only or broken files |
| Aspect ratio | width / height between 0.50 and 0.60 (9:16 = 0.5625) | landscape or square renders |
| Frames ([`frames.py`](../automation/quality/frames.py) `extract_and_analyze_frames`) | 5 grayscale frames at 0 %, 25 %, 50 %, 75 % and the end; mean brightness < 5 is black, standard deviation < 4 is empty, mean absolute difference between first and last frame < 3 is frozen | black, blank or static videos |
| Audio policy | modes with `AUDIO_REQUIRED` must have an audio stream (`AUDIO_MISSING`) | a story Reel that came back silent |
| Post-processing | `ffmpeg -c:v copy`, AAC 192 kbit/s 48 kHz kept for audio modes or `-an` for silent mode, `-movflags +faststart` | (not a check: the output file) |

Concatenation ([`concatenator.py`](../automation/quality/concatenator.py) `VideoConcatenator.concatenate_segments`) re-encodes with the concat demuxer to H.264, `yuv420p`, 30 fps, keeping audio only when the mode requires it, and falls back to a `filter_complex` concat if the output is missing or under 10,000 bytes. If both FFmpeg calls fail, it writes the segments' raw bytes joined together (a fallback meant for tests without FFmpeg), so a failed concatenation shows up as a QC failure, not as an exception. The frame checks use FFmpeg for extraction and Pillow plus NumPy for the statistics.

The audio decision itself lives in one place, [`content_modes.py`](../automation/content/content_modes.py): `silent_global_step_by_step` is `AUDIO_FORBIDDEN`; `narrative_ambient_story`, `hidden_build_story` and `cutaway_reveal_story` are `AUDIO_REQUIRED`. An unknown mode is not live-eligible and its policy is `AUDIO_FORBIDDEN` (fail closed).

**Circuit breaker.** If two Reels in a row fail with the same signature (the first two colon-separated parts of the error, e.g. `QC_FAILED: AUDIO_MISSING`), GENERATE stops (`MAX_CONSECUTIVE_SAME_FAILURES = 2`) instead of spending credits on the remaining Reels; the batch stays resumable.

### 5.6 Validate, lock and the pre-publish gate

`_run_validate_and_lock_phase` locks the manifest only if there are exactly 14 unique Reel IDs, no two Reels share a slot, and, for each Reel, the video path and hash are recorded, the file exists, [`is_live_production_eligible`](../automation/publishing/eligibility.py) passes, the Reel ID invariant holds and the metadata is not a placeholder. In a dry run only the placeholder check applies, because mock media is ineligible by design. LOCK is the only place where the Instagram routes' Reels are checked for placeholder metadata.

`is_live_production_eligible` (fail closed: no `ReelState` means ineligible) requires: the ID is not hard-excluded, no quarantine reason, `source == "flow_live_generation"`, `pipeline_version == 3`, a registered live-eligible mode, `generation_status == "COMPLETE"`, `qc_status == "PASS"`, a non-empty file whose SHA-256 matches the state, a resolution that is not the mock provider's 540×960, and an audio stream that matches the mode.

What runs right before a Reel is handed to a publisher depends on the platform:

| Check | YouTube, TikTok ([`run_pre_publish_hard_gate`](../automation/publishing/preflight_gate.py), called in `_run_platform_phase`) | Instagram web and cloud (`_instagram_preflight`) |
|---|---|---|
| Video file exists | yes | yes |
| Platform not already successful for this Reel (`ALREADY_PUBLISHED_SKIP`) | yes | no (the per-Reel skip is the only guard) |
| `is_live_production_eligible` (`PRE_PUBLISH_GATE_FAILED: …`) | yes | yes (reason recorded without the prefix) |
| Slot ID, state ID, record ID and the ID in the file name are identical (`verify_reel_id_invariant`, `REEL_ID_MEDIA_MISMATCH`) | yes | yes (the slot's ID stands in for the record's) |
| Title/caption is not the known placeholder (`PLACEHOLDER_METADATA_REJECTED`) | yes | no (checked at LOCK only) |
| The record's schedule equals the slot (`SCHEDULE_DATETIME_SLOT_MISMATCH`) | yes | no |
| The record's SHA-256 matches the file (`REEL_ID_MEDIA_MISMATCH`) | yes | no (`is_live_production_eligible` still compares the file with the `ReelState` hash) |

The gate's own docstring says every live path must pass through it; the Instagram routes use the narrower `_instagram_preflight` instead. Instagram also does not write `UPLOAD_ATTEMPTED` before acting and has no remote-ID collision guard ([5.7](#57-platform-phases)).

### 5.7 Platform phases

`_run_platform_phase` (YouTube and TikTok) and `_run_instagram_web_phase` / `_run_instagram_cloud_phase` share these rules:

- **Status classes.** Success: `SCHEDULED`, `PUBLISHED`, `REMOTE_VERIFIED`. Soft failure (the submit happened but the read-back was inconclusive; record it and continue with the next Reel): `SCHEDULE_RESUME_REQUIRED`, `UPLOADED_DRAFT`, `REVIEW_REQUIRED`. A later pass (the hold or a rerun) calls the publisher again for these Reels; the Studio publisher then verifies and resumes instead of uploading. Anything else stops the platform for this run. Instagram also treats `MEDIA_READY` and `SUBMITTED_UNVERIFIED` as terminal, so neither route can deliver a Reel the other already delivered.
- **Write before acting.** For a live YouTube or TikTok upload, `UPLOAD_ATTEMPTED` is written to `progress.json` before the publisher is called. A rebuilt `PublishRecord` carries `upload_started=True` for any status in `UPLOAD_ALREADY_ATTEMPTED_STATUSES`, which tells the Studio publisher to resume a draft instead of uploading again.
- **Remote ID collision guard** (YouTube and TikTok). A returned remote ID that any other Reel of the same brand (in any week) already holds is rejected as `REEL_ID_MEDIA_MISMATCH` and not recorded; the `FAILED_FATAL` written in its place replaces the earlier `UPLOAD_ATTEMPTED` status. TikTok's fixed marker `tiktok_scheduled_post` is exempt (`NON_IDENTIFYING_REMOTE_IDS`) because TikTok returns no per-post ID.
- **Divergence report.** `_report_state_divergence` logs `[STATE_DIVERGENCE]` at the start of a YouTube or TikTok phase when `progress.json` and the `13_PUBLISHING` record disagree on a remote ID, without choosing a winner. Only the YouTube Studio publisher writes such records, so in practice this is a YouTube check.
- **Hold for a manual fix.** If a platform ends below 14/14, `_hold_for_manual_fix` sends a Telegram alert (when a bot token and chat ID are configured) and retries the phase every 5 minutes for up to 30 minutes (`stuck_retry_seconds = 300`, `stuck_wait_minutes = 30`), then moves on to the next platform.
- **Rehearsal records are only partly fenced off.** Every record written in a dry run carries `dry_run: true`, and `_counts_as_done(entry)` returns `self.dry_run or not entry.get("dry_run")`. Some readers use it and others do not (table below). `_refuse_dry_run_over_live_week` refuses a dry run with `DRY_RUN_OVER_LIVE_WEEK` only when the week already holds a remote ID that does not start with `mock_`. A week whose live attempts failed before any ID was recorded, or whose live Instagram records came from the web route (which records no ID), is not protected.
- **Brand checks.** In a live run the YouTube, TikTok and Instagram-web phases call `Brand.ensure_publishable` first (`BRAND_NOT_CONFIGURED` for placeholder accounts), and a `--phase` for a platform the brand does not publish to raises `PLATFORM_DISABLED_FOR_BRAND`.

Which checks honour the `dry_run` stamp, as seen from a live run that finds a rehearsal's `SCHEDULED` record:

| Check (all in [`simple_weekly_pipeline.py`](../automation/simple_weekly_pipeline.py)) | Reads the stamp | Effect in a live run |
|---|---|---|
| Per-Reel skip in `_run_platform_phase` and `_run_instagram_web_phase` | yes (`_counts_as_done`) | The Reel is not skipped |
| `_build_publish_record` (upload evidence for the publisher) | yes | The status does not count as evidence of an upload; a leftover `mock_` remote ID is still passed on |
| `already_success` → the gate's `ALREADY_PUBLISHED_SKIP` (YouTube, TikTok) | no | The Reel is recorded `FAILED_FATAL` and the phase stops. That write clears the stamp but keeps the `mock_` ID, so the next pass treats the Reel as not done and that ID as evidence of an earlier upload (`upload_started=True`) |
| Per-Reel skip in `_run_instagram_cloud_phase` | no | The Reel is skipped as delivered |
| `all_platform_done` (cascade skip, end of the hold) | no | A platform whose 14 records are all successes, rehearsal ones included, is not run at all |
| `_is_batch_finished` → `_find_unfinished_week_id` | no | A locked week whose enabled platforms all pass that test counts as finished and is not resumed |
| `find_last_scheduled_date` → `_resolve_start_date` | no | The next week starts after the rehearsal's slots |
| `_platform_done_count` (hold alerts) and the counts in `build_summary_text` and `_print_status` | no | Rehearsal successes are counted as done |

The failure mode, reproduced on this commit with Crafts By Man and stand-in providers:

1. A live run generates and locks `CBM-2026-W41`; YouTube and TikTok stop with `AUTH_REQUIRED` and no remote ID.
2. A dry run is allowed (no live ID) and records `{"status": "SCHEDULED", "remote_id": "mock_yt_…", "dry_run": true}` for every Reel. The media has live provenance, so the gate passes and the mock publishers run.
3. The next live run without `--week-id` (how the `.bat` starts it) finds no unfinished week. `find_last_scheduled_date` returns 2026-10-11, so a new week would start on 2026-10-12, and `all_platform_done(W41, "youtube")` is true. W41 is never published.

So rehearsing a week that was generated live is the one kind of rehearsal that can lose a live week. The per-Reel checks protect a platform the rehearsal only partly covered; the platform-level and week-level checks still treat a fully rehearsed platform as done.

### 5.8 What each publisher does

- **YouTube Studio** ([`YouTubeStudioPublisher.upload_and_schedule`](../automation/publishing/youtube_studio_publisher.py), default `youtube_mode = "studio"`). Navigates to the expected channel's Studio URL and treats the channel ID surviving in the URL as proof of the account, otherwise reads the channel header (`ACCOUNT_MISMATCH` on a different channel). With remote evidence it first checks whether the video is already scheduled for this date and time and, if so, records success without touching it; it resumes an existing draft rather than uploading; a recorded ID whose editor no longer opens and which is not scheduled is cleared (`STALE_REMOTE_ID_CLEARED`) so the file is uploaded once more. A fresh upload captures the video ID, writes title, description and hashtags (an unverified title stops the Reel instead of publishing under the file name), walks the wizard (audience, AI disclosure), opens the schedule card, sets date and time and reads them back, submits, and verifies the scheduled state in the content list with back-offs of 10, 20 and 30 seconds. Without a video ID it verifies by title and date.
- **YouTube Data API** ([`YouTubePublisher`](../automation/publishing/youtube_publisher.py), `youtube_mode = "api"`). OAuth token per brand (`secrets/youtube/token<suffix>.json`), authenticated-channel check, `videos.insert` with `privacyStatus` (default `private`), `publishAt`, `selfDeclaredMadeForKids` and `containsSyntheticMedia`, resumable 5 MB chunks, then a `videos.list` read-back. Story and cutaway Reels also get localized titles and descriptions in `tr`, `hi`, `id` and `ja` ([`localizations.py`](../automation/publishing/localizations.py)); this happens only in API mode.
- **TikTok Studio** ([`TikTokPublisher.upload_and_schedule`](../automation/publishing/tiktok_publisher.py)). Account check by username, dismisses a leftover unsaved-draft banner, reuses an editor already open for this Reel instead of uploading again, replaces the default caption with caption plus hashtags, enables the AI-content label, selects "Planla" (schedule) and verifies it, sets the date and time and re-reads the live controls before submitting. The final click refuses to run unless schedule mode is verified and the time picker is closed ([`tiktok_ui_observer.py`](../automation/publishing/tiktok_ui_observer.py) `click_schedule_and_verify`). A secondary content-list check that comes back inconclusive is logged, and the Reel is still recorded as scheduled because the submit was confirmed.
- **Instagram web** ([`InstagramWebPublisher.schedule_reel`](../automation/publishing/instagram_web_publisher.py)). Refuses a slot less than 20 minutes away (`MIN_LEAD_MINUTES`), opens `instagram.com/scheduled_content/`, waits up to 45 seconds for the composer entry point, then runs open composer → upload → caption → AI label → schedule toggle → date → time → read date and time back → "Planla". Every step must succeed or the half-filled composer is abandoned. A confirmation that times out after the click becomes `SUBMITTED_UNVERIFIED`, which is never retried (a retry would post a second copy). A share-now wording on the final control aborts with `PUBLISH_NOW_BUTTON_REFUSED`.

All browser publishers follow the repository's browser rule ("Kural 31"): at most two semantic selector strategies per action, no forced or JavaScript clicks, and `NEEDS_USER_HTML` with a saved DOM snapshot instead of guessing when the UI changed. None of them deletes remote content; the only remote edits are finishing the Reel's own upload or draft.

### 5.9 The cloud control plane

**Request handling** ([`cloud/app.py`](../automation/cloud/app.py)). A standard-library `HTTPServer` (one request at a time, 60-second socket timeout) with these routes: `GET /` and `/health`, `POST /telegram/webhook`, `POST /worker/heartbeat`, `GET /worker/commands/next`, `POST /worker/commands/{id}/complete`, `GET /worker/state/sync`, `POST /worker/storage/self-test`, `POST /worker/media/upload`, `POST /worker/media/diagnostic-cleanup`. For every POST, `CloudApp.check_post_headers` runs before the body is read: `/worker/*` needs the worker key, the webhook needs its secret header (whenever a secret is configured, and always in production), any other path gets 404. Then: negative `Content-Length` → 400; multipart upload to `/worker/media/upload` → streamed to a temp file in 64 KB chunks with an incremental SHA-256 and a 100 MB cap (413); other bodies over 10 MB → 413; client JSON keys starting with `__` are stripped (they are reserved for server metadata such as the streamed file's path, which `_trusted_stream_path` additionally confines to the stream temp directory); a non-object JSON body → 400; unexpected exceptions → a generic 500 with the traceback only in the server log.

**Approval state machine** ([`cloud/approval_service.py`](../automation/cloud/approval_service.py)). An approval is created once per week (an existing pending one is reused) and expires after 48 hours. A callback is processed in this order: allowed user, allowed chat, parse `weekly_approve:<id>` / `weekly_reject:<id>`, approval exists, not expired, still `PENDING` (otherwise `ALREADY_PROCESSED`). Approval inserts a `GENERATE_WEEK` command; `Database.create_command` skips it if a command of the same type and week is already `PENDING`, `CLAIMED` or `RUNNING`, and `claim_command` only updates rows still `PENDING`, so two pollers cannot claim the same command.

**Health** ([`cloud/health.py`](../automation/cloud/health.py)). `/health` reports sanitized flags only: database connectivity, storage configured, scheduler and Instagram-worker switches, the three Instagram safety flags, whether Telegram is configured, and whether a worker heartbeat arrived in the last 180 seconds.

**Instagram safety flags.** `INSTAGRAM_DRY_RUN` (default true), `INSTAGRAM_ALLOW_UPLOAD` and `INSTAGRAM_ALLOW_PUBLISH` (default false). The Graph API client only transfers bytes when `dry_run` is false and upload is allowed, and only publishes when `dry_run` is false and publish is allowed ([`instagram_api.py`](../automation/publishing/instagram_api.py)). A job claimed while publishing is disabled stops at `READY_TO_PUBLISH`, and `claim_due_instagram_job` does not claim it again until publishing is enabled. What the simulated states do to a job is described in [3.4](#34-optional-cloud-instagram-route).

**Media storage** ([`cloud/media_storage.py`](../automation/cloud/media_storage.py)). One interface, `MediaStorageInterface`, with `put_file`, `get_file`, `delete_file`, `exists`, `get_metadata`, `is_ready` and `cleanup_expired_objects`. `get_media_storage` picks one of two adapters:

- `S3MediaStorageAdapter` when `MEDIA_STORAGE_BACKEND=s3` and `S3_BUCKET` is set. It uses boto3 with SigV4 against `S3_ENDPOINT_URL`, so any S3-compatible service works; `upload_file` with a content type for writes, and `head_object` for `exists` and the metadata (size, content type, ETag, last modified). `is_ready` needs the endpoint, the bucket and both keys.
- `LocalMediaStorageAdapter` otherwise, with files under `workspace/cloud_media_storage/`; its metadata includes a SHA-256 computed from the file.

`MEDIA_STORAGE_BACKEND=s3` with an empty `S3_BUCKET` falls back to local storage without an error. Production does not enforce S3 at start-up: `CloudConfig.validate_production_storage` exists, but nothing in the app calls it, and the "production requires `s3`" rule lives only in `railway_production_preflight` (check 9/17). `/health` reports the backend name and `storage_configured` (for `s3`: all four S3 values set), and reads `DEGRADED` when the database is reachable but storage is not configured. `cleanup_expired_objects` can list and delete objects older than a retention period, but nothing calls it.

Two worker endpoints exist for operating the storage:

- `POST /worker/storage/self-test` needs the worker key and the header `X-Storage-Smoke-Test: true` (otherwise 400 `CONFIRMATION_REQUIRED`). It writes 2,048 random bytes to `diagnostics/storage-smoke/<id>.bin`, checks `exists`, reads the metadata, downloads the object, compares SHA-256, deletes it and checks that it is gone. It answers 200 `S3_ROUND_TRIP_PASS` only if every step passed (500 otherwise) and always removes its temporary files.
- `POST /worker/media/diagnostic-cleanup` deletes one diagnostic hand-off job and its object, and nothing else. The job ID must start with `DIAG-HANDOFF-`, and the job must be `MEDIA_READY` with no container, remote media ID or publish time, belong to week `2099-W52` and Reel `REEL-2099-9999`, and have its object under `media/2099-W52/REEL-2099-9999/`; anything else gets 403. The object is deleted and confirmed gone before the database row is deleted and confirmed gone.

### 5.10 Security model

| Concern | Mechanism | Fails closed because |
|---|---|---|
| Worker endpoints | `X-Worker-Api-Key` compared with `hmac.compare_digest` ([`security.py`](../automation/cloud/security.py) `verify_worker_api_key`) | An empty key or a value copied from a template (`change-me`, `reels_ai_local_worker_key_dev`) disables the endpoints entirely (`CloudConfig.is_worker_api_enabled`) |
| Telegram webhook | `X-Telegram-Bot-Api-Secret-Token`, constant-time compare ([`telegram_webhook.py`](../automation/cloud/telegram_webhook.py) `check_webhook_headers`) | In production a missing secret rejects every call (403); `ENABLE_TELEGRAM_WEBHOOK=false` returns 503 |
| Who may approve | `verify_telegram_user` and `verify_telegram_chat` | No built-in IDs: with `TELEGRAM_ALLOWED_USER_ID` or `TELEGRAM_CHAT_ID` unset, every button press is refused and logged |
| Resource abuse | Header checks before any body read; 10 MB JSON cap; 100 MB streamed upload cap; 60-second socket timeout | A client without the worker key cannot make the server read a body or store a file; webhook bodies are read only after the secret check |
| Upload integrity | Client SHA-256 must equal the server's streamed hash; strict regexes for week, Reel and job IDs; `.mp4` only; an upload for a job that is already being processed or published, or a different file for an existing job, returns 409 | A mismatched or replayed upload never becomes a job |
| Production config | `APP_ENV=production` makes `Database` refuse a non-PostgreSQL URL; `railway_production_preflight` checks 17 items read-only, including template account values, a secret scan and `MEDIA_STORAGE_BACKEND=s3` (S3 is required only there, not at start-up) | A production container with SQLite fails at start-up instead of running on a throwaway database; the preflight lists every missing item before a deploy |
| Secrets in the repo | Environment variables or git-ignored files (`.env`, `secrets/`, `config.local.json`); `python -m automation.cloud.secret_scan` looks for Telegram, Meta, PostgreSQL-URL and S3 key patterns | — |
| Wrong channel | Per-brand account expectations, `ensure_publishable`, account checks in the YouTube and TikTok publishers (the Instagram web route has none, see [9](#9-limitations-known-gaps-and-next-steps)) | A placeholder or mismatched account stops before upload |
| Irreversible actions | Never clicks a share-now control, never deletes remote content, `SUBMITTED_UNVERIFIED` is never retried | A doubt ends in a stop and a human check, not a second post |

### 5.11 Configuration that shapes a run

The weekly pipeline reads `config.local.json` through [`load_config`](../automation/config.py) (or `config.example.json` when there is no local file) and `publishing.local.json` for the publishers. The keys that matter for Flow:

| Key in `config.local.json` | Default | What the code does with it |
|---|---|---|
| `flow_url` | `https://labs.google/fx/tools/flow` | Opened in a new tab when no open tab looks like Flow, and passed to Chrome when the code starts it |
| `chrome_debug_port` | 9222 | The CDP port Playwright connects to (`http://127.0.0.1:<port>`) |
| `chrome_profile_path` | `%LOCALAPPDATA%\ReelsAIFactory\chrome-profile` | The profile used when the code has to start Chrome itself |
| `approval_before_generation` | `never` | `never` makes `configure_agent_settings` click Flow's "Never" option; any other value leaves Flow's saved setting alone. A credit question during generation is still answered at most once (`APPROVE_GENERATION_ONCE`) |
| `allow_real_generation` | `true` | `false` still types each prompt but never clicks Generate; each missing segment file gets the placeholder bytes `TEST_SEGMENT_PLACEHOLDER`, so the Reel then fails QC |
| `generation_timeout_minutes` | 20 | Polling limit per segment, then `GenerationTimeoutError` |
| `video_model`, `video_ratio`, `video_outputs`, `image_*`, `segment_duration_seconds` | see `config.example.json` | Only printed by `configure_agent_settings`; the clicks it makes are fixed ([5.4](#54-the-flow-generation-state-machine)) |
| `vault_path` | auto-detected | Required by `load_config` (see below) |

Two behaviours are easy to miss:

- If `load_config` raises, for example because `vault_path` is empty and no `Reels_AI_Studio` vault is found, the pipeline catches the error and uses built-in defaults without a warning, including a Chrome profile under `workspace/chrome-profile`.
- The weekly pipeline's Obsidian mirror writes to `--vault-path` or `~/obsidian/Reels_AI_Studio`, not to `vault_path` from the configuration, and the `.bat` launchers pass no `--vault-path`.

## 6. Design decisions and trade-offs

- **Drive the web UIs and use native schedulers.** Generation goes through Google Flow's web app, and scheduling goes through each platform's own scheduler in its web UI. The Instagram composer route was added because, as its module docstring notes, the Graph API path can only publish at the moment itself and shows nothing in the account's scheduled queue. Native schedulers mean the PC does not need to be on at publish time. The cost is fragility: UI changes break selectors. The code answers that with patient waits (many timeouts in the code comments were raised after a page that was merely slow was reported as broken), read-back of the values it sets (dates, times, titles, schedule mode), error snapshots under `screenshots/errors/`, and HTML fixtures of real controls in the tests. The YouTube Data API mode exists because a locale-dependent date picker put Reels on the wrong day; it trades UI fragility for API quota.
- **Attach to a real Chrome over CDP.** The owner signs in once by hand, and the automation reuses that session. Logins and CAPTCHAs are never automated; they stop the run with `USER_ACTION_REQUIRED`.
- **Immutable plan, mutable progress.** `manifest.json` freezes what will be published once it is locked; `progress.json` records what happened. A platform failure can only touch progress, and a rerun always rebuilds the same prompt from the stored selector fields.
- **Sequential, one platform at a time.** The pipeline processes one Reel at a time and one platform at a time, and holds a stuck platform for a manual fix. This is slower than parallel uploads but each failure is isolated and easy to reason about; the operator deals with one broken platform at a time.
- **Provenance over file names.** A file called `clean_REEL-….mp4` proves nothing. Only a persisted `ReelState` with `flow_live_generation` makes a video publishable, and absence of state means ineligible. This came from a real incident in which a mock test video reached YouTube.
- **Record the attempt, not just the result.** Writing `UPLOAD_ATTEMPTED` before an upload, keeping `upload_started` on rebuilt records and treating `SUBMITTED_UNVERIFIED` as terminal all prefer a missing post (visible, fixable by hand) over a duplicate post (which this system may not delete).
- **Fail closed on configuration.** Unknown content modes are not live-eligible and are treated as silent; unconfigured brands cannot publish; empty or template worker keys close the worker API; unset Telegram IDs refuse approvals; production refuses SQLite.
- **Adaptive rotation instead of a fixed blacklist.** A fixed 21-day rest would leave the 16-concept cutaway pool with nothing to publish; `_quarantine_days` scales the rest to the pool, and the hard 7-day floor turns an exhausted pool into an explicit error.
- **Standard-library HTTP server.** The cloud app has no web framework, which keeps the Docker image small (five pip packages) and the attack surface easy to read. It serves one request at a time, which is enough for one worker and one bot but not more.
- **Rehearsals share the live state files.** A rehearsal writes into the same `workspace/` files as a live run and marks its records with a `dry_run` stamp, so it exercises the real resume logic on real paths. The cost is that every reader of those files has to know about the stamp, and today only the per-Reel checks do ([5.7](#57-platform-phases)). Keeping rehearsal state in its own directory would remove the problem instead of fencing it.
- **Obsidian as a mirror, not the source of truth.** The weekly pipeline writes notes for humans but decides from JSON state; a failure while mirroring is logged and ignored. (The older `run.py` / `publish.py` path used the vault as its database, which is why both layouts exist.)

## 7. Testing strategy

Run while writing this revision, on a git archive of commit `99b4cf4` (the commits since then change documentation only), with Python 3.11.15, FFmpeg 6.1.1 and the packages from `requirements.txt`:

```
python -m pytest -q -rs tests/
1051 passed, 3 skipped in 354.19s (0:05:54)
```

That is 1,054 collected tests in 64 files. The three skips are checks of the production PC itself (an installed `chrome.exe`, a configured Obsidian vault, the git-ignored YouTube OAuth client secret). CI ([`.github/workflows/ci.yml`](../.github/workflows/ci.yml)) installs FFmpeg and runs the same command on Python 3.10 and 3.11 for every push and pull request.

| Area | Files | Tests | Examples |
|---|---|---|---|
| Publishing: YouTube, TikTok, Instagram, gates, idempotency | 24 | 557 | `test_youtube_localizations.py` (154), `test_youtube_studio.py`, `test_tiktok_studio.py`, `test_no_duplicate_uploads.py`, `test_stale_remote_id_recovery.py`, `test_click_patience.py` |
| Planning and content | 10 | 158 | `test_concept_rotation.py`, `test_brands_and_hidden_build.py`, `test_narrative_ambient_story.py`, `test_week_planning_and_dry_run.py`, `test_diversity.py` |
| Weekly pipeline, state, config, Obsidian | 11 | 127 | `test_simple_weekly_pipeline.py`, `test_live_pipeline_safety_regression.py`, `test_tiktok_week_completes.py`, `test_lock.py` |
| Cloud control plane | 5 | 116 | `test_cloud_http_hardening.py`, `test_railway_production_deployment.py`, `test_weekly_control_plane.py`, `test_media_handoff.py`, `test_identity_config_defaults.py` |
| Flow automation and QC | 14 | 96 | `test_flow_agent_failure_recovery.py`, `test_state_machine.py`, `test_legacy_and_artifacts.py`, `test_qc.py` |

How the suite stays offline and still meaningful:

- **Fakes at the boundaries.** Publishers have mock counterparts (`MockYouTubeStudioPublisher`, `MockTikTokPublisher`, `MockInstagramWebPublisher`), Playwright pages are replaced by small fake page and locator objects, the Graph API client and Telegram bot are stubbed, and `_send_telegram` refuses to send anything while `PYTEST_CURRENT_TEST` is set.
- **Real media where it matters.** `MockVideoProvider` renders actual 540×960 FFmpeg test-pattern segments (with a silent AAC track for audio modes), so concatenation, ffprobe and frame QC run for real; that resolution is also exactly what the eligibility gate rejects as mock media.
- **Captured DOM.** `tests/fixtures/youtube_live_controls.html` and `tiktok_live_controls.html` are sanitized snapshots of the real Studio controls, used by the selector tests.
- **Real HTTP for the cloud.** `test_cloud_http_hardening.py` starts the actual `CloudHTTPRequestHandler` on a loopback port with SQLite and local storage and sends malformed, unauthenticated and stalled requests, including forged file paths in JSON bodies.
- **Incidents become tests.** Many test docstrings name the production incident they pin down (duplicate uploads, stale remote IDs, a mock video on YouTube, a week of repeated concepts, verification that read a stale page).

Not covered by the suite: real Google Flow, real platform UIs, real Meta/Telegram/S3 calls and the Docker image build; those need the owner's accounts. `test_week_planning_and_dry_run.py` pins the rehearsal stamp's per-Reel effects and `DRY_RUN_OVER_LIVE_WEEK`, but no test covers the platform- and week-level checks that ignore the stamp ([5.7](#57-platform-phases)), and none runs the `.bat` launchers.

## 8. Operator runbook: blocked and terminal states

No tool in the repository repairs state, so recovery means checking the platform and then editing JSON by hand before running the same `.bat` again. The files are `workspace/batches/<week_id>/progress.json` (per Reel and platform: `status`, `remote_id`, `url`, `error`, `dry_run`), the week's `manifest.json`, `workspace/state/reels/<reel_id>.json` and, for YouTube Studio, `13_PUBLISHING/PUB-<reel_id>-YOUTUBE.md`. Every reader takes these files at their word, so copy them before editing. A clean per-platform entry is the skeleton from `default_progress_entry`: `{"status": "PENDING", "remote_id": null, "url": null, "error": null}` (Instagram: `remote_media_id` instead of `remote_id` and `url`).

**`SUBMITTED_UNVERIFIED`** (Instagram web, `instagram.status`; a warning in the log)
- Means: "Planla" was clicked but the confirmation was not read in time. It is terminal for both Instagram routes and never retried, because a retry could post a second copy. The phase still reports success, and the summaries only show the Reel as missing from the Instagram count, without naming it (the code comment says the summary flags it; it does not).
- Check: the account's scheduled content on instagram.com, for a post at that slot.
- Then: if it is there, nothing needs doing. If it is missing, schedule it by hand, or set the status to `FAILED_RETRYABLE` and rerun; the route refuses a slot less than 20 minutes away (`TIME_TOO_SOON`).

**`REEL_ID_MEDIA_MISMATCH`** (`FAILED_FATAL`; the `error` text tells the two causes apart)
- Plain `REEL_ID_MEDIA_MISMATCH` comes from the gate, before any upload: the slot, `ReelState`, record and file-name IDs differ, or the file's SHA-256 is not the recorded one. Compare the manifest's `video_path` and `video_sha256`, the `ReelState` file and the file on disk, and put back the QC output the manifest points to; the gate checks again on the next run.
- `REEL_ID_MEDIA_MISMATCH: <id> zaten <Reel> Reel'ine ait …` comes from the collision guard after the publisher returned. In practice this is YouTube, since the live TikTok publisher returns only the exempt marker. The upload may well have happened; the returned ID belongs to another Reel and was not recorded, and `FAILED_FATAL` replaced `UPLOAD_ATTEMPTED`. Look in YouTube Studio for this Reel's title and slot, and in `PUB-<reel_id>-YOUTUBE.md` for the stale ID. If this Reel's video exists, write its real ID into both files with the matching status (`SCHEDULED` if it is scheduled at the slot, `UPLOAD_ATTEMPTED` if it is a draft, which makes the next pass resume it). If it does not exist, delete `PUB-<reel_id>-YOUTUBE.md` (or clear its `remote_id`, `upload_started` and `remote_draft_exists`). Leaving the stale ID would point the next pass at the other Reel's video, and a leftover `upload_started` alone makes the publisher look for a draft by title instead of uploading.

**`[STATE_DIVERGENCE]`** (a log line at the start of a YouTube phase; no status changes)
- Means: `progress.json` and the publish record name different remote IDs for one Reel.
- Check: which ID, if either, is this Reel's video in YouTube Studio, and whether it is scheduled at the slot.
- Then: make both files carry the right ID, or neither if no video exists. The Studio publisher uses the `progress.json` ID when there is one and the record's otherwise (`merge_with_existing`), and clears an ID whose video is gone before uploading again (`STALE_REMOTE_ID_CLEARED`). An ID that points at a different, existing video is the case it cannot catch.

**`CONCEPT_POOL_EXHAUSTED`** (PLAN raises before anything is saved)
- Means: some of the week's chosen concepts were planned less than 7 days before the new week starts. The message names them and the content mode.
- Then: add concepts to that mode's library in [`content/`](../automation/content), or start later with `--start-date`. Planned dates in rehearsal or abandoned weeks count as aired; moving such a never-published week's folder out of `workspace/batches/` removes them from the history.

**`USER_ACTION_REQUIRED`** (Flow; GENERATE fails the Reel with `generation_error`, plus a snapshot in `screenshots/errors/`)
- Means: a sign-in page, a CAPTCHA pattern or Flow's logged-out page (`UserActionRequiredError`), or the decision table gave up: an agent error, an agent failure after the two allowed retries, a second credit question after the one approval, or a duration question past the automatic-reply limit. Two Reels failing the same way in a row stop GENERATE.
- Check: the Chrome window on the CDP port, and the Reel's Flow project for the agent's message.
- Then: sign in, pass the check or deal with the prompt, and rerun. `COMPLETE` Reels are skipped, the failed Reel is tried again, and its segment files already on disk are reused.

**A rehearsal week blocks the live run** (every platform `FAILED_FATAL` with `PRE_PUBLISH_GATE_FAILED: Provenance is 'mock_test_provider'`)
- Means: the live run resumed a week created by a rehearsal ([3.5](#35-what-a-rehearsal-dry-run-exercises)).
- Then: move that week's folder out of `workspace/batches/` and rerun. Its Reel IDs stay reserved through their `ReelState` files, and its concepts stop counting as aired.

**A rehearsal wrote over a live week** (entries with `"dry_run": true` and `mock_` IDs in a week generated live; [5.7](#57-platform-phases))
- Means: the live cascade treats those platforms, and possibly the week, as done.
- Check: each such Reel on the platform.
- Then: reset each entry to the clean skeleton, or write the real status and ID if the Reel did go out live, and run the week by ID: `python -m automation.simple_weekly_pipeline --live --week-id <week_id>` (add `--brand craftsbyman` for that channel). The weekly launchers pass no `--week-id`, and a newer unfinished week would be resumed first.

For publisher stops such as `AUTH_REQUIRED`, `ACCOUNT_MISMATCH` or `NEEDS_USER_HTML`, the platform stops and is held. Fix the browser session (or the selector, using the saved snapshot) and the hold's next retry, or a rerun, continues from that Reel.

## 9. Limitations, known gaps and next steps

- **Rehearsals.** The weekly launchers' `--dry-run` never reaches the pipeline (argparse exits with code 2). Run directly, a rehearsal of a new week stops at the gate on every platform, holds each one for 30 minutes and can send real Telegram messages; the week it leaves behind is resumed by the next live run. A rehearsal of a week generated live can make the platform- and week-level checks treat that week as done ([3.5](#35-what-a-rehearsal-dry-run-exercises), [5.7](#57-platform-phases)).
- **Instagram checks are narrower.** Both Instagram routes skip the full gate (no already-succeeded, placeholder, slot or record-hash check), write no `UPLOAD_ATTEMPTED` and have no remote-ID collision guard; the web route records no remote ID at all ([5.6](#56-validate-lock-and-the-pre-publish-gate)).
- **Prompt and Flow settings.** Cutaway Reels change only the beat labels and keep the history story's beat texts, so their prompts still ask for abandonment and decay ([5.3](#53-from-concept-to-prompts)). `configure_agent_settings` does not apply `video_model`, `video_ratio` or the output counts from the configuration ([5.4](#54-the-flow-generation-state-machine)).
- **Week IDs.** The `WEEK_ID_COLLISION` check never fires, and a cloud command's ISO week ID is not reconciled with the locally computed start date ([3.3](#33-optional-cloud-start-telegram-approval-to-worker-command), [5.1](#51-calendar-week-ids-and-reel-ids)).
- **UI dependence.** Flow, YouTube Studio, TikTok Studio and the Instagram composer change their markup; each change needs a selector update from real DOM. The accounts use Turkish-language UIs; `test_selector_language_coverage.py` requires every publisher selector list to resolve structurally or to carry a non-Turkish wording as well, but the Flow selectors are outside that rule.
- **Data API mode has no resume guard.** `YouTubePublisher` ignores `upload_started`, so a Reel whose previous attempt is recorded (`UPLOAD_ATTEMPTED`, or `REVIEW_REQUIRED` after YouTube rejected an uploaded video) is uploaded again on the next pass. The default Studio mode does not have this gap.
- **Single PC, single process.** Generation needs the owner's Windows PC and signed-in Chrome profiles. The weekly pipeline does not take the process lock that `run.py` uses, so two weekly runs started at the same time are not prevented.
- **QC depth.** QC catches broken, black, blank, frozen, wrongly shaped and silent-when-it-should-not-be videos. It does not judge content, and in the weekly pipeline it does not check the final duration; the 29.0–31.5 second window exists only in the older `publish.py` path (`is_v3_publishing_eligible`). If ffprobe itself fails inside `is_live_production_eligible`, the resolution and audio checks are skipped with a warning rather than failing the Reel.
- **Cloud plane is optional and partly unwired.** No code path creates the first `cloud_weeks` row, so the day-6 approval only works once a week row exists (the tests insert one). `local_worker.py` processes one command per `--run-once` invocation and has no polling loop. `WEEKLY_APPROVAL_DAY`, `LOCAL_WORKER_POLL_SECONDS`, `MEDIA_RETENTION_DAYS` and `ENABLE_MEDIA_CLEANUP` are read but not applied. Failed worker commands and `FAILED_RETRYABLE` Instagram jobs are not retried automatically (only `MEDIA_READY`, `READY_TO_PUBLISH` and lease-expired `PREPARING` jobs are claimable), and jobs processed while the Instagram flags simulate end as a final `PUBLISHED` with `MOCK_DRY_RUN_ID` ([3.4](#34-optional-cloud-instagram-route)). Production's S3 requirement is checked only by the preflight; `MEDIA_STORAGE_BACKEND=s3` without `S3_BUCKET` silently uses local disk. `claim_due_instagram_job` updates the chosen row without re-checking its status, which is safe with the single scheduler thread but not with two workers.
- **Cloud Instagram timing and branding.** The cloud worker claims a job when its slot is within `INSTAGRAM_PREPARE_MINUTES_BEFORE` (15) minutes and publishes as soon as the container is ready, so a post can go live before its slot. The media-upload ID regexes accept only unprefixed IDs, so the cloud route works for the default brand only.
- **Brand isolation gaps that are latent today.** The Instagram web publisher always uses the default Instagram port and profile and has no account-identity check; Crafts By Man has Instagram disabled, so this does not affect current runs. Reel IDs carry a hard-coded `2026`.
- **Mirror detail.** The Obsidian `02_REELS` notes are built from `ReelState`, whose platform fields the weekly pipeline does not update, so platform progress is authoritative only in `progress.json`.

Natural next steps: make `all_platform_done` and `find_last_scheduled_date` honour the rehearsal stamp, or keep rehearsal state in a separate directory; accept `--dry-run` in `main()` (or stop the launchers from passing it) and give rehearsals a zero hold; run `run_pre_publish_hard_gate` on the Instagram routes too; give cutaways their own beat texts; take the process lock in the weekly pipeline; add the final-duration check to `VideoValidator`; seed the current week in the cloud database (or let the worker register it) and give the worker a polling loop; make the Instagram worker wait for the slot before publishing; feed brand ports and expected usernames into the Instagram web publisher; derive the year in Reel IDs from the slot date; update `ReelState` platform fields from the platform phases so the vault mirror is complete.

## 10. Code tour

Read in this order:

1. [`automation/brands.py`](../automation/brands.py) — the two channels and how a brand fails closed; short and sets the vocabulary.
2. [`automation/simple_weekly_pipeline.py`](../automation/simple_weekly_pipeline.py) — the whole weekly lifecycle; start at `run`, then `_get_or_create_manifest`, `_fresh_plans`, `_run_generate_phase`, `_run_platform_phase`.
3. [`automation/orchestration/batch_manifest.py`](../automation/orchestration/batch_manifest.py) — the manifest/progress split and atomic writes.
4. [`automation/content/content_modes.py`](../automation/content/content_modes.py) — the mode registry every audio decision goes through.
5. [`automation/content/engine.py`](../automation/content/engine.py) and [`automation/content/diversity.py`](../automation/content/diversity.py) — candidate scoring and group interleaving.
6. [`automation/content/segment_planner.py`](../automation/content/segment_planner.py), then [`story_planner.py`](../automation/content/story_planner.py) and [`hidden_build_planner.py`](../automation/content/hidden_build_planner.py) — how a concept becomes three prompts that repeat one shared context, written differently per format.
7. [`automation/flow/state_machine.py`](../automation/flow/state_machine.py), then [`automation/flow/generator.py`](../automation/flow/generator.py) — the decision table and the per-segment loop.
8. [`automation/quality/validator.py`](../automation/quality/validator.py) — the QC chain.
9. [`automation/publishing/eligibility.py`](../automation/publishing/eligibility.py) and [`automation/publishing/preflight_gate.py`](../automation/publishing/preflight_gate.py) — what must be true before a YouTube or TikTok upload; `_instagram_preflight` in the pipeline is the narrower Instagram version.
10. [`automation/publishing/youtube_studio_publisher.py`](../automation/publishing/youtube_studio_publisher.py) — the most complete example of resume-without-reupload against a web UI.
11. [`automation/cloud/app.py`](../automation/cloud/app.py) — routing and the auth-before-body rule.
12. [`automation/cloud/approval_service.py`](../automation/cloud/approval_service.py) and [`automation/cloud/instagram_worker.py`](../automation/cloud/instagram_worker.py) — the two cloud state machines.

## 11. Glossary

| Term | Meaning |
|---|---|
| Reel | One 30-second 9:16 video; the unit of planning, generation and publishing |
| Brand | A channel identity: BuildVerse (default, no ID prefix) or Crafts By Man (`CBM-` prefix) |
| Slot | One publishing time: 19:30 or 22:00 Europe/Istanbul on one of the week's 7 days |
| Week / batch | 14 Reels in 14 consecutive slots, stored under `workspace/batches/<week_id>/` |
| Manifest | `manifest.json`, the week's content plan; `DRAFT` until `LOCKED` |
| Progress | `progress.json`, per-platform outcome per Reel |
| Content mode | The Reel format: `silent_global_step_by_step`, `narrative_ambient_story`, `hidden_build_story`, `cutaway_reveal_story` |
| Concept | A curated subject from a mode's library, identified by `id_slug` |
| Segment / beat | One of the three 10-second parts of a Reel, generated separately in Flow |
| Google Flow | Google's web app for video generation that the automation drives in Chrome |
| CDP | Chrome DevTools Protocol, used by Playwright to attach to an already running Chrome |
| Baseline artifact | A video already visible in Flow before Generate was clicked; never downloaded as the new result |
| Provenance | `ReelState.source`; only `flow_live_generation` may be published |
| Pre-publish gate | `run_pre_publish_hard_gate`, run immediately before each YouTube or TikTok upload; the Instagram routes run the narrower `_instagram_preflight` |
| Rehearsal (dry run) | A weekly run without `--live`: mock Flow provider and mock publishers, everything else real ([3.5](#35-what-a-rehearsal-dry-run-exercises)) |
| Rehearsal stamp | `dry_run: true` on a `progress.json` entry written by a rehearsal; honoured by some checks only ([5.7](#57-platform-phases)) |
| Native scheduler | A platform's own "schedule for later" feature, used instead of posting at the slot time |
| Soft failure | A submit whose read-back was inconclusive; recorded, and the run moves on to the next Reel (Instagram's `SUBMITTED_UNVERIFIED` is never retried) |
| Hold | The up-to-30-minute wait for a manual fix when a platform is stuck |
| Local worker | The PC side of the cloud flow: heartbeat, command claim, pipeline run |
| Control plane | The optional cloud HTTP service, database, bucket and background jobs |
| Kural 31 | "Rule 31", the repository's browser-automation rule (see [5.8](#58-what-each-publisher-does)) |
| EVET / HAYIR, Planla, Onayla | Turkish UI words: yes / no, schedule, approve |

## Türkçe özet

Reels AI Factory, sahibinin iki kanalı (BuildVerse ve Crafts By Man) için her hafta kanal başına 14 dikey, 30 saniyelik video planlayan, üreten, kontrol eden ve YouTube, TikTok ve Instagram'ın kendi zamanlayıcılarına planlayan bir Python otomasyonudur. İçerik planı elle hazırlanmış konsept kütüphanelerinden ve şablonlardan deterministik olarak çıkar; dil modeli kullanılmaz. Videolar, sahibinin oturum açtığı gerçek Chrome'a CDP üzerinden bağlanan Playwright ile Google Flow'da üretilir (Reel başına 3 × 10 saniyelik parça, FFmpeg ile birleştirilir). Bulut kontrol katmanı Docker imajı olarak paketlenmiş ve `railway.toml` ile Railway'e hazırdır, ancak isteğe bağlıdır ve şu an çalıştırılmamaktadır.

Haftalık hat (`simple_weekly_pipeline.py`) aşamaları sabit sırayla çalıştırır ve her adımı diske yazar; aynı `.bat` tekrar çalıştırıldığında kaldığı yerden devam eder, biten videoyu yeniden üretmez, planlanmış Reel'i yeniden yüklemez. Tek istisna, bir provanın (dry run) yazdığı haftadır (aşağıda). Bu belge yazılırken test paketi yeniden çalıştırıldı: 64 dosyada 1.054 test, 1.051 geçti, 3'ü yalnızca üretim bilgisayarında anlamlı olduğu için atlandı.

- **Planlama:** 19:30 ve 22:00 slotları; yeni hafta, platforma ulaşan son slotun ertesi günü başlar (bugünün ilk slotuna en az 6 saat varsa bugün). Konseptler kanalın kendi geçmişine göre sıralanır: hiç yayınlanmamış olan önce, sonra en uzun bekleyen; dinlenme süresi havuz büyüklüğüne göre en fazla 21 gün, 7 günden kısa tekrar `CONCEPT_POOL_EXHAUSTED` ile reddedilir. Geçmiş, sonucu değil planı okur: hiç yayınlanmamış veya prova haftalarındaki konseptler de yayınlanmış sayılır.
- **Promptlar:** üç parça aynı süreklilik bilgisini taşır, ama her format kendi kalıbıyla yazar (inşa: "Visual identity" / "Preserve exactly", hikâye ve kesit: `PLACE`, `SETTING`, `CAMERA` gibi etiketli satırlar, gizli inşa: "The location is the same in every beat"). Kesit Reel'leri yalnızca parça adlarını değiştirir; parça metinleri hâlâ terk edilmişlik ve çürüme anlatır.
- **Üretim:** Reel başına bir Flow projesi; Generate'ten önce ekrandaki eski videoların parmak izi alınır ve yalnızca yeni video indirilir; ajan için en fazla 2 yeniden deneme, kredi sorusuna en fazla 1 onay; kredi harcayan yükseltilmiş indirme seçenekleri asla seçilmez; aynı SHA-256'lı iki parça reddedilir. Ayarlarda yalnızca onay "Hiçbir zaman", 9:16 ve çıktı sayısı düğmelerine tıklanır; yapılandırmadaki model adı seçilmez, yalnızca yazdırılır.
- **Kalite kontrol:** video akışı ve 0,5 sn'den uzun süre, 0,50–0,60 en-boy oranı, 5 karede siyah (ortalama < 5), boş (sapma < 4) ve donmuş (ilk-son fark < 3) kontrolü, içerik moduna göre ses zorunluluğu; aynı hata üst üste 2 kez olursa üretim durur.
- **Kapılar:** tam yayın öncesi kapı (kaynak, Reel ID eşitliği, şablon metadata, slot, kayıt SHA-256'sı) yalnızca YouTube ve TikTok yüklemelerinden önce çalışır. Instagram'ın iki yolu yalnızca uygunluk ve Reel ID kontrolünü yapar; şablon metadata yalnızca kilitlemede denetlenir.
- **Yayın:** önce YouTube, sonra TikTok, sonra Instagram; YouTube ve TikTok'ta yüklemeden önce `UPLOAD_ATTEMPTED` yazılır, başka Reel'e ait uzak ID reddedilir, takılan platform için Telegram uyarısı verilip en fazla 30 dakika beklenir; "hemen paylaş" asla tıklanmaz, uzak içerik asla silinmez.
- **Prova (dry run):** haftalık `.bat` dosyalarının `--dry-run` seçeneği Python'a ulaşmadan hata verir (çıkış kodu 2). Modül `--live` olmadan çalıştırılırsa sahte videolar kapıda durur, her platform 30 dakika bekletilir ve Telegram mesajları gerçekten gönderilebilir; geride kalan prova haftasını sonraki canlı çalıştırma devralır. Canlı üretilmiş bir hafta prova edilirse sahte `SCHEDULED` kayıtları yazılır; Reel bazındaki kontroller bu damgayı okur, ama platformun ve haftanın bitip bitmediğine bakan kontroller okumaz, bu yüzden canlı hafta hiç yayınlanmadan bitmiş sayılabilir.
- **Bulut:** Telegram onayı (izinli kullanıcı ve sohbet, 48 saat geçerlilik), işçi komut kuyruğu, yerel disk veya S3 uyumlu depolama (canlıda S3 şartını yalnızca ön kontrol denetler) ve Meta Graph API ile isteğe bağlı Instagram işçisi. Hesap kimliği tanımlıysa işçi, varsayılan güvenlik bayraklarıyla işlediği işleri `MOCK_DRY_RUN_ID` ile kalıcı olarak `PUBLISHED` yapar; bu işler sonradan gerçekten yayınlanmaz. Komuttaki ISO hafta kimliği ile yerelde hesaplanan başlangıç tarihi birbirini tutmayabilir. Her POST gövdesi okunmadan önce başlıkları denetlenir, boş veya şablon işçi anahtarı uç noktaları kapatır, Telegram kimlikleri tanımlı değilse onaylar reddedilir.
- **İşletim rehberi:** `SUBMITTED_UNVERIFIED`, `REEL_ID_MEDIA_MISMATCH`, `[STATE_DIVERGENCE]`, `CONCEPT_POOL_EXHAUSTED`, `USER_ACTION_REQUIRED` ve prova kaynaklı durumlar için platformda neye bakılacağı ve `progress.json` gibi dosyalarda neyin düzeltileceği 8. bölümdedir.
- **Bilinen eksikler:** UI değişikliklerine bağımlılık, haftalık hatta süreç kilidi ve son süre kontrolü olmaması, YouTube Data API modunda yeniden yükleme korumasının olmaması, bulut haftasının ilk kaydını oluşturan kod olmaması, bulut Instagram işçisinin slot saatinden önce yayınlayabilmesi ve yalnızca varsayılan markayı kabul etmesi, yukarıdaki prova ve Instagram kapısı boşlukları.
