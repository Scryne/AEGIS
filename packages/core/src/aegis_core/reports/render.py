"""Dosya raporunun PDF ve Word olarak üretilmesi (E1.5, ADR-0008).

İki biçim de **aynı** ``DossierData``dan beslenir: PDF Jinja2 şablonu üzerinden
xhtml2pdf ile, Word doğrudan ``python-docx`` ile yazılır. Ortak girdi bilinçlidir —
"PDF'te olan bir bulgunun Word'de olmaması" türü sapmayı yapısal olarak imkânsız kılar.

**Neden xhtml2pdf/reportlab, neden WeasyPrint değil?** WeasyPrint çok daha iyi CSS
destekler ama Pango/GDK gibi **yerel kütüphaneler** ister: Windows'ta geliştirme ortamı
kurulmaz, CI'da ek sistem paketi gerekir. Tek-host ve tek-geliştirici duruşunda (R6)
bu maliyet, bir *belge* (başlık + paragraf + tablo) için gereksizdir. xhtml2pdf saf
Python'dur ve her yerde aynı çalışır. Gerekçenin tamamı ADR-0008'dedir.

**Türkçe font.** reportlab'ın gömülü Type1 fontları (Helvetica …) WinAnsi kodlamasıdır
ve ``ş ğ ı İ`` harflerini TAŞIMAZ — bu harfler raporda kutucuk olarak çıkardı. Bu yüzden
reportlab'ın kendi dağıtımıyla gelen **Bitstream Vera** TTF yüzleri kaydedilir; Vera
Türkçe alfabenin tamamını kapsar ve ayrıca bir font dosyası depoya eklemeyi gerektirmez.

Kayıt xhtml2pdf'in ``@font-face`` yolundan **geçmez**: o yol fontu bir geçici dosyaya
kopyalayıp adıyla yeniden açar ve Windows'ta ``PermissionError`` verir (dosya hâlâ
açıktır). Bunun yerine yüzler doğrudan reportlab'a kaydedilip xhtml2pdf'in font
sözlüğüne (``default.DEFAULT_FONT``) eklenir; şablon yalnız ``font-family`` yazar.

Oluşturma **senkrondur** (reportlab/python-docx senkron kütüphanelerdir); API tarafı
``run_in_threadpool`` ile çağırır.
"""

from __future__ import annotations

import io
import os
import threading
from typing import Any

import reportlab
from docx import Document as DocxDocument
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor
from jinja2 import Environment, PackageLoader, select_autoescape
from reportlab.lib.fonts import addMapping
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from xhtml2pdf import default as xhtml2pdf_default
from xhtml2pdf import pisa

from aegis_core.logging import get_logger
from aegis_core.reports import labels
from aegis_core.reports.dossier import DossierData, dataset_version_rows
from aegis_core.reports.risk import RiskLevel

logger = get_logger("aegis.reports.render")

# Rapor gövde fontu. reportlab dağıtımıyla gelir → depoya font dosyası eklenmez.
REPORT_FONT_FAMILY = "Vera"
_VERA_FACES: dict[str, tuple[str, int, int]] = {
    # kayıt adı → (dosya, kalın, italik)
    "Vera": ("Vera.ttf", 0, 0),
    "Vera-Bold": ("VeraBd.ttf", 1, 0),
    "Vera-Italic": ("VeraIt.ttf", 0, 1),
    "Vera-BoldItalic": ("VeraBI.ttf", 1, 1),
}

_font_lock = threading.Lock()
_fonts_registered = False


class ReportRenderError(RuntimeError):
    """Rapor dosyası üretilemedi."""


