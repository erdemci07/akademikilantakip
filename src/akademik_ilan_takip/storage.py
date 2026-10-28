from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from .models import Analysis, Listing, ScanReport
from .settings import ConfigurationError, Settings


class Repository(ABC):
    @abstractmethod
    def save_listing(self, listing: Listing, analysis: Analysis) -> bool: ...

    @abstractmethod
    def recent_listings(self, eligible_only: bool, limit: int = 10) -> list[tuple[Listing, Analysis]]: ...

    @abstractmethod
    def save_report(self, report: ScanReport) -> None: ...

    @abstractmethod
    def last_report(self) -> ScanReport | None: ...


def _listing_from_dict(value: dict) -> Listing:
    from datetime import date

    copy = dict(value)
    copy["published_at"] = date.fromisoformat(copy["published_at"]) if copy.get("published_at") else None
    copy["deadline"] = date.fromisoformat(copy["deadline"]) if copy.get("deadline") else None
    copy["discovered_at"] = datetime.fromisoformat(copy["discovered_at"])
    return Listing(**copy)


class SqliteRepository(Repository):
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS listings (
              identity TEXT PRIMARY KEY, content_hash TEXT NOT NULL,
              listing_json TEXT NOT NULL, analysis_json TEXT NOT NULL,
              first_seen TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS scan_reports (
              id INTEGER PRIMARY KEY AUTOINCREMENT, report_json TEXT NOT NULL, created_at TEXT NOT NULL
            );
            """
        )
        self.connection.commit()

    def save_listing(self, listing: Listing, analysis: Analysis) -> bool:
        existing = self.connection.execute(
            "SELECT content_hash FROM listings WHERE identity = ?", (listing.identity,)
        ).fetchone()
        is_new = existing is None
        now = datetime.now(UTC).isoformat()
        self.connection.execute(
            """INSERT INTO listings(identity, content_hash, listing_json, analysis_json, first_seen, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(identity) DO UPDATE SET content_hash=excluded.content_hash,
                 listing_json=excluded.listing_json, analysis_json=excluded.analysis_json, updated_at=excluded.updated_at""",
            (
                listing.identity,
                listing.content_hash,
                json.dumps(listing.as_dict(), ensure_ascii=False),
                json.dumps(asdict(analysis), ensure_ascii=False),
                now,
                now,
            ),
        )
        self.connection.commit()
        return is_new

    def recent_listings(self, eligible_only: bool, limit: int = 10) -> list[tuple[Listing, Analysis]]:
        rows = self.connection.execute(
            "SELECT listing_json, analysis_json FROM listings ORDER BY updated_at DESC LIMIT ?", (limit * 3,)
        ).fetchall()
        output: list[tuple[Listing, Analysis]] = []
        for row in rows:
            listing = _listing_from_dict(json.loads(row["listing_json"]))
            analysis = Analysis(**json.loads(row["analysis_json"]))
            if not eligible_only or analysis.category in {"definitely_eligible", "conditional_eligible", "human_review"}:
                output.append((listing, analysis))
            if len(output) == limit:
                break
        return output

    def save_report(self, report: ScanReport) -> None:
        payload = {
            "started_at": report.started_at.isoformat(), "finished_at": report.finished_at.isoformat(),
            "new_listings": report.new_listings, "eligible_new_listings": report.eligible_new_listings,
            "sources": [asdict(source) for source in report.sources],
        }
        self.connection.execute(
            "INSERT INTO scan_reports(report_json, created_at) VALUES (?, ?)",
            (json.dumps(payload, ensure_ascii=False), datetime.now(UTC).isoformat()),
        )
        self.connection.commit()

    def last_report(self) -> ScanReport | None:
        row = self.connection.execute("SELECT report_json FROM scan_reports ORDER BY id DESC LIMIT 1").fetchone()
        if not row:
            return None
        from .models import SourceResult

        data = json.loads(row["report_json"])
        return ScanReport(
            started_at=datetime.fromisoformat(data["started_at"]), finished_at=datetime.fromisoformat(data["finished_at"]),
            new_listings=data["new_listings"], eligible_new_listings=data["eligible_new_listings"],
            sources=[SourceResult(**item) for item in data["sources"]],
        )


class FirestoreRepository(Repository):
    """Firestore adapter. Scheduled runs use this persistent backend."""

    def __init__(self, service_account_json: str, prefix: str):
        try:
            import firebase_admin
            from firebase_admin import credentials, firestore
        except ImportError as exc:  # pragma: no cover - dependency is production-only
            raise ConfigurationError("firebase-admin paketi kurulu değil.") from exc
        try:
            account = json.loads(service_account_json)
        except json.JSONDecodeError as exc:
            raise ConfigurationError("FIREBASE_SERVICE_ACCOUNT_JSON geçerli JSON değil.") from exc
        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.Certificate(account))
        self.db = firestore.client()
        self.listings = self.db.collection(f"{prefix}_listings")
        self.reports = self.db.collection(f"{prefix}_reports")

    def save_listing(self, listing: Listing, analysis: Analysis) -> bool:
        doc = self.listings.document(listing.identity)
        current = doc.get()
        is_new = not current.exists
        doc.set({"listing": listing.as_dict(), "analysis": asdict(analysis), "updated_at": datetime.now(UTC).isoformat()}, merge=True)
        return is_new

    def recent_listings(self, eligible_only: bool, limit: int = 10) -> list[tuple[Listing, Analysis]]:
        records = self.listings.order_by("updated_at", direction="DESCENDING").limit(limit * 3).stream()
        output = []
        for record in records:
            data = record.to_dict()
            listing, analysis = _listing_from_dict(data["listing"]), Analysis(**data["analysis"])
            if not eligible_only or analysis.category in {"definitely_eligible", "conditional_eligible", "human_review"}:
                output.append((listing, analysis))
            if len(output) == limit:
                break
        return output

    def save_report(self, report: ScanReport) -> None:
        self.reports.document(report.finished_at.isoformat()).set({
            "started_at": report.started_at.isoformat(), "finished_at": report.finished_at.isoformat(),
            "new_listings": report.new_listings, "eligible_new_listings": report.eligible_new_listings,
            "sources": [asdict(item) for item in report.sources],
        })

    def last_report(self) -> ScanReport | None:
        from .models import SourceResult
        records = list(self.reports.order_by("finished_at", direction="DESCENDING").limit(1).stream())
        if not records:
            return None
        data = records[0].to_dict()
        return ScanReport(datetime.fromisoformat(data["started_at"]), datetime.fromisoformat(data["finished_at"]), data["new_listings"], data["eligible_new_listings"], [SourceResult(**item) for item in data["sources"]])


def create_repository(settings: Settings, production: bool = False) -> Repository:
    if production:
        settings.require_production_database()
    if settings.database_backend == "firestore":
        if not settings.firebase_service_account_json:
            raise ConfigurationError("FIREBASE_SERVICE_ACCOUNT_JSON tanımlı değil.")
        return FirestoreRepository(settings.firebase_service_account_json, settings.firestore_prefix)
    if settings.database_backend == "local":
        return SqliteRepository(settings.sqlite_path)
    raise ConfigurationError("DATABASE_BACKEND 'local' veya 'firestore' olmalıdır.")
