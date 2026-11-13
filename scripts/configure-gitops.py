#!/usr/bin/env python3
"""Render the non-secret Argo CD values file from the provisioned dev Terraform outputs."""

from __future__ import annotations

import re
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
TF_DIR = ROOT / "infrastructure" / "terraform" / "environments" / "dev"
TEMPLATE = ROOT / "charts" / "hello-api" / "values-gitops.yaml.example"
OUTPUT = ROOT / "charts" / "hello-api" / "values-gitops.yaml"


def terraform_output(name: str) -> str:
    try:
        result = subprocess.run(
            ["terraform", f"-chdir={TF_DIR}", "output", "-raw", name],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("Terraform CLI is required and must be available on PATH.") from exc
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or f"terraform output {name} failed"
        raise RuntimeError(message) from exc

    value = result.stdout.strip()
    if not value:
        raise RuntimeError(f"Terraform output {name} is empty.")
    return value


def main() -> int:
    if not TEMPLATE.is_file():
        print(f"Template not found: {TEMPLATE}", file=sys.stderr)
        return 1

    try:
        acr_login_server = terraform_output("acr_login_server")
        client_id = terraform_output("hello_api_identity_client_id")
        key_vault_uri = terraform_output("key_vault_uri")
        uuid.UUID(client_id)
    except (RuntimeError, ValueError) as exc:
        print(f"Could not configure GitOps values: {exc}", file=sys.stderr)
        return 1

    if not re.fullmatch(r"[a-z0-9.-]+", acr_login_server):
        print("Terraform returned an unexpected ACR login server value.", file=sys.stderr)
        return 1

    parsed_vault_uri = urlparse(key_vault_uri)
    if (
        parsed_vault_uri.scheme != "https"
        or not parsed_vault_uri.hostname
        or not parsed_vault_uri.hostname.endswith(".vault.azure.net")
    ):
        print("Terraform returned an unexpected Key Vault URI.", file=sys.stderr)
        return 1

    content = TEMPLATE.read_text(encoding="utf-8")
    replacements = {
        "REPLACE_WITH_ACR_LOGIN_SERVER": acr_login_server,
        "REPLACE_WITH_HELLO_API_CLIENT_ID": client_id,
        "REPLACE_WITH_KEY_VAULT_URI": key_vault_uri,
    }

    for marker, value in replacements.items():
        if marker not in content:
            print(f"Expected template marker is missing: {marker}", file=sys.stderr)
            return 1
        content = content.replace(marker, value)

    if "REPLACE_WITH_" in content:
        print("Unresolved placeholders remain in the GitOps values file.", file=sys.stderr)
        return 1

    OUTPUT.write_text(content, encoding="utf-8")
    print(f"Created {OUTPUT.relative_to(ROOT)} from Terraform outputs.")
    print("The file contains infrastructure identifiers, not secret values.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