def register_report_fonts() -> str:
    """Türkçe kapsayan yüzleri reportlab'a ve xhtml2pdf'e kaydeder (idempotent).

    Havuzdaki birden çok iş parçacığı aynı anda rapor üretebileceği için kayıt
    kilitlidir: reportlab'ın font kayıt defteri süreç genelinde paylaşılan durumdur.
    """
    global _fonts_registered
    with _font_lock:
        if _fonts_registered:
            return REPORT_FONT_FAMILY
        font_dir = os.path.join(os.path.dirname(reportlab.__file__), "fonts")
        for name, (filename, bold, italic) in _VERA_FACES.items():
            pdfmetrics.registerFont(TTFont(name, os.path.join(font_dir, filename)))
            # <b>/<i> etiketlerinin doğru yüzü seçebilmesi için aile eşlemesi.
            addMapping(REPORT_FONT_FAMILY, bold, italic, name)
        # xhtml2pdf font adlarını kendi sözlüğünden çözer; @font-face yolunu
        # kullanmıyoruz (modül başlığındaki Windows gerekçesi).
        xhtml2pdf_default.DEFAULT_FONT[REPORT_FONT_FAMILY.lower()] = REPORT_FONT_FAMILY
        _fonts_registered = True
        return REPORT_FONT_FAMILY


