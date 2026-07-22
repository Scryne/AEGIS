"""Kuyruk sözleşmesi: task adları ve kuyruk adı sabitleri.

API (üretici) ve worker (tüketici) task'lara yalnızca bu adlarla başvurur;
API, worker kodunu import etmez (``send_task`` ada göre yayınlar).
"""

from __future__ import annotations

QUEUE_DEFAULT = "aegis"

# E1.3+ task adları buraya eklenir (screening.run, sanctions.sync ...).
TASK_PING = "system.ping"
