---
name: youtube-tiktok-safety
description: YouTube Studio ve TikTok Studio web arayüzünü Playwright/CDP ile otomatikleştiren koda dokunurken (selector ekleme/değiştirme, yeni bir UI adımı, modal/dialog yönetimi, schedule/publish akışı) Kural 31'i ve platforma özgü güvenli davranışları uygular. Selector bulunamadı, buton tıklanamadı, wizard adımı takıldı, ACCOUNT_MISMATCH, schedule doğrulanamadı gibi UI-otomasyon hatalarında ya da "Hemen paylaş/Post now'a tıklama riski var mı" türü güvenlik sorularında mutlaka bu skill'i kullan.
---

# YouTube & TikTok Studio Safety

## Ne zaman kullanılır

- `automation/publishing/youtube_studio_ui_observer.py`, `youtube_studio_selectors.py`, `youtube_studio_publisher.py`, `tiktok_ui_observer.py`, `tiktok_selectors.py`, `tiktok_publisher.py`, `tiktok_browser.py`, `youtube_studio_browser.py` dosyalarından biri değişiyor.
- Yeni bir DOM elementi (buton, modal, radio, input) bulunması/tıklanması gerekiyor.
- Bir UI otomasyon hatası var: `NEEDS_USER_HTML`, `WIZARD_STEP_TRANSITION_FAILED`, `ACCOUNT_MISMATCH`, `SCHEDULE_CONFIRMATION_NOT_VERIFIED`, `FINAL_SCHEDULE_BUTTON_DISABLED`, `TIMEPICKER_OPEN`, `TIKTOK_ONBOARDING_OVERLAY_BLOCKING` vb.
- Kullanıcı gerçek bir HTML/screenshot paylaşıp "bu elementi bul" diyor.

## Ne zaman kullanılmaz

- Sorun DOM/selector değil, hangi Reel'in/dosyanın gönderileceği (eligibility/ID) ise → **production-media-guardian**.
- Sorun bir Reel'in ne zaman/hangi slotta üretileceği/yayınlanacağıysa (UI değil, planlama) → **weekly-resume-manager**.

## KURAL 31 — mutlak, pazarlıksız

Bu proje, 2026-08-16 canlı olayından önce de var olan ve olaydan sonra CLAUDE.md'ye yazılan bir kuralı uyguluyor:

