"""Bounded, resilient academic announcement discovery from official and secondary indexes.

Secondary aggregators are discovery-only: they cannot assert official verification.
The current stage is ANNOUNCEMENT level, not reliable PDF table-row extraction.
"""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader

from .models import Listing, SourceResult
from .settings import Settings

ACADEMIC_PHRASES = (
    "öğretim görevlisi", "ogretim gorevlisi", "öğretim elemanı", "ogretim elemani",
    "öğretim üyesi", "ogretim uyesi", "araştırma görevlisi", "arastirma gorevlisi",
    "akademik personel", "akademik kadro", "akademik ilan", "öğretim üyesi dışındaki",
    "ogretim uyesi disindaki", "öğretim üyesi ve elemanı",
)
NOT_NEW_PHRASES = (
    "ön değerlendirme", "on degerlendirme", "nihai", "sınav sonucu", "sinav sonucu",
    "değerlendirme sonucu", "degerlendirme sonucu", "yedek aday", "başvuru sonucu",
    "basvuru sonucu", "sınav sonuç", "sinav sonuc", "kazanan aday",
)
RECRUITMENT_PHRASES = ("alım", "alim", "ilan", "kadrolar", "başvuru", "basvuru")
MONTHS = {
    "ocak": 1, "şubat": 2, "subat": 2, "mart": 3, "nisan": 4, "mayıs": 5,
    "mayis": 5, "haziran": 6, "temmuz": 7, "ağustos": 8, "agustos": 8,
    "eylül": 9, "eylul": 9, "ekim": 10, "kasım": 11, "kasim": 11,
    "aralık": 12, "aralik": 12,
}
NUMERIC_DATE = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](20\d{2})\b")
WORDS_DATE = re.compile(r"\b(\d{1,2})\s+([a-zçğıöşü]+)\s+(20\d{2})\b")
PDF_LIMIT = 12 * 1024 * 1024


class SourceAccessError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SourceDefinition:
    id: str
    name: str
    url: str
    kind: str = "official"   # 'official' or 'aggregator'
    enabled: bool = True
    max_candidates: int = 12


def load_sources(path: Path) -> list[SourceDefinition]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    definitions = [SourceDefinition(**item) for item in raw if item.get("enabled", True)]
    if len({source.id for source in definitions}) != len(definitions):
        raise ValueError("Kaynak kimlikleri benzersiz olmalıdır")
    for source in definitions:
        if source.kind not in {"official", "aggregator", "notice_page", "resmigazete_daily"}:
            raise ValueError(f"Bilinmeyen kaynak türü: {source.kind}")
        if source.max_candidates < 1 or source.max_candidates > 30:
            raise ValueError("max_candidates 1–30 aralığında olmalıdır")
    return definitions


def parse_turkish_date(text: str) -> date | None:
    value = " ".join(text.lower().split())
    match = NUMERIC_DATE.search(value)
    if match:
        try:
            return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
        except ValueError:
            pass
    match = WORDS_DATE.search(value)
    if match:
        try:
            return date(int(match.group(3)), MONTHS[match.group(2)], int(match.group(1)))
        except (ValueError, KeyError):
            pass
    return None


def find_deadline(text: str) -> date | None:
    normalized = " ".join(text.split())
    markers = ("son başvuru", "başvuru bitiş", "başvuru son", "başvuruların son", "son gün")
    lower = normalized.lower()
    for marker in markers:
        idx = lower.find(marker)
        if idx >= 0:
            result = parse_turkish_date(normalized[idx:idx + 115])
            if result:
                return result
    return None


def is_announcement(title: str) -> bool:
    title = " ".join(title.lower().split())
    if title in {"akademik ilanlar", "akademik personel", "akademik duyurular", "öğretim elemanı", "öğretim üyesi", "academic announcements"}:
        return False
    if any(bad in title for bad in NOT_NEW_PHRASES):
        return False
    return any(term in title for term in ACADEMIC_PHRASES) and any(
        term in title for term in RECRUITMENT_PHRASES
    )


def is_official_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (
        host.endswith(".edu.tr") or host.endswith(".gov.tr")
        or host in {"edu.tr", "gov.tr"}
    )


def same_host(left: str, right: str) -> bool:
    return urlparse(left).hostname == urlparse(right).hostname


def candidate_links(soup: BeautifulSoup, base_url: str, kind: str, limit: int) -> list[tuple[str, str]]:
    found: dict[str, str] = {}
    for anchor in soup.find_all("a", href=True):
        title = anchor.get_text(" ", strip=True)
        if not is_announcement(title):
            continue
        url = urljoin(base_url, anchor["href"])
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            continue
        # The index is a trusted page. Follow its own article links, or outbound
        # official academic institution links from a secondary aggregator.
        if not same_host(base_url, url) and not (kind == "aggregator" and is_official_url(url)):
            continue
        found.setdefault(url, title[:400])
        if len(found) >= limit:
            break
    return list(found.items())


