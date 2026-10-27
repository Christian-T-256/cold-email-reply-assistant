from reply_assistant.lint import lint_draft
from reply_assistant.models import ReplyCategory


def codes(text: str) -> set[str]:
    return {item.code for item in lint_draft(text, "Morgan", ReplyCategory.QUESTION)}


def test_lint_rejects_common_ai_tells() -> None:
    draft = "Great question. We can leverage a seamless workflow.\n\nMorgan"
    assert {"hollow_enthusiasm", "corporate_ai"} <= codes(draft)


def test_lint_rejects_wrong_signoff_links_and_long_dash() -> None:
    draft = "Jamie, here is the detail " + chr(0x2014) + " https://example.com\n\nRegards"
    assert {"dash", "unsolicited_link", "signoff"} <= codes(draft)


def test_lint_accepts_short_specific_reply() -> None:
    draft = (
        "Jamie, yes. It can read from the support inbox your team already uses.\n\n"
        "Which inbox provider are you on?\n\nMorgan"
    )
    assert lint_draft(draft, "Morgan", ReplyCategory.QUESTION) == []
