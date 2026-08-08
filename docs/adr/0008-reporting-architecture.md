# ADR-0008: Raporlama — kural tabanlı risk özeti, dosya dışa aktarma, denetim görüntüleyici

- **Durum:** Kabul edildi
- **Tarih:** 2026-08-08
- **Karar veren:** Scryne
- **İlgili:** CLAUDE.md Invariant 2 (append-only iz) ve 4 (provenans + saklama);
  ROADMAP §7 E1.5, Revizyon R7 (marka sabitlenmez); ADR-0004 (denetim izi),
  ADR-0006 (tarama: otomatik onay yok, aday silinmez), ADR-0007 (kütük)

## Bağlam

E1.5 ürünün *çıktısını* üretir: risk özeti, durum tespiti dosyası (PDF + Word) ve denetim
izi görüntüleyicisi. Bu, MASAK denetiminde masaya konan şeydir; dolayısıyla tasarımın
ölçütü "güzel rapor" değil, **savunulabilir rapor**tur: her cümlenin arkasında
gösterilebilir bir kayıt olmalıdır.

## Kararlar

### 1. Risk seviyesi kuraldır, puan değildir

`reports/risk.py` şeffaf kurallar koşar: onaylanmış yaptırım eşleşmesi → **Yüksek**,
onaylanmış PEP → **Artırılmış**, açık kritik tutarsızlık → **Artırılmış**. Seviye,
bulguların **en yükseğidir**; gizli bir toplama ya da ağırlıklandırma yoktur.

0–100 arası bir puan üretmek daha "ürün gibi" görünürdü ama "bu dosyaya neden 72 dediniz"
sorusunu cevaplayamazdı. Kural cevaplayabilir: her `RiskFinding` düz Türkçe bir
`rationale` taşır ve rapora madde madde basılır. Ağırlıklı/öğrenilmiş skor **Phase 2**'nin
işidir (Ürün Planı) ve bu fazda bilinçli olarak yoktur.

Modül **veritabanı bilmez**: girdileri küçük görünüm dataclass'larıdır. Kuralların
doğruluğu, Docker ve fixture gerektirmeden birim testlerinde sınanır.

### 2. Karara bağlanmamış eşleşme seviyeyi yükseltmez

Yüksek skorlu ama henüz onaylanmamış bir eşleşme dosyayı Yüksek **yapmaz**. Aksi,
ADR-0006'nın "otomatik onay yok" değişmezini arka kapıdan delerdi: motor skorlar, insan
karar verir. Böyle bulgular `level=None` taşır — seviyeye dokunmaz, ama `complete=False`
yaparak **dosyanın tamamlanmadığını** bildirir. Aynı şey açık uyarı tutarsızlıkları ve
başarısız koşular için de geçerlidir.

### 3. "Sonuç yok" ile "temiz" ayrı seviyelerdir

Hiç tarama yoksa ya da koşu `failed` ise seviye **Belirsiz**tir, asla Standart değil.
Sıralamada `Belirsiz` > `Standart`tır: bilgisizlik, temizlikten daha yüksek bir uyarıdır.
Gerçek bir bulgu (ör. kimlik tutarsızlığı) varsa o bastırır — bilinen kötü, bilinmezden
ağırdır. Bu ayrımı silmek, bu üründeki en tehlikeli hata olurdu.

Aynı gerekçeyle "yaptırım eşleşmesi nedir" yüklemi tek modüldedir
(`screening/topics.py`): ekrandaki sayaç ile rapordaki kural aynı tanımı kullanmak
zorundadır, yoksa ekran "1 yaptırım eşleşmesi" derken rapor "Standart risk" diyebilirdi.

### 4. Elenen eşleşmeler rapordan çıkarılmaz

ADR-0006 hiçbir adayın silinmemesini şart koşmuştu; rapor bunun karşılığıdır. Otomatik
elenen adaylar da, bandı ve gerekçesiyle birlikte basılır. MASAK denetiminde savunma
"neye bakıldı ve neden elendi"dir; yalnız onaylananları basan bir rapor bu soruyu
cevaplayamaz.

Aynı şekilde raporda **koşu anındaki eşikler ve veri kümesi sürümleri** basılır: rapor,
"hangi listeye göre, hangi eşikle" sorusunu kendi başına cevaplayabilmelidir.

### 5. PDF motoru: Jinja2 + xhtml2pdf/reportlab (WeasyPrint değil)

ROADMAP "PDF via HTML template" der. İki gerçek aday vardı:

| | WeasyPrint | xhtml2pdf + reportlab |
|---|---|---|
| CSS desteği | çok iyi (flexbox/grid) | alt küme (tablo düzeni) |
| Yerel bağımlılık | **Pango/GDK gerekir** | yok, saf Python |
| Windows geliştirme | GTK runtime kurulumu | çalışır |
| CI | ek sistem paketi | ek adım yok |

