"""The one error type a tool shows to the user. Plugins import it from here."""

from __future__ import annotations

from typing import Any


class ToolFault(Exception):
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
