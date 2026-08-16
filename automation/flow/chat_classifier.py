"""
Agent chat message classification and duration question classifier.
Accurately categorizes Google Flow Agent responses (TR and EN) and prevents false-positive
duration question loops.
"""
from enum import Enum
import re

class AgentMessageType(Enum):
    DURATION_QUESTION = "duration_question"
    GENERATION_PROGRESS = "generation_progress"
    MEDIA_READY_MESSAGE = "media_ready_message"
    GENERIC_INFO = "generic_info"
    ERROR = "error"
    UNKNOWN = "unknown"

def is_duration_followup_question(text: str) -> bool:
    """
    Strictly classify whether a message is an interactive duration selection question.
    Returns True ONLY if:
    1. Contains duration/süre concept
    2. Contains question/selection intent (e.g. 'hangi süreyi', 'which duration', 'tercih edersiniz')
    3. Contains supported options (e.g. 4 saniye, 6 saniye, 8 saniye)
    4. Does NOT match completion/ready or purely informative progress phrases.
    """
    clean_text = text.strip().lower()

    # Disqualify completion or progress phrases immediately
    disqualification_phrases = [
        "hazır",
        "hazir",
        "ready",
        "tamamlandı",
        "tamamlandi",
        "completed",
        "üretildi",
        "uretildi",
        "generated",
        "hazırlanıyor",
        "hazirlaniyor",
        "devam ediyor",
        "in progress",
        "processing"
    ]
    if any(dq in clean_text for dq in disqualification_phrases):
        return False

    # Question/selection intent patterns
    selection_intent_patterns = [
        r'(?:hangi|which)\s+s[uü]reyi',
        r'(?:hangi|which)\s+duration',
        r'duration\s+do\s+you\s+prefer',
        r's[uü]reyi\s+(?:se[cç]in|belirleyin|tercih\s+edin|se[cç]iniz)',
        r'choose\s+a\s+duration',
        r'select\s+(?:the\s+)?(?:video\s+)?duration',
        r'desteklemiyor.*?se[cç]enek',
        r'does\s+not\s+support.*?option',
        r's[uü]reyi\s+a[sş]a[gğ][iı]daki\s+se[cç]eneklerden',
        r'adjust\s+the\s+duration\s+to\s+one\s+of'
    ]

    has_intent = any(re.search(pat, clean_text, re.IGNORECASE) for pat in selection_intent_patterns)

    # Option enumeration check
    has_options = bool(
        re.search(r'(?:4|6|8|10)\s*(?:saniye|seconds|sec|sn)', clean_text) and
        re.search(r'(?:desteklememektedir|desteklemiyor|does not support|prefer|tercih|seçenek|option)', clean_text)
    )

    return has_intent or has_options

def classify_agent_message(text: str) -> AgentMessageType:
    """Classify agent chat message text into discrete semantic types."""
    if not text or not text.strip():
        return AgentMessageType.UNKNOWN

    clean_text = text.strip().lower()

    if is_duration_followup_question(clean_text):
        return AgentMessageType.DURATION_QUESTION

    # Media ready indicators
    ready_patterns = [
        r'videonuz\s+haz[ıi]r',
        r'video\s+is\s+ready',
        r'your\s+video\s+is\s+ready',
        r'ba[sş]ar[ıi]yla\s+(?:tamamland[ıi]|üretildi|olu[sş]turuldu)',
        r'successfully\s+(?:generated|completed|created)',
        r'ekran[ıi]n[ıi]zdan\s+oynatabilirsiniz',
        r'sol\s+taraftaki\s+panelde.*?izleyebilirsiniz',
        r'can\s+watch\s+it\s+in\s+the\s+left\s+panel',
        r'olu[sş]turulan\s+video\s+panelinizde\s+haz[ıi]r'
    ]
    if any(re.search(pat, clean_text, re.IGNORECASE) for pat in ready_patterns):
        return AgentMessageType.MEDIA_READY_MESSAGE

    # Generation progress indicators
    progress_patterns = [
        r'haz[ıi]rlan[ıi]yor',
        r'üretim\s+devam\s+ediyor',
        r'birazdan\s+haz[ıi]r\s+olacakt[ıi]r',
        r'is\s+still\s+being\s+generated',
        r'is\s+being\s+processed',
        r'generation\s+is\s+in\s+progress',
        r'k[ıi]sa\s+bir\s+süre\s+sonra\s+tekrar\s+kontrol\s+edebilirsiniz',
        r'check\s+back\s+in\s+a\s+(?:couple\s+of\s+)?minutes',
        r'scheduled\s+your.*?video',
        r'queued\s+and\s+is\s+waiting'
    ]
    if any(re.search(pat, clean_text, re.IGNORECASE) for pat in progress_patterns):
        return AgentMessageType.GENERATION_PROGRESS

    # Error indicators
    error_patterns = [
        r'hata\s+olu[sş]tu',
        r'an\s+error\s+occurred',
        r'kredi\s+yetersiz',
        r'out\s+of\s+credits',
        r'failed\s+to\s+generate',
        r'üretilemedi'
    ]
    if any(re.search(pat, clean_text, re.IGNORECASE) for pat in error_patterns):
        return AgentMessageType.ERROR

    return AgentMessageType.GENERIC_INFO