- **Tek bir UI aksiyonu için en fazla 2 güvenli semantic selector stratejisi.** ("Semantic" = metin içeriği, `aria-label`, gerçek DOM attribute'u; rastgele CSS class hash'i DEĞİL.)
- **Asla** kullanma: `force=True`, JavaScript `click()`/`dispatchEvent`, pointer-events hack, overlay kaldırma, manuel `aria-checked`/`checked` attribute manipülasyonu, dinamik hash'lenmiş class/id'yi koda gömme.
- İki güvenli strateji de başarısız olursa ve gerçek DOM'a (log'daki `screenshots/errors/*.html` veya kullanıcının az önce paylaştığı HTML'e) bakmadan güvenle çıkarım yapılamıyorsa: **tahmin etme.** `NEEDS_USER_HTML` döndür ve TAM OLARAK hangi elementin `outerHTML`'ine (gerekirse parent/wrapper'ına da) ihtiyaç olduğunu söyle.
- Bu proje kanıta dayalı tespiti tercih eder: gerçek bir hata anlık görüntüsü/HTML dump'ı varsa (`screenshots/errors/`), yeni bir selector eklemeden önce onu oku — 2026-08-16'daki "Yeni proje" hatası tam olarak bu şekilde çözüldü (gerçek DOM'da buton hiç yoktu, tahmin edilmedi).

## Platforma özgü davranış (mevcut kodda zaten uygulanmış, koruman gereken tasarım)

### YouTube Studio (`youtube_studio_ui_observer.py` / `youtube_studio_publisher.py`)
- Wizard adımları `WizardStep`: DETAILS → VIDEO_ELEMENTS → CHECKS → VISIBILITY. `detect_current_wizard_step()` önce `workflow-step` attribute'una (otoritatif kaynak), sonra metin/stepper sezgilerine bakar.
- `get_active_upload_dialog()` sahnede birden fazla `ytcp-uploads-dialog` olabileceği için "aktif" olanı skorlayarak bulur — asla ilk bulduğunu varsaymaz.
- Schedule tıklanmadan önce: tarih/saat doğrulanmış olmalı (`set_schedule_datetime` + okuma-doğrulama), takvim popup'ı kapalı olmalı.
- `click_schedule_and_verify` sadece tıklamayı DEĞİL, gerçek onay UI'ını da bekler — asla "tıklandı = başarılı" varsayma.
- **Content review bilgi penceresi** ("İçeriğinizi kontrol etmeye devam ediyoruz" / "Anladım"): `dismiss_content_review_info_if_present()` ile güvenle kapatılır — bu ASLA hata sayılmaz, ASLA publish-now'a geçiş anlamına gelmez.
- Uzak schedule doğrulaması (`verify_remote_scheduled_status`) en fazla 2 deneme (`youtube_studio_publisher.py` içinde bounded retry) — sonuç hâlâ belirsizse `SCHEDULE_RESUME_REQUIRED` işaretlenir, asla yanlışlıkla `SCHEDULED` denmez.
- Her `upload_and_schedule()` çağrısı, kanal doğrulamasından ÖNCE kanonik kanal sayfasına (`https://studio.youtube.com/channel/{channel_id}`) navigate eder — önceki Reel'in bıraktığı sayfa durumundan (draft/edit ekranı) miras kalan yanlış "kanal adı" okumasını önlemek için (2026-08-17 olayının kök nedeniydi).
- Opak hata noktalarında (`ACCOUNT_MISMATCH`, dosya inputu bulunamadı, wizard geçişi başarısız, schedule onayı doğrulanamadı) `capture_error_snapshot()` çağrılır — bu mekanizmayı yeni hata noktalarına da ekle.

### TikTok Studio (`tiktok_ui_observer.py` / `tiktok_publisher.py`)
- Planla/Şimdi radio durumu tıklamadan önce doğrulanır (`schedule_mode_verified`); doğrulanmadıysa `click_schedule_and_verify` anında `SCHEDULE_MODE_NOT_ACTIVE` ile durur.
- **"Hemen paylaş"/"Post now" hiçbir koşulda tıklanmaz** — bu sabit bir üst sınırdır, hiçbir refactor bunu gevşetmemeli.
- İçerik kontrolü onay modalı ("Paylaşmaya devam edilsin mi?") çıkarsa: `Escape` ile güvenle kapatılır, buton aranmaz/tıklanmaz. Maksimum 2 gönderim denemesi; ikincisinde de modal çıkarsa `NEEDS_USER_HTML`.
- `is_editor_open_for_reel()` zaten açık bir editörü tespit edip tekrar yükleme (duplicate upload) yapmaz.
- Her `upload_and_schedule()` çağrısı kullanıcı adı doğrulamasından ÖNCE `self.config.tiktok_url`'e navigate eder (aynı YouTube gerekçesiyle: sayfa kalıntısı önleme).

## Görev akışı

1. Hatanın türünü sınıflandır: selector bulunamadı mı, state/scoping hatası mı (yanlış dialog/sayfa okunuyor), yoksa gerçek bir zamanlama/network sorunu mu.
2. Elimde gerçek DOM kanıtı var mı kontrol et (`screenshots/errors/`, kullanıcının verdiği HTML). Yoksa ve 2 güvenli selector denemesi yetmiyorsa, kanıt iste — kod yazma.
3. Selector eklerken mevcut listelerdeki (`*_SELECTORS`) stile uy: TR/EN ikili metin eşleşmesi, en fazla 2 strateji.
4. Yeni bir opak hata noktası ekliyorsan `capture_error_snapshot` çağrısını da ekle.
5. Değişiklik sonrası ilgili test dosyasını (`tests/test_youtube_studio.py` veya `tests/test_tiktok_studio.py`) çalıştır — **safe-test-and-release** kurallarına uy.

## Güvenlik sınırları

CLAUDE.md Kural 31 bölümü otoritatiftir; burası onun uygulama detayıdır, çelişki varsa CLAUDE.md kazanır. Bu skill hiçbir zaman gerçek bir tarayıcıyı kullanıcı onayı olmadan canlı bir YouTube/TikTok hesabına karşı çalıştırmaz.

## İlgili repository dosyaları

`automation/publishing/youtube_studio_ui_observer.py`, `youtube_studio_selectors.py`, `youtube_studio_publisher.py`, `youtube_studio_browser.py`, `tiktok_ui_observer.py`, `tiktok_selectors.py`, `tiktok_publisher.py`, `tiktok_browser.py`, `tests/test_youtube_studio.py`, `tests/test_tiktok_studio.py`, `screenshots/errors/`.

## Başarılı sonuç kriterleri

- En fazla 2 semantic selector stratejisi kullanılmış, hiç force/JS hack yok.
- Belirsiz durumlarda tahmin yerine `NEEDS_USER_HTML` veya kanıt talebi var.
- "Hemen paylaş"/"Post now" hiçbir dalda tıklanmıyor.
- Opak hata noktalarında snapshot alınıyor.
- İlgili test dosyası geçiyor.
