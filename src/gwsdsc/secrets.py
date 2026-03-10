"""Secrets Manager abstraction — Azure Key Vault and Google Secret Manager.

Instead of referencing plain file paths for credentials, gwsdsc can
retrieve secrets at runtime from a vault.  This keeps credentials out
of config files, Git history, and pipeline logs.

Supported backends:
  * **google_secret_manager** — Google Cloud Secret Manager
  * **azure_key_vault** — Azure Key Vault (via azure-identity + azure-keyvault-secrets)
  * **env** — Environment variable (simple fallback)
  * **file** — Plain file path (legacy, not recommended)

Configuration in ``tenant.yaml``::

    credentials:
      secret_backend: google_secret_manager     # or azure_key_vault / env / file
      secret_ref: "projects/my-project/secrets/gwsdsc-sa-key/versions/latest"
      # --- Azure Key Vault options ---
      # azure_vault_url: "https://my-vault.vault.azure.net"
      # azure_secret_name: "gwsdsc-sa-key"
      # azure_tenant_id: "..."        # optional — for SP auth
      # azure_client_id: "..."        # optional
      # azure_client_secret_env: "AZURE_CLIENT_SECRET"  # env var holding SP secret
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_credentials_to_file(config: dict[str, Any]) -> str:
    """Resolve a secret reference to a temporary file path containing the key JSON.

    Parameters
    ----------
    config
        The ``credentials`` section of the tenant config, as a dict.
        Must contain ``secret_backend`` and a backend-specific reference.

    Returns
    -------
    str
        Path to a temporary file holding the service-account JSON key.
        The caller should not delete this file during the process lifetime.
    """
    backend = config.get("secret_backend", "file")

    if backend == "file":
        return _resolve_file(config)
    elif backend == "env":
        return _resolve_env(config)
    elif backend == "google_secret_manager":
        return _resolve_google_secret_manager(config)
    elif backend == "azure_key_vault":
        return _resolve_azure_key_vault(config)
    else:
        raise ValueError(
            f"Unknown secret_backend '{backend}'. "
            "Supported: google_secret_manager, azure_key_vault, env, file"
        )


# ---------------------------------------------------------------------------
# Backend: plain file
# ---------------------------------------------------------------------------


def _resolve_file(config: dict[str, Any]) -> str:
    """Legacy: use a plain file path or $ENV_VAR pointing to one."""
    path = config.get("service_account_key_path", "")
    if path.startswith("$"):
        path = os.environ.get(path.lstrip("$"), path)
    if not path or not Path(path).exists():
        raise FileNotFoundError(f"Service account key not found: {path}")
    return path


# ---------------------------------------------------------------------------
# Backend: environment variable (base64 or raw JSON)
# ---------------------------------------------------------------------------


def _resolve_env(config: dict[str, Any]) -> str:
    """Read the key JSON from an environment variable."""
    env_var = config.get("secret_ref") or config.get("secret_env", "GWS_SA_KEY_JSON")
    raw = os.environ.get(env_var)
    if not raw:
        raise EnvironmentError(f"Environment variable '{env_var}' is not set or empty")

    # Detect base64
    import base64

    try:
        decoded = base64.b64decode(raw, validate=True).decode("utf-8")
        json.loads(decoded)  # validate it's JSON
        raw = decoded
    except Exception:
        pass  # assume raw JSON

    return _write_temp_key(raw)


# ---------------------------------------------------------------------------
# Backend: Google Secret Manager
# ---------------------------------------------------------------------------


def _resolve_google_secret_manager(config: dict[str, Any]) -> str:
    """Retrieve a secret from Google Cloud Secret Manager.

    ``secret_ref`` should be a full resource name::

        projects/<project>/secrets/<name>/versions/<version>

    Or just ``<name>`` (project is auto-detected, version defaults to ``latest``).
    """
    try:
        from google.cloud import secretmanager
    except ImportError:
        raise ImportError(
            "google-cloud-secret-manager is required for secret_backend=google_secret_manager. "
            "Install it with: pip install google-cloud-secret-manager"
        )

    client = secretmanager.SecretManagerServiceClient()

    ref = config.get("secret_ref", "")
    if not ref:
        raise ValueError("credentials.secret_ref is required for google_secret_manager backend")

    # If it's not a full resource name, build one
    if not ref.startswith("projects/"):
        project_id = config.get("google_project_id") or _detect_gcp_project()
        version = config.get("secret_version", "latest")
        ref = f"projects/{project_id}/secrets/{ref}/versions/{version}"

    logger.info("Fetching secret from Google Secret Manager: %s", ref)
    response = client.access_secret_version(request={"name": ref})
    payload = response.payload.data.decode("UTF-8")

    # Validate it's JSON
    json.loads(payload)
    return _write_temp_key(payload)


def _detect_gcp_project() -> str:
    """Auto-detect the current GCP project from metadata or env."""
    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT")
    if project:
        return project
    # Try metadata server
    try:
        import urllib.request

        req = urllib.request.Request(
            "http://metadata.google.internal/computeMetadata/v1/project/project-id",
            headers={"Metadata-Flavor": "Google"},
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.read().decode("utf-8").strip()
    except Exception:
        raise ValueError(
            "Cannot auto-detect GCP project. Set credentials.google_project_id "
            "or the GOOGLE_CLOUD_PROJECT environment variable."
        )


# ---------------------------------------------------------------------------
# Backend: Azure Key Vault
# ---------------------------------------------------------------------------


def _resolve_azure_key_vault(config: dict[str, Any]) -> str:
    """Retrieve a secret from Azure Key Vault.

    Required config fields:
      * ``azure_vault_url`` — e.g. ``https://my-vault.vault.azure.net``
      * ``azure_secret_name`` — the secret name in the vault

    Authentication uses ``DefaultAzureCredential`` from the ``azure-identity``
    package, which supports Managed Identity, Azure CLI, environment variables,
    and Service Principal credentials automatically.

    Optional overrides for Service Principal auth:
      * ``azure_tenant_id``
      * ``azure_client_id``
      * ``azure_client_secret_env`` — env var name holding the SP client secret
    """
    try:
        from azure.identity import (
            ClientSecretCredential,
            DefaultAzureCredential,
        )
        from azure.keyvault.secrets import SecretClient
    except ImportError:
        raise ImportError(
            "azure-identity and azure-keyvault-secrets are required for "
            "secret_backend=azure_key_vault. Install them with:\n"
            "  pip install azure-identity azure-keyvault-secrets"
        )

    vault_url = config.get("azure_vault_url")
    secret_name = config.get("azure_secret_name")
    secret_version = config.get("azure_secret_version", "")  # empty = latest

    if not vault_url:
        raise ValueError("credentials.azure_vault_url is required for azure_key_vault backend")
    if not secret_name:
        raise ValueError("credentials.azure_secret_name is required for azure_key_vault backend")

    # Build credential
    tenant_id = config.get("azure_tenant_id")
    client_id = config.get("azure_client_id")
    client_secret_env = config.get("azure_client_secret_env")

    if tenant_id and client_id and client_secret_env:
        client_secret = os.environ.get(client_secret_env, "")
        if not client_secret:
            raise EnvironmentError(
                f"Environment variable '{client_secret_env}' required for Azure SP auth is not set"
            )
        credential = ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
        )
        logger.info("Using Azure Service Principal credential for Key Vault")
    else:
        credential = DefaultAzureCredential()
        logger.info("Using Azure DefaultAzureCredential for Key Vault")

    client = SecretClient(vault_url=vault_url, credential=credential)

    logger.info(
        "Fetching secret '%s' from Azure Key Vault: %s", secret_name, vault_url
    )
    retrieved = client.get_secret(secret_name, version=secret_version or None)
    payload = retrieved.value

    if not payload:
        raise ValueError(f"Secret '{secret_name}' in {vault_url} is empty")

    # Detect base64-encoded payload
    import base64

    try:
        decoded = base64.b64decode(payload, validate=True).decode("utf-8")
        json.loads(decoded)
        payload = decoded
    except Exception:
        pass  # assume raw JSON

    json.loads(payload)  # validate
    return _write_temp_key(payload)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_temp_key(json_content: str) -> str:
    """Write key JSON to a secure temp file and return its path."""
    fd, path = tempfile.mkstemp(prefix="gwsdsc-key-", suffix=".json")
    try:
        os.write(fd, json_content.encode("utf-8"))
    finally:
        os.close(fd)
    os.chmod(path, 0o600)
    logger.debug("Wrote temporary key file: %s", path)
    return path
