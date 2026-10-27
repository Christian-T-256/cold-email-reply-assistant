from datetime import datetime, timezone

import pytest

from reply_assistant.email_client import MockEmailClient
from reply_assistant.llm import FakeReplyLLM
from reply_assistant.models import CardStatus, InboundReply, ReplyCategory, SenderProfile
from reply_assistant.service import DraftGateError, ReplyService
from reply_assistant.storage import InvalidTransition, SQLiteCardStore


SENDER = SenderProfile(
    name="Morgan Lee",
    email="morgan@example.com",
    offer_summary="A fictional weekly feedback brief.",
)


def inbound(message_id: str, body: str) -> InboundReply:
    return InboundReply(
        message_id=message_id,
        thread_id=f"thread-{message_id}",
        from_name="Jamie Rivera",
        from_email="jamie.rivera@example.com",
        company="Northwind Dental",
        subject="Re: feedback brief",
        body=body,
        received_at=datetime.now(timezone.utc).isoformat(),
    )


@pytest.fixture
def service(tmp_path):
    email = MockEmailClient()
    service = ReplyService(SQLiteCardStore(tmp_path / "test.db"), FakeReplyLLM(), email, SENDER)
    return service, email


def test_dirty_first_draft_is_rewritten_before_queue(service) -> None:
    app, _email = service
    card = app.process(inbound("question-1", "Does this connect to our support inbox?"))

    assert card.category == ReplyCategory.QUESTION
    assert card.status == CardStatus.PENDING
    assert len(card.attempts) == 2
    assert card.attempts[0].accepted is False
    assert any("corporate_ai" in item for item in card.attempts[0].violations)
    assert card.attempts[1].accepted is True


def test_unsubscribe_and_auto_reply_are_suppressed(service) -> None:
    app, _email = service
    unsubscribe = app.process(inbound("unsubscribe-1", "Please unsubscribe me."))
    auto = app.process(inbound("auto-1", "Automatic reply: I am out of the office."))

    assert unsubscribe.category == ReplyCategory.UNSUBSCRIBE
    assert auto.category == ReplyCategory.OUT_OF_OFFICE
    assert unsubscribe.status == auto.status == CardStatus.SUPPRESSED
    assert unsubscribe.draft == auto.draft == ""


def test_approval_is_idempotent(service) -> None:
    app, email = service
    card = app.process(inbound("interested-1", "This could help our operations team."))

    first = app.approve(card.card_id)
    second = app.approve(card.card_id)

    assert first.sent_now is True
    assert second.sent_now is False
    assert second.card.status == CardStatus.SENT
    assert len(email.sent) == 1


def test_duplicate_inbound_reuses_existing_card(service) -> None:
    app, _email = service
    reply = inbound("dedupe-1", "Does this connect to our support inbox?")

    first = app.process(reply)
    second = app.process(reply)

    assert first.card_id == second.card_id
    assert app.store.count() == 1


def test_dirty_edit_is_rejected_without_mutating_card(service) -> None:
    app, _email = service
    card = app.process(inbound("interested-2", "This could help our operations team."))

    with pytest.raises(DraftGateError):
        app.edit(card.card_id, "I would be happy to leverage this.\n\nMorgan")

    stored = app.store.get(card.card_id)
    assert stored.draft == card.draft
    assert stored.status == CardStatus.PENDING


def test_skipped_card_cannot_send(service) -> None:
    app, email = service
    card = app.process(inbound("interested-3", "This could help our operations team."))
    app.skip(card.card_id)

    with pytest.raises(InvalidTransition):
        app.approve(card.card_id)
    assert email.sent == []


class FailingEmailClient:
    def send_reply(self, _card, idempotency_key):
        del idempotency_key
        raise TimeoutError("provider timed out")


def test_ambiguous_send_failure_requires_verification(tmp_path) -> None:
    app = ReplyService(SQLiteCardStore(tmp_path / "test.db"), FakeReplyLLM(), FailingEmailClient(), SENDER)
    card = app.process(inbound("interested-4", "This could help our operations team."))

    with pytest.raises(TimeoutError):
        app.approve(card.card_id)

    stored = app.store.get(card.card_id)
    assert stored.status == CardStatus.NEEDS_VERIFICATION
    with pytest.raises(InvalidTransition):
        app.approve(card.card_id)
