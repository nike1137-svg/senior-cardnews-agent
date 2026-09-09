-- 상태 정본 (D-012). trace.json / outcome.json 은 여기서 내보낸다.
--
-- 나중에 붙일 수 없는 두 가지가 여기 들어 있다:
--   tool_calls  : 실행 로그  (평가 4번)
--   llm_usage   : 토큰·비용  (평가 4번 + 종료 조건)

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- 실행 1건
CREATE TABLE IF NOT EXISTS runs (
    run_id        TEXT PRIMARY KEY,
    topic         TEXT NOT NULL,
    region        TEXT,
    status        TEXT NOT NULL,           -- running | waiting_for_user | done | failed | stopped
    provider      TEXT,                    -- gemini | openai
    model         TEXT,
    loop_count    INTEGER NOT NULL DEFAULT 0,
    image_calls   INTEGER NOT NULL DEFAULT 0,
    stop_reason   TEXT,                    -- 종료 조건에 걸렸을 때 그 이유
    started_at    TEXT NOT NULL,
    ended_at      TEXT
);

-- 9단계 진행 상황 (중단 지점부터 재개하기 위함)
CREATE TABLE IF NOT EXISTS steps (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    step_no     INTEGER NOT NULL,
    name        TEXT NOT NULL,
    status      TEXT NOT NULL,             -- pending | running | done | failed | skipped
    retry_count INTEGER NOT NULL DEFAULT 0,
    started_at  TEXT,
    ended_at    TEXT,
    UNIQUE (run_id, step_no)
);

-- 실행 로그 정본. 화면 로그 패널과 trace.json 이 전부 여기서 나온다.
CREATE TABLE IF NOT EXISTS tool_calls (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    -- 실행에 속하지 않은 호출(스모크 테스트·워밍업)도 기록은 남긴다. 그래서 NULL 허용.
    run_id         TEXT REFERENCES runs(run_id) ON DELETE CASCADE,
    step_no        INTEGER,
    tool_name      TEXT NOT NULL,
    reason         TEXT,                   -- 왜 이 도구를 호출했는가 (루브릭이 요구)
    input_json     TEXT,
    output_summary TEXT,
    ok             INTEGER NOT NULL,       -- 0 | 1. "종료 코드 0" 이 아니라 실물 검증 결과다
    error_label    TEXT,                   -- 검색부실|사실오류|문장어려움|이미지실패|도구오류|중간포기
    duration_ms    INTEGER,
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tool_calls_run ON tool_calls(run_id, id);

-- 사람 개입 지점 4곳. UNIQUE 제약 하나가 중복 제출을 막는다 (PRD 5장)
CREATE TABLE IF NOT EXISTS questions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    question_id  TEXT NOT NULL,
    version      INTEGER NOT NULL DEFAULT 1,
    payload_json TEXT NOT NULL,            -- question / options / multi_select
    answer_json  TEXT,
    asked_at     TEXT NOT NULL,
    answered_at  TEXT,
    UNIQUE (run_id, question_id, version)
);

-- 토큰·비용. 비용 대시보드와 상한 차단이 여기서 나온다.
CREATE TABLE IF NOT EXISTS llm_usage (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id            TEXT REFERENCES runs(run_id) ON DELETE CASCADE,
    provider          TEXT NOT NULL,
    model             TEXT NOT NULL,
    prompt_tokens     INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    usd               REAL NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_llm_usage_run ON llm_usage(run_id);
CREATE INDEX IF NOT EXISTS idx_llm_usage_day ON llm_usage(created_at);
