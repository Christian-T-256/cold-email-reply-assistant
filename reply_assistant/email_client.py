from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from .models import ReviewCard


@dataclass(frozen=True)
class SendReceipt:
    provider_message_id: str


class EmailClient(Protocol):
    def send_reply(self, card: ReviewCard, idempotency_key: str) -> SendReceipt: ...


class MockEmailClient:
    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    def send_reply(self, card: ReviewCard, idempotency_key: str) -> SendReceipt:
        existing = next((item for item in self.sent if item["idempotency_key"] == idempotency_key), None)
        if existing:
            return SendReceipt(existing["provider_message_id"])
        provider_message_id = f"mock-{card.card_id}"
        self.sent.append(
            {
                "idempotency_key": idempotency_key,
                "provider_message_id": provider_message_id,
                "to": card.inbound.from_email,
                "text": card.draft,
            }
        )
        return SendReceipt(provider_message_id)


class HttpEmailClient:
    """Small provider adapter for an email platform's reply endpoint."""

    def __init__(self, base_url: str, api_key: str, timeout_seconds: float = 20):
        self.endpoint = base_url.rstrip("/") + "/replies"
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def send_reply(self, card: ReviewCard, idempotency_key: str) -> SendReceipt:
        payload = {
            "reply_to_message_id": card.inbound.message_id,
            "thread_id": card.inbound.thread_id,
            "from": card.sender.email,
            "to": card.inbound.from_email,
            "subject": card.inbound.subject,
            "text": card.draft,
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Idempotency-Key": idempotency_key,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:200]
            raise RuntimeError(f"email API returned {exc.code}: {detail}") from exc
        provider_message_id = body.get("message_id") or body.get("id")
        if not provider_message_id:
            raise RuntimeError("email API response did not contain a message id")
        return SendReceipt(str(provider_message_id))
