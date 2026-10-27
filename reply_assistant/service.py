from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from .email_client import EmailClient, SendReceipt
from .lint import LintViolation, lint_draft
from .llm import ReplyLLM
from .models import (
    CardStatus,
    DraftAttempt,
    DraftCandidate,
    InboundReply,
    ReplyCategory,
    ReviewCard,
    SenderProfile,
)
from .storage import InvalidTransition, SQLiteCardStore


UNSUBSCRIBE_RE = re.compile(
    r"(?i)\b(unsubscribe|opt[ -]?out|remove me|take me off|stop emailing|do not email)\b"
)
OUT_OF_OFFICE_RE = re.compile(
    r"(?i)\b(out of (the )?office|automatic reply|auto[ -]?reply|away from (my )?email|on vacation)\b"
)


class DraftGateError(RuntimeError):
    def __init__(self, violations: list[LintViolation]):
        self.violations = violations
        super().__init__("draft did not pass the lint gate")


@dataclass(frozen=True)
class ApprovalResult:
    card: ReviewCard
    sent_now: bool


class ReplyService:
    def __init__(
        self,
        store: SQLiteCardStore,
        llm: ReplyLLM,
        email_client: EmailClient,
        sender: SenderProfile,
        max_attempts: int = 3,
    ):
        self.store = store
        self.llm = llm
        self.email_client = email_client
        self.sender = sender
        self.max_attempts = max_attempts

    @staticmethod
    def _card_id(message_id: str) -> str:
        return "card_" + hashlib.sha256(message_id.encode("utf-8")).hexdigest()[:12]

    @staticmethod
    def _safety_category(body: str) -> ReplyCategory | None:
        if UNSUBSCRIBE_RE.search(body):
            return ReplyCategory.UNSUBSCRIBE
        if OUT_OF_OFFICE_RE.search(body):
            return ReplyCategory.OUT_OF_OFFICE
        return None

    def process(self, inbound: InboundReply) -> ReviewCard:
        existing = self.store.get_by_source_message_id(inbound.message_id)
        if existing:
            return existing
        safety_category = self._safety_category(inbound.body)
        if safety_category:
            note = "No draft created. Safety rule suppressed this reply before the model ran."
            card = ReviewCard(
                card_id=self._card_id(inbound.message_id),
                inbound=inbound,
                sender=self.sender,
                category=safety_category,
                confidence="deterministic",
                one_point="explicit opt-out" if safety_category == ReplyCategory.UNSUBSCRIBE else "automatic reply",
                draft="",
                status=CardStatus.SUPPRESSED,
                status_note=note,
            )
            return self.store.insert(card)

        attempts: list[DraftAttempt] = []
        previous: DraftCandidate | None = None
        violations: list[LintViolation] = []
        for number in range(1, self.max_attempts + 1):
            candidate = self.llm.create_candidate(
                inbound,
                self.sender,
                previous_draft=previous.draft if previous else None,
                violations=[item.label() for item in violations],
            )
            if previous:
                candidate = DraftCandidate(previous.category, candidate.confidence, previous.one_point, candidate.draft)
            if candidate.category in {ReplyCategory.UNSUBSCRIBE, ReplyCategory.OUT_OF_OFFICE}:
                card = ReviewCard(
                    card_id=self._card_id(inbound.message_id),
                    inbound=inbound,
                    sender=self.sender,
                    category=candidate.category,
                    confidence=candidate.confidence,
                    one_point=candidate.one_point,
                    draft="",
                    status=CardStatus.SUPPRESSED,
                    status_note="No draft created for an opt-out or automatic reply.",
                )
                return self.store.insert(card)
            violations = lint_draft(candidate.draft, self.sender.first_name, candidate.category)
            attempts.append(
                DraftAttempt(number, candidate.draft, [item.label() for item in violations], not violations)
            )
            if not violations:
                card = ReviewCard(
                    card_id=self._card_id(inbound.message_id),
                    inbound=inbound,
                    sender=self.sender,
                    category=candidate.category,
                    confidence=candidate.confidence,
                    one_point=candidate.one_point,
                    draft=candidate.draft,
                    status=CardStatus.PENDING,
                    attempts=attempts,
                )
                return self.store.insert(card)
            previous = candidate
        raise DraftGateError(violations)

    def edit(self, card_id: str, draft: str) -> ReviewCard:
        card = self.store.get(card_id)
        if card.status != CardStatus.PENDING:
            raise InvalidTransition(f"cannot edit a {card.status.value} card")
        violations = lint_draft(draft, card.sender.first_name, card.category)
        if violations:
            raise DraftGateError(violations)
        card.draft = draft.strip()
        card.attempts.append(DraftAttempt(len(card.attempts) + 1, card.draft, [], True))
        return self.store.save(card)

    def skip(self, card_id: str) -> ReviewCard:
        card = self.store.get(card_id)
        if card.status != CardStatus.PENDING:
            raise InvalidTransition(f"cannot skip a {card.status.value} card")
        card.status = CardStatus.SKIPPED
        card.status_note = "Skipped by reviewer."
        return self.store.save(card)

    def approve(self, card_id: str) -> ApprovalResult:
        current = self.store.get(card_id)
        violations = lint_draft(current.draft, current.sender.first_name, current.category)
        if violations:
            raise DraftGateError(violations)
        card, claimed = self.store.claim_for_send(card_id, expected_draft=current.draft)
        if not claimed:
            return ApprovalResult(card, False)
        try:
            receipt: SendReceipt = self.email_client.send_reply(card, idempotency_key=card.card_id)
        except Exception as exc:
            card.status = CardStatus.NEEDS_VERIFICATION
            card.status_note = f"Provider result is uncertain. Verify before retrying. {type(exc).__name__}"
            self.store.save(card)
            raise
        card.status = CardStatus.SENT
        card.provider_message_id = receipt.provider_message_id
        card.status_note = "Approved by a human and accepted by the email provider."
        self.store.save(card)
        return ApprovalResult(card, True)
