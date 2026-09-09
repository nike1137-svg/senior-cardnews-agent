"""에이전트 루프 (D-007: 직접 구현).

    목표 → 계획 → 도구 호출 → 결과 관찰 → **다음 행동 결정** → 반복

파이프라인이 아니다. 매 반복마다 모델이 관찰 결과를 보고 셋 중 하나를 고른다.

    ① 도구를 부른다      ② 사람에게 묻는다      ③ 이 단계를 끝낸다

종료 조건이 없으면 무한히 돈다. 네 가지로 막는다.
    단계별 재시도 3회 · 전체 반복 30회 · 전체 10분 · 비용/호출 상한(어댑터가 막음)
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from app.agent import reviewer, state
from app.config import get_settings
from app.llm import Message, ToolSpec, get_adapter
from app.llm.budget import BudgetExceeded
from app.tools import registry, run_tool

# 관찰 요약을 컨텍스트에 실을 때의 길이 상한.
# 전부 300 자로 자르면 web_search 의 링크가 통째로 사라진다. 그러면 모델은
# URL 을 본 적이 없게 되고, 다음 단계에서 원문을 열 수가 없다.
OBS_CAP = {"web_search": 1500, "fetch_article": 900}
OBS_CAP_DEFAULT = 300
from app.tools.base import Failure, OnFail, log_call, ToolResult

# ── 루프 제어용 도구 ────────────────────────────────────────
# 실제 작업 도구가 아니라 '다음 행동'을 표현하는 수단이다.
ASK_HUMAN = ToolSpec(
    name="ask_human",
    description=(
        "사람에게 물어보고 답을 기다린다. 되돌리기 어려운 결정, 취향이 갈리는 선택, "
        "자료가 부족해 방향을 정해야 할 때 쓴다. 추측으로 진행하지 말 것. "
        "질문은 짧게, 선택지는 사람이 고르기 쉽게 3~5개로 준다."
    ),
    parameters={
        "type": "object",
        "properties": {
            "question_id": {"type": "string",
                            "description": "질문 구분용 짧은 영문 id. 예) pick-news, approve-storyboard"},
            "question": {"type": "string", "description": "사람에게 보여줄 질문 한 문장"},
            "options": {"type": "array", "items": {"type": "string"},
                        "description": "고를 수 있는 선택지"},
            "multi_select": {"type": "boolean", "description": "여러 개를 고를 수 있는가",
                             "default": False},
        },
        "required": ["question_id", "question"],
    },
)

FINISH_STEP = ToolSpec(
    name="finish_step",
    description=(
        "지금 단계의 목표를 달성했다고 판단되면 호출해 다음 단계로 넘어간다. "
        "무엇을 얻었는지 한 줄로 요약해 남긴다. 아직 부족하면 호출하지 말고 도구를 더 쓴다."
    ),
    parameters={
        "type": "object",
        "properties": {"summary": {"type": "string", "description": "이 단계에서 얻은 것 요약"}},
        "required": ["summary"],
    },
)

SYSTEM = """\
너는 시니어(60~80대)에게 보낼 생활정보 카드뉴스를 만드는 에이전트다.

지켜야 할 것
- 한 카드에 메시지는 하나만. 짧고 쉬운 우리말로 쓴다
- 외래어·전문용어를 쓰지 않는다. 풀어서 쓴다
- 날짜는 반드시 명시한다. "다음 주" 가 아니라 "9월 15일 월요일"
- 검색 요약만 보고 사실로 확정하지 않는다. fetch_article 로 원문을 열어 대조한다
- 확인된 사실 / 발표자 주장 / 미확인 을 구분한다. 미확인을 사실처럼 쓰지 않는다
- 되돌리기 어려운 일(발송)은 반드시 사람의 승인을 받는다

