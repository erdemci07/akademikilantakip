"""Telegram HTTPS webhook using Firebase Functions (2nd generation)."""
from __future__ import annotations

import hmac
import logging
import os
from datetime import UTC, datetime

import firebase_admin
import requests
from firebase_admin import firestore
from firebase_functions import https_fn

from subscription_logic import process_update

logging.basicConfig(level=logging.INFO)


def _firestore():
    if not firebase_admin._apps:
        firebase_admin.initialize_app()
    return firestore.client()


class Subscribers:
    def __init__(self, db):
        prefix = os.environ.get("FIRESTORE_COLLECTION_PREFIX", "akademik_ilan_takip")
        self.collection = db.collection(f"{prefix}_subscribers")

    def subscribe(self, chat_id: int) -> None:
        self.collection.document(str(chat_id)).set({
            "chat_id": chat_id,
            "active": True,
            "source": "telegram_private_start",
            "updated_at": datetime.now(UTC).isoformat(),
        }, merge=True)

    def unsubscribe(self, chat_id: int) -> None:
        self.collection.document(str(chat_id)).set({
            "chat_id": chat_id,
            "active": False,
            "updated_at": datetime.now(UTC).isoformat(),
        }, merge=True)

    def forget(self, chat_id: int) -> None:
        self.collection.document(str(chat_id)).delete()


class ReadOnlyReports:
    def __init__(self, db):
        prefix = os.environ.get("FIRESTORE_COLLECTION_PREFIX", "akademik_ilan_takip")
        self.reports = db.collection(f"{prefix}_reports")
        self.listings = db.collection(f"{prefix}_listings")

    def last_report_summary(self) -> str | None:
        docs = list(self.reports.order_by("finished_at", direction="DESCENDING").limit(1).stream())
        if not docs:
            return None
        report = docs[0].to_dict() or {}
        sources = report.get("sources") or []
        good = sum(1 for source in sources if source.get("ok"))
        return (f"🔎 Son tarama: {report.get('finished_at', 'Bilinmiyor')}\n"
                f"Başarılı kaynak: {good}/{len(sources)}\n"
                f"Yeni ilan: {report.get('new_listings', 0)}")

    def recent_listings_summary(self) -> str | None:
        docs = list(self.listings.order_by("updated_at", direction="DESCENDING").limit(6).stream())
        if not docs:
            return None
        result = ["📋 Kayıtlı son ilanlar (başvuru süresini resmî kaynaktan doğrula):"]
        for record in docs:
            item = (record.to_dict() or {}).get("listing") or {}
            title = str(item.get("title") or "İlan")[:95]
            url = str(item.get("official_url") or item.get("url") or "")
            if url.startswith("https://"):
                result.append(f"• {title}\n{url}")
        return "\n\n".join(result)[:3900] if len(result) > 1 else None


def _send(chat_id: int, message: str) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": message, "disable_web_page_preview": True},
        timeout=15,
    )
    response.raise_for_status()
    if not response.json().get("ok"):
        raise RuntimeError("Telegram refused message")


@https_fn.on_request(
    region="europe-west1",
    secrets=["TELEGRAM_BOT_TOKEN", "TELEGRAM_WEBHOOK_SECRET"],
    max_instances=3,
    timeout_sec=30,
)
def telegram_webhook(req: https_fn.Request) -> https_fn.Response:
    if req.method != "POST":
        return https_fn.Response("Method not allowed", status=405)
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    webhook_secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
    if not token or not webhook_secret:
        return https_fn.Response("Not configured", status=503)
    supplied_secret = req.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not hmac.compare_digest(supplied_secret, webhook_secret):
        return https_fn.Response("Forbidden", status=403)
    update = req.get_json(silent=True)
    if not isinstance(update, dict):
        return https_fn.Response("Bad payload", status=400)
    try:
        db = _firestore()
        process_update(update, Subscribers(db), _send, ReadOnlyReports(db))
    except Exception:
        logging.exception("Webhook update could not be processed")
        # Telegram retries non-2xx responses. /start, /dur and /sil are idempotent.
        return https_fn.Response("Temporary error", status=503)
    return https_fn.Response("OK", status=200)
