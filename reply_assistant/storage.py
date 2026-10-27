from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import CardStatus, ReviewCard, utc_now


class CardNotFound(KeyError):
    pass


class InvalidTransition(RuntimeError):
    pass


class SQLiteCardStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS cards (
                    card_id TEXT PRIMARY KEY,
                    source_message_id TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    @staticmethod
    def _decode(row: sqlite3.Row) -> ReviewCard:
        return ReviewCard.from_dict(json.loads(row["payload"]))

    @staticmethod
    def _payload(card: ReviewCard) -> str:
        return json.dumps(card.to_dict(), separators=(",", ":"), sort_keys=True)

    def clear(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM cards")

    def count(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM cards").fetchone()
            return int(row["count"])

    def insert(self, card: ReviewCard) -> ReviewCard:
        with self._connect() as connection:
            try:
                connection.execute(
                    "INSERT INTO cards(card_id, source_message_id, status, payload, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (
                        card.card_id,
                        card.inbound.message_id,
                        card.status.value,
                        self._payload(card),
                        card.updated_at,
                    ),
                )
            except sqlite3.IntegrityError:
                existing = connection.execute(
                    "SELECT * FROM cards WHERE source_message_id = ?", (card.inbound.message_id,)
                ).fetchone()
                if existing:
                    return self._decode(existing)
                raise
        return card

    def get(self, card_id: str) -> ReviewCard:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM cards WHERE card_id = ?", (card_id,)).fetchone()
        if not row:
            raise CardNotFound(card_id)
        return self._decode(row)

    def get_by_source_message_id(self, message_id: str) -> ReviewCard | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM cards WHERE source_message_id = ?", (message_id,)
            ).fetchone()
        return self._decode(row) if row else None

    def list(self) -> list[ReviewCard]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM cards ORDER BY updated_at DESC").fetchall()
        return [self._decode(row) for row in rows]

    def save(self, card: ReviewCard) -> ReviewCard:
        card.updated_at = utc_now()
        with self._connect() as connection:
            result = connection.execute(
                "UPDATE cards SET status = ?, payload = ?, updated_at = ? WHERE card_id = ?",
                (card.status.value, self._payload(card), card.updated_at, card.card_id),
            )
        if result.rowcount != 1:
            raise CardNotFound(card.card_id)
        return card

    def claim_for_send(self, card_id: str, expected_draft: str) -> tuple[ReviewCard, bool]:
        """Atomically move pending to sending. Returns false for a completed duplicate."""
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM cards WHERE card_id = ?", (card_id,)).fetchone()
            if not row:
                raise CardNotFound(card_id)
            card = self._decode(row)
            if card.status == CardStatus.SENT:
                connection.commit()
                return card, False
            if card.status != CardStatus.PENDING:
                raise InvalidTransition(f"cannot approve a {card.status.value} card")
            if card.draft != expected_draft:
                raise InvalidTransition("draft changed while approval was in progress")
            card.status = CardStatus.SENDING
            card.updated_at = utc_now()
            connection.execute(
                "UPDATE cards SET status = ?, payload = ?, updated_at = ? WHERE card_id = ? AND status = ?",
                (
                    card.status.value,
                    self._payload(card),
                    card.updated_at,
                    card.card_id,
                    CardStatus.PENDING.value,
                ),
            )
            connection.commit()
            return card, True
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
