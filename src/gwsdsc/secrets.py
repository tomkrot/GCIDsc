"""Secrets Manager abstraction — Azure Key Vault and Google Secret Manager.

Credentials are resolved entirely **in memory** — no temporary files are
written to disk.  Each backend returns a parsed ``dict`` (the service
account JSON key) which the auth layer passes directly to
``google.oauth2.service_account.Credentials.from_service_account_info()``.

Supported backends:
  * **google_secret_manager** — Google Cloud Secret Manager
  * **azure_key_vault** — Azure Key Vault (via azure-identity + azure-keyvault-secrets)
  * **env** — Environment variable (simple fallback)
  * **file** — Plain file path (legacy, not recommended)

Security properties:
  * Secret material never touches the filesystem (except ``file`` backend).
  * No temporary files, no cleanup required, no residual key on disk.
  * Base64 decoding failures are logged explicitly.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_credentials(config: dict[str, Any]) -> dict[str, Any]:
    """Resolve a secret reference to an in-memory service account key dict.

    Parameters
    ----------
    config
        The ``credentials`` section of the tenant config, as a dict.
        Must contain ``secret_backend`` and a backend-specific reference.

    Returns
    -------
    dict
        Parsed service-account JSON key, ready for
        ``Credentials.from_service_account_info()``.

    Raises
    ------
    ValueError
        If the backend is unknown or the resolved payload is not valid JSON.
    FileNotFoundError
        If the ``file`` backend cannot locate the key file.
    EnvironmentError
        If required environment variables are not set.
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


def _resolve_file(config: dict[str, Any]) -> dict[str, Any]:
    """Legacy: read a JSON key file from disk."""
    path = config.get("service_account_key_path", "")
    if path.startswith("$"):
        path = os.environ.get(path.lstrip("$"), path)
    if not path or not Path(path).exists():
        raise FileNotFoundError(f"Service account key not found: {path}")

    with open(path) as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Backend: environment variable (base64 or raw JSON)
# ---------------------------------------------------------------------------


def _resolve_env(config: dict[str, Any]) -> dict[str, Any]:
    """Read the key JSON from an environment variable."""
    env_var = config.get("secret_ref") or config.get("secret_env", "GWS_SA_KEY_JSON")
    raw = os.environ.get(env_var)
    if not raw:
        raise EnvironmentError(f"Environment variable '{env_var}' is not set or empty")

    return _decode_payload(raw, source=f"env:{env_var}")


# ---------------------------------------------------------------------------
# Backend: Google Secret Manager
# ---------------------------------------------------------------------------


def _resolve_google_secret_manager(config: dict[str, Any]) -> dict[str, Any]:
    """Retrieve a secret from Google Cloud Secret Manager.

    ``secret_ref`` should be a full resource name::

        projects/<project>/secrets/<n>/versions/<version>

    Or just ``<n>`` (project is auto-detected, version defaults to ``latest``).
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

    return _decode_payload(payload, source=f"gsm:{ref}")


def _detect_gcp_project() -> str:
    """Auto-detect the current GCP project from metadata or env."""
    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT")
    if project:
        return project
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


def _resolve_azure_key_vault(config: dict[str, Any]) -> dict[str, Any]:
    """Retrieve a secret from Azure Key Vault.

    Required config fields:
      * ``azure_vault_url`` — e.g. ``https://my-vault.vault.azure.net``
      * ``azure_secret_name`` — the secret name in the vault

    Authentication uses ``DefaultAzureCredential`` from the ``azure-identity``
    package, which supports Managed Identity, Azure CLI, environment variables,
    and Service Principal credentials automatically.
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
    secret_version = config.get("azure_secret_version", "")

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

    return _decode_payload(payload, source=f"akv:{vault_url}/{secret_name}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _decode_payload(raw: str, source: str = "unknown") -> dict[str, Any]:
    """Decode a secret payload that may be base64-encoded or raw JSON.

    Tries base64 first; on failure falls back to raw JSON parsing.
    Uses specific exception types — never silently swallows errors.

    Parameters
    ----------
    raw
        The raw string from the secret store.
    source
        Human-readable label for log messages.

    Returns
    -------
    dict
        Parsed service-account key.

    Raises
    ------
    ValueError
        If the payload is neither valid base64(JSON) nor raw JSON.
    """
    # Attempt 1: base64-encoded JSON
    try:
        decoded_bytes = base64.b64decode(raw, validate=True)
        decoded_str = decoded_bytes.decode("utf-8")
        parsed = json.loads(decoded_str)
        if isinstance(parsed, dict):
            logger.debug("Decoded base64 payload from %s", source)
            return parsed
    except binascii.Error as exc:
        logger.debug("Base64 decode failed for %s (not base64): %s", source, exc)
    except UnicodeDecodeError as exc:
        logger.debug("Base64 payload from %s is not valid UTF-8: %s", source, exc)
    except json.JSONDecodeError as exc:
        logger.debug("Base64 payload from %s is not valid JSON: %s", source, exc)

    # Attempt 2: raw JSON
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            logger.debug("Parsed raw JSON payload from %s", source)
            return parsed
        raise ValueError(f"Payload from {source} parsed as JSON but is not a dict (got {type(parsed).__name__})")
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Payload from {source} is neither valid base64(JSON) nor raw JSON: {exc}"
        ) from exc
