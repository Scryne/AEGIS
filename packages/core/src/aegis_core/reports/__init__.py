"""Raporlama alt sistemi — risk özeti ve durum tespiti dosyası (E1.5).

Katmanlar:

- ``risk``: kural tabanlı, öğrenmesiz risk özeti (saf fonksiyon, veritabanı bilmez).
- ``dossier``: dosyanın içeriğini veritabanından toplar (``DossierData``).
- ``render``: aynı ``DossierData``dan PDF (Jinja2 + xhtml2pdf) ve Word (python-docx).
- ``service``: topla → oluştur → nesne deposuna sakla → ``report`` satırı → denetim olayı.
- ``labels``: rapor metinlerinin Türkçe etiketleri.

``risk`` bilinçli olarak en altta ve bağımsızdır: kuralların doğruluğu, veritabanı ya da
oluşturucu olmadan test edilebilmelidir.
"""

from aegis_core.reports.dossier import DossierData, build_dossier
from aegis_core.reports.risk import (
    RISK_LEVEL_LABELS,
    DiscrepancyView,
    MatchView,
    RiskAssessment,
    RiskFinding,
    RiskLevel,
    ScreeningView,
    assess_risk,
)

__all__ = [
    "RISK_LEVEL_LABELS",
    "DiscrepancyView",
    "DossierData",
    "MatchView",
    "RiskAssessment",
    "RiskFinding",
    "RiskLevel",
    "ScreeningView",
    "assess_risk",
    "build_dossier",
]
