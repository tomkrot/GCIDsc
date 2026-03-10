"""Tests for configuration and resource registry."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gwsdsc.config import (
    TenantConfig,
    load_resource_catalogue,
    load_tenant_config,
)
from gwsdsc.resources import ALL_RESOURCE_NAMES, REGISTRY, get_resource_class
from gwsdsc.resources.base import BaseResource


class TestConfig:
    """Test configuration loading and validation."""

    def test_load_valid_config(self, tmp_path, sample_tenant_config):
        config_file = tmp_path / "tenant.yaml"
        import yaml

        config_file.write_text(yaml.dump(sample_tenant_config))

        cfg = load_tenant_config(config_file)
        assert cfg.tenant_name == "Test Tenant"
        assert cfg.primary_domain == "example.com"
        assert cfg.credentials.type == "adc"

    def test_load_missing_config_raises(self):
        with pytest.raises(FileNotFoundError):
            load_tenant_config("/nonexistent/path.yaml")

    def test_builtin_catalogue(self):
        cat = load_resource_catalogue()
        names = {r.name for r in cat.resources}
        assert "users" in names
        assert "groups" in names
        assert "org_units" in names
        assert "customer" in names

    def test_catalogue_scopes(self):
        cat = load_resource_catalogue()
        for entry in cat.resources:
            assert isinstance(entry.scopes, list)
            for scope in entry.scopes:
                assert scope.startswith("https://www.googleapis.com/auth/")


class TestRegistry:
    """Test the resource module registry."""

    def test_all_resources_registered(self):
        expected = {
            # Admin SDK
            "customer", "org_units", "users", "groups", "group_members",
            "roles", "role_assignments", "domains", "schemas", "app_access",
            "chrome_policies", "email_settings", "security",
            "calendar_resources", "mobile_devices",
            # Chrome Enterprise
            "chrome_browsers", "chrome_printers", "chromeos_telemetry",
            # Cloud Identity
            "ci_policies", "ci_saml_sso_profiles", "ci_oidc_sso_profiles",
            "ci_sso_assignments", "ci_devices", "ci_groups", "ci_user_invitations",
            # Access Context Manager
            "context_aware_access",
            # Google Vault
            "vault_retention",
            # Alert Center
            "alert_center",
            # License Manager
            "license_assignments",
            # Legacy / Other
            "admin_settings_legacy", "contact_delegation", "data_transfers",
        }
        assert expected == set(ALL_RESOURCE_NAMES)
        assert len(REGISTRY) == 32

    def test_registry_classes_inherit_base(self):
        for name, cls in REGISTRY.items():
            assert issubclass(cls, BaseResource), f"{name} must inherit BaseResource"

    def test_get_resource_class_valid(self):
        cls = get_resource_class("users")
        assert cls.NAME == "users"

    def test_get_resource_class_invalid(self):
        with pytest.raises(KeyError):
            get_resource_class("nonexistent")

    def test_all_resources_have_name(self):
        for name, cls in REGISTRY.items():
            assert cls.NAME == name
            assert cls.NAME != ""

    def test_all_resources_have_scopes(self):
        for name, cls in REGISTRY.items():
            assert len(cls.SCOPES) > 0, f"{name} has no OAuth scopes defined"

    def test_all_resources_have_description(self):
        for name, cls in REGISTRY.items():
            assert cls.DESCRIPTION != "", f"{name} has no description"

    def test_read_only_resources(self):
        read_only = {
            "domains", "app_access", "mobile_devices", "ci_devices",
            "ci_user_invitations", "chrome_browsers", "chromeos_telemetry",
            "alert_center", "admin_settings_legacy", "data_transfers",
        }
        for name in read_only:
            cls = REGISTRY[name]
            assert cls.IMPORTABLE is False, f"{name} should not be importable"


class TestReportEngine:
    """Test report generation."""

    def test_html_report(self, tmp_artifacts, tmp_path):
        from gwsdsc.engine.diff_engine import DiffEngine
        from gwsdsc.engine.report_engine import ReportEngine

        baseline, target = tmp_artifacts
        diff = DiffEngine.compare(baseline, target)

        output = tmp_path / "report.html"
        content = ReportEngine.generate(diff, format="html", output=output)

        assert output.exists()
        assert "Drift Report" in content
        assert "diana@example.com" in content  # added user

    def test_markdown_report(self, tmp_artifacts, tmp_path):
        from gwsdsc.engine.diff_engine import DiffEngine
        from gwsdsc.engine.report_engine import ReportEngine

        baseline, target = tmp_artifacts
        diff = DiffEngine.compare(baseline, target)

        content = ReportEngine.generate(diff, format="markdown")
        assert "Drift Report" in content
        assert "Total Changes" in content

    def test_json_report(self, tmp_artifacts):
        from gwsdsc.engine.diff_engine import DiffEngine
        from gwsdsc.engine.report_engine import ReportEngine

        baseline, target = tmp_artifacts
        diff = DiffEngine.compare(baseline, target)

        content = ReportEngine.generate(diff, format="json")
        parsed = json.loads(content)
        assert "total_changes" in parsed
