"""Confirmed callback-message storage and per-call confirmation workflow."""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import re
import sqlite3
import uuid


@dataclass(frozen=True)
class CallbackMessage:
    message_id: str
    caller_name: str
    callback_number: str
    message: str
    created_at: str
    expires_at: str


class CallbackInbox:
    """Small local inbox; callers are persisted only after workflow confirmation."""

    def __init__(self, path: Path, retention_days: int = 7) -> None:
        if not 1 <= retention_days <= 90:
            raise ValueError("callback retention must be between 1 and 90 days")
        self.path = path
        self.retention_days = retention_days
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.exists():
            os.chmod(self.path, 0o600)
        else:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                # Different LiveKit worker processes can initialize the same
                # business inbox at the same time on the first call.
                os.chmod(self.path, 0o600)
            else:
                os.close(fd)
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS callback_messages (
                    message_id TEXT PRIMARY KEY,
                    source_draft_id TEXT NOT NULL UNIQUE,
                    caller_name TEXT NOT NULL,
                    callback_number TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )"""
            )
            self._delete_expired(connection)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA secure_delete = ON")
        return connection

    @staticmethod
    def _delete_expired(connection: sqlite3.Connection) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        connection.execute("DELETE FROM callback_messages WHERE expires_at <= ?", (now,))

    @staticmethod
    def validate_details(caller_name: object, callback_number: object, message: object) -> tuple[str, str, str]:
        if not isinstance(caller_name, str) or not isinstance(callback_number, str) or not isinstance(message, str):
            raise ValueError("name, callback number, and message must be text")
        name = " ".join(caller_name.split())
        phone = " ".join(callback_number.split())
        note = " ".join(message.split())
        digits = re.sub(r"\D", "", phone)
        if not name or len(name) > 120:
            raise ValueError("caller name must be between 1 and 120 characters")
        if len(phone) > 40 or not 7 <= len(digits) <= 15 or not re.fullmatch(r"[+0-9(). -]+", phone):
            raise ValueError("callback number must contain 7 to 15 digits")
        if not note or len(note) > 1000:
            raise ValueError("message must be between 1 and 1000 characters")
        return name, phone, note

    def save_confirmed(
        self,
        source_draft_id: str,
        caller_name: str,
        callback_number: str,
        message: str,
    ) -> CallbackMessage:
        if not source_draft_id or len(source_draft_id) > 80:
            raise ValueError("invalid draft identifier")
        name, phone, note = self.validate_details(caller_name, callback_number, message)
        now = datetime.now(timezone.utc)
        message_id = str(uuid.uuid4())
        created_at = now.isoformat(timespec="seconds")
        expires_at = (now + timedelta(days=self.retention_days)).isoformat(timespec="seconds")
        with closing(self._connect()) as connection, connection:
            self._delete_expired(connection)
            connection.execute(
                """INSERT OR IGNORE INTO callback_messages
                   (message_id, source_draft_id, caller_name, callback_number, message, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (message_id, source_draft_id, name, phone, note, created_at, expires_at),
            )
            row = connection.execute(
                """SELECT message_id, caller_name, callback_number, message, created_at, expires_at
                   FROM callback_messages WHERE source_draft_id = ?""",
                (source_draft_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("callback message could not be saved")
        return CallbackMessage(**dict(row))

    def list_recent(self, limit: int = 50) -> list[CallbackMessage]:
        limit = max(1, min(int(limit), 100))
        with closing(self._connect()) as connection, connection:
            self._delete_expired(connection)
            rows = connection.execute(
                """SELECT message_id, caller_name, callback_number, message, created_at, expires_at
                   FROM callback_messages ORDER BY created_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [CallbackMessage(**dict(row)) for row in rows]

    def delete(self, message_id: str) -> bool:
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                "DELETE FROM callback_messages WHERE message_id = ?", (message_id,)
            )
        return cursor.rowcount > 0

    def prune_expired(self) -> int:
        with closing(self._connect()) as connection, connection:
            before = connection.total_changes
            self._delete_expired(connection)
            return connection.total_changes - before


class CallbackMessageWorkflow:
    """One call's consent → draft → read-back confirmation → save state."""

    def __init__(self, inbox: CallbackInbox) -> None:
        self.inbox = inbox
        self.state = "idle"
        self.draft: tuple[str, str, str, str] | None = None

    def request_consent(self) -> str:
        self.state = "awaiting_consent"
        self.draft = None
        return (
            "Say: I can take your name, callback number, and message and store them in this "
            "computer's callback inbox for a person to review. No one is automatically notified "
            f"or connected, and the details are deleted after up to {self.inbox.retention_days} days. "
            "In Gemini mode, your voice is also processed by Google. May I collect those details? "
            "Wait for a clear yes before asking for any details."
        )

    @staticmethod
    def _affirmative(text: str) -> bool:
        normalized = re.sub(r"[^a-z0-9 ]", " ", text.casefold())
        normalized = " ".join(normalized.split())
        return normalized in {
            "yes", "yes please", "yes go ahead", "yes save it", "yes do that",
            "yes that is correct", "yes that s correct", "i agree", "i consent",
            "go ahead", "correct", "that is correct", "that s correct", "save it",
        }

    @staticmethod
    def _negative(text: str) -> bool:
        normalized = re.sub(r"[^a-z0-9 ]", " ", text.casefold())
        normalized = " ".join(normalized.split())
        return normalized.startswith(("no", "do not", "don t", "stop", "cancel"))

    def observe_user_transcript(self, text: str) -> str | None:
        if self.state == "awaiting_consent":
            if self._affirmative(text):
                self.state = "collecting"
                return "consent_given"
            if self._negative(text):
                self.state = "declined"
                return "consent_declined"
        elif self.state == "awaiting_confirmation":
            if self._affirmative(text):
                self.state = "confirmed"
                return "message_confirmed"
            if self._negative(text):
                self.state = "declined"
                self.draft = None
                return "message_declined"
        return None

    def prepare(self, caller_name: object, callback_number: object, message: object) -> dict[str, str]:
        if self.state != "collecting":
            raise ValueError("caller has not given consent to collect a callback message")
        name, phone, note = self.inbox.validate_details(caller_name, callback_number, message)
        draft_id = str(uuid.uuid4())
        self.draft = (draft_id, name, phone, note)
        self.state = "awaiting_confirmation"
        return {
            "draft_id": draft_id,
            "read_back": (
                f"I have the name {name}, callback number {phone}, and this message: {note}. "
                "Ask whether these details are correct and may be saved. Wait for a clear yes."
            ),
        }

    def save(self, draft_id: str) -> CallbackMessage:
        if self.state != "confirmed" or self.draft is None:
            raise ValueError("caller has not explicitly confirmed this message")
        expected_id, name, phone, note = self.draft
        if draft_id != expected_id:
            raise ValueError("message confirmation does not match the pending draft")
        saved = self.inbox.save_confirmed(expected_id, name, phone, note)
        self.state = "saved"
        self.draft = None
        return saved
