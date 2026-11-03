"""Kiracı aç (E1.6): kurum + sahip hesabı oluştur, sahibe parola belirleme daveti gönder.

    python scripts/kiraci_ac.py --ad "Örnek Mali Müşavirlik" --slug ornek-ofis \\
        --sahip-eposta sahip@ornek.com.tr --sahip-ad "Ad Soyad" [--plan pilot]

    python scripts/kiraci_ac.py --yeniden-davet --slug ornek-ofis   # süresi geçen davet

Üretimde API konteynerinde çalışır (imaj ``scripts/``'i taşır):

    docker compose -f infra/compose/docker-compose.prod.yml --env-file /etc/aegis/aegis.env \\
        run --rm api python scripts/kiraci_ac.py ...

Davet e-postayla gider (``SMTP_*``). SMTP kurulu değilse araç **hiçbir şey açmadan** durur;
bağlantıyı elle iletmek için ``--baglantiyi-yazdir`` verilir (bağlantı ekrana basılır, kanal
denetim izine ``manual`` olarak yazılır). Parola hiçbir zaman operatörde oluşmaz.

Bağlantı uygulama rolüyle (``DATABASE_URL``, RLS'ye tabi) kurulur; ayrıcalıklı bağlantı
gerekmez. Plan değişikliği ayrı araçtır: ``scripts/plan_ata.py``.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime

from aegis_core.billing.plans import DEFAULT_PLAN, PLANS
from aegis_core.config import Settings, get_settings
from aegis_core.db import create_engine, create_session_factory
from aegis_core.notifications.email import (
    EmailSender,
    EmailSendError,
    OutgoingEmail,
    default_sender,
)
from aegis_core.provisioning import (
    InviteResult,
    ProvisionError,
    create_invite_link,
    find_owner,
    provision_tenant,
    record_invite,
    validate_invite_hours,
)

DEFAULT_INVITE_HOURS = 72


def _davet_epostasi(to: str, org_name: str, link: str, hours: int) -> OutgoingEmail:
    return OutgoingEmail(
        to=(to,),
        subject="AEGIS hesabınız açıldı",
        body=(
            f"{org_name} için AEGIS hesabınız açıldı; kurum sahibi olarak tanımlandınız.\n\n"
            "Parolanızı belirlemek için bağlantıyı açın:\n\n"
            f"{link}\n\n"
            f"Bağlantı {hours} saat geçerlidir. Süresi geçerse bize yazın, yenisini gönderelim.\n"
            "Bu e-postayı beklemiyorsanız yok sayın; parola belirlenmeden hesaba girilemez."
        ),
    )


async def _teslim(
    sender: EmailSender, message: OutgoingEmail, link: str, *, print_link: bool
) -> InviteResult:
    if sender.configured:
        try:
            await sender.send(message)
        except EmailSendError as exc:
            if print_link:
                print(f"E-posta gitmedi ({exc}); bağlantıyı elle iletin:\n{link}")
                return InviteResult(channel="manual", delivered=False, error=str(exc))
            return InviteResult(channel="smtp", delivered=False, error=str(exc))
        return InviteResult(channel="smtp", delivered=True)
    print(f"Davet bağlantısı (sahibe güvenli bir kanaldan iletin):\n{link}")
    return InviteResult(channel="manual", delivered=False, error=None)


async def run(
    args: argparse.Namespace, settings: Settings, sender: EmailSender | None = None
) -> int:
    if settings.auth_secret is None:
        print("AUTH_SECRET tanımlı değil; davet bağlantısı imzalanamaz.", file=sys.stderr)
        return 2
    try:
        validate_invite_hours(args.gecerlilik_saat)
    except ProvisionError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    sender = sender or default_sender(settings)
    if not sender.configured and not args.baglantiyi_yazdir:
        print(
            "SMTP yapılandırılmamış (SMTP_HOST/SMTP_FROM). Hiçbir şey oluşturulmadı. "
            "Bağlantıyı elle iletmek için --baglantiyi-yazdir verin.",
            file=sys.stderr,
        )
        return 2

    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            try:
                async with session.begin():
                    if args.yeniden_davet:
                        org, owner = await find_owner(session, args.slug)
                        tenant_id, org_name = org.id, org.name
                        owner_id, owner_email = owner.id, owner.email
                    else:
                        result = await provision_tenant(
                            session,
                            org_name=args.ad,
                            org_slug=args.slug,
                            owner_email=args.sahip_eposta,
                            owner_full_name=args.sahip_ad,
                            plan_code=args.plan,
                            today=datetime.now(UTC).date(),
                        )
                        tenant_id, owner_id = result.tenant_id, result.owner_user_id
                        owner_email, org_name = args.sahip_eposta.strip(), args.ad.strip()
                        print(f"Kurum açıldı: {result.slug} ({tenant_id}) plan={result.plan_code}")
                link = create_invite_link(
                    user_id=owner_id,
                    secret=settings.auth_secret,
                    web_base_url=settings.web_base_url,
                    valid_hours=args.gecerlilik_saat,
                )
            except ProvisionError as exc:
                print(f"Kiracı açılamadı: {exc}", file=sys.stderr)
                return 1

            invite = await _teslim(
                sender,
                _davet_epostasi(owner_email, org_name, link, args.gecerlilik_saat),
                link,
                print_link=args.baglantiyi_yazdir,
            )
            async with session.begin():
                await record_invite(
                    session,
                    tenant_id=tenant_id,
                    owner_user_id=owner_id,
                    result=invite,
                    valid_hours=args.gecerlilik_saat,
                )
    finally:
        await engine.dispose()

    if invite.channel == "smtp" and not invite.delivered:
        print(
            f"Davet e-postası GİTMEDİ: {invite.error}. Hesap açık; "
            f"--yeniden-davet --slug {args.slug} ile tekrar deneyin.",
            file=sys.stderr,
        )
        return 3
    if invite.delivered:
        print("Davet e-postası gönderildi.")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="AEGIS kiracı açma (kurum + sahip + davet)")
    p.add_argument("--slug", required=True, help="kurumun kısa adı (küçük harf, rakam, tire)")
    p.add_argument("--ad", help="kurumun tam adı")
    p.add_argument("--sahip-eposta", help="kurum sahibinin e-postası")
    p.add_argument("--sahip-ad", help="kurum sahibinin adı (isteğe bağlı)")
    p.add_argument("--plan", default=DEFAULT_PLAN, choices=sorted(PLANS))
    p.add_argument(
        "--gecerlilik-saat",
        type=int,
        default=DEFAULT_INVITE_HOURS,
        help=f"davet bağlantısının ömrü (saat, varsayılan {DEFAULT_INVITE_HOURS}, en çok 168)",
    )
    p.add_argument(
        "--baglantiyi-yazdir",
        action="store_true",
        help="SMTP yoksa ya da gitmezse bağlantıyı ekrana bas (elle iletilecek)",
    )
    p.add_argument(
        "--yeniden-davet",
        action="store_true",
        help="var olan kurumun sahibine yeni davet bağlantısı gönder",
    )
    args = p.parse_args(argv)
    if not args.yeniden_davet and not (args.ad and args.sahip_eposta):
        p.error("yeni kurum için --ad ve --sahip-eposta zorunlu")
    return args


def main(argv: list[str] | None = None) -> int:
    if sys.platform == "win32":  # psycopg async, ProactorEventLoop ile çalışmaz
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(run(parse_args(argv), get_settings()))


if __name__ == "__main__":
    raise SystemExit(main())
