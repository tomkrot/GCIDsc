"""Abstract base class for artifact stores."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class BaseStore(ABC):
    """Interface for versioned artifact storage."""

    @abstractmethod
    def commit(self, snapshot_dir: Path, message: str) -> str:
        """Persist a snapshot directory and return a version identifier."""

    @abstractmethod
    def list_versions(self, limit: int = 20) -> list[dict[str, Any]]:
        """List available snapshot versions (newest first)."""

    @abstractmethod
    def checkout(self, version: str, target_dir: Path) -> Path:
        """Retrieve a specific version into target_dir and return the path."""
