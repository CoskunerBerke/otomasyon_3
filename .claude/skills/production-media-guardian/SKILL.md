---
name: production-media-guardian
description: Bir final MP4 dosyasının YouTube/TikTok/Instagram/S3 handoff'a gitmeden önce gerçekten production'a uygun olduğunu doğrulayan pre-publish eligibility gate mantığını yazar, denetler veya genişletir. Yeni bir yayın yolu eklerken, mevcut is_live_production_eligible / run_pre_publish_hard_gate mantığını değiştirirken, ya da "mock video production'a girdi", "yanlış Reel yayınlandı", "placeholder metadata gitti" gibi provenance/eligibility temelli sorunlarda mutlaka bu skill'i kullan.
---

# Production Media Guardian

## Ne zaman kullanılır

- Yeni bir kod yolu final MP4'ü bir platforma (YouTube/TikTok/Instagram) veya cloud handoff'a gönderiyor ve bu yolun gate'lerden geçtiğinden emin olunması gerekiyor.
- `automation/publishing/eligibility.py` veya `automation/publishing/preflight_gate.py` değiştiriliyor/genişletiliyor.
- "REEL-2026-0001 gibi bir mock/test video tekrar production'a girdi" veya "yanlış video/ID yayınlandı" şüphesi var.
- Yeni bir provenance kaynağı (`ReelProvenance` enum'una yeni bir değer) eklenmesi gerekiyor.

## Ne zaman kullanılmaz

- Sorun DOM/selector/tarayıcı otomasyonu ise (elemanı bulamıyor, tıklayamıyor) → **youtube-tiktok-safety**.
- Sorun hangi Reel'in hangi slota atanacağı / resume mantığıysa (eligibility'nin kendisi değil, envanter planlaması) → **weekly-resume-manager**.
- Sorun sadece başlık/caption/hashtag İÇERİĞİNİN kalitesiyle ilgiliyse (placeholder olup olmadığı DEĞİL, gerçek içerik üretimi) → **reel-metadata-director**.
- Genel, alanı belirsiz bir hata teşhisi gerekiyorsa önce **reels-pipeline-doctor**'ı kullan; o seni gerekirse buraya yönlendirir.

## Gerçek gate mimarisi (mevcut koddan)

Bu proje iki katmanlı bir yayın-öncesi doğrulama kullanır, ikisi de bozulmadan korunmalı:

