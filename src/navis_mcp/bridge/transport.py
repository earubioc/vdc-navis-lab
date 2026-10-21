"""Transports: a named pipe on Windows (the real add-in) and loopback TCP (simulator, development).

A named pipe is the default for the real add-in because it has no port to find or squat, is
reachable only by the owning user through its ACL, and cannot be touched by a web page. TCP exists
so the whole stack can be exercised on any OS against the simulator.
"""

from __future__ import annotations

import json
import os
import socket
import sys
from dataclasses import dataclass
from pathlib import Path

from ..paths import home
from .protocol import MAX_LINE, TIMEOUT, UNREACHABLE, BridgeError

PIPE_PREFIX = "navis-mcp."
ENV_ENDPOINT = "NAVIS_MCP_ENDPOINT"


@dataclass(frozen=True, slots=True)
class Endpoint:
    scheme: str  # "pipe" | "tcp"
    target: str  # pipe name, or host:port

    def __str__(self) -> str:
        return f"{self.scheme}://{self.target}"

    @classmethod
    def parse(cls, text: str) -> "Endpoint":
        scheme, sep, target = text.strip().partition("://")
        if not sep or scheme not in ("pipe", "tcp") or not target:
            raise BridgeError(UNREACHABLE, f"invalid endpoint {text!r}", "use pipe://NAME or tcp://127.0.0.1:PORT")
        if scheme == "tcp" and not target.startswith(("127.0.0.1:", "localhost:")):
            raise BridgeError(UNREACHABLE, "TCP endpoints must be loopback", "use tcp://127.0.0.1:PORT")
        return cls(scheme, target)


class _Conn:
    def __init__(self) -> None:
        self._buf = b""

    def _recv(self, n: int) -> bytes:  # pragma: no cover - abstract
        raise NotImplementedError

    def send(self, data: bytes) -> None:  # pragma: no cover - abstract
        raise NotImplementedError

    def close(self) -> None:  # pragma: no cover - abstract
        raise NotImplementedError

    def read_line(self) -> bytes:
        while b"\n" not in self._buf:
            chunk = self._recv(65536)
            if not chunk:
                raise BridgeError(UNREACHABLE, "connection closed before a full response arrived")
            self._buf += chunk
            if len(self._buf) > MAX_LINE:
                raise BridgeError(UNREACHABLE, "response exceeds the 64 MB limit")
        line, _, self._buf = self._buf.partition(b"\n")
        return line


class _Tcp(_Conn):
    def __init__(self, host: str, port: int, timeout: float) -> None:
        super().__init__()
        try:
            self._s = socket.create_connection((host, port), timeout=timeout)
        except OSError as exc:
            raise BridgeError(UNREACHABLE, f"cannot connect to {host}:{port}: {exc.strerror or exc}") from None
        self._s.settimeout(timeout)

    def _recv(self, n: int) -> bytes:
        try:
            return self._s.recv(n)
        except socket.timeout:
            raise BridgeError(TIMEOUT, "the add-in did not answer in time",
                              "long operations run as jobs: poll with nw_job") from None
        except OSError as exc:
            raise BridgeError(UNREACHABLE, f"connection error: {exc.strerror or exc}") from None

    def send(self, data: bytes) -> None:
        try:
            self._s.sendall(data)
        except OSError as exc:
            raise BridgeError(UNREACHABLE, f"connection error: {exc.strerror or exc}") from None

    def close(self) -> None:
        try:
            self._s.close()
        except OSError:
            pass


class _Pipe(_Conn):  # Windows only; not exercised by the automated tests (see docs/ARCHITECTURE.md)
    def __init__(self, name: str) -> None:
        super().__init__()
        if sys.platform != "win32":
            raise BridgeError(UNREACHABLE, "named pipes are only available on Windows")
        try:
            self._f = open(rf"\\.\pipe\{name}", "r+b", buffering=0)
        except OSError as exc:
            raise BridgeError(UNREACHABLE, f"cannot open pipe {name}: {exc.strerror or exc}") from None

    def _recv(self, n: int) -> bytes:
        try:
            return self._f.read(n)
        except OSError as exc:
            raise BridgeError(UNREACHABLE, f"pipe error: {exc.strerror or exc}") from None

    def send(self, data: bytes) -> None:
        try:
            self._f.write(data)
        except OSError as exc:
            raise BridgeError(UNREACHABLE, f"pipe error: {exc.strerror or exc}") from None

    def close(self) -> None:
        try:
            self._f.close()
        except OSError:
            pass


def connect(ep: Endpoint, timeout: float) -> _Conn:
    if ep.scheme == "pipe":
        return _Pipe(ep.target)
    host, _, port = ep.target.rpartition(":")
    return _Tcp(host, int(port), timeout)


def registry_dir() -> Path:
    d = home() / "endpoints"
    d.mkdir(parents=True, exist_ok=True)
    return d


def discover() -> list[Endpoint]:
    """Where could a Navisworks add-in be listening? Environment first, then the platform's own way."""
    raw = os.environ.get(ENV_ENDPOINT, "")
    if raw.strip():
        return [Endpoint.parse(p) for p in raw.split(",") if p.strip()]
    found: list[Endpoint] = []
    if sys.platform == "win32":
        try:
            names = os.listdir(r"\\.\pipe")
        except OSError:
            names = []
        found += [Endpoint("pipe", n) for n in sorted(names) if n.startswith(PIPE_PREFIX)]
    for f in sorted(registry_dir().glob("*.json")):  # simulators and development instances
        try:
            info = json.loads(f.read_text(encoding="utf-8"))
            ep = Endpoint.parse(info["endpoint"])
            pid = int(info.get("pid", 0))
            if pid and sys.platform != "win32":
                os.kill(pid, 0)
            found.append(ep)
        except (OSError, ValueError, KeyError, BridgeError):
            try:
                f.unlink()  # stale entry
            except OSError:
                pass
    return found
