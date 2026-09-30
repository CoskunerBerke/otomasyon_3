# Reels AI Factory (otomasyon_3)

End-to-end automation that plans, generates, quality-checks and schedules short vertical videos (Reels / Shorts) on YouTube, TikTok and Instagram, with an Obsidian vault as the production log.

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Playwright](https://img.shields.io/badge/Playwright-2EAD33?logo=playwright&logoColor=white)
![FFmpeg](https://img.shields.io/badge/FFmpeg-007808?logo=ffmpeg&logoColor=white)
![OpenCV](https://img.shields.io/badge/OpenCV-5C3EE8?logo=opencv&logoColor=white)
![YouTube Data API](https://img.shields.io/badge/YouTube_Data_API-v3-FF0000?logo=youtube&logoColor=white)
![Meta Graph API](https://img.shields.io/badge/Meta_Graph_API-Instagram-0467DF?logo=meta&logoColor=white)
![Obsidian](https://img.shields.io/badge/Obsidian-7C3AED?logo=obsidian&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)
![Railway](https://img.shields.io/badge/Railway-0B0D0E?logo=railway&logoColor=white)
![Telegram](https://img.shields.io/badge/Telegram-bot-26A5E4?logo=telegram&logoColor=white)
![pytest](https://img.shields.io/badge/pytest-0A9EDC?logo=pytest&logoColor=white)

> **Status:** personal automation project, in active use for the weekly schedule of two of my own channels
> (BuildVerse and Crafts By Man). Windows-first; the cloud control plane runs in Docker.

## Overview

Every week the factory produces a 14-Reel series (7 days × 2 time slots) per channel. It reads past Reels from an Obsidian vault to avoid repeating topics, writes an English video prompt, drives the **Google Flow** web app with Playwright to generate the clips, validates and assembles the final MP4 with FFmpeg, and then uses each platform's **native scheduler** so nothing has to be online at publish time. A small cloud service on Railway handles Telegram approvals and an optional Instagram worker.

## Features

- **Weekly pipeline** — `PLAN → GENERATE → VALIDATE → LOCK → YOUTUBE → TIKTOK → INSTAGRAM → DONE`; a phase starts only when the previous one is complete, and the content plan is immutable once locked.
- **Idea and prompt engine** — topic history and diversity scoring, multiple content modes (silent step-by-step builds, narrated real-history stories with ambient audio, hidden-build and cutaway-reveal stories).
- **Google Flow automation** — connects to a real Chrome session over CDP, sets 9:16, submits prompts, resumes and downloads segments; stops with `USER_ACTION_REQUIRED` instead of bypassing logins or CAPTCHAs.
- **Quality control** — FFprobe checks for aspect ratio and duration, frame sampling for black or frozen frames, audio handling per content mode, faststart, and 3 × 10 s segment concatenation into a 30 s Reel.
- **Publishing** — YouTube (Data API v3 or YouTube Studio), TikTok Studio and Instagram (web scheduler or Meta Graph API), with localized metadata (en, tr, hi, id, ja on YouTube) and AI-content disclosure.
- **Safety by design** — idempotent uploads (`reel_id + platform` + SHA-256), per-platform failure isolation, never clicks "post now", never deletes remote content, brand isolation so one channel's video cannot reach another channel, single-run lock and a hard cap per run.
- **Multi-brand** — each channel has its own accounts, Chrome profiles, ports, ID prefix and inventory.
- **Obsidian integration** — Reel notes move through `03_SCRIPTS → 04_PRODUCTION → 05_READY / 07_REJECTED`, plus a publishing queue, an agent control center and graph-view links.
- **Cloud control plane** — HTTP service with Telegram webhook approvals, weekly scheduler, local-worker command queue, S3-compatible media storage and health checks.
- **Test suite** — about 780 pytest tests, including regression tests for past production incidents.

## Tech stack

| Area | Tools |
|---|---|
| Language | Python 3.10+ (Docker image: 3.11) |
| Browser automation | Playwright (Chrome over CDP) |
| Media | FFmpeg / FFprobe, OpenCV, Pillow, NumPy |
| Platforms | YouTube Data API v3 (google-api-python-client, OAuth), TikTok Studio, Instagram web + Meta Graph API |
| Cloud | Python `http.server`, PostgreSQL (psycopg) or SQLite, boto3 (S3-compatible storage), Telegram Bot API |
| Knowledge base | Obsidian (Markdown notes, graph view) |
| Ops | Docker, Railway (`railway.toml`), Windows `.bat` launchers, pytest |

## Project structure

```text
automation/
├── simple_weekly_pipeline.py   # live weekly entry point (phase by phase)
├── run.py, publish.py          # generation / publishing CLIs
├── brands.py                   # per-channel accounts, profiles, ID prefixes
├── agents/                     # history, idea, segment planner, flow, quality, publish agents
├── content/                    # concepts, content modes, prompt engine, diversity rules
├── flow/                       # Google Flow browser automation
├── quality/                    # ffprobe checks, frame analysis, concatenation
├── publishing/                 # YouTube, TikTok, Instagram publishers + guards
├── orchestration/              # weekly manifests, slots, state, reconciliation
├── obsidian/                   # vault reader / writer
└── cloud/                      # Railway control plane, Telegram bot, workers, storage
tests/                          # pytest suite
docs/                           # RAILWAY_DEPLOYMENT.md, TELEGRAM_SETUP.md
*.bat                           # one-click Windows launchers
```

## Getting started (Windows)

Requirements: Windows 10/11, Python 3.10+, FFmpeg and FFprobe on `PATH`, a Google account with Flow access, and an Obsidian vault.

1. `INSTALL_FIRST_TIME.bat` — creates `.venv`, installs `requirements.txt` and Playwright Chromium, prepares `config.local.json` (template: `config.example.json`).
2. `FLOW_LOGIN.bat` — opens a dedicated Chrome profile; sign in to Google Flow manually and leave the window open.
3. `BUILDVERSE_GIRIS.bat` / `CRAFTSBYMAN_GIRIS.bat` — sign in to each channel's platforms once.
4. Rehearse without spending credits or uploading:

```powershell
.venv\Scripts\python automation\run.py --count 1 --dry-run
.venv\Scripts\python automation\publish.py --count 14 --dry-run
pytest -v tests/
```

5. Weekly run: `BUILDVERSE_HAFTALIK_14_REEL.bat` or `CRAFTSBYMAN_HAFTALIK_14_REEL.bat`; the `*_SADECE_*` launchers finish a single platform for a half-done week.

If Google Flow's UI changes, error screenshots and HTML are saved under `screenshots/errors/`, and selectors live in `automation/flow/selectors.py`.

### Environment variables (names only)

See `.env.example` and `.env.railway.example`: `META_GRAPH_VERSION`, `META_APP_ID`, `META_APP_SECRET`, `META_ACCESS_TOKEN`, `INSTAGRAM_ACCOUNT_ID`, `INSTAGRAM_EXPECTED_USERNAME`, `INSTAGRAM_DRY_RUN`, `INSTAGRAM_ALLOW_UPLOAD`, `INSTAGRAM_ALLOW_PUBLISH`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USER_ID`, `TELEGRAM_CHAT_ID`, `TELEGRAM_WEBHOOK_SECRET`, `PUBLIC_BASE_URL`, `WEEKLY_APPROVAL_DAY`, `WEEKLY_APPROVAL_LOCAL_TIME`, `APP_TIMEZONE`, `APP_ENV`, `DATABASE_URL`, `LOCAL_WORKER_API_KEY`, `LOCAL_WORKER_POLL_SECONDS`, `MEDIA_STORAGE_BACKEND`, `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_REGION`, `ENABLE_TELEGRAM_WEBHOOK`, `ENABLE_WEEKLY_SCHEDULER`, `ENABLE_INSTAGRAM_WORKER`.
OAuth files and tokens live in `secrets/` and are git-ignored.

## Deployment

The cloud control plane is built from the `Dockerfile` and deployed on **Railway** (`railway.toml`, health check at `/health`). `docker-compose.example.yml` runs it locally. Step-by-step guides: [docs/RAILWAY_DEPLOYMENT.md](docs/RAILWAY_DEPLOYMENT.md) and [docs/TELEGRAM_SETUP.md](docs/TELEGRAM_SETUP.md). Video generation itself runs on the local Windows worker.

---

## Türkçe

**Reels AI Factory**, dikey kısa videoları (Reels / Shorts) planlayan, üreten, kalite kontrolünden geçiren ve YouTube, TikTok ve Instagram'da planlayan uçtan uca bir otomasyondur. Üretim kaydı olarak Obsidian kasası kullanılır.

> **Durum:** kişisel otomasyon projesi; kendi iki kanalımın (BuildVerse ve Crafts By Man) haftalık yayın takvimi için aktif
> olarak kullanılıyor. Windows öncelikli; bulut kontrol katmanı Docker ile çalışır.

### Ne yapar?

Her hafta kanal başına 14 Reel'lik (7 gün × 2 slot) bir seri üretir. Obsidian'daki geçmiş Reel'leri okuyarak konu tekrarını engeller, İngilizce video promptu yazar, **Google Flow** arayüzünü Playwright ile kullanarak klipleri üretir, FFmpeg ile doğrulayıp birleştirir ve platformların **kendi zamanlayıcılarına** planlar; yayın anında bilgisayarın açık olması gerekmez. Railway üzerindeki küçük bir bulut servisi Telegram onaylarını ve isteğe bağlı Instagram işçisini yönetir.

### Özellikler

- **Haftalık hat:** PLAN → ÜRET → DOĞRULA → KİLİTLE → YOUTUBE → TIKTOK → INSTAGRAM; bir aşama ancak önceki tamamlanınca başlar.
- **Fikir ve prompt motoru:** geçmiş analizi, çeşitlilik puanı, birden çok içerik modu (sessiz adım adım inşa, ortam sesli gerçek tarih hikâyeleri vb.).
- **Google Flow otomasyonu:** gerçek Chrome oturumuna CDP ile bağlanır; giriş veya CAPTCHA çıkarsa atlatmaya çalışmaz, `USER_ACTION_REQUIRED` ile durur.
- **Kalite kontrol:** en-boy oranı ve süre kontrolü, siyah/donmuş kare analizi, 3 × 10 sn parçayı 30 sn Reel'e birleştirme.
- **Yayınlama:** YouTube (API veya Studio), TikTok Studio, Instagram (web veya Meta Graph API); çok dilli metadata ve yapay zekâ içerik bildirimi.
- **Güvenlik:** çift yükleme koruması (SHA-256), platform bazında hata izolasyonu, "hemen paylaş" asla tıklanmaz, uzak içerik asla silinmez, kanallar arası karışma engellenir.
- **Obsidian entegrasyonu**, **Telegram onaylı bulut kontrol katmanı** ve yaklaşık **780 pytest testi**.

### Kurulum (Windows)

Gerekenler: Windows 10/11, Python 3.10+, `PATH`'te FFmpeg/FFprobe, Google Flow erişimi olan bir Google hesabı ve bir Obsidian kasası.

1. `INSTALL_FIRST_TIME.bat` — sanal ortamı ve bağımlılıkları kurar.
2. `FLOW_LOGIN.bat` — Google Flow'a elle giriş yapın, pencereyi açık bırakın.
3. `BUILDVERSE_GIRIS.bat` / `CRAFTSBYMAN_GIRIS.bat` — kanal hesaplarına bir kez giriş yapın.
4. Kredi harcamadan deneme: `.venv\Scripts\python automation\run.py --count 1 --dry-run`
5. Haftalık çalışma: `BUILDVERSE_HAFTALIK_14_REEL.bat` veya `CRAFTSBYMAN_HAFTALIK_14_REEL.bat`.

Ortam değişkenlerinin adları `.env.example` ve `.env.railway.example` dosyalarındadır; gerçek değerler ve OAuth dosyaları git'e girmez. Bulut kurulumu için [docs/RAILWAY_DEPLOYMENT.md](docs/RAILWAY_DEPLOYMENT.md) ve [docs/TELEGRAM_SETUP.md](docs/TELEGRAM_SETUP.md) dosyalarına bakın.

---

Built by [Berke Coşkuner](https://github.com/CoskunerBerke)
