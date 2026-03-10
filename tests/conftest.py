"""Shared test fixtures for GoogleWorkspaceDsc."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def tmp_artifacts(tmp_path: Path):
    """Create a pair of snapshot directories for diff testing."""
    baseline = tmp_path / "baseline"
    target = tmp_path / "target"
    baseline.mkdir()
    target.mkdir()

    # --- Baseline snapshot ---
    (baseline / "_metadata.json").write_text(json.dumps({
        "tenant_name": "Test Tenant",
        "exported_at": "2025-03-01T020000Z",
    }))

    (baseline / "users.json").write_text(json.dumps([
        {"primaryEmail": "alice@example.com", "name": {"fullName": "Alice Smith"}, "orgUnitPath": "/", "suspended": False},
        {"primaryEmail": "bob@example.com", "name": {"fullName": "Bob Jones"}, "orgUnitPath": "/", "suspended": False},
        {"primaryEmail": "charlie@example.com", "name": {"fullName": "Charlie Brown"}, "orgUnitPath": "/Engineering", "suspended": False},
    ]))

    (baseline / "groups.json").write_text(json.dumps([
        {"email": "engineering@example.com", "name": "Engineering", "directMembersCount": "5"},
        {"email": "marketing@example.com", "name": "Marketing", "directMembersCount": "3"},
    ]))

    (baseline / "org_units.json").write_text(json.dumps([
        {"orgUnitPath": "/Engineering", "name": "Engineering", "parentOrgUnitPath": "/"},
        {"orgUnitPath": "/Marketing", "name": "Marketing", "parentOrgUnitPath": "/"},
    ]))

    # --- Target snapshot (with changes) ---
    (target / "_metadata.json").write_text(json.dumps({
        "tenant_name": "Test Tenant",
        "exported_at": "2025-03-09T020000Z",
    }))

    (target / "users.json").write_text(json.dumps([
        {"primaryEmail": "alice@example.com", "name": {"fullName": "Alice Smith"}, "orgUnitPath": "/", "suspended": False},
        {"primaryEmail": "bob@example.com", "name": {"fullName": "Bob Jones"}, "orgUnitPath": "/Marketing", "suspended": False},  # Changed OU
        # charlie removed
        {"primaryEmail": "diana@example.com", "name": {"fullName": "Diana Prince"}, "orgUnitPath": "/Engineering", "suspended": False},  # New user
    ]))

    (target / "groups.json").write_text(json.dumps([
        {"email": "engineering@example.com", "name": "Engineering", "directMembersCount": "4"},  # Member count changed
        {"email": "marketing@example.com", "name": "Marketing", "directMembersCount": "3"},
        {"email": "design@example.com", "name": "Design", "directMembersCount": "2"},  # New group
    ]))

    (target / "org_units.json").write_text(json.dumps([
        {"orgUnitPath": "/Engineering", "name": "Engineering", "parentOrgUnitPath": "/"},
        {"orgUnitPath": "/Marketing", "name": "Marketing", "parentOrgUnitPath": "/"},
        {"orgUnitPath": "/Design", "name": "Design", "parentOrgUnitPath": "/"},  # New OU
    ]))

    return baseline, target


@pytest.fixture
def sample_tenant_config() -> dict:
    """Return a valid tenant config dict (no real credentials)."""
    return {
        "tenant_name": "Test Tenant",
        "customer_id": "C0123test",
        "primary_domain": "example.com",
        "credentials": {
            "type": "adc",
        },
        "store": {
            "type": "local",
            "path": "/tmp/gwsdsc-test-artifacts",
        },
        "resources": ["all"],
        "exclude_resources": [],
        "export_options": {},
    }
