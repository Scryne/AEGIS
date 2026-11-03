---
version: alpha
name: AEGIS
description: MASAK kapsamındaki yükümlüler için KYB / kurumsal due diligence çalışma alanı — denetim dosyası kimliği; kâğıt zemin, mürekkep gezinme, pirinç mühür, kanıt odaklı.
colors:
  bg: "oklch(0.973 0.006 85)"
  surface: "oklch(0.997 0.002 85)"
  subtle: "oklch(0.955 0.007 85)"
  border: "oklch(0.897 0.009 85)"
  border-strong: "oklch(0.8 0.012 85)"
  fg: "oklch(0.245 0.03 255)"
  muted: "oklch(0.47 0.02 255)"
  primary: "oklch(0.42 0.1 240)"
  primary-fg: "oklch(0.985 0.003 85)"
  danger: "oklch(0.49 0.18 27)"
  warning: "oklch(0.5 0.11 70)"
  success: "oklch(0.46 0.11 155)"
  seal: "oklch(0.7 0.11 80)"
  ink: "oklch(0.235 0.035 258)"
  ink-fg: "oklch(0.95 0.006 85)"
  ink-muted: "oklch(0.76 0.018 258)"
typography:
  sans:
    fontFamily: Public Sans
  mono:
    fontFamily: JetBrains Mono
rounded:
  card: 0.5rem
components:
  kart:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.card}"
  birincil-buton:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-fg}"
  mühür-eylemi:
    backgroundColor: "{colors.seal}"
    textColor: "{colors.ink}"
---

## Overview

AEGIS, MASAK kapsamındaki yükümlülerin müşteri şirketleri hakkında kimlik doğrulama, yaptırım/PEP
taraması ve denetime dayanıklı dosya hazırlamasını sağlayan çok kiracılı bir KYB aracıdır.
Uyum kararını **belgeler ve destekler, kendisi vermez**. Arayüzün işi, analistin bir karara
kanıtıyla birlikte hızla varmasıdır: sakin, açık tema bir çalışma alanı; dikkat yalnız risk
durumuna çekilir.

## Colors

- Marka ve tema değerleri yalnız CSS değişkeni olarak (`@theme`) tanımlanır; bileşen kodunda
  renk değeri yazılmaz. Beyaz etiket (kiracıya özel tema, alan adı) bu fazın dışındadır.
- Kimlik "denetim dosyası"dır: sıcak kâğıt zemin (`bg`), mürekkep gezinme ve günün durumu bandı
  (`ink`), mühür vurgusu (`seal`). `seal` yalnız mürekkep üstünde kullanılır: aktif gezinme
  çizgisi, marka işareti, bant içindeki tek eylem. Kâğıt üstünde eylem rengi `primary`'dir.
- `primary` yalnız eylem içindir (birincil buton, bağlantı).
- Risk tonu üç semantik renkle anlatılır: `danger` (onaylanmış eşleşme, acil inceleme, tarama
  yapılamadı), `warning` (inceleme bekleyen, bayat yaptırım verisi), `success` (eşik üstü
  eşleşme yok). Ton her zaman bir metinle birlikte verilir; renk tek başına anlam taşımaz.

## Typography

- Arayüz Public Sans ile yazılır (latin-ext, Türkçe karakter için şart). Kimlik numaraları,
  skorlar, sürümler, özet (hash), tarihler ve normalize edilmiş adlar JetBrains Mono ile
  yazılır: denetçinin karakter karakter karşılaştıracağı her değer eş aralıklıdır.

## Layout

- Kabuk: solda sabit mürekkep gezinme (Çalışma, Bildirim ve denetim, Hesap grupları), üstte
  kullanıcı ve rol. Dar ekranda gezinme çekmeceye taşınır; yatay şerit kullanılmaz, sayfa hiçbir
  genişlikte yatay kaymaz.
- İçerik `.page` genişliğindedir (76rem). Form + liste ekranları genişte iki sütundur.
- Panel günün tek cümlesiyle açılır (en acil konu + tek eylem); sayaçlar ve kuyruklar sonra gelir.
- Bir ekran, önce **sonucu** (risk başlığı), sonra **gerekçeyi** (adaylar, eşleşme nedenleri,
  kaynak), en son **eylemi** gösterir.

## Shapes

- Paneller ve kartlar tek bir köşe yarıçapı (`card`) kullanır.

## Components

- **Kanıt rayı** (`.rail`): kuyruk satırı ve sayaçta sol kenardaki 3 px çizgi risk tonunu taşır.
  Ürünün ayırt edici öğesidir; süs için kullanılmaz, tonu olmayan yerde nötr kalır.
- Risk başlığı her tarama ve varlık ekranının tepesindedir ve tek cümledir. Tarama motora
  ulaşamadıysa başlık "sonuç YOK (temiz değil)" der; başarısız tarama hiçbir zaman temiz
  görünmez.
- Yaptırım verisi 24 saatten eskiyse tarama ekranında uyarı şeridi görünür.
- Her eşleşme adayı skoru, eşleşme nedenleri ve **kaynak bağlantısıyla** gösterilir; elemek
  gerekçe ister, gerekçe denetim izinde kalır.
- Belgeden çıkan hiçbir bilgi onaysız kütüğe girmez: öneriler kanıt metniyle birlikte
  kabul/ret için listelenir.

## Do's and Don'ts

- Don't: başarısız ya da sonuçsuz taramayı "temiz" diliyle göstermek.
- Don't: bileşen koduna marka rengi veya değeri gömmek.
- Do: her bulguyu kaynağına bağlamak; kaynaksız bulgu gösterilmez.
