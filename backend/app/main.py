import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import (
    chat,
    crm,
    crm_console,
    crm_forms,
    crm_inbox,
    crm_integrations,
    crm_online,
    crm_sheets,
    crm_team,
    crm_webhooks,
    crm_websites,
    crm_whatsapp,
    health,
    integrations,
    widget,
)
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
    # Browsers may call from the CRM (settings) and from any https website: a clinic's site is approved in the
    # Dashboard (Website install) and the chat checks every message against the clinic's approved sites,
    # refusing the rest. The CRM's calls also need the staff's sign-in token, which a website never has.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_origin_regex=r"^https://[a-z0-9.-]+(:[0-9]{2,5})?$",
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
        max_age=600,
    )
    app.include_router(health.router, prefix="/v1")
    app.include_router(chat.router, prefix="/v1")
    app.include_router(crm.router, prefix="/v1")
    app.include_router(crm_inbox.router, prefix="/v1")
    app.include_router(crm_console.router, prefix="/v1")
    app.include_router(crm_websites.router, prefix="/v1")
    app.include_router(crm_integrations.router, prefix="/v1")
    app.include_router(crm_online.router, prefix="/v1")
    app.include_router(crm_sheets.router, prefix="/v1")
    app.include_router(crm_forms.router, prefix="/v1")
    app.include_router(crm_team.router, prefix="/v1")
    app.include_router(crm_webhooks.router, prefix="/v1")
    app.include_router(crm_whatsapp.router, prefix="/v1")
    app.include_router(crm_whatsapp.links, prefix="/v1")
    app.include_router(widget.router, prefix="/v1")
    app.include_router(integrations.router, prefix="/v1")
    return app


app = create_app()
