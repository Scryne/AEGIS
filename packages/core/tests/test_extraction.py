"""Türkçe belge çıkarımı testleri (E1.4, R2).

Fixture'lar gerçek faaliyet belgesi / imza sirküleri metinlerinin yapısını taklit eder.
Ölçüt iki yönlüdür:

- **Recall:** belgede yazan alanlar öneri olarak çıkmalı (kaçan öneri, kullanıcının
  fark etmeyeceği eksiktir).
- **Kesinlik:** tarih, sermaye, telefon gibi rakam öbekleri vergi numarası sanılmamalı;
  "Yönetim Kurulu" gibi kurumsal ifadeler kişi adı sanılmamalı.
"""

from __future__ import annotations

from aegis_core.documents.extraction import (
    CONF_LABELLED_BAD_CHECKSUM,
    CONF_LABELLED_CHECKSUM,
    extract_from_text,
)

# Kontrol basamağı geçerli bir vergi numarası (test_identifiers ile aynı kaynaktan).
GECERLI_VKN = "4840847211"
GECERLI_TCKN = "10000000146"

FAALIYET_BELGESI = f"""
T.C.
İSTANBUL TİCARET ODASI
FAALİYET BELGESİ

Ticaret Unvanı      : YILDIZ İNŞAAT SANAYİ VE TİCARET LİMİTED ŞİRKETİ
Ticaret Sicil No    : 123456-5
MERSİS No           : 0123456789012345
Vergi Dairesi       : Beyoğlu
Vergi Kimlik No     : {GECERLI_VKN}
Merkez Adresi       : Cumhuriyet Mah. Halaskargazi Cad. No:15/4 Şişli/İstanbul
Kuruluş Tarihi      : 12.03.2015
Sermaye             : 500000 TL
Telefon             : 02121234567

Yukarıda bilgileri yazılı firmanın Odamız kaydı 08.08.2026 tarihi itibarıyla faaldir.
"""

IMZA_SIRKULERI = f"""
İMZA SİRKÜLERİ

YILDIZ İNŞAAT SANAYİ VE TİCARET LİMİTED ŞİRKETİ

Şirketimizi temsil ve ilzama yetkili kişiler aşağıda gösterilmiştir.

AHMET YILMAZ - T.C. Kimlik No: {GECERLI_TCKN}
Şirketi münferiden temsil ve ilzama yetkilidir.

Ayşe Öztürk
Yönetim Kurulu Üyesi olarak müştereken imza yetkisine sahiptir.

İstanbul 15. Noterliği
Tarih: 20.05.2024
"""


# ── Faaliyet belgesi ─────────────────────────────────────────────────────────


def _attribute(text: str, doc_type: str, name: str) -> str | None:
    result = extract_from_text(text, doc_type)
    for attribute in result.attributes:
        if attribute.name == name:
            return attribute.value
    return None


def test_faaliyet_belgesinden_unvan() -> None:
    value = _attribute(FAALIYET_BELGESI, "faaliyet_belgesi", "name")
    assert value == "YILDIZ İNŞAAT SANAYİ VE TİCARET LİMİTED ŞİRKETİ"


def test_faaliyet_belgesinden_vergi_no_ve_yuksek_guven() -> None:
    result = extract_from_text(FAALIYET_BELGESI, "faaliyet_belgesi")
    tax = next(a for a in result.attributes if a.name == "taxNumber")
    assert tax.value == GECERLI_VKN
    # Etiketli + kontrol basamağı tutuyor → en yüksek güven.
    assert tax.confidence == CONF_LABELLED_CHECKSUM


def test_faaliyet_belgesinden_mersis_sicil_adres_tarih() -> None:
    assert _attribute(FAALIYET_BELGESI, "faaliyet_belgesi", "mersisNumber") == "0123456789012345"
    assert _attribute(FAALIYET_BELGESI, "faaliyet_belgesi", "tradeRegistryNumber") == "123456-5"
    adres = _attribute(FAALIYET_BELGESI, "faaliyet_belgesi", "address")
    assert adres is not None
    assert "Halaskargazi" in adres
    assert _attribute(FAALIYET_BELGESI, "faaliyet_belgesi", "incorporationDate") == "2015-03-12"


def test_sermaye_ve_telefon_vergi_no_sanilmaz() -> None:
    """Kesinlik: belgedeki diğer rakam öbekleri vergi numarası olarak önerilmemeli."""
    result = extract_from_text(FAALIYET_BELGESI, "faaliyet_belgesi")
    tax_values = [a.value for a in result.attributes if a.name == "taxNumber"]
    assert tax_values == [GECERLI_VKN]
    assert "02121234567" not in tax_values
    assert "500000" not in tax_values


def test_kontrol_basamagi_tutmayan_vergi_no_dusuk_guvenle_onerilir() -> None:
    """Öneri atılmaz — kullanıcı belgeden teyit eder; ama güven düşer.

    Not: "1234567890" kontrol basamağını tesadüfen SAĞLIYOR; geçersiz örnek olarak
    "1234567891" kullanılır (bkz. test_identifiers).
    """
    metin = FAALIYET_BELGESI.replace(GECERLI_VKN, "1234567891")
    result = extract_from_text(metin, "faaliyet_belgesi")
    tax = next(a for a in result.attributes if a.name == "taxNumber")
    assert tax.value == "1234567891"
    assert tax.confidence == CONF_LABELLED_BAD_CHECKSUM


