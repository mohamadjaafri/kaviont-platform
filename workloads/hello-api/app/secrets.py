"""Read-only Azure Key Vault secret checks for the sample API."""

from azure.core.exceptions import ResourceNotFoundError
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient


def secret_is_configured(vault_url: str, secret_name: str) -> bool:
    """Return whether a non-empty secret exists, without returning its value.

    DefaultAzureCredential supports AKS Workload Identity and local developer
    authentication through the Azure CLI. Values are never logged or returned.
    """
    credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
    client = None

    try:
        client = SecretClient(vault_url=vault_url, credential=credential)
        try:
            secret = client.get_secret(secret_name)
        except ResourceNotFoundError:
            return False
        return bool(secret.value)
    finally:
        if client is not None:
            client.close()
        credential.close()
