"""Olumsuz haber betası saf parçaları (E2.5, ADR-0013): RSS ayrıştırma, sorgu, olumsuz terim."""

from __future__ import annotations

from aegis_core.adverse_media.service import build_queries, core_name, negative_terms
from aegis_core.adverse_media.source import parse_rss

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item><title>Deniz Ticaret yöneticisi gözaltına alındı - Örnek Gazete</title>
<link>https://news.example.com/a1</link><pubDate>Thu, 16 Oct 2025 10:00:00 GMT</pubDate>
<source url="https://ornekgazete.com">Örnek Gazete</source></item>
<item><title>Bozuk bağlantı</title><link>javascript:alert(1)</link></item>
<item><title></title><link>https://news.example.com/bos</link></item>
<item><title>Deniz Ticaret yeni fabrikasını açtı</title><link>https://news.example.com/a2</link>
<pubDate>gecersiz</pubDate></item>
</channel></rss>"""


def test_parse_rss_strips_publisher_and_skips_bad_items() -> None:
    hits = parse_rss(RSS, limit=10)
    assert [h.url for h in hits] == ["https://news.example.com/a1", "https://news.example.com/a2"]
    assert hits[0].title == "Deniz Ticaret yöneticisi gözaltına alındı"
    assert hits[0].source_name == "Örnek Gazete"
    assert hits[0].published_at is not None
    assert hits[1].published_at is None
    assert len(parse_rss(RSS, limit=1)) == 1


def test_parse_rss_rejects_entities_and_garbage() -> None:
    bomba = (
        '<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aaaa">]>'
        "<rss><channel><item><title>&a;</title><link>https://x.y/z</link></item></channel></rss>"
    )
    assert parse_rss(bomba, 10) == []
    assert parse_rss("Please limit requests", 10) == []


def test_core_name_and_queries() -> None:
    assert core_name("Deniz Ticaret A.Ş.", "Company") == "Deniz Ticaret"
    assert core_name("Ege Gıda San. ve Tic. Ltd. Şti.", "Company") == "Ege Gıda"
    assert core_name("Ali  Veli", "Person") == "Ali Veli"
    assert core_name("AŞ", "Company") == "AŞ"  # çok kısa kalırsa ad olduğu gibi
    q = build_queries("Deniz Ticaret Anonim Şirketi", "Company")
    assert q[0] == '"Deniz Ticaret"'
    assert q[1].startswith('"Deniz Ticaret" (')
    assert '"kara para"' in q[1]


def test_negative_terms_turkish_case() -> None:
    assert negative_terms("İŞ İNSANI GÖZALTINA ALINDI, DOLANDIRICILIK İDDİASI") == [
        "dolandır",
        "gözaltı",
    ]
    assert negative_terms("Yeni fabrika açıldı") == []
