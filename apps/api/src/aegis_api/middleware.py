"""İstek bağlamı middleware'i: request_id üretimi + loglama bağlamı.

Saf ASGI middleware'dir (BaseHTTPMiddleware değil): BaseHTTPMiddleware,
``http.disconnect`` mesajının iç uygulamaya akışını bozarak uzun ömürlü stream'lerin
istemci kopuşunu görmesini engeller.
"""

from __future__ import annotations

import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from aegis_core.logging import request_id_var

REQUEST_ID_HEADER = "X-Request-ID"


class RequestContextMiddleware:
    """Her istek için bir ``request_id`` üretir/yayar ve log bağlamına bağlar."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = Headers(scope=scope).get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        token = request_id_var.set(request_id)

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            request_id_var.reset(token)
