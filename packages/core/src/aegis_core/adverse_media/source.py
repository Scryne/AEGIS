"""Haber kaynağı: Google News RSS arama (tr-TR) — E2.5 beta, ADR-0013.

Seçim (2026-11-01 deneme): anahtarsız, Türkçe kapsamı güçlü (bir kamuya mal olmuş isimde 58
sonuç, ulusal ve yerel yayıncılar). GDELT DOC 2.0 aynı gün bu ağdan sürekli oran sınırına takıldı;
ikinci kaynak olarak `NewsProvider` arayüzünün arkasına sonra eklenebilir.

Yalnız başlık, kaynak adı, bağlantı ve tarih okunur; haber metni indirilmez ve saklanmaz.
Sorgu sabit bir ana bilgisayara gider (SSRF yüzeyi yok); dış XML ``defusedxml`` ile ayrıştırılır
(DTD, varlık genişletmesi ve dış kaynak yasak).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Protocol
from urllib.parse import quote_plus
from xml.etree.ElementTree import ParseError

import httpx
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
PROVIDER = "google_news_rss"
_YAYINCI_EKI = re.compile(r"\s+-\s+[^-]{1,80}$")


@dataclass(frozen=True)
class NewsHit:
    title: str
    url: str
    source_name: str
    published_at: datetime | None


class NewsProvider(Protocol):
    name: str

    async def search(self, query: str, limit: int) -> list[NewsHit]: ...


def parse_rss(xml_text: str, limit: int) -> list[NewsHit]:
    """RSS 2.0 öğelerini ``NewsHit``e çevirir; bozuk öğe atlanır, bozuk belge boş liste."""
    try:
        kok = ElementTree.fromstring(xml_text)
    except (ParseError, DefusedXmlException):
        return []
    sonuc: list[NewsHit] = []
    for item in kok.iter("item"):
        baslik = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not baslik or not link.startswith("https://"):
            continue
        kaynak = (item.findtext("source") or "").strip()
        if kaynak:
            # Google başlığın sonuna " - Yayıncı" ekler; kaynak ayrı alanda zaten var.
            baslik = _YAYINCI_EKI.sub("", baslik) if baslik.endswith(kaynak) else baslik
        tarih: datetime | None = None
        ham = item.findtext("pubDate")
        if ham:
            try:
                tarih = parsedate_to_datetime(ham)
            except (TypeError, ValueError):
                tarih = None
        sonuc.append(NewsHit(baslik[:1000], link, kaynak[:255], tarih))
        if len(sonuc) >= limit:
            break
    return sonuc


class GoogleNewsRss:
    name = PROVIDER

    def __init__(self, client: httpx.AsyncClient | None = None, timeout: float = 15.0) -> None:
        self._client = client or httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": "AEGIS-adverse-media/0.1 (+compliance screening)"},
            follow_redirects=False,
        )

    async def search(self, query: str, limit: int) -> list[NewsHit]:
        url = f"{GOOGLE_NEWS_RSS}?q={quote_plus(query)}&hl=tr&gl=TR&ceid=TR:tr"
        r = await self._client.get(url)
        r.raise_for_status()
        return parse_rss(r.text, limit)

    async def aclose(self) -> None:
        await self._client.aclose()
