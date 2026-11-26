"""Bound write-body memory before JSON parsing (including chunked requests).

A reverse proxy must still enforce connection, request-rate and read-time limits.
"""
from starlette.responses import JSONResponse

MAX_WRITE_BYTES = 64 * 1024
MAX_SIGNED_BYTES = 16 * 1024


class WriteBodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in {"POST", "PUT", "PATCH", "DELETE"}:
            return await self.app(scope, receive, send)

        limit = MAX_SIGNED_BYTES if scope["path"] == "/api/webhooks/signed" else MAX_WRITE_BYTES

        async def reject(status, detail):
            await JSONResponse(
                {"detail": detail}, status_code=status,
                headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
            )(scope, receive, send)

        lengths = [value for name, value in scope.get("headers", []) if name.lower() == b"content-length"]
        if lengths:
            if len(lengths) != 1 or not lengths[0].isdigit():
                return await reject(400, "Invalid Content-Length")
            # Avoid converting arbitrarily long numeric strings.
            declared = lengths[0].lstrip(b"0") or b"0"
            if len(declared) > len(str(limit)) or int(declared) > limit:
                return await reject(413, "Request body too large")

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > limit:
                return await reject(413, "Request body too large")
            body.extend(chunk)
            if not message.get("more_body", False):
                break

        # Preserve original byte order and content for signature verification.
        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        return await self.app(scope, replay, send)
