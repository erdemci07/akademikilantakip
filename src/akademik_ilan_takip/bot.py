from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from .scanner import run_scan
from .settings import Settings
from .storage import create_repository
from .telegram import listing_message, report_message

logging.basicConfig(level=logging.INFO)


def authorized(handler):
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        settings: Settings = context.application.bot_data["settings"]
        chat_id = update.effective_chat.id if update.effective_chat else None
        if chat_id not in settings.authorized_ids:
            logging.warning("Yetkisiz Telegram komutu chat_id=%s", chat_id)
            return
        await handler(update, context)
    return wrapped


@authorized
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Akademik İlan Takip hazır. /yardim yazabilirsiniz.")


@authorized
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("/tara, /sonilanlar, /uygun, /durum komutlarını kullanabilirsiniz.")


@authorized
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    report = context.application.bot_data["repository"].last_report()
    await update.message.reply_text(report_message(report) if report else "Henüz tarama yapılmadı.")


async def _show_listings(update: Update, context: ContextTypes.DEFAULT_TYPE, eligible_only: bool) -> None:
    records = context.application.bot_data["repository"].recent_listings(eligible_only=eligible_only)
    if not records:
        await update.message.reply_text("Gösterilecek ilan yok.")
        return
    for listing, analysis in records:
        await update.message.reply_text(listing_message(listing, analysis), disable_web_page_preview=True)


@authorized
async def recent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _show_listings(update, context, False)


@authorized
async def suitable(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _show_listings(update, context, True)


@authorized
async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Tarama başlatıldı.")
    settings = context.application.bot_data["settings"]
    repository = context.application.bot_data["repository"]
    report, new_items = await run_scan(settings, repository)
    for listing, analysis in new_items:
        await update.message.reply_text(listing_message(listing, analysis), disable_web_page_preview=True)
    await update.message.reply_text(report_message(report))


def main() -> None:
    settings = Settings.from_env()
    settings.require_telegram()
    if not settings.authorized_ids:
        raise SystemExit("HATA: AUTHORIZED_TELEGRAM_IDS tanımlı değil; komut botu başlatılmadı.")
    application = Application.builder().token(settings.telegram_token).build()
    application.bot_data["settings"] = settings
    application.bot_data["repository"] = create_repository(settings)
    application.add_handlers([
        CommandHandler("start", start), CommandHandler("yardim", help_command), CommandHandler("tara", scan),
        CommandHandler("sonilanlar", recent), CommandHandler("uygun", suitable), CommandHandler("durum", status),
    ])
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
