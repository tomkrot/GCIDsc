"""Abstract base class for all Google Workspace resource modules.

Every resource module (users, groups, org_units, …) inherits from
``BaseResource`` and implements at minimum:

  * ``export_all()`` → list of dicts (the current state from the API)
  * ``get_key(item)`` → a unique identifier for diff / matching
  * ``import_one(desired, existing)`` → create-or-update a single item
  * ``delete_one(existing)`` → optional, for resources that support removal
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from googleapiclient.discovery import Resource

from gwsdsc.auth import build_service
from gwsdsc.config import CredentialsConfig, ResourceEntry

logger = logging.getLogger(__name__)


class BaseResource(ABC):
    """Interface that every resource module must implement."""

    # -- Class-level metadata (override in subclass) -----------------------

    NAME: str = ""                         # e.g. "users"
    API_SERVICE: str = "admin"             # e.g. "admin", "chromepolicy"
    API_VERSION: str = "directory_v1"      # e.g. "directory_v1", "v1"
    SCOPES: list[str] = []
    IMPORTABLE: bool = True
    DESCRIPTION: str = ""

    # Fields to strip before persisting (ephemeral / non-config data)
    STRIP_FIELDS: list[str] = ["etag", "kind"]

    # Fields that identify the resource (used for matching, not diffing)
    KEY_FIELDS: list[str] = ["id"]

    def __init__(
        self,
        credentials_config: CredentialsConfig,
        customer_id: str = "my_customer",
        options: dict[str, Any] | None = None,
    ) -> None:
        self.credentials_config = credentials_config
        self.customer_id = customer_id
        self.options = options or {}
        self._service: Resource | None = None

    # -- Lazy service accessor ---------------------------------------------

    @property
    def service(self) -> Resource:
        if self._service is None:
            self._service = build_service(
                config=self.credentials_config,
                api_service=self.API_SERVICE,
                api_version=self.API_VERSION,
                scopes=self.SCOPES,
            )
        return self._service

    # -- Abstract methods --------------------------------------------------

    @abstractmethod
    def export_all(self) -> list[dict[str, Any]]:
        """Return every instance of this resource from the API.

        Each dict represents a single resource instance (user, group, OU, …).
        Implementations should handle pagination automatically.
        """

    @abstractmethod
    def get_key(self, item: dict[str, Any]) -> str:
        """Return a stable, unique key that identifies *item*.

        This key is used to match exported items across snapshots and to
        correlate desired-state items with live-state during import.
        """

    def import_one(
        self,
        desired: dict[str, Any],
        existing: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Create or update a single resource instance.

        Parameters
        ----------
        desired : dict
            The desired-state configuration for this item.
        existing : dict or None
            The current live-state of the item, or ``None`` if it doesn't exist yet.

        Returns
        -------
        dict or None
            The API response, or None if no change was needed.

        Raises
        ------
        NotImplementedError
            If the resource is read-only (``IMPORTABLE = False``).
        """
        if not self.IMPORTABLE:
            raise NotImplementedError(
                f"Resource '{self.NAME}' does not support import."
            )
        raise NotImplementedError(
            f"import_one() not implemented for '{self.NAME}'"
        )

    def delete_one(self, existing: dict[str, Any]) -> None:
        """Delete a resource instance (optional — not all resources support this)."""
        raise NotImplementedError(
            f"delete_one() not implemented for '{self.NAME}'"
        )

    # -- Helpers -----------------------------------------------------------

    def clean(self, item: dict[str, Any]) -> dict[str, Any]:
        """Remove ephemeral fields that shouldn't be stored / diffed."""
        return {
            k: v
            for k, v in item.items()
            if k not in self.STRIP_FIELDS
        }

    def export_cleaned(self) -> list[dict[str, Any]]:
        """Export + clean in one step."""
        raw = self.export_all()
        return [self.clean(item) for item in raw]

    def _paginate(
        self,
        request,
        items_key: str,
        next_func=None,
    ) -> list[dict[str, Any]]:
        """Generic pagination helper.

        Parameters
        ----------
        request
            The initial API request object (already built, not yet executed).
        items_key : str
            The key in the response dict that holds the list of results.
        next_func
            Callable that returns the next-page request, or None.
            Defaults to ``request_type.list_next``.
        """
        results: list[dict[str, Any]] = []
        while request is not None:
            response = request.execute()
            results.extend(response.get(items_key, []))
            if next_func:
                request = next_func(request, response)
            else:
                request = None  # subclass should override if needed
        return results

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.NAME!r}>"
