"""Git-based versioned artifact store.

Each export is committed to a Git repository. Snapshots are stored
in a configurable sub-directory (default ``artifacts/``), and each
commit is tagged with the export timestamp for easy retrieval.
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from git import Repo
from git.exc import InvalidGitRepositoryError

from gwsdsc.config import StoreConfig
from gwsdsc.store.base import BaseStore

logger = logging.getLogger(__name__)


class GitStore(BaseStore):
    """Persist snapshots as Git commits in a local (+ optionally remote) repo."""

    def __init__(self, config: StoreConfig) -> None:
        self.config = config
        self.repo_path = Path(config.path).resolve().parent  # repo root
        self.artifacts_dir = Path(config.path).resolve()      # artifacts sub-dir
        self.repo = self._ensure_repo()

    def commit(self, snapshot_dir: Path, message: str | None = None) -> str:
        """Stage all files in ``snapshot_dir``, commit, and optionally push."""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
        msg = (message or self.config.git_commit_message_template).format(
            timestamp=timestamp
        )

        # Copy snapshot into the artifacts directory under a timestamped folder
        dest = self.artifacts_dir / timestamp
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(snapshot_dir, dest)

        # Update "latest" symlink
        latest = self.artifacts_dir / "latest"
        if latest.is_symlink() or latest.exists():
            latest.unlink()
        latest.symlink_to(dest)

        # Stage and commit
        self.repo.index.add([str(dest), str(latest)])
        self.repo.index.commit(msg)

        # Tag
        tag_name = f"export/{timestamp}"
        self.repo.create_tag(tag_name, message=msg)

        # Push if remote configured
        if self.config.git_remote:
            try:
                remote = self.repo.remote(self.config.git_remote)
                remote.push(self.config.git_branch)
                remote.push(tags=True)
                logger.info("Pushed to remote '%s'", self.config.git_remote)
            except Exception as exc:
                logger.warning("Push failed: %s", exc)

        sha = self.repo.head.commit.hexsha[:12]
        logger.info("Committed snapshot: %s (tag=%s)", sha, tag_name)
        return sha

    def list_versions(self, limit: int = 20) -> list[dict[str, Any]]:
        """List recent export tags."""
        tags = sorted(
            self.repo.tags,
            key=lambda t: t.commit.committed_datetime,
            reverse=True,
        )
        return [
            {
                "tag": t.name,
                "sha": t.commit.hexsha[:12],
                "date": t.commit.committed_datetime.isoformat(),
                "message": t.commit.message.strip(),
            }
            for t in tags[:limit]
            if t.name.startswith("export/")
        ]

    def checkout(self, version: str, target_dir: Path) -> Path:
        """Restore a snapshot by tag name or commit SHA."""
        self.repo.git.checkout(version, "--", str(self.artifacts_dir))
        target_dir.mkdir(parents=True, exist_ok=True)
        # Find the snapshot dir inside artifacts
        for child in sorted(self.artifacts_dir.iterdir()):
            if child.is_dir() and child.name != "latest":
                shutil.copytree(child, target_dir / child.name, dirs_exist_ok=True)
        return target_dir

    def _ensure_repo(self) -> Repo:
        """Open existing Git repo or initialise a new one."""
        try:
            return Repo(self.repo_path)
        except (InvalidGitRepositoryError, Exception):
            logger.info("Initialising new Git repo at %s", self.repo_path)
            self.repo_path.mkdir(parents=True, exist_ok=True)
            repo = Repo.init(self.repo_path)
            # Initial commit
            readme = self.repo_path / "README.md"
            if not readme.exists():
                readme.write_text("# Google Workspace DSC Artifacts\n")
            repo.index.add([str(readme)])
            repo.index.commit("Initial commit — GoogleWorkspaceDsc artifacts repo")
            return repo
