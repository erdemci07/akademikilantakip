from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import date
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader

from .models import Listing, SourceResult
from .settings import Settings

KEYWORDS = (
    "öğretim görevlisi", "ogretim gorevlisi", "akademik personel", "öğretim elemanı",
    "yapay zekâ", "yapay zeka", "robotik", "bilgisayar programcılığı", "bilgisayar programciligi",
    "bilişim", "bilisim", "otomasyon", "matematik",
)
TURKISH_MONTHS = {
    "ocak": 1, "şubat": 2, "subat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "mayis": 5,
    "haziran": 6, "temmuz": 7, "ağustos": 8, "agustos": 8, "eylül": 9, "eylul": 9,
    "ekim": 10, "kasım": 11, "kasim": 11, "aralık": 12, "aralik": 12,
}


class SourceAccessError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SourceDefinition:
    id: str
    name: str
    url: str
    kind: str = "notice_page"
    enabled: bool = True


def load_sources(path: Path) -> list[SourceDefinition]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [SourceDefinition(**item) for item in raw if item.get("enabled", True)]


def parse_turkish_date(text: str) -> date | None:
    text = " ".join(text.lower().split())
    for pattern in (r"\b(\d{1,2})[./-](\d{1,2})[./-](20\d{2})\b", r"\b(\d{1,2})\s+([a-zçğıöşü]+)\s+(20\d{2})\b"):
        match = re.search(pattern, text)
        if not match:
            continue
        try:
            if pattern.startswith("\\b(\\d{1,2})[."):
                return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
            return date(int(match.group(3)), TURKISH_MONTHS[match.group(2)], int(match.group(1)))
        except (ValueError, KeyError):
            return None
    return None


def find_deadline(text: str) -> date | None:
    normalized = " ".join(text.split())
    markers = ("son başvuru", "başvuru son", "başvuruların son", "son gün")
    for marker in markers:
        index = normalized.lower().find(marker)
        if index >= 0:
            value = parse_turkish_date(normalized[index:index + 180])
            if value:
                return value
    return None


def _matches(text: str) -> bool:
    folded = text.lower()
    return any(keyword in folded for keyword in KEYWORDS)


def _is_official_link(base_url: str, candidate_url: str) -> bool:
    base, candidate = urlparse(base_url), urlparse(candidate_url)
    return candidate.scheme in {"http", "https"} and candidate.netloc == base.netloc


class NoticePageSource:
    def __init__(self, definition: SourceDefinition, client: httpx.AsyncClient):
        self.definition, self.client = definition, client

    async def collect(self) -> list[Listing]:
        response = await self.client.get(self.definition.url, follow_redirects=True)
        if response.status_code in {401, 403, 429}:
            raise SourceAccessError(f"erişim kısıtlaması (HTTP {response.status_code}); atlatılmadı")
        response.raise_for_status()
        if "captcha" in response.text.lower():
            raise SourceAccessError("CAPTCHA algılandı; atlatılmadı")
        soup = BeautifulSoup(response.text, "html.parser")
        candidates: dict[str, str] = {}
        for anchor in soup.find_all("a", href=True):
            label = anchor.get_text(" ", strip=True)
            href = urljoin(str(response.url), str(anchor["href"]))
            if not _is_official_link(str(response.url), href):
                continue
            if _matches(label) or href.lower().endswith(".pdf") and _matches(soup.get_text(" ", strip=True)):
                candidates[href] = label or href.rsplit("/", 1)[-1]
        # The root page itself may be a direct notice page.
        if _matches(soup.get_text(" ", strip=True)):
            candidates.setdefault(str(response.url), soup.title.get_text(strip=True) if soup.title else self.definition.name)
        return await asyncio.gather(*(self._to_listing(url, title) for url, title in candidates.items()))

    async def _to_listing(self, url: str, title: str) -> Listing:
        response = await self.client.get(url, follow_redirects=True)
        if response.status_code in {401, 403, 429}:
            raise SourceAccessError(f"ilan bağlantısı erişim kısıtlaması (HTTP {response.status_code})")
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        if url.lower().endswith(".pdf") or "application/pdf" in content_type:
            text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(response.content)).pages)
        else:
            text = BeautifulSoup(response.text, "html.parser").get_text(" ", strip=True)
        return Listing(
            source_id=self.definition.id, source_name=self.definition.name, source_url=self.definition.url,
            url=str(response.url), title=title[:500], text=text[:100_000],
            university=self.definition.name if self.definition.id not in {"resmi_gazete", "ilan_gov_tr"} else None,
            position="Öğretim Görevlisi" if "öğretim görevlisi" in text.lower() else None,
            published_at=parse_turkish_date(text), deadline=find_deadline(text),
        )


async def collect_all(settings: Settings) -> tuple[list[Listing], list[SourceResult]]:
    definitions = load_sources(settings.sources_file)
    headers = {"User-Agent": settings.user_agent, "Accept-Language": "tr-TR,tr;q=0.9"}
    async with httpx.AsyncClient(headers=headers, timeout=settings.request_timeout_seconds) as client:
        async def one(definition: SourceDefinition) -> tuple[list[Listing], SourceResult]:
            try:
                listings = await NoticePageSource(definition, client).collect()
                return listings, SourceResult(definition.id, definition.name, True, len(listings))
            except (httpx.HTTPError, SourceAccessError, ValueError) as exc:
                return [], SourceResult(definition.id, definition.name, False, error=str(exc)[:500])
        items = await asyncio.gather(*(one(source) for source in definitions))
    return [listing for listings, _ in items for listing in listings], [result for _, result in items]
