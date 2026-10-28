from __future__ import annotations

import asyncio

from zoneinfo import ZoneInfo

import httpx

from .models import Analysis, Listing, ScanReport
from .settings import ConfigurationError, Settings

CATEGORY_LABELS = {
    "definitely_eligible": "Eğitim koşulları kesin uygun",
    "conditional_eligible": "ALES/dil nedeniyle koşullu uygun",
    "human_review": "Şartları insan kontrolünde — uygunluk kesin değil",
    "ineligible": "Uygun değil",
}


def _date(value) -> str:
    return value.isoformat() if value else "Doğrulanamadı"


def listing_message(listing: Listing, analysis: Analysis) -> str:
    official = listing.official_url if listing.official_verified else None
    lines = [
        f"📌 {listing.university or listing.source_name}",
        f"Duyuru: {listing.title[:260]}",
        f"Kadro: {(listing.position or 'Öğretim görevlisi içerip içermediği ayrıca doğrulanmalı')[:150]}",
        f"Kontenjan: {listing.quota or 'Doğrulanamadı'}",
        f"Son başvuru: {_date(listing.deadline)}",
        f"ALES: {(analysis.ales_requirement or 'Doğrulanamadı')[:180]}",
        f"YDS/YÖKDİL: {(analysis.language_requirement or 'Doğrulanamadı')[:180]}",
        f"Deneyim: {(analysis.experience_requirement or 'Doğrulanamadı')[:180]}",
        f"Lisans koşulu: {analysis.bachelors_match[:250]}",
        f"Yüksek lisans koşulu: {analysis.masters_match[:250]}",
        f"Değerlendirme: {CATEGORY_LABELS.get(analysis.category, analysis.category)}",
        f"Özet: {analysis.summary[:480]}",
        f"📄 {'Resmî ilan / PDF: ' + official if official else 'Resmî ilan bağlantısı doğrulanamadı'}",
    ]
    if listing.application_url:
        lines.append(f"📝 Başvuru bağlantısı: {listing.application_url}")
    lines.append(f"🔗 Duyuru sayfası: {listing.url}")
    if not listing.official_verified:
        lines.append("⚠️ Üçüncü taraf kaynağı — başvurmadan önce üniversite ilanını doğrulayın.")
    return "\n".join(lines)[:4000]


def report_message(report: ScanReport) -> str:
    finished = report.finished_at.astimezone(ZoneInfo("Europe/Istanbul")).strftime("%d.%m.%Y %H:%M (TR)")
    good = len(report.sources) - len(report.failed_sources)
    details = [
        f"{'✅' if result.ok else '⚠️'} {result.source_name}: "
        f"{result.listings_found} duyuru" + (f" — {result.error}" if result.error else "")
        for result in report.sources
    ]
    msg = (
        f"🔎 Akademik ilan saatlik raporu — {finished}\n"
        f"Kaynak başarısı: {good}/{len(report.sources)}\n"
        f"Yeni, süresi geçmemiş duyuru: {report.new_listings}\n"
        f"Uygun / potansiyel: {report.eligible_new_listings}\n"
    )
    if report.new_listings == 0:
        msg += "Bu saatlik kontrolde yeni uygun ilan bulunamadı.\n"
    if report.failed_sources:
        msg += f"⚠️ {len(report.failed_sources)} kaynak eksik: tarama Türkiye genelinde tam değil.\n"
    msg += "\nKaynaklar:\n" + ("\n".join(details) or "Kaynak yapılandırılmadı.")
    return msg[:4000]


async def send_message(
    settings: Settings, chat_id: int, text: str, *, allow_subscriber: bool = False
) -> None:
    settings.require_telegram()
    if not allow_subscriber and chat_id not in settings.authorized_ids and settings.authorized_ids:
        raise ConfigurationError("Bu chat ID yetkili listesinde değil.")
    if allow_subscriber and chat_id <= 0:
        raise ConfigurationError("Abonelik mesajı yalnızca özel sohbetlere gönderilebilir.")
    url = f"https://api.telegram.org/bot{settings.telegram_token}/sendMessage"
    async with httpx.AsyncClient(timeout=20) as client:
        for attempt in range(4):
            response = await client.post(url, json={
                "chat_id": chat_id, "text": text, "disable_web_page_preview": True,
            })
            if response.status_code == 429 and attempt < 3:
                retry_after = response.json().get("parameters", {}).get("retry_after", 2)
                await asyncio.sleep(max(1, min(float(retry_after), 30)))
                continue
            if response.status_code >= 500 and attempt < 3:
                await asyncio.sleep(min(2 ** attempt, 8))
                continue
            response.raise_for_status()
            data = response.json()
            if not data.get("ok"):
                raise RuntimeError("Telegram API yanıtı başarısız")
            return
