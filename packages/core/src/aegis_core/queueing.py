"""Kuyruk sözleşmesi: task adları ve kuyruk adı sabitleri.

API (üretici) ve worker (tüketici) task'lara yalnızca bu adlarla başvurur;
API, worker kodunu import etmez (``send_task`` ada göre yayınlar).
"""

from __future__ import annotations

QUEUE_DEFAULT = "aegis"

# E1.3+ task adları buraya eklenir (screening.run, sanctions.sync ...).
TASK_PING = "system.ping"
# E1.2 saklama süresi imha job'ı (şimdilik kuru çalışma; E3.7'de silmeye döner).
TASK_RETENTION_DISPOSE = "retention.dispose"