행동 방식
- 매번 지금까지의 관찰을 보고 다음 행동 하나를 고른다
- 도구를 부르거나, ask_human 으로 사람에게 묻거나, finish_step 으로 단계를 끝낸다
- 추측으로 메우지 말고, 모르면 사람에게 묻는다
"""


class Stopped(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _wall_seconds(run: state.Run) -> float:
    """시작부터 지금까지의 벽시계 시간. 참고용으로만 쓴다."""
    started = datetime.strptime(run.started_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - started).total_seconds()


class AgentLoop:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.settings = get_settings()

    # ── 종료 조건 ───────────────────────────────────────────
    def _check_limits(self, run: state.Run) -> None:
        s = self.settings
        if run.loop_count >= s.max_loop_iterations:
            raise Stopped(f"전체 반복 상한 {s.max_loop_iterations}회 도달")
        # 사람이 답을 기다린 시간은 빼고 잰다. 벽시계로 재면 담당자가
        # 자리를 비운 사이 상한에 걸려 버린다.
        secs = run.active_ms / 1000
        if secs > s.max_run_seconds:
            raise Stopped(f"에이전트 작업 시간 상한 {s.max_run_seconds}초 초과 ({int(secs)}초)")

    # ── 모델에게 줄 재료 ────────────────────────────────────
    def _context(self, run: state.Run, phase: dict) -> list[Message]:
        obs = state.observations(self.run_id)
        answered = state.answers_of(self.run_id)

        lines = [f"주제: {run.topic}", f"대상 지역: {run.region or '지정 없음'}",
                 f"현재 단계: {phase['no']}. {phase['name']}",
                 f"이 단계의 목표: {phase['goal']}"]

        if answered:
            lines.append("\n사람이 답한 것:")
            for a in answered:
                lines.append(f"  - {a['question']} → {a['answer']}")

        if obs:
            lines.append("\n지금까지의 관찰(도구 호출 결과):")
            for o in obs:
                mark = "성공" if o["ok"] else f"실패({o['error_label'] or '?'})"
                cap = OBS_CAP.get(o["tool_name"], OBS_CAP_DEFAULT)
                lines.append(f"  - [{o['tool_name']}] {mark} {o['duration_ms']}ms :: "
                             f"{(o['output_summary'] or '')[:cap]}")

            # 같은 도구를 몇 번 불렀는지 알려준다.
            # 이걸 안 주면 모델이 검색어만 바꿔 가며 계속 검색한다 (실제로 12회 반복했다).
            #
            # **단계 안에서만 센다.** 실행 전체로 세면 앞 단계에서 3회를 넘긴 기록이
            # 뒤 단계까지 따라와, 엉뚱한 단계에서 "그만하고 finish_step 하라"는 경고가
            # 뜬다. 심층 검증 단계가 원문을 열기도 전에 종료된 원인이었다 (D-023).
            counts: dict[str, int] = {}
            for o in obs:
                if o["step_no"] == phase["no"]:
                    counts[o["tool_name"]] = counts.get(o["tool_name"], 0) + 1
            if counts:
                lines.append("")
                lines.append("이 단계에서 부른 횟수: "
                             + ", ".join(f"{k} {v}회" for k, v in counts.items()))
                over = [k for k, v in counts.items() if v >= 3]
                if over:
                    lines.append(
                        f"  경고: 이 단계에서 {', '.join(over)} 를 이미 3회 이상 불렀다. "
                        "같은 도구를 더 부르지 말고 지금 있는 자료로 판단해 "
                        "finish_step 으로 넘어가거나 ask_human 으로 사람에게 물어라.")
        else:
            lines.append("\n아직 도구를 부른 적이 없다.")

        if phase["gate"]:
            # 앞 단계에서 받은 답을 이 단계의 승인으로 쓰면 개입 지점이 새어나간다.
            # 그래서 "이 단계에서 물은 질문" 만 근거로 삼는다 (D-023).
            g = state.gate_state(self.run_id, phase["no"])
            if g is None:
                lines.append(
                    "\n이 단계는 사람이 결정해야 하는 단계다. "
                    "**이 단계에서는 아직 아무것도 묻지 않았다.** "
                    "다른 단계에서 받은 답은 이 단계의 승인으로 쓸 수 없다. "
                    "먼저 ask_human 을 호출해 물어라. finish_step 을 부르지 마라.")
            elif g["answered"]:
                lines.append(
                    f"\n이 단계에서 물은 것에 답을 받았다. "
                    f"질문: {g['question']} → 답: {g['answer']} "
                    "그 답을 반영하고 finish_step 으로 넘어가라.")
            else:
                lines.append(
                    "\n이 단계의 질문에 아직 답이 오지 않았다. 사람을 기다려야 한다.")

        return [Message(role="system", content=SYSTEM),
                Message(role="user", content="\n".join(lines))]

    def _tools(self, phase: dict) -> list[ToolSpec]:
        return [*registry.specs(phase["tools"]), ASK_HUMAN, FINISH_STEP]

    # ── 한 번의 반복 ────────────────────────────────────────
    async def tick(self) -> dict:
        """한 바퀴 돈다. 걸린 시간은 '에이전트가 일한 시간'에만 더한다."""
        t0 = time.perf_counter()
        try:
            return await self._tick()
        finally:
            state.add_active_ms(self.run_id, int((time.perf_counter() - t0) * 1000))

    async def _tick(self) -> dict:
        run = state.get_run(self.run_id)
        if run is None:
            raise Stopped("실행을 찾을 수 없다")
        if run.status == "waiting_for_user":
            return {"action": "waiting", "question": state.open_question(self.run_id)}

        self._check_limits(run)

        step = state.current_step(self.run_id)
        if step is None:
            state.set_status(self.run_id, "done")
            return {"action": "done"}

        phase = state.PHASE_BY_NO[step["step_no"]]
        state.start_step(self.run_id, phase["no"])
        state.bump_loop(self.run_id)

        # 실행에 기록된 제공자·모델을 쓴다. 설정 기본값을 쓰면 세팅 비교가 불가능하다.
        adapter = get_adapter(provider=run.provider or None,
                              model=run.model or None,
                              run_id=self.run_id)
        try:
            result = await adapter.chat(self._context(run, phase), tools=self._tools(phase))
        except BudgetExceeded as exc:
            raise Stopped(f"비용·호출 상한: {exc}") from exc
        except Exception as exc:  # noqa: BLE001
            # 예외로 죽지 않고 '중단'으로 남긴다. 진행분이 보존되고 사람이 다시 이어갈 수 있다.
            raise Stopped(f"LLM 호출 실패: {type(exc).__name__} — {str(exc)[:180]}") from exc

        if not result.tool_calls:
            # 아무 행동도 안 고른 경우. 재시도 상한을 세어 무한 루프를 막는다.
            tries = state.bump_retry(self.run_id, phase["no"])
            log_call(self.run_id, phase["no"], "판단", "행동을 고르지 못함", {},
                     ToolResult(ok=False, summary=(result.text or "")[:300],
                                error_label=Failure.GAVE_UP))
            if tries > self.settings.max_retry_per_step:
                raise Stopped(f"{phase['name']} 단계에서 재시도 {tries}회 — 사람에게 넘긴다")
            return {"action": "retry", "step": phase["name"], "tries": tries}

        call = result.tool_calls[0]

        if call.name == ASK_HUMAN.name:
            # 질문에도 상한을 둔다. 재시도 상한(3회)은 실패에만 걸리고 질문은 무제한이었다.
            # 카드 합성 단계에서 같은 것을 세 번 물어 반복 예산을 3회 태운 적이 있다.
            # 사람을 부르는 것 자체는 좋은 행동이지만, 같은 자리를 맴돌면 완주를 막는다.
            asked_here = sum(1 for o in state.observations(self.run_id)
                             if o["step_no"] == phase["no"] and o["tool_name"] == ASK_HUMAN.name)
            if asked_here >= self.settings.max_asks_per_step:
                state.bump_retry(self.run_id, phase["no"])
                log_call(self.run_id, phase["no"], "ask_human",
                         "질문 상한 초과", call.arguments,
                         ToolResult(ok=False,
                                    summary=f"이 단계에서 이미 {asked_here}회 물었다. "
                                            "더 묻지 말고 지금 있는 답으로 진행하라.",
                                    error_label=Failure.GAVE_UP))
                return {"action": "ask_limit", "step": phase["name"], "asked": asked_here}

            args = call.arguments
            payload = {"question": args.get("question", "어떻게 할까요?"),
                       "options": args.get("options", []),
                       "multi_select": bool(args.get("multi_select", False)),
                       "step_no": phase["no"]}
            version = state.ask(self.run_id, args.get("question_id", f"step{phase['no']}"), payload)
            log_call(self.run_id, phase["no"], "ask_human", "사람에게 질문", args,
                     ToolResult(ok=True, summary=f"질문: {payload['question']}"))
            return {"action": "ask", "question": {**payload, "version": version}}

        if call.name == FINISH_STEP.name:
            # 게이트는 **이 단계에서 사람이 답한 것**으로만 넘어갈 수 있다.
            # 지시문으로만 막으면 앞 단계 답변을 근거로 그냥 종료한다 —
            # 실제로 단계2(후보 선택)가 질문 없이 finish_step 만 하고 넘어갔다.
            # 허용 도구를 코드로 강제한 것과 같은 이유다 (D-023).
            if phase["gate"]:
                g = state.gate_state(self.run_id, phase["no"])
                if not (g and g["answered"]):
                    tries = state.bump_retry(self.run_id, phase["no"])
                    log_call(self.run_id, phase["no"], "finish_step",
                             "사람 승인 없이 게이트를 넘으려 함", call.arguments,
                             ToolResult(ok=False,
                                        summary="이 단계는 사람의 승인이 필요하다. "
                                                "ask_human 으로 먼저 물어라.",
                                        error_label=Failure.TOOL_ERROR))
                    if tries > self.settings.max_retry_per_step:
                        raise Stopped(
                            f"{phase['name']} 단계는 사람 승인이 필요한데 "
                            f"승인 없이 종료를 {tries}회 시도했다 — 사람에게 넘긴다")
                    return {"action": "gate_not_approved", "step": phase["name"]}

            summary = call.arguments.get("summary", "")
            state.finish_step(self.run_id, phase["no"])
            log_call(self.run_id, phase["no"], "finish_step", "단계 종료 판단",
                     call.arguments, ToolResult(ok=True, summary=summary))
            return {"action": "finish_step", "step": phase["name"], "summary": summary}

        # 이 단계에서 허용된 도구인가. 모델에게 보여주지 않았어도 이름을 대면
        # 레지스트리에서 찾아 실행돼 버린다. 실제로 심층검증 단계에서 web_search 를
        # 6회 불러 반복 상한을 태웠다. 권한 최소화는 목록을 안 주는 것으로는 부족하다.
        if call.name not in phase["tools"]:
            state.bump_retry(self.run_id, phase["no"])
            log_call(self.run_id, phase["no"], call.name,
                     f"{phase['name']} 단계에서 허용되지 않은 도구", call.arguments,
                     ToolResult(ok=False,
                                summary=(f"{call.name} 은 이 단계에서 쓸 수 없다. "
                                         f"허용: {', '.join(phase['tools']) or '없음'}"),
                                error_label=Failure.TOOL_ERROR))
            return {"action": "not_allowed", "name": call.name, "step": phase["name"]}

        tool = registry.get(call.name)
        if tool is None:
            log_call(self.run_id, phase["no"], call.name, "없는 도구를 부름", call.arguments,
                     ToolResult(ok=False, summary=f"등록되지 않은 도구: {call.name}",
                                error_label=Failure.TOOL_ERROR))
            return {"action": "unknown_tool", "name": call.name}

        args = dict(call.arguments)
        if tool.name == "compose_cards":
            # 저장 폴더는 **모델이 정하지 않는다.** setdefault 로 뒀더니 모델이 지어낸
            # 이름(nowon_health_20240909)으로 새 폴더를 만들어 결과가 실행과 분리됐다.
            args["run_id"] = self.run_id

        res = await run_tool(tool, args, run_id=self.run_id, step_no=phase["no"],
                             reason=(result.text or "").strip()[:200] or "다음 행동으로 선택")

        # 카드가 만들어졌으면 **다른 역할의 에이전트**가 문구를 검사한다 (⭐확장5).
        # 만든 쪽이 스스로 채점하면 대체로 통과시킨다.
        if tool.name == "compose_cards" and res.ok:
            review = await reviewer.review_cards(
                self.run_id,
                cards=args.get("cards", []),
                evidence="\n".join(
                    f"- {o['tool_name']}: {o['output_summary']}"
                    for o in state.observations(self.run_id) if o["ok"]),
                step_no=phase["no"],
                rejects_so_far=state.reject_count(self.run_id),
            )
            if not review.passed:
                # 스토리보드부터 다시 짜게 되돌린다
                state.reopen_from(self.run_id, 4)
                return {"action": "review_reject", "step": phase["name"],
                        "summary": review.summary, "problems": len(review.problems),
                        "rejects": review.rejects}
            return {"action": "review_pass", "step": phase["name"],
                    "summary": review.summary, "escalated": review.escalated}

        if not res.ok and tool.on_fail is OnFail.ASK_HUMAN:
            payload = {"question": f"{tool.name} 이(가) 실패했습니다. 어떻게 할까요?",
                       "options": ["기간을 30일로 넓혀 다시 찾기", "검색어를 바꿔 다시 찾기",
                                   "이 단계를 건너뛰기"],
                       "multi_select": False, "step_no": phase["no"]}
            state.ask(self.run_id, f"recover-{tool.name}", payload)
            return {"action": "ask", "question": payload}

        if not res.ok:
            tries = state.bump_retry(self.run_id, phase["no"])
            if tries > self.settings.max_retry_per_step:
                raise Stopped(f"{phase['name']} 단계 재시도 {tries}회 초과")

        return {"action": "tool", "name": tool.name, "ok": res.ok,
                "summary": res.summary, "ms": res.duration_ms}

    # ── 막힐 때까지 돌린다 ──────────────────────────────────
    async def run_until_blocked(self, max_ticks: int = 30) -> dict:
        """사람에게 물어야 하거나, 끝나거나, 상한에 걸릴 때까지 반복한다."""
        t0 = time.perf_counter()
        history: list[dict] = []
        for _ in range(max_ticks):
            try:
                out = await self.tick()
            except Stopped as stop:
                state.set_status(self.run_id, "stopped", stop.reason)
                history.append({"action": "stopped", "reason": stop.reason})
                break
            history.append(out)
            if out["action"] in ("ask", "waiting", "done"):
                break
        return {"run_id": self.run_id, "ticks": len(history),
                "seconds": round(time.perf_counter() - t0, 1), "history": history}
