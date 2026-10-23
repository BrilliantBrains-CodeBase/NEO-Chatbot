import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import chat, health
from app.chat import kb
from app.core.cache import close_redis
from app.core.config import get_settings
from app.core.db import close_pool


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Database and Redis connect on first use, so the API starts even while they are still booting.
    # The embedding model loads and the KB meanings are filled in the background; semantic matching
    # starts once they are ready.
    warming = asyncio.create_task(kb.warm())
    yield
    warming.cancel()
    await close_pool()
    await close_redis()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="NEO Chatbot API",
        version="0.1.0",
        lifespan=lifespan,
        # Every route declares a response model, so FastAPI writes JSON straight from Pydantic.
        # API docs only outside production.
        docs_url=None if settings.app_env == "production" else "/docs",
        redoc_url=None,
        openapi_url=None if settings.app_env == "production" else "/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
        max_age=600,
    )
    app.include_router(health.router, prefix="/v1")
    app.include_router(chat.router, prefix="/v1")
    return app


app = create_app()
