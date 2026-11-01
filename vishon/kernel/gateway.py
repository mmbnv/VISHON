"""G_b: the private sensorimotor gateway.

G_b is the only route from the system to what is not the system. What comes
back through it is *raw*: a status code, a content type, the bytes, their
digest, the final URL, and an error string if the request failed. Nothing
else.

There is no parser here, no extractor, no summariser, no example, no
template, no "try this next". If the system wants meaning out of a response,
it has to produce that meaning itself (I4). That is the entire design
constraint on this module, and it is why the module is so small.

Isolation (I9)
--------------
``observe`` accepts a URL string. It refuses anything that is not a plain
string, in particular an ``AuthorityToken``: the gateway must not become a
laundering route between the system and the father's key. It holds no
reference to A_P, B, V_P or M. It cannot read or write any of them.

Network policy -- which hosts may be reached, how fast, how many bytes -- is
father-owned and bound by keyed digest, exactly as the boundary's policy is.
"""

from __future__ import annotations

import hashlib
import hmac
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Iterable


class GatewayError(RuntimeError):
    """A gateway request was malformed or refused."""


def _keyed_digest(secret: bytes) -> bytes:
    return hmac.new(secret, b"vishon.gateway.policy", "sha256").digest()


@dataclass(frozen=True)
class Observation:
    """What reality returned. Raw, uninterpreted."""

    url: str
    final_url: str
    status: int
    content_type: str
    bytes: bytes
    sha256: str
    elapsed_ms: int
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and 200 <= self.status < 400

    @property
    def length(self) -> int:
        return len(self.bytes)

    def describe(self) -> str:
        if self.error:
            return f"{self.url} -> error {self.error!r}"
        return f"{self.url} -> {self.status} {self.content_type} {self.length}B"


@dataclass(frozen=True)
class _Fetch:
    """What a transport returns before any interpretation."""

    body: bytes
    status: int
    content_type: str
    final_url: str


class Gateway:
    """G_b: raw observation of reality, and nothing more."""

    def __init__(
        self,
        *,
        allowed_domains: Iterable[str] = (),
        allow_all: bool = False,
        max_bytes: int = 262_144,
        min_interval_s: float = 0.5,
        timeout_s: float = 10.0,
        user_agent: str = "vishon-gateway/1",
        transport: "Callable[[str], _Fetch] | None" = None,
    ) -> None:
        self._domains: frozenset[str] = frozenset(d.lower() for d in allowed_domains)
        self._allow_all = allow_all
        self._max_bytes = max_bytes
        self._min_interval = min_interval_s
        self._timeout = timeout_s
        self._user_agent = user_agent
        # The transport is a seam: the default reaches the network, and a test
        # can substitute one that does not. Swapping it changes nothing about
        # what the gateway does with the result, which is the point.
        self._transport = transport
        self._last_request = 0.0
        self._key: bytes | None = None
        self._observations: int = 0
        self._refused: int = 0

    # -- father-owned policy --------------------------------------------

    def bind_authority(self, token: "Any") -> None:
        secret = getattr(token, "_secret", None)
        if not isinstance(secret, (bytes, bytearray)) or len(secret) < 16:
            raise GatewayError("a token must carry at least 16 bytes of secret")
        self._key = _keyed_digest(bytes(secret))

    def configure(self, token: "Any", **changes: Any) -> None:
        """Change the network policy. Requires P's token."""

        secret = getattr(token, "_secret", None)
        if self._key is None:
            raise GatewayError("gateway has no bound authority (I9)")
        if not isinstance(secret, (bytes, bytearray)) or not hmac.compare_digest(
            _keyed_digest(bytes(secret)), self._key
        ):
            raise GatewayError("the gateway policy is owned by P alone (I9)")
        if "allowed_domains" in changes:
            self._domains = frozenset(str(d).lower() for d in changes["allowed_domains"])
        if "allow_all" in changes:
            self._allow_all = bool(changes["allow_all"])
        if "max_bytes" in changes:
            self._max_bytes = max(1, int(changes["max_bytes"]))
        if "min_interval_s" in changes:
            self._min_interval = max(0.0, float(changes["min_interval_s"]))

    def policy(self) -> dict[str, Any]:
        return {
            "allowed_domains": tuple(sorted(self._domains)),
            "allow_all": self._allow_all,
            "max_bytes": self._max_bytes,
            "min_interval_s": self._min_interval,
        }

    @property
    def stats(self) -> dict[str, int]:
        return {"observations": self._observations, "refused": self._refused}

    # -- the one operation ----------------------------------------------

    def observe(self, url: Any) -> Observation:
        """Fetch a URL and return what came back, uninterpreted."""

        if not isinstance(url, str):
            # This is the I9 chokepoint: a token, a boundary, a gateway, a
            # modification -- anything that is not a plain URL string -- is
            # refused rather than passed along.
            self._refused += 1
            raise GatewayError(
                "the gateway accepts a URL string only; it is not a route to "
                "the father's authority (I9)"
            )

        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            self._refused += 1
            raise GatewayError(f"scheme {parsed.scheme!r} is not permitted")
        host = (parsed.hostname or "").lower()
        if not self._allow_all and host not in self._domains:
            self._refused += 1
            raise GatewayError(f"host {host!r} is not on the gateway allowlist")

        self._throttle()
        started = time.monotonic()
        if self._transport is None:
            result = self._fetch_over_network(url)
        else:
            result = self._transport(url)
        elapsed = int((time.monotonic() - started) * 1000)

        if isinstance(result, _Fetch):
            body, status, content_type, final_url, error = (
                result.body,
                result.status,
                result.content_type,
                result.final_url,
                "",
            )
        else:
            body, status, content_type, final_url, error = result

        self._observations += 1
        return Observation(
            url=url,
            final_url=final_url,
            status=status,
            content_type=content_type,
            bytes=body,
            sha256=hashlib.sha256(body).hexdigest(),
            elapsed_ms=elapsed,
            error=error,
        )

    def _fetch_over_network(self, url: str):
        """The default transport. Reaches the network and interprets nothing."""

        request = urllib.request.Request(url, headers={"User-Agent": self._user_agent})
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                return _Fetch(
                    body=response.read(self._max_bytes),
                    status=int(response.status),
                    content_type=str(response.headers.get("Content-Type", "")),
                    final_url=str(response.geturl()),
                )
        except urllib.error.HTTPError as exc:
            headers = exc.headers
            return (
                b"",
                int(exc.code),
                str(headers.get("Content-Type", "")) if headers else "",
                url,
                f"HTTPError {exc.code}",
            )
        except BaseException as exc:
            # A transport failure is a fact about reality, not a failure of the
            # gateway. It comes back as an observation with an error and an
            # empty body; whether that counts as contact is not G_b's call.
            return (b"", 0, "", url, f"{type(exc).__name__}: {exc}")

    def _throttle(self) -> None:
        now = time.monotonic()
        wait = self._min_interval - (now - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()
