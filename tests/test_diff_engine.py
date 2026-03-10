"""Tests for the DiffEngine."""

from __future__ import annotations

import json

from gwsdsc.engine.diff_engine import DiffEngine


class TestDiffEngine:
    """Test suite for DiffEngine.compare()."""

    def test_detects_added_users(self, tmp_artifacts):
        baseline, target = tmp_artifacts
        result = DiffEngine.compare(baseline, target, resource_names=["users"])

        users_diff = result.resources["users"]
        added_keys = [c.key for c in users_diff.added]
        assert "diana@example.com" in added_keys

    def test_detects_removed_users(self, tmp_artifacts):
        baseline, target = tmp_artifacts
        result = DiffEngine.compare(baseline, target, resource_names=["users"])

        users_diff = result.resources["users"]
        removed_keys = [c.key for c in users_diff.removed]
        assert "charlie@example.com" in removed_keys

    def test_detects_modified_users(self, tmp_artifacts):
        baseline, target = tmp_artifacts
        result = DiffEngine.compare(baseline, target, resource_names=["users"])

        users_diff = result.resources["users"]
        modified_keys = [c.key for c in users_diff.modified]
        assert "bob@example.com" in modified_keys

    def test_detects_added_groups(self, tmp_artifacts):
        baseline, target = tmp_artifacts
        result = DiffEngine.compare(baseline, target, resource_names=["groups"])

        groups_diff = result.resources["groups"]
        added_keys = [c.key for c in groups_diff.added]
        assert "design@example.com" in added_keys

    def test_detects_added_org_units(self, tmp_artifacts):
        baseline, target = tmp_artifacts
        result = DiffEngine.compare(baseline, target, resource_names=["org_units"])

        ou_diff = result.resources["org_units"]
        added_keys = [c.key for c in ou_diff.added]
        assert "/Design" in added_keys

    def test_total_changes(self, tmp_artifacts):
        baseline, target = tmp_artifacts
        result = DiffEngine.compare(baseline, target)

        # Users: 1 added + 1 removed + 1 modified = 3
        # Groups: 1 added + 1 modified = 2
        # OUs: 1 added = 1
        assert result.total_changes >= 5

    def test_has_changes_flag(self, tmp_artifacts):
        baseline, target = tmp_artifacts
        result = DiffEngine.compare(baseline, target)
        assert result.has_changes is True

    def test_no_changes_for_identical(self, tmp_artifacts):
        baseline, _ = tmp_artifacts
        result = DiffEngine.compare(baseline, baseline)
        assert result.has_changes is False

    def test_summary_format(self, tmp_artifacts):
        baseline, target = tmp_artifacts
        result = DiffEngine.compare(baseline, target)
        summary = result.summary

        assert "total_changes" in summary
        assert "resources" in summary
        assert isinstance(summary["total_changes"], int)

    def test_to_json_serializable(self, tmp_artifacts):
        baseline, target = tmp_artifacts
        result = DiffEngine.compare(baseline, target)
        json_str = result.to_json()

        # Should be valid JSON
        parsed = json.loads(json_str)
        assert "total_changes" in parsed
        assert "resources" in parsed

    def test_empty_baseline(self, tmp_path):
        """Diff with empty baseline should show everything as added."""
        empty = tmp_path / "empty"
        empty.mkdir()
        target = tmp_path / "target"
        target.mkdir()
        (target / "users.json").write_text(json.dumps([
            {"primaryEmail": "test@example.com", "name": {"fullName": "Test"}}
        ]))

        result = DiffEngine.compare(empty, target)
        users_diff = result.resources["users"]
        assert len(users_diff.added) == 1
        assert len(users_diff.removed) == 0

    def test_empty_target(self, tmp_path):
        """Diff with empty target should show everything as removed."""
        baseline = tmp_path / "baseline"
        baseline.mkdir()
        (baseline / "users.json").write_text(json.dumps([
            {"primaryEmail": "test@example.com", "name": {"fullName": "Test"}}
        ]))
        empty = tmp_path / "empty"
        empty.mkdir()

        result = DiffEngine.compare(baseline, empty)
        users_diff = result.resources["users"]
        assert len(users_diff.removed) == 1
        assert len(users_diff.added) == 0
