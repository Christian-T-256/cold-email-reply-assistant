from reply_assistant.demo_data import seed_demo
from reply_assistant.email_client import MockEmailClient
from reply_assistant.llm import FakeReplyLLM
from reply_assistant.models import ReplyCategory, SenderProfile
from reply_assistant.service import ReplyService
from reply_assistant.storage import SQLiteCardStore


def test_demo_covers_every_category_and_exposes_lint_rejection(tmp_path) -> None:
    sender = SenderProfile(
        name="Morgan Lee",
        email="morgan@example.com",
        offer_summary="A fictional weekly feedback brief.",
    )
    service = ReplyService(SQLiteCardStore(tmp_path / "demo.db"), FakeReplyLLM(), MockEmailClient(), sender)

    cards = seed_demo(service)

    assert {card.category for card in cards} == set(ReplyCategory)
    question = next(card for card in cards if card.category == ReplyCategory.QUESTION)
    assert [attempt.accepted for attempt in question.attempts] == [False, True]
