"""Yaptırım/PEP konu (topic) yüklemleri — "eşleşme neyi ifade ediyor" tek kaynağı.

yente/OpenSanctions her varlığa FtM **topic** etiketleri verir (``sanction``,
``sanction.linked``, ``role.pep``, ``crime.fin`` …). "Bu bir yaptırım eşleşmesi mi",
"bu kişi siyasi nüfuz sahibi mi" soruları iki ayrı yerde sorulur:

- ``screening.service.summarize_screening`` — koşunun karar dağılımı (ekranda gösterilen
  "yaptırım/PEP" sayaçları),
- ``reports.risk`` — dosyanın risk seviyesini belirleyen kural motoru.

İkisinin **aynı** cevabı vermesi zorunludur: ekranda "1 yaptırım eşleşmesi" yazıp raporda
"Standart risk" demek, ürünün savunulabilirliğini bozar. Bu yüzden yüklemler tek modülde
durur ve her iki taraf da buradan import eder.

Önek eşleşmesi bilinçlidir: ``sanction.linked`` (yaptırımlıya bağlı varlık) ve
``sanction.counter`` (karşı-yaptırım listesi) de yaptırım bağlamıdır ve gözden
kaçırılmamalıdır — yanlış negatif bu üründeki tehlikeli hatadır.
"""

from __future__ import annotations

from collections.abc import Iterable

SANCTION_TOPIC_PREFIX = "sanction"
PEP_TOPIC_PREFIX = "role.pep"


def is_sanction_topic(topic: object) -> bool:
    """Konu bir yaptırım bağlamını mı gösteriyor (``sanction*``)."""
    return str(topic).startswith(SANCTION_TOPIC_PREFIX)


def is_pep_topic(topic: object) -> bool:
    """Konu siyasi nüfuz sahibi (PEP) etiketini mi taşıyor (``role.pep*``)."""
    return str(topic).startswith(PEP_TOPIC_PREFIX)


def has_sanction_topic(topics: Iterable[object]) -> bool:
    """Konu listesinde yaptırım etiketi var mı."""
    return any(is_sanction_topic(topic) for topic in topics)


def has_pep_topic(topics: Iterable[object]) -> bool:
    """Konu listesinde PEP etiketi var mı."""
    return any(is_pep_topic(topic) for topic in topics)
