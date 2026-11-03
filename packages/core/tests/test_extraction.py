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


# ── Docling paragraf birleştirmesi (2026-09-26) ──────────────────────────────

# Docling'in üretilmiş bir imza sirküleri PDF'inden verdiği gerçek çıktı biçimi: iki
# yetkilinin satırları tek paragrafta.
DOCLING_BIRLESIK = """## İMZA SİRKÜLERİ

KUZEY AMBALAJ SANAYİ VE TİCARET ANONİM ŞİRKETİ

Şirketimizi temsil ve ilzama yetkili kişiler aşağıda gösterilmiştir.

DENİZ KARACA - T.C. Kimlik No: 10000000214 Şirketi münferiden temsil ve ilzama yetkilidir. \
ELİF YURTSEVER - T.C. Kimlik No: 10000000382 Yönetim Kurulu Üyesi olarak müştereken imza \
yetkisine sahiptir.

Ankara 12. Noterliği Tarih: 14.03.2026"""


def test_birlesik_paragrafta_her_yetkili_kendi_tckn_sine_baglanir() -> None:
    kisiler = {p.name: p for p in extract_from_text(DOCLING_BIRLESIK, "imza_sirkuleri").persons}
    assert kisiler["DENİZ KARACA"].national_id == "10000000214"
    assert kisiler["ELİF YURTSEVER"].national_id == "10000000382"


def test_birlesik_paragrafta_yetki_ifadesi_dogru_kisiye_gider() -> None:
    kisiler = {p.name: p for p in extract_from_text(DOCLING_BIRLESIK, "imza_sirkuleri").persons}
    deniz = kisiler["DENİZ KARACA"].role_title or ""
    elif_ = kisiler["ELİF YURTSEVER"].role_title or ""
    assert "münferiden" in deniz
    assert "müştereken" not in deniz
    assert "müştereken" in elif_
    assert "münferiden" not in elif_
    # Yetki metni kişinin adını/kimlik numarasını taşımaz.
    assert "DENİZ" not in elif_
    assert "Kimlik" not in deniz


def test_unvan_satirindan_kisi_onerilmez() -> None:
    for metin in (IMZA_SIRKULERI, DOCLING_BIRLESIK):
        adlar = {p.name for p in extract_from_text(metin, "imza_sirkuleri").persons}
        assert not any("SANAYİ" in ad or "İNŞAAT" in ad or "AMBALAJ" in ad for ad in adlar), adlar


def test_satir_yapisi_zaten_duzgunse_degismez() -> None:
    from aegis_core.documents.extraction import restore_line_structure

    assert restore_line_structure(IMZA_SIRKULERI) == IMZA_SIRKULERI


ORTAKLIK_TABLOSU = """
DENİZ TİCARET ANONİM ŞİRKETİ PAY DEFTERİ DÖKÜMÜ
| Ortak | Kimlik | Pay adedi | Oran |
| --- | --- | --- | --- |
| Ahmet Yılmaz | 10000000146 | 40.000 | %40 |
| Ayşe Demir | - | 35.000 | 35,5% |
| Liman Holding A.Ş. | 4840847211 | 24.500 | %24,5 |
| Toplam |  | 100.000 | %100 |
"""


def test_ortaklik_tablosundan_pay_orani_okunur() -> None:
    sonuc = extract_from_text(ORTAKLIK_TABLOSU, "ortaklik_yapisi")
    ortaklar = {p.name: p for p in sonuc.persons if p.rel_type == "shareholder"}
    assert set(ortaklar) == {"Ahmet Yılmaz", "Ayşe Demir", "Liman Holding A.Ş."}
    assert ortaklar["Ahmet Yılmaz"].ownership_percent == 40
    assert ortaklar["Ahmet Yılmaz"].national_id == "10000000146"
    assert "10000000146" not in ortaklar["Ahmet Yılmaz"].evidence  # kanıt metni maskeli
    assert ortaklar["Ayşe Demir"].ownership_percent == 35.5
    assert ortaklar["Liman Holding A.Ş."].is_company is True
    assert ortaklar["Liman Holding A.Ş."].national_id is None
    assert all(p.confidence == 0.85 for p in ortaklar.values())
    assert sonuc.warnings == []


def test_duz_metin_satirlari_da_okunur() -> None:
    metin = "1. Mehmet Kaya 10000000078 %60\n2) Zeynep Aydın %40\nGenel Toplam %100"
    ortaklar = extract_from_text(metin, "ortaklik_yapisi").persons
    assert {(p.name, p.ownership_percent) for p in ortaklar} == {
        ("Mehmet Kaya", 60),
        ("Zeynep Aydın", 40),
    }


def test_pay_toplami_tutmazsa_guven_duser_ve_uyarir_oran_degismez() -> None:
    sonuc = extract_from_text("Ahmet Yılmaz %40\nAyşe Demir %35", "ortaklik_yapisi")
    assert [p.ownership_percent for p in sonuc.persons] == [40, 35]
    assert all(p.confidence == 0.6 for p in sonuc.persons)
    assert any("%75.00" in w for w in sonuc.warnings)


def test_pay_satiri_olmayan_metinden_ortak_uydurulmaz() -> None:
    metin = "Şirketin KDV oranı %20 olarak uygulanır.\nSermaye artışı %150 oranında yapıldı."
    sonuc = extract_from_text(metin, "ortaklik_yapisi")
    assert [p for p in sonuc.persons if p.rel_type == "shareholder"] == []
    assert any("ortak satırı bulunamadı" in w for w in sonuc.warnings)


def test_baska_belge_turunde_pay_taramasi_yapilmaz() -> None:
    sonuc = extract_from_text("Ahmet Yılmaz %40\nAyşe Demir %60", "faaliyet_belgesi")
    assert all(p.rel_type != "shareholder" for p in sonuc.persons)


def test_kimlik_ve_adet_sutunu_oran_sanilmaz() -> None:
    """Regresyon: kimliğin son haneleri ile yüzdenin arasındaki boşluk oranı %78 okutuyordu."""
    metin = "Mehmet Kaya 10000000078 %60\nZeynep Aydın 400 %25\nCan Tok 40.000 15 %"
    oranlar = {
        p.name: p.ownership_percent for p in extract_from_text(metin, "ortaklik_yapisi").persons
    }
    assert oranlar == {"Mehmet Kaya": 60, "Zeynep Aydın": 25, "Can Tok": 15}
