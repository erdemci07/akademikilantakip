from datetime import date

import pytest

from akademik_ilan_takip.models import Listing, SourceResult
from akademik_ilan_takip.scanner import run_scan
from akademik_ilan_takip.settings import Settings
from akademik_ilan_takip.storage import SqliteRepository


@pytest.mark.asyncio
async def test_expired_listing_is_not_reported_as_new(monkeypatch, tmp_path) -> None:
    item = Listing("source", "Kaynak", "https://example.edu", "https://example.edu/a", "İlan", "öğretim görevlisi", deadline=date(2020, 1, 1))
    async def fake_collect(settings):
        return [item], [SourceResult("source", "Kaynak", True, 1)]
    monkeypatch.setattr("akademik_ilan_takip.scanner.collect_all", fake_collect)
    settings = Settings(None, frozenset(), None, "x", "local", tmp_path / "db.sqlite", None, "x", tmp_path / "sources.json", 1, "test")
    report, fresh = await run_scan(settings, SqliteRepository(tmp_path / "db.sqlite"))
    assert report.new_listings == 0
    assert fresh == []


@pytest.mark.asyncio
async def test_source_failure_is_preserved_in_status_report(monkeypatch, tmp_path) -> None:
    async def fake_collect(settings):
        return [], [SourceResult("source", "Kaynak", False, error="HTTP 403")]

    monkeypatch.setattr("akademik_ilan_takip.scanner.collect_all", fake_collect)
    settings = Settings(
        None,
        frozenset(),
        None,
        "x",
        "local",
        tmp_path / "db.sqlite",
        None,
        "x",
        tmp_path / "sources.json",
        1,
        "test",
    )
    repository = SqliteRepository(tmp_path / "db.sqlite")
    report, _ = await run_scan(settings, repository)
    assert report.failed_sources[0].error == "HTTP 403"
    assert repository.last_report().failed_sources[0].error == "HTTP 403"
