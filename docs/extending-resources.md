# Extending GoogleWorkspaceDsc with Custom Resources

This guide explains how to add new resource modules to the framework.

---

## Architecture

Every resource module inherits from `gwsdsc.resources.base.BaseResource` and
implements a standard interface. The framework discovers modules through the
`REGISTRY` dict in `gwsdsc/resources/__init__.py`.

## Creating a New Resource

### 1. Create the module file

Create `src/gwsdsc/resources/my_resource.py`:

```python
from __future__ import annotations
from typing import Any
from gwsdsc.resources.base import BaseResource


class MyNewResource(BaseResource):
    # --- Required class attributes ---
    NAME = "my_resource"                    # used in CLI, config, file names
    API_SERVICE = "admin"                   # Google API service name
    API_VERSION = "directory_v1"            # API version
    SCOPES = [                              # OAuth scopes needed
        "https://www.googleapis.com/auth/admin.directory...",
    ]
    IMPORTABLE = True                       # can we apply this back?
    DESCRIPTION = "My custom resource"

    # --- Optional overrides ---
    STRIP_FIELDS = ["etag", "kind"]         # fields to remove before storing
    KEY_FIELDS = ["id"]                     # fields used for matching

    def export_all(self) -> list[dict[str, Any]]:
        """Fetch all instances from the Google API."""
        # Use self.service to access the API client
        # Use self._paginate() for paginated endpoints
        response = self.service.myresource().list(
            customer=self.customer_id
        ).execute()
        return response.get("items", [])

    def get_key(self, item: dict[str, Any]) -> str:
        """Return a unique key for matching across snapshots."""
        return item.get("uniqueField", item.get("id", ""))

    def import_one(
        self,
        desired: dict[str, Any],
        existing: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Create or update a single resource instance."""
        body = {
            k: v for k, v in desired.items()
            if k not in ("id", *self.STRIP_FIELDS)
        }
        if existing:
            return self.service.myresource().update(
                resourceId=existing["id"], body=body
            ).execute()
        else:
            return self.service.myresource().insert(body=body).execute()

    def delete_one(self, existing: dict[str, Any]) -> None:
        """Optional: delete a resource instance."""
        self.service.myresource().delete(
            resourceId=existing["id"]
        ).execute()
```

### 2. Register the module

Add your class to `src/gwsdsc/resources/__init__.py`:

```python
from gwsdsc.resources.my_resource import MyNewResource

REGISTRY: dict[str, type[BaseResource]] = {
    # ... existing entries ...
    MyNewResource.NAME: MyNewResource,
}
```

### 3. Add to the catalogue

Either add an entry to `config/resources.yaml` or add a built-in entry
in `gwsdsc/config.py :: _builtin_catalogue()`.

### 4. Add OAuth scopes

Update `docs/authentication.md` with any new scopes, and ensure
domain-wide delegation includes them.

### 5. Test

```bash
gwsdsc export --resources my_resource --config config/tenant.yaml
gwsdsc catalogue   # verify it appears
```

## Tips

- **Always use `self._call_api(request)`** instead of `request.execute()` — this wraps every API call with exponential backoff retry on 429/5xx errors
- Use `self._paginate()` for endpoints that return paginated results (it uses `_call_api` internally)
- Use `self.clean()` to strip ephemeral fields before storage
- Use `self.options` to read per-resource config from `export_options`
- The `get_key()` method is critical for correct diffing — choose a
  stable, unique identifier (email, path, name — not a volatile ID
  if possible)
- Set `IMPORTABLE = False` for read-only resources
- The `API_SERVICE` and `API_VERSION` fields are used to dynamically
  resolve the Google API discovery endpoint — no need to register in
  a separate service map
