from __future__ import annotations

from .config import Settings, load_settings
from .demo_data import seed_demo
from .email_client import HttpEmailClient, MockEmailClient
from .llm import AnthropicReplyLLM, FakeReplyLLM
from .service import ReplyService
from .storage import SQLiteCardStore


def build_service(settings: Settings | None = None) -> ReplyService:
    settings = settings or load_settings()
    store = SQLiteCardStore(settings.database_path)
    if settings.demo:
        service = ReplyService(store, FakeReplyLLM(), MockEmailClient(), settings.sender)
        if store.count() == 0:
            seed_demo(service)
        return service

    missing = []
    if not settings.anthropic_api_key:
        missing.append("ANTHROPIC_API_KEY")
    if not settings.email_api_base_url:
        missing.append("EMAIL_API_BASE_URL")
    if not settings.email_api_key:
        missing.append("EMAIL_API_KEY")
    if not settings.access_token:
        missing.append("APP_ACCESS_TOKEN")
    if missing:
        raise RuntimeError("live mode requires: " + ", ".join(missing))
    return ReplyService(
        store,
        AnthropicReplyLLM(settings.anthropic_api_key, settings.anthropic_model),
        HttpEmailClient(settings.email_api_base_url, settings.email_api_key, settings.email_api_timeout_seconds),
        settings.sender,
    )
