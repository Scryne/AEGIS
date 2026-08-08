"""Nesne deposu adaptörü — S3-uyumlu (MinIO) belge saklama (E1.4).

Belgelerin kendisi **asla veritabanında tutulmaz**: veritabanı yedeği/dökümü PII taşıyan
binlerce PDF'i sürüklemek zorunda kalmamalı, saklama süresi imhası (E3.7) dosyayı ayrı
silebilmelidir. Veritabanında yalnız meta + nesne anahtarı durur.

Anahtar şeması::

    <tenant_id>/<yyyy>/<mm>/<document_id>-<güvenli dosya adı>

Kiracı kimliğinin önekte olması bilinçlidir: nesne deposunda RLS yoktur, bu yüzden
kiracı ayrımı anahtar düzeyinde görünür olmalı (yanlış anahtara erişimi *uygulama*
engeller; ön ek denetimi kolaylaştırır ve yanlışlıkla karışmayı zorlaştırır).

İstemci **senkrondur** (boto3). API tarafı bunu ``run_in_threadpool`` ile çağırır;
ayrı bir async S3 bağımlılığı (aioboto3) eklemek, tek-host duruşunda (R6) gereksiz
bir bağımlılık olurdu.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from aegis_core.config import Settings, get_settings
from aegis_core.logging import get_logger

logger = get_logger("aegis.documents.storage")

_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")
MAX_FILENAME_LENGTH = 120


class StorageError(RuntimeError):
    """Nesne deposu erişilemedi ya da işlem başarısız."""


class StorageNotConfiguredError(StorageError):
    """Nesne deposu ayarları eksik (``OBJECT_STORAGE_*``)."""


@dataclass(frozen=True)
class StoredObject:
    """Yüklenen nesnenin kimliği ve bütünlük kanıtı."""

    key: str
    size_bytes: int
    sha256: str


def safe_filename(filename: str) -> str:
    """Dosya adını nesne anahtarında kullanılabilir hâle getirir.

    Türkçe karakterler ASCII'ye indirgenir, ayraçlar sadeleştirilir. Amaç güvenlik
    değil okunabilirliktir — anahtarın tekilliğini ``document_id`` sağlar.
    """
    decomposed = unicodedata.normalize("NFKD", filename)
    ascii_only = "".join(char for char in decomposed if not unicodedata.combining(char))
    cleaned = _UNSAFE_FILENAME.sub("-", ascii_only).strip("-._")
    return (cleaned or "belge")[:MAX_FILENAME_LENGTH]


def build_storage_key(tenant_id: uuid.UUID, document_id: uuid.UUID, filename: str) -> str:
    """Belge için nesne anahtarı üretir (kiracı öneki + tarih + kimlik)."""
    now = datetime.now(UTC)
    return f"{tenant_id}/{now:%Y}/{now:%m}/{document_id}-{safe_filename(filename)}"


def sha256_hex(data: bytes) -> str:
    """İçerik özeti (bütünlük kanıtı ve tekilleştirme anahtarı)."""
    return hashlib.sha256(data).hexdigest()


@lru_cache(maxsize=2)
def _client(endpoint: str, access_key: str, secret_key: str, region: str) -> Any:
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
        config=Config(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"}),
    )


def get_client(settings: Settings | None = None) -> tuple[Any, str]:
    """(istemci, kova adı) döndürür; yapılandırma eksikse açık hata verir."""
    resolved = settings or get_settings()
    if not (
        resolved.object_storage_endpoint_url
        and resolved.object_storage_bucket
        and resolved.object_storage_access_key_id
        and resolved.object_storage_secret_access_key
    ):
        raise StorageNotConfiguredError(
            "Nesne deposu yapılandırılmamış (OBJECT_STORAGE_ENDPOINT_URL / BUCKET / "
            "ACCESS_KEY_ID / SECRET_ACCESS_KEY)."
        )
    client = _client(
        resolved.object_storage_endpoint_url,
        resolved.object_storage_access_key_id,
        resolved.object_storage_secret_access_key,
        resolved.object_storage_region,
    )
    return client, resolved.object_storage_bucket


def ensure_bucket(settings: Settings | None = None) -> None:
    """Kova yoksa oluşturur (geliştirme/ilk kurulum kolaylığı)."""
    client, bucket = get_client(settings)
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError:
        try:
            client.create_bucket(Bucket=bucket)
            logger.info("nesne_deposu_kova_olusturuldu", bucket=bucket)
        except (ClientError, BotoCoreError) as exc:
            raise StorageError(f"Kova oluşturulamadı: {exc}") from exc


def put_object(
    key: str, data: bytes, content_type: str, settings: Settings | None = None
) -> StoredObject:
    """Nesneyi depoya yazar ve özetini döndürür."""
    client, bucket = get_client(settings)
    digest = sha256_hex(data)
    try:
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            # Bütünlük: metadata'daki özet, DB'deki ile karşılaştırılabilir.
            Metadata={"sha256": digest},
        )
    except (ClientError, BotoCoreError) as exc:
        raise StorageError(f"Belge depoya yazılamadı: {exc}") from exc
    return StoredObject(key=key, size_bytes=len(data), sha256=digest)


def get_object(key: str, settings: Settings | None = None) -> bytes:
    """Nesneyi depodan okur."""
    client, bucket = get_client(settings)
    try:
        response = client.get_object(Bucket=bucket, Key=key)
        body: bytes = response["Body"].read()
    except (ClientError, BotoCoreError) as exc:
        raise StorageError(f"Belge depodan okunamadı: {exc}") from exc
    return body


def delete_object(key: str, settings: Settings | None = None) -> None:
    """Nesneyi siler (saklama süresi imhası E3.7'de bunu kullanacak)."""
    client, bucket = get_client(settings)
    try:
        client.delete_object(Bucket=bucket, Key=key)
    except (ClientError, BotoCoreError) as exc:
        raise StorageError(f"Belge silinemedi: {exc}") from exc


def presigned_url(key: str, *, expires_in: int = 300, settings: Settings | None = None) -> str:
    """Belgeyi indirmek için kısa ömürlü imzalı URL üretir.

    Kısa ömür (varsayılan 5 dk) bilinçlidir: bağlantı paylaşılırsa bile kalıcı bir
    erişim kapısı bırakmaz.
    """
    client, bucket = get_client(settings)
    try:
        url: str = client.generate_presigned_url(
            "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires_in
        )
    except (ClientError, BotoCoreError) as exc:
        raise StorageError(f"İndirme bağlantısı üretilemedi: {exc}") from exc
    return url