def find_document_and_application(soup: BeautifulSoup, base_url: str) -> tuple[str | None, str | None]:
    """Return explicitly linked official PDF (if any) and actual application link.

    Never synthesize a likely link from university name or assume a homepage is an
    application URL. Exclude rules, regulations and exam/result PDFs.
    """
    pdf_candidates: list[tuple[int, str]] = []
    application: str | None = None
    for anchor in soup.find_all("a", href=True):
        label = anchor.get_text(" ", strip=True).lower()
        href = urljoin(base_url, anchor["href"])
        if not is_official_url(href):
            continue
        if any(bad in label for bad in ("yönetmelik", "yonetmelik", "form örneği", "form ornegi", "sınav sonucu", "sinav sonucu")):
            continue
        if ("başvuru" in label or "basvuru" in label) and any(
            term in label for term in ("online", "çevrim", "sistem", "yapmak", "yeri", "başvur", "basvur")
        ) and not href.lower().split("?")[0].endswith(".pdf"):
            application = application or href
        if href.lower().split("?")[0].endswith(".pdf"):
            score = 2 if any(word in label for word in ("ilan", "kadro", "metni", "tıklay", "tiklay")) else 0
            if any(word in label for word in ("değerlendirme", "degerlendirme", "sonuç", "sonuc")):
                continue
            pdf_candidates.append((score, href))
    pdf_candidates.sort(key=lambda x: x[0], reverse=True)
    return (pdf_candidates[0][1] if pdf_candidates else None), application


