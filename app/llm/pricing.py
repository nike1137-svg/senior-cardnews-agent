"""모델별 단가표 (1,000,000 토큰당 USD).

출처는 D-010 의 조사표. 값이 바뀌면 여기만 고친다.
모르는 모델은 **가장 비싼 값**으로 계산한다 — 과소평가해서 상한을 그냥 지나치는 것보다
과대평가해서 일찍 멈추는 쪽이 안전하다.
"""

from __future__ import annotations

# (provider, model) -> (입력 단가, 출력 단가)
PRICES: dict[tuple[str, str], tuple[float, float]] = {
    # OpenAI — 기관 지급 크레딧 $5
    ("openai", "gpt-5-mini"): (0.25, 2.00),
    ("openai", "gpt-5-nano"): (0.05, 0.40),
    ("openai", "gpt-5"): (1.25, 10.00),
}

# 모르는 모델에 적용할 보수적 단가
FALLBACK_PRICE = (1.25, 10.00)

# Gemini 는 무료 티어로 쓴다. 한도를 넘으면 과금이 아니라 429 가 난다.
# 그래서 달러가 아니라 **호출 수**로 막는다 (MAX_LLM_CALLS_PER_RUN / _PER_DAY).
# 결제를 붙이게 되면 이 값을 실제 단가로 바꿔야 한다.
FREE_TIER_PROVIDERS = frozenset({"gemini"})


def price_of(provider: str, model: str) -> tuple[float, float]:
    hit = PRICES.get((provider, model))
    if hit is not None:
        return hit
    if provider in FREE_TIER_PROVIDERS:
        return (0.0, 0.0)
    return FALLBACK_PRICE


def estimate_usd(provider: str, model: str, prompt_tokens: int, completion_tokens: int) -> float:
    p_in, p_out = price_of(provider, model)
    return (prompt_tokens * p_in + completion_tokens * p_out) / 1_000_000
