"""두뇌 LLM 어댑터 — 2단계에서 채운다.

base.py    LLMAdapter 추상 (도구 스키마를 넘기고 ToolCall 또는 텍스트를 받는다)
gemini.py  Gemini 2.5 Flash  (기본, 무료)
openai.py  GPT-5 mini        (비교·시연, 기관 크레딧 $5)
budget.py  호출 수·달러 카운터. 상한 초과 시 앱이 먼저 멈춘다 (D-010)
redact.py  프롬프트에 키·토큰이 섞이지 않게 거르는 필터 (9번 규칙)
"""
