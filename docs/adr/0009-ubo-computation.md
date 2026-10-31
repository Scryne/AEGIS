# ADR-0009: Gerçek faydalanıcı hesabı — saf çekirdek, CTE, anlık görüntü, açık belirsizlik

- **Durum:** Kabul edildi
- **Tarih:** 2026-10-31
- **Karar veren:** Scryne (geliştirme devri, "tüm projelerimi bitir")
- **İlgili:** ROADMAP §8 E2.1; CLAUDE.md Invariant 1 (RLS), 2 (denetim olayı), 4 (provenans +
  saklama); ADR-0006 (anlık görüntü duruşu), ADR-0007 (kütük: ilişki = gözlem)

## Bağlam

E2.1, ortaklık zincirinden gerçek faydalanıcıyı (UBO) hesaplamayı ister: katmanlar arası pay
çarpımı, eşik, döngü tespiti, çözülemeyen zincirin açıkça raporlanması ve "o gün ne
biliyorduk" sorusuna cevap veren anlık görüntüler. Ölçüt yine savunulabilirliktir: denetçi
"Ali neden UBO, Mehmet neden değil" diye sorduğunda cevap kayıtta durmalıdır.

## Kararlar

### 1. Hesap saf bir çekirdektir; veritabanı yalnız zinciri toplar

`aegis_core.ubo.compute.compute_ubo` veritabanı, saat ve ağ bilmez: düğüm ve kenar listesi
alır, deterministik sonuç verir. Kenar durumları (katman, çapraz pay, döngü, tam %25,
yabancı ana şirket, eksik pay, payların %100'e ulaşmaması, kontrol ve yönetici dayanakları)
Docker gerektirmeyen birim testlerinde sınanır. `ubo.service` hedeften yukarı doğru
özyinelemeli bir CTE ile zinciri toplar (CTE yol dizisi taşır, aynı düğüme ikinci kez
girmez) ve sonra çekirdeğe verir.

### 2. Eşik "%25'ten fazla"dır; yorum her sonuçla saklanır

Yol haritası "≥25%" yazıyordu; MASAK düzenlemesinin ifadesi "yüzde yirmi beşinden fazla"dır.
Varsayılan **kesin** yorumdur (`inclusive=False`); istek gövdesi kapsayıcı yorumu
(`inclusive=True`) seçebilir. Eşik ve yorum anlık görüntüde ve denetim olayında saklanır, arayüz
hangi kuralla hesaplandığını yazar. Bu bir hukuk yorumu değil, motorun ayarıdır; kurum kendi
uyum politikasına göre seçer.

### 3. Belirsizlik bir sonuçtur, boşluk değildir

Çözülemeyen pay (ortakları kayıtlı olmayan tüzel kişi, payı girilmemiş bağ, %100'e ulaşmayan
toplam, döngüde kalan pay) **kimseye bağlanmadan** toplanır. Bu pay eşiği aşabiliyorsa ya da
bir payın büyüklüğü hiç bilinmiyorsa sonuç `not_determinable`'dır: bulunan UBO'lar yine
listelenir, ama "tam liste" iddiası yapılmaz. Döngüdeki pay kişilere sonsuz seri olarak
dağıtılmaz; döngü kesilir ve açıkça raporlanır. Bu muhafazakâr bir seçimdir: döngülü yapı
kendi başına bir uyum sinyalidir ve analistin önüne konmalıdır.

### 4. Pay yoksa sırayla kontrol, sonra üst düzey yönetici

Zincir tamamen çözülmüş ve kimse eşiği aşmıyorsa: hedefe ya da zincirdeki bir şirkete
`control` bağı olan kişiler, onlar da yoksa hedefin `officer` bağlı kişileri gösterilir.
Hangi dayanağın kullanıldığı `basis` alanında yazar; arayüz bunu "Kontrol" / "Üst düzey
yönetici" olarak etiketler.

### 5. Her hesap yeni bir anlık görüntüdür

`ubo_computation` (RLS + `retention_until`) sonucu, hesabın gördüğü düğüm ve kenarların
kanonik kopyasını ve onun SHA-256 özetini saklar. Kütük sonradan değişse de eski karar yeniden
yorumlanmaz (ADR-0006'nın duruşu). Aynı girdi aynı özeti verir; "bir şey değişti mi" sorusu
özet karşılaştırmasıyla cevaplanır. Her hesap tek bir `ubo.compute` denetim olayı üretir.

### 6. Beyan edilmiş UBO bağı hesabın girdisi değildir

`rel_type = ubo` beyanı hesaplamaya girmez; hesap sahiplik zincirini çözer. Beyan ile hesap
farklıysa ikisi yan yana görünür; aradaki fark analistin işidir.

## Sonuçlar

- Bitmiş bağlar (`end_date` geçmişte) ve birleştirilmiş kayıtlar hesaba girmez.
- Taranmamış UBO'lar yanıtta `unscreened_ubo_ids` ile döner; arayüz tek tıkla tarar. Otomatik
  tarama tetiği (kuyruğa atma) bilinçli olarak yok: yente çağrısı ağırdır ve tarama bir
  denetim eylemidir; kimin başlattığı izde görünmelidir.
- Ortaklık tablosunun belgeden çıkarımı (Docling uzantısı) ve pilot dosyalarda doğrulama
  ayrı işlerdir (ROADMAP E2.1'in açık kalemleri).
