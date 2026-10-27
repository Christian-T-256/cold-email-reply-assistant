from __future__ import annotations

import json
import re
from typing import Protocol

from .models import DraftCandidate, InboundReply, ReplyCategory, SenderProfile


class ReplyLLM(Protocol):
    def create_candidate(
        self,
        inbound: InboundReply,
        sender: SenderProfile,
        previous_draft: str | None = None,
        violations: list[str] | None = None,
    ) -> DraftCandidate: ...


class AnthropicReplyLLM:
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    def create_candidate(
        self,
        inbound: InboundReply,
        sender: SenderProfile,
        previous_draft: str | None = None,
        violations: list[str] | None = None,
    ) -> DraftCandidate:
        import anthropic

        repair = ""
        if previous_draft:
            repair = (
                "\nThe prior draft failed a deterministic gate. Rewrite it.\n"
                f"Prior draft:\n{previous_draft}\n"
                f"Violations:\n{json.dumps(violations or [])}\n"
            )
        system = f"""You draft replies to people who answered a cold email.

Classify as exactly one of: interested, question, objection, not_now, unsubscribe, out_of_office.
React to the single most specific point in the person's reply. Do not repeat the original pitch.
Write 25 to 80 words in the sender's voice: {sender.voice_notes}
Use only facts in the inbound reply and this offer summary: {sender.offer_summary}
Never invent a claim, price, person, date, result, or link. Use one natural next step.
For an objection, acknowledge it before one concise response. For not_now, honor the timing.
For unsubscribe or out_of_office, return an empty draft.
Use short paragraphs. End with {sender.first_name} alone on the last line.
Avoid canned greetings, formal sign-offs, corporate jargon, long dashes, and explicit call durations.

Return JSON only with keys category, confidence, one_point, draft."""
        user = f"""Prospect: {inbound.from_name} at {inbound.company}
Subject: {inbound.subject}
Reply:
{inbound.body}
{repair}"""
        client = anthropic.Anthropic(api_key=self.api_key)
        message = client.messages.create(
            model=self.model,
            max_tokens=700,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        raw = "".join(block.text for block in message.content if getattr(block, "type", "") == "text")
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end < start:
            raise RuntimeError("model did not return a JSON object")
        data = json.loads(raw[start : end + 1])
        return DraftCandidate(
            category=ReplyCategory(data["category"]),
            confidence=str(data.get("confidence", "medium")),
            one_point=str(data.get("one_point", "")).strip(),
            draft=str(data.get("draft", "")).strip(),
        )


class FakeReplyLLM:
    """Deterministic demo model. One fixture intentionally fails its first lint pass."""

    def create_candidate(
        self,
        inbound: InboundReply,
        sender: SenderProfile,
        previous_draft: str | None = None,
        violations: list[str] | None = None,
    ) -> DraftCandidate:
        body = inbound.body.casefold()
        first = inbound.from_name.split()[0]
        signoff = sender.first_name

        if "connect" in body or "support inbox" in body:
            if previous_draft is None:
                return DraftCandidate(
                    ReplyCategory.QUESTION,
                    "high",
                    "whether it connects to the existing support inbox",
                    f"Great question, {first}. We can leverage that inbox seamlessly.\n\nI'd be happy to show you.\n\n{signoff}",
                )
            return DraftCandidate(
                ReplyCategory.QUESTION,
                "high",
                "whether it connects to the existing support inbox",
                f"{first}, yes. It can read from the support inbox you already use, so the team keeps one place to work.\n\nWhich inbox provider are you on?\n\n{signoff}",
            )
        if re.search(r"\b(already|in-house|in house)\b", body):
            return DraftCandidate(
                ReplyCategory.OBJECTION,
                "high",
                "the team already prepares reports in-house",
                f"That is fair, {first}. If the current report reaches the right people on time, I would keep it.\n\nIs the hard part compiling it or getting decisions from it?\n\n{signoff}",
            )
        if re.search(r"\b(january|later|next quarter|not now)\b", body):
            return DraftCandidate(
                ReplyCategory.NOT_NOW,
                "high",
                "the migration needs to finish first",
                f"Understood, {first}. The migration comes first.\n\nI will leave this with you until January.\n\n{signoff}",
            )
        return DraftCandidate(
            ReplyCategory.INTERESTED,
            "high",
            "the weekly summary could help the operations team",
            f"{first}, that sounds like the right use case. The weekly brief is built for teams that need the signal without another reporting project.\n\nWhat gets missed in the current process?\n\n{signoff}",
        )
