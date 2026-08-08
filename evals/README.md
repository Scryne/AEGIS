# AEGIS — Türkçe tarama değerlendirme seti ve recall tabanı

Bu dizin, taramanın **doğruluk kapısıdır**. CLAUDE.md'deki kural:

> Bir **recall floor (~%100)** CI'da "tarama tamam" demenin ön koşuludur — yanlış
> negatifler tehlikeli hatadır.

Yanlış pozitif bir eşleşme kullanıcıya birkaç dakikaya mal olur; yanlış negatif, yükümlüyü
MASAK karşısında savunmasız bırakır. Bu yüzden kapı asimetriktir: recall %100, kesinlik
yalnız "aşırı temizlik" emniyet kemeriyle korunur.

## İki katman

| Katman | Dosya | Ne ölçer | Nerede koşar |
|---|---|---|---|
| 1. Normalizasyon | `test_normalization_recall.py` | Aynı varlığın tüm yazımları aynı kanonik anahtara iniyor mu | **Her push** (Docker yok, ~0.1 sn) |
| 2. Uçtan uca | `test_screening_recall.py` | Varyantla arayan kullanıcı listedeki kaydı gerçekten buluyor mu | `-m screening` (yente + Elasticsearch) |

Katman 1, hızlı geri bildirim ve regresyon koruması içindir. Katman 2, asıl sorunun
cevabıdır — normalizasyon tutarlı olup da motor yine de bulamayabilir.

## Veri seti

`turkish_screening/cases.json` — 34 vaka, 100+ yazım varyantı. Her vakada:

- `canonical`: gerçek varlığın referans yazımı (indekslenen budur)
- `variants`: sahada karşılaşılan yazımlar (aranan bunlardır)
- `category`: `legal_form` · `casing_i` · `transliteration` · `punctuation` ·
  `word_order` · `person_title` · `branch` · `conjunction` · `over_stripping_guard`

Ayrıca `distinct_pairs`: aynı anahtara **inmemesi** gereken benzer adlar. Bu olmasaydı
kapı "her şeyi sil, hepsi eşleşsin" diyen bir normalizasyonla geçilebilirdi.

### Kapsanan Türkçe tuzaklar

- **İ/ı**: `ISTANBUL` ≠ `İSTANBUL` — Python'un `str.lower()`'ı bunu yanlış yapar
- **Harf çevirisi**: uluslararası listeler `Şahin`'i `Sahin` yazar
- **Tüzel ek**: `A.Ş.`, `Ltd. Şti.`, `San. ve Tic.` — ASCII yazımları (`LTD STI`, `AS`) dahil
- **Gövde-içi ek**: `ABC Lojistik A.Ş. İstanbul Şubesi`
- **Ad-soyad sırası**: `YILMAZ, Ayşe`
- **Unvan öneki**: `Dr.`, `Av.`, `Prof.`

## Katman 2'yi koşturma

```bash
# 1. Değerlendirme veri kümesini üret (cases.json değiştiyse)
uv run python evals/build_eval_dataset.py

# 2. Ortamı kaldır (yalnız 34 varlık indekslenir — OpenSanctions indirilmez)
docker compose -f infra/compose/docker-compose.evals.yml up -d --wait

# 3. Kapıyı koştur
YENTE_TEST_URL=http://localhost:8002 uv run pytest -m screening

# 4. Temizle
docker compose -f infra/compose/docker-compose.evals.yml down -v
```

`YENTE_TEST_URL` verilmezse katman 2 **atlanır** — yerel geliştirmede 4 GB'lık bir
Elasticsearch ayağa kaldırmak zorunlu olmasın diye.

## Vaka ekleme

Gerçek bir kaçak yakalandığında (pilot geri bildirimi, üretim incelemesi) önce buraya
bir vaka eklenir, kapının kırmızıya düştüğü görülür, sonra normalizasyon düzeltilir.
Kapıyı gevşetmek — `RECALL_FLOOR`'u düşürmek — kod incelemesinde açıkça gerekçelendirilmesi
gereken bir karardır.

`cases.json` değiştiğinde `build_eval_dataset.py` yeniden koşturulup
`fixtures/entities.ftm.json` güncellenmelidir (ikisi birlikte işlenir).
