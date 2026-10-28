"""Pure command handling; exercised by unit tests without Google or Telegram APIs."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any


def process_update(
    update: dict[str, Any],
    subscribers: Any,
    send: Callable[[int, str], None],
    repository: Any | None = None,
) -> bool:
    """Process Telegram private-chat messages. Return True when a command handled."""
    message = update.get("message")
    if not isinstance(message, dict):
        return False
    chat = message.get("chat")
    if not isinstance(chat, dict) or chat.get("type") != "private":
        return False
    chat_id = chat.get("id")
    if type(chat_id) is not int or chat_id <= 0:
        return False
    text = message.get("text", "")
    if not isinstance(text, str) or not text.startswith("/"):
        return False
    command = text.split(maxsplit=1)[0].split("@", maxsplit=1)[0].lower()
    if command in {"/start", "/devam"}:
        subscribers.subscribe(chat_id)
        send(chat_id, (
            "✅ Akademik İlan Takip aboneliğin aktif!\n"
            "Türkiye'deki yeni akademik ilanlar ve saatlik tarama raporu buraya gönderilecek.\n"
            "📄 İlan bağlantıları ayrıca paylaşılır.\n\n"
            "Bildirimleri kapat: /dur\nYeniden aç: /devam\nSon ilanlar: /sonilanlar\n"
            "Son tarama: /durum\nVerilerini sil: /sil"
        ))
        return True
    if command in {"/dur", "/stop", "/iptal"}:
        subscribers.unsubscribe(chat_id)
        send(chat_id, "🔕 Saatlik bildirimlerin kapatıldı. Yeniden başlatmak için /devam yazabilirsin.")
        return True
    if command == "/sil":
        subscribers.forget(chat_id)
        send(chat_id, "🗑️ Abonelik kaydın silindi. Yeniden kaydolmak için /start yazabilirsin.")
        return True
    if command in {"/yardim", "/help"}:
        send(chat_id, (
            "Komutlar:\n/start — abone ol\n/dur — bildirimleri kapat\n"
            "/devam — yeniden abone ol\n/sonilanlar — son kayıtlı ilanlar\n"
            "/durum — son tarama raporu\n/sil — abonelik kaydını sil\n"
            "İlanlar saatlik taramayla gönderilir; /tara herkese açık değildir."
        ))
        return True
    if command == "/durum":
        summary = repository.last_report_summary() if repository else None
        send(chat_id, summary or "Henüz kayıtlı tarama raporu bulunamadı.")
        return True
    if command == "/sonilanlar":
        summary = repository.recent_listings_summary() if repository else None
        send(chat_id, summary or "Gösterilecek kayıtlı ilan bulunamadı.")
        return True
    return False
