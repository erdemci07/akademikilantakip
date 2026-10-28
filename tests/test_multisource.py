from datetime import date

import httpx
import pytest
from bs4 import BeautifulSoup

from akademik_ilan_takip.analyzer import without_ai
from akademik_ilan_takip.models import Listing
from akademik_ilan_takip.sources import (
    NoticePageSource,
    SourceDefinition,
    candidate_links,
    find_document_and_application,
    is_announcement,
    is_official_url,
    parse_turkish_date,
)
from akademik_ilan_takip.telegram import listing_message


def test_index_filters_results_and_keeps_recruitment():
    html = '''<a href="/d/1">Öğretim Görevlisi Alım İlanı</a>
              <a href="/d/2">Öğretim Görevlisi Ön Değerlendirme Sonuçları</a>
              <a href="/d/3">4/B Sözleşmeli Personel Alımı</a>'''
    links = candidate_links(BeautifulSoup(html, "html.parser"), "https://personel.uni.edu.tr/duyurular", "official", 12)
    assert links == [("https://personel.uni.edu.tr/d/1", "Öğretim Görevlisi Alım İlanı")]
    assert is_announcement("2026 Öğretim Elemanı Alım İlanı")
    assert not is_announcement("Öğretim Görevlisi Nihai Değerlendirme Sonuçları")


def test_document_and_application_links_are_separate():
    html = '''<a href="https://personel.uni.edu.tr/docs/ilan.pdf">İlan metni için tıklayınız</a>
              <a href="https://basvuru.uni.edu.tr/giris">Online başvuru yapmak için</a>
              <a href="https://personel.uni.edu.tr/docs/yonetmelik.pdf">Yönetmelik</a>'''
    pdf, apply = find_document_and_application(BeautifulSoup(html, "html.parser"), "https://personel.uni.edu.tr/duyuru/1")
    assert pdf == "https://personel.uni.edu.tr/docs/ilan.pdf"
    assert apply == "https://basvuru.uni.edu.tr/giris"


def test_third_party_not_assumed_official():
    assert not is_official_url("https://ilan.memurlar.net/ilan/123")
    assert is_official_url("https://personel.bogazici.edu.tr/duyuru")
    item = Listing("memurlar", "Memurlar", "https://ilan.memurlar.net", "https://ilan.memurlar.net/1", "Öğretim Görevlisi Alım İlanı", "metin")
    message = listing_message(item, without_ai())
    assert "Resmî ilan bağlantısı doğrulanamadı" in message
    assert "Üçüncü taraf" in message


def test_same_official_pdf_cross_source_deduplicated():
    first = Listing("uni", "Uni", "https://uni.edu.tr", "https://uni.edu.tr/duyuru/1", "Öğretim Görevlisi Alım İlanı", "x", official_url="https://uni.edu.tr/ilan.pdf")
    second = Listing("secondary", "Memurlar", "https://ilan.memurlar.net", "https://ilan.memurlar.net/1", "Öğretim Görevlisi Alım İlanı", "x", official_url="https://uni.edu.tr/ilan.pdf")
    assert first.identity == second.identity


@pytest.mark.asyncio
async def test_source_fetches_announcement_without_false_index_listing():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/duyurular":
            return httpx.Response(200, text='<a href="/detail">Öğretim Görevlisi Alım İlanı</a>')
        if request.url.path == "/detail":
            return httpx.Response(200, text="Son Başvuru Tarihi: 05.11.2026. Öğretim Görevlisi başvuru koşulları.")
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = NoticePageSource(SourceDefinition("uni", "Üniversite", "https://personel.uni.edu.tr/duyurular"), client)
        listings = await source.collect()
    assert len(listings) == 1
    assert listings[0].deadline == date(2026, 11, 5)
    assert listings[0].official_verified
    assert listings[0].official_url == "https://personel.uni.edu.tr/detail"


def test_date_parser_handles_two_variants():
    assert parse_turkish_date("28.10.2026") == date(2026, 10, 28)
    assert parse_turkish_date("7 Kasım 2026") == date(2026, 11, 7)

@pytest.mark.asyncio
async def test_one_bad_notice_does_not_discard_successful_notice():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/duyurular":
            return httpx.Response(200, text='''
                <a href="/blocked">Öğretim Görevlisi Alım İlanı 1</a>
                <a href="/working">Öğretim Görevlisi Alım İlanı 2</a>''')
        if request.url.path == "/blocked":
            return httpx.Response(403)
        if request.url.path == "/working":
            return httpx.Response(200, text="Öğretim Görevlisi alımı. Son başvuru 07.11.2026")
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = NoticePageSource(SourceDefinition("uni", "Üniversite", "https://personel.uni.edu.tr/duyurular"), client)
        listings = await source.collect()
    assert len(listings) == 1
    assert listings[0].deadline == date(2026, 11, 7)
    assert source.errors and "HTTP 403" in source.errors[0]
