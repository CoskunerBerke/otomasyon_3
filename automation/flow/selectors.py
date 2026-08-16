"""
Centralized UI Selectors and state definitions for Google Flow automation.
Supports bilingual TR/EN interfaces, settings configuration, and follow-up question detection.
"""
from enum import Enum
from typing import List

class FlowPageState(Enum):
    HOME = "home"
    PROJECT_EDITOR = "project_editor"
    AUTH_REQUIRED = "auth_required"
    UNKNOWN = "unknown"

class FlowError(Exception):
    """Base exception for Google Flow automation."""
    pass

class FlowUIChangedError(FlowError):
    """Raised when critical UI elements cannot be found due to interface changes (Pre-submit error)."""
    pass

class UserActionRequiredError(FlowError):
    """Raised when human intervention is needed (Sign-in, CAPTCHA, 2FA)."""
    pass

class InsufficientCreditsError(FlowError):
    """Raised when user has run out of Flow generation credits."""
    pass

class GenerationTimeoutError(FlowError):
    """Raised when video generation exceeds timeout limit (Post-submit error)."""
    pass

class RealGenerationDisabled(FlowError):
    """Raised/signaled when allow_real_generation is false (Test Guard)."""
    pass

class GenerationStateUncertain(FlowError):
    """Raised when submit click happened but start was unconfirmed; prevents dangerous duplicate clicks."""
    pass

class FlowSelectors:
    """Multi-tier selector patterns for Google Flow."""

    # Sign-in & Security challenges (if seen, prompt USER_ACTION_REQUIRED)
    AUTH_CHALLENGE_PATTERNS: List[str] = [
        "text='Sign in'",
        "text='Oturum açın'",
        "text='Verify it\\'s you'",
        "text='Doğrulayın'",
        "iframe[src*='recaptcha']",
        "iframe[src*='challenges.cloudflare']",
        "div#captcha",
        "div.g-recaptcha"
    ]

    # Home page New Project button (TR / EN variations)
    NEW_PROJECT_BUTTON_SELECTORS: List[str] = [
        "button:has-text('Yeni proje')",
        "button:has-text('New project')",
        "button:has-text('+ Yeni proje')",
        "button:has-text('+ New project')",
        "button:has([data-icon='add_2'])",
        "button:has([data-icon='add'])",
        "button:has-text('Yeni')",
        "button:has-text('New')",
        "[aria-label*='Yeni proje' i]",
        "[aria-label*='New project' i]"
    ]

    # Settings / Ayarlar button (tune icon next to prompt composer)
    SETTINGS_BUTTON_SELECTORS: List[str] = [
        "button:has(i.google-symbols:text-is('tune'))",
        "button:has(i:text-is('tune'))",
        "button:has-text('Ayarlar')",
        "button:has-text('Settings')",
        "[aria-label*='Ayarlar' i]",
        "[aria-label*='Settings' i]"
    ]

    # Settings panel radio / controls
    APPROVAL_NEVER_SELECTORS: List[str] = [
        "button[role='radio'][value='AUTO_APPROVE']",
        "button[role='radio']:has-text('Never')",
        "button[role='radio']:has-text('Hiçbir zaman')",
        "div:has-text('Never'):has([role='radio'])",
        "div:has-text('Hiçbir zaman'):has([role='radio'])"
    ]

    APPROVAL_ALWAYS_SELECTORS: List[str] = [
        "button[role='radio'][value='ALWAYS_ASK']",
        "button[role='radio']:has-text('Always')",
        "button[role='radio']:has-text('Her zaman')"
    ]

    SAVE_SETTINGS_BUTTON_SELECTORS: List[str] = [
        "button:has-text('Save')",
        "button:has-text('Kaydet')"
    ]

    # Prompt text entry area (Slate.js contenteditable and textarea fallbacks)
    PROMPT_INPUT_SELECTORS: List[str] = [
        "div[data-slate-editor='true']",
        "div[role='textbox'][contenteditable='true']",
        "[contenteditable='true'][role='textbox']",
        "div[contenteditable='true']",
        "textarea[placeholder*='prompt' i]",
        "textarea[placeholder*='describe' i]",
        "textarea[aria-label*='prompt' i]",
        "textarea[aria-label*='Enter prompt' i]",
        "textarea"
    ]

    # Generate / Create button in Project Editor
    GENERATE_BUTTON_SELECTORS: List[str] = [
        "button:has(i:text-is('arrow_forward'))",
        "button:has(i.google-symbols:text-is('arrow_forward'))",
        "button[aria-disabled='false']:has-text('Oluştur')",
        "button[aria-disabled='false']:has-text('Generate')",
        "button:has-text('Oluştur')",
        "button:has-text('Generate')",
        "button:has-text('Create')",
        "button:has-text('Submit')",
        "button:has-text('Üret')",
        "button:has([data-icon='arrow_forward'])",
        "button[aria-label*='Generate' i]",
        "button[aria-label*='Oluştur' i]"
    ]

    # Aspect ratio & settings selectors
    RATIO_9_16_SELECTORS: List[str] = [
        "button:has-text('9:16')",
        "button[aria-label*='9:16' i]",
        "div[role='radio']:has-text('9:16')",
        "button[data-ratio='9:16']",
        "[data-value='9:16']"
    ]

    # Insufficient credits / Limit reached warnings
    CREDIT_WARNING_SELECTORS: List[str] = [
        "text=/insufficient credits/i",
        "text=/out of credits/i",
        "text=/kredi yetersiz/i",
        "text=/limit reached/i",
        "text=/quota exceeded/i"
    ]

    # Generation in-progress indicators
    GENERATING_INDICATORS: List[str] = [
        "[aria-label*='Generating' i]",
        "[role='progressbar']",
        "div.spinner",
        "div[class*='progress' i]",
        "text=/Generating/i",
        "text=/Processing/i",
        "text=/Üretiliyor/i"
    ]

    # Completed video output cards & download triggers
    DOWNLOAD_BUTTON_SELECTORS: List[str] = [
        "button[aria-label*='Download' i]",
        "a[download]",
        "button:has-text('Download')",
        "button:has-text('İndir')",
        "button[title*='Download' i]",
        "svg[data-icon='download']"
    ]
