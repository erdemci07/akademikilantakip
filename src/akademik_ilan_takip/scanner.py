from __future__ import annotations

from datetime import UTC, date, datetime

from .analyzer import analyze_listing
from .models import ScanReport
from .settings import Settings
from .sources import collect_all
from .storage import Repository


async def run_scan(settings: Settings, repository: Repository) -> tuple[ScanReport, list[tuple]]:
    started = datetime.now(UTC)
    listings, source_results = await collect_all(settings)
    new_items = []
    eligible_count = 0
    for listing in listings:
        # No deadline means unknown, not expired. Expired items are stored only if already known, never notified as new.
        expired = listing.deadline is not None and listing.deadline < date.today()
        analysis = analyze_listing(listing, settings)
        is_new = repository.save_listing(listing, analysis)
        if is_new and not expired:
            new_items.append((listing, analysis))
            if analysis.category in {"definitely_eligible", "conditional_eligible", "human_review"}:
                eligible_count += 1
    report = ScanReport(started, datetime.now(UTC), len(new_items), eligible_count, source_results)
    repository.save_report(report)
    return report, new_items
