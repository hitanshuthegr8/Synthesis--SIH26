"""Small SQLite connection and schema manager for Phase 1 persistence.

In-memory databases (path == ":memory:") use a single persistent connection
kept alive for the lifetime of the SQLiteDatabase instance, because SQLite
creates a brand-new empty database on every fresh connect() call when the
path is ":memory:".

File-backed databases use the normal open-per-call pattern via a context
manager that commits/rolls-back and then closes the connection.
"""
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Generator


@contextmanager
def _file_connection(path: str) -> Generator[sqlite3.Connection, None, None]:
    """Open a file-backed SQLite connection, commit/rollback, then close."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def _memory_connection(conn: sqlite3.Connection) -> Generator[sqlite3.Connection, None, None]:
    """Yield the shared in-memory connection, commit/rollback but do NOT close."""
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


class SQLiteDatabase:
    """Thin wrapper around an SQLite database file or in-memory store."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._in_memory = self.path == ":memory:"
        self._memory_conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()

    def connect(self):  # returns a context manager
        """Return a context manager yielding a ready-to-use SQLite connection.

        Usage::

            with self.connect() as conn:
                conn.execute(...)
        """
        if self._in_memory:
            with self._lock:
                if self._memory_conn is None:
                    self._memory_conn = sqlite3.connect(
                        ":memory:", check_same_thread=False
                    )
                    self._memory_conn.row_factory = sqlite3.Row
            return _memory_connection(self._memory_conn)
        else:
            return _file_connection(self.path)

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS forecasts (id INTEGER PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS observations (id INTEGER PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS model_skills (id INTEGER PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS blend_results (run_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS verification_results (run_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS forecast_cycles (run_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                """
            )
