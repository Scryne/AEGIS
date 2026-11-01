"""Kuyruk sözleşmesi: task adları ve kuyruk adı sabitleri.

API (üretici) ve worker (tüketici) task'lara yalnızca bu adlarla başvurur;
API, worker kodunu import etmez (``send_task`` ada göre yayınlar — bkz.
``aegis_api.queue``). Bu modül bilinçli olarak bağımlılıksızdır: yalnız sabitler.
"""

from __future__ import annotations

QUEUE_DEFAULT = "aegis"

TASK_PING = "system.ping"
# E1.2 saklama süresi imha job'ı (şimdilik kuru çalışma; E3.7'de silmeye döner).
TASK_RETENTION_DISPOSE = "retention.dispose"
# E1.3 tarama: derin (çok özneli) koşu — senkron yol NFR'yi (< 30 sn) korur.
TASK_SCREENING_RUN = "screening.run"
# E1.3 günlük yaptırım verisi senkronu + tazelik metriği + bayatlık alarmı.
TASK_SANCTIONS_SYNC = "sanctions.sync"
# E1.4 belge çıkarımı (Docling) — yükleme isteğini bekletmemek için asenkron.
TASK_DOCUMENT_EXTRACT = "document.extract"

# E2.4 izleme-lite gece koşusu.
TASK_MONITORING_NIGHTLY = "monitoring.nightly"
# E3.3 toplu tarama: bir toplu işin bekleyen satırlarını parça parça işler.
TASK_BATCH_PROCESS = "batch.process"
# E3.4 webhook teslimi: zamanı gelen teslimleri dener (beat, 30 sn).
TASK_WEBHOOKS_DELIVER = "webhooks.deliver"
# E3.6 haftalık eşleşme kalitesi ölçümü (eğilim için kayıt).
TASK_QUALITY_WEEKLY = "quality.weekly"
# E3.5 ay sonu kullanım dökümü (önceki dönemi dondurur; idempotent).
TASK_BILLING_CLOSE = "billing.close_period"
