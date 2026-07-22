-- AEGIS — RLS'ye TABİ, süper-kullanıcı OLMAYAN uygulama rolü.
--
-- POSTGRES_USER (aegis) süper-kullanıcıdır ve RLS'yi baypas eder; uygulama
-- (api/worker) ASLA o rolle bağlanmaz. Migration'lar aegis (ayrıcalıklı),
-- runtime ise aegis_app (RLS'ye tabi) ile çalışır. Bkz. ADR-0002.
--
-- Not: init script'leri yalnızca boş veri hacminde (ilk kurulum) çalışır.
CREATE ROLE aegis_app LOGIN PASSWORD 'aegis_app';

GRANT USAGE ON SCHEMA public TO aegis_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO aegis_app;

-- Migration'ların (aegis) oluşturacağı GELECEK tablolar için varsayılan yetkiler.
-- E1.2'de audit_events için UPDATE/DELETE bu rolden REVOKE edilecektir (append-only).
ALTER DEFAULT PRIVILEGES FOR ROLE aegis IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO aegis_app;
