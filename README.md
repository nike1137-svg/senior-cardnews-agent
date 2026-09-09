# 시니어 생활정보 카드뉴스 에이전트

주제 한 줄을 넣으면 **자료를 조사하고, 중간중간 사람에게 물어보며 진행해**
시니어용 카드뉴스 5장(PNG 1080×1350)을 만들어 주는 웹 서비스.

챗봇이 아니라 **일을 끝내주는 에이전트**다. 사람은 고르고 승인만 한다.

> 상태: 뼈대 단계. 화면과 에이전트 루프는 아직 연결되지 않았다.

---

## 실행 방법

필요한 것: Python 3.12 이상, [uv](https://docs.astral.sh/uv/)

```bash
uv sync
```

```bash
Copy-Item .env.example .env
```

`.env` 에 키를 채운다. **이미 환경변수에 있는 키는 비워둬도 된다** (환경변수가 우선).

| 키 | 필요한 곳 | 없으면 |
|---|---|---|
| `GEMINI_API_KEY` | 두뇌 LLM (기본) | 에이전트가 판단을 못 한다 |
| `TAVILY_API_KEY` | 웹 검색 | 검색 도구 비활성 |
| `OPENAI_API_KEY` | 모델 비교용 | 비교 실험만 못 한다 |
| `LINE_CHANNEL_ACCESS_TOKEN` | 발송 | dry-run 으로만 동작 |

서버 실행:

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8765 --reload
```

- 화면: http://127.0.0.1:8765
- 상태 점검: http://127.0.0.1:8765/healthz

`/healthz` 는 **서버가 떴는지만 보지 않고 DB 테이블까지 확인**한다.
`{"status":"ok","db":"ok"}` 가 나와야 정상이다.

---

## 안전 장치

- **LINE 발송은 기본 `dry-run`.** 실제 발송은 ①사람 승인 ②`LINE_SEND_ENABLED=true` 가
  **둘 다** 있어야 한다. 발송 실패 시 자동 재시도하지 않는다 (중복 발송 방지)
- **비용 상한을 코드에 박아뒀다.** 1회 실행당·누적 상한에 닿으면 앱이 먼저 멈춘다
- API 키는 전부 환경변수. `.env` 는 커밋하지 않는다
- 파일 쓰기는 `output/<실행ID>/` 안으로만 제한

---

## 구조

```
app/
  config.py     설정과 종료 조건 상한값 (한 곳에 모음)
  db.py         SQLite 연결 (WAL) — 상태 정본
  schema.sql    runs / steps / tool_calls / questions / llm_usage
  main.py       FastAPI 진입점
  routes/       화면과 API
  templates/    Jinja2
  llm/          LLM 어댑터 (Gemini / OpenAI 교체 가능)
  tools/        에이전트가 호출할 도구 6종
  agent/        에이전트 루프
data/           SQLite 파일 (git 제외)
runs/           실행별 trace.json · outcome.json (git 제외)
output/         생성된 카드 (git 제외)
```

`tool_calls` 와 `llm_usage` 테이블이 실행 로그·비용 대시보드·평가표의 원본이다.
**나중에 붙일 수 없어서 뼈대 단계에 넣었다.**

---

## 문서

| 파일 | 내용 |
|---|---|
| [PRD.md](PRD.md) | 요구사항 명세 — 워크플로·도구·사람 개입 지점·화면·평가 설계 |
| [DECISIONS.md](DECISIONS.md) | 무엇을 왜 골랐는지 (D-001~) |
| [docs/screenshots/](docs/screenshots/) | 실행 화면 캡처 |

---

## 실행 화면

> 각 화면이 완성되는 대로 여기에 넣는다.

| 화면 | 캡처 |
|---|---|
| 주제 입력 | *(예정)* |
| 질문 대기 상태 | *(예정)* |
| 실행 로그 패널 | *(예정)* |
| 카드 검수 | *(예정)* |
| 완성된 카드뉴스 5장 | *(예정)* |
| 비용·소요시간 대시보드 | *(예정)* |
| 실패·재시도 | *(예정)* |
| 배포 URL 접속 | *(예정)* |
