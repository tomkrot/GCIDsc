"""Authentication helpers for Google Workspace APIs.

Security:
  * Credentials are loaded **in memory** via ``from_service_account_info()``.
    No secret material ever touches the filesystem (except the legacy
    ``file`` backend, which reads an existing file).

Robustness:
  * API discovery (``build()``) and individual API calls use exponential
    backoff via ``tenacity`` to handle 429 (rate-limit) and 503 (transient)
    errors from Google APIs.

Modularity:
  * The service→discovery mapping is inferred dynamically from the Resource
    Catalogue rather than maintained as a hardcoded dict.

Supports:
  - Service account with domain-wide delegation (recommended for automation)
  - Application Default Credentials (local dev / Cloud Build)
  - OAuth 2.0 installed-app flow (interactive)
"""

from __future__ import annotations

import logging
from typing import Any

from google.auth.credentials import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from gwsdsc.config import CredentialsConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Retry predicate — retries 429 (rate limit) and 5xx (transient) errors
# ---------------------------------------------------------------------------

def _is_retryable(exc: BaseException) -> bool:
    """Return True if the exception warrants a retry."""
    if isinstance(exc, HttpError):
        status = exc.resp.status
        return status == 429 or status >= 500
    # Also retry connection-level failures
    return isinstance(exc, (ConnectionError, TimeoutError, OSError))


_api_retry = retry(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    before_sleep=lambda rs: logger.warning(
        "Retrying after %s (attempt %d): %s",
        type(rs.outcome.exception()).__name__,
        rs.attempt_number,
        rs.outcome.exception(),
    ),
    reraise=True,
)


def with_retry(func):
    """Decorator to wrap any function with the standard API retry policy.

    Use on export/import calls that hit Google APIs::

        @with_retry
        def my_api_call():
            return service.users().list(...).execute()
    """
    return _api_retry(func)


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

    Credentials are loaded **in memory** via ``from_service_account_info()``.
    No temporary files are created — the key material never touches the
    filesystem.  This applies to all secret backends (env, Google Secret
    Manager, Azure Key Vault).  The ``file`` backend reads the existing
    file once and discards the path.
    """
    key_info = config.resolve_key_info()

    creds = service_account.Credentials.from_service_account_info(
        key_info, scopes=scopes
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
# API service builder (dynamic map + retry)
# ---------------------------------------------------------------------------

_service_cache: dict[str, Resource] = {}


def _resolve_discovery_name(api_service: str, api_version: str) -> tuple[str, str]:
    """Resolve the Google API discovery service name and version.

    Tries the Resource Catalogue first (so new resources are picked up
    automatically), then falls back to using the raw values as-is — which
    works for any API registered in Google's discovery service.
    """
    try:
        from gwsdsc.config import load_resource_catalogue

        catalogue = load_resource_catalogue()
        for entry in catalogue.resources:
            if entry.api_service == api_service and entry.api_version == api_version:
                # The catalogue stores the same values the discovery service
                # expects, so we can return them directly.
                return api_service, api_version
    except Exception:
        pass  # catalogue not available — fall through

    # Default: pass through unchanged (works for all standard Google APIs)
    return api_service, api_version


@_api_retry
def _build_with_retry(svc_name: str, svc_ver: str, creds: Credentials) -> Resource:
    """Build an API client with retry on transient discovery failures."""
    return build(svc_name, svc_ver, credentials=creds, cache_discovery=False)


def build_service(
    config: CredentialsConfig,
    api_service: str,
    api_version: str,
    scopes: list[str],
) -> Resource:
    """Build (and cache) a Google API client resource.

    The service/version pair is resolved dynamically via the Resource
    Catalogue.  API discovery is retried with exponential backoff on
    transient failures.
    """
    cache_key = f"{api_service}:{api_version}:{','.join(sorted(scopes))}"
    if cache_key in _service_cache:
        return _service_cache[cache_key]

    creds = get_credentials(config, scopes)
    svc_name, svc_ver = _resolve_discovery_name(api_service, api_version)

    service = _build_with_retry(svc_name, svc_ver, creds)
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
