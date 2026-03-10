"""Tests for the secrets abstraction layer."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import pytest

from gwsdsc.secrets import resolve_credentials_to_file


# Fake SA key for testing
_FAKE_KEY = json.dumps({
    "type": "service_account",
    "project_id": "test-project",
    "private_key_id": "abc123",
    "private_key": "-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----\n",
    "client_email": "test@test-project.iam.gserviceaccount.com",
    "client_id": "123456789",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
})


class TestFileBackend:
    """Test secret_backend=file."""

    def test_resolves_existing_file(self, tmp_path):
        key_file = tmp_path / "sa-key.json"
        key_file.write_text(_FAKE_KEY)

        path = resolve_credentials_to_file({
            "secret_backend": "file",
            "service_account_key_path": str(key_file),
        })
        assert Path(path).exists()
        assert json.loads(Path(path).read_text())["type"] == "service_account"

    def test_raises_on_missing_file(self):
        with pytest.raises(FileNotFoundError):
            resolve_credentials_to_file({
                "secret_backend": "file",
                "service_account_key_path": "/nonexistent/key.json",
            })

    def test_expands_env_var(self, tmp_path, monkeypatch):
        key_file = tmp_path / "sa-key.json"
        key_file.write_text(_FAKE_KEY)
        monkeypatch.setenv("TEST_KEY_PATH", str(key_file))

        path = resolve_credentials_to_file({
            "secret_backend": "file",
            "service_account_key_path": "$TEST_KEY_PATH",
        })
        assert Path(path).exists()


class TestEnvBackend:
    """Test secret_backend=env."""

    def test_resolves_raw_json_from_env(self, monkeypatch):
        monkeypatch.setenv("GWS_SA_KEY_JSON", _FAKE_KEY)

        path = resolve_credentials_to_file({
            "secret_backend": "env",
            "secret_ref": "GWS_SA_KEY_JSON",
        })
        assert Path(path).exists()
        content = json.loads(Path(path).read_text())
        assert content["type"] == "service_account"

    def test_resolves_base64_from_env(self, monkeypatch):
        encoded = base64.b64encode(_FAKE_KEY.encode()).decode()
        monkeypatch.setenv("GWS_SA_KEY_B64", encoded)

        path = resolve_credentials_to_file({
            "secret_backend": "env",
            "secret_ref": "GWS_SA_KEY_B64",
        })
        assert Path(path).exists()
        content = json.loads(Path(path).read_text())
        assert content["type"] == "service_account"

    def test_raises_on_unset_env(self, monkeypatch):
        monkeypatch.delenv("NONEXISTENT_VAR", raising=False)
        with pytest.raises(EnvironmentError):
            resolve_credentials_to_file({
                "secret_backend": "env",
                "secret_ref": "NONEXISTENT_VAR",
            })


class TestUnknownBackend:
    """Test unsupported backend."""

    def test_raises_on_unknown(self):
        with pytest.raises(ValueError, match="Unknown secret_backend"):
            resolve_credentials_to_file({
                "secret_backend": "unsupported_vault",
            })


class TestGoogleSecretManagerBackend:
    """Test secret_backend=google_secret_manager (mocked)."""

    def test_raises_without_ref(self):
        with pytest.raises(ValueError, match="secret_ref"):
            resolve_credentials_to_file({
                "secret_backend": "google_secret_manager",
                "secret_ref": "",
            })


class TestAzureKeyVaultBackend:
    """Test secret_backend=azure_key_vault (validation only — no live vault)."""

    def test_raises_without_vault_url(self):
        with pytest.raises(ValueError, match="azure_vault_url"):
            resolve_credentials_to_file({
                "secret_backend": "azure_key_vault",
                "azure_secret_name": "my-secret",
            })

    def test_raises_without_secret_name(self):
        with pytest.raises(ValueError, match="azure_secret_name"):
            resolve_credentials_to_file({
                "secret_backend": "azure_key_vault",
                "azure_vault_url": "https://my-vault.vault.azure.net",
            })
