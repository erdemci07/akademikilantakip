from pathlib import Path

from akademik_ilan_takip.analyzer import analyze_listing
from akademik_ilan_takip.models import Listing
from akademik_ilan_takip.settings import Settings


def test_missing_ai_key_requires_human_review() -> None:
    settings = Settings(
        None, frozenset(), None, "x", "local", Path("x"), None, "x", Path("x"), 1, "test"
    )
    item = Listing("source", "Kaynak", "https://example.edu", "https://example.edu/a", "İlan", "metin")
    result = analyze_listing(item, settings)
    assert result.category == "human_review"
    assert result.needs_human_review is True
