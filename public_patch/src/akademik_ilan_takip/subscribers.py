"""Firestore-backed, private-chat subscribers for scheduled Telegram delivery.

Chat IDs are taken only from Telegram /start registrations, or legacy admin IDs.
Unsubscribing wins over legacy bootstrap on all subsequent scheduled runs.
"""
from __future__ import annotations

from datetime import UTC, datetime


class FirestoreSubscribers:
    def __init__(self, db, prefix: str):
        self.collection = db.collection(f"{prefix}_subscribers")
        self.meta = db.collection(f"{prefix}_meta").document("legacy_admin_import_v1")

    def bootstrap_legacy(self, chat_ids: frozenset[int]) -> None:
        """Preserve existing recipients without reviving someone who opted out."""
        from google.api_core.exceptions import AlreadyExists

        # One-time migration, so deleted or unsubscribed users are not re-added.
        if self.meta.get().exists:
            return
        for chat_id in sorted(chat_ids):
            if chat_id <= 0:
                continue
            try:
                self.collection.document(str(chat_id)).create({
                    "chat_id": chat_id,
                    "active": True,
                    "source": "legacy_admin",
                    "updated_at": datetime.now(UTC).isoformat(),
                })
            except AlreadyExists:
                continue
        self.meta.set({"completed_at": datetime.now(UTC).isoformat()})

    def active_ids(self) -> list[int]:
        """Fetch only active subscribers, not all historical users."""
        from google.cloud.firestore_v1.base_query import FieldFilter

        docs = self.collection.where(filter=FieldFilter("active", "==", True)).stream()
        ids: set[int] = set()
        for doc in docs:
            data = doc.to_dict() or {}
            candidate = data.get("chat_id")
            # Only integer private-chat identifiers are accepted; no groups.
            if type(candidate) is int and candidate > 0:
                ids.add(candidate)
        return sorted(ids)

    def deactivate(self, chat_id: int) -> None:
        self.collection.document(str(chat_id)).set({
            "active": False,
            "updated_at": datetime.now(UTC).isoformat(),
            "disabled_reason": "telegram_blocked_or_chat_missing",
        }, merge=True)
