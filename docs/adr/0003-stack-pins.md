# ADR-0003: Yığın sürüm sabitleri (Phase 1 başlangıcı)

- **Durum:** Kabul edildi
- **Tarih:** 2026-07-22
- **Karar veren:** Scryne

## Bağlam
Roadmap, Phase 1 başında Next.js'i "güncel kararlı ana sürüme" sabitlemeyi ister; yente
resmi olarak belirli bir Elasticsearch sürümünü destekler. Sürümler baştan kilitlenmezse
sürükleniş (drift) ve uyumsuzluk riski doğar.

## Karar

| Bileşen | Sabit | Not |
|---|---|---|
| Python | 3.12 · uv | TenderIQ ile aynı |
| Next.js | **16.x** | Turbopack varsayılan; `middleware.ts` → **`proxy.ts`** (Node runtime) |
| React | 19.2 | Next 16 ile gelir |
| Node | 22 LTS | Next 16 min 20.9 |
| PostgreSQL | 16 | `gen_random_uuid()` çekirdekte. **pgvector YOK** (Revision R4) |
| Redis | 7 | |
| Elasticsearch | **9.4.2** | yente 5.5.0'ın kendi compose'undan pinlendi |
| yente | **5.5.0** | self-host tarama; `YENTE_INDEX_URL` |

**Elasticsearch gerekçesi:** Temmuz 2026 itibarıyla Mayıs 2026 sonrası yente sürümleri
Elasticsearch 9.x gerektirir (ES 8 desteği son pre-Mayıs sürümde kaldı). Güncel yente
(5.5.0) vendor'landığı için ES 9.4.2 pinlenir; kesin patch, vendor'lanan yente sürümüyle
birlikte E1.3'te güncellenir.

**yente/ES footprint (host boyutlandırması, E1.6):** OpenSanctions ES indeksi için
**4–16 GB RAM + 10–30 GB SSD** belgeler; yente 5.5.0 compose'u `ES_JAVA_OPTS=-Xms4g
-Xmx4g` ayarlar. Tek-host'ta baskın maliyet — 2–4 GB VPS yetmez. Dev compose'da
`screening` profili altında dahil edilir (erken ölçüm).

**Next 16 `proxy.ts` sonucu:** TenderIQ'nun Next `middleware.ts` (auth yönlendirme
kapısı) deseni AEGIS'te `proxy.ts` + `proxy` export'u olarak taşınır (Node runtime;
yalnız rewrite/redirect/başlık). **Güvenlik-kritik RLS kiracı çözümlemesi Python
tarafındadır** (`get_tenant_session`) ve bu yeniden adlandırmadan etkilenmez.

## Sonuçlar
**Olumlu:** Uyumluluk baştan kilitli; ES/yente footprint kayıtlı.
**Ödünler:** Next 16 Turbopack varsayılanı; egzotik webpack eklentileri gerekirse
`next build --webpack`'e düşülür.

## İlgili
Roadmap §5 (R4, R6); CLAUDE.md (Stack pins).
