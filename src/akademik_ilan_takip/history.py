"""Create a one-time welcome digest from previously stored, still-relevant notices."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .scanner import is_relevant_open_notice
from .storage import Repository


def initial_history_summary(
    repository: Repository, *, today: date | None = None, max_items: int = 8
) -> str:
    """Send a compact digest, not an unbounded backlog, on first /start."""
    if today is None:
        today = datetime.now(ZoneInfo("Europe/Istanbul")).date()
    candidates = repository.recent_listings(eligible_only=False, limit=50)
    candidates.sort(
        key=lambda record: record[0].discovered_at,
        reverse=True,
    )
    lines = [
        "📚 İLK ABONELİK | GEÇMİŞTEN GÜNCEL İLANLAR",
        "",
        "Botun daha önce kaydettiği, süresi geçmiş olduğu bilinmeyen akademik duyurular:",
    ]
    count = 0
    seen: set[str] = set()
    for listing, _analysis in candidates:
        if listing.identity in seen:
            continue
        seen.add(listing.identity)
        if listing.discovered_at.date() < today - timedelta(days=60):
            continue
        if not is_relevant_open_notice(listing, today):
            continue
        url = listing.official_url if listing.official_verified and listing.official_url else listing.url
        if not url.startswith(("https://", "http://")):
            continue
        title = " ".join(listing.title.split())[:145]
        institution = (listing.university or listing.source_name)[:75]
        deadline = listing.deadline.strftime("%d.%m.%Y") if listing.deadline else "Duyurudan doğrulayın"
        link_type = "Resmî ilan" if listing.official_verified else "Duyuru bağlantısı (doğrulanmalı)"
        entry = (
            f"\n\n{count + 1}. {institution}\n"
            f"📌 {title}\n"
            f"📅 Son başvuru: {deadline}\n"
            f"🔗 {link_type}: {url[:650]}"
        )
        if len("\n".join(lines)) + len(entry) > 3700:
            break
        lines.append(entry)
        count += 1
        if count >= max_items:
            break
    if count == 0:
        return (
            "📚 GEÇMİŞ İLANLAR\n"
            "Şu anda kayıtlı, güncel olabilecek akademik ilan bulunamadı. "
            "Yeni duyurular saatlik bildirimle paylaşılacak."
        )
    lines.extend([
        "",
        "ℹ️ Liste yeni yayımlanan ilanlar değil, daha önce kaydedilen duyurulardır.",
        "Başvuru süresini ve şartlarını bağlantıdan mutlaka kontrol edin.",
        "Son kayıtları tekrar görmek için /sonilanlar yazabilirsiniz.",
    ])
    return "\n".join(lines)[:4000]
