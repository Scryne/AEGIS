"""İzleme bildirimi: tercih ayrıştırma ve e-posta metni. Metin kişisel veri taşımaz."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from aegis_core.config import Settings
from aegis_core.monitoring.notify import Preferences, _body, _parse
from aegis_core.notifications.email import OutgoingEmail, SmtpEmailSender, build_message


def test_gecersiz_tercih_varsayilana_duser() -> None:
    prefs = _parse({"critical": "kapali", "high": "digest", "roles": ["yok"]})
    assert prefs.critical == "immediate"
    assert prefs.high == "digest"
    assert prefs.roles == Preferences().roles


def test_eposta_metni_kisisel_veri_tasimaz_ve_taranamayani_soyler() -> None:
    alarm = SimpleNamespace(severity="critical", diff={"items": [{"name": "Gizli Şirket A.Ş."}]})
    ayar = cast(Settings, SimpleNamespace(web_base_url="https://panel.example/"))
    konu, govde = _body(alerts=[cast(Any, alarm)], unreachable=2, settings=ayar)
    assert "1 kritik" in konu
    assert "Gizli Şirket" not in govde
    assert "sonuç YOK, temiz değil" in govde
    assert "https://panel.example/monitoring" in govde


def test_alicilar_birbirini_gormez() -> None:
    posta = build_message(
        OutgoingEmail(to=("a@x.test", "b@x.test"), subject="k", body="g"), sender="s@x.test"
    )
    assert posta["To"] == "s@x.test"
    assert "a@x.test" in posta["Bcc"]


def test_smtp_ayari_yoksa_kapali_sayilir() -> None:
    ayar = cast(Settings, SimpleNamespace(smtp_host=None, smtp_from=None))
    assert SmtpEmailSender(ayar).configured is False
