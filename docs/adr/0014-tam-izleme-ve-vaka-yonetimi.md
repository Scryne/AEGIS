# ADR-0014: Tam izleme çekirdeği ve vaka yönetimi

- **Durum:** Kabul edildi
- **Tarih:** 2026-11-01
- **İlgili:** ROADMAP E3.1, E3.2, Phase 3 çıkış ölçütü 1; ADR-0010 (risk puanı); CLAUDE.md
  Invariant 1 (RLS), 2 (denetim izi)

## Bağlam

E2.4 izleme-lite alarmı yazıyor ve "görüldü" yapılıyordu; alarmın derecesi, alarmdan sonra ne
olacağı ve kimin karar vereceği yoktu. Phase 3'ün ilk çıkış ölçütü: *izlenen bir varlıkta veri
değişikliği gözetimsiz akar: fark → alarm → vaka → yeniden puanlanmış dosya.*

## Kararlar

### 1. Alarm derecesi farkın kendisinden çıkar (`monitoring/severity.py`)
`critical` = bir kayda yaptırım etiketi geldi (yeni aday ya da eklenen `sanction*`). `high` = PEP
etiketi geldi ya da onaylı eşleşme listeden çıktı. `info` = geri kalan önemli farklar. Alarmın
derecesi kalemlerinin en yükseği. "Yaptırım/PEP" tanımı `screening/topics.py`'den gelir. Yol
haritasındaki "high: ownership change" sicil/gazete farkı gelince eklenir; bugün o kaynak yok.

### 2. Alarm anında puan kayda geçer, alarm önce/sonrayı taşır
`score_service.snapshot(reason="monitoring_alert")`; alarm satırına `reassessment` (önceki/sonraki
puan ve bant). Onaylanmamış aday puanı değiştirmez (ADR-0008/0010 kuralı), bu yüzden çoğu yeni
eşleşmede puan aynı kalır ve ekran bunu söyler. Asıl yeniden puanlama vakada karar verilince olur
(madde 4).

### 3. `critical` ve `high` alarm vaka açar; `critical` EDD işaretli
Vaka `compliance_case` tablosunda (`case` SQL'de ayrılmış sözcük). Bir alarm en çok bir vaka açar:
`source_alert_id` üzerinde tekillik kısıtı (asıl garanti) + servis önce mevcut vakayı arar. Alarm,
puan ve vaka aynı alt işlemdedir; biri düşerse hiçbiri yazılmaz ve ertesi koşu aynı farkı yeniden
bulur. `info` alarm yalnız listede kalır (alarm yorgunluğu, yol haritası riski).

### 4. Yaşam döngüsü saf bir durum makinesi (`cases/lifecycle.py`)
`new → in_review → approved / escalated (EDD) → closed`, artı `reopen`. Analist inceler ve
**yükseltebilir** ama karar veremez; onay, kapanış, yeniden açma ve son tarih uyum uzmanı ile
sahibin. Denetçi hiçbir geçiş yapamaz, her şeyi görür. Karar gerektiren geçişler en az 10
karakterlik gerekçe ister. EDD açık bir vaka liste tamamlanmadan onaylanamaz ve kapatılamaz.
Onay ve kapanışta varlığın puanı `reason="case_decision"` ile yeniden kayda geçer; geçiş olayı
kaydın kimliğini taşır.

### 5. Vaka geçmişi denetim izinin kendisidir
Ayrı bir vaka olay tablosu yok: açılış, geçiş, atama, son tarih, EDD maddesi ve yorum birer
`case.*` denetim olayıdır ve `GET /cases/{id}` geçmişi `seq` sırasıyla oradan okur. Hash zinciri
geçmişi de korur. Yorumlar ayrı tabloda (`case_comment`), silinmez ve düzenlenmez.

### 6. EDD listesi ve süreler ürün varsayılanıdır, mevzuat yorumu değildir
Yedi madde FATF Tavsiye 10/12'nin sıkılaştırılmış tedbir başlıklarından derlenmiş genel bir
şablondur; sürümü (`edd-sablon-v1`) vakaya yazılır, şablon değişirse eski vaka kendi sürümünü
korur. Varsayılan süreler kritik 2, yüksek 5, bilgi 10 gündür ve uyum uzmanı vaka başına
değiştirebilir. Şüphe değerlendirmesi maddesi sonucu yazmaz: ŞİB'in varlığı yalnız yetkili rollere
açıktır (ADR-0011).

## Bilerek yapılmayanlar

- Kiracı başına yönlendirme ve özet (digest) tercihleri: e-posta altyapısı yok (E2.4 ile aynı).
- Sicil/gazete ve olumsuz haber yeniden kontrolü: kaynaklar (E0.3, E3.6) hazır değil.
- İzlenen varlık başına ölçüm: E2.6'nın plan sınırı uygulanıyor; faturalama E3.5'te.

## Doğrulama

Birim 13 (derece + durum makinesi), entegrasyon 4: yaptırım değişikliği → kritik alarm → EDD vakası
→ eşleşme onayı → yükseltme → liste → kapanış → puan yükseldi, kayıt `case_decision`; PEP → yüksek,
analist karar veremez; elle vaka, atama, gecikme süzgeci, kiracı izolasyonu; tekillik kısıtı.
Sekiz koruma tek tek kaldırıldığında testler düştü. İki tablo izolasyon kapısında.
