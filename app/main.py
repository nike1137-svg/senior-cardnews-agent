"""FastAPI 앱 진입점."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.db import init_db
from app.routes import pages

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_settings().ensure_dirs()
    init_db()
    # TODO(4단계): status='running' 인 실행을 찾아 중단 지점부터 재개한다.
    #   asyncio 백그라운드 태스크는 프로세스가 죽으면 유실되지만,
    #   상태 정본이 SQLite 에 있으므로 기동 시 이어갈 수 있다 (D-012).
    yield


app = FastAPI(
    title="시니어 생활정보 카드뉴스 에이전트",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.include_router(pages.router)