Seçim **xhtml2pdf**tir. Gerekçe tek-host ve tek-geliştirici duruşudur (R6): dosya raporu
bir *belgedir* — başlık, paragraf, tablo. Flexbox'a ihtiyaç duymayan bir çıktı için
geliştirme ortamını ve CI'ı yerel kütüphanelere bağlamak, ödenmeye değmeyen bir
maliyettir. Motor değişirse yalnız `reports/render.py` değişir: şablon ve `DossierData`
motordan bağımsızdır.

**Türkçe font.** reportlab'ın gömülü Type1 yüzleri (Helvetica …) WinAnsi kodlamasıdır ve
`ş ğ ı İ` harflerini **taşımaz** — rapor sessizce kutucuklarla dolardı. Çözüm,
reportlab'ın kendi dağıtımıyla gelen **Bitstream Vera** TTF yüzleridir: Türkçe alfabenin
tamamını kapsar ve depoya font dosyası eklemeyi gerektirmez. (Vera, 2012'de Unicode'a
giren ₺ işaretini taşımaz; Faz 1 raporunda parasal tutar basılmadığı için bu bir kısıt
değildir.)

Kayıt, xhtml2pdf'in `@font-face` yolundan **geçmez**: o yol fontu geçici bir dosyaya
kopyalayıp adıyla yeniden açar ve Windows'ta `PermissionError` verir. Yüzler doğrudan
reportlab'a kaydedilip xhtml2pdf'in font sözlüğüne eklenir. Testler, üretilen PDF'ten
metni **geri okuyup** harflerin yerinde olduğunu doğrular — bu tür bir bozulma göze
bakmadan fark edilmez.

### 6. PDF ve Word tek bir `DossierData`dan üretilir

Toplama (`reports/dossier.py`) oluşturuculardan ayrıdır. İki biçim aynı nesneden
beslendiği için "PDF'te olan bir bulgunun Word'de olmaması" yapısal olarak imkânsızdır.
Word (`python-docx`) çıktısı, kurumun raporu kendi antetli şablonuna taşıyabilmesi
içindir.

Raporda **TCKN maskelidir** (son dört hane): dosya kurumdan dışarı çıkan bir belgedir.
Vergi/MERSİS/LEI kamuya açık kütük numaralarıdır ve tam basılır (ADR-0005'in duruşu).

### 7. Üretilen dosya donar ve özetiyle saklanır

Rapor her istendiğinde yeniden üretilseydi "denetime sunduğum belge buydu" iddiası
kanıtlanamazdı: aradan geçen sürede kütük değişir, eşik değişir, veri kümesi güncellenir.
Bu yüzden dosya nesne deposuna yazılır, `report` satırı `sha256` bütünlük kanıtını ve
donmuş risk özetini taşır, `retention_until` doğuştan işletilir (Invariant 4).

Sıra bilinçlidir: **önce depo, sonra veritabanı**. Depo yazımı başarısızsa hiçbir satır
yazılmaz — kaydı olup dosyası olmayan rapor üretilmez. Tersi (depoda öksüz nesne) kabul
edilebilir ve E3.7'nin imha job'ında temizlenir.

Dışa aktarma tam olarak **bir** `report.export` olayı yazar ve olayın `source_ref`'i
dosyanın özetidir. **Canlı risk özeti** (`GET /reports/risk/{id}`) ise olay yazmaz: bir
okuma işlemi denetim izini gürültüyle doldurmamalıdır.

### 8. Denetim görüntüleyici salt-okunurdur ve aktör adını izde tutmaz

`GET /audit/events` zincir sırasına (`seq`) göre listeler — `occurred_at`'a göre değil:
`seq` zincirin gerçek sırasıdır ve aynı saniyeye düşen iki olayı da kesin sıralar.
Erişim `owner`/`compliance_officer`/`auditor` ile sınırlıdır; analist göremez.

Denetim izi yalnız `actor_user_id` tutar (ADR-0004: kullanıcı silinse de olay durur). Ad,
görüntüleme anında kimlik düzleminden tek sorguyla çözülür; çözülemezse kimliğin kendisi
gösterilir — olay hiçbir koşulda gizlenmez.

## Sonuçlar

**Olumlu.** Risk özeti savunulabilir ve test edilebilir; rapor motoru yerel bağımlılık
istemez ve her platformda aynı çalışır; üretilen dosya kanıt niteliğindedir; PDF/Word
içerik olarak ayrışamaz.

**Bedeli.** xhtml2pdf'in CSS alt kümesi mizanpajı tablolarla kurmayı gerektirir; karmaşık
bir görsel tasarım istenirse motor değişimi gündeme gelir (etkisi `render.py` ile
sınırlıdır). Etiket sözlüğü hem TypeScript hem Python tarafında durur ve birlikte
güncellenmelidir.

**Ertelenen.** Ağırlıklı/öğrenilmiş risk skoru, ŞİB (şüpheli işlem bildirimi) taslağı ve
raporun kurum logosuyla markalanması Phase 2+'dır (R7: bu fazda beyaz etiket yok).
