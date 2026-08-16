---
name: railway-cloud-operator
description: Local Worker → Railway HTTP API → PostgreSQL → private S3 → Instagram cloud worker mimarisini doğru yorumlar; worker heartbeat, LOCAL_WORKER_API_KEY auth, media handoff, MEDIA_READY, storage self-test, health endpoint gibi cloud/Railway kavramlarıyla ilgili kod değişikliklerini yönetir. "Railway'e bağlanamıyor", "media handoff başarısız", "worker heartbeat atmıyor", "S3'e yüklenmiyor", "cloud state senkronize olmuyor" gibi durumlarda mutlaka bu skill'i kullan. Gerçek Railway flag/env değişikliğini veya destructive cloud operasyonunu kendi başına yapmaz.
---

# Railway Cloud Operator

## Ne zaman kullanılır

- `automation/cloud/` (özellikle `config.py`, `local_worker_api.py`, `media_storage.py`, `health.py`, `railway_production_preflight.py`, `scheduler.py`) değişiyor.
- `automation/local_worker.py`, `automation/local_worker_cloud_client.py`, `automation/media_handoff.py` değişiyor.
- Instagram için "media handoff" / "MEDIA_READY" akışında bir sorun var.
- Railway ortam değişkenlerinin (env var) ne anlama geldiği, local vs cloud storage backend farkı netleştirilmesi gerekiyor.

## Ne zaman kullanılmaz

- Sorun Instagram'a fiilen YAYINLAMA (Meta Graph API çağrısı, `instagram_api.py`/`instagram_publisher` katmanı) ile ilgiliyse ve cloud handoff'tan SONRAsıysa, önce bu skille mimariyi doğrula ama gerçek Instagram publish mantığı ayrı bir alan — genel teşhis gerekiyorsa **reels-pipeline-doctor**'a yönlendir.
- Sorun Obsidian notu senkronizasyonuysa (cloud'dan gelen veri DOĞRU ama Obsidian'a YANLIŞ yansıyorsa) → **obsidian-state-reconciler**.

## Gerçek mimari (doğrulanmış akış)

```
WeeklyOrchestrator (Windows local)
  -> automation/media_handoff.py::handoff_reel_to_cloud()
    -> automation/local_worker_cloud_client.py::LocalWorkerCloudClient.upload_media_for_instagram()
      -> HTTP (X-Worker-Api-Key header, LOCAL_WORKER_API_KEY ile doğrulanır)
        -> automation/cloud/local_worker_api.py::handle_media_upload()
          -> automation/cloud/media_storage.py (backend'e göre S3MediaStorageAdapter veya LocalMediaStorageAdapter)
            -> PostgreSQL: InstagramScheduledJob kaydı, status=MEDIA_READY
```

- `automation/local_worker.py::LocalWorker` Windows tarafında çalışan sürekli ajan: `send_heartbeat()`, `process_next_command()` (komut tipleri: `GENERATE_WEEK` → `WeeklyOrchestrator.run_weekly_pipeline()`'ı tetikler, `SYNC_STATE` → Obsidian senkronizasyonu), `run_cycle()`. **Varsayılan CLI modu `--heartbeat-only`'dir** (`run_heartbeat_only`) — sıfır yazma, sıfır üretim; bu güvenli tanı modudur, canlı komut çekmez.
- `automation/cloud/config.py::CloudConfig` tüm davranışı env var'lardan okur: `APP_ENV`, `MEDIA_STORAGE_BACKEND` (`"local"` veya `"s3"`), `LOCAL_WORKER_API_KEY`, `PUBLIC_BASE_URL`, `ENABLE_WEEKLY_SCHEDULER`, `ENABLE_INSTAGRAM_WORKER`, `INSTAGRAM_*`. `is_production` gibi türetilmiş özellikler production'da S3 zorunluluğu gibi ek kısıtlar uygular.
- **Local makinede (Windows worker) S3 credential'larına gerek YOKTUR** — local worker sadece Railway HTTP API'sine `LOCAL_WORKER_API_KEY` ile kimlik doğrular; asıl S3 erişimi Railway TARAFINDA (`S3MediaStorageAdapter`) gerçekleşir. Bu ayrımı karıştırıp local `.env`'e S3 secret'ı önerme.
- `automation/cloud/local_worker_api.py::handle_storage_self_test()` ve `automation/cloud/health.py::get_health_status()` — gerçek bir sorunu teşhis ederken önce bunların (varsa) çıktısını/loglarını incele, tahmin etme.
- `automation/cloud/railway_production_preflight.py::run_railway_preflight()` production'a çıkmadan önceki güvenlik/konfig kontrolüdür — buradaki kontrolleri gevşetme.

## Görev akışı

1. Sorunun hangi hop'ta koptuğunu belirle: local worker → HTTP → auth → storage backend → PostgreSQL zincirinde nerede kanıt var (log, hata mesajı, HTTP status).
2. `CloudConfig`'in ilgili env var'ının doğru okunup okunmadığını kodda doğrula — gerçek `.env` değerini ASLA ekrana basma, sadece hangi değişkenin eksik/yanlış olabileceğini söyle.
3. Local vs S3 storage backend farkını netleştirirken `get_media_storage(config)` fonksiyonunun hangi adapter'ı seçtiğine bak (`config.media_storage_backend`).
4. Bir düzeltme öneriyorsan, bunun sadece KOD tarafı mı yoksa gerçek Railway panelinde bir env var/flag değişikliği mi gerektirdiğini açıkça ayır — ikincisi kullanıcının kendisinin yapması gereken bir aksiyondur, bu skill Railway panelini kendi başına değiştirmez.
5. Gerçek bir Railway MCP/connector erişimin yoksa, "Railway'e bağlandım" gibi bir izlenim verme; sadece repodaki kodun/konfigürasyonun ne yapması GEREKTİĞİNİ analiz et.

## Güvenlik sınırları

- `.env`, `LOCAL_WORKER_API_KEY`, `DATABASE_URL`, S3 secret, Meta token, Telegram bot token içeriklerini asla ham olarak yazdırma; sadece mevcut güvenli config loader'lar (`CloudConfig`, `mask_secret`) üzerinden konuş.
- Gerçek Railway destructive operasyonu (servis silme, veritabanı sıfırlama, env var'ı production'da değiştirme) yapmaz — bunu öneriyorsa kullanıcının açık onayını iste ve adımları kullanıcının kendisinin çalıştırması için yaz.
- `--live` bir haftalık komutu veya gerçek Instagram publish akışını kendi başına tetiklemez.

## İlgili repository dosyaları

`automation/cloud/{config.py,local_worker_api.py,media_storage.py,health.py,railway_production_preflight.py,scheduler.py,database.py}`, `automation/local_worker.py`, `automation/local_worker_cloud_client.py`, `automation/media_handoff.py`, `automation/cloud_sync.py`.

## Başarılı sonuç kriterleri

- Zincirdeki hangi hop'un koptuğu net kanıtla gösterilmiş.
- Local/cloud storage backend ayrımı doğru anlatılmış.
- Hiçbir secret ekrana basılmamış.
- Gerçek Railway'de değişiklik gerekiyorsa bu açıkça kullanıcıya devredilmiş, otomatik yapılmamış.
