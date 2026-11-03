"""Her kiracının denetim izi zincirini doğrula (E1.6 geri yükleme tatbikatı, ADR-0004).

    python scripts/denetim_zinciri_dogrula.py                    # DATABASE_URL'deki veritabanı
    python scripts/denetim_zinciri_dogrula.py --veritabani aegis_tatbikat

Geri yüklenen bir yedeğin "açılıyor" olması yetmez; denetim izinin hash zinciri her kiracıda
baştan sona tutmalıdır. Uygulama rolüyle (RLS'ye tabi) bağlanır, her kiracı için kendi
bağlamını ayarlayıp ``verify_chain`` koşar — API'deki ``GET /audit/verify`` ile aynı kod.

Çıkış: 0 tüm zincirler sağlam, 1 en az bir kiracıda kırık, 2 bağlantı/yapılandırma hatası.
Kiracı adı değil yalnız kısa adı (slug) ve sayılar basılır.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.engine import make_url

from aegis_core.config import get_settings
from aegis_core.db import create_session_factory, set_tenant_context
from aegis_core.models import Organization
from aegis_core.services.audit import verify_chain


async def run(database_url: str) -> int:
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(database_url, pool_pre_ping=True)
    factory = create_session_factory(engine)
    broken = 0
    try:
        async with factory() as session, session.begin():
            tenants = (await session.execute(select(Organization.id, Organization.slug))).all()
        for tenant_id, slug in sorted(tenants, key=lambda t: t.slug):
            async with factory() as session, session.begin():
                await set_tenant_context(session, tenant_id)
                result = await verify_chain(session)
            durum = "sağlam" if result.ok else f"KIRIK seq={result.broken_seq} ({result.reason})"
            print(f"{slug:30s} olay={result.events_checked:6d} {durum}")
            broken += 0 if result.ok else 1
    finally:
        await engine.dispose()
    print(f"{len(tenants)} kiracı, {broken} kırık zincir")
    return 1 if broken else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Denetim izi zincir doğrulaması (tüm kiracılar)")
    p.add_argument("--veritabani", help="DATABASE_URL'deki veritabanı adının yerine (tatbikat)")
    args = p.parse_args(argv)
    url = make_url(get_settings().database_url)
    if args.veritabani:
        url = url.set(database=args.veritabani)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        return asyncio.run(run(url.render_as_string(hide_password=False)))
    except OSError as exc:
        print(f"Bağlantı kurulamadı: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
