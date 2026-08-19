"""Best-effort off-device webhook notifications for operational incidents."""
from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def send_webhook(url: str, event: dict[str, Any], timeout: int = 5) -> bool:
    if not url:
        return False
    request = urllib.request.Request(
        url,
        data=json.dumps(event, sort_keys=True).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return 200 <= response.status < 300
    except (OSError, ValueError):
        return False


def notify_state_change(
    *,
    url: str,
    state_path: Path,
    station_id: str,
    conditions: list[str],
    detail: dict[str, Any],
    timeout: int = 5,
) -> bool:
    signature = sorted(set(conditions))
    previous: list[str] = []
    try:
        previous = json.loads(state_path.read_text()).get("conditions", [])
    except (OSError, ValueError, AttributeError):
        pass
    if signature == previous:
        return False
    event = {
        "schema_version": 1,
        "station_id": station_id,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "conditions": signature,
        "status": "recovered" if not signature else "alert",
        "detail": detail,
    }
    delivered = send_webhook(url, event, timeout)
    if delivered:
        state_path.write_text(json.dumps(event, sort_keys=True) + "\n")
        state_path.chmod(0o640)
    return delivered
