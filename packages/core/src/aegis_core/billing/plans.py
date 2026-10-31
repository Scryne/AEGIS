"""Plan kataloğu v1 (E2.6, ADR-0012) — kodda sabit, kiracıya elle atanır.

Fiyat burada değil: fiyat Phase 0 sinyallerine bağlı bir ticari karardır ve sözleşmede yaşar.
Kod yalnız planın *ne kadar iş* içerdiğini bilir: ayda dahil tarama sorgusu, izlemeye alınabilen
varlık sayısı ve dahil kotanın aşılıp aşılamayacağı.

**Sorgu = taranan özne.** Bir tarama şirketi ve ilgili kişilerini (yönetici, UBO) birlikte tarar;
maliyet ve değer özne başınadır, bu yüzden kota özne sayar. Gece izlemesinin kendi koşuları
izleme eklentisinin parçasıdır, sorgu kotasından düşmez.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    code: str
    name: str
    included_queries: int
    """Takvim ayı başına dahil taranan özne."""
    monitored_entity_limit: int
    """Aynı anda gece izlemesinde tutulabilecek varlık."""
    overage_allowed: bool
    """True: dahil kota aşılınca tarama sürer, aşım ayrıca faturalanır (elle). False: durur."""


PLANS: dict[str, Plan] = {
    "pilot": Plan("pilot", "Pilot", 300, 25, overage_allowed=False),
    "standart": Plan("standart", "Standart", 1500, 150, overage_allowed=True),
    "kurumsal": Plan("kurumsal", "Kurumsal", 6000, 1000, overage_allowed=True),
}
DEFAULT_PLAN = "pilot"


def get_plan(code: str | None) -> Plan:
    return PLANS.get(code or DEFAULT_PLAN, PLANS[DEFAULT_PLAN])
