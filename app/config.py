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
    gemini_model: str = "gemini-3.6-flash"
    gemini_image_model: str = "gemini-3.1-flash-image"
    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"

    # ── 도구 (D-011) ────────────────────────────────────────
    tavily_api_key: str = ""

    # ── LINE 발송 3중 잠금 (D-005) ──────────────────────────
    # 실발송은 이 스위치 + 사람 승인이 모두 있어야 한다. 기본은 dry-run.
    line_channel_access_token: str = ""
    line_send_enabled: bool = False

    # ── 종료 조건 (PRD 3장) ─────────────────────────────────
    max_retry_per_step: int = 3
    max_loop_iterations: int = 20
    max_run_seconds: int = 600
    max_image_calls: int = 8
    max_llm_calls_per_run: int = 40
    max_llm_calls_per_day: int = 300
    max_usd_per_run: float = 0.30
    max_usd_total: float = 3.00

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
