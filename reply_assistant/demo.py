from __future__ import annotations

import argparse

from .bootstrap import build_service
from .config import load_settings
from .demo_data import seed_demo


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed fictional replies and print the review queue.")
    parser.add_argument("--reset", action="store_true", help="replace local demo cards with fresh fixtures")
    args = parser.parse_args()

    settings = load_settings()
    if not settings.demo:
        raise SystemExit("Set APP_MODE=demo before loading demo fixtures.")
    service = build_service(settings)
    if args.reset:
        service.store.clear()
        seed_demo(service)

    print("Demo review queue")
    print("=" * 78)
    for card in service.store.list():
        rejected = sum(1 for attempt in card.attempts if not attempt.accepted)
        print(
            f"{card.category.value:<15} {card.status.value:<11} "
            f"{card.inbound.from_name:<18} lint rejects: {rejected}"
        )
        for attempt in card.attempts:
            if attempt.violations:
                print(f"  attempt {attempt.number} blocked: " + "; ".join(attempt.violations))
    print("\nRun: uvicorn reply_assistant.web:app --reload")


if __name__ == "__main__":
    main()
