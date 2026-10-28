from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from .analyzer import analyze_listing, without_ai
from .models import ScanReport
from .settings import Settings
from .sources import collect_all
from .storage import Repository


def is_relevant_open_notice(listing, today) -> bool:
    # No verified deadline means UNCONFIRMED, not definitely open.
    # Still send as a lead so a human can check the official application date.
    if listing.deadline is not None and listing.deadline < today:
        return False
    if listing.published_at is not None and (today - listing.published_at).days > 60:
        return False
    title = listing.title.lower()
    return "öğretim görevlisi" in listing.text[:50000].lower() or any(term in title for term in (
        "öğretim görevlisi", "öğretim elemanı", "ogretim gorevlisi",
        "ogretim elemani", "öğretim üyesi ve elemanı", "akademik personel",
        "akademik kadro", "akademik ilan",
    ))


async def run_scan(settings: Settings, repository: Repository) -> tuple[ScanReport, list[tuple]]:
    started = datetime.now(UTC)
    today = datetime.now(ZoneInfo("Europe/Istanbul")).date()
    listings, source_results = await collect_all(settings)
    new_items = []
    seen_in_run = set()
    eligible_count = 0
    for listing in listings:
        if listing.identity in seen_in_run:
            continue
        seen_in_run.add(listing.identity)
        # Do not spend on AI for unrelated, expired or old postings.
        relevant = is_relevant_open_notice(listing, today)
        if relevant:
            analysis = analyze_listing(listing, settings)
        else:
            analysis = without_ai()
        is_new = repository.save_listing(listing, analysis)
        if is_new and relevant:
            new_items.append((listing, analysis))
            if analysis.category in {"definitely_eligible", "conditional_eligible", "human_review"}:
                eligible_count += 1
    report = ScanReport(started, datetime.now(UTC), len(new_items), eligible_count, source_results)
    repository.save_report(report)
    return report, new_items
