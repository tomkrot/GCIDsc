"""Tests for the secrets abstraction layer (in-memory, no temp files)."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import pytest

from gwsdsc.secrets import resolve_credentials, _decode_payload


# Fake SA key for testing
_FAKE_KEY = {
    "type": "service_account",
    "project_id": "test-project",
    "private_key_id": "abc123",
    "private_key": "-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----\n",
    "client_email": "test@test-project.iam.gserviceaccount.com",
    "client_id": "123456789",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
}

_FAKE_KEY_JSON = json.dumps(_FAKE_KEY)


class TestDecodePayload:
    """Test the _decode_payload helper with specific exception handling."""

    def test_decodes_raw_json(self):
        result = _decode_payload(_FAKE_KEY_JSON, source="test")
        assert result["type"] == "service_account"
        assert result["project_id"] == "test-project"

    def test_decodes_base64_json(self):
        encoded = base64.b64encode(_FAKE_KEY_JSON.encode()).decode()
        result = _decode_payload(encoded, source="test")
        assert result["type"] == "service_account"

    def test_rejects_non_json_non_base64(self):
        with pytest.raises(ValueError, match="neither valid base64"):
            _decode_payload("this is not json or base64", source="test")

    def test_rejects_base64_non_json(self):
        # Valid base64 but not JSON
        encoded = base64.b64encode(b"not json content").decode()
        # Falls through base64 (valid b64 but JSON parse fails), then
        # also fails raw JSON parse
        with pytest.raises(ValueError):
            _decode_payload(encoded, source="test")

    def test_rejects_non_dict_json(self):
        array_json = json.dumps([1, 2, 3])
        with pytest.raises(ValueError, match="not a dict"):
            _decode_payload(array_json, source="test")

    def test_returns_dict_not_path(self):
        """The core security property: result is a dict, not a file path."""
        result = _decode_payload(_FAKE_KEY_JSON, source="test")
        assert isinstance(result, dict)
        assert not isinstance(result, str)


class TestFileBackend:
    """Test secret_backend=file — returns dict from file."""

    def test_resolves_existing_file(self, tmp_path):
        key_file = tmp_path / "sa-key.json"
        key_file.write_text(_FAKE_KEY_JSON)

        result = resolve_credentials({
            "secret_backend": "file",
            "service_account_key_path": str(key_file),
        })
        assert isinstance(result, dict)
        assert result["type"] == "service_account"

    def test_raises_on_missing_file(self):
        with pytest.raises(FileNotFoundError):
            resolve_credentials({
                "secret_backend": "file",
                "service_account_key_path": "/nonexistent/key.json",
            })

    def test_expands_env_var(self, tmp_path, monkeypatch):
        key_file = tmp_path / "sa-key.json"
        key_file.write_text(_FAKE_KEY_JSON)
        monkeypatch.setenv("TEST_KEY_PATH", str(key_file))

        result = resolve_credentials({
            "secret_backend": "file",
            "service_account_key_path": "$TEST_KEY_PATH",
        })
        assert isinstance(result, dict)
        assert result["type"] == "service_account"


class TestEnvBackend:
    """Test secret_backend=env — returns dict from env var."""

    def test_resolves_raw_json(self, monkeypatch):
        monkeypatch.setenv("GWS_SA_KEY_JSON", _FAKE_KEY_JSON)

        result = resolve_credentials({
            "secret_backend": "env",
            "secret_ref": "GWS_SA_KEY_JSON",
        })
        assert isinstance(result, dict)
        assert result["type"] == "service_account"

    def test_resolves_base64(self, monkeypatch):
        encoded = base64.b64encode(_FAKE_KEY_JSON.encode()).decode()
        monkeypatch.setenv("GWS_SA_KEY_B64", encoded)

        result = resolve_credentials({
            "secret_backend": "env",
            "secret_ref": "GWS_SA_KEY_B64",
        })
        assert isinstance(result, dict)
        assert result["type"] == "service_account"

    def test_raises_on_unset_env(self, monkeypatch):
        monkeypatch.delenv("NONEXISTENT_VAR", raising=False)
        with pytest.raises(EnvironmentError):
            resolve_credentials({
                "secret_backend": "env",
                "secret_ref": "NONEXISTENT_VAR",
            })

    def test_no_temp_files_created(self, tmp_path, monkeypatch):
        """Verify no files are written to /tmp during resolution."""
        monkeypatch.setenv("GWS_TEST_KEY", _FAKE_KEY_JSON)
        import tempfile
        before = set(Path(tempfile.gettempdir()).glob("gwsdsc-key-*"))

        resolve_credentials({
            "secret_backend": "env",
            "secret_ref": "GWS_TEST_KEY",
        })

        after = set(Path(tempfile.gettempdir()).glob("gwsdsc-key-*"))
        assert before == after, "Temp files should not be created"


class TestUnknownBackend:
    def test_raises_on_unknown(self):
        with pytest.raises(ValueError, match="Unknown secret_backend"):
            resolve_credentials({"secret_backend": "unsupported_vault"})


class TestGoogleSecretManagerValidation:
    def test_raises_without_ref(self):
        with pytest.raises(ValueError, match="secret_ref"):
            resolve_credentials({
                "secret_backend": "google_secret_manager",
                "secret_ref": "",
            })


class TestAzureKeyVaultValidation:
    def test_raises_without_vault_url(self):
        with pytest.raises(ValueError, match="azure_vault_url"):
            resolve_credentials({
                "secret_backend": "azure_key_vault",
                "azure_secret_name": "my-secret",
            })

    def test_raises_without_secret_name(self):
        with pytest.raises(ValueError, match="azure_secret_name"):
            resolve_credentials({
                "secret_backend": "azure_key_vault",
                "azure_vault_url": "https://my-vault.vault.azure.net",
            })
