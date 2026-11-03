#!/usr/bin/env bash
# AEGIS işletim betiklerinin ortak parçası (deploy.sh, yedek.sh, geri_yukle.sh, saglik.sh).
# Doğrudan çalıştırılmaz; `source` edilir.
#
# Ortam dosyası `source` EDİLMEZ (kod çalıştırırdı): yalnız ANAHTAR=değer satırları okunur.
# Dosya yolu: AEGIS_ENV_FILE (varsayılan /etc/aegis/aegis.env).

set -euo pipefail
umask 077

AEGIS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
AEGIS_ENV_FILE="${AEGIS_ENV_FILE:-/etc/aegis/aegis.env}"
AEGIS_STATE_DIR="${AEGIS_STATE_DIR:-/var/lib/aegis}"
COMPOSE_FILE_PROD="$AEGIS_ROOT/infra/compose/docker-compose.prod.yml"
# Compose proje adı sabit: ağ adı (aegis_default) yedek konteynerinde kullanılır.
COMPOSE_PROJECT="aegis"
RCLONE_IMAGE="rclone/rclone:1.75.2"

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2; }
die() { log "HATA: $*"; exit 1; }

env_oku() {
	local file="$1" line key val
	[[ -r "$file" ]] || die "ortam dosyası okunamıyor: $file"
	while IFS= read -r line || [[ -n "$line" ]]; do
		[[ "$line" =~ ^[[:space:]]*(#|$) ]] && continue
		key="${line%%=*}"
		val="${line#*=}"
		[[ "$key" =~ ^[A-Z_][A-Z0-9_]*$ ]] || continue
		# Kabuk ortamında zaten verilmiş değer önceliklidir (compose ile aynı kural).
		[[ -n "${!key+x}" ]] && continue
		val="${val%%[[:space:]]#*}"                 # satır sonu yorumu
		val="${val%"${val##*[![:space:]]}"}"        # sağ boşluk
		val="${val#"${val%%[![:space:]]*}"}"        # sol boşluk
		if [[ "$val" =~ ^\"(.*)\"$ || "$val" =~ ^\'(.*)\'$ ]]; then
			val="${BASH_REMATCH[1]}"
		fi
		export "$key=$val"
	done <"$file"
}

gerekli() {
	local name
	for name in "$@"; do
		[[ -n "${!name:-}" ]] || die "$name tanımlı değil ($AEGIS_ENV_FILE)"
	done
}

env_oku "$AEGIS_ENV_FILE"

# Son dağıtılan imaj etiketi: cron'dan çalışan yedek/sağlık betikleri de compose'u aynı
# etiketle yorumlasın (deploy.sh yazar).
if [[ -z "${AEGIS_IMAGE_TAG:-}" && -r "$AEGIS_STATE_DIR/deployed-tag" ]]; then
	AEGIS_IMAGE_TAG="$(<"$AEGIS_STATE_DIR/deployed-tag")"
	export AEGIS_IMAGE_TAG
fi

dc() {
	local extra=()
	# Sunucuya özgü ek compose dosyası (ör. yerel tatbikat); boşsa yalnız üretim dosyası.
	if [[ -n "${AEGIS_COMPOSE_EXTRA:-}" ]]; then extra=(-f "$AEGIS_COMPOSE_EXTRA"); fi
	docker compose -p "$COMPOSE_PROJECT" -f "$COMPOSE_FILE_PROD" "${extra[@]}" \
		--env-file "$AEGIS_ENV_FILE" "$@"
}

# rclone: kaynak = yerel MinIO, uzak = ikinci konum (S3-uyumlu), sifreli = uzak üzerinde
# istemci tarafı şifreleme. Sırlar komut satırına değil, ortamdan (-e AD) geçer.
rclone_calistir() {
	gerekli MINIO_ROOT_USER MINIO_ROOT_PASSWORD BACKUP_S3_ENDPOINT BACKUP_S3_BUCKET \
		BACKUP_S3_ACCESS_KEY_ID BACKUP_S3_SECRET_ACCESS_KEY BACKUP_CRYPT_PASSWORD BACKUP_CRYPT_SALT
	local obscured obscured_salt
	obscured="$(printf '%s' "$BACKUP_CRYPT_PASSWORD" | docker run --rm -i "$RCLONE_IMAGE" obscure -)"
	obscured_salt="$(printf '%s' "$BACKUP_CRYPT_SALT" | docker run --rm -i "$RCLONE_IMAGE" obscure -)"
	export RCLONE_CONFIG_KAYNAK_TYPE=s3 RCLONE_CONFIG_KAYNAK_PROVIDER=Minio \
		RCLONE_CONFIG_KAYNAK_ENDPOINT=http://minio:9000 \
		RCLONE_CONFIG_KAYNAK_ACCESS_KEY_ID="$MINIO_ROOT_USER" \
		RCLONE_CONFIG_KAYNAK_SECRET_ACCESS_KEY="$MINIO_ROOT_PASSWORD" \
		RCLONE_CONFIG_UZAK_TYPE=s3 RCLONE_CONFIG_UZAK_PROVIDER="${BACKUP_S3_PROVIDER:-Other}" \
		RCLONE_CONFIG_UZAK_ENDPOINT="$BACKUP_S3_ENDPOINT" \
		RCLONE_CONFIG_UZAK_REGION="${BACKUP_S3_REGION:-}" \
		RCLONE_CONFIG_UZAK_ACCESS_KEY_ID="$BACKUP_S3_ACCESS_KEY_ID" \
		RCLONE_CONFIG_UZAK_SECRET_ACCESS_KEY="$BACKUP_S3_SECRET_ACCESS_KEY" \
		RCLONE_CONFIG_SIFRELI_TYPE=crypt \
		RCLONE_CONFIG_SIFRELI_REMOTE="uzak:$BACKUP_S3_BUCKET/aegis" \
		RCLONE_CONFIG_SIFRELI_PASSWORD="$obscured" \
		RCLONE_CONFIG_SIFRELI_PASSWORD2="$obscured_salt"
	local envs=() name
	for name in $(compgen -e | grep '^RCLONE_CONFIG_'); do envs+=(-e "$name"); done
	docker run --rm --network "${COMPOSE_PROJECT}_default" "${envs[@]}" \
		-v "${BACKUP_DIR:-/var/backups/aegis}:/yedek" "$RCLONE_IMAGE" "$@"
}
