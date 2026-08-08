"""yente istemcisi — self-host yaptırım/PEP tarama motoru (E1.3).

**KVKK (Invariant 3):** tarama yalnız kendi ortamımızdaki yente örneğine gider; müşteri
PII'si hiçbir koşulda dış bir tarama API'sine çıkmaz. Bu modülde tek bir taban URL
vardır ve o da ``settings.yente_url``dir.

Modül üç parçadır:

- **Saf fonksiyonlar** (``build_match_payload``, ``parse_match_response``,
  ``parse_catalog``): ağ gerektirmez, birim testlerinin asıl hedefi budur. yente'nin
  yanıt şeması değişirse kırılacak tek yer burasıdır.
- **``YenteClient``**: API (async) tarafı.
- **``SyncYenteClient``**: Celery worker (senkron) tarafı — aynı saf fonksiyonları kullanır.

Yanıt ayrıştırması **savunmacıdır**: beklenmeyen/eksik alan istisna değil, o alanın
yokluğu olarak ele alınır. Tek bir aday kaydının biçimsizliği yüzünden tüm taramanın
düşmesi, yanlış negatif üretir — bu üründeki tehlikeli hata türü.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, Self

import httpx

from aegis_core.logging import get_logger

logger = get_logger("aegis.screening.yente")

# OpenSanctions kaynaklı varlıklar için kanıt bağlantısı (provenance, Invariant 4).
OPENSANCTIONS_ENTITY_BASE = "https://www.opensanctions.org/entities/"

# yente'nin varsayılan skorlama algoritması (5.x). Ayarlardan değiştirilebilir.
DEFAULT_ALGORITHM = "logic-v1"

# FtM şema adları — özne türü eşlemesi.
SCHEMA_PERSON = "Person"
SCHEMA_COMPANY = "Company"


class YenteError(RuntimeError):
    """yente ile iletişimde/ yanıtında hata."""


class YenteUnavailableError(YenteError):
    """yente erişilemez veya hata durumu döndürdü (ağ, 5xx, zaman aşımı)."""


@dataclass(frozen=True)
class MatchQuery:
    """Tek bir öznenin (şirket ya da kişi) tarama sorgusu."""

    key: str
    """Yanıtı isteğe geri bağlayan anahtar (yente sorguları anahtarla döndürür)."""

    schema: str
    names: tuple[str, ...]
    country: str | None = None
    identifiers: Mapping[str, str] = field(default_factory=dict)
    """FtM özellik adı → değer (``taxNumber``, ``registrationNumber``, ``idNumber`` …)."""


@dataclass(frozen=True)
class YenteMatch:
    """yente'den dönen tek bir eşleşme adayı (skor + "neden eşleşti" verisiyle)."""

    entity_id: str
    caption: str
    schema: str
    score: float
    matched: bool
    """yente'nin kendi eşik kararı (bizim bandımızdan bağımsız; bilgi amaçlı saklanır)."""

    datasets: tuple[str, ...]
    topics: tuple[str, ...]
    """FtM ``topics``: ``sanction``, ``role.pep``, ``crime`` … — risk özetini besler."""

    countries: tuple[str, ...]
    features: dict[str, float]
    """Skoru oluşturan özellik→ağırlık kırılımı ("neden eşleşti" ekranının kaynağı)."""

    properties: dict[str, list[str]]
    source_url: str | None

    @property
    def is_sanctioned(self) -> bool:
        """Adayın konuları arasında yaptırım var mı."""
        return any(topic.startswith("sanction") for topic in self.topics)

    @property
    def is_pep(self) -> bool:
        """Adayın konuları arasında siyasi nüfuz sahibi (PEP) var mı."""
        return any(topic.startswith("role.pep") or topic == "poi" for topic in self.topics)


@dataclass(frozen=True)
class DatasetInfo:
    """Kataloğdan okunan veri kümesi durumu (tazelik metriğinin kaynağı)."""

    name: str
    title: str | None
    version: str | None
    last_export: datetime | None
    """Kaynağın dışa aktarım zamanı; yoksa yente'nin sürüm damgasından türetilir."""

    entity_count: int | None

    @property
    def age_hours(self) -> float | None:
        """Son dışa aktarımın üzerinden geçen saat (bilinmiyorsa ``None``)."""
        if self.last_export is None:
            return None
        delta = datetime.now(UTC) - self.last_export
        return delta.total_seconds() / 3600.0


