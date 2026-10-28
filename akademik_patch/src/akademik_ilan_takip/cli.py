from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import replace

from .scanner import run_scan
from .settings import ConfigurationError, Settings
from .storage import create_repository
from .telegram import listing_message, report_message, send_message


async def _scan(notify: bool) -> None:
    settings = Settings.from_env()
    repository = create_repository(settings, production=bool(os.getenv("GITHUB_ACTIONS")))
    report, new_items = await run_scan(settings, repository)
    print(report_message(report))
    if notify:
        settings.require_telegram()
        if not settings.authorized_ids:
            raise ConfigurationError("Bildirim için AUTHORIZED_TELEGRAM_IDS tanımlı değil.")
        for chat_id in settings.authorized_ids:
            # Avoid Telegram flood limits; every new notice still gets a link.
            for index, (listing, analysis) in enumerate(new_items):
                await send_message(settings, chat_id, listing_message(listing, analysis))
                if index < len(new_items) - 1:
                    await asyncio.sleep(1.1)
            await send_message(settings, chat_id, report_message(report))
    if report.sources and len(report.failed_sources) == len(report.sources):
        # If every source failed, make the workflow red instead of claiming success.
        raise RuntimeError("Bütün kaynaklar başarısız oldu; durum raporu iletildi.")
    # Partial failures must still be visible in report but should not prevent
    # a healthy hourly run from succeeding.


async def _telegram_test(chat_id: int) -> None:
    settings = Settings.from_env()
    if settings.authorized_ids and chat_id not in settings.authorized_ids:
        settings = replace(settings, authorized_ids=settings.authorized_ids | {chat_id})
    await send_message(settings, chat_id, "✅ Akademik İlan Takip Telegram bağlantı testi başarılı.")
    print("Telegram test mesajı Telegram API tarafından kabul edildi.")


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    test = sub.add_parser("telegram-test")
    test.add_argument("--chat-id", type=int, required=True)
    scan = sub.add_parser("scan")
    scan.add_argument("--notify", action="store_true")
    scan.add_argument("--database-backend", choices=["local", "firestore"])
    args = parser.parse_args()
    if getattr(args, "database_backend", None):
        os.environ["DATABASE_BACKEND"] = args.database_backend
    try:
        if args.command == "telegram-test":
            asyncio.run(_telegram_test(args.chat_id))
        else:
            asyncio.run(_scan(args.notify))
    except (ConfigurationError, RuntimeError) as exc:
        raise SystemExit(f"HATA: {exc}") from exc


if __name__ == "__main__":
    main()
