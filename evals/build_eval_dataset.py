"""Değerlendirme seti → yente'nin indeksleyeceği FtM veri kümesi (E1.3).

``cases.json`` içindeki her referans varlığı "yaptırımlı" bir FtM kaydına çevirir.
Uçtan uca recall kapısı (``test_screening_recall.py``) bu küçük veri kümesini indeksler:
OpenSanctions'ın tamamını (GB'larca) indirmeden, gerçek yente + Elasticsearch üzerinden
ölçüm yapılabilir.

Kullanım::

    uv run python evals/build_eval_dataset.py

Çıktı ``evals/fixtures/entities.ftm.json`` dosyasına yazılır ve depoya işlenir; compose
bu dosyayı yente konteynerine bağlar.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

EVALS_DIR = Path(__file__).parent
CASES_PATH = EVALS_DIR / "turkish_screening" / "cases.json"
OUTPUT_PATH = EVALS_DIR / "fixtures" / "entities.ftm.json"
DATASET_NAME = "aegis_eval"


def build_entities() -> list[dict[str, Any]]:
    """Vakaların referans yazımlarından FtM varlıkları üretir."""
    with CASES_PATH.open(encoding="utf-8") as handle:
        data = json.load(handle)

    entities: list[dict[str, Any]] = []
    for case in data["cases"]:
        entities.append(
            {
                "id": f"aegis-eval-{case['id']}",
                "schema": "Person" if case["subject_type"] == "person" else "Company",
                "properties": {
                    # YALNIZ referans yazım indekslenir: varyantları takma ad olarak
                    # eklemek testi anlamsızlaştırırdı — ölçtüğümüz şey tam olarak
                    # normalizasyonun varyantları referansa taşıyıp taşımadığı.
                    "name": [case["canonical"]],
                    "topics": ["sanction"],
                    "country": ["tr"],
                    "sourceUrl": [f"https://aegis.local/evals/{case['id']}"],
                },
                "datasets": [DATASET_NAME],
            }
        )
    return entities


def main() -> None:
    entities = build_entities()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as handle:
        for entity in entities:
            handle.write(json.dumps(entity, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
    # Not: ASCII çıktı — Windows konsolu (cp1254) tipografik okları kodlayamıyor.
    print(f"{len(entities)} varlik yazildi: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
