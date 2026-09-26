---
version: alpha
name: AEGIS
description: MASAK kapsamındaki yükümlüler için KYB / kurumsal due diligence çalışma alanı — sakin, açık tema, kanıt odaklı; renk yalnız risk durumunu taşır.
colors:
  bg: "oklch(0.99 0 0)"
  surface: "oklch(1 0 0)"
  border: "oklch(0.92 0.004 260)"
  fg: "oklch(0.22 0.02 260)"
  muted: "oklch(0.55 0.02 260)"
  primary: "oklch(0.52 0.13 245)"
  primary-fg: "oklch(0.99 0 0)"
  danger: "oklch(0.55 0.19 25)"
  warning: "oklch(0.72 0.15 75)"
  success: "oklch(0.6 0.13 150)"
typography:
  sans:
    fontFamily: ui-sans-serif
  mono:
    fontFamily: ui-monospace
rounded:
  card: 0.625rem
components:
  kart:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.card}"
  birincil-buton:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-fg}"
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
- `primary` yalnız eylem içindir (birincil buton, bağlantı).
- Risk tonu üç semantik renkle anlatılır: `danger` (onaylanmış eşleşme, acil inceleme, tarama
  yapılamadı), `warning` (inceleme bekleyen, bayat yaptırım verisi), `success` (eşik üstü
  eşleşme yok). Ton her zaman bir metinle birlikte verilir; renk tek başına anlam taşımaz.

## Typography

- Arayüz sistem sans ailesiyle yazılır. Kimlik numaraları, skorlar, sürümler, özet (hash)
  ve normalize edilmiş adlar `mono` ile yazılır: denetçinin karakter karakter karşılaştıracağı
  her değer eş aralıklıdır.

## Layout

- Kabuk: solda sabit gezinme (Panel, Taramalar, Varlıklar, Denetim İzi), üstte kullanıcı ve rol,
  içerik ortalı tek sütun. Dar ekranda gezinme içeriğin üstüne taşınır; sayfa hiçbir genişlikte
  yatay kaymaz.
- Bir ekran, önce **sonucu** (risk başlığı), sonra **gerekçeyi** (adaylar, eşleşme nedenleri,
  kaynak), en son **eylemi** gösterir.

## Shapes

- Paneller ve kartlar tek bir köşe yarıçapı (`card`) kullanır.

## Components

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
