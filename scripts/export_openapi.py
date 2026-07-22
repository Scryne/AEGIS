"""OpenAPI şemasını ``docs/openapi.json``'a yazar (sözleşme-drift kapısının kaynağı).

CI, bu script'i çalıştırıp ``git diff --exit-code`` ile şemanın commit'lenenle aynı
olduğunu doğrular; API yüzeyi değişince şema yeniden üretilip commit'lenmelidir.
"""

from __future__ import annotations

import json
from pathlib import Path

from aegis_api.main import create_app

OUTPUT = Path(__file__).resolve().parent.parent / "docs" / "openapi.json"


def main() -> None:
    """Uygulamanın OpenAPI şemasını deterministik biçimde diske yazar."""
    app = create_app()
    schema = app.openapi()
    OUTPUT.write_text(
        json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"OpenAPI şeması yazıldı: {OUTPUT}")


if __name__ == "__main__":
    main()
