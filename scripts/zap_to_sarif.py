#!/usr/bin/env python3
"""Convert the ZAP Baseline JSON report into SARIF 2.1.0."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def level_for(risk: Any) -> str:
    try:
        value = int(risk)
    except (TypeError, ValueError):
        value = 0
    return "error" if value >= 3 else "warning" if value == 2 else "note"


def convert(payload: dict[str, Any]) -> dict[str, Any]:
    rules: dict[str, dict[str, Any]] = {}
    results: list[dict[str, Any]] = []
    for site in payload.get("site", []):
        for alert in site.get("alerts", []):
            rule_id = str(alert.get("pluginid") or alert.get("alertRef") or alert.get("name") or "ZAP-ALERT")
            title = str(alert.get("alert") or alert.get("name") or rule_id)
            description = str(alert.get("desc") or alert.get("description") or title)
            rules.setdefault(rule_id, {
                "id": rule_id,
                "shortDescription": {"text": title[:240]},
                "fullDescription": {"text": description[:4000]},
            })
            instances = alert.get("instances") or [{}]
            for instance in instances:
                uri = instance.get("uri") or site.get("@name")
                result: dict[str, Any] = {
                    "ruleId": rule_id,
                    "level": level_for(alert.get("riskcode")),
                    "message": {"text": f"{title}: {description[:1500]}"},
                    "properties": {
                        "riskcode": alert.get("riskcode"),
                        "confidence": alert.get("confidence"),
                        "cweid": alert.get("cweid"),
                        "wascid": alert.get("wascid"),
                        "solution": alert.get("solution"),
                    },
                }
                if uri:
                    result["locations"] = [{
                        "physicalLocation": {
                            "artifactLocation": {"uri": str(uri)}
                        }
                    }]
                results.append(result)
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {"name": "OWASP ZAP Baseline", "informationUri": "https://www.zaproxy.org/docs/docker/baseline-scan/", "rules": list(rules.values())}},
            "results": results,
        }],
    }


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: zap_to_sarif.py INPUT.json OUTPUT.sarif", file=sys.stderr)
        return 2
    source, destination = map(Path, sys.argv[1:])
    payload = json.loads(source.read_text(encoding="utf-8"))
    destination.write_text(json.dumps(convert(payload), indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
