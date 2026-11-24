"""Authentication, authorization and audit logging for private Kaviont access."""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

_AUDIT = logging.getLogger("kaviont.audit")
_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,80}$")
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _email_set(variable: str) -> set[str]:
    return {
        value.strip().lower()
        for value in os.getenv(variable, "").split(",")
        if value.strip()
    }


def _protected_path(path: str) -> bool:
    return (
        path == "/engineering"
        or path.startswith("/engineering/")
        or path == "/market"
        or path.startswith("/market/")
        or path.startswith("/v1/")
    )


def _audit(
    *,
    actor: str,
    role: str,
    mode: str,
    method: str,
    path: str,
    status: int,
    request_id: str,
) -> None:
    event: dict[str, Any] = {
        "event": "http_access",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor": actor,
        "role": role,
        "auth_mode": mode,
        "method": method,
        "path": path,
        "status": status,
        "request_id": request_id,
    }
    # Do not log query strings, request bodies, cookies, or authorization headers.
    _AUDIT.info(json.dumps(event, separators=(",", ":"), sort_keys=True))


async def platform_access_middleware(request: Request, call_next: Any) -> Response:
    """Trust Tailscale Serve identity headers only on the loopback-bound home stack."""

    mode = os.getenv("KAVIONT_AUTH_MODE", "disabled").strip().lower()
    path = request.url.path
    method = request.method.upper()
    supplied_id = request.headers.get("x-request-id", "")
    request_id = supplied_id if _REQUEST_ID.fullmatch(supplied_id) else uuid.uuid4().hex
    actor = "local"
    role = "local"

    if mode not in {"disabled", "tailscale"}:
        response = JSONResponse(
            {"detail": "Kaviont authentication mode is invalid."},
            status_code=503,
        )
        response.headers["X-Kaviont-Request-ID"] = request_id
        _audit(
            actor="anonymous", role="none", mode=mode, method=method,
            path=path, status=503, request_id=request_id,
        )
        return response

    if mode == "tailscale" and _protected_path(path):
        actor = request.headers.get("tailscale-user-login", "").strip().lower()
        if not actor or "@" not in actor:
            response = JSONResponse(
                {"detail": "Authentication required. Open Kaviont through your private Tailscale Serve URL."},
                status_code=401,
            )
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Kaviont-Request-ID"] = request_id
            _audit(
                actor="anonymous", role="none", mode=mode, method=method,
                path=path, status=401, request_id=request_id,
            )
            return response

        admins = _email_set("KAVIONT_ADMIN_USERS")
        readers = _email_set("KAVIONT_READER_USERS")
        role = "admin" if actor in admins else "reader"

        if readers and actor not in readers and actor not in admins:
            response = JSONResponse(
                {"detail": "Your Tailscale identity is not authorized for Kaviont."},
                status_code=403,
            )
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Kaviont-Request-ID"] = request_id
            _audit(
                actor=actor, role=role, mode=mode, method=method,
                path=path, status=403, request_id=request_id,
            )
            return response

        if method in _MUTATING_METHODS and role != "admin":
            response = JSONResponse(
                {"detail": "Administrator role required for this operation."},
                status_code=403,
            )
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Kaviont-Request-ID"] = request_id
            _audit(
                actor=actor, role=role, mode=mode, method=method,
                path=path, status=403, request_id=request_id,
            )
            return response

    request.state.kaviont_actor = actor
    request.state.kaviont_role = role
    request.state.kaviont_request_id = request_id
    response = await call_next(request)
    response.headers["X-Kaviont-Request-ID"] = request_id

    if mode == "tailscale" and _protected_path(path):
        response.headers["Cache-Control"] = "no-store"

    if path.startswith("/v1/") or _protected_path(path):
        _audit(
            actor=actor, role=role, mode=mode, method=method,
            path=path, status=response.status_code, request_id=request_id,
        )
    return response
