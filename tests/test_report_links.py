import json
from datetime import UTC, datetime
from pathlib import Path

from akademik_ilan_takip.models import ScanReport, SourceResult
from akademik_ilan_takip.telegram import report_message


def test_report_has_every_source_link_and_no_raw_errors(monkeypatch, tmp_path):
    sources = json.loads(Path("config/sources.json").read_text(encoding="utf-8"))
    source_file = tmp_path / "sources.json"
    source_file.write_text(json.dumps(sources, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("SOURCES_FILE", str(source_file))

    errors = {"ilan_gov", "kamuilan", "gazi", "firat", "memurlar"}
    rows = [
        SourceResult(
            item["id"],
            item["name"],
            item["id"] not in errors,
            10 if item["id"] == "bogazici" else 0,
            "HTTP 403 CAPTCHA SSL CERTIFICATE_VERIFY_FAILED" if item["id"] in errors else None,
        )
        for item in sources
    ]
    now = datetime(2026, 10, 28, 16, 0, tzinfo=UTC)
    report = ScanReport(now, now, 0, 0, rows)
    message = report_message(report)
    for source in sources:
        assert source["url"] in message
    assert message.count("https://") == len(sources)
    assert "Kontrolü tamamlanan kaynak: 9/14" in message
    assert "🟠 Kontrolü eksik kalan kaynak: 5" in message
    assert "Yeni tespit edilen ilan: 0" in message
    assert "CERTIFICATE_VERIFY_FAILED" not in message
    assert "CAPTCHA" not in message
    assert "HTTP 403" not in message
    assert len(message) <= 4000
