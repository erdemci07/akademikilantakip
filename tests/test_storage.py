from datetime import date

from akademik_ilan_takip.models import Analysis, Listing
from akademik_ilan_takip.storage import SqliteRepository


def listing(url: str = "https://example.edu.tr/ilan.pdf") -> Listing:
    return Listing("uni", "Örnek Üniversite", "https://example.edu.tr", url, "Öğretim Görevlisi", "metin", deadline=date(2026, 11, 1))


def analysis(category: str = "human_review") -> Analysis:
    return Analysis(category, "İnsan kontrolü", "belirsiz", "belirsiz", None, None, None, True, [])


def test_identity_deduplicates_same_official_url(tmp_path) -> None:
    repository = SqliteRepository(tmp_path / "test.db")
    assert repository.save_listing(listing(), analysis()) is True
    assert repository.save_listing(listing(), analysis()) is False


def test_eligible_filter_excludes_ineligible(tmp_path) -> None:
    repository = SqliteRepository(tmp_path / "test.db")
    repository.save_listing(listing("https://example.edu.tr/one.pdf"), analysis("ineligible"))
    repository.save_listing(listing("https://example.edu.tr/two.pdf"), analysis("conditional_eligible"))
    assert len(repository.recent_listings(eligible_only=True)) == 1
