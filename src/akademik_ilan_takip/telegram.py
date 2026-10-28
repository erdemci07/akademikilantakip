from __future__ import annotations

from datetime import UTC

import httpx

from .models import Analysis, Listing, ScanReport
from .settings import ConfigurationError, Settings

CATEGORY_LABELS = {
    "definitely_eligible": "Eğitim koşulları kesin uygun",
    "conditional_eligible": "ALES/dil nedeniyle koşullu uygun",
    "human_review": "Eğitim eşleşmesi insan kontrolünde",
    "ineligible": "Uygun değil",
}


def _date(value) -> str:
    return value.isoformat() if value else "Belirtilmemiş"


def listing_message(listing: Listing, analysis: Analysis) -> str:
    return "\n".join([
        f"📌 {listing.university or listing.source_name}",
        f"Kadro: {listing.position or listing.title}",
        f"Kontenjan: {listing.quota or 'Belirtilmemiş'}",
        f"Son başvuru: {_date(listing.deadline)}",
        f"ALES: {analysis.ales_requirement or 'İlan metninde bulunamadı'}",
        f"YDS/YÖKDİL: {analysis.language_requirement or 'İlan metninde bulunamadı'}",
        f"Deneyim: {analysis.experience_requirement or 'İlan metninde bulunamadı'}",
        f"Lisans koşulu: {analysis.bachelors_match}",
        f"Yüksek lisans koşulu: {analysis.masters_match}",
        f"Değerlendirme: {CATEGORY_LABELS.get(analysis.category, analysis.category)}",
        f"Özet: {analysis.summary}",
        f"Resmî bağlantı: {listing.url}",
    ])[:4000]


def report_message(report: ScanReport) -> str:
    finished = report.finished_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
    source_lines = [
        f"{'✅' if source.ok else '⚠️'} {source.source_name}: "
        f"{source.listings_found} bağlantı" + (f" — {source.error}" if source.error else "")
        for source in report.sources
    ]
    header = (
        f"Tarama raporu — {finished}\nYeni, süresi geçmemiş ilan: {report.new_listings}\n"
        f"Uygun/potansiyel uygun: {report.eligible_new_listings}"
    )
    return header + "\n\nKaynaklar:\n" + ("\n".join(source_lines) or "Yapılandırılmış kaynak yok.")


async def send_message(settings: Settings, chat_id: int, text: str) -> None:
    settings.require_telegram()
    if chat_id not in settings.authorized_ids and settings.authorized_ids:
        raise ConfigurationError("Bu chat ID yetkili listesinde değil.")
    url = f"https://api.telegram.org/bot{settings.telegram_token}/sendMessage"
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(url, json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True})
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram mesajı kabul etmedi: {data.get('description', 'bilinmeyen hata')}")
