"""Authentication helpers for Google Workspace APIs.

Supports:
  - Service account with domain-wide delegation (recommended for automation)
  - Application Default Credentials (local dev / Cloud Build)
  - OAuth 2.0 installed-app flow (interactive)
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from google.auth.credentials import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import Resource, build

from gwsdsc.config import CredentialsConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Credential factories
# ---------------------------------------------------------------------------


def get_credentials(config: CredentialsConfig, scopes: list[str]) -> Credentials:
    """Build credentials from the given configuration."""
    merged_scopes = list(set(config.scopes + scopes))

    if config.type == "service_account":
        return _service_account_creds(config, merged_scopes)
    elif config.type == "adc":
        return _adc_creds(merged_scopes)
    elif config.type == "oauth":
        return _oauth_creds(merged_scopes)
    else:
        raise ValueError(f"Unknown credential type: {config.type}")


def _service_account_creds(
    config: CredentialsConfig, scopes: list[str]
) -> Credentials:
    """Create service-account credentials with optional domain-wide delegation.

    The service account key is resolved via the configured ``secret_backend``:
      * ``file`` — plain file path
      * ``env`` — environment variable
      * ``google_secret_manager`` — Google Cloud Secret Manager
      * ``azure_key_vault`` — Azure Key Vault
    """
    key_path = config.resolve_key_path()

    creds = service_account.Credentials.from_service_account_file(
        key_path, scopes=scopes
    )

    if config.delegated_admin_email:
        creds = creds.with_subject(config.delegated_admin_email)
        logger.info("Using domain-wide delegation as %s", config.delegated_admin_email)

    return creds


def _adc_creds(scopes: list[str]) -> Credentials:
    """Use Application Default Credentials (gcloud auth, metadata server, etc.)."""
    import google.auth

    creds, project = google.auth.default(scopes=scopes)
    logger.info("Using ADC credentials (project=%s)", project)
    return creds


def _oauth_creds(scopes: list[str]) -> Credentials:
    """Interactive OAuth flow (for local development only)."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file("credentials.json", scopes)
    creds = flow.run_local_server(port=0)
    logger.info("OAuth flow completed")
    return creds


# ---------------------------------------------------------------------------
# API service builder
# ---------------------------------------------------------------------------

# Cache to avoid re-building the same service repeatedly
_service_cache: dict[str, Resource] = {}


def build_service(
    config: CredentialsConfig,
    api_service: str,
    api_version: str,
    scopes: list[str],
) -> Resource:
    """Build (and cache) a Google API client resource."""
    cache_key = f"{api_service}:{api_version}:{','.join(sorted(scopes))}"
    if cache_key in _service_cache:
        return _service_cache[cache_key]

    creds = get_credentials(config, scopes)

    # Map convenience names to discoverable service/version pairs
    service_map: dict[str, tuple[str, str]] = {
        ("admin", "directory_v1"): ("admin", "directory_v1"),
        ("admin", "datatransfer_v1"): ("admin", "datatransfer_v1"),
        ("chromepolicy", "v1"): ("chromepolicy", "v1"),
        ("chromemanagement", "v1"): ("chromemanagement", "v1"),
        ("gmail", "v1"): ("gmail", "v1"),
        ("groupssettings", "v1"): ("groupssettings", "v1"),
        ("cloudidentity", "v1"): ("cloudidentity", "v1"),
        ("accesscontextmanager", "v1"): ("accesscontextmanager", "v1"),
        ("vault", "v1"): ("vault", "v1"),
        ("alertcenter", "v1beta1"): ("alertcenter", "v1beta1"),
        ("licensing", "v1"): ("licensing", "v1"),
    }

    svc_name, svc_ver = service_map.get(
        (api_service, api_version), (api_service, api_version)
    )

    service = build(svc_name, svc_ver, credentials=creds, cache_discovery=False)
    _service_cache[cache_key] = service
    logger.info("Built API service: %s %s", svc_name, svc_ver)
    return service


def clear_service_cache() -> None:
    """Clear the cached API services (useful in tests)."""
    _service_cache.clear()


# ---------------------------------------------------------------------------
# Scope aggregator
# ---------------------------------------------------------------------------


def aggregate_scopes(resource_names: list[str], catalogue) -> list[str]:
    """Collect all OAuth scopes needed for the requested resources."""
    all_scopes: set[str] = set()
    by_name = {r.name: r for r in catalogue.resources}
    for name in resource_names:
        entry = by_name.get(name)
        if entry:
            all_scopes.update(entry.scopes)
    return sorted(all_scopes)
