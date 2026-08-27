# DURUM — AEGIS — MASAK/KYB due diligence

> **Ne bu dosya:** sertifika değil **envanter**. 2026-08-27 denetiminde ölçülen gerçek durum.
> "Çalışmıyor" yazan satır kusur değil, kayıt. Kapanış standardı:
> `ScryneOS/🎯 100-Command-Center/Kapanis-Standardi.md`

**Ölçüm tarihi:** 2026-08-27
**Tek cümle:** Backend ve web derleniyor, 250 test geçiyor; proje 2026-08-08'den beri duraklamış.

## Ne çalışıyor

- **Python testleri: 250 geçti**, 109 deselect (entegrasyon, DB isteyenler). Süre 4,85 sn.
- **Web derlemesi başarılı** — 8 rota: `/dashboard` · `/entities` · `/entities/[id]` ·
  `/screenings` · `/screenings/[id]` · `/audit` · `/login` · `/api/v1/[...path]` proxy.
- Bağımlılıklar kurulu (`node_modules` + `.venv`), `uv run pytest` sorunsuz.
- Git: `main`, `origin/main` ile eşit.

## Ne çalışmıyor / doğrulanmadı

- **Uçtan uca çalıştırma denenmedi.** `docker-compose` yok; `api:dev` / `worker:dev`
  ayrı ayrı başlatılıyor, gerçek bir istek akışı bu denetimde koşturulmadı.
- 109 deselect edilen test hiç koşmadı — neyi kapsadıkları doğrulanmadı.
- JWT testinde uyarı: HMAC anahtarı 12 bayt (önerilen 32). Test ortamı ayarı olabilir,
  üretim ayarı olup olmadığı bakılmadı.

## Ne yarım

- `PORTFOLYO-BRIFING.md` yazılmış ama commit edilmemişti (bu denetimde commit edildi).
- Portföy vaka çalışması var, ekran görüntüsü yok.

## Sonraki adım

Ekranı gerçekten açıp bir tarama akışını uçtan uca koştur; sonucu buraya yaz.
