from datetime import UTC, date, datetime, timedelta

from akademik_ilan_takip.history import initial_history_summary
from akademik_ilan_takip.models import Analysis, Listing


class FakeRepo:
    def __init__(self, records):
        self.records = records

    def recent_listings(self, eligible_only, limit):
        assert eligible_only is False
        assert limit >= 8
        return self.records


def sample(url, today, *, expiry=None, discovered_days_ago=0, title="Öğretim Görevlisi Alım İlanı"):
    listing = Listing(
        "uni", "Üniversite", "https://uni.edu.tr", url, title,
        "Öğretim Görevlisi alımı",
        deadline=expiry,
        discovered_at=datetime(2026, 10, 28, 9, tzinfo=UTC) - timedelta(days=discovered_days_ago),
        official_url=url,
        official_verified=True,
    )
    analysis = Analysis("human_review", "Kontrol", "?", "?", None, None, None, True, [])
    return listing, analysis


def test_first_history_includes_active_and_unverified_deadline():
    today = date(2026, 10, 28)
    repo = FakeRepo([
        sample("https://uni.edu.tr/a", today, expiry=date(2026, 11, 5)),
        sample("https://uni.edu.tr/b", today),
    ])
    text = initial_history_summary(repo, today=today)
    assert "https://uni.edu.tr/a" in text
    assert "https://uni.edu.tr/b" in text
    assert "05.11.2026" in text
    assert "Duyurudan doğrulayın" in text


def test_history_excludes_expired_and_old_notices():
    today = date(2026, 10, 28)
    repo = FakeRepo([
        sample("https://uni.edu.tr/old-deadline", today, expiry=date(2026, 10, 20)),
        sample("https://uni.edu.tr/old-discovery", today, discovered_days_ago=65),
        sample("https://uni.edu.tr/fresh", today),
    ])
    text = initial_history_summary(repo, today=today)
    assert "https://uni.edu.tr/fresh" in text
    assert "old-deadline" not in text
    assert "old-discovery" not in text


def test_history_empty_message_and_maximum():
    today = date(2026, 10, 28)
    assert "bulunamadı" in initial_history_summary(FakeRepo([]), today=today)
    repo = FakeRepo([sample(f"https://uni.edu.tr/{i}", today) for i in range(20)])
    text = initial_history_summary(repo, today=today)
    assert text.count("📌") == 8
    assert len(text) < 4000
