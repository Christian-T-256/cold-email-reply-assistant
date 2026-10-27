from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReplyCategory(str, Enum):
    INTERESTED = "interested"
    QUESTION = "question"
    OBJECTION = "objection"
    NOT_NOW = "not_now"
    UNSUBSCRIBE = "unsubscribe"
    OUT_OF_OFFICE = "out_of_office"


class CardStatus(str, Enum):
    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    SKIPPED = "skipped"
    SUPPRESSED = "suppressed"
    NEEDS_VERIFICATION = "needs_verification"


@dataclass(frozen=True)
class SenderProfile:
    name: str
    email: str
    offer_summary: str
    voice_notes: str = "Short, plain, specific, and calm."

    @property
    def first_name(self) -> str:
        return self.name.split()[0]


@dataclass(frozen=True)
class InboundReply:
    message_id: str
    thread_id: str
    from_name: str
    from_email: str
    company: str
    subject: str
    body: str
    received_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InboundReply":
        return cls(**data)


@dataclass(frozen=True)
class DraftCandidate:
    category: ReplyCategory
    confidence: str
    one_point: str
    draft: str


@dataclass(frozen=True)
class DraftAttempt:
    number: int
    draft: str
    violations: list[str]
    accepted: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReviewCard:
    card_id: str
    inbound: InboundReply
    sender: SenderProfile
    category: ReplyCategory
    confidence: str
    one_point: str
    draft: str
    status: CardStatus
    attempts: list[DraftAttempt] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    provider_message_id: str | None = None
    status_note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["category"] = self.category.value
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewCard":
        values = dict(data)
        values["inbound"] = InboundReply.from_dict(values["inbound"])
        values["sender"] = SenderProfile(**values["sender"])
        values["category"] = ReplyCategory(values["category"])
        values["status"] = CardStatus(values["status"])
        values["attempts"] = [DraftAttempt(**item) for item in values.get("attempts", [])]
        return cls(**values)
