"""Optional local log of which capability was used and when. Off by default; nothing leaves the computer.

It records the capability name, the date and the outcome code. It never records arguments, paths, model,
project or test names. Turn it on with VDC_NAVIS_LAB_USAGE_LOG=1; the file is usage.log in the data folder.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone

from .paths import home

ENV = "VDC_NAVIS_LAB_USAGE_LOG"
_LOCK = threading.Lock()


def enabled() -> bool:
    return os.environ.get(ENV, "").lower() in ("1", "true", "yes")


class UsageLog:
    def record(self, capability: str, outcome: str) -> None:
        if not enabled():
            return
        line = json.dumps({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                           "capability": capability, "outcome": outcome}, ensure_ascii=False)
        try:
            with _LOCK, open(home() / "usage.log", "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass  # a log that cannot be written must never break a tool

    @staticmethod
    def path() -> str:
        return str(home() / "usage.log")