def _environment() -> Environment:
    """Jinja2 ortamı — HTML kaçışı AÇIK (rapor içeriği kullanıcı verisidir)."""
    return Environment(
        loader=PackageLoader("aegis_core.reports", "templates"),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_dossier_html(data: DossierData) -> str:
    """Dosya raporunu HTML olarak üretir (PDF'in kaynağı; testte de okunabilir)."""
    font_family = register_report_fonts()
    template = _environment().get_template("dossier.html")
    return template.render(
        data=data,
        font_family=font_family,
        dataset_versions=dataset_version_rows(data.dataset_versions),
    )


def render_dossier_pdf(data: DossierData) -> bytes:
    """Dosya raporunu PDF olarak üretir."""
    html = render_dossier_html(data)
    buffer = io.BytesIO()
    result = pisa.CreatePDF(src=html, dest=buffer, encoding="utf-8")
    if result.err:
        raise ReportRenderError(f"PDF üretilemedi ({result.err} hata).")
    payload = buffer.getvalue()
    if not payload.startswith(b"%PDF-"):
        raise ReportRenderError("PDF çıktısı geçerli bir PDF başlığı taşımıyor.")
    return payload


# ── Word ─────────────────────────────────────────────────────────────────────

_RISK_COLORS: dict[RiskLevel, RGBColor] = {
    RiskLevel.HIGH: RGBColor(0xA1, 0x12, 0x12),
    RiskLevel.ELEVATED: RGBColor(0xA8, 0x65, 0x00),
    RiskLevel.UNKNOWN: RGBColor(0x55, 0x55, 0x55),
    RiskLevel.STANDARD: RGBColor(0x2B, 0x6B, 0x2B),
}


def _add_table(document: Any, headers: list[str], rows: list[list[str]]) -> None:
    """Başlıklı bir tablo ekler; satır yoksa hiç tablo yazmaz."""
    if not rows:
        return
    table = document.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    for cell, header in zip(table.rows[0].cells, headers, strict=True):
        cell.text = ""
        run = cell.paragraphs[0].add_run(header)
        run.bold = True
    for row in rows:
        cells = table.add_row().cells
        for cell, value in zip(cells, row, strict=True):
            cell.text = value
    document.add_paragraph()


def _add_key_values(document: Any, pairs: list[tuple[str, str]]) -> None:
    """Etiket/değer tablosu (kimlik ve koşu künyesi bölümleri)."""
    _add_table(document, ["Alan", "Değer"], [[key, value] for key, value in pairs])


def render_dossier_docx(data: DossierData) -> bytes:
    """Dosya raporunu Word (.docx) olarak üretir.

    İçerik PDF ile birebir aynı bölümlerden oluşur; kaynak da aynı ``DossierData``dır.
    Word çıktısı, kurumun raporu kendi antetli şablonuna taşıyabilmesi içindir.
    """
    document = DocxDocument()
    normal = document.styles["Normal"]
    normal.font.size = Pt(9)

    heading = document.add_heading(data.title, level=0)
    heading.alignment = WD_ALIGN_PARAGRAPH.LEFT
    meta = [data.subject_kind_label]
    if data.organization_name:
        meta.append(data.organization_name)
    meta.append(f"Üretim tarihi: {data.generated_at_label}")
    if data.generated_by:
        meta.append(f"Üreten: {data.generated_by}")
    document.add_paragraph(" · ".join(meta))

    # ── Risk özeti ───────────────────────────────────────────────────────────
    document.add_heading("Risk değerlendirmesi", level=1)
    level_paragraph = document.add_paragraph()
    level_run = level_paragraph.add_run(data.risk.level_label)
    level_run.bold = True
    level_run.font.size = Pt(14)
    level_run.font.color.rgb = _RISK_COLORS[data.risk.level]
    document.add_paragraph(data.risk.rationale)
    for index, finding in enumerate(data.risk.findings, start=1):
        paragraph = document.add_paragraph()
        title_run = paragraph.add_run(f"{index}. {finding.title}")
        title_run.bold = True
        if finding.needs_action:
            paragraph.add_run("  [İŞLEM BEKLİYOR]").italic = True
        document.add_paragraph(finding.rationale)
        if finding.source_refs:
            document.add_paragraph(f"Kaynak: {' · '.join(finding.source_refs)}")
    if not data.risk.findings:
        document.add_paragraph("Kuralların ürettiği bulgu yok.")
    document.add_paragraph(
        "Bu rapor bir karar desteği çıktısıdır; müşteri kabul, ret ya da şüpheli işlem "
        "bildirimi kararı yükümlü kuruma aittir."
    )

    # ── Kimlik ───────────────────────────────────────────────────────────────
    document.add_heading("1. Kimlik bilgileri", level=1)
    _add_key_values(document, [(item.label, item.value) for item in data.profile])

    # ── İlgili taraflar ──────────────────────────────────────────────────────
    document.add_heading("2. İlgili taraflar", level=1)
    if data.related_parties:
        _add_table(
            document,
            ["Ad / unvan", "Bağ türü", "Yetki / unvan", "Pay", "Kaynak"],
            [
                [
                    party.name,
                    party.rel_type_label,
                    party.role_title or "—",
                    party.ownership_percent,
                    labels.format_value(
                        f"{party.source_label} · {party.source_ref}"
                        if party.source_ref
                        else party.source_label
                    ),
                ]
                for party in data.related_parties
            ],
        )
    else:
        document.add_paragraph("Kayıtlı bağ yok.")

    # ── Tarama ───────────────────────────────────────────────────────────────
    document.add_heading("3. Yaptırım ve PEP taraması", level=1)
    if not data.screenings:
        document.add_paragraph(
            "Bu varlık için tarama kaydı yok. Dosya, tarama koşulmadan tamamlanmış sayılamaz."
        )
    for index, screening in enumerate(data.screenings, start=1):
        document.add_heading(
            f"3.{index} Koşu — {screening.status_label} ({screening.completed_at})", level=2
        )
        _add_key_values(
            document,
            [
                ("Veri kümesi kapsamı", screening.dataset),
                ("Eşleştirme algoritması", screening.algorithm),
                ("Koşu anındaki eşikler", screening.thresholds),
                ("Başlangıç / süre", f"{screening.started_at} · {screening.duration}"),
            ],
        )
        if not screening.succeeded:
            paragraph = document.add_paragraph()
            paragraph.add_run("Bu koşu sonuç üretmedi. ").bold = True
            paragraph.add_run(
                "Başarısız bir tarama “temiz” anlamına gelmez."
                + (f" Hata: {screening.error}" if screening.error else "")
            )
            continue
        if screening.matches:
            _add_table(
                document,
                ["Taranan", "Eşleşen kayıt", "Skor", "Karar", "Konular / listeler"],
                [
                    [
                        f"{match.subject_name}\n{match.subject_role_label}",
                        "\n".join(
                            part
                            for part in (
                                match.caption,
                                match.source_url,
                                f"Eşleşme nedeni: {match.match_features}",
                            )
                            if part
                        ),
                        f"{match.score}\n{match.band_label}",
                        "\n".join(
                            part
                            for part in (
                                match.decision_label,
                                "eşik bandı kararı" if match.decided_automatically else None,
                                f"Gerekçe: {match.review_note}" if match.review_note else None,
                            )
                            if part
                        ),
                        f"{match.topics}\n{match.datasets}",
                    ]
                    for match in screening.matches
                ],
            )
            document.add_paragraph(
                "Elenen eşleşmeler de tabloda yer alır: dosyanın savunması “neye bakıldı "
                "ve neden elendi” bilgisini içerir."
            )
        else:
            document.add_paragraph("Bu koşuda eşik üstünde aday bulunamadı.")

    # ── Tutarsızlıklar ───────────────────────────────────────────────────────
    document.add_heading("4. Tutarsızlıklar", level=1)
    if data.discrepancies:
        _add_table(
            document,
            ["Alan", "Beyan", "Belge / kütük", "Ağırlık", "Durum"],
            [
                [
                    item.attribute_label,
                    item.declared_value,
                    "\n".join(
                        part
                        for part in (
                            item.observed_value,
                            item.observed_source_label,
                            item.observed_source_ref,
                        )
                        if part
                    ),
                    item.severity_label,
                    "\n".join(part for part in (item.status_label, item.resolution_note) if part),
                ]
                for item in data.discrepancies
            ],
        )
    else:
        document.add_paragraph("Tutarsızlık tespit edilmedi.")

    # ── Belgeler ─────────────────────────────────────────────────────────────
    document.add_heading("5. Dosyadaki belgeler", level=1)
    if data.documents:
        _add_table(
            document,
            ["Dosya adı", "Tür", "Yükleme", "SHA-256 (bütünlük)"],
            [
                [
                    "\n".join(part for part in (item.filename, item.source_ref) if part),
                    item.doc_type_label,
                    item.uploaded_at,
                    item.sha256,
                ]
                for item in data.documents
            ],
        )
    else:
        document.add_paragraph("Belge yüklenmedi.")

    # ── Provenans ────────────────────────────────────────────────────────────
    document.add_heading("6. Veri kaynakları ve gözlemler", level=1)
    if data.observations:
        _add_table(
            document,
            ["Alan", "Değer", "Kaynak", "Gözlem zamanı"],
            [
                [
                    row.attribute_label,
                    row.value,
                    "\n".join(part for part in (row.source_label, row.source_ref) if part),
                    row.observed_at,
                ]
                for row in data.observations
            ],
        )
    else:
        document.add_paragraph("Gözlem kaydı yok.")

    # ── Veri kümesi sürümleri ────────────────────────────────────────────────
    document.add_heading("7. Kullanılan veri kümeleri", level=1)
    version_rows = dataset_version_rows(data.dataset_versions)
    if version_rows:
        _add_table(
            document,
            ["Veri kümesi", "Sürüm", "Son güncelleme"],
            [list(row) for row in version_rows],
        )
        document.add_paragraph(
            "Sürümler koşu anında donduruldu; sonraki güncellemeler bu raporun "
            "bulgularını değiştirmez."
        )
    else:
        document.add_paragraph("Veri kümesi sürüm bilgisi kaydedilmedi.")

    buffer = io.BytesIO()
    document.save(buffer)
    payload = buffer.getvalue()
    if not payload.startswith(b"PK"):  # docx = zip konteyner
        raise ReportRenderError("Word çıktısı geçerli bir .docx konteyneri değil.")
    return payload
