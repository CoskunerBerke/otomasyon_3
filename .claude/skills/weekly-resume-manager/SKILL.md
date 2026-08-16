---
name: weekly-resume-manager
description: Haftalık 14 Reel'lik (7 gün x 2 slot, 19:30 & 22:00 Europe/Istanbul) pipeline'ın envanter tarama, eksik üretim, slot atama ve resume/idempotency mantığını yönetir. "Bu Reel neden tekrar üretildi", "aynı ID iki slota atandı", "kaç Reel eksik", "resume güvenli mi" gibi sorularda ya da weekly_orchestrator.py'nin _scan_v3_inventory / _assign_reels_to_slots / _generate_missing_v3_reels fonksiyonlarına dokunulacağı her durumda mutlaka bu skill'i kullan.
---

# Weekly Resume Manager

## Ne zaman kullanılır

- `automation/weekly_orchestrator.py::run_weekly_pipeline` akışı, `_scan_v3_inventory`, `_assign_reels_to_slots`, `_generate_missing_v3_reels`, `_find_or_create_reel_state` değişiyor veya hata veriyor.
- Bir haftalık plan (`WeekPlan`/`PublishingSlot`) tutarsız görünüyor: aynı `reel_id` iki slotta, boş slot, yanlış zaman damgası.
- "Gerçek/tamamlanmış bir Reel neden yeniden üretildi" veya "Flow kredisi boşa gitti" şikayeti var.
- Bir hafta kısmen tamamlanmış (bazı slotlar SCHEDULED, bazıları değil) ve devam ettirilmesi gerekiyor.

## Ne zaman kullanılmaz

- Sorun tek bir Reel'in yayın-öncesi uygunluğu (mock mu, placeholder metadata mı) ise → **production-media-guardian**.
- Sorun tarayıcı/DOM otomasyonu ise → **youtube-tiktok-safety**.
- Sorun sadece metadata İÇERİĞİ (başlık/caption kalitesi) ise → **reel-metadata-director**.

## Gerçek mimari (kod okunmadan varsayım yapma)

- `WeekPlan` 14 `PublishingSlot` içerir (`automation/orchestration/slot_generator.py::generate_14_slot_week_plan`), her biri `reel_id`, `youtube_status`, `tiktok_status`, `instagram_status`, `qc_status` taşır.
- `run_weekly_pipeline` sırası: (1) `REEL-2026-0010`'u `TEST_COMPLETED` işaretle → (2) plan yükle/oluştur → (3) reconciliation (salt-okunur) → (4) `_scan_v3_inventory()` ile mevcut UYGUN envanteri bul → (5) `unassigned_slots` sayısı `available_reels` sayısını aşıyorsa `_generate_missing_v3_reels(needed, week_id, used_ids=...)` ile eksik kadar üret → (6) `_assign_reels_to_slots` ile 14 benzersiz ID'yi slotlara dağıt → (7) her platform için sırayla schedule/handoff.
- `_scan_v3_inventory`, dosya adı deseniyle DEĞİL, `StateRepository.list_all_reels()`'ten okunan gerçek `ReelState`'ler üzerinden ve `is_live_production_eligible` (production-media-guardian'ın alanı) ile filtreler.
- `_generate_missing_v3_reels`'in `used_ids` parametresi KRİTİKTİR: çağıran taraf (`run_weekly_pipeline`) zaten uygun bulunan `available_reels`'in ID'lerini buna geçirir; fonksiyon içindeki ID seçim döngüsü hem `HARD_EXCLUDED_REEL_IDS` hem `used_ids` hem de "bu ID'nin zaten `generation_status == COMPLETE` bir state'i var mı" kontrolünü yapar. Bu üç kontrolden biri eksik bırakılırsa, sistem zaten tamamlanmış gerçek bir Reel'in ID'sini "boş" sanıp üzerine yeni içerik üretebilir (2026-08-17 canlı olayının kök nedeni tam olarak buydu — aynı ID iki slota atanmasına, o da paylaşılan tarayıcı sayfasının bozulmasına yol açtı).
- `_assign_reels_to_slots`, `available_reels` listesinde aynı ID'nin birden fazla kez geçmesine karşı (`avail_ids`'i tekilleştirerek) bir güvenlik ağı da içerir — bu ağı kaldırma, sadece asıl nedeni (üstteki madde) düzeltmiş olman bunu gereksiz kılmaz.
- Bir slot gerçek, uygun bir video bulamazsa `generation_status="NOT_STARTED"`, `qc_status="PENDING"` kalır ve `WAITING_FOR_GENERATION` olarak işaretlenir — bu Reel için ASLA `COMPLETE`/`PASS` uydurulmaz (phantom completion yasağı, CLAUDE.md kural 4).
- Zamanlama döngülerinin her biri (`_schedule_youtube_slot`, `_schedule_tiktok_slot`, `_handoff_instagram_slot`), reel `COMPLETE`/`PASS` değilse veya platform zaten `SCHEDULED`/`PUBLISHED`/`REMOTE_VERIFIED` ise o slotu atlar — hiçbir zaman tekrar yüklemez.

## Görev akışı

1. Sorunu netleştirirken önce gerçek `workspace/state/weeks/{week_id}.json` ve `workspace/state/reels/*.json` dosyalarını oku — kodun ne YAPMASI gerektiğini değil, state'in ŞU AN ne DEDİĞİni gör.
2. `git diff`/`git log` ile en son bu alanlara dokunan commit'i bul, aynı hatanın daha önce düzeltilip düzeltilmediğini kontrol et.
3. Bir ID çakışması/duplicate slot bulursan: kodda kök nedeni düzelt (yukarıdaki üç kontrol), SONRA yerel state'i onar — çakışan slotlardan birini, dosyası fiziksel olarak yeniden adlandırılmış (Reel ID invariant'ı sağlayan) yeni bir ID'ye taşı; asla iki slotu aynı ID'de bırakma.
4. Gerçek platform ilerlemesi olan bir Reel'i (örn. bir platformda zaten SCHEDULED) ASLA state onarımı sırasında geri alma/üzerine yazma — kanıtı (screenshot, `13_PUBLISHING/*.md` kaydı) koru ve state'e yansıt.
5. Düzeltmeden sonra `_scan_v3_inventory()`'yi (dry_run=True ile, canlı aksiyon olmadan) manuel çağırıp envanterin beklenen şekilde göründüğünü doğrula.

## Güvenlik sınırları

- Bu skill hiçbir zaman gerçek Flow üretimi, gerçek platform yükleme/planlama tetiklemez; sadece state/plan/kod düzeyinde çalışır.
- REEL-2026-0010 hiçbir koşulda yeniden kullanılamaz.
- Zaten tamamlanmış segment/final video asla yeniden üretilmez veya silinmez.

## İlgili repository dosyaları

`automation/weekly_orchestrator.py`, `automation/orchestration/{models.py,slot_generator.py,state_repository.py}`, `automation/publishing/eligibility.py` (referans, değiştirmez), `tests/test_weekly_orchestrator.py`, `tests/test_live_pipeline_safety_regression.py`.

## Başarılı sonuç kriterleri

- Hiçbir `reel_id` iki slota atanmıyor.
- Zaten `COMPLETE` bir Reel asla yeniden üretilmiyor.
- `WAITING_FOR_GENERATION` slotlar asla yayınlanmaya çalışılmıyor.
- Gerçek platform ilerlemesi (varsa) state onarımında kaybolmuyor.