def test_faaliyet_belgesinde_serbest_ad_taramasi_yapilmaz() -> None:
    """Bu belgede kişi ancak yetki ifadesiyle birlikte önerilir (gürültü kontrolü)."""
    result = extract_from_text(FAALIYET_BELGESI, "faaliyet_belgesi")
    assert result.persons == []


# ── İmza sirküleri ───────────────────────────────────────────────────────────


def test_imza_sirkulerinden_yetkililer() -> None:
    result = extract_from_text(IMZA_SIRKULERI, "imza_sirkuleri")
    adlar = {person.name for person in result.persons}
    assert "AHMET YILMAZ" in adlar
    assert "Ayşe Öztürk" in adlar


def test_yetkiliye_tckn_baglanir() -> None:
    result = extract_from_text(IMZA_SIRKULERI, "imza_sirkuleri")
    ahmet = next(p for p in result.persons if p.name == "AHMET YILMAZ")
    assert ahmet.national_id == GECERLI_TCKN
    assert ahmet.role_title is not None
    assert ahmet.confidence >= 0.9


def test_yetki_ifadesi_rol_olarak_kaydedilir() -> None:
    result = extract_from_text(IMZA_SIRKULERI, "imza_sirkuleri")
    ayse = next(p for p in result.persons if p.name == "Ayşe Öztürk")
    assert ayse.role_title is not None
    assert "müştereken" in ayse.role_title.lower() or "yönetim" in ayse.role_title.lower()


def test_kurumsal_ifadeler_kisi_adi_sanilmaz() -> None:
    """Kesinlik: "Yönetim Kurulu", "İmza Sirküleri", "Ticaret Odası" kişi değildir."""
    result = extract_from_text(IMZA_SIRKULERI, "imza_sirkuleri")
    adlar = {person.name for person in result.persons}
    yasakli = {"Yönetim Kurulu", "İmza Sirküleri", "Ticaret Odası", "Kimlik No"}
    assert not (adlar & yasakli)


def test_imza_sirkulerinden_sirket_unvani_da_cikar() -> None:
    value = _attribute(IMZA_SIRKULERI, "imza_sirkuleri", "name")
    assert value is not None
    assert "YILDIZ" in value


def test_tckn_kanit_metninde_ve_unvanda_maskelenir() -> None:
    """KVKK: öneri satırı şifresiz saklanır → kanıt/unvan metninde düz TCKN olamaz.

    Vergi numarası maskelenmez: tüzel kişinin kamuya açık tanımlayıcısıdır ve kanıtın
    okunabilirliği için gerekir.
    """
    result = extract_from_text(IMZA_SIRKULERI, "imza_sirkuleri")
    ahmet = next(p for p in result.persons if p.name == "AHMET YILMAZ")
    assert GECERLI_TCKN not in ahmet.evidence
    assert "*******0146" in ahmet.evidence
    assert ahmet.role_title is not None
    assert GECERLI_TCKN not in ahmet.role_title
    # Numaranın kendisi ayrı alanda taşınır (kabul edilince şifreli kolona yazılır).
    assert ahmet.national_id == GECERLI_TCKN


def test_vergi_numarasi_kanitta_maskelenmez() -> None:
    """Tüzel kişinin kamuya açık tanımlayıcısı okunabilir kalmalı (kanıt değerini korur)."""
    result = extract_from_text(FAALIYET_BELGESI, "faaliyet_belgesi")
    vergi = next(a for a in result.attributes if a.name == "taxNumber")
    assert GECERLI_VKN in vergi.evidence


def test_yetki_unvani_yalniz_ilgili_satiri_alir() -> None:
    """Unvan, kişinin adını ve kimlik satırını içermemeli."""
    result = extract_from_text(IMZA_SIRKULERI, "imza_sirkuleri")
    ahmet = next(p for p in result.persons if p.name == "AHMET YILMAZ")
    assert ahmet.role_title is not None
    assert "AHMET YILMAZ" not in ahmet.role_title
    assert "münferiden" in ahmet.role_title.lower()


def test_gecersiz_tckn_kisiye_baglanmaz() -> None:
    metin = IMZA_SIRKULERI.replace(GECERLI_TCKN, "12345678901")
    result = extract_from_text(metin, "imza_sirkuleri")
    ahmet = next(p for p in result.persons if p.name == "AHMET YILMAZ")
    assert ahmet.national_id is None


# ── Kenar durumlar ───────────────────────────────────────────────────────────


def test_bos_metin_uyari_uretir() -> None:
    result = extract_from_text("", "faaliyet_belgesi")
    assert result.is_empty
    assert result.warnings


def test_taninmayan_belge_uyari_uretir() -> None:
    result = extract_from_text("Bu bir alışveriş fişidir. Toplam 45 TL.", "other")
    assert result.is_empty
    assert result.warnings


def test_ayni_kisi_iki_kez_onerilmez() -> None:
    metin = IMZA_SIRKULERI + "\n\nAHMET YILMAZ tekrar geçiyor.\n"
    result = extract_from_text(metin, "imza_sirkuleri")
    adlar = [person.name for person in result.persons]
    assert adlar.count("AHMET YILMAZ") == 1
