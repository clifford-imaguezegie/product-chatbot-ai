"""Small, explicit controls for a public-facing portfolio demonstration."""
from __future__ import annotations
import hmac
import re
import threading
import time
from collections import deque
from urllib.parse import urlparse

INJECTION_PATTERNS = re.compile(
    r"(?i)(ignore (?:all |any |your |the )?(?:previous |prior |system |developer )?instructions|"
    r"reveal (?:the |your )?(?:system prompt|api key|secret|credentials)|"
    r"you are now (?:a |the )?(?:system|developer)|"
    r"<\s*/?\s*(?:system|developer|assistant)\s*>|"
    r"begin (?:system|developer) prompt|exfiltrat(?:e|ion))"
)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_text(value: object, limit: int = 300) -> str:
    """Normalize untrusted catalog text; suppress overt instruction-shaped content."""
    if value is None:
        return ""
    s = _CONTROL.sub(" ", str(value))[:limit].strip()
    return "[Catalog text omitted by safety filter]" if INJECTION_PATTERNS.search(s) else s


def is_sensitive_request(text: str) -> bool:
    """Block overt credential or system-instruction extraction requests before LLM use."""
    return bool(INJECTION_PATTERNS.search(text or ""))


def verify_code(entered: str, expected: str) -> bool:
    return bool(expected) and hmac.compare_digest(entered.encode(), expected.encode())


def safe_catalog_image(url: object) -> str | None:
    if not isinstance(url, str) or len(url) > 700:
        return None
    p = urlparse(url)
    # Browser-side image rendering only, never use these URLs for backend requests.
    try:
        if p.scheme != "https" or p.username or p.password or p.port:
            return None
    except ValueError:
        return None
    if p.hostname not in {"cdn.dummyjson.com", "dummyjson.com", "images.unsplash.com", "i.dummyjson.com"}:
        return None
    return url


class SlidingLimit:
    """Best-effort in-process request limiter; not a distributed billing guarantee."""
    def __init__(self):
        self._lock = threading.Lock()
        self._events = deque()

    def accept(self, max_calls: int, window_sec: int, now: float | None = None) -> bool:
        stamp = time.monotonic() if now is None else now
        with self._lock:
            while self._events and self._events[0] <= stamp - window_sec:
                self._events.popleft()
            if len(self._events) >= max_calls:
                return False
            self._events.append(stamp)
            return True