# ── Saf yardımcılar (ağ yok — birim testlerinin hedefi) ──────────────────────


def build_match_payload(queries: Sequence[MatchQuery]) -> dict[str, Any]:
    """Sorgu listesinden yente ``POST /match`` gövdesini üretir.

    Aynı özne için birden çok ad varyantı (kanonik + ASCII + ham) tek sorgunun ``name``
    özelliğine çoklu değer olarak konur; yente bunları alternatif olarak değerlendirir.
    """
    payload: dict[str, Any] = {"queries": {}}
    for query in queries:
        properties: dict[str, list[str]] = {"name": [name for name in query.names if name]}
        if query.country:
            properties["country"] = [query.country]
        for prop, value in query.identifiers.items():
            if value:
                properties[prop] = [value]
        payload["queries"][query.key] = {"schema": query.schema, "properties": properties}
    return payload


def _as_float(value: object, default: float = 0.0) -> float:
    """Sayıya çevirir; çevrilemiyorsa varsayılana düşer (yanıt biçimine dayanıklılık)."""
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def _as_str_list(value: object) -> tuple[str, ...]:
    """Bir alanı string demetine çevirir (tek değer, liste veya yokluk kabul eder)."""
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(str(item) for item in value if item is not None)
    return ()


def _parse_timestamp(value: object) -> datetime | None:
    """ISO-8601 zaman damgasını UTC'ye çözer; çözülemezse ``None``."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _parse_version_timestamp(value: object) -> datetime | None:
    """yente sürüm damgasını (``20260808090010``) zamana çevirir.

    **Neden gerekli:** OpenSanctions kataloğu ``last_export`` alanını doldurur, ama
    manifest'ten yüklenen **özel** veri kümelerinde (MASAK, değerlendirme seti) bu alan
    ``null`` gelir; yente orada yalnız indeksleme zamanını ``version`` olarak yazar.
    Yedek olmasaydı MASAK kümesi her gün "dışa aktarım zamanı bilinmiyor" diye bayat
    sayılır ve alarm üretirdi — alarm yorgunluğu, gerçek bayatlığı görünmez kılardı.
    """
    if not isinstance(value, str):
        return None
    digits = value.strip()
    if not digits.isdigit():
        return None
    formats = {14: "%Y%m%d%H%M%S", 12: "%Y%m%d%H%M", 8: "%Y%m%d"}
    fmt = formats.get(len(digits))
    if fmt is None:
        return None
    try:
        return datetime.strptime(digits, fmt).replace(tzinfo=UTC)
    except ValueError:
        return None


def _resolve_source_url(entity_id: str, properties: Mapping[str, list[str]]) -> str | None:
    """Adayın kanıt bağlantısını çözer (Invariant 4: her bulguda kaynak referansı).

    Önce varlığın kendi ``sourceUrl`` özelliği (MASAK gibi özel veri kümelerimizde bunu
    biz doldururuz), yoksa OpenSanctions varlık sayfası.
    """
    urls = properties.get("sourceUrl")
    if urls:
        return urls[0]
    return f"{OPENSANCTIONS_ENTITY_BASE}{entity_id}/" if entity_id else None


def parse_match_entity(raw: Mapping[str, Any]) -> YenteMatch | None:
    """Tek bir aday kaydını çözer; kimliksiz/biçimsiz kayıt ``None`` döner."""
    entity_id = raw.get("id")
    if not isinstance(entity_id, str) or not entity_id:
        return None
    raw_properties = raw.get("properties")
    properties: dict[str, list[str]] = {}
    if isinstance(raw_properties, Mapping):
        for key, value in raw_properties.items():
            properties[str(key)] = list(_as_str_list(value))

    raw_features = raw.get("features")
    features: dict[str, float] = {}
    if isinstance(raw_features, Mapping):
        for key, value in raw_features.items():
            features[str(key)] = _as_float(value)

    return YenteMatch(
        entity_id=entity_id,
        caption=str(raw.get("caption") or entity_id),
        schema=str(raw.get("schema") or ""),
        score=_as_float(raw.get("score")),
        matched=bool(raw.get("match", False)),
        datasets=_as_str_list(raw.get("datasets")),
        topics=tuple(properties.get("topics", ())),
        countries=tuple(properties.get("country", ())),
        features=features,
        properties=properties,
        source_url=_resolve_source_url(entity_id, properties),
    )


def parse_match_response(payload: Mapping[str, Any]) -> dict[str, list[YenteMatch]]:
    """``POST /match`` yanıtını ``sorgu anahtarı → adaylar`` sözlüğüne çevirir.

    Adaylar skora göre azalan sıralanır. Bir sorgu hata döndürdüyse (``status`` 2xx
    değil) o anahtar boş listeyle temsil edilir ve durum loglanır — diğer öznelerin
    sonuçları bu yüzden atılmaz.
    """
    responses = payload.get("responses")
    if not isinstance(responses, Mapping):
        raise YenteError("yente yanıtında 'responses' alanı yok.")

    parsed: dict[str, list[YenteMatch]] = {}
    for key, response in responses.items():
        if not isinstance(response, Mapping):
            parsed[str(key)] = []
            continue
        status = response.get("status")
        if isinstance(status, int) and not 200 <= status < 300:
            logger.warning(
                "yente_sorgu_hatasi", query=str(key), status=status, error=response.get("error")
            )
            parsed[str(key)] = []
            continue
        results = response.get("results")
        matches: list[YenteMatch] = []
        if isinstance(results, Sequence):
            for item in results:
                if isinstance(item, Mapping):
                    match = parse_match_entity(item)
                    if match is not None:
                        matches.append(match)
        matches.sort(key=lambda item: item.score, reverse=True)
        parsed[str(key)] = matches
    return parsed


def parse_catalog(payload: Mapping[str, Any]) -> list[DatasetInfo]:
    """``GET /catalog`` yanıtını veri kümesi durumlarına çevirir."""
    datasets = payload.get("datasets")
    if not isinstance(datasets, Sequence):
        raise YenteError("yente kataloğunda 'datasets' alanı yok.")
    parsed: list[DatasetInfo] = []
    for item in datasets:
        if not isinstance(item, Mapping):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name:
            continue
        entity_count = item.get("entity_count")
        version = item.get("version")
        parsed.append(
            DatasetInfo(
                name=name,
                title=str(item["title"]) if item.get("title") else None,
                version=str(version) if version else None,
                # Özel veri kümelerinde last_export boştur; sürüm damgası yedeğe geçer.
                last_export=(
                    _parse_timestamp(item.get("last_export")) or _parse_version_timestamp(version)
                ),
                entity_count=int(entity_count) if isinstance(entity_count, int) else None,
            )
        )
    return parsed


def _match_params(*, algorithm: str, cutoff: float, threshold: float, limit: int) -> dict[str, Any]:
    """``POST /match`` sorgu parametreleri.

    ``cutoff``ın altındaki adaylar hiç dönmez; ``threshold`` yente'nin kendi ``match``
    bayrağını belirler ve kiracının otomatik-işaretleme eşiğiyle hizalanır.
    """
    return {
        "algorithm": algorithm,
        "cutoff": cutoff,
        "threshold": threshold,
        "limit": limit,
        "fuzzy": "false",
    }


# ── İstemciler ───────────────────────────────────────────────────────────────


class YenteClient:
    """Async yente istemcisi (FastAPI tarafı)."""

    def __init__(
        self,
        base_url: str,
        *,
        dataset: str = "default",
        algorithm: str = DEFAULT_ALGORITHM,
        timeout_seconds: float = 20.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._dataset = dataset
        self._algorithm = algorithm
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
        """İstemci bu sınıf tarafından açıldıysa kapatır (dışarıdan verilene dokunmaz)."""
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = await self._get_client().request(method, path, **kwargs)
            response.raise_for_status()
            data: Any = response.json()
        except httpx.TimeoutException as exc:
            raise YenteUnavailableError(f"yente zaman aşımı ({self._timeout}s).") from exc
        except httpx.HTTPStatusError as exc:
            raise YenteUnavailableError(
                f"yente {exc.response.status_code} döndürdü: {path}"
            ) from exc
        except httpx.HTTPError as exc:
            raise YenteUnavailableError(f"yente'ye ulaşılamadı: {exc}") from exc
        except ValueError as exc:  # JSON çözümlenemedi
            raise YenteError("yente yanıtı JSON değil.") from exc
        if not isinstance(data, dict):
            raise YenteError("yente yanıtı beklenen nesne biçiminde değil.")
        return data

    async def match(
        self,
        queries: Sequence[MatchQuery],
        *,
        cutoff: float,
        threshold: float,
        limit: int = 10,
    ) -> dict[str, list[YenteMatch]]:
        """Verilen özneleri veri kümesine karşı eşleştirir."""
        if not queries:
            return {}
        payload = await self._request(
            "POST",
            f"/match/{self._dataset}",
            json=build_match_payload(queries),
            params=_match_params(
                algorithm=self._algorithm, cutoff=cutoff, threshold=threshold, limit=limit
            ),
        )
        return parse_match_response(payload)

    async def catalog(self) -> list[DatasetInfo]:
        """Veri kümesi kataloğunu (sürüm + son dışa aktarım) döndürür."""
        return parse_catalog(await self._request("GET", "/catalog"))

    async def is_ready(self) -> bool:
        """yente hazır mı (readiness ucu) — hazırlık kontrolünde kullanılır."""
        try:
            await self._request("GET", "/readyz")
        except YenteError:
            return False
        return True


class SyncYenteClient:
    """Senkron yente istemcisi (Celery worker tarafı) — aynı ayrıştırıcıları kullanır."""

    def __init__(
        self,
        base_url: str,
        *,
        dataset: str = "default",
        algorithm: str = DEFAULT_ALGORITHM,
        timeout_seconds: float = 60.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._dataset = dataset
        self._algorithm = algorithm
        self._timeout = timeout_seconds
        self._client = client
        self._owns_client = client is None

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(base_url=self._base_url, timeout=self._timeout)
        return self._client

    def close(self) -> None:
        """İstemci bu sınıf tarafından açıldıysa kapatır."""
        if self._client is not None and self._owns_client:
            self._client.close()
            self._client = None

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self._get_client().request(method, path, **kwargs)
            response.raise_for_status()
            data: Any = response.json()
        except httpx.TimeoutException as exc:
            raise YenteUnavailableError(f"yente zaman aşımı ({self._timeout}s).") from exc
        except httpx.HTTPStatusError as exc:
            raise YenteUnavailableError(
                f"yente {exc.response.status_code} döndürdü: {path}"
            ) from exc
        except httpx.HTTPError as exc:
            raise YenteUnavailableError(f"yente'ye ulaşılamadı: {exc}") from exc
        except ValueError as exc:
            raise YenteError("yente yanıtı JSON değil.") from exc
        if not isinstance(data, dict):
            raise YenteError("yente yanıtı beklenen nesne biçiminde değil.")
        return data

    def match(
        self,
        queries: Sequence[MatchQuery],
        *,
        cutoff: float,
        threshold: float,
        limit: int = 10,
    ) -> dict[str, list[YenteMatch]]:
        """Verilen özneleri veri kümesine karşı eşleştirir (senkron)."""
        if not queries:
            return {}
        payload = self._request(
            "POST",
            f"/match/{self._dataset}",
            json=build_match_payload(queries),
            params=_match_params(
                algorithm=self._algorithm, cutoff=cutoff, threshold=threshold, limit=limit
            ),
        )
        return parse_match_response(payload)

    def catalog(self) -> list[DatasetInfo]:
        """Veri kümesi kataloğunu döndürür (senkron)."""
        return parse_catalog(self._request("GET", "/catalog"))

    def trigger_reindex(self, token: str) -> bool:
        """yente'ye yeniden indeksleme (delta senkron) tetikler.

        yente kendi zamanlayıcısıyla da yenilenir; bu çağrı, günlük job'ın senkronu
        **bizim** takvimimize bağlamasını sağlar (tazelik alarmı ile aynı koşuda).
        Uç yapılandırılmamışsa (jeton yok) çağıran bu metodu hiç kullanmaz.

        Not: ``/updatez`` yente'de jetonla korunur ve uzun sürebilir; başarısızlık
        istisna değil ``False`` döner — tazelik ölçümü yine de yapılmalıdır.
        """
        try:
            self._request("POST", "/updatez", params={"token": token})
        except YenteError as exc:
            logger.warning("yente_reindex_tetiklenemedi", error=str(exc))
            return False
        return True
