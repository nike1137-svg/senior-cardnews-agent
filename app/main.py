"""FastAPI 앱 진입점."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.agent import runner
from app.config import get_settings
from app.db import init_db
from app.routes import api, pages
from app.tools import mcp_bridge

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_settings().ensure_dirs()
    init_db()
    # 재시작 복구 — 백그라운드 태스크는 프로세스가 죽으면 유실되지만
    # 상태 정본이 SQLite 에 있으므로 기동 시 이어갈 수 있다 (D-012, 루브릭 3번).
    # 자체 MCP 서버의 도구를 등록한다 (⭐확장3).
    # 붙지 않아도 앱은 나머지 도구로 돌아간다.
    await mcp_bridge.discover()
    await runner.recover()
    yield


app = FastAPI(
    title="시니어 생활정보 카드뉴스 에이전트",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
# 만들어진 카드를 화면에서 보여주기 위한 것. 우리 산출물뿐이라 비밀정보가 없다.
app.mount("/output", StaticFiles(directory=get_settings().output_path), name="output")
app.include_router(pages.router)
app.include_router(api.router)
