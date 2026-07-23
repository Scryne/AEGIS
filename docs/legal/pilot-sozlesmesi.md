# Pilot Katılım Sözleşmesi — Şablon (v1)

> ⚠️ **v1 TASLAK — hukuki inceleme gerekir.** İmzadan önce avukat onayı alınmalı,
> `{{...}}` doldurulmalıdır. Bu metin hukuki tavsiye değildir.

**Taraflar**
- **Sağlayıcı ("AEGIS"):** {{ŞİRKET_UNVANI}}, {{ADRES}}
- **Pilot Katılımcı ("Ofis"):** {{OFIS_UNVANI}}, {{OFIS_ADRES}}

**Amaç:** Ofis'in, AEGIS KYB/tarama platformunu **ücretsiz pilot** olarak, gerçek
dosyalar üzerinde kullanması; karşılığında geri bildirim ve (anonimleştirilmiş) vaka
çalışması hakkı sağlaması.

## 1. Pilot Kapsamı ve Süre
- **Kapsam:** Şirket profili oluşturma, yaptırım/PEP/watchlist tarama, denetim-kanıtlı
  rapor dışa aktarma (Faz 1 özellikleri).
- **Süre:** {{PILOT_SURESI}} (ör. 8–12 hafta); Taraflar {{BILDIRIM_SURESI}} önceden
  yazılı bildirimle sonlandırabilir.
- **Ücret:** Pilot dönemi **ücretsizdir**. Ücretli aboneliğe geçiş ayrı sözleşmeyle olur.

## 2. Karar-Destek ve Sorumluluğun Sınırı (ESAS MADDE)
1. **AEGIS bir karar-destek aracıdır.** Uyum, risk ve MASAK bildirim kararlarını **Ofis
   verir**; AEGIS bu kararları **vermez**, yalnızca verileri toplar, tarar, belgeler ve
   kaynak-bağlantılı biçimde sunar.
2. **Nihai sorumluluk Ofis'tedir.** 5549 sayılı Kanun ve ikincil mevzuat kapsamındaki
   yükümlülükler (müşterini tanı, şüpheli işlem bildirimi/ŞİB, kayıt saklama vb.) ve bu
   yükümlülüklerin yerine getirilmesine ilişkin **hukuki sorumluluk münhasıran Ofis'e
   aittir.**
3. **Doğruluk taahhüdü yoktur (pilot).** Tarama sonuçları ve eşleştirmeler olasılıksaldır;
   yanlış pozitif/negatif içerebilir. Ofis, sonuçları **kendi mesleki değerlendirmesiyle**
   teyit eder. AEGIS, sonuçların eksiksizliği/hatasızlığı konusunda garanti vermez.
4. **ŞİB sorumluluğu:** Platformun ürettiği taslaklar (Faz 2 ŞİB dahil) yalnızca
   hazırlığı kolaylaştırır; MASAK'a resmi bildirim ve içeriğin doğruluğu **Ofis'in**
   yükümlülüğündedir.
5. AEGIS'in bu pilot kapsamındaki toplam sorumluluğu, ücretsiz nitelik gözetilerek
   {{SORUMLULUK_SINIRI}} ile sınırlıdır; dolaylı/sonuçsal zararlardan sorumlu değildir
   (amir hükümler saklıdır).

## 3. KVKK / Veri Koruma
- Taranan üçüncü kişilere ait verilerde **Ofis veri sorumlusu**, AEGIS **veri işleyendir**;
  işleme, imzalanan [DPA](dpa-sablonu.md) hükümlerine tabidir (bu sözleşmenin ekidir).
- **Veri yerelliği:** Veri Türkiye'de işlenir; yurt dışına aktarılmaz. Tarama self-host
  yente ile yapılır (PII dışa çıkmaz). Faz 1'de LLM/dış AI çağrısı yoktur.
- **Saklama:** Bel­ge ve dosyalar en az {{SAKLAMA_YILI}} yıl saklanır; süre sonunda imha
  edilir. Denetim izi append-only ve tamper-evident tutulur.

## 4. Geri Bildirim ve Vaka Çalışması
- Ofis, düzenli geri bildirim (haftalık check-in + uygulama-içi geri bildirim) sağlar.
- AEGIS, Ofis'in kimliğini ifşa etmeden ve gizli veriyi paylaşmadan, **anonimleştirilmiş**
  metrikleri (ör. dosya başına kazanılan süre) vaka çalışmasında kullanabilir; **Ofis
  adının/logosunun** kullanımı ayrı yazılı onaya tabidir.

## 5. Gizlilik
Taraflar, pilot kapsamında eriştikleri gizli bilgiyi korur ve yalnızca pilot amacıyla
kullanır. Yükümlülük, pilot bitiminden sonra {{GIZLILIK_SURESI}} sürer.

## 6. Fikri Mülkiyet
Platform ve tüm bileşenleri AEGIS'e aittir. Ofis'in yüklediği veriler ve ürettiği dosyalar
Ofis'e aittir; AEGIS bunları yalnızca hizmeti sunmak için (işleyen sıfatıyla) işler.

## 7. Muhtelif
- **Uygulanacak hukuk / yetki:** Türkiye Cumhuriyeti hukuku; {{YETKILI_MAHKEME}}.
- **Bütünlük:** DPA ve varsa ekler bu sözleşmenin ayrılmaz parçasıdır.

**İmza — Ofis:** {{IMZA}} · **İmza — AEGIS:** {{IMZA}} · **Tarih:** {{TARIH}} · **Sürüm:** v1 (taslak)
