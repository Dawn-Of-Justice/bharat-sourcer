"""Transport-level request guards that run before routing and body parsing."""

import json
import re

TOO_LARGE = json.dumps(
    {"error": {"code": "BODY_TOO_LARGE", "message": "Request body is too large"}}
).encode()


async def reject_too_large(send) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(TOO_LARGE)).encode()),
                (b"connection", b"close"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": TOO_LARGE})


class BodyLimit:
    """ASGI middleware refusing request bodies above a byte limit with 413.

    A declared Content-Length is checked before anything is read; streamed (chunked or
    under-declared) bodies are counted as they arrive, the route sees an empty final chunk
    and its response is replaced by the 413. `overrides` maps full-match path patterns to
    their own limits (the parts-bin scan photo).
    """

    def __init__(self, app, limit: int, overrides: tuple[tuple[str, int], ...] = ()):
        self.app, self.limit = app, limit
        self.overrides = [(re.compile(pattern), size) for pattern, size in overrides]

    def limit_for(self, path: str) -> int:
        return next(
            (size for pattern, size in self.overrides if pattern.fullmatch(path)), self.limit
        )

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self.limit_for(scope.get("path", ""))
        for name, value in scope.get("headers", []):
            if name.lower() == b"content-length":
                try:
                    declared = int(value)
                except ValueError:
                    declared = limit + 1
                if declared > limit:
                    await reject_too_large(send)
                    return
        received, exceeded, started, replaced = 0, False, False, False

        async def counted_receive():
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request" and not exceeded:
                received += len(message.get("body", b""))
                if received > limit:
                    exceeded = True
                    return {"type": "http.request", "body": b"", "more_body": False}
            return message

        async def guarded_send(message):
            nonlocal started, replaced
            if message["type"] == "http.response.start":
                if exceeded and not started:
                    started = replaced = True
                    await reject_too_large(send)
                    return
                started = True
            if replaced:
                return
            await send(message)

        await self.app(scope, counted_receive, guarded_send)
