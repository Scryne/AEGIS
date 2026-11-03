# ADR-0019: İzleme koşu kaydı, yeniden deneme ve e-posta bildirimi

**Durum:** Kabul edildi (2026-11-03). E3.1'in güvenilirlik ve yönlendirme maddelerini kapatır.

## Bağlam

Gece izlemesinde motora ulaşılamayan varlık yalnız log satırı bırakıyordu. Uyum görevlisi taramanın
yapılmadığını göremiyordu; DESIGN.md'nin "başarısız tarama temiz görünmez" ilkesiyle çelişiyordu.
Üründe e-posta altyapısı da yoktu: alarm yönlendirmesi ve üretimde parola sıfırlama teslimi bekliyordu.

## Karar

- **Koşu kaydı (`monitoring_run`, göç 0017, RLS):** her koşu taranan, atlanan, alarm, başarısız ve yeniden
  denenen sayıları, süre dökümünü ve taranamayan varlıkları tutar. İzleme ekranında görünür.
- **Yeniden deneme:** düşen varlıklar koşu sonunda bir kez daha denenir. Kalıcı hata `failures` listesinde
  kalır (işlenemeyen iş kaydı); sonraki gece koşusu yeniden dener. Ayrı bir kuyruk kurulmaz.
- **Başarısız tarama savepoint'i geri almaz:** hata fırlatılmaz, sonuç değeri döner. Yoksa "tarama yapılamadı"
  kaydı ve denetim olayı silinirdi.
- **Tekrar koşmama:** görev yeniden teslim edilirse (`acks_late`) gece koşusu son 18 saatte tamamlanmış kullanıcısız
  taraması olan varlığı atlar. Elle koşu her zaman tarar.
- **Bildirim:** derece başına `immediate` ya da `digest`, alıcı roller (`tenant_setting`, denetim izinde). "Kapalı" kipi
  yoktur; alarm ekranda her zaman görünür. Alarm, sunucu iletiyi kabul edince `notified_at` alır; SMTP düşerse sonraki turda
  yeniden denenir. E-posta kişisel veri taşımaz: sayı, derece, panele bağlantı (ADR-0016 ile aynı ilke).
- **SMTP:** tek arayüz (`notifications/email.py`), sağlayıcı SDK'sı yok. Yapılandırılmamışsa "gönderildi" sayılmaz,
  arayüz bunu açıkça söyler. Parola sıfırlama da aynı kanaldan gider; yanıt hesabın varlığını ele vermez.

## Sonuç ve açık kalan

- Prometheus yok: aşama süreleri koşu kaydında ve yapılandırılmış logdadır. Metrik sunucusu üretim kurulumuyla gelir.
- Gerçek SMTP sunucusuyla teslim denenmedi; davranış sahte gönderici ve birim testleriyle sınandı.
- Sicil/gazete farkı kapsam dışı: veri kaynağı erişimi (E0.3) yok. Olumsuz haber yeniden kontrolü E2.5 beta çıkışına bağlı.
