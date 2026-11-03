#!/usr/bin/env bash
# Geri yükleme ve geri yükleme tatbikatı (E1.6). Ayrıntılı adımlar: docs/deploy.md.
#
#   infra/ops/geri_yukle.sh liste                          # yerel + uzak dökümler
#   infra/ops/geri_yukle.sh indir <aegis-...dump>          # uzaktan (şifreli) indir
#   infra/ops/geri_yukle.sh tatbikat <dump-yolu> [--birak] # AYRI veritabanına yükle + doğrula
#   infra/ops/geri_yukle.sh uretim <dump-yolu> --onayla [--nesneler]
#
# tatbikat: canlı veritabanına DOKUNMAZ. Dökümü `aegis_tatbikat`a yükler, SHA-256'yı denetler,
#   her kiracının denetim izi hash zincirini doğrular (scripts/denetim_zinciri_dogrula.py),
#   tablo sayılarını basar, sonra tatbikat veritabanını siler (--birak verilmedikçe).
# uretim: api/web/worker/beat durdurulur, `aegis` dökümle değiştirilir (tek transaction),
#   migration koşar, zincir doğrulanır, servisler açılır. --nesneler: belgeleri de uzaktan
#   geri kopyalar (var olanların üzerine yazmaz).
source "$(dirname "${BASH_SOURCE[0]}")/ortak.sh"

BACKUP_DIR="${BACKUP_DIR:-/var/backups/aegis}"
TATBIKAT_DB="aegis_tatbikat"

sha_denetle() {
	local dump="$1"
	if [[ -r "$dump.sha256" ]]; then
		(cd "$(dirname "$dump")" && sha256sum --check --quiet "$(basename "$dump").sha256") \
			|| die "SHA-256 tutmuyor: $dump"
		log "SHA-256 tuttu"
	else
		log "UYARI: $dump.sha256 yok; bütünlük yalnız pg_restore --list ile denetlenecek"
	fi
	dc exec -T postgres pg_restore --list <"$dump" >/dev/null || die "döküm okunamıyor: $dump"
}

zincir_dogrula() {
	local db="$1"
	log "denetim izi zinciri doğrulanıyor ($db)"
	dc run --rm --no-deps api python scripts/denetim_zinciri_dogrula.py --veritabani "$db"
}

sayilar() {
	dc exec -T postgres psql -U aegis -d "$1" -v ON_ERROR_STOP=1 -At -F ' ' -c "
		SELECT 'kiraci', count(*)::text FROM organization
		UNION ALL SELECT 'kullanici', count(*)::text FROM user_account
		UNION ALL SELECT 'denetim_olayi', count(*)::text FROM audit_event
		UNION ALL SELECT 'varlik', count(*)::text FROM entity
		UNION ALL SELECT 'tarama', count(*)::text FROM screening
		UNION ALL SELECT 'belge', count(*)::text FROM document
		UNION ALL SELECT 'rapor', count(*)::text FROM report
		UNION ALL SELECT 'alembic', version_num FROM alembic_version"
}

komut="${1:-}"
case "$komut" in
	liste)
		ls -l "$BACKUP_DIR/postgres" 2>/dev/null || log "yerel döküm yok"
		rclone_calistir lsl sifreli:postgres
		;;
	indir)
		ad="${2:?dosya adı gerekli (geri_yukle.sh liste)}"
		[[ "$ad" =~ ^aegis-[0-9TZ]+\.dump$ ]] || die "geçersiz dosya adı: $ad"
		mkdir -p "$BACKUP_DIR/indirilen"
		rclone_calistir copy "sifreli:postgres/$ad" /yedek/indirilen
		rclone_calistir copy "sifreli:postgres/$ad.sha256" /yedek/indirilen || true
		log "indirildi: $BACKUP_DIR/indirilen/$ad"
		;;
	tatbikat)
		dump="${2:?döküm yolu gerekli}"
		[[ -r "$dump" ]] || die "okunamıyor: $dump"
		sha_denetle "$dump"
		baslangic=$SECONDS
		dc exec -T postgres dropdb -U aegis --if-exists "$TATBIKAT_DB"
		dc exec -T postgres createdb -U aegis -O aegis "$TATBIKAT_DB"
		dc exec -T postgres pg_restore -U aegis -d "$TATBIKAT_DB" --exit-on-error \
			--single-transaction <"$dump"
		log "geri yüklendi: $((SECONDS - baslangic)) sn"
		sayilar "$TATBIKAT_DB"
		zincir_dogrula "$TATBIKAT_DB"
		if [[ "${3:-}" != "--birak" ]]; then
			dc exec -T postgres dropdb -U aegis "$TATBIKAT_DB"
		fi
		log "TATBİKAT BAŞARILI — sonucu docs/deploy.md 'Tatbikat kaydı' tablosuna yazın"
		;;
	uretim)
		dump="${2:?döküm yolu gerekli}"
		[[ "${3:-}" == "--onayla" ]] || die "canlı veritabanı değişecek; --onayla gerekli"
		[[ -r "$dump" ]] || die "okunamıyor: $dump"
		sha_denetle "$dump"
		log "uygulama servisleri durduruluyor"
		dc stop caddy web api worker beat
		dc exec -T postgres pg_restore -U aegis -d aegis --clean --if-exists --exit-on-error \
			--single-transaction <"$dump"
		dc run --rm migrate
		sayilar aegis
		zincir_dogrula aegis
		if [[ "${4:-}" == "--nesneler" ]]; then
			log "belgeler uzaktan geri kopyalanıyor"
			rclone_calistir copy sifreli:nesneler kaynak:aegis-documents --ignore-existing
		fi
		dc up -d
		log "üretim geri yüklemesi tamam; saglik.sh ile doğrulayın"
		;;
	*)
		die "kullanım: geri_yukle.sh liste | indir <dosya> | tatbikat <dump> [--birak] | uretim <dump> --onayla [--nesneler]"
		;;
esac
