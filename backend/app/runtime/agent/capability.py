"""Short-lived scoped capabilities for one agent run.

The scheduler issues a capability after it binds a session and generation; the
CLI presents it to the internal model/tool gateway. A capability is bound to
user, session, run, attempt and runtime generation, so a stale or reused token
cannot act on a newer run. No provider credentials reach the CLI.
"""

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass

from app.core.config import get_settings

VERSION = 1


class CapabilityError(Exception):
    pass


@dataclass(frozen=True)
class Capability:
    user_id: str
    session_id: str
    run_id: str
    attempt: int
    runtime_generation: int
    expires_at: int


def _secret() -> bytes:
    settings = get_settings()
    material = f"{settings.auth_token_pepper}|agent-capability|v{VERSION}"
    return hashlib.sha256(material.encode()).digest()


def _encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def issue(
    *,
    user_id: str,
    session_id: str,
    run_id: str,
    attempt: int,
    runtime_generation: int,
    ttl_seconds: int | None = None,
) -> str:
    ttl = ttl_seconds or get_settings().agent_capability_ttl_seconds
    payload = {
        "v": VERSION,
        "sub": user_id,
        "sid": session_id,
        "rid": run_id,
        "att": attempt,
        "gen": runtime_generation,
        "exp": int(time.time()) + ttl,
    }
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    signature = hmac.new(_secret(), body, hashlib.sha256).digest()
    return f"{_encode(body)}.{_encode(signature)}"


def verify(token: str) -> Capability:
    try:
        body_part, signature_part = token.split(".", 1)
        body = _decode(body_part)
        signature = _decode(signature_part)
    except (ValueError, TypeError) as exc:
        raise CapabilityError("Malformed capability") from exc
    expected = hmac.new(_secret(), body, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected):
        raise CapabilityError("Capability signature mismatch")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise CapabilityError("Capability payload is not JSON") from exc
    if payload.get("v") != VERSION:
        raise CapabilityError("Unsupported capability version")
    if int(payload.get("exp", 0)) <= int(time.time()):
        raise CapabilityError("Capability expired")
    try:
        return Capability(
            user_id=str(payload["sub"]),
            session_id=str(payload["sid"]),
            run_id=str(payload["rid"]),
            attempt=int(payload["att"]),
            runtime_generation=int(payload["gen"]),
            expires_at=int(payload["exp"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CapabilityError("Capability is missing required claims") from exc
