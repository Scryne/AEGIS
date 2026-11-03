#!/usr/bin/env bash
# Sağlık kontrolü + telefona uyarı (E1.6). cron: 5 dakikada bir (infra/ops/aegis.cron).
#
# Denetlenenler:
#   - arayüz ve API dışarıdan, TLS üzerinden yanıt veriyor mu (Caddy dahil tüm yol)
#   - /readyz: veritabanı + Redis hazır mı; yente düşükse ayrıca uyarır (tarama "failed" döner)
#   - TLS sertifikasının bitişine 14 günden az mı kaldı (Caddy yenileyemiyor demektir)
#   - compose servislerinden sağlıksız/durmuş olan var mı
#   - son yerel yedek ve son uzak kopya 26 saatten eski mi
#   - kök disk %85'ten dolu mu (ES ve Postgres ilk etkilenen)
#
# Sorun varsa ALERT_WEBHOOK_URL'e düz metin POST edilir (ör. kendi ntfy konunuz → telefon).
# Aynı sorun sürerken en çok saatte bir tekrar edilir; düzelince "düzeldi" gönderilir.
# NOT: Sunucu tümden düşerse bu betik de çalışmaz — dışarıdan bir uptime izleyicisi
# (https://$AEGIS_API_DOMAIN/readyz) ayrıca kurulmalı (docs/deploy.md).
source "$(dirname "${BASH_SOURCE[0]}")/ortak.sh"

BACKUP_DIR="${BACKUP_DIR:-/var/backups/aegis}"
YEDEK_MAX_SN=$((26 * 3600))
DISK_ESIK="${AEGIS_DISK_ALARM_PERCENT:-85}"
TEKRAR_SN=3600
mkdir -p "$AEGIS_STATE_DIR"
durum_dosyasi="$AEGIS_STATE_DIR/saglik.durum"
sorunlar=()

gerekli AEGIS_DOMAIN AEGIS_API_DOMAIN

curl -fsS --max-time 15 -o /dev/null "https://$AEGIS_DOMAIN/login" \
	|| sorunlar+=("arayüz yanıt vermiyor (https://$AEGIS_DOMAIN)")

if hazir="$(curl -sS --max-time 15 "https://$AEGIS_API_DOMAIN/readyz" 2>&1)"; then
	if ! grep -q '"ready":true' <<<"$hazir"; then
		sorunlar+=("API hazır değil: $hazir")
	elif grep -q '"name":"yente","healthy":false' <<<"$hazir"; then
		sorunlar+=("tarama motoru (yente) hazır değil — taramalar başarısız döner")
	fi
else
	sorunlar+=("API'ye ulaşılamıyor: $hazir")
fi

for alan in "$AEGIS_DOMAIN" "$AEGIS_API_DOMAIN"; do
	if ! echo | openssl s_client -connect "$alan:443" -servername "$alan" 2>/dev/null \
		| openssl x509 -noout -checkend $((14 * 86400)) >/dev/null 2>&1; then
		sorunlar+=("TLS sertifikası okunamadı ya da 14 günden az kaldı: $alan")
	fi
done

while IFS='|' read -r ad durum saglik; do
	[[ -z "$ad" || "$ad" == "migrate" ]] && continue
	if [[ "$durum" != "running" || ("$saglik" != "healthy" && -n "$saglik") ]]; then
		sorunlar+=("servis $ad: ${durum} ${saglik}")
	fi
done < <(dc ps -a --format '{{.Service}}|{{.State}}|{{.Health}}' 2>/dev/null || echo "compose|okunamadı|")

simdi="$(date -u +%s)"
for isaret in son-yerel son-uzak; do
	son="$(cat "$BACKUP_DIR/.$isaret" 2>/dev/null || echo 0)"
	if ((simdi - son > YEDEK_MAX_SN)); then
		sorunlar+=("yedek ($isaret) 26 saatten eski ya da hiç alınmamış")
	fi
done

doluluk="$(df --output=pcent / | tail -n1 | tr -dc '0-9')"
((doluluk < DISK_ESIK)) || sorunlar+=("kök disk %$doluluk dolu (eşik %$DISK_ESIK)")

gonder() {
	log "$1"
	[[ -n "${ALERT_WEBHOOK_URL:-}" ]] || return 0
	curl -fsS --max-time 10 -H "Title: AEGIS $(hostname)" -d "$1" "$ALERT_WEBHOOK_URL" >/dev/null \
		|| log "UYARI: uyarı gönderilemedi ($ALERT_WEBHOOK_URL)"
}

onceki_imza="" onceki_zaman=0
if [[ -r "$durum_dosyasi" ]]; then read -r onceki_zaman onceki_imza <"$durum_dosyasi" || true; fi

if ((${#sorunlar[@]} == 0)); then
	if [[ -n "$onceki_imza" && "$onceki_imza" != "ok" ]]; then gonder "AEGIS düzeldi: tüm kontroller geçti"; fi
	printf '%s ok\n' "$simdi" >"$durum_dosyasi"
	exit 0
fi

metin="$(printf '%s\n' "${sorunlar[@]}")"
imza="$(sha256sum <<<"$metin" | cut -c1-16)"
if [[ "$imza" != "$onceki_imza" ]] || ((simdi - onceki_zaman >= TEKRAR_SN)); then
	gonder "AEGIS SORUN (${#sorunlar[@]}):"$'\n'"$metin"
	printf '%s %s\n' "$simdi" "$imza" >"$durum_dosyasi"
else
	log "sorun sürüyor (uyarı zaten gönderildi): ${sorunlar[*]}"
fi
exit 1
