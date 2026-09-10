"""설정 한 곳 모음.

종료 조건 상한값(PRD 3장)이 전부 여기 있다. 코드 곳곳에 숫자를 흩뿌리지 않는다.
환경변수가 .env 보다 우선한다 — GEMINI_API_KEY 는 이미 Windows 환경변수에 있다.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── 두뇌 LLM (D-010) ────────────────────────────────────
    llm_provider: str = "gemini"          # gemini | openai
    gemini_api_key: str = ""
    # 2.5-flash 는 신규 사용자에게 차단됐다 (2026-09-09 확인). D-014 참조.
    # 무료 티어는 **모델마다 하루 20회** 정도로 묶여 있다 (실측).
    # 한 모델이 429 를 내면 아래 순서대로 갈아탄다. 모델마다 한도가 따로라 총량이 늘어난다.
    gemini_model: str = "gemini-3.5-flash"
    gemini_fallback_models: str = (
        "gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-3-flash-preview,"
        "gemini-3.7-flash,gemini-3.6-flash"
    )
    gemini_image_model: str = "gemini-3.1-flash-image"
    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"

    # ── 도구 (D-011) ────────────────────────────────────────
    tavily_api_key: str = ""

    # ── LINE 발송 3중 잠금 (D-005) ──────────────────────────
    # 실발송은 이 스위치 + 사람 승인이 모두 있어야 한다. 기본은 dry-run.
    line_channel_access_token: str = ""
    line_send_enabled: bool = False
    # 수신자 한 명을 명시한다. 비워 두면 실발송을 하지 않는다.
    # broadcast(친구 전체 발송)는 쓰지 않는다 — 대상이 늘어나면 사고가 된다.
    line_to: str = ""

    # 카드 이미지를 LINE 에 보내려면 공개 https 주소여야 한다. 로컬 파일은 못 보낸다.
    public_base_url: str = "https://cardnews.dodami-ai.com"

    # ── 종료 조건 (PRD 3장) ─────────────────────────────────
    max_retry_per_step: int = 3
    # 20 으로 뒀다가 올렸다. 검토 에이전트가 반려하면 스토리보드부터 다시 하므로
    # 재작업 사이클 한 번에 5~6회가 더 든다. 20 이면 반려가 한 번만 나도 카드까지 못 간다.
    # 상한이 고장난 게 아니라 기준이 실제 동작과 안 맞았다.
    # 20 -> 30 -> 45. 두 번 다 실측으로 올렸다 (D-020, D-024).
    # 완주한 실행이 루프 27 로 상한 30 의 90% 를 썼고, 그 뒤 세 실행이
    # 모두 30 에 걸려 6/7 에서 멈췄다. 무한 루프를 막는 장치가 정상 작업을 막고 있었다.
    max_loop_iterations: int = 45
    # 한 단계에서 사람에게 물을 수 있는 횟수. 질문도 루프를 태운다 —
    # 실제로 카드 합성 단계에서 같은 것을 세 번 물어 반복 예산을 3회 먹었다.
    max_asks_per_step: int = 3
    max_run_seconds: int = 600
    max_image_calls: int = 8
    max_llm_calls_per_run: int = 40
    # 실제 무료 한도(모델당 하루 20회)보다 넉넉히 두고, 429 는 모델 교체로 대응한다.
    max_llm_calls_per_day: int = 300
    max_usd_per_run: float = 0.30
    max_usd_total: float = 3.00

    # ── 실패 주입 (개발·시연용) ─────────────────────────────
    # 쉼표로 구분: search_empty, fetch_fail, weather_fail, image_fail, line_fail
    # 실패·재시도 화면은 나중에 재현하기 어렵다. 스위치로 언제든 만들 수 있게 한다.
    fault_inject: str = ""

    # ── 경로 (상대경로면 프로젝트 루트 기준) ────────────────
    db_path: Path = Path("data/app.db")
    runs_dir: Path = Path("runs")
    output_dir: Path = Path("output")

    def _abs(self, p: Path) -> Path:
        return p if p.is_absolute() else BASE_DIR / p

    @property
    def db_file(self) -> Path:
        return self._abs(self.db_path)

    @property
    def runs_path(self) -> Path:
        return self._abs(self.runs_dir)

    @property
    def output_path(self) -> Path:
        return self._abs(self.output_dir)

    def ensure_dirs(self) -> None:
        self.db_file.parent.mkdir(parents=True, exist_ok=True)
        self.runs_path.mkdir(parents=True, exist_ok=True)
        self.output_path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
