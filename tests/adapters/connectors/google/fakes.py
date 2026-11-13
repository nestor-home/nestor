"""Google's errors, as its APIs answer them."""

import httpx


def error(status: int, reason: str, message: str) -> httpx.Response:
    body = {"error": {"code": status, "message": message, "errors": [{"domain": "global", "reason": reason}]}}
    return httpx.Response(status, json=body)
