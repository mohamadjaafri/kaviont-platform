#!/usr/bin/env python3
"""Exercise Alertmanager -> SMTP -> Mailpit email delivery end to end."""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


ALERTMANAGER_URL = os.getenv("ALERTMANAGER_URL", "http://127.0.0.1:9093").rstrip("/")
MAILPIT_URL = os.getenv("MAILPIT_URL", "http://127.0.0.1:8025").rstrip("/")
EXPECTED_RECIPIENT = os.getenv("ALERT_EMAIL_TO", "platform-ops@local.test")
TIMEOUT_SECONDS = max(15, int(os.getenv("ALERT_EMAIL_TIMEOUT_SECONDS", "45")))


def request_json(url: str, *, method: str = "GET", payload: object | None = None) -> object:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = Request(url, data=body, headers=headers, method=method)
    with urlopen(request, timeout=5) as response:
        raw = response.read()
        if not raw:
            return None
        return json.loads(raw.decode("utf-8"))


def field(value: dict, *names: str, default=None):
    for name in names:
        if name in value:
            return value[name]
    return default


def recipient_addresses(message: dict) -> set[str]:
    recipients = field(message, "To", "to", default=[]) or []
    addresses = set()
    for recipient in recipients:
        if isinstance(recipient, str):
            addresses.add(recipient.lower())
        elif isinstance(recipient, dict):
            address = field(recipient, "Address", "address", default="")
            if address:
                addresses.add(str(address).lower())
    return addresses


def wait_until_ready(deadline: float) -> None:
    checks = (
        f"{ALERTMANAGER_URL}/api/v2/status",
        f"{MAILPIT_URL}/api/v1/info",
    )
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            for endpoint in checks:
                request_json(endpoint)
            return
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(1)
    raise RuntimeError(f"Alertmanager or Mailpit did not become ready: {last_error}")


def find_delivered_message(marker: str) -> dict | None:
    response = request_json(f"{MAILPIT_URL}/api/v1/messages?start=0&limit=100")
    if not isinstance(response, dict):
        raise RuntimeError("Mailpit returned an unexpected messages response")

    messages = field(response, "messages", "Messages", default=[]) or []
    for summary in messages:
        if not isinstance(summary, dict):
            continue
        message_id = field(summary, "ID", "id")
        if not message_id:
            continue
        if EXPECTED_RECIPIENT.lower() not in recipient_addresses(summary):
            continue

        detail = request_json(f"{MAILPIT_URL}/api/v1/message/{quote(str(message_id), safe='')}")
        if not isinstance(detail, dict):
            continue
        content = " ".join(
            str(field(detail, name, name.lower(), default="") or "")
            for name in ("Subject", "Text", "HTML")
        )
        if marker in content:
            return detail
    return None


def main() -> int:
    marker = f"kaviont-email-smoke-{uuid.uuid4().hex}"
    now = datetime.now(timezone.utc)
    alert_name = f"KaviontEmailDeliverySmokeTest_{uuid.uuid4().hex[:8]}"
    alert = {
        "labels": {
            "alertname": alert_name,
            "severity": "warning",
            "service": "kaviont",
        },
        "annotations": {
            "summary": f"Kaviont email delivery test {marker}",
            "description": f"Automated end-to-end notification check. Marker: {marker}",
        },
        "startsAt": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "endsAt": (now + timedelta(minutes=2)).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "generatorURL": "https://github.com/mohamadjaafri/kaviont-platform",
    }

    deadline = time.monotonic() + TIMEOUT_SECONDS
    try:
        wait_until_ready(deadline)
        request_json(f"{ALERTMANAGER_URL}/api/v2/alerts", method="POST", payload=[alert])

        while time.monotonic() < deadline:
            message = find_delivered_message(marker)
            if message is not None:
                actual_recipients = ", ".join(sorted(recipient_addresses(message)))
                subject = field(message, "Subject", "subject", default="(no subject)")
                print(
                    "Email delivery verified: "
                    f"subject={subject!r}, recipients={actual_recipients}"
                )
                return 0
            time.sleep(2)
    except (HTTPError, URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"Email delivery check failed: {exc}", file=sys.stderr)
        return 1

    print(
        "Email delivery check timed out. Alertmanager accepted the synthetic alert, "
        f"but Mailpit did not receive it at {EXPECTED_RECIPIENT}. "
        "Inspect: docker compose --profile observability logs alertmanager mailpit",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
