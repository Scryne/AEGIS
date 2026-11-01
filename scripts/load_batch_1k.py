"""Yük ölçümü (E3.7): 1.000 satırlık toplu tarama, satır başına durum ve kota doğruluğu.

Phase 3 çıkış ölçütü 3: *"1k-row batch completes with per-row status and correct quota
accounting"*. Uygulama süreç içinde (TestClient) ve gerçek PostgreSQL'e karşı koşar; yente taklit
edilir (motor gecikmesi ``--latency-ms`` ile eklenebilir), çünkü ölçülen bizim hattımızdır.

Kullanım (hazır bir test veritabanında, ``DATABASE_URL`` uygulama rolüyle):

    uv run python scripts/load_batch_1k.py --rows 1000 --latency-ms 0

Çıktı: süre, satır/sn, satır durumları, kota sayacı = taranan satır mı.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid

import httpx
from fastapi.testclient import TestClient

from aegis_api.main import create_app
from aegis_core.screening.yente import YenteClient

WORDS = [
    "Akdeniz",
    "Boğaziçi",
    "Çukurova",
    "Doruk",
    "Ege",
    "Fırat",
    "Güneş",
    "Hazar",
    "Ilgaz",
    "Kaçkar",
    "Lale",
    "Marmara",
    "Nil",
    "Ozan",
    "Pamuk",
    "Rüzgar",
    "Sakarya",
    "Toros",
]
KINDS = ["Tekstil", "Lojistik", "Gıda", "Enerji", "Yazılım", "Madencilik", "İnşaat", "Kimya"]


def _names(n: int) -> list[str]:
    out = []
    i = 0
    while len(out) < n:
        w = WORDS[i % len(WORDS)]
        k = KINDS[(i // len(WORDS)) % len(KINDS)]
        out.append(f"{w} {k} {uuid.uuid4().hex[:6].upper()} A.Ş.")
        i += 1
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=1000)
    ap.add_argument("--latency-ms", type=int, default=0)
    ap.add_argument(
        "--admin-url",
        default=None,
        help="Yük kiracısına kurumsal plan atamak için ayrıcalıklı DB adresi (pilot: 300)",
    )
    args = ap.parse_args()

    async def handler(request: httpx.Request) -> httpx.Response:
        if args.latency_ms:
            await asyncio.sleep(args.latency_ms / 1000)
        queries = json.loads(request.content)["queries"]
        return httpx.Response(
            200, json={"responses": {k: {"status": 200, "results": []} for k in queries}}
        )

    with TestClient(create_app()) as c:
        http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://yente")
        c.app.state.yente_client = YenteClient("http://yente", client=http)  # type: ignore[attr-defined]
        slug = f"yuk-{uuid.uuid4().hex[:8]}"
        email = f"u@{slug}.com"
        c.post(
            "/api/v1/auth/register",
            json={"org_name": slug, "org_slug": slug, "email": email, "password": "sifre-12345"},
        )
        if args.admin_url:
            from sqlalchemy import create_engine, text

            engine = create_engine(args.admin_url)
            with engine.begin() as conn:
                conn.execute(
                    text("UPDATE organization SET plan_code = 'kurumsal' WHERE slug = :s"),
                    {"s": slug},
                )
            engine.dispose()
        token = c.post(
            "/api/v1/auth/login", json={"email": email, "password": "sifre-12345"}
        ).json()["access_token"]
        h = {"Authorization": f"Bearer {token}"}
        body = ("Ad\r\n" + "".join(f"{n}\r\n" for n in _names(args.rows))).encode()
        t0 = time.perf_counter()
        batch = c.post(
            "/api/v1/batches",
            files={"file": ("yuk.csv", body, "text/csv")},
            data={"mapping": json.dumps({"name": "Ad"})},
            headers=h,
        ).json()
        t_create = time.perf_counter() - t0
        start = c.post(f"/api/v1/batches/{batch['id']}/start", headers=h)
        if start.status_code != 200:
            print("başlatılamadı:", start.status_code, start.json())
            return
        t1 = time.perf_counter()
        rounds = 0
        while True:
            r = c.post(
                f"/api/v1/batches/{batch['id']}/process", params={"limit": 100}, headers=h
            ).json()
            rounds += 1
            if r["remaining"] == 0:
                break
        t_process = time.perf_counter() - t1
        state = c.get(f"/api/v1/batches/{batch['id']}", headers=h).json()
        usage = c.get("/api/v1/billing/usage", headers=h).json()
        print(
            json.dumps(
                {
                    "rows": args.rows,
                    "latency_ms": args.latency_ms,
                    "create_s": round(t_create, 2),
                    "process_s": round(t_process, 2),
                    "rows_per_s": round(args.rows / t_process, 1),
                    "rounds": rounds,
                    "status": state["status"],
                    "counts": {k: v for k, v in state["counts"].items() if v},
                    "used_queries": usage["used_queries"],
                    "quota_matches_rows": usage["used_queries"] == state["counts"]["done"],
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
