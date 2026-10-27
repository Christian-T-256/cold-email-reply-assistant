from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .models import SenderProfile


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    mode: str
    database_path: Path
    anthropic_api_key: str | None
    anthropic_model: str
    email_api_base_url: str | None
    email_api_key: str | None
    email_api_timeout_seconds: float
    access_token: str | None
    sender: SenderProfile

    @property
    def demo(self) -> bool:
        return self.mode == "demo"


def load_settings() -> Settings:
    mode = os.getenv("APP_MODE", "demo").strip().lower()
    database_path = Path(os.getenv("DATABASE_PATH", str(ROOT / ".data" / "replies.db")))
    return Settings(
        mode=mode,
        database_path=database_path,
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY") or None,
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5"),
        email_api_base_url=os.getenv("EMAIL_API_BASE_URL") or None,
        email_api_key=os.getenv("EMAIL_API_KEY") or None,
        email_api_timeout_seconds=float(os.getenv("EMAIL_API_TIMEOUT_SECONDS", "20")),
        access_token=os.getenv("APP_ACCESS_TOKEN") or None,
        sender=SenderProfile(
            name=os.getenv("SENDER_NAME", "Morgan Lee"),
            email=os.getenv("SENDER_EMAIL", "morgan@example.com"),
            offer_summary=os.getenv(
                "SENDER_OFFER_SUMMARY",
                "We turn scattered customer feedback into a concise weekly decision brief.",
            ),
            voice_notes=os.getenv(
                "SENDER_VOICE_NOTES",
                "Short, plain, specific, and calm. Never pushy.",
            ),
        ),
    )
