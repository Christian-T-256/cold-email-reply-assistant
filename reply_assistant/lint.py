from __future__ import annotations

import re
from dataclasses import dataclass

from .models import ReplyCategory


@dataclass(frozen=True)
class LintViolation:
    code: str
    message: str
    match: str = ""

    def label(self) -> str:
        return f"{self.code}: {self.message}" + (f" [{self.match}]" if self.match else "")


RULES: tuple[tuple[str, str, str], ...] = (
    ("dash", f"[{chr(0x2013)}{chr(0x2014)}]", "replace long dashes with plain punctuation"),
    (
        "canned_opener",
        r"(?i)\b(i hope this finds you|hope you are doing well|thank you for reaching out|thanks for sharing)\b",
        "remove the canned opener",
    ),
    (
        "canned_closer",
        r"(?i)\b(looking forward to hearing|feel free to|do not hesitate to|let me know if you have any questions)\b",
        "remove the canned closer",
    ),
    (
        "corporate_ai",
        r"(?i)\b(leverage|utilize|seamless|robust|delve|elevate|streamline|synergy|holistic|empower|facilitate|game[ -]?changer|deep dive|tailored solutions)\b",
        "replace corporate AI wording",
    ),
    (
        "hollow_enthusiasm",
        r"(?i)\b(great question|fantastic|delighted|thrilled|resonated|i would be happy to|i'd be happy to)\b",
        "remove hollow enthusiasm",
    ),
    (
        "formal_signoff",
        r"(?im)^\s*(best|warm|kind) regards[,!]?$|^\s*sincerely[,]?$",
        "use the sender's first name as the sign-off",
    ),
    (
        "colon_opener",
        r"(?im)^\s*(quick one|short version|the gist|bottom line|in short)\s*:",
        "remove the formulaic colon opener",
    ),
    (
        "call_duration",
        r"(?i)\b(10|15|20|30|45|ten|fifteen|twenty|thirty|forty[ -]?five)[ -]?(minute|min)\b",
        "remove the call duration",
    ),
    ("worth_call", r"(?i)\bworth\s+(a\s+)?(call|chat|conversation)\b", "remove the formulaic call ask"),
    (
        "mechanical_transition",
        r"(?i)\b(furthermore|moreover|additionally|consequently|in conclusion)\b",
        "remove the mechanical transition",
    ),
)


def lint_draft(draft: str, sender_first_name: str, category: ReplyCategory) -> list[LintViolation]:
    violations: list[LintViolation] = []
    text = draft.strip()
    if not text:
        return [LintViolation("empty", "draft cannot be empty")]

    for code, pattern, message in RULES:
        match = re.search(pattern, text)
        if match:
            violations.append(LintViolation(code, message, match.group(0)[:48]))

    words = re.findall(r"\b[\w']+\b", text)
    if len(words) > 90:
        violations.append(LintViolation("too_long", "keep the reply under 90 words", str(len(words))))

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines or lines[-1].casefold() != sender_first_name.casefold():
        violations.append(
            LintViolation("signoff", f"last non-empty line must be {sender_first_name}", lines[-1] if lines else "")
        )

    if len(words) > 45 and "\n\n" not in text:
        violations.append(LintViolation("dense_block", "break a longer reply into short paragraphs"))

    if re.search(r"https?://|www\.", text, re.IGNORECASE):
        violations.append(LintViolation("unsolicited_link", "remove links from the first reply"))

    if category in {ReplyCategory.UNSUBSCRIBE, ReplyCategory.OUT_OF_OFFICE}:
        violations.append(LintViolation("suppressed_category", "this category must not produce a draft"))

    return violations
