"""
Multilingual resilient selectors for TikTok Studio web interface.
Includes explicit selectors for 'Paylaşıldığında' radio buttons (Şimdi vs Planla),
contenteditable Açıklama / Caption fields, and date/time inputs.
"""
from typing import List

class TikTokSelectors:
    """Resilient selector candidates for TikTok Studio web upload and scheduler."""

    # 1. File input & Upload triggers
    FILE_INPUT_SELECTORS: List[str] = [
        "input[type='file'][accept*='video']",
        "input[type='file'][accept*='mp4']",
        "input[type='file']",
        "iframe[src*='upload'] >>> input[type='file']"
    ]

    SELECT_VIDEO_BUTTONS: List[str] = [
        "button:has-text('Video seçin')",
        "button:has-text('Video seç')",
        "button:has-text('Select video')",
        "button:has-text('Select file')",
        "button:has-text('Upload')",
        "button:has-text('Yükle')",
        "div[role='button']:has-text('Video seçin')",
        "div[role='button']:has-text('Select video')",
        "div:has-text('Video seçin'):not(:has(*))",
        "div:has-text('Select video'):not(:has(*))",
        "[aria-label*='Video seçin']",
        "[aria-label*='Select video']",
        ".upload-btn",
        ".btn-upload"
    ]

    # 2. Upload state & Existing Loaded Editor Check
    UPLOAD_COMPLETE_INDICATORS: List[str] = [
        "div:has-text('Yüklendi')",
        "span:has-text('Yüklendi')",
        "div:has-text('Uploaded')",
        "span:has-text('Uploaded')",
        "div[class*='uploaded-container']",
        "div[class*='upload-success']",
        "div[class*='file-info']:has-text('.mp4')",
        "div:has-text('100%')"
    ]

    # 2b. React-Joyride Onboarding / Tour Overlay Selectors
    JOYRIDE_OVERLAYS: List[str] = [
        "#react-joyride-portal",
        "div[data-test-id='overlay']",
        "div.react-joyride__overlay",
        "div.react-joyride__tooltip",
        "div[class*='joyride']"
    ]

    JOYRIDE_DISMISS_BUTTONS: List[str] = [
        "#react-joyride-portal button:has-text('Kapat')",
        "#react-joyride-portal button:has-text('Close')",
        "#react-joyride-portal button:has-text('Atla')",
        "#react-joyride-portal button:has-text('Skip')",
        "#react-joyride-portal button:has-text('Tamam')",
        "#react-joyride-portal button:has-text('Bitir')",
        "#react-joyride-portal button:has-text('Done')",
        "#react-joyride-portal button:has-text('Got it')",
        "#react-joyride-portal button[aria-label*='Close']",
        "#react-joyride-portal button[aria-label*='Kapat']",
        "#react-joyride-portal button[aria-label*='Skip']",
        "#react-joyride-portal button[aria-label*='Atla']",
        "div[class*='joyride'] button:has-text('Kapat')",
        "div[class*='joyride'] button:has-text('Close')",
        "div[class*='joyride'] button:has-text('Atla')",
        "div[class*='joyride'] button:has-text('Skip')"
    ]

    JOYRIDE_NEXT_BUTTONS: List[str] = [
        "#react-joyride-portal button:has-text('İleri')",
        "#react-joyride-portal button:has-text('Next')",
        "div[class*='joyride'] button:has-text('İleri')",
        "div[class*='joyride'] button:has-text('Next')"
    ]

    # 3. Caption / Açıklama Field
    CAPTION_EDITORS: List[str] = [
        "div[contenteditable='true'][class*='editor']",
        "div[contenteditable='true'][role='combobox']",
        "div[class*='DraftEditor-root'] div[contenteditable='true']",
        "div[data-placeholder*='Açıklama'] div[contenteditable='true']",
        "div[data-placeholder*='caption'] div[contenteditable='true']",
        "div[contenteditable='true']",
        "textarea[placeholder*='Açıklama']",
        "textarea[placeholder*='caption']",
        "textarea[placeholder*='Başlık']",
        "textarea"
    ]

    # 4. Schedule Mode: 'Paylaşıldığında' -> 'Şimdi' (Now) vs 'Planla' (Schedule)
    SCHEDULE_MODE_SECTION: List[str] = [
        "div:has-text('Paylaşıldığında')",
        "div:has-text('When to post')"
    ]

    NOW_RADIO_OPTIONS: List[str] = [
        "input[name='postSchedule'][value='post_now']",
        "label:has(input[name='postSchedule'][value='post_now'])",
        "div.schedule-radio-container label:has-text('Şimdi')",
        "div[role='radio']:has-text('Şimdi')",
        "div[role='radio']:has-text('Now')",
        "label:has-text('Şimdi')",
        "label:has-text('Now')"
    ]

    SCHEDULE_RADIO_OPTIONS: List[str] = [
        "input[name='postSchedule'][value='schedule']",
        "label:has(input[name='postSchedule'][value='schedule'])",
        "div.schedule-radio-container label:has-text('Planla')",
        "div.schedule-radio-container label:has-text('Schedule')",
        "div[role='radio']:has-text('Planla')",
        "div[role='radio']:has-text('Schedule')",
        "label:has-text('Planla')",
        "label:has-text('Schedule')",
        "span:has-text('Planla')",
        "span:has-text('Schedule')"
    ]

    # 5. Date & Time Inputs (Appears after Planla is selected)
    DATE_INPUTS: List[str] = [
        "div.scheduled-picker input[value*='-']",
        "div.scheduled-picker input[placeholder*='YYYY']",
        "div.scheduled-container input[value*='-']",
        "input.TUXTextInputCore-input[value*='-']",
        "input.TUXTextInputCore-input[placeholder*='YYYY']",
        "input.TUXTextInputCore-input",
        "input.Tiktok-date-input",
        "div[class*='date-picker'] input",
        "div[class*='date'] input",
        "input[placeholder*='YYYY-MM-DD']",
        "input[placeholder*='Date']",
        "input[placeholder*='Tarih']"
    ]

    TIME_INPUTS: List[str] = [
        "input.TUXTextInputCore-input[value*=':']",
        "div[class*='time-picker'] input",
        "div[class*='timepicker'] input",
        "div.scheduled-picker input[value*=':']",
        "div.scheduled-picker input[placeholder*='HH']",
        "div.scheduled-container input[value*=':']",
        "input.TUXTextInputCore-input",
        "input.Tiktok-time-input",
        "div[class*='time'] input",
        "input[placeholder*='HH:mm']",
        "input[placeholder*='Time']",
        "input[placeholder*='Saat']"
    ]

    # 6. AI-generated content disclosure
    MORE_SETTINGS_BUTTONS: List[str] = [
        "div.more-btn:has(span:text-is('Daha fazla göster'))",
        "div.more-btn:has(span:text-is('Show more'))",
        "button:has-text('Daha fazla göster')",
        "button:has-text('Show more')",
        "div:has-text('Daha fazla göster')",
        "div:has-text('Show more')",
        "span:has-text('Daha fazla göster')",
        "span:has-text('Show more')"
    ]

    AI_DISCLOSURE_TOGGLES: List[str] = [
        "[data-e2e='aigc_container'] .Switch__root",
        "[data-e2e='aigc_container'] .Switch__content",
        "[data-e2e='aigc_container'] [role='switch']",
        "[data-e2e='aigc_container'] input[type='checkbox']",
        "div:has-text('AI ile oluşturulmuş içerik') .Switch__root",
        "div:has-text('AI ile oluşturulmuş içerik') .Switch__content",
        "div:has-text('AI ile oluşturulmuş içerik') [role='switch']",
        "div:has-text('AI-generated content') .Switch__root",
        "div:has-text('AI-generated content') .Switch__content",
        "input[type='checkbox'][name*='ai']",
        "input[type='checkbox'][aria-label*='AI']",
        "div:has-text('Yapay zeka tarafından oluşturuldu') ~ div input[type='checkbox']",
        "div:has-text('Yapay zekâ tarafından oluşturulan içerik') ~ div input[type='checkbox']",
        "label:has-text('AI ile oluşturulmuş içerik')",
        "label:has-text('AI-generated content')",
        "div[class*='ai-label'] div[role='switch']",
        "div[role='switch']:has-text('AI')"
    ]

    # 7. Final Action Buttons (Bottom Bar: Paylaş / Planla / Post / Schedule)
    FINAL_ACTION_BUTTONS: List[str] = [
        "button[data-e2e='post_video_button']",
        "button.Button__root[data-e2e='post_video_button']",
        "button[type='button']:has-text('Planla')",
        "button[type='submit']:has-text('Planla')",
        "button[type='button']:has-text('Schedule')",
        "button[type='submit']:has-text('Schedule')",
        "button:has-text('Planla')",
        "button:has-text('Schedule')",
        "button:has-text('Paylaş')",
        "button:has-text('Post')"
    ]

    # Modal Confirmation button
    MODAL_CONFIRM_BUTTONS: List[str] = [
        "div[role='dialog'] button:has-text('Schedule')",
        "div[role='dialog'] button:has-text('Planla')",
        "div[role='dialog'] button:has-text('Confirm')",
        "div[role='dialog'] button:has-text('Onayla')",
        "div[role='dialog'] button:has-text('Tamam')",
        "button:has-text('Allow')",
        "button:has-text('İzin ver')"
    ]

    # "Paylaşmaya devam edilsin mi?" -- shown when Planla is pressed while TikTok is still
    # running its content check. Real DOM (user-supplied 2026-08-17):
    #   <div class="TUXModal common-modal-confirm-modal" role="dialog"
    #        title="Paylaşmaya devam edilsin mi?">
    #     ... <button class="TUXButton--secondary"><div class="TUXButton-label">İptal</div></button>
    #         <button class="TUXButton--primary"><div class="TUXButton-label">Hemen paylaş</div></button>
    #
    # The ONLY safe exit is İptal. "Hemen paylaş" publishes IMMEDIATELY instead of at the
    # scheduled slot -- it would dump the whole week's Reels out at once and destroy the
    # schedule. It is never clicked, under any circumstance (CLAUDE.md, Kural 31).
    CONTENT_CHECK_CONFIRM_MODAL: List[str] = [
        "div[role='dialog']:has-text('Paylaşmaya devam edilsin mi?')",
        "div.TUXModal:has-text('Paylaşmaya devam edilsin mi?')",
    ]

    CONTENT_CHECK_MODAL_CANCEL_BUTTONS: List[str] = [
        "div[role='dialog'] button:has-text('İptal')",
        "div.TUXModal button:has-text('İptal'), div.common-modal-confirm-modal button:has-text('İptal')",
    ]

    # Guard list: if a selector would ever resolve to one of these, it must be discarded.
    FORBIDDEN_IMMEDIATE_PUBLISH_LABELS: List[str] = [
        "hemen paylaş",
        "post now",
        "şimdi paylaş",
    ]

    # TikTok Studio shows a resume banner when a previous editing session was left
    # unsaved: "Düzenlemekte olduğunuz bir video kaydedilmedi. Düzenlemeye devam
    # edilsin mi?" with [Sil] [Devam]. While it is up, the upload area is inert and both
    # the file input and the 'Video seçin' button are unreachable -- which surfaced as
    # "TikTok file input not found on page" and stalled the whole TikTok phase.
    UNSAVED_DRAFT_BANNER_MARKERS: List[str] = [
        "kaydedilmedi",
        "düzenlemeye devam",
        "unsaved",
        "continue editing",
    ]

    # A DELETE confirmation is a different dialog with the same button label, and TikTok
    # shows it over the same screens: "Bu gönderi silinsin mi? Videonuz ... ve tum
    # duzenlemeler kalici olarak silinecek." with [Simdi degil] [Sil]. Its [Sil] destroys
    # a post -- exactly what CLAUDE.md forbids this system from ever doing automatically.
    #
    # The banner check reads the whole page, so a stale "kaydedilmedi" bar anywhere would
    # authorise a click that then lands on THIS dialog's [Sil]. Whenever any of these
    # markers is present, no discard is attempted at all and a human is asked to look.
    DESTRUCTIVE_DELETE_CONFIRM_MARKERS: List[str] = [
        "silinsin mi",
        "kalıcı olarak silinecek",
        "kalici olarak silinecek",
        "permanently deleted",
        "delete this post",
    ]

    # The SAFE way out of that delete dialog. "Şimdi değil" cancels it -- nothing is
    # removed, the post stays exactly as it is -- so clicking it is not a destructive
    # action and needs no human. Its sibling [Sil] is the one that must never be touched.
    #
    # Real DOM, captured 2026-08-19:
    #   <div class="jsx-1150920910 common-modal-footer">
    #     <button class="TUXButton ... TUXButton--secondary" aria-disabled="false">
    #       <div class="TUXButton-content"><div class="TUXButton-label">Şimdi değil</div></div>
    #     </button>
    #     <button class="TUXButton ... TUXButton--primary" aria-disabled="false">
    #       <div class="TUXButton-content"><div class="TUXButton-label">Sil</div></div>
    #     </button>
    #   </div>
    #
    # The two are siblings differing only by label and by primary/secondary -- and the
    # DESTRUCTIVE one is the primary. So both strategies below pin the exact label text
    # with :text-is (never a substring), which cannot resolve to "Sil". The jsx-* class is
    # a build hash and is deliberately not used (Kural 31); TUXButton-label and
    # common-modal-footer are stable design-system names.
    DELETE_DIALOG_CANCEL_BUTTONS: List[str] = [
        "button:has(div.TUXButton-label:text-is('Şimdi değil')), "
        "button:has(div.TUXButton-label:text-is('Not now'))",
        ".common-modal-footer button:has(div:text-is('Şimdi değil')), "
        ".common-modal-footer button:has(div:text-is('Not now'))",
    ]

    # Never resolve to this one. Kept as a named constant so the guard can assert it is
    # not what it is about to click.
    DELETE_DIALOG_DESTRUCTIVE_LABELS: List[str] = ["sil", "delete"]

    # Discards the UNSAVED editing session only. This is not published content and not a
    # scheduled post -- worst case the Reel is uploaded again, which the idempotency
    # checks already handle. 'Devam' is deliberately NOT used: it would reopen the old
    # video's editor and risk operating on the wrong Reel.
    UNSAVED_DRAFT_DISCARD_BUTTONS: List[str] = [
        "button:has-text('Sil'), button:has-text('Discard')",
        "div[class*='banner'] button:has-text('Sil'), div[role='alert'] button:has-text('Sil')",
    ]

    # Purely informational "we're still reviewing your content" notice, same class of
    # blocker as YouTube's 'Anladım' overlay. Dismissing it is never a publish action --
    # these labels only ever acknowledge a notice. Kural 31: 2 semantic strategies.
    # NOTE: deliberately excludes anything resembling "Hemen paylaş"/"Post now".
    CONTENT_REVIEW_INFO_DISMISS_BUTTONS: List[str] = [
        "button[aria-label='Anladım'], button[aria-label='Got it'], "
        "button[aria-label='OK'], button[aria-label='Tamam']",
        "div[role='dialog'] button:has-text('Anladım'), div[role='dialog'] button:has-text('Got it')",
    ]

    # 8. Success Indicators & Remote Posts Management
    SCHEDULE_SUCCESS_INDICATORS: List[str] = [
        "div:has-text('Your video has been scheduled')",
        "div:has-text('Videolarınız planlandı')",
        "div:has-text('Video scheduled')",
        "div:has-text('Video planlandı')",
        "div:has-text('Planlandı')",
        "a[href*='manage']:has-text('Manage your posts')",
        "a[href*='manage']:has-text('Gönderilerinizi yönetin')",
        "a[href*='content']:has-text('Gönderiler')"
    ]

    LOGIN_BUTTONS: List[str] = [
        "button:has-text('Log in')",
        "button:has-text('Giriş yap')",
        "a[href*='login']"
    ]
