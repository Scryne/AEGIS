"""PDF → metin dönüşümü (Docling adaptörü) — E1.4, Revizyon R2.

**Docling isteğe bağlı bir kurulumdur.** Paket, PyTorch dahil ~2 GB'lık bir bağımlılık
ağacı getirir. Bunu zorunlu bağımlılık yapmak CI'ı her koşuda o ağacı çözmeye zorlar ve
tek-host duruşumuzu (R6) ağırlaştırırdı. Bu yüzden:

- Docling ``extraction`` opsiyonel grubundadır ve **worker imajına** kurulur.
- Bu modül onu **tembel** import eder; kurulu değilse açık bir hata döner ve belge
  ``skipped`` durumuna geçer — çıkarım yapılamaz ama yükleme/saklama çalışmaya devam eder.
- Asıl kırılgan mantık (Türkçe desen eşleştirme) ``extraction`` modülündedir ve Docling
  olmadan test edilir.

Düz metin (``text/plain``) belgeler Docling gerektirmez; küçük bir yedek yol onları
doğrudan okur — bu, uçtan uca akışın motor kurulmadan da sınanabilmesini sağlar.
"""

from __future__ import annotations

from dataclasses import dataclass

from aegis_core.logging import get_logger

logger = get_logger("aegis.documents.docling")

ENGINE_DOCLING = "docling"
ENGINE_PLAIN_TEXT = "text"


class ExtractionEngineUnavailableError(RuntimeError):
    """Docling kurulu değil (opsiyonel ``extraction`` grubu yüklenmemiş)."""


@dataclass(frozen=True)
class ConvertedDocument:
    """Bir belgenin metne çevrilmiş hâli."""

    text: str
    page_count: int | None
    engine: str


def _convert_plain_text(data: bytes) -> ConvertedDocument:
    """Düz metin belgeleri doğrudan çözer (motor gerektirmez)."""
    text = data.decode("utf-8", errors="replace")
    return ConvertedDocument(text=text, page_count=None, engine=ENGINE_PLAIN_TEXT)


def _convert_with_docling(data: bytes, filename: str) -> ConvertedDocument:
    """Docling ile PDF/görüntü belgeyi markdown metne çevirir (tembel import)."""
    try:
        from docling.datamodel.base_models import DocumentStream
        from docling.document_converter import DocumentConverter
    except ImportError as exc:  # pragma: no cover - kurulum kararına bağlı
        raise ExtractionEngineUnavailableError(
            "Docling kurulu değil. Worker imajında `uv sync --extra extraction` ile "
            "kurulur; kurulmadan PDF çıkarımı yapılamaz (belge yine de saklanır)."
        ) from exc

    import io

    converter = DocumentConverter()
    stream = DocumentStream(name=filename, stream=io.BytesIO(data))
    result = converter.convert(stream)
    document = result.document
    text: str = document.export_to_markdown()
    pages = getattr(document, "pages", None)
    page_count = len(pages) if pages is not None else None
    return ConvertedDocument(text=text, page_count=page_count, engine=ENGINE_DOCLING)


def convert(data: bytes, *, filename: str, content_type: str) -> ConvertedDocument:
    """Belgeyi metne çevirir; düz metinde motor gerektirmez, aksi hâlde Docling kullanır."""
    if content_type.startswith("text/"):
        return _convert_plain_text(data)
    converted = _convert_with_docling(data, filename)
    logger.info(
        "belge_metne_cevrildi",
        engine=converted.engine,
        pages=converted.page_count,
        chars=len(converted.text),
    )
    return converted


def is_available() -> bool:
    """Docling kurulu mu (sağlık/tanı amaçlı)."""
    try:
        import docling  # noqa: F401
    except ImportError:
        return False
    return True
