from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from hashlib import sha256
from typing import Any


@dataclass(frozen=True, slots=True)
class CandidateProfile:
    bachelor: str = "Fen Fakültesi Matematik"
    masters: str = "Yapay Zekâ ve Robotik (tezli, tamamlandı)"
    ales_score: float | None = None
    language_score: float | None = None


@dataclass(slots=True)
class Listing:
    source_id: str
    source_name: str
    source_url: str
    url: str
    title: str
    text: str
    university: str | None = None
    position: str | None = None
    quota: str | None = None
    published_at: date | None = None
    deadline: date | None = None
    discovered_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def identity(self) -> str:
        raw = f"{self.source_id}|{self.url.strip().lower()}"
        return sha256(raw.encode()).hexdigest()

    @property
    def content_hash(self) -> str:
        raw = " ".join((self.title + " " + self.text).lower().split())
        return sha256(raw.encode()).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for key in ("published_at", "deadline"):
            value[key] = value[key].isoformat() if value[key] else None
        value["discovered_at"] = self.discovered_at.isoformat()
        return value


@dataclass(frozen=True, slots=True)
class Analysis:
    category: str
    summary: str
    bachelors_match: str
    masters_match: str
    ales_requirement: str | None
    language_requirement: str | None
    experience_requirement: str | None
    needs_human_review: bool
    evidence: list[str]


@dataclass(frozen=True, slots=True)
class SourceResult:
    source_id: str
    source_name: str
    ok: bool
    listings_found: int = 0
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ScanReport:
    started_at: datetime
    finished_at: datetime
    new_listings: int
    eligible_new_listings: int
    sources: list[SourceResult]

    @property
    def failed_sources(self) -> list[SourceResult]:
        return [result for result in self.sources if not result.ok]
