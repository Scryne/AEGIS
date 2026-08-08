"""Tarama eşikleri ve eşleşme kararı — kiracı-başına yapılandırılabilir bant (E1.3).

Üç bölgeli bant (Ürün Planı: "otomatik temizle / incele / otomatik işaretle"):

    0 ─────────── auto_dismiss_below ─────────── auto_flag_at ─────────── 1
      otomatik elenen        İNCELEME BANDI        otomatik işaretlenen

- **Alt bölge:** skor düşük → aday otomatik *elenir* (``dismissed``, ``auto=True``).
  Kayıt silinmez: dosyada "gerekçesiyle elenen eşleşmeler" olarak raporlanır (E1.5).
- **Orta bant:** insan incelemesi bekler (``pending``) — HITL'in asıl işi budur.
- **Üst bölge:** skor yüksek → yine ``pending`` ama **işaretli** (``flagged``). Yüksek
  skorlu bir yaptırım eşleşmesi *otomatik onaylanmaz*: onay bir insan kararıdır
  (Ürün Planı §3.3 — karar desteği, karar değil).

Eşikler ``tenant_setting`` tablosunda ``screening.thresholds`` anahtarında tutulur.
Bozuk bir yapılandırma sessizce varsayılana düşmez: yanlış bir ``auto_dismiss_below``
gerçek bir yaptırım eşleşmesini sessizce eleyebilirdi (yanlış negatif). Bu yüzden
``ScreeningThresholds.from_mapping`` hatalı değerde ``ValueError`` yükseltir.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Self

SCREENING_THRESHOLD_SETTING_KEY = "screening.thresholds"


class MatchDecision(StrEnum):
    """Bir eşleşme adayının insan-değerlendirmesi durumu (HITL)."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"


class MatchBand(StrEnum):
    """Adayın skoruna göre düştüğü bant (kararın gerekçesi)."""

    AUTO_DISMISS = "auto_dismiss"
    REVIEW = "review"
    AUTO_FLAG = "auto_flag"


@dataclass(frozen=True)
class MatchDisposition:
    """Eşik bandının bir skor için ürettiği başlangıç kararı."""

    decision: MatchDecision
    band: MatchBand
    auto: bool
    """Kararı eşik bandı mı verdi (insan değil) — denetim izinde ayırt edilir."""

    flagged: bool
    """Yüksek skor bölgesi: acil inceleme gerektirir, risk özetinde öne çıkar."""


@dataclass(frozen=True)
class ScreeningThresholds:
    """Kiracının tarama eşikleri (0..1 aralığında skorlar)."""

    auto_dismiss_below: float = 0.65
    auto_flag_at: float = 0.85
    candidate_cutoff: float = 0.50
    """yente'ye gönderilen alt kesme: bunun altındaki adaylar hiç döndürülmez.

    ``auto_dismiss_below``dan küçük ya da eşit olmalıdır — aksi hâlde otomatik eleme
    bölgesinin bir kısmı hiç görülmez ve "elenen eşleşmeler" raporu eksik kalır.
    """

    def __post_init__(self) -> None:
        for field_name in ("auto_dismiss_below", "auto_flag_at", "candidate_cutoff"):
            value = getattr(self, field_name)
            if not isinstance(value, int | float) or isinstance(value, bool):
                raise ValueError(f"{field_name} sayısal olmalıdır.")
            if not 0.0 <= float(value) <= 1.0:
                raise ValueError(f"{field_name} 0 ile 1 arasında olmalıdır (verilen: {value}).")
        if self.candidate_cutoff > self.auto_dismiss_below:
            raise ValueError("candidate_cutoff, auto_dismiss_below değerinden büyük olamaz.")
        if self.auto_dismiss_below > self.auto_flag_at:
            raise ValueError("auto_dismiss_below, auto_flag_at değerinden büyük olamaz.")

    @classmethod
    def from_mapping(cls, raw: dict[str, Any] | None) -> Self:
        """Kiracı ayarından eşikleri kurar; eksik alanlar varsayılana düşer.

        Tanınmayan anahtar **hata** üretir: ``auto_dismis_below`` gibi bir yazım hatası
        sessizce yok sayılırsa kiracı, ayarladığını sandığı eşikle çalışmaz.
        """
        if not raw:
            return cls()
        known = {"auto_dismiss_below", "auto_flag_at", "candidate_cutoff"}
        unknown = sorted(set(raw) - known)
        if unknown:
            raise ValueError(f"Tanınmayan eşik anahtarı: {', '.join(unknown)}")
        defaults = cls()
        return cls(
            auto_dismiss_below=float(raw.get("auto_dismiss_below", defaults.auto_dismiss_below)),
            auto_flag_at=float(raw.get("auto_flag_at", defaults.auto_flag_at)),
            candidate_cutoff=float(raw.get("candidate_cutoff", defaults.candidate_cutoff)),
        )

    def to_mapping(self) -> dict[str, float]:
        """Denetim olayına ve tarama kaydına gömülecek anlık görüntü (JSONB uyumlu)."""
        return {
            "auto_dismiss_below": self.auto_dismiss_below,
            "auto_flag_at": self.auto_flag_at,
            "candidate_cutoff": self.candidate_cutoff,
        }

    def disposition(self, score: float) -> MatchDisposition:
        """Skora göre başlangıç kararını üretir (bkz. modül başlığındaki bant şeması)."""
        if score < self.auto_dismiss_below:
            return MatchDisposition(
                decision=MatchDecision.DISMISSED,
                band=MatchBand.AUTO_DISMISS,
                auto=True,
                flagged=False,
            )
        if score >= self.auto_flag_at:
            return MatchDisposition(
                decision=MatchDecision.PENDING,
                band=MatchBand.AUTO_FLAG,
                auto=False,
                flagged=True,
            )
        return MatchDisposition(
            decision=MatchDecision.PENDING,
            band=MatchBand.REVIEW,
            auto=False,
            flagged=False,
        )


DEFAULT_THRESHOLDS = ScreeningThresholds()
