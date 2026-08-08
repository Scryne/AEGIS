"""Kural tabanlı risk özeti v1 — şeffaf, öğrenmesiz (E1.5).

ROADMAP E1.5: *"Rule-based risk summary v1 (transparent, no ML): confirmed sanctions hit
→ High; PEP → Elevated; unresolved discrepancies → flag; each with plain-language
rationale"*. Ağırlıklı/öğrenilmiş risk skoru **Phase 2**'nin işidir ve burada YOKTUR.

**Neden kural, neden puan değil?** Ürünün duruşu karar *desteği*dir: MASAK denetiminde
"bu dosyaya neden Yüksek dediniz" sorusunun cevabı, tek tek gösterilebilir cümleler
olmalıdır. 0..100 arası bir puan bu soruyu cevaplayamaz; kuralın kendisi cevaplar.
Bu yüzden her bulgu (``RiskFinding``) düz Türkçe bir ``rationale`` taşır ve seviye,
bulguların **en yükseğidir** — gizli bir toplama/ağırlıklandırma yoktur.

**Seviyeyi yükseltmeyen bulgular.** Yüksek skorlu ama henüz karara bağlanmamış bir
eşleşme dosyayı Yüksek yapmaz: bu, "otomatik onay yok" değişmezinin (ADR-0006) arka
kapıdan delinmesi olurdu. Böyle bulgular ``level=None`` taşır; seviyeye dokunmaz, ama
``complete=False`` yaparak dosyanın **tamamlanmadığını** bildirir.

**Sonuçsuzluk ile temizlik ayrı şeydir.** Hiç tarama yoksa ya da koşu başarısızsa
seviye ``UNKNOWN``tır — asla ``STANDARD`` değil. "Tarama çalışmadı" ile "tarama çalıştı,
bulgu yok" arasındaki farkı silmek, bu üründeki en tehlikeli hatadır.

Modül **veritabanı bilmez**: girdileri küçük görünüm (view) dataclass'larıdır ve
``reports.dossier`` bunları ORM satırlarından kurar. Böylece kurallar saf fonksiyon
olarak, veritabanı olmadan test edilir.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from aegis_core.models import DiscrepancySeverity, DiscrepancyStatus, ScreeningStatus
from aegis_core.screening.thresholds import MatchDecision
from aegis_core.screening.topics import has_pep_topic, has_sanction_topic


class RiskLevel(StrEnum):
    """Dosyanın risk seviyesi (Ürün Planı'nın üç kademesi + "sonuç yok")."""

    UNKNOWN = "unknown"
    """Belirsiz: tarama hiç koşmadı ya da koşamadı. "Temiz" DEĞİLDİR."""

    STANDARD = "standard"
    """Standart: tarama koştu, seviyeyi yükselten bulgu yok."""

    ELEVATED = "elevated"
    """Artırılmış: PEP eşleşmesi ya da kimlik tanımlayıcısında açık tutarsızlık."""

    HIGH = "high"
    """Yüksek: onaylanmış yaptırım eşleşmesi."""


# Seviye sıralaması — ``UNKNOWN`` en altta DEĞİL: bilgisizlik, temizlikten daha
# yüksek bir uyarıdır ve STANDARD'ın üstüne çıkmalıdır. Yalnız gerçek bulgular
# (ELEVATED/HIGH) onu bastırır.
_LEVEL_RANK: dict[RiskLevel, int] = {
    RiskLevel.STANDARD: 0,
    RiskLevel.UNKNOWN: 1,
    RiskLevel.ELEVATED: 2,
    RiskLevel.HIGH: 3,
}

RISK_LEVEL_LABELS: dict[RiskLevel, str] = {
    RiskLevel.UNKNOWN: "Belirsiz",
    RiskLevel.STANDARD: "Standart",
    RiskLevel.ELEVATED: "Artırılmış",
    RiskLevel.HIGH: "Yüksek",
}


# ── Kural kodları (rapor ve denetim izinde sabit kalır) ──────────────────────
CODE_SANCTION_CONFIRMED = "sanction.confirmed"
CODE_PEP_CONFIRMED = "pep.confirmed"
CODE_MATCH_CONFIRMED_OTHER = "match.confirmed_other"
CODE_MATCH_PENDING_FLAGGED = "match.pending_flagged"
CODE_MATCH_PENDING = "match.pending"
CODE_DISCREPANCY_CRITICAL = "discrepancy.critical_open"
CODE_DISCREPANCY_OPEN = "discrepancy.open"
CODE_SCREENING_FAILED = "screening.failed"
CODE_SCREENING_MISSING = "screening.missing"


# ── Girdi görünümleri (ORM'den bağımsız) ─────────────────────────────────────


@dataclass(frozen=True)
class MatchView:
    """Bir aday eşleşmenin risk kuralları için gereken alanları."""

    subject_name: str
    caption: str
    score: float
    decision: str
    band: str
    flagged: bool
    decided_automatically: bool
    topics: tuple[str, ...] = ()
    datasets: tuple[str, ...] = ()
    source_url: str | None = None
    review_note: str | None = None


@dataclass(frozen=True)
class ScreeningView:
    """Bir tarama koşusunun risk kuralları için gereken alanları."""

    status: str
    completed_at: datetime | None
    dataset: str
    matches: tuple[MatchView, ...] = ()
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        """Koşu sonuç üretti mi (``failed`` bir sonuç DEĞİLDİR)."""
        return self.status == ScreeningStatus.COMPLETED.value


@dataclass(frozen=True)
class DiscrepancyView:
    """Bir tutarsızlığın risk kuralları için gereken alanları."""

    attribute_label: str
    severity: str
    status: str
    declared_value: str
    observed_value: str
    observed_source_ref: str | None = None


# ── Çıktı ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RiskFinding:
    """Tek bir kuralın ürettiği bulgu — raporda bir madde olarak görünür."""

    code: str
    title: str
    rationale: str
    """Düz Türkçe gerekçe: "neden bu bulgu var" sorusunun tam cevabı."""

    level: RiskLevel | None = None
    """Bulgunun seviyeye katkısı. ``None`` = seviyeyi yükseltmez, yalnız işarettir."""

    needs_action: bool = False
    """İnsan kararı bekliyor → dosya tamamlanmamış sayılır."""

    source_refs: tuple[str, ...] = ()
    """Kanıt bağlantıları (Invariant 4): liste URL'i, belge/gazete referansı."""


@dataclass(frozen=True)
class RiskAssessment:
    """Dosyanın risk özeti — seviye + onu doğuran bulgular."""

    level: RiskLevel
    rationale: str
    """Tek cümlelik özet (rapor kapağında ve arayüzde başlık olarak kullanılır)."""

    findings: tuple[RiskFinding, ...] = ()
    complete: bool = True
    """Bekleyen inceleme ya da açık tutarsızlık yoksa ``True``."""

    assessed_at: datetime | None = None

    @property
    def level_label(self) -> str:
        """Seviyenin Türkçe etiketi."""
        return RISK_LEVEL_LABELS[self.level]

    @property
    def open_actions(self) -> tuple[RiskFinding, ...]:
        """İnsan işlemi bekleyen bulgular."""
        return tuple(finding for finding in self.findings if finding.needs_action)

    def to_payload(self) -> list[dict[str, object]]:
        """Bulguları JSONB/denetim-izi uyumlu biçime çevirir (``report`` satırına yazılır)."""
        return [
            {
                "code": finding.code,
                "title": finding.title,
                "rationale": finding.rationale,
                "level": finding.level.value if finding.level else None,
                "needs_action": finding.needs_action,
                "source_refs": list(finding.source_refs),
            }
            for finding in self.findings
        ]


@dataclass
class _Accumulator:
    """Kural değerlendirmesi sırasında biriken bulgular (yalnız modül içi)."""

    findings: list[RiskFinding] = field(default_factory=list)

    def add(self, finding: RiskFinding) -> None:
        self.findings.append(finding)


def _source_refs(match: MatchView) -> tuple[str, ...]:
    """Bir eşleşmenin kanıt referansları: kaynak URL + liste adları."""
    refs: list[str] = []
    if match.source_url:
        refs.append(match.source_url)
    refs.extend(match.datasets)
    return tuple(dict.fromkeys(refs))


def _confirmed_rule(match: MatchView) -> RiskFinding:
    """Onaylanmış bir eşleşmenin hangi seviyeyi doğurduğunu belirler.

    Sıra önemlidir: bir varlık hem yaptırımlı hem PEP olabilir; yaptırım baskındır.
    """
    if has_sanction_topic(match.topics):
        return RiskFinding(
            code=CODE_SANCTION_CONFIRMED,
            level=RiskLevel.HIGH,
            title="Onaylanmış yaptırım eşleşmesi",
            rationale=(
                f"“{match.subject_name}” için “{match.caption}” kaydı yaptırım listesinde "
                f"bulundu ve eşleşme bir uzman tarafından onaylandı "
                f"(skor {match.score:.2f}). Yaptırım listesindeki bir tarafla iş ilişkisi "
                "kurulması ya da sürdürülmesi ayrı bir değerlendirme gerektirir."
            ),
            source_refs=_source_refs(match),
        )
    if has_pep_topic(match.topics):
        return RiskFinding(
            code=CODE_PEP_CONFIRMED,
            level=RiskLevel.ELEVATED,
            title="Onaylanmış PEP eşleşmesi",
            rationale=(
                f"“{match.subject_name}” siyasi nüfuz sahibi kişi (PEP) olarak "
                f"“{match.caption}” kaydıyla eşleşti ve eşleşme onaylandı "
                f"(skor {match.score:.2f}). PEP statüsü tek başına olumsuz bir bulgu "
                "değildir; sıkılaştırılmış müşteri tanıma tedbirleri uygulanmalıdır."
            ),
            source_refs=_source_refs(match),
        )
    return RiskFinding(
        code=CODE_MATCH_CONFIRMED_OTHER,
        level=RiskLevel.ELEVATED,
        title="Onaylanmış izleme listesi eşleşmesi",
        rationale=(
            f"“{match.subject_name}” için “{match.caption}” kaydıyla eşleşme onaylandı "
            f"(skor {match.score:.2f}). Kayıt yaptırım ya da PEP etiketi taşımıyor; "
            "eşleşmenin dosya açısından anlamı gerekçesiyle birlikte değerlendirilmelidir."
        ),
        source_refs=_source_refs(match),
    )


def _evaluate_screenings(
    screenings: Sequence[ScreeningView], accumulator: _Accumulator
) -> tuple[bool, int]:
    """Tarama koşularını değerlendirir; (başarılı koşu var mı, başarısız koşu sayısı)."""
    has_success = False
    failed = 0
    pending_flagged: list[MatchView] = []
    pending_plain: list[MatchView] = []

    for screening in screenings:
        if screening.succeeded:
            has_success = True
        elif screening.status == ScreeningStatus.FAILED.value:
            failed += 1
            continue
        else:
            # queued/running: henüz sonuç yok, ama başarısız da değil.
            continue

        for match in screening.matches:
            if match.decision == MatchDecision.CONFIRMED.value:
                accumulator.add(_confirmed_rule(match))
            elif match.decision == MatchDecision.PENDING.value:
                (pending_flagged if match.flagged else pending_plain).append(match)

    if pending_flagged:
        names = ", ".join(sorted({f"“{match.caption}”" for match in pending_flagged}))
        accumulator.add(
            RiskFinding(
                code=CODE_MATCH_PENDING_FLAGGED,
                level=None,  # Karara bağlanmamış eşleşme seviyeyi YÜKSELTMEZ (ADR-0006).
                needs_action=True,
                title=f"{len(pending_flagged)} yüksek skorlu eşleşme karar bekliyor",
                rationale=(
                    "Eşik bandının üst bölgesine düşen ve otomatik olarak işaretlenen "
                    f"eşleşmeler henüz karara bağlanmadı: {names}. Yüksek skor tek başına "
                    "onay değildir; dosya, bu eşleşmeler onaylanana ya da gerekçesiyle "
                    "elenene kadar tamamlanmış sayılmaz."
                ),
                source_refs=tuple(ref for match in pending_flagged for ref in _source_refs(match)),
            )
        )
    if pending_plain:
        accumulator.add(
            RiskFinding(
                code=CODE_MATCH_PENDING,
                level=None,
                needs_action=True,
                title=f"{len(pending_plain)} eşleşme inceleme bekliyor",
                rationale=(
                    "İnceleme bandına düşen eşleşmeler henüz karara bağlanmadı. "
                    "Her biri onaylanmalı ya da gerekçesiyle elenmelidir."
                ),
            )
        )

    if failed:
        accumulator.add(
            RiskFinding(
                code=CODE_SCREENING_FAILED,
                level=None,
                needs_action=True,
                title=f"{failed} tarama koşusu sonuç üretmedi",
                rationale=(
                    "Tarama motoruna erişilemediği için koşu başarısız oldu. Başarısız bir "
                    "koşu “temiz” anlamına GELMEZ; tarama tekrarlanmadan dosya hakkında "
                    "sonuç çıkarılmamalıdır."
                ),
            )
        )
    return has_success, failed


def _evaluate_discrepancies(
    discrepancies: Sequence[DiscrepancyView], accumulator: _Accumulator
) -> None:
    """Açık tutarsızlıkları değerlendirir (kapatılmış olanlar seviyeyi etkilemez)."""
    open_items = [item for item in discrepancies if item.status == DiscrepancyStatus.OPEN.value]
    critical = [item for item in open_items if item.severity == DiscrepancySeverity.CRITICAL.value]
    other = [item for item in open_items if item.severity != DiscrepancySeverity.CRITICAL.value]

    for item in critical:
        accumulator.add(
            RiskFinding(
                code=CODE_DISCREPANCY_CRITICAL,
                level=RiskLevel.ELEVATED,
                needs_action=True,
                title=f"Kimlik tanımlayıcısında açık tutarsızlık: {item.attribute_label}",
                rationale=(
                    f"Beyan edilen değer ({item.declared_value}) ile belge/kütük kaydındaki "
                    f"değer ({item.observed_value}) örtüşmüyor. Kimlik tanımlayıcısındaki "
                    "fark, müşterinin beyan ettiği kişi/kuruluş olup olmadığı sorusunu "
                    "doğurur ve açıklanmadan dosya kapatılmamalıdır."
                ),
                source_refs=(item.observed_source_ref,) if item.observed_source_ref else (),
            )
        )
    if other:
        labels = ", ".join(sorted({item.attribute_label for item in other}))
        accumulator.add(
            RiskFinding(
                code=CODE_DISCREPANCY_OPEN,
                level=None,
                needs_action=True,
                title=f"{len(other)} açık tutarsızlık",
                rationale=(
                    f"Şu alanlarda beyan ile belge/kütük verisi çelişiyor: {labels}. "
                    "Tutarsızlık tek başına olumsuz bir bulgu değildir, ancak "
                    "açıklanması ve gerekçesiyle karara bağlanması gerekir."
                ),
                source_refs=tuple(
                    item.observed_source_ref for item in other if item.observed_source_ref
                ),
            )
        )


def _summary_sentence(level: RiskLevel, findings: Sequence[RiskFinding], complete: bool) -> str:
    """Seviyeyi tek cümleyle özetler (rapor kapağı ve arayüz başlığı)."""
    leading = next(
        (finding for finding in findings if finding.level is level and finding.level), None
    )
    if level is RiskLevel.UNKNOWN:
        return (
            "Risk seviyesi belirlenemedi: bu varlık için sonuç üreten bir tarama koşusu yok. "
            "Bu, “temiz” anlamına gelmez."
        )
    if leading is not None:
        base = f"{RISK_LEVEL_LABELS[level]} risk — {leading.title.lower()}."
    else:
        base = "Standart risk — tarama koştu, risk seviyesini yükselten bir bulgu tespit edilmedi."
    if not complete:
        base += " Dosyada karar bekleyen bulgular var; değerlendirme henüz tamamlanmamıştır."
    return base


def assess_risk(
    *,
    screenings: Sequence[ScreeningView],
    discrepancies: Sequence[DiscrepancyView] = (),
    assessed_at: datetime | None = None,
) -> RiskAssessment:
    """Kural tabanlı risk özetini üretir (şeffaf, öğrenmesiz — bkz. modül başlığı).

    Seviye, bulguların en yükseğidir; ``level=None`` taşıyan bulgular seviyeyi
    değiştirmez, yalnız dosyayı "tamamlanmadı" olarak işaretler.
    """
    accumulator = _Accumulator()
    has_success, _failed = _evaluate_screenings(screenings, accumulator)
    _evaluate_discrepancies(discrepancies, accumulator)

    if not screenings:
        accumulator.add(
            RiskFinding(
                code=CODE_SCREENING_MISSING,
                level=None,
                needs_action=True,
                title="Tarama yapılmadı",
                rationale=(
                    "Bu varlık için yaptırım/PEP taraması hiç çalıştırılmadı. Müşteri tanıma "
                    "dosyası, tarama koşulmadan tamamlanmış sayılamaz."
                ),
            )
        )

    findings = tuple(
        sorted(
            accumulator.findings,
            key=lambda finding: (
                -_LEVEL_RANK.get(finding.level, -1) if finding.level else 1,
                finding.code,
            ),
        )
    )
    complete = not any(finding.needs_action for finding in findings)

    levels = [finding.level for finding in findings if finding.level is not None]
    if not has_success:
        # Sonuç üreten koşu yoksa seviye Belirsiz'dir — ancak gerçek bir bulgu
        # (ör. kimlik tutarsızlığı) varsa o bastırır: bilinen kötü, bilinmezden ağırdır.
        levels.append(RiskLevel.UNKNOWN)
    level = max(levels, key=lambda item: _LEVEL_RANK[item]) if levels else RiskLevel.STANDARD

    return RiskAssessment(
        level=level,
        rationale=_summary_sentence(level, findings, complete),
        findings=findings,
        complete=complete,
        assessed_at=assessed_at,
    )
