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
-- audit_event için UPDATE/DELETE, migration 0002'de bu rolden REVOKE edilir
-- (append-only, Invariant 2) — ayrıca bir BEFORE trigger'ı rolden bağımsız reddeder.
ALTER DEFAULT PRIVILEGES FOR ROLE aegis IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO aegis_app;
