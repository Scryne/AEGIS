#!/usr/bin/env bash
# Gece yedeği (E1.6): Postgres dökümü + nesne deposu → ikinci konum (şifreli).
#
#   infra/ops/yedek.sh                 # cron: her gece 01:30 UTC (bkz. infra/ops/aegis.cron)
#   infra/ops/yedek.sh --yalniz-yerel  # uzak kopyayı atla (tatbikat / bağlantı yokken)
#
# 1. pg_dump (özel biçim, ayrıcalıklı rol) → $BACKUP_DIR/postgres/aegis-<zaman>.dump
# 2. Döküm doğrulanır (pg_restore --list) ve SHA-256'sı yanına yazılır; bozuksa iş düşer.
# 3. Uzak kopya: döküm + nesne deposu (belgeler) rclone ile S3-uyumlu ikinci konuma, istemci
#    tarafında şifrelenerek (crypt). Nesneler `copy` ile gider: kaynaktan silinen belge uzakta
#    kalır — saklama süresi imhası açıldığında uzak kopya da ayrıca ele alınmalı (docs/deploy.md).
# 4. Başarı işaretleri: .son-yerel / .son-uzak (saglik.sh tazeliği bunlardan ölçer).
# 5. Yerelde BACKUP_KEEP_DAYS, uzakta BACKUP_REMOTE_KEEP_DAYS günden eski dökümler silinir.
#
# Yedek KAPSAMI DIŞI (bilerek): Elasticsearch indeksi (yente yeniden kurar), MASAK FtM dosyası
# (günlük iş yeniden üretir), Redis (kuyruk; işler veritabanında), Caddy sertifikaları
# (yeniden alınır), ortam dosyası (sırlar — parola kasasında ayrıca tutulur).
source "$(dirname "${BASH_SOURCE[0]}")/ortak.sh"

BACKUP_DIR="${BACKUP_DIR:-/var/backups/aegis}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
REMOTE_KEEP_DAYS="${BACKUP_REMOTE_KEEP_DAYS:-35}"
yalniz_yerel=0
[[ "${1:-}" == "--yalniz-yerel" ]] && yalniz_yerel=1

mkdir -p "$BACKUP_DIR/postgres"
exec 9>"$BACKUP_DIR/.kilit"
flock -n 9 || die "başka bir yedek sürüyor"

zaman="$(date -u +%Y%m%dT%H%M%SZ)"
dosya="$BACKUP_DIR/postgres/aegis-$zaman.dump"

log "Postgres dökümü: $dosya"
dc exec -T postgres pg_dump -U aegis -d aegis --format=custom --compress=6 >"$dosya.tmp"
dc exec -T postgres pg_restore --list <"$dosya.tmp" >/dev/null || die "döküm okunamıyor (bozuk)"
mv "$dosya.tmp" "$dosya"
(cd "$BACKUP_DIR/postgres" && sha256sum "$(basename "$dosya")" >"$(basename "$dosya").sha256")
log "döküm doğrulandı ($(du -h "$dosya" | cut -f1))"
date -u +%s >"$BACKUP_DIR/.son-yerel"

if ((yalniz_yerel)); then
	log "UYARI: uzak kopya atlandı (--yalniz-yerel); .son-uzak güncellenmedi"
else
	log "uzak kopya: dökümler"
	rclone_calistir copy /yedek/postgres sifreli:postgres --include "aegis-*" --no-traverse
	log "uzak kopya: nesne deposu (aegis-documents)"
	rclone_calistir copy kaynak:aegis-documents sifreli:nesneler --checksum
	log "uzak dökümlerden ${REMOTE_KEEP_DAYS} günden eskiler siliniyor"
	rclone_calistir delete sifreli:postgres --min-age "${REMOTE_KEEP_DAYS}d"
	date -u +%s >"$BACKUP_DIR/.son-uzak"
fi

find "$BACKUP_DIR/postgres" -name 'aegis-*' -type f -mtime "+$KEEP_DAYS" -print -delete
log "yedek tamam"
