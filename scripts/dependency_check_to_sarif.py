#!/usr/bin/env python3
"""Convert an OWASP Dependency-Check JSON report into SARIF 2.1.0."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def level_for(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"critical", "high"}:
        return "error"
    if normalized in {"medium", "moderate"}:
        return "warning"
    return "note"


def convert(payload: dict[str, Any]) -> dict[str, Any]:
    rules: dict[str, dict[str, Any]] = {}
    results: list[dict[str, Any]] = []
    for dependency in payload.get("dependencies", []):
        filename = dependency.get("fileName") or dependency.get("filePath") or "dependency"
        for vulnerability in dependency.get("vulnerabilities", []):
            rule_id = str(vulnerability.get("name") or vulnerability.get("source") or "DEPENDENCY-CVE")
            severity = str(vulnerability.get("severity") or "unknown")
            description = str(vulnerability.get("description") or vulnerability.get("name") or "Vulnerable dependency")
            cvss = vulnerability.get("cvssv3") or {}
            score = cvss.get("baseScore")
            rules.setdefault(rule_id, {
                "id": rule_id,
                "shortDescription": {"text": description[:240]},
                "fullDescription": {"text": description[:4000]},
                "properties": {"security-severity": str(score or "")},
            })
            result: dict[str, Any] = {
                "ruleId": rule_id,
                "level": level_for(severity),
                "message": {"text": f"{filename}: {description[:2000]}"},
                "properties": {
                    "severity": severity,
                    "package": filename,
                    "recommendation": "Upgrade the affected dependency to a patched release and regenerate the lockfile.",
                },
            }
            if filename:
                result["locations"] = [{
                    "physicalLocation": {
                        "artifactLocation": {"uri": str(filename).replace("\\", "/")}
                    }
                }]
            results.append(result)
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {"name": "OWASP Dependency-Check", "informationUri": "https://owasp.org/www-project-dependency-check/", "rules": list(rules.values())}},
            "results": results,
        }],
    }


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: dependency_check_to_sarif.py INPUT.json OUTPUT.sarif", file=sys.stderr)
        return 2
    source, destination = map(Path, sys.argv[1:])
    payload = json.loads(source.read_text(encoding="utf-8"))
    destination.write_text(json.dumps(convert(payload), indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
