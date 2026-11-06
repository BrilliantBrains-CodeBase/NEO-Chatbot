"""POST /v1/chat/message, step B1: input checks, clinic, website origin, rate limit.

The clinic lookup is replaced with a fixed clinic, so these tests need no database.
"""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.chat import guard, service, store
from app.chat.schemas import BotMessage, ChatRequest, ChatResponse
from app.core.config import get_settings
from app.main import create_app

SITE = "https://neofollicletransplant.com"
ARYA = guard.Clinic("NFHT", "Arya AI", (SITE,))
TAKEN = "s_" + "9" * 32


def body(**over: Any) -> dict[str, Any]:
    b: dict[str, Any] = {
        "client_id": "NFHT",
        "session_id": "s_" + "a" * 32,
        "visitor_id": "v_" + "b" * 32,
        "event": "start",
        "payload": {},
        "context": {"page_url": SITE + "/", "device": "desktop", "lang": "en"},
    }
    b.update(over)
    return b


@pytest.fixture
async def api(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    async def fake_clinic(clinic_id: str) -> guard.Clinic | None:
        return ARYA if clinic_id == "NFHT" else None

    async def fake_handle(req: ChatRequest, clinic: guard.Clinic) -> ChatResponse:
        # The front door only: no database. Saving is tested on CL99 in test_chat_store.py.
        if req.session_id == TAKEN:
            raise store.SessionMismatch
        return ChatResponse(messages=[BotMessage(text=f"Hi from {clinic.bot_name}")])

    monkeypatch.setattr(guard, "get_clinic", fake_clinic)
    monkeypatch.setattr(service, "handle", fake_handle)
    monkeypatch.setattr(guard, "limiter", guard.RateLimiter())
    get_settings.cache_clear()
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as c:
        yield c
    get_settings.cache_clear()


async def post(api: AsyncClient, origin: str | None = SITE, **over: Any) -> Any:
    headers = {"origin": origin} if origin else {}
    return await api.post("/v1/chat/message", json=body(**over), headers=headers)


async def test_clinic_website_gets_a_json_reply(api: AsyncClient) -> None:
    r = await post(api)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/json"
    assert r.json()["messages"] == [{"type": "text", "text": "Hi from Arya AI"}]


async def test_someone_elses_session_is_refused(api: AsyncClient) -> None:
    assert (await post(api, session_id=TAKEN)).status_code == 403


async def test_www_form_of_the_site_is_the_same_site(api: AsyncClient) -> None:
    assert (await post(api, origin="https://www.neofollicletransplant.com")).status_code == 200


@pytest.mark.parametrize("origin", ["https://evil.example", "http://neofollicletransplant.com", None])
async def test_other_websites_are_refused(api: AsyncClient, origin: str | None) -> None:
    assert (await post(api, origin=origin)).status_code == 403


async def test_local_dev_origin_only_outside_production(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert (await post(api, origin="http://127.0.0.1:5173")).status_code == 200
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    assert (await post(api, origin="http://127.0.0.1:5173")).status_code == 403


async def test_unknown_clinic(api: AsyncClient) -> None:
    assert (await post(api, client_id="CL77")).status_code == 404


@pytest.mark.parametrize(
    "over",
    [
        {"client_id": "neo-follicle"},
        {"session_id": "s_123"},
        {"visitor_id": "v_" + "Z" * 32},
        {"event": "delete_everything"},
        {"payload": {"text": "x" * 501}},
        {"payload": {"action": "DROP TABLE"}},
        {"payload": {"cc": "91"}},
        {"payload": {"surprise": 1}},  # unknown field
        {"context": {"page_url": "x", "device": "tv", "lang": "en"}},
        {"admin": True},  # unknown top-level field
    ],
)
async def test_bad_input_is_refused(api: AsyncClient, over: dict[str, Any]) -> None:
    assert (await post(api, **over)).status_code == 422


async def test_rate_limit_per_visitor(api: AsyncClient) -> None:
    for _ in range(guard.VISITOR_PER_MIN):
        assert (await post(api)).status_code == 200
    assert (await post(api)).status_code == 429
    # Another visitor is not affected.
    assert (await post(api, visitor_id="v_" + "c" * 32)).status_code == 200


def test_ip_comes_from_vercel_only_on_vercel(monkeypatch: pytest.MonkeyPatch) -> None:
    headers = {"x-real-ip": "203.0.113.9"}
    monkeypatch.delenv("VERCEL", raising=False)
    assert guard.client_ip(headers, "10.0.0.1") == "10.0.0.1"  # off Vercel the header could be faked
    monkeypatch.setenv("VERCEL", "1")
    assert guard.client_ip(headers, "10.0.0.1") == "203.0.113.9"
