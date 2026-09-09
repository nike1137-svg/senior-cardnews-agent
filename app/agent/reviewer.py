"""검토 에이전트 (⭐확장5) — 만든 쪽과 검사하는 쪽을 나눈다.

**왜 나누나**
카드를 만든 에이전트에게 "잘 만들었니?" 를 물으면 대체로 잘 만들었다고 답한다.
자기가 쓴 문장을 자기가 채점하는 셈이라, 날짜를 틀리게 적었어도 그대로 넘어간다.
루브릭이 지적한 *"작업을 끝냈다고 말하는 것과 실제 결과물이 만들어진 것은 다르다"* 를
구조로 푸는 방법이 역할을 나누는 것이다.

검토자는 카드를 만들지 않는다. **트집만 잡는다.** 시스템 프롬프트부터 다르다.

**무한 반려를 막는 장치**
검토자가 계속 반려하면 루프가 안 끝난다. 그래서 반려 상한을 2회로 두고,
넘으면 사람에게 넘긴다 (PRD 3장 종료 조건).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.agent import state
from app.llm import Message, ToolSpec, get_adapter
from app.llm.budget import BudgetExceeded
from app.tools.base import Failure, ToolResult, log_call

MAX_REJECTS = 2

SYSTEM = """\
너는 시니어용 카드뉴스를 **검사하는** 사람이다. 만드는 사람이 아니다.
너의 일은 트집을 잡는 것이다. 좋게 봐주지 마라.

검사 항목
1. 날짜·수치가 근거 자료와 일치하는가. 근거에 없는 숫자를 지어내지 않았는가
2. 시니어가 못 알아들을 표현이 남았는가 (외래어·전문용어·줄임말)
3. 날짜를 "다음 주" 처럼 모호하게 쓰지 않았는가. "9월 15일 월요일" 처럼 명시했는가
4. 한 카드에 메시지가 하나인가. 두 가지를 욱여넣지 않았는가
5. 의학적 진단이나 단정적인 조언으로 읽힐 표현이 있는가

판정 기준
- 위 항목 중 하나라도 **분명한 위반**이 있으면 reject
- 취향 문제(더 예쁘게, 더 길게)로는 reject 하지 마라
- 애매하면 pass. 검사자가 까다로우면 아무것도 못 만든다

reject 할 때는 **몇 번 카드의 어느 문장이 왜 문제인지** 구체적으로 적어라.
"전반적으로 아쉽다" 같은 말은 쓰지 마라.
"""

VERDICT = ToolSpec(
    name="verdict",
    description="검토 결과를 낸다. 반드시 이 도구로만 답한다.",
    parameters={
        "type": "object",
        "properties": {
            "passed": {"type": "boolean", "description": "통과면 true, 고쳐야 하면 false"},
            "problems": {
                "type": "array",
                "description": "고쳐야 할 점. 통과면 빈 배열.",
                "items": {
                    "type": "object",
                    "properties": {
                        "card_no": {"type": "integer", "description": "몇 번째 카드인가"},
                        "rule": {"type": "string",
                                 "description": "어긴 항목 (사실오류 / 어려운말 / 모호한날짜 / 메시지둘 / 단정적조언)"},
                        "quote": {"type": "string", "description": "문제가 되는 문장 그대로"},
                        "fix": {"type": "string", "description": "어떻게 고치면 되는지"},
                    },
                    "required": ["card_no", "rule", "quote", "fix"],
                },
            },
            "summary": {"type": "string", "description": "한 줄 요약"},
        },
        "required": ["passed", "summary"],
    },
)


@dataclass
class Review:
    passed: bool
    summary: str = ""
    problems: list[dict] = field(default_factory=list)
    rejects: int = 0
    escalated: bool = False       # 상한을 넘어 사람에게 넘겼는가

    @property
    def label(self) -> str:
        return "통과" if self.passed else f"반려 {len(self.problems)}건"


def _rule_to_label(rule: str) -> Failure:
    return {
        "사실오류": Failure.FACT_ERROR,
        "어려운말": Failure.HARD_WORDS,
        "모호한날짜": Failure.FACT_ERROR,
        "메시지둘": Failure.HARD_WORDS,
        "단정적조언": Failure.HALLUCINATION,
    }.get(rule, Failure.FACT_ERROR)


async def review_cards(run_id: str, cards: list[dict], evidence: str,
                       step_no: int, rejects_so_far: int = 0) -> Review:
    """카드 문구를 검사한다. 만든 에이전트와 다른 역할·다른 프롬프트로 부른다."""
    run = state.get_run(run_id)
    adapter = get_adapter(provider=run.provider or None, model=run.model or None, run_id=run_id)

    body = [
        "아래는 만들어진 카드뉴스 5장의 문구다. 검사해라.",
        "",
        "[수집한 근거]",
        evidence[:2000] or "(근거 자료가 비어 있다. 이 경우 숫자·날짜가 있으면 특히 의심해라)",
        "",
        "[카드]",
        json.dumps(cards, ensure_ascii=False, indent=2)[:4000],
    ]

    try:
        result = await adapter.chat(
            [Message(role="system", content=SYSTEM),
             Message(role="user", content="\n".join(body))],
            tools=[VERDICT],
        )
    except BudgetExceeded:
        # 검토를 못 했다고 카드를 버리지 않는다. 사람 검수로 넘긴다.
        rv = Review(passed=True, summary="검토 예산 초과 — 사람 검수로 넘김", rejects=rejects_so_far)
        log_call(run_id, step_no, "검토에이전트", "예산 초과", {},
                 ToolResult(ok=True, summary=rv.summary))
        return rv

    call = next((c for c in result.tool_calls if c.name == VERDICT.name), None)
    if call is None:
        rv = Review(passed=True, summary="검토자가 판정을 내지 않음 — 사람 검수로 넘김",
                    rejects=rejects_so_far)
        log_call(run_id, step_no, "검토에이전트", "판정 없음", {},
                 ToolResult(ok=True, summary=rv.summary))
        return rv

    args = call.arguments
    passed = bool(args.get("passed"))
    problems = list(args.get("problems") or [])
    summary = (args.get("summary") or "").strip()
    rejects = rejects_so_far + (0 if passed else 1)

    escalated = False
    if not passed and rejects > MAX_REJECTS:
        # 검토자가 계속 반려해 루프가 안 끝나는 것을 막는다 (PRD 3장)
        passed, escalated = True, True
        summary = f"반려 {rejects}회 — 상한({MAX_REJECTS})을 넘어 사람 검수로 넘김. {summary}"

    detail = summary
    if problems:
        detail += " :: " + "; ".join(
            f"카드{p.get('card_no','?')} [{p.get('rule','?')}] {str(p.get('quote',''))[:40]}"
            for p in problems[:4])

    log_call(
        run_id, step_no, "검토에이전트",
        "만든 쪽과 검사하는 쪽을 나눠 문구를 검증",
        {"cards": len(cards), "rejects_so_far": rejects_so_far},
        ToolResult(ok=passed, summary=detail[:600],
                   error_label=None if passed else _rule_to_label(
                       (problems[0].get("rule") if problems else "") or "")),
    )
    return Review(passed=passed, summary=summary, problems=problems,
                  rejects=rejects, escalated=escalated)
