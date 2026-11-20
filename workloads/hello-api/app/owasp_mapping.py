"""Heuristic mappings from scanner metadata to OWASP Top 10:2025."""

from __future__ import annotations

import re
from collections.abc import Iterable

OWASP_2025_BY_CWE = {
    "CWE-22": "A01:2025 Broken Access Control",
    "CWE-284": "A01:2025 Broken Access Control",
    "CWE-285": "A01:2025 Broken Access Control",
    "CWE-862": "A01:2025 Broken Access Control",
    "CWE-863": "A01:2025 Broken Access Control",
    "CWE-918": "A01:2025 Broken Access Control",
    "CWE-16": "A02:2025 Security Misconfiguration",
    "CWE-2": "A02:2025 Security Misconfiguration",
    "CWE-611": "A02:2025 Security Misconfiguration",
    "CWE-1104": "A03:2025 Software Supply Chain Failures",
    "CWE-937": "A03:2025 Software Supply Chain Failures",
    "CWE-1035": "A03:2025 Software Supply Chain Failures",
    "CWE-327": "A04:2025 Cryptographic Failures",
    "CWE-328": "A04:2025 Cryptographic Failures",
    "CWE-330": "A04:2025 Cryptographic Failures",
    "CWE-916": "A04:2025 Cryptographic Failures",
    "CWE-78": "A05:2025 Injection",
    "CWE-79": "A05:2025 Injection",
    "CWE-89": "A05:2025 Injection",
    "CWE-77": "A05:2025 Injection",
    "CWE-94": "A05:2025 Injection",
    "CWE-287": "A07:2025 Authentication Failures",
    "CWE-306": "A07:2025 Authentication Failures",
    "CWE-307": "A07:2025 Authentication Failures",
    "CWE-345": "A08:2025 Software or Data Integrity Failures",
    "CWE-494": "A08:2025 Software or Data Integrity Failures",
    "CWE-502": "A08:2025 Software or Data Integrity Failures",
    "CWE-778": "A09:2025 Security Logging and Alerting Failures",
    "CWE-532": "A09:2025 Security Logging and Alerting Failures",
    "CWE-755": "A10:2025 Mishandling of Exceptional Conditions",
    "CWE-248": "A10:2025 Mishandling of Exceptional Conditions",
    "CWE-703": "A10:2025 Mishandling of Exceptional Conditions",
}


def extract_cwes(tags: Iterable[str]) -> list[str]:
    return sorted({
        match.group(0).upper()
        for tag in tags
        for match in re.finditer(r"CWE-\d+", str(tag), flags=re.IGNORECASE)
    })


def map_owasp_2025(tags: Iterable[str] = (), *, dependency: bool = False) -> str | None:
    """Return a heuristic category only when scanner metadata supports one."""
    if dependency:
        return "A03:2025 Software Supply Chain Failures"
    for cwe in extract_cwes(tags):
        if cwe in OWASP_2025_BY_CWE:
            return OWASP_2025_BY_CWE[cwe]
    return None
