"""수집 경로 전체에서 공통으로 사용하는 최소 개인정보 비식별화."""

from __future__ import annotations

import hashlib
import re


EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?:\+82[- ]?)?0?1[0-9][ -]?\d{3,4}[ -]?\d{4}")
RESIDENT_ID = re.compile(r"\b\d{6}[- ]?[1-4]\d{6}\b")


def mask_text(value: str) -> str:
    value = EMAIL.sub("[EMAIL]", value)
    value = PHONE.sub("[PHONE]", value)
    return RESIDENT_ID.sub("[RESIDENT_ID]", value)


def pseudonymize(value: str, namespace: str = "author") -> str:
    """원본 식별자를 보존하지 않는 결정적 참조값을 만든다."""
    digest = hashlib.sha256(f"{namespace}:{value}".encode()).hexdigest()[:20]
    return f"{namespace}:{digest}"


def sanitize_event(payload: dict) -> dict:
    sanitized = dict(payload)
    sanitized["text"] = mask_text(str(payload.get("text", "")))
    sanitized["author_ref"] = pseudonymize(str(payload.get("author_ref", "unknown")))
    return sanitized
