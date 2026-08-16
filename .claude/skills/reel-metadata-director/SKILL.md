---
name: reel-metadata-director
description: YouTube/TikTok/Instagram için başlık, caption ve hashtag üretimini gerçek ReelConceptPlan/ContentEngine/topic_key verisinden türetir; jenerik fallback metin veya tekrarlanan hashtag bloğu üretilmesini engeller. "Başlık jenerik görünüyor", "Architectural Marvel gibi bir isim çıktı", "hashtag iki kere yazılmış", "yeni bir concept/kategori eklemem lazım" durumlarında ya da PublishingMetadataBuilder / ReelConceptPlan / concepts.py'ye dokunulacağı her durumda mutlaka bu skill'i kullan.
---

# Reel Metadata Director

## Ne zaman kullanılır

- `automation/publishing/metadata_builder.py`, `automation/content/{prompt_engine.py,concepts.py,engine.py}` değişiyor.
- Yayınlanan/yayınlanacak bir Reel'in başlığı/caption'ı jenerik veya boş görünüyor.
- Yeni bir görsel konsept kategorisi (`ConceptDefinition`) eklenmesi gerekiyor.
- Hashtag'lerin bir kez mi yoksa iki kez mi eklendiği belirsiz.

## Ne zaman kullanılmaz

- Sorun bu metadata'nın PLATFORMA doğru şekilde YAZILIP yazılmadığı (UI otomasyonu) ise → **youtube-tiktok-safety**.
- Sorun jenerik metadata'nın yayın öncesi REDDEDİLİP reddedilmediği (gate mantığı, `is_placeholder_metadata`) ise → **production-media-guardian** (bu skill üretimi yapar, o skill üretileni denetler).

## Gerçek veri kaynağı zinciri

`automation/content/concepts.py::CATEGORIES` (40+ `ConceptDefinition`: `id_slug`, `name`, `category_group`, `environments`, `architectures`, `transformations`, `camera_styles`, `lighting_schemes`, `materials`, `reveals`, `default_title`, `topic_description`)
→ `PromptEngine.build_concept_plan()` bunlardan bir `ReelConceptPlan` üretir (`title`, `topic_description`, `topic_key`, `category`, `environment`, `architecture`, `transformation`, `reveal` vb.)
→ `automation/publishing/metadata_builder.py::PublishingMetadataBuilder.build_youtube_metadata()` / `build_tiktok_metadata()` bu alanlardan deterministik (seed = `reel_id + title`, hash tabanlı) başlık/caption/hashtag üretir — **LLM çağrısı YOKTUR ve olmamalıdır**, tamamen `automation/content` verisinden türetilir.

Resume/backfill senaryosunda (üretim anındaki `ReelConceptPlan` artık bellekte yoksa) `automation/content/concepts.py::find_concept_by_topic_key(topic_key)` kullan — `topic_key` formatı `"{id_slug}-{env_son_kelime}-{arch_son_kelime}"` şeklindedir (bkz. `PromptEngine.build_concept_plan`'daki `topic_key` satırı); bu fonksiyon en uzun eşleşen `id_slug`'ı bulur.

## Kesin yasaklar

- `f"Architectural Marvel {reel_id}"` veya buna benzer, Reel ID'yi doğrudan başlığa gömen jenerik fallback ASLA yazma. Bu proje 2026-08-16'da tam olarak bu string'in yanlış bir mock videoyla birlikte YouTube'a gitmesiyle sarsıldı; `production-media-guardian`'daki `is_placeholder_metadata` bunu artık reddediyor ama üretim tarafında da bu deseni asla yeniden yazma.
- Boş caption/placeholder metin üretme.
- Hashtag'leri hem `description`/`caption` string'inin İÇİNE göm hem de ayrı bir `hashtags` listesi olarak DÖNDÜRME — bu iki katmanlı ekleme, YouTube/TikTok'a giden son metinde tekrarlanan hashtag bloğuna yol açar (2026-08-16 olayının bir diğer bulgusu). Bu proje'nin sözleşmesi:
  - `PublishingMetadataBuilder.build_youtube_metadata()` zaten `description`'ı hashtag'siz, düzyazı olarak döndürür — böyle kalmalı.
  - `weekly_orchestrator.py`'deki `_schedule_youtube_slot`/`_schedule_tiktok_slot`, `PublishRecord.description`'a SADECE `r_state.caption`'ı koyar, hashtag EKLEMEZ.
  - Hashtag'i son metne ekleyen TEK katman, gerçekten platforma yazan katmandır: `YouTubeStudioUIObserver.fill_details()` ve `TikTokUIObserver.replace_caption()`. Yeni bir yayın yolu eklerken bu sözleşmeyi kopyala, ihlal etme.

## Görev akışı

1. Değişiklik yeni bir concept mi (kategori/tema), yoksa mevcut concept'ten üretim mantığı mı — buna göre `concepts.py` mü yoksa `metadata_builder.py` mü değişecek karar ver.
2. Yeni bir `ConceptDefinition` eklerken mevcut örneklerin (bkz. `desert-megacity`, `tropical-resort`, `abandoned-restoration`) alan sayısı/tonunu koru: her liste alanında (environments, architectures, ...) birden fazla gerçekçi seçenek olsun (deterministik hash bunlar arasından seçim yapıyor).
3. `build_youtube_metadata`/`build_tiktok_metadata` imzasını değiştiriyorsan, `weekly_orchestrator.py::_generate_missing_v3_reels` ve backfill script'lerindeki çağrı yerlerini de güncelle.
4. Bir Reel'in metadata'sını manuel onarıyorsan (resume/backfill), `find_concept_by_topic_key` ile gerçek concept'i bul, uydurma.
5. Değişiklik sonrası üretilen `(title, description, hashtags)` üçlüsünü gözden geçir: `description` hashtag İÇERMİYOR mu, `title` placeholder değil mi.

## Güvenlik sınırları

- Bu skill dış bir LLM/AI metadata sağlayıcısı çağırmaz (CLAUDE.md/proje kararı: "Do not require an external LLM for this repair... AI metadata provider may be added later as OPTIONAL infrastructure"). Böyle bir entegrasyon isteniyorsa mevcut deterministik yolu bozmadan, opsiyonel bir katman olarak ekle.
- Gerçek platform çağrısı yapmaz.

## İlgili repository dosyaları

`automation/content/concepts.py`, `automation/content/prompt_engine.py`, `automation/content/engine.py`, `automation/publishing/metadata_builder.py`, `automation/weekly_orchestrator.py` (`_generate_missing_v3_reels`, `_schedule_youtube_slot`, `_schedule_tiktok_slot`), `automation/publishing/preflight_gate.py` (`is_placeholder_metadata` — referans).

## Başarılı sonuç kriterleri

- Üretilen başlık/caption gerçek concept verisinden türetilmiş, Reel ID'yi çıplak şekilde başlığa gömmüyor.
- `description`/`caption` hashtag içermiyor; hashtag'ler ayrı listede.
- Yeni concept eklendiyse mevcut alan yapısıyla tutarlı ve `find_concept_by_topic_key` onu doğru bulabiliyor.
