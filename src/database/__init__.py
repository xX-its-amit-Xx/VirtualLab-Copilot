"""Database layer (SQLite) for VirtualLab-Copilot."""

from .repo import Database, ensure_database, get_database

__all__ = ["Database", "ensure_database", "get_database"]
