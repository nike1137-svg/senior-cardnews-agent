"""프롬프트에 비밀정보가 섞여 나가는 것을 막는 필터 (전역 규칙 9번).

Gemini 무료 티어는 입력이 학습에 쓰일 수 있다. 이 프로젝트가 다루는 것은
공개 뉴스·날씨뿐이지만, 도구 결과에 키가 섞여 들어올 여지를 코드로 막는다.

두 갈래로 거른다.
  1. 설정에 실제로 들어 있는 키 값 — 가장 확실하다
  2. 흔한 키 형태 (sk-..., gho_..., AIza..., Bearer ...)
"""

from __future__ import annotations

import re

from app.config import get_settings

MASK = "[비밀정보-가림]"

# 키처럼 생긴 문자열
_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"),        # OpenAI
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),    # GitHub
    re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}"),       # Google API
    re.compile(r"\btvly-[A-Za-z0-9_\-]{16,}"),      # Tavily
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{20,}"),
]

# 설정에서 읽어올 실제 비밀값 필드
_SECRET_FIELDS = (
    "gemini_api_key",
    "openai_api_key",
    "tavily_api_key",
    "line_channel_access_token",
)

_MIN_SECRET_LEN = 8  # 너무 짧은 값은 오탐이 나므로 건너뛴다


def _known_secrets() -> list[str]:
    s = get_settings()
    out = []
    for field in _SECRET_FIELDS:
        v = getattr(s, field, "") or ""
        if len(v) >= _MIN_SECRET_LEN:
            out.append(v)
    return out


def redact(text: str) -> str:
    if not text:
        return text
    for secret in _known_secrets():
        text = text.replace(secret, MASK)
    for pat in _PATTERNS:
        text = pat.sub(MASK, text)
    return text


def contains_secret(text: str) -> bool:
    """가려야 할 것이 있었는지 여부. 로그에 경고를 남길 때 쓴다."""
    return redact(text) != text
