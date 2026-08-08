"""MASAK dondurma listesini FtM veri kümesine çeviren operatör aracı (E1.3).

Günlük otomatik yenileme ``sanctions.sync`` Celery job'ındadır; bu script iki iş içindir:

1. **İlk kurulum / doğrulama:** yeni indirilen bir liste dosyasının sütun düzeni
   ``COLUMN_ALIASES`` ile eşleşiyor mu, kaç kayıt tanınıyor — job'ı beklemeden görülür.
2. **Acil güncelleme:** yeni bir karar yayımlandığında dosyayı elle üretip yente'yi
   yeniden indeksletmek.

Kullanım::

    uv run python scripts/masak_dataset.py girdi.csv --out /manifests/masak/entities.ftm.json
    uv run python scripts/masak_dataset.py girdi.csv --dry-run   # yalnız rapor

``--dry-run`` hiçbir dosya yazmaz; tanınan/atlanan kayıtları ve tür dağılımını basar.
Yeni bir liste biçimini ilk kez bağlarken **önce bununla** bakılmalıdır.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from aegis_core.screening.masak import (
    DEFAULT_DATASET_NAME,
    build_dataset_file,
    parse_csv,
    to_ftm_entities,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MASAK dondurma listesi → FtM veri kümesi")
    parser.add_argument("source", type=Path, help="Kaynak CSV dosyası")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("entities.ftm.json"),
        help="Yazılacak FtM JSON-lines dosyası",
    )
    parser.add_argument("--dataset", default=DEFAULT_DATASET_NAME, help="Veri kümesi adı")
    parser.add_argument("--source-url", default=None, help="Kayıtlara basılacak kanıt bağlantısı")
    parser.add_argument(
        "--dry-run", action="store_true", help="Dosya yazma; yalnız tanıma raporu bas"
    )
    args = parser.parse_args(argv)

    if not args.source.exists():
        print(f"HATA: kaynak dosya yok: {args.source}", file=sys.stderr)
        return 1

    # utf-8-sig: Excel'den çıkan Türkçe CSV'ler BOM ile başlar.
    content = args.source.read_text(encoding="utf-8-sig")
    records = parse_csv(content)
    if not records:
        print(
            "HATA: hicbir kayit taninmadi. Sutun basliklarini COLUMN_ALIASES ile "
            "karsilastirin (aegis_core/screening/masak.py).",
            file=sys.stderr,
        )
        return 2

    turler = Counter(record.record_type.value for record in records)
    print(f"Taninan kayit: {len(records)}")
    for tur, adet in sorted(turler.items()):
        print(f"  {tur}: {adet}")
    tanimsiz = sum(1 for record in records if record.extra)
    if tanimsiz:
        print(f"UYARI: {tanimsiz} kayitta eslenmemis sutun var (extra alaninda saklandi).")

    if args.dry_run:
        entities = to_ftm_entities(records, dataset_name=args.dataset, source_url=args.source_url)
        print(f"Uretilecek varlik: {len(entities)} (kuru calisma — dosya yazilmadi)")
        return 0

    written = build_dataset_file(
        content, args.out, dataset_name=args.dataset, source_url=args.source_url
    )
    print(f"{written} varlik yazildi: {args.out}")
    print("yente'yi yeniden indeksletmeyi unutmayin (sanctions.sync ya da /updatez).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