class NoticePageSource:
    def __init__(self, definition: SourceDefinition, client: httpx.AsyncClient):
        self.definition = definition
        self.client = client
        self.errors: list[str] = []

    async def _get(self, url: str) -> httpx.Response:
        response = await self.client.get(url, follow_redirects=True)
        if response.status_code in {401, 403, 429}:
            raise SourceAccessError(f"HTTP {response.status_code} erişim kısıtı: {url}")
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        if "text/html" in content_type and "captcha" in response.text.lower():
            raise SourceAccessError(f"CAPTCHA görüldü: {url}")
        return response

    @staticmethod
    def _text(response: httpx.Response) -> str:
        mime = response.headers.get("content-type", "").lower()
        if "pdf" in mime or response.url.path.lower().endswith(".pdf"):
            if len(response.content) > PDF_LIMIT:
                raise SourceAccessError("PDF boyut sınırını aşıyor")
            try:
                text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(response.content)).pages)
            except Exception as exc:
                raise SourceAccessError(f"PDF ayrıştırma hatası: {type(exc).__name__}") from exc
            if not text.strip():
                raise SourceAccessError("PDF taranmış görsel; metin çıkarılamadı")
            return text[:100_000]
        return BeautifulSoup(response.text, "html.parser").get_text(" ", strip=True)[:100_000]

    async def collect(self) -> list[Listing]:
        if self.definition.kind == "resmigazete_daily":
            return await self._collect_gazette_daily()
        response = await self._get(self.definition.url)
        soup = BeautifulSoup(response.text, "html.parser")
        links = candidate_links(
            soup, str(response.url), self.definition.kind,
            self.definition.max_candidates,
        )
        output: list[Listing] = []
        for url, title in links:
            try:
                output.append(await self._to_listing(url, title))
            except (httpx.HTTPError, SourceAccessError, ValueError) as exc:
                self.errors.append(str(exc)[:160])
        return output

    async def _collect_gazette_daily(self) -> list[Listing]:
        # Gazette's published 'Çeşitli İlânlar' daily page, *not* an invented PDF.
        today = datetime.now(ZoneInfo("Europe/Istanbul")).date()
        links: dict[str, str] = {}
        for offset in range(3):
            day = today - timedelta(days=offset)
            prefix = day.strftime("%Y/%m/%Y%m%d")
            index = f"https://www.resmigazete.gov.tr/ilanlar/eskiilanlar/{prefix}-4.htm"
            try:
                response = await self._get(index)
            except (httpx.HTTPError, SourceAccessError) as exc:
                self.errors.append(f"{day.isoformat()}: {str(exc)[:100]}")
                continue
            soup = BeautifulSoup(response.text, "html.parser")
            for anchor in soup.find_all("a", href=True):
                href = urljoin(str(response.url), anchor["href"])
                label = anchor.get_text(" ", strip=True)
                if not href.lower().split("?")[0].endswith(".pdf") or not is_official_url(href):
                    continue
                # The official index can label PDFs with university name only.
                context = anchor.parent.get_text(" ", strip=True).lower() if anchor.parent else label.lower()
                if not any(word in (label + " " + context).lower() for word in
                           ("üniversite", "ogretim", "öğretim", "yüksekokul", "yuksekokul")):
                    continue
                links.setdefault(href, (label or "Üniversite ilan PDF'si")[:400])
                if len(links) >= self.definition.max_candidates:
                    break
            if len(links) >= self.definition.max_candidates:
                break
        output: list[Listing] = []
        for url, title in links.items():
            try:
                output.append(await self._to_listing(url, title))
            except (httpx.HTTPError, SourceAccessError, ValueError) as exc:
                self.errors.append(str(exc)[:140])
        return output

    async def _to_listing(self, url: str, title: str) -> Listing:
        response = await self._get(url)
        location = str(response.url)
        mimetype = response.headers.get("content-type", "").lower()
        pdf = "pdf" in mimetype or response.url.path.lower().endswith(".pdf")
        document: str | None = location if pdf and is_official_url(location) else None
        application: str | None = None
        text = self._text(response)
        if not pdf:
            soup = BeautifulSoup(response.text, "html.parser")
            document, application = find_document_and_application(soup, location)
            if document:
                try:
                    doc_response = await self._get(document)
                    document = str(doc_response.url)
                    pdf_text = self._text(doc_response)
                    # Preserve detail page's application/deadline data as well.
                    text = (text[:18_000] + "\n\nEKLİ İLAN METNİ:\n" + pdf_text)[:100_000]
                except (httpx.HTTPError, SourceAccessError, ValueError) as exc:
                    self.errors.append(f"Ek PDF okunamadı: {str(exc)[:110]}")
                    document = None
        verified = is_official_url(location) or (document is not None and is_official_url(document))
        if self.definition.kind == "aggregator" and not verified and not pdf:
            # A third-party article can link to a university's official notice.
            # Verify the target exists before labeling it official.
            for anchor in soup.find_all("a", href=True):
                target = urljoin(location, anchor["href"])
                label = anchor.get_text(" ", strip=True).lower()
                if not is_official_url(target) or not any(
                    marker in label for marker in ("resmî", "resmi", "kaynak", "ilan", "duyuru")
                ):
                    continue
                try:
                    official_response = await self._get(target)
                    document = str(official_response.url)
                    verified = is_official_url(document)
                    if verified and "pdf" in official_response.headers.get("content-type", "").lower():
                        text = (text[:18_000] + "\nEKLİ RESMÎ METİN:\n" + self._text(official_response))[:100_000]
                except (httpx.HTTPError, SourceAccessError, ValueError):
                    continue
                if verified:
                    break
        university = self.definition.name if self.definition.kind != "aggregator" else None
        if university is None:
            match = re.search(r"(.+? Üniversitesi)", title)
            university = match.group(1) if match else None
        return Listing(
            source_id=self.definition.id,
            source_name=self.definition.name,
            source_url=self.definition.url,
            url=location,
            title=title,
            text=text,
            university=university,
            position="Öğretim Görevlisi" if "öğretim görevlisi" in text.lower() or "öğretim görevlisi" in title.lower() else None,
            published_at=parse_turkish_date(title) or parse_turkish_date(text[:1800]),
            deadline=find_deadline(text),
            official_url=document or (location if verified else None),
            application_url=application,
            official_verified=verified,
        )


async def collect_all(settings: Settings) -> tuple[list[Listing], list[SourceResult]]:
    definitions = load_sources(settings.sources_file)
    headers = {"User-Agent": settings.user_agent, "Accept-Language": "tr-TR,tr;q=0.9"}
    limiter = asyncio.Semaphore(5)
    async with httpx.AsyncClient(headers=headers, timeout=settings.request_timeout_seconds) as client:
        async def one(definition: SourceDefinition) -> tuple[list[Listing], SourceResult]:
            async with limiter:
                source = NoticePageSource(definition, client)
                try:
                    listings = await source.collect()
                    return listings, SourceResult(
                        definition.id, definition.name, not source.errors,
                        len(listings), "; ".join(source.errors[:2]) if source.errors else None,
                    )
                except (httpx.HTTPError, SourceAccessError, ValueError) as exc:
                    return [], SourceResult(definition.id, definition.name, False, error=str(exc)[:350])
        batches = await asyncio.gather(*(one(source) for source in definitions))
    listings = [record for records, _ in batches for record in records]
    return listings, [status for _, status in batches]
