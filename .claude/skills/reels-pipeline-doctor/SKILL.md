---
name: reels-pipeline-doctor
description: Reels AI Factory'de (weekly_orchestrator, publishing, Flow, state, Obsidian, cloud) bir şey bozulduğunda uçtan uca kök neden teşhisi yapar ve güvenli şekilde düzeltir. Yanlış Reel ID, yanlış dosya seçimi, mock/test videonun production'a sızması, duplicate upload, resume/idempotency bozulması, state uyuşmazlığı, yanlış metadata, platform state ile local state çelişkisi, ya da genel olarak "bir run patladı, sebebini bul" tarzı her belirsiz hata için ilk başvurulacak skill budur. Kullanıcı "hata var", "bug var", "neden oldu", "düzelt" gibi ifadeler kullandığında ve semptom birden fazla dosyayı/katmanı ilgilendiriyor gibi göründüğünde mutlaka bu skill'i kullan.
---

# Reels Pipeline Doctor

## Ne zaman kullanılır

- Bir log/terminal çıktısında beklenmeyen hata, yanlış davranış veya "bir şeyler ters gitti" belirtisi var.
- Semptomun kaynağı belli değil: birden fazla katmanı (generation, publishing, state, Obsidian, cloud) ilgilendirebilir.
- Kullanıcı geçmişte olan bir canlı/gerçek çalıştırmanın çıktısını yapıştırıp "bunu incele" diyor.
- "Neden REEL-2026-XXXX yanlış yayınlandı", "state tutarsız", "aynı video iki kere yüklendi" gibi somut ama kök nedeni belirsiz şikayetler.

## Ne zaman kullanılmaz

- Sorun zaten net şekilde tek bir alana ait ve spesifik bir skill onu daha iyi kapsıyorsa, doğrudan o skill'i kullan:
  - Yayın öncesi uygunluk/gate mantığı → **production-media-guardian**
  - YouTube/TikTok Studio DOM/selector/otomasyon güvenliği → **youtube-tiktok-safety**
  - Haftalık resume/idempotency planlaması → **weekly-resume-manager**
  - Sadece başlık/caption/hashtag üretimi → **reel-metadata-director**
  - Sadece Obsidian notu eksik/bozuk → **obsidian-state-reconciler**
  - Sadece Railway/local worker/S3 handoff sorunu → **railway-cloud-operator**
- Kullanıcı sadece test/commit/push istiyor, bug avı istemiyorsa → **safe-test-and-release**.

