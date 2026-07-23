# VERBİS Kayıt Yükümlülüğü Değerlendirmesi ve Hazırlık (v1)

> ⚠️ **v1 TASLAK — hukuki inceleme gerekir.** VERBİS (Veri Sorumluları Sicil Bilgi
> Sistemi) kayıt yükümlülüğünün olup olmadığı ve kapsamı, KVKK Kurulu kararları ve güncel
> istisna kriterlerine göre bir **KVKK uzmanı** tarafından teyit edilmelidir. Aşağısı
> hazırlık amaçlıdır, bağlayıcı değildir.

## 1. Yükümlülük var mı? (değerlendirme soruları)
Kurul, bazı veri sorumlularını yıllık çalışan sayısı ve mali bilanço eşiklerine göre
VERBİS kaydından **istisna** tutmuştur; ancak **ana faaliyeti özel nitelikli kişisel veri
işleme** olanlar bu istisnadan yararlanamayabilir. Karar için netleştirilecekler:

- [ ] AEGIS'i işleten tüzel kişinin **yıllık çalışan sayısı** ({{CALISAN_SAYISI}}) ve
      **yıllık mali bilanço toplamı** ({{BILANCO}}) güncel istisna eşiklerinin altında mı?
- [ ] AEGIS'in **ana faaliyeti** kişisel veri işleme sayılır mı? (SaaS olarak
      işletiliyor; müşteri adına veri işleme *işleyen* sıfatıyla — bu ayrım kayıt
      kapsamını etkiler.)
- [ ] İşlenen veriler arasında **özel nitelikli** veri var mı? (Faz 1 platform-kullanıcı
      verisinde yok; müşteri-verisinde tarama sonuçları hassas olabilir — *işleyen*
      rolünde değerlendirilir.)
- [ ] **Sonuç/karar:** {{KAYIT_GEREKLI_Mi: evet/hayır}} — gerekçe: {{GEREKCE}} ·
      teyit eden: {{KVKK_UZMANI}} · tarih: {{TARIH}}

> Not: Yukarıdaki eşikler ve istisnalar zaman içinde Kurul kararlarıyla değişebilir;
> kayıt kararı **güncel** kriterlere göre verilmelidir.

## 2. Kayıt gerekiyorsa hazırlanacak bilgiler
- **Veri Sorumlusu kimliği:** unvan, MERSIS/vergi no, adres, KEP.
- **İrtibat Kişisi:** {{IRTIBAT_KISISI}} (varsa Veri Sorumlusu Temsilcisi).
- **İşleme amaçları:** bkz. [aydınlatma-metni.md](aydinlatma-metni.md) §3.
- **Veri kategorileri:** kimlik, iletişim, işlem güvenliği, denetim/log
  (bkz. [envanter](veri-isleme-envanteri.md) tablo A).
- **İlgili kişi grupları:** platform kullanıcıları (ofis çalışanları).
- **Alıcı/alıcı grupları:** dahili; barındırma/altyapı sağlayıcıları (işleyen sıfatıyla).
- **Yurt dışına aktarım:** **yok** (veri yerelliği — self-host, Türkiye DC seçenekli).
- **Saklama süreleri:** kategori bazında (bkz. envanter).
- **Teknik/idari tedbirler:** bkz. envanter §C (RLS, denetim izi, şifreleme, saklama/imha).

## 3. Ana faaliyet ("işleyen") notu
AEGIS, müşterinin taradığı üçüncü-kişi verisinde **veri işleyendir**; bu ilişki
[DPA](../legal/dpa-sablonu.md) ile kurulur. İşleyen faaliyeti, müşterinin (veri
sorumlusunun) VERBİS/aydınlatma yükümlülüklerini AEGIS'e devretmez; AEGIS yalnız
teknik/organizasyonel tedbir ve talimatla-işleme taahhüdü verir.

## 4. Yapılacaklar (checklist)
- [ ] Yükümlülük kararını KVKK uzmanıyla teyit et ve §1'e işle.
- [ ] Gerekliyse İrtibat Kişisi ata ve VERBİS başvurusunu yap.
- [ ] Aydınlatma metnini ve envanteri güncel tut (değişiklikte revize).
- [ ] Saklama & imha politikasını yaz (retention job dry-run raporuyla; E3.7).
- [ ] İhlal bildirim prosedürünü tanımla (Kurul'a ve ilgili kişiye bildirim süreleri).

**Sürüm:** v1 (taslak) · **Güncelleme:** {{TARIH}}
