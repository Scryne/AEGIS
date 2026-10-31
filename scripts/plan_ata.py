"""Kiracıya plan ata (E2.6, ADR-0012) — elle yetkilendirme; ödeme dışarıda yürür.

    python scripts/plan_ata.py --slug ornek-ofis --plan standart
    python scripts/plan_ata.py --liste

Plan kontrol düzlemi tablosundadır (``organization``, RLS'siz); ayrıcalıklı bağlantı
(``AEGIS_DATABASE_ADMIN_URL``) kullanılır. Her değişiklik ekrana eski → yeni olarak yazılır;
sözleşme numarası ``--not`` ile kayda düşülebilir.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime

from sqlalchemy import create_engine, text

from aegis_core.billing.plans import PLANS
from aegis_core.config import get_settings


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="AEGIS kiracı planı")
    p.add_argument("--slug")
    p.add_argument("--plan", choices=sorted(PLANS))
    p.add_argument("--liste", action="store_true", help="kiracıları ve planlarını listele")
    args = p.parse_args(argv)

    engine = create_engine(get_settings().migration_database_url)
    with engine.begin() as conn:
        if args.liste or not (args.slug and args.plan):
            for slug, plan, since in conn.execute(
                text("SELECT slug, plan_code, plan_started_on FROM organization ORDER BY slug")
            ):
                print(f"{slug:30s} {plan:10s} {since or '—'}")
            return 0 if args.liste else 2
        eski = conn.execute(
            text("SELECT plan_code FROM organization WHERE slug = :s FOR UPDATE"), {"s": args.slug}
        ).scalar()
        if eski is None:
            print(f"kiracı bulunamadı: {args.slug}", file=sys.stderr)
            return 1
        conn.execute(
            text(
                "UPDATE organization SET plan_code = :p, plan_started_on = :d, updated_at = now() "
                "WHERE slug = :s"
            ),
            {"p": args.plan, "d": datetime.now(UTC).date(), "s": args.slug},
        )
    print(f"{args.slug}: {eski} → {args.plan}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
