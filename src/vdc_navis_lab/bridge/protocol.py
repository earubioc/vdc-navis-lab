"""Wire protocol between the MCP server and the Navisworks add-in.

JSON-RPC 2.0, one JSON object per line (UTF-8, newline-terminated), one request per
connection. See docs/PROTOCOL.md for the method catalogue.
"""

from __future__ import annotations

import itertools
import json
from typing import Any

API_VERSION = 1
MAX_LINE = 64 * 1024 * 1024

# error codes carried in error.data.code
STALE_DOCUMENT = "stale_document"
BUSY = "busy"
NOT_FOUND = "not_found"
UNSUPPORTED = "unsupported"
INVALID_PARAMS = "invalid_params"
NO_DOCUMENT = "no_document"
NO_INSTANCE = "no_instance"
AMBIGUOUS = "ambiguous_instance"
UNREACHABLE = "unreachable"
TIMEOUT = "timeout"
INTERNAL = "internal"

_ids = itertools.count(1)


class BridgeError(RuntimeError):
    def __init__(self, code: str, message: str, hint: str = "", data: Any = None) -> None:
        super().__init__(message)
        self.code, self.message, self.hint, self.data = code, message, hint, data

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"error": self.code, "detail": self.message}
        if self.hint:
            out["hint"] = self.hint
        if self.data is not None:
            out["data"] = self.data
        return out


def encode_request(method: str, params: dict[str, Any] | None) -> bytes:
    body = {"jsonrpc": "2.0", "id": next(_ids), "method": method, "params": params or {}}
    return (json.dumps(body, separators=(",", ":")) + "\n").encode("utf-8")


def decode_response(line: bytes) -> Any:
    try:
        msg = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise BridgeError(INTERNAL, "the add-in sent an unreadable response") from None
    if not isinstance(msg, dict):
        raise BridgeError(INTERNAL, "the add-in sent a malformed response")
    err = msg.get("error")
    if err:
        data = err.get("data") or {}
        raise BridgeError(str(data.get("code") or INTERNAL), str(err.get("message", "add-in error")),
                          str(data.get("hint", "")), data.get("detail"))
    return msg.get("result")


def encode_result(request_id: Any, result: Any) -> bytes:
    return (json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}, separators=(",", ":")) + "\n").encode("utf-8")


def encode_error(request_id: Any, code: str, message: str, hint: str = "", detail: Any = None) -> bytes:
    data: dict[str, Any] = {"code": code}
    if hint:
        data["hint"] = hint
    if detail is not None:
        data["detail"] = detail
    body = {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32000, "message": message, "data": data}}
    return (json.dumps(body, separators=(",", ":")) + "\n").encode("utf-8")
