"""OpenAPI şemasından Postman koleksiyonu üretir (E3.4): ``docs/api/aegis.postman_collection.json``.

``docs/openapi.json`` güncel olmalıdır (``scripts/export_openapi.py``). Koleksiyon iki değişken
kullanır: ``baseUrl`` (ör. ``https://aegis.example.com/api/v1``) ve ``apiKey``; kimlik doğrulama
``X-API-Key`` başlığıyla yapılır. Çıktı deterministiktir (CI'da sürüklenme denetlenebilir).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "openapi.json"
OUTPUT = ROOT / "docs" / "api" / "aegis.postman_collection.json"
PREFIX = "/api/v1"
METHODS = ("get", "post", "put", "patch", "delete")


def _example(schema: dict[str, Any], components: dict[str, Any], depth: int = 0) -> Any:
    if depth > 4:
        return None
    if "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[-1]
        return _example(components.get(name, {}), components, depth + 1)
    if "anyOf" in schema:
        options = [s for s in schema["anyOf"] if s.get("type") != "null"]
        return _example(options[0], components, depth + 1) if options else None
    if "default" in schema:
        return schema["default"]
    kind = schema.get("type")
    if kind == "object":
        props = schema.get("properties", {})
        required = schema.get("required", list(props))
        return {k: _example(v, components, depth + 1) for k, v in props.items() if k in required}
    if kind == "array":
        return [_example(schema.get("items", {}), components, depth + 1)]
    if kind == "integer":
        return 0
    if kind == "number":
        return 0.0
    if kind == "boolean":
        return False
    if schema.get("format") == "uuid":
        return "00000000-0000-0000-0000-000000000000"
    return ""


def build(spec: dict[str, Any]) -> dict[str, Any]:
    components = spec.get("components", {}).get("schemas", {})
    folders: dict[str, list[dict[str, Any]]] = {}
    for path, item in sorted(spec["paths"].items()):
        if not path.startswith(PREFIX) or path.startswith(f"{PREFIX}/auth"):
            continue
        for method in METHODS:
            op = item.get(method)
            if op is None:
                continue
            rel = path[len(PREFIX) :]
            segments = [
                s if not s.startswith("{") else ":" + s[1:-1] for s in rel.strip("/").split("/")
            ]
            request: dict[str, Any] = {
                "method": method.upper(),
                "header": [{"key": "X-API-Key", "value": "{{apiKey}}"}],
                "url": {
                    "raw": "{{baseUrl}}/" + "/".join(segments),
                    "host": ["{{baseUrl}}"],
                    "path": segments,
                },
                "description": (op.get("description") or op.get("summary") or "").strip(),
            }
            body = op.get("requestBody", {}).get("content", {})
            if "application/json" in body:
                example = _example(body["application/json"].get("schema", {}), components)
                request["header"].append({"key": "Content-Type", "value": "application/json"})
                request["body"] = {
                    "mode": "raw",
                    "raw": json.dumps(example, ensure_ascii=False, indent=2),
                }
            elif "multipart/form-data" in body:
                request["body"] = {
                    "mode": "formdata",
                    "formdata": [{"key": "file", "type": "file", "src": ""}],
                }
            tag = (op.get("tags") or ["diğer"])[0]
            folders.setdefault(tag, []).append(
                {"name": op.get("summary") or f"{method.upper()} {rel}", "request": request}
            )
    return {
        "info": {
            "name": "AEGIS API v1",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            "description": "AEGIS genel API'si. Hızlı başlangıç: docs/api/README.md",
        },
        "variable": [
            {"key": "baseUrl", "value": "https://aegis.example.com/api/v1"},
            {"key": "apiKey", "value": ""},
        ],
        "item": [{"name": tag, "item": items} for tag, items in sorted(folders.items())],
    }


def main() -> None:
    spec = json.loads(SOURCE.read_text(encoding="utf-8"))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(build(spec), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"Postman koleksiyonu yazıldı: {OUTPUT}")


if __name__ == "__main__":
    main()
