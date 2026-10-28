from datetime import date

from akademik_ilan_takip.sources import find_deadline, parse_turkish_date


def test_parses_numeric_turkish_date() -> None:
    assert parse_turkish_date("İlan tarihi 28.10.2026") == date(2026, 10, 28)


def test_parses_written_turkish_date() -> None:
    assert parse_turkish_date("Son gün 7 Kasım 2026") == date(2026, 11, 7)


def test_finds_deadline_near_marker() -> None:
    assert find_deadline("Başvuruların son başvuru tarihi: 05/11/2026 mesai bitimi") == date(2026, 11, 5)