1. **`automation/publishing/eligibility.py::is_live_production_eligible(reel_state, video_path)`**
   Bir Reel'in canlı ENVANTERE girip giremeyeceğini belirler (yani `_scan_v3_inventory` ve `_assign_reels_to_slots` bunu çağırır). Kontrol ettikleri:
   - `reel_id not in HARD_EXCLUDED_REEL_IDS` (şu an `REEL-2026-0010`, `REEL-2026-0001`)
   - `reel_state is not None` (state yoksa = uygun değil, varsayılan olarak DEĞİL uygun)
   - `reel_state.quarantine_reason` boş
   - `reel_state.source == "flow_live_generation"` (`ReelProvenance.FLOW_LIVE_GENERATION`)
   - `pipeline_version == 3`, `content_mode == "silent_global_step_by_step"`
   - `generation_status == "COMPLETE"`, `qc_status == "PASS"`
   - dosya var mı, boyutu yeterli mi
   - `video_sha256` state ile dosya eşleşiyor mu
   - çözünürlük bilinen mock imzasına (`KNOWN_MOCK_RESOLUTIONS = {(540, 960)}`) uymuyor mu (gerçek Flow çıktısı 720x1280'dir)

2. **`automation/publishing/preflight_gate.py::run_pre_publish_hard_gate(reel_state, slot, publish_record, video_path, already_platform_success)`**
   Bir Reel gerçekten UPLOAD anına geldiğinde çağrılır (`_schedule_youtube_slot`, `_schedule_tiktok_slot`, ve Instagram için `is_live_production_eligible` + `verify_reel_id_invariant` doğrudan). Yukarıdaki eligibility kontrolüne EK olarak:
   - `verify_reel_id_invariant`: `slot.reel_id == state.reel_id == publish_record.reel_id == dosya adı içindeki reel_id` — dördü de aynı değilse `REEL_ID_MEDIA_MISMATCH`.
   - `is_placeholder_metadata`: başlık/caption boşsa veya `PLACEHOLDER_TITLE_MARKERS` (şu an: `"architectural marvel"`) içeriyorsa reddet.
   - `publish_record.scheduled_at_local == slot.scheduled_at_local` (tam eşleşme).
   - `already_platform_success` True ise (o platform zaten başarılıysa) direkt `ALREADY_PUBLISHED_SKIP`.
   - `publish_record.video_sha256` dosyayla eşleşiyor mu (tekrar, PublishRecord'a özel doğrulama).

## Görev akışı

1. Değiştirilecek/incelenecek kod yolunu bul ve hangi gate'in (envanter mi, upload-anı mı) ilgili olduğuna karar ver.
2. Yeni bir eligibility kuralı gerekiyorsa `is_live_production_eligible`'a ekle; yeni bir upload-anı kuralı gerekiyorsa `run_pre_publish_hard_gate`'e ekle. İkisini karıştırma — envanter tarama ile gerçek upload anı farklı zamanlar, farklı hata mesajları üretmeli.
3. Yeni bir `ReelProvenance` değeri eklerken `automation/orchestration/models.py`'deki enum'u güncelle ve `LIVE_PRODUCTION_PROVENANCE` setinin (`eligibility.py`) sadece gerçekten canlı-üretim anlamına gelen değerleri içerdiğinden emin ol.
4. Hiçbir zaman "dosya adı `clean_REEL-*.mp4` desenine uyuyor" tek başına yeterlilik kanıtı olarak kabul etme — bu proje 2026-08-16 olayının doğrudan nedeniydi (bkz. CLAUDE.md kural 3).
5. Reddedilen bir Reel'i asla otomatik silme; sadece `quarantine_reason` ile işaretle (bkz. gerçek örnek: `REEL-2026-0001` state kaydı).
6. Değişiklikten sonra **reels-pipeline-doctor**'ın test/commit adımlarını izle (veya doğrudan `tests/test_live_pipeline_safety_regression.py`'deki ilgili test gruplarını genişlet).

## Güvenlik sınırları

- Bu skill asla mock/test dosyalarını fiziksel olarak silmez; sadece mantıksal olarak dışlar/karantinaya alır.
- `HARD_EXCLUDED_REEL_IDS` listesinden bir ID'yi kaldırmak (yani onu tekrar production'a açmak) her zaman kullanıcının açık onayını gerektirir — bu bir güvenlik regresyonudur.
- Gate mantığını "geçici olarak" gevşetip sonra unutma riski olan hiçbir değişiklik yapma; gevşetme gerekiyorsa neden gerektiğini ve nasıl geri alınacağını raporda açıkça belirt.

## İlgili repository dosyaları

`automation/publishing/eligibility.py`, `automation/publishing/preflight_gate.py`, `automation/orchestration/models.py` (`ReelState`, `ReelProvenance`), `automation/weekly_orchestrator.py` (`_scan_v3_inventory`, `_schedule_youtube_slot`, `_schedule_tiktok_slot`, `_handoff_instagram_slot`), `tests/test_live_pipeline_safety_regression.py`, `tests/test_eligibility.py`.

## Başarılı sonuç kriterleri

- Yeni/değişen kural hem `is_live_production_eligible` hem de (upload anı söz konusuysa) `run_pre_publish_hard_gate` seviyesinde tutarlı.
- Mock/test/quarantined/REEL-2026-0010/REEL-2026-0001 hâlâ kesin olarak dışlanıyor.
- Reel ID invariant hâlâ dördü de (slot/state/record/dosya adı) karşılaştırıyor.
- Placeholder metadata kontrolü hâlâ aktif.
- İlgili testler güncellenmiş ve geçiyor.
