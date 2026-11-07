import re

PATTERNS = [
    (re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"), "[EMAIL]"),
    (re.compile(r"(?<!\d)(?:\+?82[- .]?)?0?1[016789][- .]?\d{3,4}[- .]?\d{4}(?!\d)"), "[PHONE]"),
    (re.compile(r"\b(?:\d[ -]?){15}\d\b"), "[DEVICE_ID]"),
    (re.compile(r"\b(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b"), "[MAC]"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[IP]"),
    (re.compile(r"(?i)\b(?:serial|imei|imsi|android_id|device_id|token|password|ssid)\s*[:=]\s*[^\s,;]+"), "[IDENTIFIER]"),
]


def mask(text: str, serial: str | None = None) -> str:
    if serial:
        text = text.replace(serial, "[DEVICE_ID]")
    for pattern, replacement in PATTERNS:
        text = pattern.sub(replacement, text)
    return text
