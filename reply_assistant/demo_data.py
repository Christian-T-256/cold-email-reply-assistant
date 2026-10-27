from __future__ import annotations

from datetime import datetime, timezone

from .models import InboundReply
from .service import ReplyService


FIXTURES = (
    {
        "message_id": "demo-interested-001",
        "thread_id": "thread-interested-001",
        "from_name": "Jamie Rivera",
        "from_email": "jamie.rivera@example.com",
        "company": "Northwind Dental",
        "subject": "Re: weekly feedback summary",
        "body": "This could help our operations team. I am open to hearing more.",
    },
    {
        "message_id": "demo-question-001",
        "thread_id": "thread-question-001",
        "from_name": "Priya Shah",
        "from_email": "priya.shah@example.com",
        "company": "Contoso Freight",
        "subject": "Re: support feedback",
        "body": "Does this connect to the support inbox we already use?",
    },
    {
        "message_id": "demo-objection-001",
        "thread_id": "thread-objection-001",
        "from_name": "Theo Martin",
        "from_email": "theo.martin@example.com",
        "company": "Alpine Ledger",
        "subject": "Re: weekly feedback summary",
        "body": "We already compile these reports in-house.",
    },
    {
        "message_id": "demo-not-now-001",
        "thread_id": "thread-not-now-001",
        "from_name": "Amina Okafor",
        "from_email": "amina.okafor@example.com",
        "company": "Fabrikam Health",
        "subject": "Re: weekly feedback summary",
        "body": "Please check back in January after our migration is finished.",
    },
    {
        "message_id": "demo-unsubscribe-001",
        "thread_id": "thread-unsubscribe-001",
        "from_name": "Jordan Kim",
        "from_email": "jordan.kim@example.com",
        "company": "Litware Foods",
        "subject": "Re: weekly feedback summary",
        "body": "Please unsubscribe me.",
    },
    {
        "message_id": "demo-ooo-001",
        "thread_id": "thread-ooo-001",
        "from_name": "Casey Nguyen",
        "from_email": "casey.nguyen@example.com",
        "company": "Adventure Works",
        "subject": "Automatic reply",
        "body": "I am out of the office until next week and will respond when I return.",
    },
)


def seed_demo(service: ReplyService) -> list:
    received_at = datetime.now(timezone.utc).isoformat()
    return [service.process(InboundReply(received_at=received_at, **item)) for item in FIXTURES]
