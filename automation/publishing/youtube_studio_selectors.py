"""
Multilingual resilient DOM selectors for YouTube Studio web interface.
Includes distinct selectors for accordion headers, month headers, video link extraction,
time inputs & dropdown items, and final schedule submit buttons.
"""
from typing import List

class YouTubeStudioSelectors:
    """Resilient selector candidates for YouTube Studio (TR/EN)."""

    # 1. Header & Channel Identification
    CHANNEL_HEADER_SELECTORS: List[str] = [
        "#channel-title",
        "#entity-name",
        "ytcp-header #channel-title",
        "div[class*='channel-title']",
        "span[class*='channel-name']",
        "ytcp-entity-badge"
    ]

    LOGIN_BUTTONS: List[str] = [
        "a[href*='signin']",
        "a[aria-label*='Sign in']",
        "a[aria-label*='Oturum aç']",
        "button:has-text('Sign in')",
        "button:has-text('Oturum aç')"
    ]

    # 2. Upload Entry & Draft Wizard Triggers
    DRAFT_BANNER_SELECTORS: List[str] = [
        "div:has-text('Bu video taslak durumunda')",
        "div:has-text('This video is a draft')",
        "span:has-text('Bu video taslak durumunda')",
        "span:has-text('This video is a draft')",
        "ytcp-banner:has-text('taslak')",
        "ytcp-banner:has-text('draft')"
    ]

    EDIT_DRAFT_BUTTONS: List[str] = [
        "button:has-text('Taslağı düzenle')",
        "button:has-text('Edit draft')",
        "button:has-text('Continue editing')",
        "ytcp-button:has-text('Taslağı düzenle')",
        "ytcp-button:has-text('Edit draft')",
        "ytcp-button#edit-draft-button",
        "button[aria-label*='Taslağı düzenle']",
        "button[aria-label*='Edit draft']",
        "a:has-text('Taslağı düzenle')",
        "a:has-text('Edit draft')"
    ]

    WIZARD_STEPPER_SELECTORS: List[str] = [
        "ytcp-stepper",
        "div[role='tablist']",
        "tp-yt-paper-tab:has-text('Ayrıntılar')",
        "tp-yt-paper-tab:has-text('Details')",
        "tp-yt-paper-tab:has-text('Görünürlük')",
        "tp-yt-paper-tab:has-text('Visibility')",
        "div#step-badge",
        "ytcp-uploads-dialog"
    ]

    # --- Existing-draft resume (enter_existing_draft_wizard) -------------------
    # Kural 31: exactly TWO semantic strategies for the 'Taslağı düzenle' action --
    # (1) visible button text, (2) aria-label. Each strategy carries its own TR+EN
    # variants as one comma-grouped CSS selector, which Playwright treats as a single
    # "match any of these" query, so this remains 2 locator attempts, not 8.
    EDIT_DRAFT_BUTTON_STRATEGIES: List[str] = [
        "ytcp-button:has-text('Taslağı düzenle'), ytcp-button:has-text('Edit draft'), "
        "button:has-text('Taslağı düzenle'), button:has-text('Edit draft')",
        "button[aria-label*='Taslağı düzenle' i], button[aria-label*='Edit draft' i], "
        "ytcp-button[aria-label*='Taslağı düzenle' i], ytcp-button[aria-label*='Edit draft' i]",
    ]

    # The ONLY element that proves the real upload wizard is mounted. A normal
    # /video/<id>/edit page never contains this -- it has its own title/description
    # inputs, which is exactly why a title input must never be accepted as wizard proof.
    UPLOAD_WIZARD_DIALOG: str = "ytcp-uploads-dialog"

    # Stepper proof, always resolved SCOPED INSIDE UPLOAD_WIZARD_DIALOG (2 strategies).
    WIZARD_STEPPER_IN_DIALOG: List[str] = [
        "ytcp-stepper",
        "tp-yt-paper-tab, div[role='tablist']",
    ]

    CREATE_BUTTONS: List[str] = [
        "#create-icon",
        "#create-button",
        "ytcp-button#create-icon",
        "button[aria-label*='Create']",
        "button[aria-label*='Oluştur']",
        "ytcp-button:has-text('CREATE')",
        "ytcp-button:has-text('OLUŞTUR')"
    ]

    UPLOAD_MENU_ITEMS: List[str] = [
        "#text-item-0",
        "tp-yt-paper-item:has-text('Upload videos')",
        "tp-yt-paper-item:has-text('Video yükle')",
        "ytcp-text-menu tp-yt-paper-item",
        "a[href*='upload']"
    ]

    FILE_INPUT_SELECTORS: List[str] = [
        "input[type='file'][name='Filedata']",
        "input[type='file']",
        "#file-loader input[type='file']"
    ]

    # Video Link Elements (for immediate Video ID capture during upload)
    VIDEO_LINK_SELECTORS: List[str] = [
        "a.ytcp-video-info",
        "a[href*='youtu.be/']",
        "a[href*='youtube.com/shorts/']",
        "a[href*='youtube.com/watch']",
        "span.ytcp-video-info a",
        "#share-url",
        "a[aria-label*='Video bağlantısı']",
        "a[aria-label*='Video link']"
    ]

    # 3. Metadata Form Inputs
    TITLE_INPUTS: List[str] = [
        "#title-textarea #textbox",
        "ytcp-mention-input#title-textarea div[contenteditable='true']",
        "ytcp-social-suggestions-textbox#title-textarea div[contenteditable='true']",
        "#title-textarea div[contenteditable='true']",
        "ytcp-form-input-container#title textarea",
        "div[aria-label*='Title']",
        "div[aria-label*='Başlık']"
    ]

    DESCRIPTION_INPUTS: List[str] = [
        "#description-textarea #textbox",
        "ytcp-mention-input#description-textarea div[contenteditable='true']",
        "ytcp-social-suggestions-textbox#description-textarea div[contenteditable='true']",
        "#description-textarea div[contenteditable='true']",
        "ytcp-form-input-container#description textarea",
        "div[aria-label*='Description']",
        "div[aria-label*='Açıklama']"
    ]

    AUDIENCE_NOT_MADE_FOR_KIDS: List[str] = [
        "tp-yt-paper-radio-button[name='VIDEO_MADE_FOR_KIDS_NOT_MFK']",
        "#radioLabel:has-text('No, it\\'s not made for kids')",
        "#radioLabel:has-text('Hayır, çocuklara özel değil')",
        "tp-yt-paper-radio-button:has-text('No, it\\'s not made for kids')",
        "tp-yt-paper-radio-button:has-text('Hayır, çocuklara özel değil')"
    ]

    SHOW_MORE_BUTTONS: List[str] = [
        "ytcp-button#toggle-button",
        "#toggle-button",
        "button:has-text('Daha fazla göster')",
        "button:has-text('Show more')",
        "ytcp-button:has-text('DAHA FAZLA GÖSTER')",
        "ytcp-button:has-text('SHOW MORE')",
        "div:has-text('Daha fazla göster'):not(:has(div))"
    ]

    AI_DISCLOSURE_SECTION_CONTAINERS: List[str] = [
        "div.section:has-text('Değiştirilmiş içerik')",
        "div.section:has-text('Altered content')",
        "div.section:has-text('Değiştirilmiş veya sentetik')",
        "div.section:has-text('Synthetic content')",
        "div:has(.section-title:has-text('Değiştirilmiş içerik'))",
        "div:has(.section-title:has-text('Altered content'))"
    ]

    AI_DISCLOSURE_YES_RADIO: List[str] = [
        "tp-yt-paper-radio-button[name='ALTERED_CONTENT_YES']",
        "tp-yt-paper-radio-button[name='SYNTHETIC_CONTENT_YES']",
        "div.section:has-text('Değiştirilmiş içerik') tp-yt-paper-radio-button[name='ALTERED_CONTENT_YES']",
        "div.section:has-text('Altered content') tp-yt-paper-radio-button[name='ALTERED_CONTENT_YES']"
    ]

    AI_DISCLOSURE_NO_RADIO: List[str] = [
        "tp-yt-paper-radio-button[name='ALTERED_CONTENT_NO']",
        "tp-yt-paper-radio-button[name='SYNTHETIC_CONTENT_NO']",
        "div.section:has-text('Değiştirilmiş içerik') tp-yt-paper-radio-button[name='ALTERED_CONTENT_NO']",
        "div.section:has-text('Altered content') tp-yt-paper-radio-button[name='ALTERED_CONTENT_NO']"
    ]

    NEXT_BUTTONS: List[str] = [
        "#next-button",
        "ytcp-button#next-button",
        "ytcp-button:has-text('İleri')",
        "ytcp-button:has-text('Next')",
        "#next-button ytcp-button",
        "button[aria-label*='Next']",
        "button[aria-label*='İleri']"
    ]

    # 4. Visibility & Scheduling Tab
    SCHEDULE_ACCORDION_HEADERS: List[str] = [
        "#schedule-section",
        "#schedule-card",
        "tp-yt-paper-radio-button[name='SCHEDULE']",
        "#schedule-radio-button",
        "div#heading:has-text('Planlayın')",
        "div#heading:has-text('Schedule')",
        "div:has-text('Planlayın'):not(:has(div))",
        "div:has-text('Schedule'):not(:has(div))",
        "#second-container-checkbox-photos",
        "ytcp-visibility-card:has-text('Planlayın')",
        "ytcp-visibility-card:has-text('Schedule')",
        "button[aria-label*='Planlayın']",
        "button[aria-label*='Schedule']"
    ]

    SCHEDULE_RADIO_BUTTONS: List[str] = SCHEDULE_ACCORDION_HEADERS

    DATE_PICKER_INPUTS: List[str] = [
        "ytcp-datetime-picker #date-picker input",
        "ytcp-datetime-picker #datepicker-trigger input",
        "ytcp-datetime-picker #datepicker-trigger",
        "#datepicker-trigger input",
        "#datepicker-trigger",
        "input[aria-label*='Tarih']",
        "input[aria-label*='Date']",
        "input[aria-label*='Planlama tarihi']",
        "input[aria-label*='Schedule date']",
        "#date-picker input",
        "#date-picker"
    ]

    TIME_PICKER_INPUTS: List[str] = [
        "ytcp-time-of-day-picker input",
        "ytcp-datetime-picker #time-picker input",
        "ytcp-datetime-picker #time-of-day-trigger input",
        "#time-of-day-trigger input",
        "input[aria-label*='Saat']",
        "input[aria-label*='Time']",
        "input[aria-label*='Planlama saati']",
        "input[aria-label*='Schedule time']",
        "ytcp-form-input-container#time-of-day input",
        "#time-picker input",
        "#time-of-day-trigger",
        "#time-picker"
    ]

    TIME_DROPDOWN_ITEMS: List[str] = [
        "tp-yt-paper-item:has-text('19:30')",
        "tp-yt-paper-listbox tp-yt-paper-item:has-text('19:30')",
        "ytcp-time-of-day-picker tp-yt-paper-item:has-text('19:30')",
        "div[role='option']:has-text('19:30')"
    ]

    # Calendar Picker Dialog & Month Navigation (Excludes weekday rows)
    CALENDAR_DIALOGS: List[str] = [
        "tp-yt-paper-dialog#dialog",
        "ytcp-calendar",
        "ytcp-date-picker tp-yt-paper-dialog",
        "div[role='dialog']:has(ytcp-calendar)",
        "div.calendar-container"
    ]

    CALENDAR_MONTH_HEADERS: List[str] = [
        "ytcp-calendar #month-header",
        "ytcp-calendar .month-title",
        "ytcp-calendar div[class*='month-header']",
        "ytcp-calendar h2",
        "#month-header"
    ]

    CALENDAR_PREV_MONTH_BUTTONS: List[str] = [
        "ytcp-calendar #previous-month",
        "ytcp-calendar button[aria-label*='Önceki']",
        "ytcp-calendar button[aria-label*='Previous']",
        "#previous-month",
        "button[aria-label*='Önceki ay']"
    ]

    CALENDAR_NEXT_MONTH_BUTTONS: List[str] = [
        "ytcp-calendar #next-month",
        "ytcp-calendar button[aria-label*='Sonraki']",
        "ytcp-calendar button[aria-label*='Next']",
        "#next-month",
        "button[aria-label*='Sonraki ay']"
    ]

    CALENDAR_DAY_CELLS: List[str] = [
        "ytcp-calendar td:not(.is-disabled):not(.is-outside-month)",
        "ytcp-calendar div[role='gridcell']:not([aria-disabled='true'])",
        "ytcp-calendar .day-btn:not([disabled])",
        "ytcp-calendar button:not([disabled])"
    ]

    DATE_ERROR_INDICATORS: List[str] = [
        "div:has-text('Geçersiz Tarih')",
        "div:has-text('Geçersiz tarih')",
        "div:has-text('Invalid date')",
        "div:has-text('Invalid Date')",
        "ytcp-input-container[invalid]",
        "input[aria-invalid='true']",
        "#error-message:visible"
    ]

    TIME_ERROR_INDICATORS: List[str] = [
        "div:has-text('Geçersiz Saat')",
        "div:has-text('Geçersiz saat')",
        "div:has-text('Invalid time')",
        "div:has-text('Invalid Time')",
        "div:has-text('Gelecekte bir zaman seçin')",
        "div:has-text('Select a time in the future')",
        "#time-picker[invalid]"
    ]

    TIMEZONE_INDICATORS: List[str] = [
        "div:has-text('GMT+3')",
        "div:has-text('UTC+3')",
        "div:has-text('GMT+03:00')",
        "div:has-text('UTC+03:00')",
        "div:has-text('İstanbul')",
        "div:has-text('Istanbul')"
    ]

    # Distinct Final Schedule Action Button (bottom right)
    FINAL_SCHEDULE_BUTTONS: List[str] = [
        "#done-button:has-text('Planla')",
        "#done-button:has-text('Schedule')",
        "ytcp-button#done-button:has-text('Planla')",
        "ytcp-button#done-button:has-text('Schedule')",
        "ytcp-button:has-text('Planla')",
        "ytcp-button:has-text('Schedule')",
        "#done-button"
    ]

    SUBMIT_SCHEDULE_BUTTONS: List[str] = FINAL_SCHEDULE_BUTTONS

    DRAFT_CONTENT_ROWS: List[str] = [
        "ytcp-video-row",
        "div[role='row'][class*='video-row']",
        "tr[class*='video-row']",
        "ytcp-video-list-cell-video"
    ]

    CLOSE_MODAL_BUTTONS: List[str] = [
        "#close-button",
        "ytcp-button#close-button",
        "ytcp-button:has-text('Close')",
        "ytcp-button:has-text('Kapat')",
        "button[aria-label*='Close']",
        "button[aria-label*='Kapat']"
    ]

    # Informational "we're still checking your content" review notice (TR: "İçeriğinizi
    # kontrol etmeye devam ediyoruz" / "İçeriği tekrar gözden geçirmenizi öneririz").
    # This is NOT a failed schedule -- it must be safely dismissed (never treated as
    # fatal) without ever switching from schedule to publish-now.
    CONTENT_REVIEW_INFO_TEXT_MARKERS: List[str] = [
        "kontrol etmeye devam",
        "gözden geçirmenizi öneririz",
        "we're still checking",
        "we recommend you review"
    ]

    # Real DOM (user-supplied 2026-08-17):
    #   <ytcp-button><ytcp-button-shape>
    #     <button aria-label="Anladım" aria-disabled="false" tabindex="0">
    #       <div class="ytcpButtonShapeImpl__button-text-content">Anladım</div>
    #   </button></ytcp-button-shape></ytcp-button>
    # Kural 31: exactly 2 semantic strategies -- aria-label, then visible text.
    # aria-label is unambiguous here ("Anladım"/"Got it" is only ever the dismiss
    # button), so this is safe to click without a surrounding text precondition.
    CONTENT_REVIEW_INFO_DISMISS_BUTTONS: List[str] = [
        "button[aria-label='Anladım'], button[aria-label='Got it'], "
        "button[aria-label='Anladim'], ytcp-button[aria-label='Anladım']",
        "button:has-text('Anladım'), button:has-text('Got it'), "
        "ytcp-button:has-text('Anladım'), ytcp-button:has-text('Got it')",
    ]
