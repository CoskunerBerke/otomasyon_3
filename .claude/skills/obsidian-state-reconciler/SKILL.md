---
name: obsidian-state-reconciler
description: Yerel/cloud state ile C:\Users\berke\obsidian\Reels_AI_Studio vault'undaki notlar arasında tutarlılığı sağlar; eksik/bozuk/güncel-olmayan Obsidian notunu gerçek state'e göre düzeltir. Obsidian notu eksik, yanlış, state ile uyuşmuyor, veya "Obsidian'da görünmüyor/yanlış görünüyor" şikayetlerinde mutlaka bu skill'i kullan. Obsidian'ı ASLA gerçek veri kaynağı (source of truth) olarak kullanma veya öyle davranma.
---

# Obsidian State Reconciler

## Ne zaman kullanılır

- `automation/orchestration/obsidian_mirror.py` veya `automation/cloud_sync.py` değişiyor.
- Bir Reel/hafta/run için state var ama Obsidian'da yansımıyor veya eski bilgi gösteriyor.
- Kullanıcı Obsidian vault'unda (`01_WEEKS`, `02_REELS`, `03_APPROVALS`, `04_RUNS`, `05_ALERTS`, `06_REPORTS`) bir tutarsızlık bildiriyor.
- Yeni bir alan (örn. `ReelState.source`, `quarantine_reason` gibi) eklendi ve Obsidian notuna da yansıması isteniyor.

## Ne zaman kullanılmaz

- Sorun `workspace/state/` içindeki asıl state'in kendisi (Obsidian'a hiç bakmadan da var olan bir hata) ise → **reels-pipeline-doctor** veya ilgili spesifik skill.
- Sorun Railway/PostgreSQL cloud state'i ise (Obsidian mirror değil, kaynağın kendisi) → **railway-cloud-operator**.

## Gerçek mimari — İKİ AYRI Obsidian entegrasyonu var, karıştırma

Bu repository'de birbirinden bağımsız, farklı klasör yapıları kullanan iki Obsidian sistemi vardır:

1. **`automation/orchestration/obsidian_mirror.py::ObsidianControlCenter`** — güncel V3 haftalık pipeline'ın aynası. Klasörler: `00_SYSTEM`, `01_WEEKS`, `02_REELS`, `03_APPROVALS`, `04_RUNS`, `05_ALERTS`, `06_REPORTS`. Metodlar: `sync_week_note(WeekPlan)`, `sync_reel_note(ReelState)`, `sync_run_report(RunReport)`, `create_alert_note(...)`. `WeeklyOrchestrator` her `run_weekly_pipeline` sonunda bunu çağırır. **`automation/cloud_sync.py::CloudObsidianSync`** bu SINIFI sarmalayıp Railway/PostgreSQL'deki cloud state'i (Telegram onayları, cloud haftaları, Instagram kuyruğu) aynı vault'a yazar — `LocalWorker.sync_cloud_to_obsidian()` bunu kullanır.
2. **`automation/obsidian/` paketi** (`reader.py::ObsidianReader`, `writer.py::ObsidianWriter`, `reel_repository.py::ObsidianReelRepository`) — DAHA ESKİ, V1/V2 tekil-Reel pipeline'ının (`automation/run.py`) kullandığı sistem. Farklı klasörler: `03_SCRIPTS`, `04_PRODUCTION`, `05_READY`, `06_PUBLISHED`, `07_REJECTED`, `09_TEMPLATES`. **Bu iki sistemi birbirine karıştırıp aynı fonksiyonu iki yerde yazma** — hangi pipeline'ın (haftalık V3 mü, tekil V1/V2 mi) ilgili olduğuna göre doğru modülü kullan.

Not: `automation/obsidian/` paketi daha önce `.gitignore`'daki hatalı bir `obsidian/` kuralı yüzünden yanlışlıkla git'ten tamamen dışlanmıştı (kaynak kodu, vault değil) — bu düzeltildi, ama benzer bir `.gitignore` hatasına karşı dikkatli ol: vault'u (`obsidian/`, `Obsidian/`) dışlarken kaynak kod klasörlerini (`automation/obsidian/`) yanlışlıkla dışlamamak için pattern'lerin repo köküne sabitlenmiş (`/obsidian/`) olduğunu doğrula.

## Görev akışı

1. Önce gerçek state'i oku (`workspace/state/reels/*.json`, `workspace/state/weeks/*.json`) — bu her zaman doğru kaynaktır.
2. İlgili Obsidian notunu (`vault_path/02_REELS/{reel_id}.md` gibi) oku, hangi alanların eksik/yanlış olduğunu karşılaştır.
3. Eksiklik `ObsidianControlCenter.sync_reel_note`/`sync_week_note`/`sync_run_report` kodunda bir alanın hiç yazılmıyor olmasından kaynaklanıyorsa, o metoda alanı ekle (frontmatter + okunabilir gövde).
4. Kod düzeltildikten sonra, mevcut gerçek state üzerinden notları YENİDEN üret (örn. `StateRepository.list_all_reels()` + `ObsidianControlCenter().sync_reel_note(reel)` döngüsü) — kullanıcı manuel olarak her notu düzeltmek zorunda kalmasın.
5. Kullanıcının vault'taki KENDİ yazdığı notları (Obsidian'ın kendi kullanıcı içeriği, template'ler, kişisel notlar) sebepsiz silme veya üzerine yazma; sadece bu araçların ürettiği/yönettiği dosyalara dokun.

## Güvenlik sınırları

- Obsidian asla `StateRepository`'nin (yerel JSON) veya Railway/PostgreSQL'in (cloud) yerine geçmez; o sadece insan-okunur bir ayna. Mimariyi tersine çevirip Obsidian'dan state OKUYAN yeni bir mantık ekleme (V1/V2'nin `ObsidianReader`'ı bu kuralın istisnasıdır, o zaten var olan, bilinçli bir tasarım — yeni V3 kodunda tekrarlama).
- Vault yolunu (`C:\Users\berke\obsidian\Reels_AI_Studio`) hardcode etmek yerine mevcut `DEFAULT_VAULT_PATH`/`vault_path` parametrelerini kullan.

## İlgili repository dosyaları

`automation/orchestration/obsidian_mirror.py`, `automation/cloud_sync.py`, `automation/obsidian/{reader.py,writer.py,reel_repository.py}` (V1/V2, ayrı sistem), `automation/orchestration/state_repository.py` (referans kaynak).

## Başarılı sonuç kriterleri

- Vault notu, o an gerçek state ile tam tutarlı.
- İki Obsidian sistemi (V3 mirror vs V1/V2 reader/writer) karıştırılmamış.
- Kullanıcının kendi vault içeriği bozulmamış.
