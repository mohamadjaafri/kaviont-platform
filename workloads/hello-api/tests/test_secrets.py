from types import SimpleNamespace

import pytest
from azure.core.exceptions import ResourceNotFoundError

from app import secrets


class FakeCredential:
    def __init__(self, **_kwargs):
        self.closed = False

    def close(self):
        self.closed = True


class FakeClient:
    def __init__(self, *, vault_url, credential):
        self.vault_url = vault_url
        self.credential = credential
        self.closed = False
        self.result = SimpleNamespace(value="do-not-return-this-secret")

    def get_secret(self, _secret_name):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    def close(self):
        self.closed = True


def test_secret_check_returns_true_for_non_empty_secret(monkeypatch):
    credential = FakeCredential()
    client = FakeClient(vault_url="https://example.vault.azure.net/", credential=credential)
    monkeypatch.setattr(secrets, "DefaultAzureCredential", lambda **_kwargs: credential)
    monkeypatch.setattr(secrets, "SecretClient", lambda **kwargs: client)

    assert secrets.secret_is_configured("https://example.vault.azure.net/", "demo-secret") is True
    assert credential.closed is True
    assert client.closed is True


def test_secret_check_returns_false_when_secret_is_missing(monkeypatch):
    credential = FakeCredential()
    client = FakeClient(vault_url="https://example.vault.azure.net/", credential=credential)
    client.result = ResourceNotFoundError("not found")
    monkeypatch.setattr(secrets, "DefaultAzureCredential", lambda **_kwargs: credential)
    monkeypatch.setattr(secrets, "SecretClient", lambda **kwargs: client)

    assert secrets.secret_is_configured("https://example.vault.azure.net/", "demo-secret") is False
    assert credential.closed is True
    assert client.closed is True


def test_secret_check_propagates_access_errors_and_closes_clients(monkeypatch):
    credential = FakeCredential()
    client = FakeClient(vault_url="https://example.vault.azure.net/", credential=credential)
    client.result = RuntimeError("access denied")
    monkeypatch.setattr(secrets, "DefaultAzureCredential", lambda **_kwargs: credential)
    monkeypatch.setattr(secrets, "SecretClient", lambda **kwargs: client)

    with pytest.raises(RuntimeError, match="access denied"):
        secrets.secret_is_configured("https://example.vault.azure.net/", "demo-secret")

    assert credential.closed is True
    assert client.closed is True
