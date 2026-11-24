"""Actionable, conservative remediation hints for scanner findings."""

from __future__ import annotations

_CWE_REMEDIATIONS = {
    "CWE-22": "Canonicalize and validate paths against an explicit allowed root. Reject traversal segments and avoid building filesystem paths from untrusted input.",
    "CWE-78": "Avoid shell execution with user-controlled input. Prefer a library API or pass a fixed executable and validated argument array without a shell.",
    "CWE-79": "Use context-aware output encoding and safe templating. Do not insert untrusted values into HTML or JavaScript with string concatenation.",
    "CWE-89": "Use parameterized SQL queries or prepared statements. Never concatenate untrusted input into SQL text.",
    "CWE-287": "Verify identity using a supported authentication flow, validate tokens and issuer/audience claims, and enforce session expiry and revocation.",
    "CWE-352": "Protect state-changing requests with CSRF tokens or an equivalent origin-bound mechanism and configure secure SameSite cookies.",
    "CWE-502": "Avoid deserializing untrusted object graphs. Use a strict data schema, disable polymorphic type resolution, and validate inputs.",
    "CWE-611": "Disable external entity resolution and DTD processing in XML parsers. Reject external references unless explicitly required.",
    "CWE-798": "Remove embedded credentials, rotate any exposed secret, and load secrets from a managed secret store at runtime.",
    "CWE-862": "Enforce authorization on the server for every requested resource and action. Apply least-privilege checks rather than relying on UI visibility.",
    "CWE-918": "Prevent SSRF with destination allowlists, DNS/IP validation, and egress restrictions. Block loopback, link-local, private and metadata endpoints.",
    "CWE-327": "Replace obsolete or weak cryptographic algorithms and use modern, reviewed libraries with secure defaults.",
}


def remediation_for_cwes(cwes: list[str] | None) -> str:
    for cwe in cwes or []:
        hint = _CWE_REMEDIATIONS.get(str(cwe).upper())
        if hint:
            return hint
    return "Review the affected code path and its data flow, confirm exploitability, then apply the secure coding guidance for the reported rule. Re-run the scanner after the fix."


def remediation_for_dependency(package: str | None, fixed_version: str | None) -> str:
    if fixed_version:
        label = package or "the affected dependency"
        return f"Upgrade {label} to {fixed_version} or a later patched release, then rebuild and rescan the lockfile."
    return "Check the advisory for a supported patched release. Upgrade the dependency and regenerate the lockfile; if no fix exists, assess reachability and apply a documented mitigation."
