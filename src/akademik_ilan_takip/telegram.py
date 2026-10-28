from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
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


def _source_catalog() -> dict[str, tuple[str, str]]:
    """Use the actual configured source URLs, never guessed announcement links."""
    path = Path(os.environ.get("SOURCES_FILE", "config/sources.json"))
    if not path.is_file() and not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / path
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
        return {
            item["id"]: (item["url"], item.get("kind", "official"))
            for item in records
            if isinstance(item, dict) and item.get("enabled", True)
        }
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def report_message(report: ScanReport) -> str:
    """A readable hourly digest with links to every source actually attempted."""
    finished = report.finished_at.astimezone(ZoneInfo("Europe/Istanbul"))
    catalog = _source_catalog()
    successful = sum(1 for source in report.sources if source.ok)
    total_found = sum(source.listings_found for source in report.sources)
    failed = len(report.sources) - successful

    lines = [
        "📚 AKADEMİK İLAN TAKİP | SAATLİK RAPOR",
        f"🗓️ {finished.strftime('%d.%m.%Y • %H:%M')} (Türkiye)",
        "",
        "📊 TARAMA ÖZETİ",
        f"🆕 Yeni tespit edilen ilan: {report.new_listings}",
        f"📄 Kaynaklarda incelenen duyuru: {total_found}",
        f"✅ Kontrolü tamamlanan kaynak: {successful}/{len(report.sources)}",
    ]
    if failed:
        lines.append(f"🟠 Kontrolü eksik kalan kaynak: {failed}")
    if report.new_listings == 0:
        lines.extend(["", "📭 Bu saat yeni bir ilan tespit edilmedi."])
        lines.append("Daha önce kaydedilen ilanlar her saat yeniden gönderilmez.")
    else:
        lines.append("📬 Yeni ilanların ayrıntıları ayrı mesajlarda paylaşıldı.")

    def source_group(source) -> str:
        if source.source_id in {"resmi_gazete", "ilan_gov", "kamuilan"}:
            return "🏛️ KAMU İLAN PORTALLARI"
        if catalog.get(source.source_id, ("", ""))[1] == "aggregator":
            return "📰 EK İLAN KAYNAKLARI"
        return "🎓 ÜNİVERSİTE DUYURULARI"

    for heading in (
        "🏛️ KAMU İLAN PORTALLARI",
        "🎓 ÜNİVERSİTE DUYURULARI",
        "📰 EK İLAN KAYNAKLARI",
    ):
        group = [source for source in report.sources if source_group(source) == heading]
        if not group:
            continue
        lines.extend(["", heading])
        for source in group:
            if source.ok and source.listings_found:
                status = f"{source.listings_found} duyuru incelendi"
                sign = "✅"
            elif source.ok:
                status = "bu taramada ilgili duyuru bulunmadı"
                sign = "✅"
            elif source.listings_found:
                status = f"{source.listings_found} duyuru incelendi; kontrol kısmen eksik"
                sign = "🟠"
            else:
                status = "kontrol tamamlanamadı"
                sign = "🟠"
            lines.append(f"{sign} {source.source_name} — {status}")
            url = catalog.get(source.source_id, ("", ""))[0]
            if url:
                lines.append(f"🔗 {url}")

    lines.extend([
        "",
        "ℹ️ Duyuru sayısı, yeni ve başvuruya açık ilan sayısı değildir.",
        "Bu rapor yalnızca botta tanımlı kaynakları kapsar; tüm üniversiteleri kapsamaz.",
    ])
    if failed:
        lines.append("Bazı kaynakların kontrolü eksik olduğundan yeni ilanlar gözden kaçmış olabilir.")
    return "\n".join(lines)[:4000]

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
