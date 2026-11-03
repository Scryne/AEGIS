"""Kiracı açma (E1.6): operatörün kurum + sahip hesabı açıp sahibe davet göndermesi.

Kayıt ucundan (``POST /auth/register``) farkı: parola operatörde hiç oluşmaz. Sahip hesabı
parolasız açılır (giriş yapamaz) ve sahibe süreli bir **parola belirleme bağlantısı**
gönderilir; bağlantı mevcut parola sıfırlama jetonudur, yeni bir kimlik yolu açılmaz.

Değişmezler:

- Uygulama rolüyle (``DATABASE_URL``, RLS'ye tabi ``aegis_app``) çalışır; süper kullanıcı
  RLS'yi baypas ederdi. Kontrol düzlemi tabloları (organization/user_account/membership)
  RLS'sizdir (ADR-0002); denetim olayı ise yeni kiracının bağlamı ayarlanarak yazılır.
- Kurum, sahip, üyelik ve ``tenant.provision`` olayı TEK transaction'dır: yarım kiracı
  kalmaz, olaysız kiracı da olmaz. Davet ayrı bir ``tenant.invite`` olayıdır (kanal ve
  sonuçla) — e-posta adresi olaya yazılmaz.
"""

from aegis_core.provisioning.service import (
    InviteResult,
    ProvisionError,
    ProvisionResult,
    create_invite_link,
    find_owner,
    provision_tenant,
    record_invite,
    validate_invite_hours,
)

__all__ = [
    "InviteResult",
    "ProvisionError",
    "ProvisionResult",
    "create_invite_link",
    "find_owner",
    "provision_tenant",
    "record_invite",
    "validate_invite_hours",
]