Bu skill genel giriş noktasıdır: teşhisi yapar, kök neden hangi alana düşüyorsa o alanın kurallarını (yukarıdaki skill'lerden) uygular, ama kendi başına o alanların detaylı kural setini tekrar yazmaz.

## Görev akışı

1. **Kanıtı topla, tahmin etme.** Önce gerçek repository durumunu oku:
   - `git status`, `git log --oneline -15`, `git diff` (önceki ajanların raporlarına körü körüne güvenme — CLAUDE.md'nin dediği gibi, mevcut koda karşı doğrula).
   - `logs/` altındaki en yeni run log'ları.
   - `workspace/state/reels/*.json`, `workspace/state/weeks/*.json`, `workspace/state/runs/*.json` — gerçek persisted state.
   - `13_PUBLISHING/*.md` — gerçek PublishRecord kayıtları (varsa).
   - `screenshots/errors/*.html` / `*.png` / `*_diag.txt` — DOM kanıtı olan hatalar için birebir gerçek kanıt.
   - Obsidian vault'taki `02_REELS/`, `01_WEEKS/`, `04_RUNS/` notları (state ile tutarlı mı).
2. **Zinciri takip et.** Reels AI Factory'de tipik veri akışı:
   `ContentEngine/PromptEngine → Flow generation → VideoValidator (QC) → ReelState (StateRepository) → is_live_production_eligible (eligibility.py) → PublishRecord → run_pre_publish_hard_gate (preflight_gate.py) → YouTube/TikTok publisher → Instagram media_handoff → ObsidianControlCenter mirror`.
   Semptomu bu zincirde nerede başladığını bulana kadar geriye doğru izle (örnek: "yanlış video yüklendi" → PublishRecord.video_file nereden geldi → `_resolve_video_file` → `ReelState.video_path`/dosya adı eşleşmesi → `_scan_v3_inventory`/`_assign_reels_to_slots`).
3. **Aynı bug'ın başka yerde tekrarlanıp tekrarlanmadığını ara.** Bir kalıp (örn. bir field adı yanlış kullanılmış, bir ID kontrolü eksik) bulunduğunda `grep`/`Grep` ile aynı kalıbın başka dosyalarda da olup olmadığını kontrol et (`weekly_orchestrator.py`, `youtube_studio_publisher.py`, `tiktok_publisher.py`, `youtube_studio_ui_observer.py`, `tiktok_ui_observer.py` en sık etkilenen dosyalardır).
4. **Kök nedeni bulunca, en küçük güvenli düzeltmeyi doğrudan uygula.** Semptomu patchleme, kaynağı düzelt. Mevcut çalışan production modüllerini koru (CLAUDE.md: "Preserve working production modules; prefer the smallest fix that removes the root cause").
5. **Hedefli bir regresyon testi ekle veya güncelle.** Tek bir odaklı test dosyası tercih et (repo örneği: `tests/test_live_pipeline_safety_regression.py`), var olan mock/fake tarzına uy (gerçek tarayıcı/Flow/platform çağrısı yok).
6. **Test + secret scan + git diff** için **safe-test-and-release** skill'inin kurallarını uygula (pytest limiti, secret scan komutu, commit disiplini).
7. **Türkçe rapor ver.** Kök neden(ler), yapılan düzeltme(ler), korunan gerçek dosyalar/veriler, test sonucu, commit/push durumu.

## Güvenlik sınırları

- CLAUDE.md'deki tüm kurallar (V3-only, REEL-2026-0010 hariç tutma, Kural 31, canlı aksiyon yasağı, secret yasağı) geçerlidir — burada tekrar edilmiyor, oradan referans al.
- Bu skill hiçbir zaman kendiliğinden `--live` bir çalıştırma başlatmaz, gerçek Flow/YouTube/TikTok/Instagram/Telegram aksiyonu tetiklemez.
- Uzak platform içeriğini (YouTube/TikTok video, taslak) otomatik silmez veya değiştirmez; şüpheli bir uzak kayıt bulursa yerel state'i karantinaya alır ve `MANUAL_REMOTE_CLEANUP_RECOMMENDED` olarak raporlar.
- `workspace/`, `.env`, secret içeren config dosyalarının içeriğini asla ham olarak ekrana basmaz.

## İlgili repository dosyaları

`automation/weekly_orchestrator.py`, `automation/orchestration/{models.py,state_repository.py,reconciliation.py,slot_generator.py,obsidian_mirror.py}`, `automation/publishing/{eligibility.py,preflight_gate.py,models.py,repository.py,metadata_builder.py}`, `automation/flow/{page.py,selectors.py,generator.py}`, `logs/`, `workspace/state/`, `13_PUBLISHING/`, `screenshots/errors/`.

## Başarılı sonuç kriterleri

- Semptomun gerçek kök nedeni, kod/log/state kanıtıyla gösterilmiş (varsayımla değil).
- Düzeltme en küçük, en odaklı halde ve mevcut güvenlik davranışını zayıflatmıyor.
- Aynı bug kalıbının başka yerlerde tekrarlanıp tekrarlanmadığı kontrol edilmiş.
- Hedefli regresyon testi var ve geçiyor.
- Secret scan temiz, git diff gözden geçirilmiş, gereksiz/istenmeyen dosya stage edilmemiş.
