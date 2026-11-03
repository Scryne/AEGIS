#!/bin/sh
# AEGIS üretim — RLS'ye TABİ, süper kullanıcı OLMAYAN uygulama rolü (ADR-0002).
#
# Geliştirmedeki initdb/10-app-role.sql ile aynı yetkiler; tek fark parola: sabit değil,
# ortam dosyasından (AEGIS_APP_DB_PASSWORD). Yalnız boş veri hacminde (ilk kurulum) çalışır.
# audit_event için UPDATE/DELETE, migration 0002'de bu rolden geri alınır (Invariant 2).
set -eu

: "${AEGIS_APP_DB_PASSWORD:?AEGIS_APP_DB_PASSWORD tanımlı değil}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
	-v app_password="$AEGIS_APP_DB_PASSWORD" <<'SQL'
CREATE ROLE aegis_app LOGIN PASSWORD :'app_password';

GRANT USAGE ON SCHEMA public TO aegis_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO aegis_app;

ALTER DEFAULT PRIVILEGES FOR ROLE aegis IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO aegis_app;
SQL
