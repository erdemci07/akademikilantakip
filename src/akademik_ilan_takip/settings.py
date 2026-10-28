from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class ConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Settings:
    telegram_token: str | None
    authorized_ids: frozenset[int]
    openai_api_key: str | None
    openai_model: str
    database_backend: str
    sqlite_path: Path
    firebase_service_account_json: str | None
    firestore_prefix: str
    sources_file: Path
    request_timeout_seconds: float
    user_agent: str

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv()
        raw_ids = os.getenv("AUTHORIZED_TELEGRAM_IDS", "")
        try:
            authorized_ids = frozenset(int(value.strip()) for value in raw_ids.split(",") if value.strip())
        except ValueError as exc:
            raise ConfigurationError("AUTHORIZED_TELEGRAM_IDS yalnızca sayısal chat ID içermelidir.") from exc
        return cls(
            telegram_token=os.getenv("TELEGRAM_BOT_TOKEN") or None,
            authorized_ids=authorized_ids,
            openai_api_key=os.getenv("OPENAI_API_KEY") or None,
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            database_backend=os.getenv("DATABASE_BACKEND", "local").lower(),
            sqlite_path=Path(os.getenv("SQLITE_PATH", "data/ilanlar.db")),
            firebase_service_account_json=os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON") or None,
            firestore_prefix=os.getenv("FIRESTORE_COLLECTION_PREFIX", "akademik_ilan_takip"),
            sources_file=Path(os.getenv("SOURCES_FILE", "config/sources.json")),
            request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "25")),
            user_agent=os.getenv("USER_AGENT", "AkademikIlanTakip/0.1"),
        )

    def require_telegram(self) -> None:
        if not self.telegram_token:
            raise ConfigurationError("TELEGRAM_BOT_TOKEN tanımlı değil.")

    def require_production_database(self) -> None:
        if self.database_backend != "firestore":
            raise ConfigurationError("Zamanlanmış üretim taraması için DATABASE_BACKEND=firestore zorunludur.")
        if not self.firebase_service_account_json:
            raise ConfigurationError("FIREBASE_SERVICE_ACCOUNT_JSON tanımlı değil.")
        try:
            json.loads(self.firebase_service_account_json)
        except json.JSONDecodeError as exc:
            raise ConfigurationError("FIREBASE_SERVICE_ACCOUNT_JSON geçerli JSON değil.") from exc
