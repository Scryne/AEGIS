#!/usr/bin/env bash
# Tek komutluk dağıtım (E1.6). Sunucuda, depo kökünde:
#
#   infra/ops/deploy.sh <imaj-etiketi>        # ör. git commit SHA'sı (CI GHCR'a iter)
#   infra/ops/deploy.sh --geri-al              # bir önceki etikete dön
#
# Sıra: imajları çek → veritabanını ayağa kaldır → migration (ayrıcalıklı rol, tek seferlik)
# → tüm servisleri yeni etiketle başlat → sağlık kontrollerini bekle → etiketi kaydet.
# Sağlık beklemesi zaman aşımına uğrarsa etiket KAYDEDİLMEZ ve çıkış kodu 1 olur; geri dönmek
# için `--geri-al`. Migration'lar ileri yönlüdür: geri alma şemayı geri almaz (docs/deploy.md).
source "$(dirname "${BASH_SOURCE[0]}")/ortak.sh"

SERVISLER=(postgres redis minio elasticsearch yente api worker beat web caddy)
BEKLEME_SN="${AEGIS_DEPLOY_WAIT_SECONDS:-600}"

hedef="${1:-}"
[[ -n "$hedef" ]] || die "kullanım: deploy.sh <imaj-etiketi> | --geri-al"
mkdir -p "$AEGIS_STATE_DIR"
if [[ "$hedef" == "--geri-al" ]]; then
	[[ -r "$AEGIS_STATE_DIR/previous-tag" ]] || die "önceki etiket kaydı yok"
	hedef="$(<"$AEGIS_STATE_DIR/previous-tag")"
fi
[[ "$hedef" =~ ^[A-Za-z0-9._-]{1,128}$ ]] || die "geçersiz etiket: $hedef"
onceki="$(cat "$AEGIS_STATE_DIR/deployed-tag" 2>/dev/null || true)"
export AEGIS_IMAGE_TAG="$hedef"

gerekli AEGIS_DOMAIN AEGIS_API_DOMAIN AEGIS_IMAGE_REGISTRY
log "dağıtım: ${onceki:-ilk kurulum} → $hedef"

dc config --quiet
dc pull --quiet
dc up -d --wait postgres
dc run --rm migrate
dc up -d --remove-orphans

saglikli_mi() {
	local svc state
	for svc in "${SERVISLER[@]}"; do
		state="$(dc ps --format '{{.Health}}|{{.State}}' "$svc" 2>/dev/null | head -n1)"
		case "$state" in
			healthy\|running) ;;
			*) printf '%s=%s ' "$svc" "${state:-yok}"; return 1 ;;
		esac
	done
}

bitis=$((SECONDS + BEKLEME_SN))
until durum="$(saglikli_mi)"; do
	if ((SECONDS >= bitis)); then
		dc ps
		die "servisler ${BEKLEME_SN} sn içinde sağlıklı olmadı: $durum (geri dönmek için: deploy.sh --geri-al)"
	fi
	sleep 10
done

if [[ -n "$onceki" && "$onceki" != "$hedef" ]]; then
	printf '%s\n' "$onceki" >"$AEGIS_STATE_DIR/previous-tag"
fi
printf '%s\n' "$hedef" >"$AEGIS_STATE_DIR/deployed-tag"

# Dışarıdan (Caddy + TLS üzerinden) son bir duman testi.
if ! curl -fsS --max-time 15 "https://$AEGIS_API_DOMAIN/readyz" >/dev/null; then
	log "UYARI: https://$AEGIS_API_DOMAIN/readyz dışarıdan yanıt vermedi (DNS/TLS?)"
fi
docker image prune -f >/dev/null
dc ps
log "dağıtım tamam: $hedef"
