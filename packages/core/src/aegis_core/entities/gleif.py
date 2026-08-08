"""GLEIF LEI kütüğü zenginleştirmesi (E1.4).

LEI (Legal Entity Identifier), şirketlerin **kendi başvurularıyla aldıkları, kamuya açık
küresel bir tanımlayıcıdır**; GLEIF kütüğü de kamuya açıktır. ROADMAP E0.3 bunu "open
data, low risk" olarak sınıflar.

**KVKK duruşu (Invariant 3).** Dışarı çıkan tek şey **LEI kodudur**: ad, adres, TCKN,
vergi numarası ya da başka hiçbir müşteri verisi gönderilmez. Tarama tarafındaki katı
kural ("PII asla dış servise gitmez") burada da korunur; LEI kişisel veri değildir ve
zaten kamuya açık bir sicilde durur. Yine de her sorgu bir **denetim olayı** yazar
(``enrichment.lookup``) — hangi tanımlayıcının ne zaman dışarı gittiği izde durmalıdır.

Zenginleştirme sonucu **doğrudan kütüğe yazılmaz**: gelen değerler ``registry``/``gleif``
kaynaklı gözlemler olarak kaydedilir ve beyanla çelişirse tutarsızlık üretir. Böylece
kamuya açık kütük, müşterinin beyanını sessizce ezmez.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import TracebackType
from typing import Any, Self

import httpx

from aegis_core.entities.identifiers import IdentifierKind, check_identifier
from aegis_core.logging import get_logger

logger = get_logger("aegis.entities.gleif")

GLEIF_API_BASE = "https://api.gleif.org/api/v1"
DEFAULT_TIMEOUT_SECONDS = 15.0


class GleifError(RuntimeError):
    """GLEIF sorgusu başarısız."""


class GleifNotFoundError(GleifError):
    """Verilen LEI kütükte yok."""


@dataclass(frozen=True)
class GleifRecord:
    """GLEIF kaydından okunan alanlar (yalnız ihtiyacımız olanlar)."""

    lei: str
    legal_name: str | None
    country: str | None
    address: str | None
    status: str | None
    """``ACTIVE`` / ``LAPSED`` … — kaydın kütükteki durumu."""

    legal_form: str | None
    registration_authority_id: str | None
    """Ulusal sicil numarası (Türkiye'de MERSİS/ticaret sicil olabilir)."""

    source_url: str
    """Kanıt bağlantısı (Invariant 4)."""


def _first_string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _join_address(node: Any) -> str | None:
    """GLEIF adres nesnesini tek satıra indirger."""
    if not isinstance(node, dict):
        return None
    lines = node.get("addressLines")
    parts: list[str] = []
    if isinstance(lines, list):
        parts.extend(str(line).strip() for line in lines if str(line).strip())
    for key in ("postalCode", "city", "region", "country"):
        value = _first_string(node.get(key))
        if value:
            parts.append(value)
    return ", ".join(parts) or None


def parse_lei_record(payload: dict[str, Any]) -> GleifRecord:
    """GLEIF JSON:API yanıtını ``GleifRecord``a çevirir (savunmacı okuma).

    Alan adları değişirse burada ``None`` üretilir; zenginleştirme boş döner ama
    çağıran akış çökmez — eksik zenginleştirme, düşen bir dosya sayfasından iyidir.
    """
    data = payload.get("data")
    if isinstance(data, list):
        data = data[0] if data else None
    if not isinstance(data, dict):
        raise GleifNotFoundError("GLEIF yanıtında kayıt yok.")

    lei = _first_string(data.get("id")) or ""
    attributes = data.get("attributes")
    attributes = attributes if isinstance(attributes, dict) else {}
    entity = attributes.get("entity")
    entity = entity if isinstance(entity, dict) else {}
    registration = attributes.get("registration")
    registration = registration if isinstance(registration, dict) else {}

    legal_name_node = entity.get("legalName")
    legal_name = (
        _first_string(legal_name_node.get("name"))
        if isinstance(legal_name_node, dict)
        else _first_string(legal_name_node)
    )
    legal_address = entity.get("legalAddress")
    country = (
        _first_string(legal_address.get("country")) if isinstance(legal_address, dict) else None
    )
    registered_as = entity.get("registeredAs")

    return GleifRecord(
        lei=lei,
        legal_name=legal_name,
        country=country,
        address=_join_address(legal_address),
        status=_first_string(entity.get("status")) or _first_string(registration.get("status")),
        legal_form=(
            _first_string(entity.get("legalForm", {}).get("id"))
            if isinstance(entity.get("legalForm"), dict)
            else None
        ),
        registration_authority_id=_first_string(registered_as),
        source_url=f"https://search.gleif.org/#/record/{lei}" if lei else GLEIF_API_BASE,
    )


class GleifClient:
    """GLEIF LEI kütüğü istemcisi (yalnız LEI kodu dışarı çıkar)."""

    def __init__(
        self,
        base_url: str = GLEIF_API_BASE,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout)
        return self._client

    async def aclose(self) -> None:
        """İstemci bu sınıf tarafından açıldıysa kapatır."""
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    async def fetch(self, lei: str) -> GleifRecord:
        """Bir LEI kaydını getirir.

        Kod önce ISO 17442 kontrol basamağıyla doğrulanır: biçimsiz bir kodu dış servise
        göndermek gereksiz bir dış çağrıdır ve izde gürültü üretir.
        """
        check = check_identifier(IdentifierKind.LEI, lei)
        if not check.looks_valid:
            raise GleifError(check.reason or "Geçersiz LEI kodu.")
        try:
            response = await self._get_client().get(f"/lei-records/{check.normalized}")
            if response.status_code == 404:
                raise GleifNotFoundError(f"LEI kütükte bulunamadı: {check.normalized}")
            response.raise_for_status()
            payload: Any = response.json()
        except httpx.TimeoutException as exc:
            raise GleifError(f"GLEIF zaman aşımı ({self._timeout}s).") from exc
        except httpx.HTTPStatusError as exc:
            raise GleifError(f"GLEIF {exc.response.status_code} döndürdü.") from exc
        except httpx.HTTPError as exc:
            raise GleifError(f"GLEIF'e ulaşılamadı: {exc}") from exc
        except ValueError as exc:
            raise GleifError("GLEIF yanıtı JSON değil.") from exc
        if not isinstance(payload, dict):
            raise GleifError("GLEIF yanıtı beklenen biçimde değil.")
        record = parse_lei_record(payload)
        logger.info("gleif_kayit_alindi", lei=record.lei, status=record.status)
        return record
